import logging
import os
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from pydantic import BaseModel
import httpx

log = logging.getLogger(__name__)

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


@router.get("/sources/{source_id}/preview")
async def source_preview(
    source_id: int,
    overlay: bool = Query(True, description="Draw detection boxes on frame"),
    t: str = Query("0", description="Preview tick; vision uses t*5 sec for YouTube seek"),
):
    """Live preview frame for an approved source. overlay=1 draws detection boxes. t=tick for YouTube time seek. Guest-accessible."""
    # Use a short-lived session so we don't hold a DB connection during the long vision call (avoids pool exhaustion).
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
    vision_url = os.getenv("VISION_URL", "http://vision:9000")
    try:
        # Vision fetches NVR + runs detection; allow up to 45s (slow cameras / first-frame)
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(
                f"{vision_url}/snapshot",
                params={"url": row.url, "overlay": overlay, "t": t},
            )
            if r.status_code != 200:
                body_preview = (r.text or (r.content.decode("utf-8", errors="replace") if r.content else ""))[:200]
                log.warning("preview source_id=%s vision_status=%s body=%s", source_id, r.status_code, body_preview)
                raise HTTPException(status_code=502, detail="Vision snapshot failed")
            headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
            if "X-Detection-Count" in r.headers:
                headers["X-Detection-Count"] = r.headers["X-Detection-Count"]
            return Response(content=r.content, media_type="image/jpeg", headers=headers)
    except httpx.RequestError as e:
        log.warning(
            "preview source_id=%s vision unreachable: %s %s",
            source_id, type(e).__name__, str(e) or repr(e),
        )
        raise HTTPException(status_code=502, detail="Vision service unavailable")


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
