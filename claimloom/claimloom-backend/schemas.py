"""Shared API v3 contract (what Rohit's frontend receives) + deterministic scoring.
Maintains 100% backward compatibility with Round 2 (IssueItem alias, PillarScores, Region)
while adding all Round 3 Collision Point 1 & 4 fields with safe defaults."""
import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int


class EvidenceCitation(BaseModel):
    verdict: str  # "Verified" | "Contradicted" | "Unsupported"
    doc_title: str
    page: int = 1
    paragraph: int = 1
    excerpt: str
    similarity: float
    chunk_id: Optional[int] = None


class Issue(BaseModel):
    # Existing Round 2 fields (kept intact for backward compatibility)
    id: str = ""
    severity: str  # "High" | "Medium" | "Low"
    violation_type: str  # "Factual" | "Tone" | "Terminology" | "Accessibility" | "Visual"
    flagged_text: str
    start: Optional[int] = 0   # -1 means "no text position, show card without highlight"
    end: Optional[int] = 0     # UTF-16 units so JavaScript highlighting matches exactly
    region: Optional[Any] = None
    rule_id: Optional[int] = None
    rule_cited: str
    source_ref: str
    explanation: str
    suggested_fix: str
    confidence: float
    detected_by: str  # "rule_engine" | "ai" | "rag_verifier" | "pdf_layout"
    claim_status: Optional[str] = None

    # New Round 3 fields for Collision Point 1
    page: Optional[int] = None  # 1-based page number (null for plain text)
    bbox: Optional[List[float]] = None  # [x0, y0, x1, y1] normalized 0.0 to 1.0
    evidence: Optional[EvidenceCitation] = None
    channel: Optional[str] = "general"


# Backward-compatible alias so vision_router.py, engine.py, and existing tests never break
IssueItem = Issue


class PillarScores(BaseModel):
    tone: int = 100
    terminology: int = 100
    claims: int = 100
    accessibility: int = 100
    visual: int = 100


class ReauditInfo(BaseModel):
    needed: bool = False
    note: Optional[str] = None


class ScanResponse(BaseModel):
    # Existing Round 2 fields
    scan_id: str
    readiness_score: int
    status: str  # "approved" | "needs_review" | "needs_reaudit"
    ai_status: str = "ok"  # "ok" | "degraded"
    pillar_scores: Union[PillarScores, Dict[str, int]]
    ai_disclosure: str
    pii_redacted_count: int = 0
    issues: List[Issue]

    # New Round 3 fields for Collision Point 1 & 4
    input_type: str = "text"  # "text" | "pdf" | "image"
    redacted_text: Optional[str] = None  # Returned on GET /api/scans/{id} for reload
    cached: bool = False
    channel: str = "general"
    workspace_id: str = "default"
    kb_version: int = 1
    rules_version: int = 1
    page_count: int = 1
    verified_claims: List[EvidenceCitation] = Field(default_factory=list)
    reaudit: ReauditInfo = Field(default_factory=ReauditInfo)


class ScanTextRequest(BaseModel):
    text: str = Field(..., max_length=8000, description="Draft content to scan")
    channel: str = Field(default="general", description="Target publication channel")
    workspace_id: str = Field(default="default", description="Workspace identifier")


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


ALLOWED_CHANNELS = {"general", "linkedin", "instagram", "billboard", "email"}

WEIGHTS = {"High": 20, "Medium": 12, "Low": 6}
PILLAR_OF = {
    "Tone": "tone",
    "Terminology": "terminology",
    "Factual": "claims",
    "Accessibility": "accessibility",
    "Visual": "visual",
}


def normalize_channel(channel: Optional[str]) -> str:
    cleaned = (channel or "general").strip().lower()
    return cleaned if cleaned in ALLOWED_CHANNELS else "general"


def new_scan_id() -> str:
    return f"scan_{uuid.uuid4().hex[:8]}"


def score_issues(issues: List[Issue], ai_ok: bool = True):
    """Returns (overall_score, pillar_scores, status).
    Overall = 100 minus ALL deductions, so multiple problems lower the score."""
    deductions = {p: 0 for p in PILLAR_OF.values()}
    total = 0
    for iss in issues:
        w = WEIGHTS.get(iss.severity, 12)
        pillar_key = PILLAR_OF.get(iss.violation_type, "claims")
        deductions[pillar_key] += w
        total += w
    pillars = PillarScores(**{p: max(0, 100 - d) for p, d in deductions.items()})
    overall = max(0, 100 - total)
    has_blocker = any(i.severity in ("High", "Medium") for i in issues)
    status = "approved" if (overall >= 90 and not has_blocker and ai_ok) else "needs_review"
    return overall, pillars, status
