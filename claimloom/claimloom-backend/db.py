"""Database layer. Every function works even if Neon is down or not configured:
rules fall back to seed_db.py, events fall back to memory. A scan never crashes because of the DB."""
import os
import time
from typing import Dict, List, Optional, Tuple

from seed_db import DEMO_FLAG_EVENTS, FACTS_DATA, RULES_DATA

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # psycopg2 missing -> run in local mode
    psycopg2 = None

OK_TTL = 300     # re-read rules from Neon every 5 minutes
FAIL_TTL = 120   # if Neon failed, don't retry for 2 minutes (avoids slow requests)

_cache = {"at": 0.0, "ttl": 0, "rules": list(RULES_DATA), "facts": list(FACTS_DATA), "source": "local-fallback"}
_memory_events: List[Dict] = [
    {"scan_id": s, "rule_id": r, "action": a, "reason": why} for s, r, a, why in DEMO_FLAG_EVENTS
]


def _connect():
    url = os.getenv("DATABASE_URL", "").strip()
    if not psycopg2 or not url or "ep-xyz" in url or "user:password" in url:
        return None
    return psycopg2.connect(url, connect_timeout=5)


def ping() -> bool:
    """Wakes Neon from its idle sleep. Used by /health."""
    try:
        conn = _connect()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[db] ping failed: {e}")
        return False


def get_vault(force: bool = False) -> Tuple[List[Dict], List[Dict], str]:
    """Returns (rules, facts, source). source is 'neon' or 'local-fallback'."""
    now = time.time()
    if not force and now - _cache["at"] < _cache["ttl"]:
        return _cache["rules"], _cache["facts"], _cache["source"]
    try:
        conn = _connect()
        if not conn:
            raise RuntimeError("DATABASE_URL not configured")
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM brand_rules ORDER BY rule_id;")
        rules = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM facts ORDER BY fact_id;")
        facts = [dict(f) for f in cur.fetchall()]
        cur.close()
        conn.close()
        if not rules:
            raise RuntimeError("brand_rules table is empty (run python seed_db.py)")
        for r in rules:
            r.setdefault("allowed_numbers", None)
            r["applies_to"] = r.get("applies_to") or "text"
        _cache.update(at=now, ttl=OK_TTL, rules=rules, facts=facts, source="neon")
    except Exception as e:
        print(f"[db] using local rules ({e})")
        _cache.update(at=now, ttl=FAIL_TTL, rules=list(RULES_DATA), facts=list(FACTS_DATA), source="local-fallback")
    return _cache["rules"], _cache["facts"], _cache["source"]


def rules_by_id() -> Dict[int, Dict]:
    return {r["rule_id"]: r for r in get_vault()[0]}


def save_scan(scan_id: str, score: int, status: str, input_type: str, payload: dict) -> None:
    """Best-effort audit log. Called after the response is sent, so it never slows the user."""
    try:
        conn = _connect()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO scans (scan_id, readiness_score, status, input_type, payload)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (scan_id) DO NOTHING;""",
            (scan_id, score, status, input_type, Json(payload)),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[db] save_scan failed: {e}")


def log_flag_event(scan_id: str, rule_id: int, action: str, reason: str) -> str:
    """Returns where it was stored: 'neon' or 'memory'."""
    try:
        conn = _connect()
        if conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO flag_events (scan_id, rule_id, action, reason) VALUES (%s, %s, %s, %s);",
                (scan_id, rule_id, action, reason or ""),
            )
            conn.commit()
            cur.close()
            conn.close()
            return "neon"
    except Exception as e:
        print(f"[db] log_flag_event failed, keeping in memory: {e}")
    _memory_events.append({"scan_id": scan_id, "rule_id": rule_id, "action": action, "reason": reason or ""})
    return "memory"


def get_flag_events() -> List[Dict]:
    try:
        conn = _connect()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT scan_id, rule_id, action, reason FROM flag_events;")
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return rows
    except Exception as e:
        print(f"[db] get_flag_events failed, using memory: {e}")
    return list(_memory_events)
