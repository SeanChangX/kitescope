import asyncio
import logging
import os
import time
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from pydantic import BaseModel
import httpx

log = logging.getLogger(__name__)

# Shared vision HTTP client (connection pool) to avoid opening a new connection per preview request.
_vision_client: httpx.AsyncClient | None = None
_vision_client_lock = asyncio.Lock()
_VISION_PREVIEW_CONCURRENCY = max(1, min(20, int(os.getenv("VISION_PREVIEW_CONCURRENCY", "8"))))
_preview_semaphore = asyncio.Semaphore(_VISION_PREVIEW_CONCURRENCY)


async def get_vision_client() -> httpx.AsyncClient:
    global _vision_client
    async with _vision_client_lock:
        if _vision_client is None:
            limits = httpx.Limits(max_keepalive_connections=8, max_connections=16, keepalive_expiry=30.0)
            _vision_client = httpx.AsyncClient(timeout=45.0, limits=limits)
        return _vision_client


async def close_vision_client() -> None:
    global _vision_client
    async with _vision_client_lock:
        if _vision_client is not None:
            await _vision_client.aclose()
            _vision_client = None

# --- Preview cache -----------------------------------------------------------
# For each (source_id, overlay) we keep the latest JPEG in memory. All clients
# requesting the same source within the TTL window get the cached frame instead
# of each hitting vision independently.  With 30 users x 4 sources every 5 s =
# 120 req/5s, this reduces actual vision calls to 4 per TTL window.

_PREVIEW_CACHE_TTL = float(os.getenv("PREVIEW_CACHE_TTL", "3.0"))

# (source_id, overlay_bool) -> (jpeg_bytes, detection_count_header|None, monotonic_timestamp)
_preview_cache: dict[tuple[int, bool], tuple[bytes, str | None, float]] = {}

# Per-key locks: when cache is stale, only ONE coroutine fetches from vision;
# others wait on the lock and then read the freshly-populated cache.
_preview_key_locks: dict[tuple[int, bool], asyncio.Lock] = {}
_preview_key_locks_guard = asyncio.Lock()


async def _get_key_lock(key: tuple[int, bool]) -> asyncio.Lock:
    async with _preview_key_locks_guard:
        if key not in _preview_key_locks:
            _preview_key_locks[key] = asyncio.Lock()
        return _preview_key_locks[key]

from datetime import timedelta
from database import get_db, AsyncSessionLocal
from models import Source, CountHistory, PendingSource, BotConfig
from utils import detect_source_type
from auth_admin import get_current_user

router = APIRouter()


def _utc_iso(dt: datetime | None) -> str:
    """Return ISO string with Z suffix so frontend parses as UTC and displays in local time."""
    if dt is None:
        return ""
    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()


class SuggestSourceBody(BaseModel):
    url: str
    location: str = ""
    name: str = ""


@router.post("/sources/suggest")
async def suggest_source(
    body: SuggestSourceBody,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Submit a new stream suggestion (URL + location). Type is auto-detected. Requires login."""
    source_type = detect_source_type(body.url)
    pending = PendingSource(
        url=body.url,
        type=source_type,
        name=body.name or "",
        location=body.location or "",
        user_id=user.id,
    )
    db.add(pending)
    await db.flush()
    await db.refresh(pending)
    return {"id": pending.id, "type": source_type, "message": "Submitted for approval"}


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    from weather import COORDS_PATTERN
    from location import reverse_geocode
    result = await db.execute(select(Source).where(Source.enabled == True))
    sources = result.scalars().all()
    out = []
    for s in sources:
        loc = s.location or ""
        location_display = loc
        m = COORDS_PATTERN.match(loc.strip()) if loc else None
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                addr = await reverse_geocode(lat, lon)
                if addr:
                    location_display = addr
        # direct_embed = recognition off (show pill). url only when embeddable as img (not YouTube)
        direct_embed = getattr(s, "direct_embed", False)
        stype = (s.type or "").strip().lower()
        include_url = direct_embed and stype != "youtube_live"
        out.append({
            "id": s.id,
            "name": s.name,
            "type": s.type,
            "location": s.location,
            "location_display": location_display,
            "enabled": s.enabled,
            "direct_embed": direct_embed,
            **({"url": s.url} if include_url else {}),
        })
    return out


def _make_preview_response(data: bytes, detection_count: str | None) -> Response:
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
    if detection_count is not None:
        headers["X-Detection-Count"] = detection_count
    return Response(content=data, media_type="image/jpeg", headers=headers)


@router.get("/sources/{source_id}/preview")
async def source_preview(
    source_id: int,
    overlay: bool = Query(True, description="Draw detection boxes on frame"),
    t: str = Query("0", description="Preview tick (cache-bust only; ignored by cache key)"),
):
    """Live preview frame. Cached per (source_id, overlay) so 30 concurrent
    users only cause 1 vision call per TTL window instead of 30."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source).where(Source.id == source_id, Source.enabled == True)
        )
        row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    if (row.type or "").strip().lower() == "go2rtc" and getattr(row, "origin_url", None):
        from go2rtc_client import ensure_go2rtc_stream
        await ensure_go2rtc_stream(row.origin_url, row.id)
    direct_embed = getattr(row, "direct_embed", False)
    if direct_embed:
        overlay = False

    cache_key = (source_id, bool(overlay))

    # Fast path: serve from cache if fresh.
    cached = _preview_cache.get(cache_key)
    if cached and (time.monotonic() - cached[2]) < _PREVIEW_CACHE_TTL:
        return _make_preview_response(cached[0], cached[1])

    # Cache miss / stale. Acquire per-key lock so only one coroutine fetches
    # from vision; all other concurrent callers wait here and then hit the
    # fresh cache above or read the just-populated entry below.
    lock = await _get_key_lock(cache_key)
    async with lock:
        # Re-check after acquiring lock (another waiter may have refreshed).
        cached = _preview_cache.get(cache_key)
        if cached and (time.monotonic() - cached[2]) < _PREVIEW_CACHE_TTL:
            return _make_preview_response(cached[0], cached[1])

        vision_url = os.getenv("VISION_URL", "http://vision:9000")
        try:
            client = await get_vision_client()
            async with _preview_semaphore:
                r = await client.get(
                    f"{vision_url}/snapshot",
                    params={"url": row.url, "overlay": overlay, "t": t},
                )
            if r.status_code != 200:
                body_preview = (r.text or (r.content.decode("utf-8", errors="replace") if r.content else ""))[:200]
                log.warning("preview source_id=%s vision_status=%s body=%s", source_id, r.status_code, body_preview)
                raise HTTPException(status_code=502, detail="Vision snapshot failed")
            detection_count = r.headers.get("X-Detection-Count")
            _preview_cache[cache_key] = (r.content, detection_count, time.monotonic())
            return _make_preview_response(r.content, detection_count)
        except httpx.RequestError as e:
            log.warning(
                "preview source_id=%s vision unreachable: %s %s",
                source_id, type(e).__name__, str(e) or repr(e),
            )
            raise HTTPException(status_code=502, detail="Vision service unavailable")


