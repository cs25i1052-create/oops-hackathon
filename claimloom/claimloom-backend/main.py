from dotenv import load_dotenv

load_dotenv()  # must run before the other imports read environment variables

import io
import json
import os
import threading
import time
import zipfile
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

import ai_client
import cache
import db
import pipeline
from ratelimit import rate_limit_scan
from rule_version import get_rules_version
from schemas import (
    FlagActionRequest,
    ReauditInfo,
    ScanResponse,
    ScanTextRequest,
    new_scan_id,
    normalize_channel,
    score_issues,
)
from session import SessionUser, get_current_session, resolve_workspace_id, router as session_router
from vision_router import router as vision_router

#Bounded in-memory fallback store for Collision Point 4 (?scan_id= reload)
# Ensures GET /api/scans/{scan_id} works even if Neon is asleep or unmigrated
_MEM_SCANS_LIMIT = 150
_mem_scans: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_vault(force=True)  # load the Brand Truth Vault from Neon once at startup (falls back to local)
    try:
        from kb_router import ensure_demo_scans_seeded
        ensure_demo_scans_seeded()
    except Exception as _lifespan_exc:
        print(f"[main] ensure_demo_scans_seeded skipped at startup: {_lifespan_exc}")
    yield


app = FastAPI(title="ClaimLoom Governance API v3", lifespan=lifespan)

# ------------------------------------------------------------------ Collision Point 2: Bulletproof CORS
raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,https://oops-hackathon.vercel.app",
)
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip() and "*" not in o]
if not allowed_origins:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://oops-hackathon.vercel.app",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Allows all Vercel preview & production links
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],  # Allows Authorization, X-Workspace-Id, Content-Type
    expose_headers=["Content-Disposition"],  # Needed for Redlined PDF file download
)

# Core routers (Modules 1 & 2)
app.include_router(session_router)
app.include_router(vision_router)

# Auto-mount Round 3 routers (Modules 3, 4, 5 & Devraj's KB router) as soon as they exist
for _mod_name in ("pdf_engine", "collab_router", "rules_router", "webhook_router", "kb_router"):
    try:
        _mod = __import__(_mod_name)
        if hasattr(_mod, "router"):
            app.include_router(_mod.router)
    except ImportError:
        pass


