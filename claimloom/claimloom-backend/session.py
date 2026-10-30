"""Stateless HMAC-SHA256 Role Session Tokens (Creator / Reviewer / Admin).
Provides POST /api/session to issue tokens and FastAPI dependencies to inspect
Authorization: Bearer <token> and X-Workspace-Id headers.
Falls back to Creator role if Authorization header is missing so basic curl tests never break."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()

_database_url = os.getenv("DATABASE_URL", "")
SESSION_SECRET = os.getenv("SESSION_SECRET") or (hashlib.sha256(_database_url.encode()).hexdigest() if _database_url else secrets.token_hex(32))
TOKEN_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days default

VALID_ROLES = {
    "creator": "Creator",
    "reviewer": "Reviewer",
    "admin": "Admin",
}


class SessionRequest(BaseModel):
    role: str = Field(default="Creator", description="Creator | Reviewer | Admin")
    name: str = Field(default="Demo User", max_length=80, description="Display name for audit trails")
    workspace_id: str = Field(default="default", max_length=64, description="Target workspace ID")


class SessionUser(BaseModel):
    name: str = "Creator"
    role: str = "Creator"  # "Creator" | "Reviewer" | "Admin"
    workspace_id: str = "default"
    iat: int = 0
    exp: int = 0
    authenticated: bool = False


class SessionResponse(BaseModel):
    token: str
    role: str
    name: str
    workspace_id: str
    expires_at: int


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def normalize_role(role: Optional[str]) -> str:
    cleaned = (role or "Creator").strip().lower()
    if cleaned not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role}'. Must be one of: Creator, Reviewer, Admin.",
        )
    return VALID_ROLES[cleaned]


def create_session_token(name: str, role: str = "Creator", workspace_id: str = "default") -> Tuple_Token:
    norm_role = normalize_role(role)
    clean_name = (name or norm_role).strip()[:80] or norm_role
    clean_ws = (workspace_id or "default").strip()[:64] or "default"
    now = int(time.time())
    exp = now + TOKEN_TTL_SECONDS

    payload = {
        "sub": clean_name,
        "role": norm_role,
        "ws": clean_ws,
        "iat": now,
        "exp": exp,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    token = f"{payload_b64}.{_b64url_encode(sig)}"
    return token, norm_role, clean_name, clean_ws, exp


# Type alias helper for readability
Tuple_Token = tuple[str, str, str, str, int]


def verify_session_token(token: str) -> Optional[SessionUser]:
    """Verifies an HMAC-SHA256 token and returns SessionUser, or None if invalid/expired."""
    try:
        parts = (token or "").strip().split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        expected_sig = hmac.new(
            SESSION_SECRET.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if exp and time.time() > exp:
            return None

        raw_role = str(payload.get("role", "Creator")).strip().lower()
        role = VALID_ROLES.get(raw_role, "Creator")
        return SessionUser(
            name=str(payload.get("sub") or role),
            role=role,
            workspace_id=str(payload.get("ws") or "default"),
            iat=int(payload.get("iat") or 0),
            exp=exp,
            authenticated=True,
        )
    except Exception:
        return None


def get_current_session(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
) -> SessionUser:
    """FastAPI dependency: extracts role & workspace from headers.
    Falls back to Creator role if Authorization header is missing so curl & Round 2 callers work."""
    ws_header = (x_workspace_id or "").strip()
    now = int(time.time())

    if authorization:
        scheme, _, param = authorization.strip().partition(" ")
        if scheme.lower() != "bearer" or not param:
            raise HTTPException(status_code=401, detail="Authorization must use a Bearer token.")
        raw_token = param
        user = verify_session_token(raw_token)
        if user:
            if ws_header and ws_header != user.workspace_id:
                raise HTTPException(status_code=403, detail="X-Workspace-Id must match the workspace in the session token.")
            return user
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    return SessionUser(
        name="Creator",
        role="Creator",
        workspace_id="default",
        iat=now,
        exp=now + TOKEN_TTL_SECONDS,
        authenticated=False,
    )


def require_role(*allowed_roles: str) -> Callable:
    """Dependency factory for endpoints that require Reviewer or Admin role.
    Example: Depends(require_role("Reviewer", "Admin"))"""
    normalized_allowed = {VALID_ROLES.get(r.lower(), r) for r in allowed_roles}

    def _checker(session: SessionUser = Depends(get_current_session)) -> SessionUser:
        if session.role not in normalized_allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{session.role}' is not authorized. Required: {', '.join(sorted(normalized_allowed))}.",
            )
        return session

    return _checker


def resolve_workspace_id(requested_workspace_id: Optional[str], session: SessionUser) -> str:
    """Resolve a requested workspace without allowing cross-workspace scans by default."""
    requested = (requested_workspace_id or "default").strip() or "default"
    own_workspace = (session.workspace_id or "default").strip() or "default"
    if requested == "default":
        return own_workspace
    if requested != own_workspace and session.role != "Admin":
        raise HTTPException(status_code=403, detail="This session cannot access the requested workspace.")
    return requested


@router.post("/api/session", response_model=SessionResponse)
def issue_session(
    req: SessionRequest,
    issuer_secret: Optional[str] = Header(default=None, alias="X-Session-Issuer-Secret"),
):
    """Issues an HMAC-SHA256 role token for Creator, Reviewer, or Admin."""
    role = normalize_role(req.role)
    required_issuer_secret = os.getenv("SESSION_ISSUER_SECRET", "").strip()
    requested_workspace = (req.workspace_id or "default").strip() or "default"
    elevated_issuance = role != "Creator" or requested_workspace != "default"
    if elevated_issuance:
        if not required_issuer_secret and os.getenv("ALLOW_INSECURE_DEMO_ROLES", "true").lower() != "true":
            raise HTTPException(status_code=503, detail="Elevated role or non-default workspace issuance is disabled until SESSION_ISSUER_SECRET is configured.")
        if required_issuer_secret and (not issuer_secret or not hmac.compare_digest(issuer_secret, required_issuer_secret)):
            raise HTTPException(status_code=403, detail="A valid X-Session-Issuer-Secret is required for elevated roles or non-default workspaces.")
    token, role, name, ws, exp = create_session_token(
        name=req.name,
        role=req.role,
        workspace_id=req.workspace_id,
    )
    return SessionResponse(
        token=token,
        role=role,
        name=name,
        workspace_id=ws,
        expires_at=exp,
    )


@router.get("/api/session/me", response_model=SessionUser)
def read_current_session(session: SessionUser = Depends(get_current_session)):
    """Returns the currently active session decoded from Authorization & X-Workspace-Id headers."""
    return session