async def warm_preview_cache() -> None:
    """Pre-populate preview cache for all enabled non-direct_embed sources so first user gets fast previews."""
    vision_url = os.getenv("VISION_URL", "http://vision:9000")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Source).where(Source.enabled == True))
        rows = result.scalars().all()
    for row in rows:
        if getattr(row, "direct_embed", False):
            continue
        cache_key = (row.id, True)
        if (row.type or "").strip().lower() == "go2rtc" and getattr(row, "origin_url", None):
            try:
                from go2rtc_client import ensure_go2rtc_stream
                await ensure_go2rtc_stream(row.origin_url, row.id)
            except Exception:
                pass
        try:
            client = await get_vision_client()
            async with _preview_semaphore:
                r = await client.get(
                    f"{vision_url}/snapshot",
                    params={"url": row.url, "overlay": True, "t": "0"},
                )
            if r.status_code == 200 and r.content:
                detection_count = r.headers.get("X-Detection-Count")
                _preview_cache[cache_key] = (r.content, detection_count, time.monotonic())
        except Exception:
            pass
        await asyncio.sleep(1)


_GUEST_HOURS_MIN, _GUEST_HOURS_MAX = 1, 8760  # 1 hour to 365 days

@router.get("/history-config")
async def get_history_config(db: AsyncSession = Depends(get_db)):
    """Public: return guest history config (hours to show, interval) for home page cards."""
    result = await db.execute(
        select(BotConfig).where(BotConfig.key.in_(["history_guest_hours", "history_guest_days", "history_default_interval"]))
    )
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    guest_hours = 24
    try:
        if by_key.get("history_guest_hours") is not None:
            guest_hours = max(_GUEST_HOURS_MIN, min(_GUEST_HOURS_MAX, int(by_key.get("history_guest_hours") or "24")))
        else:
            days = max(1, min(365, int(by_key.get("history_guest_days") or "1")))
            guest_hours = days * 24
    except (TypeError, ValueError):
        pass
    default_interval = by_key.get("history_default_interval") or "hour"
    if default_interval not in ("minute", "5min", "10min", "30min", "hour", "day"):
        default_interval = "hour"
    return {"guest_hours": guest_hours, "default_interval": default_interval}


@router.get("/history")
async def get_history(
    source_id: int | None = None,
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    interval: str = Query("hour", pattern="^(minute|hour|day|5min|10min|30min)$"),
    db: AsyncSession = Depends(get_db),
):
    if from_ts is None:
        ret = await db.execute(select(BotConfig).where(BotConfig.key == "history_retention_days"))
        row = ret.scalar_one_or_none()
        days = int(row.value) if row and row.value else 30
        from_ts = datetime.utcnow() - timedelta(days=days)
    q = select(CountHistory).where(CountHistory.recorded_at >= from_ts)
    if source_id is not None:
        q = q.where(CountHistory.source_id == source_id)
    if to_ts:
        q = q.where(CountHistory.recorded_at <= to_ts)
    q = q.order_by(CountHistory.recorded_at.asc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [{"source_id": r.source_id, "count": r.count, "recorded_at": _utc_iso(r.recorded_at)} for r in rows]


@router.get("/counts")
async def current_counts(db: AsyncSession = Depends(get_db)):
    # Placeholder: vision service will POST counts; here return latest from history or empty
    result = await db.execute(
        select(CountHistory).order_by(CountHistory.recorded_at.desc()).limit(100)
    )
    rows = result.scalars().all()
    by_source = {}
    for r in rows:
        if r.source_id not in by_source:
            by_source[r.source_id] = {"count": r.count, "recorded_at": _utc_iso(r.recorded_at)}
    return by_source


@router.get("/weather")
async def get_weather(location: str = Query("", description="Place name or lat,lon for weather")):
    """Kite-relevant weather: temp, wind at 10m/80m, condition. Returns text + detail for dashboard."""
    from weather import get_weather_detail
    detail = await get_weather_detail(location or "")
    if not detail:
        return {"text": "", "detail": None}
    return {"text": detail.get("text", ""), "detail": {k: v for k, v in detail.items() if k != "text"}}