# ------------------------------------------------------------------ Collision Point 4: Persistence Helpers
def save_scan_persistence(
    scan_resp: Dict[str, Any],
    redacted_text: str,
    input_type: str = "text",
    pdf_bytes: Optional[bytes] = None,
    file_sha256: Optional[str] = None,
    actor_name: str = "Creator",
    rag_results: Optional[Dict[str, Any]] = None,
) -> None:
    """Write the scan to memory immediately and persist it without blocking callers."""
    scan_id = scan_resp["scan_id"]
    payload = {
        **scan_resp,
        "redacted_text": redacted_text,
        "input_type": input_type,
    }

    # 1. Always keep a lightweight copy (without pdf_bytes) in bounded memory
    _mem_scans[scan_id] = payload
    _mem_scans.move_to_end(scan_id)
    while len(_mem_scans) > _MEM_SCANS_LIMIT:
        _mem_scans.popitem(last=False)
    try:
        import collab_router
        collab_router._memory_versions.setdefault(scan_id, [{
            "version_no": 1,
            "text_snapshot": redacted_text or "",
            "score": int(scan_resp.get("readiness_score", 100)),
            "actor_name": actor_name or "Creator",
            "created_at": "",
        }])
    except Exception:
        pass
    try:
        import pdf_engine
        pdf_engine._mem_scan_json[scan_id] = payload
        pdf_engine._mem_scan_json.move_to_end(scan_id)
        while len(pdf_engine._mem_scan_json) > 100:
            pdf_engine._mem_scan_json.popitem(last=False)
    except Exception:
        pass

    effective_rag = rag_results or {
        "verified_claims": scan_resp.get("verified_claims") or [],
        "issues": [i for i in (scan_resp.get("issues") or []) if i.get("evidence")],
    }

    def _db_persist_worker() -> None:
        conn = None
        try:
            conn = db._connect()
            if not conn:
                return
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scans (scan_id, readiness_score, status, input_type, payload)
                       VALUES (%s, %s, %s, %s, %s) ON CONFLICT (scan_id) DO NOTHING;""",
                    (scan_id, int(scan_resp.get("readiness_score", 100)), str(scan_resp.get("status", "needs_review")), input_type, db.Json(payload)),
                )
                if pdf_bytes and file_sha256:
                    cur.execute(
                        "SELECT 1 FROM public.scan_documents WHERE file_sha256 = %s AND pdf_bytes IS NOT NULL LIMIT 1;",
                        (file_sha256,),
                    )
                    if cur.fetchone():
                        stored_pdf_bytes = None
                    else:
                        stored_pdf_bytes = pdf_bytes
                else:
                    stored_pdf_bytes = pdf_bytes
                cur.execute(
                    """INSERT INTO public.scan_documents
                       (scan_id, workspace_id, channel, redacted_text, file_sha256, pdf_bytes, result_json, reaudit_needed)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, FALSE)
                       ON CONFLICT (scan_id) DO UPDATE SET result_json = EXCLUDED.result_json,
                       redacted_text = EXCLUDED.redacted_text;""",
                    (scan_id, scan_resp.get("workspace_id", "default"), scan_resp.get("channel", "general"),
                     redacted_text, file_sha256, stored_pdf_bytes, json.dumps(payload)),
                )
                cur.execute(
                    """INSERT INTO public.scan_versions (scan_id, version_no, text_snapshot, score, actor_name)
                       VALUES (%s, 1, %s, %s, %s) ON CONFLICT DO NOTHING;""",
                    (scan_id, redacted_text or "", int(scan_resp.get("readiness_score", 100)), actor_name or "Creator"),
                )
                cur.execute("DELETE FROM public.scan_documents WHERE created_at < NOW() - INTERVAL '24 hours';")
                cur.execute("DELETE FROM public.scan_cache WHERE created_at < NOW() - INTERVAL '24 hours';")
            conn.commit()
        except Exception as exc:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[main] scan persistence DB write skipped: {exc}")
        finally:
            if conn:
                conn.close()
            if effective_rag["verified_claims"] or effective_rag["issues"]:
                pipeline.record_evidence(scan_id, effective_rag)

    threading.Thread(target=_db_persist_worker, daemon=True, name="scan-persist").start()


# ------------------------------------------------------------------ Keep-Alive, Health & Diagnostics
@app.get("/ping")
def keep_alive_ping():
    """DB-free keep-alive endpoint for cron-job.org.
    Keeps Render container warm without waking Neon or burning Neon compute hours."""
    return {"status": "awake", "service": "claimloom-backend-v3", "ts": time.time()}


@app.get("/health")
def health_check():
    """Frontend pings this when the page loads: wakes Render AND Neon."""
    _, _, source = db.get_vault()
    db_ok = source == "neon" or db.ping()
    return {
        "status": "awake",
        "database": "connected" if db_ok else "not connected (using local rules)",
        "rules_source": source,
        "ai_providers_configured": [p["name"] for p in ai_client._ordered_providers()],
        "ai_budget": ai_client.budget_info(),
    }


@app.get("/api/ai-status")
def ai_status():
    """Open this URL after deploying: it tests every AI provider and tells you which model works."""
    return {"providers": ai_client.status(), "ai_budget": ai_client.budget_info()}


# ------------------------------------------------------------------ Text Scan (Cached + Rate-Limited)
@app.post("/api/scan-text", response_model=ScanResponse)
def scan_text(
    request: ScanTextRequest,
    background: BackgroundTasks,
    _client_ip: str = Depends(rate_limit_scan),
    session: SessionUser = Depends(get_current_session),
):
    original_text = request.text
    if not original_text or not original_text.strip():
        raise HTTPException(status_code=400, detail="Draft text cannot be empty.")

    channel = normalize_channel(request.channel)
    workspace_id = resolve_workspace_id(request.workspace_id, session)

    # Compute current versions for deterministic SHA-256 cache lookup
    rules, _facts, _src = db.get_workspace_vault(workspace_id)
    rules_version = get_rules_version()
    kb_version = pipeline.get_kb_version(workspace_id)

    cache_key = cache.make_cache_key(
        text=original_text,
        channel=channel,
        workspace_id=workspace_id,
        rules_version=rules_version,
        kb_version=kb_version,
    )
    cached_hit = cache.get_cached_scan(cache_key)
    if cached_hit:
        cached_hit["scan_id"] = new_scan_id()
        cached_hit["cached"] = True
        cached_hit["channel"] = channel
        cached_hit["workspace_id"] = workspace_id
        cached_response = ScanResponse(**cached_hit)
        background.add_task(
            save_scan_persistence,
            cached_response.model_dump(),
            cached_response.redacted_text or original_text,
            "text",
            None,
            None,
            session.name,
            None,
        )
        return cached_response

    analysis = pipeline.analyze_text(
        original_text,
        with_positions=True,
        channel=channel,
        workspace_id=workspace_id,
    )
    score, pillars, status = score_issues(analysis.issues, ai_ok=analysis.ai_ok)
    scan_id = new_scan_id()

    response_obj = ScanResponse(
        scan_id=scan_id,
        readiness_score=score,
        status=status,
        ai_status="ok" if analysis.ai_ok else "degraded",
        pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(analysis.model_label, analysis.ai_ok),
        pii_redacted_count=analysis.pii_count,
        issues=analysis.issues,
        input_type="text",
        redacted_text=analysis.redacted_text,
        cached=False,
        channel=channel,
        workspace_id=workspace_id,
        kb_version=analysis.kb_version,
        rules_version=analysis.rules_version,
        page_count=1,
        verified_claims=analysis.verified_claims,
        reaudit=ReauditInfo(needed=False, note=None),
    )

    resp_dict = response_obj.model_dump()

    # Only cache when AI tier succeeded (ai_status == "ok")
    if response_obj.ai_status == "ok":
        background.add_task(cache.set_cached_scan, cache_key, resp_dict)

    background.add_task(
        save_scan_persistence,
        resp_dict,
        analysis.redacted_text,
        "text",
        None,
        None,
        session.name,
        analysis.rag_results,
    )
    return response_obj


# ------------------------------------------------------------------ Truth Vault
@app.get("/api/rules")
def list_rules(refresh: bool = False, workspace_id: str = "default"):
    rules, facts, source = db.get_workspace_vault(workspace_id, force=refresh)
    return {"source": source, "rules": rules, "facts": facts, "rules_version": get_rules_version(force=refresh)}


@app.get("/api/analytics/summary")
def analytics_summary():
    """Summary metrics for the governance dashboard."""
    total_scans, avg_score, approved_count, reaudit_count = 0, 0.0, 0, 0
    try:
        conn = db._connect()
    except Exception as exc:
        print(f"[main] analytics DB connection fallback: {exc}")
        conn = None
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), COALESCE(AVG(readiness_score), 0), "
                    "COUNT(*) FILTER (WHERE status = 'approved') FROM public.scans;"
                )
                row = cur.fetchone()
                if row:
                    total_scans, avg_score, approved_count = int(row[0]), round(float(row[1]), 1), int(row[2])
                cur.execute("SELECT COUNT(*) FROM public.scan_documents WHERE reaudit_needed = TRUE;")
                r_row = cur.fetchone()
                if r_row:
                    reaudit_count = int(r_row[0])
        except Exception as exc:
            print(f"[main] analytics query fallback: {exc}")
        finally:
            conn.close()
    else:
        vals = list(_mem_scans.values())
        total_scans = len(vals)
        avg_score = round(sum(int(v.get("readiness_score", 0)) for v in vals) / max(total_scans, 1), 1)
        approved_count = sum(1 for v in vals if v.get("status") == "approved")
        reaudit_count = sum(1 for v in vals if (v.get("reaudit") or {}).get("needed"))

    return {
        "total_scans": total_scans,
        "average_readiness_score": avg_score,
        "approved_scans": approved_count,
        "reaudit_queue_count": reaudit_count,
        "rules_version": get_rules_version(),
        "ambiguity_radar": get_ambiguity_radar(suggest=False)["ambiguity_radar"],
    }


# ------------------------------------------------------------------ Guideline Ambiguity Radar
@app.post("/api/flag-action")
def log_flag_action(req: FlagActionRequest):
    if req.rule_id not in db.rules_by_id():
        raise HTTPException(status_code=404, detail=f"Unknown rule_id {req.rule_id}.")
    stored = db.log_flag_event(req.scan_id, req.rule_id, req.action, req.reason or "")
    return {"status": "logged", "rule_id": req.rule_id, "action": req.action, "stored_in": stored}


MIN_EVENTS = 3          # don't judge a rule from 1 or 2 clicks
OVERRIDE_LIMIT = 30.0   # Round 1 promise: more than 30% overrides = unclear rule


def _suggest_rewording(rule: dict, reasons: list) -> str:
    try:
        data, _ = ai_client.complete_json(
            'You are a brand-guideline editor. Reply with ONE JSON object: {"clearer_rule": "..."}.',
            f"This brand rule is often overridden by human reviewers.\nRule: {rule['rule_text']}\n"
            f"Override reasons: {reasons or ['(none given)']}\n"
            "Rewrite the rule in 1-2 clear sentences that state the exceptions explicitly.",
            max_tokens=800,
        )
        return str(data.get("clearer_rule", "")).strip() if isinstance(data, dict) else ""
    except Exception:
        return ""


@app.get("/api/analytics/ambiguity")
def get_ambiguity_radar(suggest: bool = False):
    """Rules with a high human-override rate. Add ?suggest=true to let the AI draft a clearer wording."""
    stats = {}
    for ev in db.get_flag_events():
        s = stats.setdefault(ev["rule_id"], {"total": 0, "overridden": 0, "reasons": []})
        s["total"] += 1
        if ev["action"] == "Overridden":
            s["overridden"] += 1
            if ev.get("reason"):
                s["reasons"].append(ev["reason"])

    rules = db.rules_by_id()
    results = []
    for rid, c in sorted(stats.items()):
        rule = rules.get(rid, {})
        rate = round(c["overridden"] / c["total"] * 100, 1)
        flagged = c["total"] >= MIN_EVENTS and rate > OVERRIDE_LIMIT
        item = {
            "rule_id": rid,
            "rule_cited": rule.get("rule_cited", f"Rule {rid}"),
            "source_ref": rule.get("source_ref", "Brand Guide"),
            "total_flags": c["total"],
            "override_count": c["overridden"],
            "override_rate_percent": rate,
            "needs_clarification": flagged,
            "enough_data": c["total"] >= MIN_EVENTS,
            "sample_override_reasons": c["reasons"][:3],
        }
        if suggest and flagged and rule:
            item["suggested_rewording"] = _suggest_rewording(rule, c["reasons"][:5]) or None
        results.append(item)
    return {"ambiguity_radar": results}


@app.get("/api/extension/download")
def download_chrome_extension():
    """Package the ClaimLoom Chrome Extension bundle as a downloadable zip archive."""
    ext_dir = Path(__file__).resolve().parent / "chrome-extension"
    if not ext_dir.is_dir():
        raise HTTPException(status_code=404, detail="Chrome extension bundle not found.")

    zip_buffer = io.BytesIO()
    target_files = ["manifest.json", "popup.html", "popup.css", "popup.js"]
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname in target_files:
            fpath = ext_dir / fname
            if fpath.is_file():
                zf.write(fpath, arcname=fname)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ClaimLoom-Chrome-Extension.zip"'},
    )

