from dotenv import load_dotenv

load_dotenv()  # must run before the other imports read environment variables

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import ai_client
import db
import pipeline
from schemas import (FlagActionRequest, ScanResponse, ScanTextRequest, new_scan_id, score_issues)
from vision_router import router as vision_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_vault(force=True)  # load the Brand Truth Vault from Neon once at startup (falls back to local)
    yield


app = FastAPI(title="ClaimLoom Hybrid Brand Governance API", lifespan=lifespan)

# CORS: set ALLOWED_ORIGINS="http://localhost:3000,https://your-app.vercel.app" in production.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=None if "*" in _origins else r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vision_router)


# ------------------------------------------------------------------ health & diagnostics
@app.get("/health")
def health_check():
    """Frontend pings this when the page loads: wakes Render AND Neon."""
    db_ok = db.ping()
    _, _, source = db.get_vault()
    return {
        "status": "awake",
        "database": "connected" if db_ok else "not connected (using local rules)",
        "rules_source": source,
        "ai_providers_configured": [p["name"] for p in ai_client._ordered_providers()],
    }


@app.get("/api/ai-status")
def ai_status():
    """Open this URL after deploying: it tests every AI provider and tells you which model works."""
    return {"providers": ai_client.status()}


# ------------------------------------------------------------------ text scan
@app.post("/api/scan-text", response_model=ScanResponse)
def scan_text(request: ScanTextRequest, background: BackgroundTasks):
    original_text = request.text
    if not original_text.strip():
        raise HTTPException(status_code=400, detail="Draft text cannot be empty.")

    analysis = pipeline.analyze_text(original_text)
    score, pillars, status = score_issues(analysis.issues, ai_ok=analysis.ai_ok)
    scan_id = new_scan_id()

    background.add_task(  # audit log after the response is sent; the draft text itself is NOT stored
        db.save_scan, scan_id, score, status, "text",
        {"issues": [i.model_dump() for i in analysis.issues], "ai_ok": analysis.ai_ok, "chars": len(original_text)},
    )
    return ScanResponse(
        scan_id=scan_id,
        readiness_score=score,
        status=status,
        ai_status="ok" if analysis.ai_ok else "degraded",
        pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(analysis.model_label, analysis.ai_ok),
        pii_redacted_count=analysis.pii_count,
        issues=analysis.issues,
    )


# ------------------------------------------------------------------ Truth Vault
@app.get("/api/rules")
def list_rules(refresh: bool = False):
    rules, facts, source = db.get_vault(force=refresh)
    return {"source": source, "rules": rules, "facts": facts}


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
            "You are a brand-guideline editor. Reply with ONE JSON object: {\"clearer_rule\": \"...\"}.",
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
