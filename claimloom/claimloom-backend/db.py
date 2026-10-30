"""Database layer. Every function works even if Neon is down or not configured:
rules fall back to seed_db.py, events fall back to memory. A scan never crashes because of the DB."""
import os
import threading
import time
from typing import Dict, List, Optional, Tuple

from seed_db import DEMO_FLAG_EVENTS, FACTS_DATA, RULES_DATA

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
    from psycopg2.extensions import connection as _PgConnection, STATUS_BEGIN, TRANSACTION_STATUS_INERROR
except Exception:  # psycopg2 missing -> run in local mode
    psycopg2 = None
    _PgConnection = object
    STATUS_BEGIN = TRANSACTION_STATUS_INERROR = -1

OK_TTL = 300     # re-read rules from Neon every 5 minutes
FAIL_TTL = 120   # if Neon failed, don't retry for 2 minutes (avoids slow requests)

_cache = {"at": 0.0, "ttl": 0, "rules": list(RULES_DATA), "facts": list(FACTS_DATA), "source": "local-fallback", "flag_events": None, "flag_events_loaded": False}
_memory_events: List[Dict] = [
    {"scan_id": s, "rule_id": r, "action": a, "reason": why} for s, r, a, why in DEMO_FLAG_EVENTS
]

for _rule in RULES_DATA:
    _rule.setdefault("workspace_id", "default")


_db_lock = threading.RLock()
_lease_state = threading.local()
_sticky_conn: Optional["_StickyConnection"] = None
_sticky_dsn: Optional[str] = None


def _is_connection_error(exc: Exception) -> bool:
    return bool(
        psycopg2
        and isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError))
    )


def reset_connection(conn=None) -> None:
    """Discard a dead sticky socket so the next request can reconnect."""
    global _sticky_conn, _sticky_dsn
    with _db_lock:
        if conn is None or conn is _sticky_conn:
            if _sticky_conn is not None:
                _sticky_conn.force_close()
            _sticky_conn = None
            _sticky_dsn = None


