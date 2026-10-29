"""Proxy-aware Token Bucket Rate Limiter for Render Free Web Service.
Reads the first IP in X-Forwarded-For (never relying solely on request.client.host,
which is Render's internal load balancer) and bounds memory usage for Render's 512 MB limit."""
import math
import os
import threading
import time
from typing import Dict, Tuple

from fastapi import HTTPException, Request

# Generous defaults for live hackathon judging while blocking automated floods
BUCKET_CAPACITY = float(os.getenv("RATE_LIMIT_CAPACITY", "30"))       # burst of 30 scans
REFILL_RATE = float(os.getenv("RATE_LIMIT_REFILL_PER_SEC", "0.1"))    # refills 30 tokens every 5 minutes
MAX_TRACKED_IPS = 2048                                                # strict cap for Render 512 MB RAM

_lock = threading.Lock()
# ip -> (tokens_remaining, last_updated_monotonic)
_buckets: Dict[str, Tuple[float, float]] = {}


def get_client_ip(request: Request) -> str:
    """Extracts the real client IP from the first entry in X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def _prune_stale_buckets(now: float) -> None:
    """Evicts oldest or full buckets when table exceeds MAX_TRACKED_IPS."""
    if len(_buckets) <= MAX_TRACKED_IPS:
        return
    stale_cutoff = now - 300.0  # 5 minutes idle
    stale_keys = [ip for ip, (_, ts) in _buckets.items() if ts < stale_cutoff]
    for k in stale_keys:
        _buckets.pop(k, None)
    if len(_buckets) > MAX_TRACKED_IPS:
        # Drop oldest half if still over capacity
        sorted_ips = sorted(_buckets.items(), key=lambda kv: kv[1][1])
        for ip, _ in sorted_ips[: len(_buckets) // 2]:
            _buckets.pop(ip, None)


def consume_token(ip: str, cost: float = 1.0) -> Tuple[bool, float, float]:
    """Consumes `cost` tokens from `ip`'s bucket.
    Returns (allowed, remaining_tokens, retry_after_seconds)."""
    now = time.monotonic()
    with _lock:
        _prune_stale_buckets(now)
        tokens, last_ts = _buckets.get(ip, (BUCKET_CAPACITY, now))
        elapsed = max(0.0, now - last_ts)
        tokens = min(BUCKET_CAPACITY, tokens + elapsed * REFILL_RATE)

        if tokens >= cost:
            tokens -= cost
            _buckets[ip] = (tokens, now)
            return True, round(tokens, 2), 0.0

        deficit = cost - tokens
        retry_after = deficit / REFILL_RATE if REFILL_RATE > 0 else 5.0
        _buckets[ip] = (tokens, now)
        return False, round(tokens, 2), round(retry_after, 2)


def rate_limit_scan(request: Request) -> str:
    """FastAPI dependency for scan endpoints. Raises HTTP 429 with Retry-After if bucket is empty."""
    ip = get_client_ip(request)
    allowed, _remaining, retry_after = consume_token(ip, cost=1.0)
    if not allowed:
        wait_sec = max(1, int(math.ceil(retry_after)))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for IP {ip}. Please retry in {wait_sec}s.",
            headers={"Retry-After": str(wait_sec)},
        )
    return ip


def reset_rate_limits() -> None:
    """Clears all rate-limit buckets (used by unit tests)."""
    with _lock:
        _buckets.clear()
