"""Internal API for vision service: sources list (with url) and push counts."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime
import os

from database import get_db
from models import Source, CountHistory

router = APIRouter()
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")


def _check_internal(x_internal_secret: str | None = Header(None, alias="X-Internal-Secret")):
    if INTERNAL_SECRET and x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/sources")
async def internal_list_sources(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_check_internal),
):
    """Return enabled sources with url for vision ingestion. Skip direct_embed (recognition disabled)."""
    result = await db.execute(select(Source).where(Source.enabled == True))
    rows = result.scalars().all()
    from go2rtc_client import ensure_go2rtc_stream
    for s in rows:
        if (s.type or "").strip().lower() == "go2rtc" and getattr(s, "origin_url", None):
            await ensure_go2rtc_stream(s.origin_url, s.id)
    out = []
    for s in rows:
        if getattr(s, "direct_embed", False):
            continue
        out.append({
            "id": s.id,
            "url": s.url,
            "type": s.type,
            "pull_interval_sec": s.pull_interval_sec,
        })
    return out


class CountPayload(BaseModel):
    source_id: int
    count: float


@router.post("/counts")
async def internal_push_count(
    body: CountPayload,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_check_internal),
):
    """Vision service posts current count for a source. Appended to history."""
    rec = CountHistory(source_id=body.source_id, count=body.count, recorded_at=datetime.utcnow())
    db.add(rec)
    await db.flush()
    return {"ok": True}
