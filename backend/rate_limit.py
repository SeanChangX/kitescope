"""
In-memory rate limit for admin auth (login/setup). Per-IP sliding window;
no lockout, only throttle to avoid burst of requests (e.g. many tabs) causing a ban.
"""
import os
import time
from collections import defaultdict
from fastapi import Request, HTTPException

# Sliding window: 60 seconds, max 20 requests per IP for admin auth combined.
_ADMIN_AUTH_WINDOW_SEC = 60
_ADMIN_AUTH_MAX_PER_WINDOW = 20

# Only trust X-Forwarded-For when the direct client is in this set (e.g. reverse proxy, Cloudflare Tunnel).
# Comma-separated list: 127.0.0.1,::1,172.16.0.0/12 or exact IPs. Unset => use request.client.host only.
_TRUSTED_PROXY_IPS = frozenset(
    ip.strip().lower()
    for ip in (os.getenv("TRUSTED_PROXY_FORWARDED_FOR") or "").split(",")
    if ip.strip()
)

_store: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    """Client IP for rate limit. Use X-Forwarded-For only when direct client is in TRUSTED_PROXY_FORWARDED_FOR."""
    direct = (request.client.host if request.client else "").strip().lower()
    if not direct:
        return "unknown"
    if not _TRUSTED_PROXY_IPS:
        return direct
    if direct not in _TRUSTED_PROXY_IPS:
        return direct
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return direct


def _prune(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - _ADMIN_AUTH_WINDOW_SEC
    _store[ip] = [t for t in _store[ip] if t > cutoff]


async def rate_limit_admin_auth(request: Request) -> None:
    """
    Dependency for admin login and setup endpoints. Raises 429 if this IP
    has made too many requests in the last 60 seconds. Counts all requests
    (success and failure) to avoid lockout from a burst of failed requests.
    """
    ip = _client_ip(request)
    _prune(ip)
    if len(_store[ip]) >= _ADMIN_AUTH_MAX_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait a minute and try again.",
        )
    _store[ip].append(time.monotonic())
