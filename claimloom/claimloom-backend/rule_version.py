"""Lightweight version counter backed by the non-RAG rule history table."""
from __future__ import annotations

import time

import db

_cached_at = 0.0
_cached_version = 1
_TTL_SECONDS = 60.0


def get_rules_version(force: bool = False) -> int:
    global _cached_at, _cached_version
    now = time.monotonic()
    if not force and now - _cached_at < _TTL_SECONDS:
        return _cached_version
    version = 1
    try:
        conn = db._connect()
    except Exception as exc:
        print(f"[rule_version] database connection fallback: {exc}")
        conn = None
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(version_no), 1) FROM public.rule_versions")
                row = cur.fetchone()
                version = max(1, int(row[0] or 1)) if row else 1
        except Exception as exc:
            print(f"[rule_version] history version lookup fallback: {exc}")
        finally:
            conn.close()
    if version <= 1:
        rules, _facts, _source = db.get_vault()
        version = max((int(rule.get("version_no") or 1) for rule in rules), default=1)
    _cached_version = version
    _cached_at = now
    return version


def invalidate_rules_version() -> None:
    global _cached_at
    _cached_at = 0.0


def set_rules_version(version: int) -> None:
    """Update the process cache after a local rules mutation."""
    global _cached_at, _cached_version
    _cached_version = max(1, int(version))
    _cached_at = time.monotonic()
