"""Ed25519 signing and SHA-256 hash-chain helpers for approval records."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def _load_private_key() -> Ed25519PrivateKey:
    """Load SIGNING_PRIVATE_KEY (PEM or base64 32-byte seed), or create a dev key.

    Production deployments should set SIGNING_PRIVATE_KEY to a persistent PEM
    private key or seed. A deterministic development fallback derived from the
    session secret keeps local restarts verifiable without generating key files.
    """
    configured = os.getenv("SIGNING_PRIVATE_KEY", "").strip()
    if not configured:
        fallback_secret = (
            os.getenv("SIGNING_KEY_FALLBACK_SECRET")
            or os.getenv("SECRET_KEY")
            or os.getenv("SESSION_SECRET")
            or "claimloom-development-signing-key-change-before-production"
        )
        return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(fallback_secret.encode("utf-8")).digest())
    raw = configured.encode("utf-8")
    try:
        if "BEGIN" in configured:
            key = serialization.load_pem_private_key(raw, password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("SIGNING_PRIVATE_KEY must be an Ed25519 private key")
            return key
        decoded = base64.urlsafe_b64decode(configured + "=" * (-len(configured) % 4))
        if len(decoded) != 32:
            raise ValueError("base64 SIGNING_PRIVATE_KEY must decode to a 32-byte Ed25519 seed")
        return Ed25519PrivateKey.from_private_bytes(decoded)
    except Exception as exc:
        raise RuntimeError(f"Invalid SIGNING_PRIVATE_KEY: {exc}") from exc


_PRIVATE_KEY = _load_private_key()
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def public_key_bytes() -> bytes:
    return _PUBLIC_KEY.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def public_key_b64() -> str:
    return base64.b64encode(public_key_bytes()).decode("ascii")


def canonical_json(value: Dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def approval_entry_hash(
    *, scan_id: str, version_no: int, text_sha256: str, score: int,
    reviewer: str, role: str, prev_hash: Optional[str], created_at: str,
) -> str:
    record = {
        "scan_id": scan_id,
        "version_no": int(version_no),
        "text_sha256": text_sha256,
        "score": int(score),
        "reviewer": reviewer,
        "role": role,
        "prev_hash": prev_hash or "",
        "created_at": created_at,
    }
    return hashlib.sha256(canonical_json(record)).hexdigest()


def sign_entry_hash(entry_hash: str) -> str:
    return base64.b64encode(_PRIVATE_KEY.sign(bytes.fromhex(entry_hash))).decode("ascii")


def verify_entry_hash(entry_hash: str, signature: str, public_key: Optional[bytes] = None) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key or public_key_bytes())
        key.verify(base64.b64decode(signature, validate=True), bytes.fromhex(entry_hash))
        return True
    except Exception:
        return False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
