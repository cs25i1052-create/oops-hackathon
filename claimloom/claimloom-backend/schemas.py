"""Shared API contract (what Rohit's frontend receives) + scoring.
Both /api/scan-text and /api/scan-image use these, so the JSON never drifts apart."""
import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int


class IssueItem(BaseModel):
    id: str
    severity: Literal["High", "Medium", "Low"]
    violation_type: Literal["Tone", "Terminology", "Factual", "Accessibility", "Visual"]
    flagged_text: str
    start: int   # -1 means "no text position, show the card without a highlight"
    end: int     # UTF-16 units, so JavaScript highlighting matches exactly
    region: Optional[Region] = None
    rule_id: int
    rule_cited: str
    source_ref: str
    explanation: str
    suggested_fix: str
    confidence: float
    detected_by: Literal["rule_engine", "ai"]
    claim_status: Optional[
        Literal["Verified Fact", "Outdated Spec", "Unverified Promotional Claim"]
    ] = None


class PillarScores(BaseModel):
    tone: int
    terminology: int
    claims: int
    accessibility: int
    visual: int


class ScanResponse(BaseModel):
    scan_id: str
    readiness_score: int
    status: Literal["approved", "needs_review"]
    ai_status: Literal["ok", "degraded"]   # "degraded" = AI tier was unavailable
    pillar_scores: PillarScores
    ai_disclosure: str
    pii_redacted_count: int = 0
    issues: List[IssueItem]


class ScanTextRequest(BaseModel):
    text: str = Field(..., max_length=8000, description="Draft content to scan")


class FlagActionRequest(BaseModel):
    scan_id: str
    rule_id: int
    action: Literal["Accepted", "Dismissed", "Overridden"]
    reason: Optional[str] = ""

    @model_validator(mode="after")
    def reason_needed_for_override(self):
        # Round 1 promise: "Human Override with Justification"
        if self.action == "Overridden" and not (self.reason or "").strip():
            raise ValueError("A reason is required when overriding a flag.")
        return self


WEIGHTS = {"High": 20, "Medium": 12, "Low": 6}
PILLAR_OF = {
    "Tone": "tone",
    "Terminology": "terminology",
    "Factual": "claims",
    "Accessibility": "accessibility",
    "Visual": "visual",
}


def new_scan_id() -> str:
    return f"scan_{uuid.uuid4().hex[:8]}"


def score_issues(issues: List[IssueItem], ai_ok: bool = True):
    """Returns (overall_score, pillar_scores, status).
    Overall = 100 minus ALL deductions, so three problems really do lower the score."""
    deductions = {p: 0 for p in PILLAR_OF.values()}
    total = 0
    for iss in issues:
        w = WEIGHTS[iss.severity]
        deductions[PILLAR_OF[iss.violation_type]] += w
        total += w
    pillars = PillarScores(**{p: max(0, 100 - d) for p, d in deductions.items()})
    overall = max(0, 100 - total)
    has_high = any(i.severity == "High" for i in issues)
    status = "approved" if (overall >= 88 and not has_high and ai_ok) else "needs_review"
    return overall, pillars, status