class _LockedCursor:
    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection
        self._released = False

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def _call(self, method, *args, **kwargs):
        try:
            return getattr(self._cursor, method)(*args, **kwargs)
        except Exception as exc:
            if _is_connection_error(exc):
                reset_connection(self._connection)
            raise

    def execute(self, *args, **kwargs):
        return self._call("execute", *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._call("executemany", *args, **kwargs)

    def fetchone(self):
        return self._call("fetchone")

    def fetchmany(self, *args, **kwargs):
        return self._call("fetchmany", *args, **kwargs)

    def fetchall(self):
        return self._call("fetchall")

    def _release(self):
        if not self._released:
            self._released = True
            _db_lock.release()

    def close(self):
        try:
            return self._cursor.close()
        finally:
            self._release()

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._cursor.__exit__(exc_type, exc, tb)
        finally:
            self._release()


class _StickyConnection(_PgConnection):
    """One persistent database socket, with serialized cursor use."""
    def cursor(self, *args, **kwargs):
        _db_lock.acquire()
        try:
            return _LockedCursor(super().cursor(*args, **kwargs), self)
        except Exception:
            _db_lock.release()
            raise

    def commit(self):
        with _db_lock:
            try:
                return super().commit()
            except Exception as exc:
                if _is_connection_error(exc):
                    reset_connection(self)
                raise

    def rollback(self):
        with _db_lock:
            try:
                return super().rollback()
            except Exception as exc:
                if _is_connection_error(exc):
                    reset_connection(self)
                raise

    def close(self):
        with _db_lock:
            try:
                if not self.closed and (
                    self.status == STATUS_BEGIN
                    or self.get_transaction_status() == TRANSACTION_STATUS_INERROR
                ):
                    super().rollback()
            except Exception:
                pass
            leases = getattr(_lease_state, "count", 0)
            if leases:
                _lease_state.count = leases - 1
                _db_lock.release()

    def force_close(self):
        try:
            super().close()
        except Exception:
            pass


def _connect():
    global _sticky_conn, _sticky_dsn
    url = os.getenv("DATABASE_URL", "").strip()
    if not psycopg2 or not url or "ep-xyz" in url or "user:password" in url:
        return None
    _db_lock.acquire()
    try:
        if _sticky_conn is not None and _sticky_dsn != url:
            _sticky_conn.force_close()
            _sticky_conn = None
        if _sticky_conn is not None and not _sticky_conn.closed:
            _lease_state.count = getattr(_lease_state, "count", 0) + 1
            return _sticky_conn
        _sticky_conn = psycopg2.connect(
            url,
            connect_timeout=5,
            connection_factory=_StickyConnection,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        _sticky_dsn = url
        _lease_state.count = getattr(_lease_state, "count", 0) + 1
        return _sticky_conn
    except Exception:
        _db_lock.release()
        raise


def ping() -> bool:
    """Wakes Neon from its idle sleep. Used by /health."""
    conn = None
    try:
        conn = _connect()
        if not conn:
            return False
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        return True
    except Exception as e:
        print(f"[db] ping failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_vault(force: bool = False) -> Tuple[List[Dict], List[Dict], str]:
    """Returns (rules, facts, source). source is 'neon' or 'local-fallback'."""
    now = time.time()
    if not force and now - _cache["at"] < _cache["ttl"]:
        return _cache["rules"], _cache["facts"], _cache["source"]
    conn = None
    try:
        conn = _connect()
        if not conn:
            raise RuntimeError("DATABASE_URL not configured")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM brand_rules ORDER BY rule_id;")
            rules = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM facts ORDER BY fact_id;")
            facts = [dict(f) for f in cur.fetchall()]
            try:
                cur.execute("SAVEPOINT flag_events_prefetch")
                cur.execute("SELECT scan_id, rule_id, action, reason FROM flag_events;")
                flag_events = [dict(r) for r in cur.fetchall()]
                cur.execute("RELEASE SAVEPOINT flag_events_prefetch")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT flag_events_prefetch")
                cur.execute("RELEASE SAVEPOINT flag_events_prefetch")
                flag_events = []
            try:
                cur.execute("SAVEPOINT rule_version_prefetch")
                cur.execute("SELECT rule_id, version_no, old_rule_text, old_pattern, changed_by, created_at FROM public.rule_versions ORDER BY version_no ASC, id ASC;")
                rule_version_rows = [dict(r) for r in cur.fetchall()]
                max_version = max((int(r["version_no"] or 1) for r in rule_version_rows), default=1)
                cur.execute("RELEASE SAVEPOINT rule_version_prefetch")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT rule_version_prefetch")
                cur.execute("RELEASE SAVEPOINT rule_version_prefetch")
                max_version = 1
                rule_version_rows = []
            try:
                cur.execute("SAVEPOINT approvals_prefetch")
                cur.execute("SELECT approval_id, scan_id, version_no, text_sha256, score, reviewer, role, prev_hash, entry_hash, signature, created_at FROM public.approvals ORDER BY created_at ASC, approval_id ASC;")
                approval_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("RELEASE SAVEPOINT approvals_prefetch")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT approvals_prefetch")
                cur.execute("RELEASE SAVEPOINT approvals_prefetch")
                approval_rows = []
        conn.close()
        if not rules:
            raise RuntimeError("brand_rules table is empty (run python seed_db.py)")
        for r in rules:
            r.setdefault("allowed_numbers", None)
            r["applies_to"] = r.get("applies_to") or "text"
        _cache.update(at=now, ttl=OK_TTL, rules=rules, facts=facts, source="neon", flag_events=flag_events, flag_events_loaded=True)
        try:
            import collab_router
            if not collab_router._approvals_loaded:
                collab_router._approvals[:] = [
                    {**r, "approval_id": int(r["approval_id"]), "version_no": int(r["version_no"]),
                     "score": int(r["score"]), "created_at": collab_router._iso(r["created_at"])}
                    for r in approval_rows
                ]
                collab_router._approvals_loaded = True
        except Exception:
            pass
        try:
            import rules_router
            histories: Dict[int, List[Dict]] = {}
            for row in rule_version_rows:
                rule_id = int(row["rule_id"])
                histories.setdefault(rule_id, []).append({
                    "version_no": int(row["version_no"]),
                    "rule_text": row["old_rule_text"],
                    "regex_pattern": row["old_pattern"],
                    "changed_by": row["changed_by"],
                    "created_at": str(row["created_at"]),
                })
            for rule_id, history in histories.items():
                if rule_id not in rules_router._history_loaded and rule_id not in rules_router._memory_history:
                    rules_router._memory_history[rule_id] = history
                    rules_router._history_loaded.add(rule_id)
            for rule in rules:
                rule_id = int(rule.get("rule_id") or 0)
                if rule_id and rule_id not in rules_router._history_loaded:
                    rules_router._memory_history.setdefault(rule_id, [])
                    rules_router._history_loaded.add(rule_id)
        except Exception:
            pass
        try:
            from rule_version import set_rules_version
            set_rules_version(max_version)
        except Exception:
            pass
    except Exception as e:
        if conn:
            conn.close()
        print(f"[db] using local rules ({e})")
        _cache.update(at=now, ttl=FAIL_TTL, rules=list(RULES_DATA), facts=list(FACTS_DATA), source="local-fallback", flag_events=list(_memory_events), flag_events_loaded=True)
    return _cache["rules"], _cache["facts"], _cache["source"]


def get_workspace_vault(workspace_id: str = "default", force: bool = False) -> Tuple[List[Dict], List[Dict], str]:
    """Return baseline rules plus rules scoped to the requested workspace."""
    workspace = (workspace_id or "default").strip() or "default"
    rules, facts, source = get_vault(force=force)
    scoped_rules = [
        dict(rule) for rule in rules
        if rule.get("workspace_id", "default") == "default"
        or (workspace != "default" and rule.get("workspace_id") == workspace)
    ]
    return scoped_rules, facts, source


def rules_by_id() -> Dict[int, Dict]:
    return {r["rule_id"]: r for r in get_vault()[0]}


def save_scan(scan_id: str, score: int, status: str, input_type: str, payload: dict) -> None:
    """Best-effort audit log. Called after the response is sent, so it never slows the user."""
    conn = None
    try:
        conn = _connect()
        if not conn:
            return
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO scans (scan_id, readiness_score, status, input_type, payload)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT (scan_id) DO NOTHING;""",
                (scan_id, score, status, input_type, Json(payload)),
            )
        conn.commit()
    except Exception as e:
        print(f"[db] save_scan failed: {e}")
    finally:
        if conn:
            conn.close()


def log_flag_event(scan_id: str, rule_id: int, action: str, reason: str) -> str:
    """Returns where it was stored: 'neon' or 'memory'."""
    event = {"scan_id": scan_id, "rule_id": rule_id, "action": action, "reason": reason or ""}
    _memory_events.append(event)
    if _cache.get("flag_events") is None:
        _cache["flag_events"] = []
    _cache["flag_events"].append(event)
    _cache["flag_events_loaded"] = True

    def _persist() -> None:
        conn = None
        try:
            conn = _connect()
            if not conn:
                return
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO flag_events (scan_id, rule_id, action, reason) VALUES (%s, %s, %s, %s);",
                    (scan_id, rule_id, action, reason or ""),
                )
            conn.commit()
        except Exception as exc:
            print(f"[db] log_flag_event failed, keeping in memory: {exc}")
        finally:
            if conn:
                conn.close()

    threading.Thread(target=_persist, daemon=True, name="flag-event-persist").start()
    return "memory"


def get_flag_events() -> List[Dict]:
    if _cache.get("flag_events_loaded"):
        return list(_cache.get("flag_events") or _memory_events)
    conn = None
    try:
        conn = _connect()
        if conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT scan_id, rule_id, action, reason FROM flag_events;")
                rows = [dict(r) for r in cur.fetchall()]
            return rows
    except Exception as e:
        print(f"[db] get_flag_events failed, using memory: {e}")
    finally:
        if conn:
            conn.close()
    return list(_memory_events)
