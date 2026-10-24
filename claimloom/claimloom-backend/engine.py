"""Tier 1 (no AI): PII redaction, the regex rule engine, and highlight-position helpers."""
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from schemas import WEIGHTS, IssueItem

# ---------------------------------------------------------------- PII redaction
# Every match is replaced by the SAME number of "X" so start/end positions never shift.
PII_PATTERNS = [
    r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+",                              # emails
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",                                              # card-like numbers
    r"(?<!\w)\+\d{1,3}[\s.-]?\d{2,5}[\s.-]?\d{3,5}(?:[\s.-]?\d{2,5})?(?!\d)",       # +CC phone numbers
    r"(?<!\d)[6-9]\d{4}[\s-]?\d{5}(?!\d)",                                           # Indian 10-digit mobiles
]


def redact_pii_same_length(text: str) -> Tuple[str, int]:
    count = 0

    def mask(match):
        nonlocal count
        count += 1
        return "X" * len(match.group(0))

    for pattern in PII_PATTERNS:
        text = re.sub(pattern, mask, text)
    return text, count


# ---------------------------------------------------------------- helpers
@lru_cache(maxsize=256)
def compile_pattern(pattern: str):
    return re.compile(pattern)


def to_utf16(text: str, index: int) -> int:
    """Python counts emoji as 1 character, JavaScript counts them as 2. Convert so highlights match."""
    return len(text[:index].encode("utf-16-le")) // 2


def overlaps(a_start: int, a_end: int, spans: List[Tuple[int, int]]) -> bool:
    return any(a_start < e and a_end > s for s, e in spans)


def locate_phrase(draft: str, phrase: str, taken: List[Tuple[int, int]]) -> Tuple[int, int]:
    """Finds `phrase` in the ORIGINAL draft. Ignores case/extra spaces, and skips
    occurrences that are already flagged, so repeated phrases each get their own highlight."""
    words = phrase.split()
    if not words:
        return -1, -1
    pattern = r"\s+".join(map(re.escape, words))
    for m in re.finditer(pattern, draft, re.IGNORECASE):
        if not overlaps(m.start(), m.end(), taken):
            return m.start(), m.end()
    return -1, -1


def _pick_fix(rule: Dict, matched: str) -> str:
    fix = rule.get("default_fix") or matched
    if "|" in fix:  # "Creator|Creators" -> singular|plural
        singular, plural = fix.split("|", 1)
        fix = plural if matched.lower().endswith("s") else singular
    return fix


def _allowed_numbers(rule: Dict) -> set:
    raw = rule.get("allowed_numbers")
    if not raw:
        return set()
    return {float(x) for x in str(raw).split(",") if x.strip()}


# ---------------------------------------------------------------- Tier 1 engine
def run_rule_engine(text: str, rules: List[Dict], scope: str = "text") -> List[IssueItem]:
    """Exact regex checks. Zero hallucination, exact positions.
    Pattern tips: a named group (?P<flag>...) highlights only that part;
    a named group (?P<num>...) plus `allowed_numbers` flags numbers that are not on the approved list."""
    found = []
    for rule in rules:
        if rule.get("applies_to", "text") not in (scope, "both"):
            continue
        pattern = rule.get("regex_pattern")
        if not pattern:
            continue
        try:
            rx = compile_pattern(pattern)
        except re.error:
            continue  # a bad pattern typed into the database must never crash a scan
        allowed = _allowed_numbers(rule)
        for m in rx.finditer(text):
            if allowed and "num" in rx.groupindex and m.group("num"):
                try:
                    if float(m.group("num")) in allowed:
                        continue  # price/number is approved, no violation
                except ValueError:
                    pass
            if "flag" in rx.groupindex and m.group("flag"):
                start, end = m.span("flag")
            else:
                start, end = m.span()
            matched = text[start:end]
            found.append(
                IssueItem(
                    id="",
                    severity=rule["severity"],
                    violation_type=rule["violation_type"],
                    flagged_text=matched,
                    start=start,
                    end=end,
                    rule_id=rule["rule_id"],
                    rule_cited=rule["rule_cited"],
                    source_ref=rule["source_ref"],
                    explanation=f"Violates {rule['rule_cited']}. {rule['rule_text']}",
                    suggested_fix=_pick_fix(rule, matched),
                    confidence=1.0,
                    detected_by="rule_engine",
                    claim_status=rule.get("claim_status"),
                )
            )
    return _drop_overlaps(found)


def _drop_overlaps(issues: List[IssueItem]) -> List[IssueItem]:
    """If two rules flag the same words, keep the more severe one."""
    issues.sort(key=lambda i: (i.start, -WEIGHTS[i.severity]))
    kept: List[IssueItem] = []
    for iss in issues:
        if not overlaps(iss.start, iss.end, [(k.start, k.end) for k in kept]):
            kept.append(iss)
    return kept
