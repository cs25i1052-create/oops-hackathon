"""SHA-256 Deterministic + Semantic Scan Cache.
Computes SHA-256 over (text + channel + workspace_id + rules_version + kb_version).
Backed by Neon's `scan_cache(cache_key PK, response_json JSONB, created_at)` table
with a bounded in-memory LRU fallback.
CRITICAL RULE: Never caches or serves responses where ai_status != 'ok'."""
import copy
import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

import db
from schemas import normalize_channel

MAX_MEMORY_CACHE_ITEMS = 200  # Bounded for Render 512 MB RAM
_mem_lock = threading.Lock()
_mem_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_known_misses: set[str] = set()
_cache_warm = False


def make_cache_key(
    text: str,
    channel: str = "general",
    workspace_id: str = "default",
    rules_version: int = 1,
    kb_version: int = 1,
) -> str:
    """Builds a deterministic SHA-256 hex digest over normalized scan inputs."""
    norm_text = (text or "").strip()
    norm_ch = normalize_channel(channel)
    norm_ws = (workspace_id or "default").strip() or "default"
    raw = f"v3|{norm_ws}|{norm_ch}|r:{int(rules_version)}|kb:{int(kb_version)}|{norm_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mem_get(cache_key: str) -> Optional[Dict[str, Any]]:
    with _mem_lock:
        item = _mem_cache.get(cache_key)
        if item is not None:
            _mem_cache.move_to_end(cache_key)
            return copy.deepcopy(item)
        return None


def _mem_set(cache_key: str, payload: Dict[str, Any]) -> None:
    with _mem_lock:
        _mem_cache[cache_key] = copy.deepcopy(payload)
        _mem_cache.move_to_end(cache_key)
        while len(_mem_cache) > MAX_MEMORY_CACHE_ITEMS:
            _mem_cache.popitem(last=False)


def get_cached_scan(cache_key: str) -> Optional[Dict[str, Any]]:
    """Looks up a cached ScanResponse dict by cache_key.
    Returns a copy with `cached=True`, or None on miss / degraded status."""
    # 1. Fast path: check in-memory LRU first (saves Neon compute & latency)
    mem_hit = _mem_get(cache_key)
    if mem_hit and mem_hit.get("ai_status") == "ok":
        mem_hit["cached"] = True
        return mem_hit

    global _cache_warm
    with _mem_lock:
        if cache_key in _known_misses:
            return None

    # 2. Check Neon `scan_cache` table
    try:
        conn = db._connect()
        if not conn:
            with _mem_lock:
                _known_misses.add(cache_key)
                _cache_warm = True
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT response_json FROM public.scan_cache WHERE cache_key = %s;",
                    (cache_key,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row or not row[0]:
            with _mem_lock:
                _known_misses.add(cache_key)
                _cache_warm = True
            return None

        data = row[0]
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict) or data.get("ai_status") != "ok":
            return None

        data["cached"] = True
        _mem_set(cache_key, data)
        with _mem_lock:
            _cache_warm = True
        return copy.deepcopy(data)
    except Exception as e:
        with _mem_lock:
            _known_misses.add(cache_key)
            _cache_warm = True
        print(f"[cache] get_cached_scan fallback (table may not exist yet): {e}")
        return None


def set_cached_scan(cache_key: str, response_data: Dict[str, Any]) -> bool:
    """Stores a ScanResponse dict in memory and Neon `scan_cache`.
    Skips caching if `ai_status != 'ok'`."""
    if not isinstance(response_data, dict):
        return False
    if response_data.get("ai_status") != "ok":
        return False

    to_store = copy.deepcopy(response_data)
    to_store["cached"] = True
    _mem_set(cache_key, to_store)
    with _mem_lock:
        try:
            _known_misses.discard(cache_key)
        except AttributeError:
            _known_misses.pop(cache_key, None)

    def _persist_cache_entry() -> None:
        try:
            conn = db._connect()
            if not conn:
                return
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO public.scan_cache (cache_key, response_json)
                       VALUES (%s, %s::jsonb)
                       ON CONFLICT (cache_key) DO UPDATE SET response_json = EXCLUDED.response_json,
                       created_at = CURRENT_TIMESTAMP;""",
                    (cache_key, json.dumps(to_store)),
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            print(f"[cache] set_cached_scan Neon write skipped: {exc}")

    threading.Thread(target=_persist_cache_entry, daemon=True, name="scan-cache-persist").start()
    return True


def invalidate_cache() -> None:
    """Clears in-memory and Neon scan_cache when brand rules or KB facts are modified."""
    global _cache_warm
    with _mem_lock:
        _mem_cache.clear()
        _known_misses.clear()
        _cache_warm = False

    def _delete_neon_cache() -> None:
        try:
            conn = db._connect()
            if not conn:
                return
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.scan_cache;")
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            print(f"[cache] invalidate_cache Neon delete skipped: {e}")

    threading.Thread(target=_delete_neon_cache, daemon=True, name="scan-cache-invalidate").start()
