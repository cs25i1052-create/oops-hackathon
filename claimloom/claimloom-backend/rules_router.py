"""Self-healing brand-rule suggestions, safe backtests, edits, and rollback."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

import ai_client
import cache
import db
from engine import redact_pii_same_length
from session import SessionUser, get_current_session, require_role
from rule_version import get_rules_version as _global_rules_version, set_rules_version

router = APIRouter()

MAX_PATTERN_LENGTH = 512
MAX_BACKTEST_SCANS = 100
MAX_BACKTEST_TEXT_CHARS = 4000
_memory_history: Dict[int, List[Dict[str, Any]]] = {}
_history_loaded: set[int] = set()
_past_scan_texts_cache: List[Dict[str, str]] = []
_past_scan_texts_cached_at = 0.0
_PAST_SCAN_TEXTS_TTL = 60.0


def _safe_connect():
    try:
        return db._connect()
    except Exception as exc:
        print(f"[rules_router] database connection fallback: {exc}")
        return None


class BacktestRequest(BaseModel):
    regex_pattern: Optional[str] = Field(
        default=None,
        max_length=MAX_PATTERN_LENGTH,
        validation_alias=AliasChoices("proposed_regex", "regex_pattern"),
    )


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    violation_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    severity: Optional[str] = Field(default=None, min_length=1, max_length=20)
    rule_cited: Optional[str] = Field(default=None, min_length=1, max_length=500)
    source_ref: Optional[str] = Field(default=None, max_length=500)
    rule_text: Optional[str] = Field(default=None, min_length=1, max_length=4000, validation_alias=AliasChoices("rule_text", "proposed_rule_text"))
    regex_pattern: Optional[str] = Field(default=None, max_length=MAX_PATTERN_LENGTH, validation_alias=AliasChoices("regex_pattern", "proposed_regex"))
    default_fix: Optional[str] = Field(default=None, max_length=1000)
    claim_status: Optional[str] = Field(default=None, max_length=100)
    allowed_numbers: Optional[str] = Field(default=None, max_length=500)
    applies_to: Optional[str] = Field(default=None, pattern=r"^(text|image|both)$")


class RollbackRequest(BaseModel):
    version_no: Optional[int] = Field(default=None, ge=1)


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    violation_type: str = Field(..., pattern=r"^(Factual|Tone|Terminology|Accessibility|Visual)$")
    severity: str = Field(default="Medium", pattern=r"^(High|Medium|Low)$")
    rule_cited: str = Field(..., min_length=3, max_length=500)
    source_ref: str = Field(default="Custom Workspace Guideline", max_length=500)
    rule_text: str = Field(..., min_length=5, max_length=4000)
    regex_pattern: Optional[str] = Field(default=None, max_length=MAX_PATTERN_LENGTH)
    default_fix: Optional[str] = Field(default="compliant phrasing", max_length=1000)
    applies_to: str = Field(default="text", pattern=r"^(text|image|both)$")
    workspace_id: Optional[str] = Field(default=None, max_length=64)


@router.post("/api/rules")
def create_custom_rule(
    req: RuleCreate,
    session: SessionUser = Depends(require_role("Admin")),
):
    _validate_regex(req.regex_pattern)
    if req.workspace_id and req.workspace_id != session.workspace_id:
        raise HTTPException(status_code=403, detail="Rule workspace must match the active session workspace.")
    rules, _, _ = db.get_vault()
    next_id = max((int(r.get("rule_id") or 0) for r in rules), default=20) + 1
    new_rule = {
        "rule_id": next_id,
        "workspace_id": session.workspace_id,
        **req.model_dump(),
        "claim_status": None,
        "allowed_numbers": None,
    }
    next_version = _global_rules_version() + 1
    new_rule["version_no"] = next_version
    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO public.brand_rules
                       (rule_id, workspace_id, version_no, violation_type, severity, rule_cited, source_ref, rule_text, regex_pattern, default_fix, applies_to)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        next_id, session.workspace_id, next_version, req.violation_type, req.severity, req.rule_cited,
                        req.source_ref, req.rule_text, req.regex_pattern,
                        req.default_fix, req.applies_to,
                    ),
                )
            conn.commit()
            cached_rules = db._cache.setdefault("rules", [])
            cached_rules[:] = [r for r in cached_rules if int(r.get("rule_id", -1)) != next_id]
            cached_rules.append(new_rule)
        except Exception as exc:
            conn.rollback()
            raise HTTPException(status_code=503, detail=f"Could not create rule: {exc}") from exc
        finally:
            conn.close()
    else:
        db._cache.setdefault("rules", []).append(new_rule)
    set_rules_version(next_version)
    cache.invalidate_cache()
    return {"status": "created", "rule": new_rule, "rules_version": _global_rules_version()}


def _get_rule(rule_id: int) -> Dict[str, Any]:
    rule = db.rules_by_id().get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Unknown rule_id {rule_id}.")
    return dict(rule)


def _parse_scan_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if not payload:
        return None
    try:
        value = payload if isinstance(payload, dict) else json.loads(payload)
        if not isinstance(value, dict):
            return None
        text = value.get("redacted_text") or value.get("text_snapshot") or ""
        return {"scan_id": value.get("scan_id"), "text": str(text)} if text else None
    except Exception:
        return None


def _past_scan_texts() -> List[Dict[str, str]]:
    global _past_scan_texts_cached_at, _past_scan_texts_cache
    now = time.monotonic()
    try:
        import main
        memory_samples = [
            {"scan_id": str(scan_id), "text": str(data.get("redacted_text") or "")}
            for scan_id, data in reversed(main._mem_scans.items())
            if data.get("redacted_text")
        ][:MAX_BACKTEST_SCANS]
    except Exception:
        memory_samples = []
    if memory_samples:
        result = [{**s, "text": s["text"][:MAX_BACKTEST_TEXT_CHARS]} for s in memory_samples]
        _past_scan_texts_cache = result
        _past_scan_texts_cached_at = now
        return [dict(item) for item in result]
    if now - _past_scan_texts_cached_at < _PAST_SCAN_TEXTS_TTL:
        return [dict(item) for item in _past_scan_texts_cache]
    samples: List[Dict[str, str]] = []
    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT scan_id, payload FROM public.scans ORDER BY created_at DESC LIMIT %s", (MAX_BACKTEST_SCANS,))
                for scan_id, payload in cur.fetchall():
                    item = _parse_scan_payload(payload)
                    if item:
                        item["scan_id"] = str(scan_id)
                        samples.append(item)
                if len(samples) < MAX_BACKTEST_SCANS:
                    cur.execute(
                        "SELECT scan_id, redacted_text FROM public.scan_documents ORDER BY created_at DESC LIMIT %s",
                        (MAX_BACKTEST_SCANS - len(samples),),
                    )
                    seen = {s["scan_id"] for s in samples}
                    for scan_id, text in cur.fetchall():
                        if text and str(scan_id) not in seen:
                            samples.append({"scan_id": str(scan_id), "text": str(text)})
        except Exception as exc:
            print(f"[rules_router] past scan load fallback: {exc}")
        finally:
            conn.close()
    if not samples:
        try:
            import main
            samples = [
                {"scan_id": str(scan_id), "text": str(data.get("redacted_text") or "")}
                for scan_id, data in reversed(main._mem_scans.items())
                if data.get("redacted_text")
            ][:MAX_BACKTEST_SCANS]
        except Exception:
            pass
    result = [{**s, "text": s["text"][:MAX_BACKTEST_TEXT_CHARS]} for s in samples[:MAX_BACKTEST_SCANS]]
    _past_scan_texts_cache = result
    _past_scan_texts_cached_at = now
    return [dict(item) for item in result]


def _contains_nested_repeat_or_branch(nodes: Any, inside_repeat: bool = False) -> bool:
    """Conservative regex safety check: no quantified group containing another
    quantifier or alternation, the common source of catastrophic backtracking."""
    import re._constants as constants

    repeat_ops = {constants.MAX_REPEAT, constants.MIN_REPEAT}
    if hasattr(constants, "POSSESSIVE_REPEAT"):
        repeat_ops.add(constants.POSSESSIVE_REPEAT)
    for op, arg in nodes:
        if op in repeat_ops:
            _min_repeat, max_repeat, child = arg
            unbounded = max_repeat == constants.MAXREPEAT
            if inside_repeat and unbounded:
                return True
            if _contains_nested_repeat_or_branch(child, inside_repeat=inside_repeat or unbounded):
                return True
        elif op is constants.SUBPATTERN:
            if _contains_nested_repeat_or_branch(arg[-1], inside_repeat=inside_repeat):
                return True
        elif op is constants.BRANCH:
            if inside_repeat or any(_contains_nested_repeat_or_branch(branch, inside_repeat=inside_repeat) for branch in arg[1]):
                return True
    return False


def _validate_regex(pattern: Optional[str]) -> Optional[str]:
    if pattern is None or pattern == "":
        return None
    if len(pattern.strip()) < 3:
        raise HTTPException(status_code=422, detail="Regex pattern is too short/broad (min 3 chars).")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise HTTPException(status_code=422, detail=f"Regex exceeds {MAX_PATTERN_LENGTH} characters.")
    if re.search(r"\\[1-9]|\(\?P=", pattern):
        raise HTTPException(status_code=422, detail="Regex backreferences are not allowed in editable brand rules.")
    try:
        compiled = re.compile(pattern)
        if compiled.search("ClaimLoom Creators build compliant enterprise assets."):
            raise HTTPException(status_code=422, detail="Regex is overly broad and flags clean baseline copy.")
        import re._parser as parser
        parsed = parser.parse(pattern, 0)
        if _contains_nested_repeat_or_branch(parsed):
            raise HTTPException(status_code=422, detail="Regex has a nested or ambiguous repetition that could cause excessive backtracking.")
        return pattern
    except HTTPException:
        raise
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {exc}") from exc


def _version_and_history(rule_id: int) -> Tuple[int, List[Dict[str, Any]]]:
    if _history_loaded is True or rule_id in _history_loaded or rule_id in _memory_history:
        history = list(_memory_history.get(rule_id, []))
        return max((h["version_no"] for h in history), default=int(_get_rule(rule_id).get("version_no") or 1)), history
    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version_no, old_rule_text, old_pattern, changed_by, created_at FROM public.rule_versions WHERE rule_id = %s ORDER BY version_no ASC, id ASC", (rule_id,))
                history = [
                    {"version_no": int(r[0]), "rule_text": r[1], "regex_pattern": r[2], "changed_by": r[3], "created_at": str(r[4])}
                    for r in cur.fetchall()
                ]
                _memory_history[rule_id] = history
                _history_loaded.add(rule_id)
                return max((h["version_no"] for h in history), default=1), history
        except Exception as exc:
            print(f"[rules_router] rule history unavailable: {exc}")
        finally:
            conn.close()
    history = list(_memory_history.get(rule_id, []))
    _history_loaded.add(rule_id)
    return max((h["version_no"] for h in history), default=int(_get_rule(rule_id).get("version_no") or 1)), history


def _save_rule_change(rule_id: int, old_rule: Dict[str, Any], new_values: Dict[str, Any], changed_by: str) -> int:
    current_version, _ = _version_and_history(rule_id)
    next_version = _global_rules_version() + 1
    history = _memory_history.setdefault(rule_id, [])
    history.append({"version_no": current_version, "rule_text": old_rule.get("rule_text"), "regex_pattern": old_rule.get("regex_pattern"), "changed_by": changed_by, "created_at": None})
    history.append({"version_no": next_version, "rule_text": new_values.get("rule_text", old_rule.get("rule_text")), "regex_pattern": new_values.get("regex_pattern", old_rule.get("regex_pattern")), "changed_by": changed_by, "created_at": None})
    _history_loaded.add(rule_id)
    rules = db._cache.setdefault("rules", [])
    for rule in rules:
        if int(rule.get("rule_id", -1)) == rule_id:
            rule.update(new_values)
            rule["version_no"] = next_version
            break
    else:
        rules.append({**old_rule, **new_values, "rule_id": rule_id, "version_no": next_version})
    # Keep local changes in the rule cache even while Neon persistence is pending.
    db._cache["at"] = time.time()
    db._cache["ttl"] = max(int(db._cache.get("ttl") or 0), 24 * 60 * 60)

    def _persist_rule_change() -> None:
        conn = _safe_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO public.rule_versions (rule_id, version_no, old_rule_text, old_pattern, changed_by) VALUES (%s, %s, %s, %s, %s)",
                    (rule_id, current_version, old_rule.get("rule_text"), old_rule.get("regex_pattern"), changed_by),
                )
                assignments = ", ".join(f"{column} = %s" for column in new_values)
                values = [new_values[column] for column in new_values]
                cur.execute(f"UPDATE public.brand_rules SET {assignments} WHERE rule_id = %s", (*values, rule_id))
                if cur.rowcount == 0:
                    raise RuntimeError(f"Unknown rule_id {rule_id}")
                cur.execute(
                    "INSERT INTO public.rule_versions (rule_id, version_no, old_rule_text, old_pattern, changed_by) VALUES (%s, %s, %s, %s, %s)",
                    (rule_id, next_version, new_values.get("rule_text", old_rule.get("rule_text")), new_values.get("regex_pattern", old_rule.get("regex_pattern")), changed_by),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[rules_router] rule persistence skipped: {exc}")
        finally:
            conn.close()

    import threading
    threading.Thread(target=_persist_rule_change, daemon=True, name="rule-change-persist").start()
    set_rules_version(next_version)
    cache.invalidate_cache()
    return next_version


@router.post("/api/rules/{rule_id}/rewrite")
def rewrite_rule(rule_id: int, session: SessionUser = Depends(require_role("Reviewer", "Admin"))):
    rule = _get_rule(rule_id)
    event_reasons = [
        str(event.get("reason") or "").strip()
        for event in db.get_flag_events()
        if int(event.get("rule_id") or -1) == rule_id
        and event.get("action") in {"Overridden", "Dismissed"}
        and str(event.get("reason") or "").strip()
    ][:12]
    event_reasons = [redact_pii_same_length(reason)[0] for reason in event_reasons]
    system = (
        "You are a precise brand-governance rule editor. Return one JSON object with keys "
        "proposed_rule_text, proposed_regex, default_fix, and rationale. Preserve the rule's policy intent. "
        "Use null for proposed_regex when a deterministic regex is unsuitable. Do not invent policy facts."
    )
    prompt = (
        f"Rewrite this rule for clarity and a deterministic text detector where appropriate.\n"
        f"Rule ID: {rule_id}\nType: {rule.get('violation_type')}\n"
        f"Current rule: {rule.get('rule_text')}\nCurrent regex: {rule.get('regex_pattern')}\n"
        f"Current fix: {rule.get('default_fix')}\n"
        f"Reviewer override/dismissal reasons: {event_reasons or ['No recorded reasons']}"
    )
    try:
        result, model = ai_client.complete_json(system, prompt, max_tokens=900)
    except ai_client.AIUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Rule rewrite unavailable: {exc}") from exc
    proposed_text = result.get("proposed_rule_text", result.get("rule_text")) if isinstance(result, dict) else None
    if not isinstance(result, dict) or not isinstance(proposed_text, str) or not proposed_text.strip():
        raise HTTPException(status_code=502, detail="AI returned an invalid rule rewrite.")
    candidate_pattern = result.get("proposed_regex", result.get("regex_pattern"))
    if candidate_pattern is not None and not isinstance(candidate_pattern, str):
        raise HTTPException(status_code=502, detail="AI returned a non-string regex pattern.")
    _validate_regex(candidate_pattern)
    return {
        "rule_id": rule_id,
        "current": {"rule_text": rule.get("rule_text"), "regex_pattern": rule.get("regex_pattern"), "default_fix": rule.get("default_fix")},
        "suggestion": {
            "rule_text": proposed_text.strip(),
            "regex_pattern": candidate_pattern,
            "default_fix": result.get("default_fix"),
            "rationale": str(result.get("rationale") or "").strip(),
        },
        "model": model,
        "applied": False,
        "proposed_rule_text": proposed_text.strip(),
        "proposed_regex": candidate_pattern,
    }


@router.post("/api/rules/{rule_id}/backtest")
def backtest_rule(rule_id: int, req: BacktestRequest, session: SessionUser = Depends(require_role("Reviewer", "Admin"))):
    rule = _get_rule(rule_id)
    pattern = req.regex_pattern if req.regex_pattern is not None else rule.get("regex_pattern")
    _validate_regex(pattern)
    try:
        compiled = re.compile(pattern) if pattern else None
        old_pattern = rule.get("regex_pattern")
        old_compiled = re.compile(old_pattern) if old_pattern else None
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {exc}") from exc

    samples = _past_scan_texts()
    default_fix = str(rule.get("default_fix") or "").strip()
    if compiled and default_fix and compiled.search(default_fix):
        raise HTTPException(status_code=422, detail="Proposed regex matches this rule's own suggested_fix.")
    candidate_ids: List[str] = []
    existing_ids: List[str] = []
    examples: List[Dict[str, str]] = []
    candidate_match_total = 0
    existing_match_total = 0
    for sample in samples:
        text = sample["text"]
        candidate = list(compiled.finditer(text))[:20] if compiled else []
        existing = list(old_compiled.finditer(text))[:20] if old_compiled else []
        candidate_match_total += len(candidate)
        existing_match_total += len(existing)
        if candidate:
            candidate_ids.append(sample["scan_id"])
            if len(examples) < 10:
                examples.append({"scan_id": sample["scan_id"], "match": candidate[0].group(0)[:160]})
        if existing:
            existing_ids.append(sample["scan_id"])
    candidate_set, old_set = set(candidate_ids), set(existing_ids)
    eliminated = sorted(old_set - candidate_set)
    return {
        "rule_id": rule_id,
        "regex_pattern": pattern,
        "proposed_regex": pattern,
        "valid_regex": True,
        "scans_sampled": len(samples),
        "scans_with_matches": len(candidate_set),
        "total_matches_capped_per_scan": candidate_match_total,
        "scans_evaluated": len(samples),
        "previous_flags": existing_match_total,
        "new_flags": candidate_match_total,
        "false_positives_eliminated": len(eliminated),
        "scans_newly_flagged": sorted(candidate_set - old_set),
        "scans_no_longer_flagged": sorted(old_set - candidate_set),
        "example_matches": examples,
        "safety": "passed" if pattern is None or pattern == "" or compiled is not None else "failed",
        "note": "Backtest compares regex matches against up to 100 recent stored scan texts. 'false_positives_eliminated' is a match-count proxy, not a human-labeled precision metric.",
    }


@router.patch("/api/rules/{rule_id}")
def update_rule(
    rule_id: int,
    req: RulePatch,
    session: SessionUser = Depends(require_role("Admin")),
):
    old_rule = _get_rule(rule_id)
    updates = req.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one rule field to update.")
    if "severity" in updates and updates["severity"] not in {"High", "Medium", "Low"}:
        raise HTTPException(status_code=422, detail="severity must be High, Medium, or Low.")
    if "violation_type" in updates and updates["violation_type"] not in {"Factual", "Tone", "Terminology", "Accessibility", "Visual"}:
        raise HTTPException(status_code=422, detail="Unsupported violation_type.")
    if "regex_pattern" in updates:
        updates["regex_pattern"] = _validate_regex(updates["regex_pattern"])
    version_no = _save_rule_change(rule_id, old_rule, updates, session.name)
    refreshed = _get_rule(rule_id)
    refreshed["version_no"] = version_no
    return {"status": "updated", "version_no": version_no, "rule": refreshed}


@router.post("/api/rules/{rule_id}/rollback")
def rollback_rule(
    rule_id: int,
    req: RollbackRequest = RollbackRequest(),
    session: SessionUser = Depends(require_role("Admin")),
):
    current = _get_rule(rule_id)
    current_version, history = _version_and_history(rule_id)
    earlier = [h for h in history if h["version_no"] < current_version]
    target_version = req.version_no if req.version_no is not None else max((h["version_no"] for h in earlier), default=0)
    if target_version < 1 or target_version >= current_version:
        raise HTTPException(status_code=400, detail="Rollback target must be an earlier rule version.")
    candidates = [h for h in history if h["version_no"] == target_version]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"Rule version {target_version} was not found.")
    target = candidates[-1]
    # The history table tracks the two fields it was designed for. Keep every other
    # current field as-is, while recording this rollback as a new rule version.
    updates = {"rule_text": target.get("rule_text"), "regex_pattern": target.get("regex_pattern")}
    _validate_regex(updates["regex_pattern"])
    new_version = _save_rule_change(rule_id, current, updates, session.name)
    refreshed = _get_rule(rule_id)
    refreshed["version_no"] = new_version
    return {"status": "rolled_back", "from_version": current_version, "restored_version": target_version, "version_no": new_version, "rule": refreshed}
