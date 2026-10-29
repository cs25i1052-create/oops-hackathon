"""Authenticated automation entry point for text scans."""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import pipeline
from ratelimit import rate_limit_scan
from schemas import ReauditInfo, ScanResponse, new_scan_id, normalize_channel, score_issues
from session import SessionUser, get_current_session, resolve_workspace_id

router = APIRouter()


class WebhookScanRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    channel: str = "general"
    workspace_id: str = "default"


@router.post("/api/webhooks/scan", response_model=ScanResponse)
def webhook_scan(
    req: WebhookScanRequest,
    background: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    _client_ip: str = Depends(rate_limit_scan),
    session: SessionUser = Depends(get_current_session),
):
    expected = os.getenv("WEBHOOK_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook scanning is disabled until WEBHOOK_SECRET is configured.")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Draft text cannot be empty.")
    channel = normalize_channel(req.channel)
    workspace_id = resolve_workspace_id(req.workspace_id, session)
    analysis = pipeline.analyze_text(text, with_positions=True, channel=channel, workspace_id=workspace_id)
    score, pillars, status = score_issues(analysis.issues, ai_ok=analysis.ai_ok)
    response = ScanResponse(
        scan_id=new_scan_id(), readiness_score=score, status=status,
        ai_status="ok" if analysis.ai_ok else "degraded", pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(analysis.model_label, analysis.ai_ok, "Submitted through the authenticated scan webhook."),
        pii_redacted_count=analysis.pii_count, issues=analysis.issues,
        input_type="text", redacted_text=analysis.redacted_text, channel=channel,
        workspace_id=workspace_id, kb_version=analysis.kb_version,
        rules_version=analysis.rules_version, page_count=1,
        verified_claims=analysis.verified_claims, reaudit=ReauditInfo(needed=False, note=None),
    )
    try:
        import main
        background.add_task(
            main.save_scan_persistence, response.model_dump(), analysis.redacted_text,
            "text", None, None, session.name, analysis.rag_results,
        )
    except Exception as exc:
        print(f"[webhook] scan persistence unavailable: {exc}")
    return response
