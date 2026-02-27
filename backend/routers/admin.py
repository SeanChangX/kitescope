import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from database import get_db
from models import Source, PendingSource, User, BotConfig, CountHistory, NotificationSubscription
from auth_admin import get_current_admin
from utils import should_proxy_via_go2rtc
from go2rtc_client import register_go2rtc_stream_by_name, delete_go2rtc_stream

router = APIRouter()

# Unicode dash/minus variants that break NVR auth (e.g. pass=); normalize to ASCII hyphen
_UNICODE_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2212\uff0d]")


def _normalize_source_url(url: str) -> str:
    """Replace Unicode dash/minus in URL with ASCII hyphen so NVR query params work."""
    if not url:
        return url
    return _UNICODE_DASHES.sub("-", url)


def _admin_only(admin=Depends(get_current_admin)):
    return admin


@router.get("/sources/pending")
async def list_pending_sources(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(PendingSource).order_by(PendingSource.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "url": r.url,
            "type": r.type,
            "name": r.name,
            "location": r.location,
            "user_id": r.user_id,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/sources/pending/{id}/preview")
async def pending_source_preview(
    id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """Proxy vision snapshot for pending source URL. Returns image/jpeg or 502 if vision fails.
    For RTSP and http_snapshot we register with go2rtc first so vision gets a fast MJPEG snapshot."""
    import os
    from fastapi.responses import Response
    import httpx
    result = await db.execute(select(PendingSource).where(PendingSource.id == id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Pending source not found")
    vision_url = os.getenv("VISION_URL", "http://vision:9000")
    snapshot_url = row.url
    stype = (row.type or "").strip().lower()
    if stype in ("rtsp", "http_snapshot"):
        stream_name = f"kitescope_pending_{id}"
        go2rtc_url = await register_go2rtc_stream_by_name(row.url, stream_name)
        if go2rtc_url:
            snapshot_url = go2rtc_url
            import asyncio
            await asyncio.sleep(2)  # give go2rtc time to pull first frame
    try:
        timeout = 25.0 if snapshot_url != row.url else 15.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{vision_url}/snapshot", params={"url": snapshot_url})
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail="Vision snapshot failed")
            return Response(content=r.content, media_type="image/jpeg")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Vision service unavailable")


@router.post("/sources/pending/{id}/approve")
async def approve_pending_source(
    id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(PendingSource).where(PendingSource.id == id))
    pending = result.scalar_one_or_none()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending source not found")
    normalized_url = _normalize_source_url(pending.url)
    stype = (pending.type or "").strip().lower()
    source = Source(
        url=normalized_url,
        type=stype or "http_snapshot",
        name=pending.name or "",
        location=pending.location or "",
        enabled=True,
    )
    db.add(source)
    await db.flush()
    if should_proxy_via_go2rtc(source.type):
        from go2rtc_client import register_go2rtc_stream
        go2rtc_url = await register_go2rtc_stream(normalized_url, source.id)
        if go2rtc_url:
            source.url = go2rtc_url
            source.type = "go2rtc"
            source.origin_url = normalized_url
        # if register failed, keep original url/type (direct adapter will be used)
    await db.delete(pending)
    await db.flush()
    return {"message": "Approved", "source_id": source.id}


@router.delete("/sources/pending/{id}")
async def delete_pending_source(
    id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(delete(PendingSource).where(PendingSource.id == id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pending source not found")
    await db.flush()
    await delete_go2rtc_stream(f"kitescope_pending_{id}")
    return {"message": "Deleted"}


@router.get("/sources")
async def list_sources(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """List all approved (live) sources for admin management."""
    result = await db.execute(select(Source).order_by(Source.id))
    rows = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "type": s.type,
            "location": s.location,
            "enabled": s.enabled,
            "direct_embed": getattr(s, "direct_embed", False),
            "url": s.url,
        }
        for s in rows
    ]


class UpdateSourceBody(BaseModel):
    name: str | None = None
    location: str | None = None
    enabled: bool | None = None
    direct_embed: bool | None = None
    url: str | None = None


@router.patch("/sources/{source_id}")
async def update_source(
    source_id: int,
    body: UpdateSourceBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(Source).where(Source.id == source_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    if body.name is not None:
        row.name = body.name[:256] if body.name else ""
    if body.location is not None:
        row.location = body.location[:512] if body.location else ""
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.direct_embed is not None:
        row.direct_embed = body.direct_embed
    if body.url is not None:
        row.url = _normalize_source_url(body.url)[:2048]
    await db.flush()
    return {"message": "Updated", "id": row.id}


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(Source).where(Source.id == source_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    if (getattr(row, "type", None) or "").strip().lower() == "go2rtc" or getattr(row, "origin_url", None):
        await delete_go2rtc_stream(f"kitescope_{source_id}")
    await db.execute(delete(NotificationSubscription).where(NotificationSubscription.source_id == source_id))
    await db.execute(delete(CountHistory).where(CountHistory.source_id == source_id))
    await db.execute(delete(Source).where(Source.id == source_id))
    await db.flush()
    return {"message": "Deleted"}


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "display_name": r.display_name,
            "email": r.email,
            "avatar": r.avatar,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            "last_ip": r.last_ip,
            "banned": r.banned,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.banned = True
    db.add(user)
    await db.flush()
    return {"message": "User banned"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.flush()
    return {"message": "User deleted"}


class BroadcastBody(BaseModel):
    message: str
    user_ids: list[int] | None = None  # None = all non-banned users


@router.post("/notifications/broadcast")
async def broadcast_notification(
    body: BroadcastBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    from notify import send_line_message, send_telegram_message
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    q = select(User).where(User.banned == False)
    if body.user_ids is not None:
        q = q.where(User.id.in_(body.user_ids))
    result = await db.execute(q)
    users = result.scalars().all()
    bot_rows = (await db.execute(select(BotConfig))).scalars().all()
    by_key = {r.key: r.value for r in bot_rows}
    line_token = (by_key.get("line_channel_access_token") or "").strip()
    telegram_token = (by_key.get("telegram_bot_token") or "").strip()
    sent = 0
    for u in users:
        if u.line_id and line_token:
            if await send_line_message(line_token, u.line_id, body.message.strip()):
                sent += 1
        if u.telegram_id and telegram_token:
            if await send_telegram_message(telegram_token, u.telegram_id, body.message.strip()):
                sent += 1
    return {"message": "Broadcast sent", "recipients": len(users), "sent": sent}


def _mask(value: str | None) -> str:
    if not value or len(value) < 8:
        return "***" if value else ""
    return value[:4] + "***" + value[-2:] if len(value) > 6 else "***"


@router.get("/settings/bots")
async def get_bot_settings(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(BotConfig))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    return {
        "line": {
            "channel_id": by_key.get("line_channel_id") or "",
            "channel_secret": _mask(by_key.get("line_channel_secret")),
            "channel_access_token": _mask(by_key.get("line_channel_access_token")),
            "configured": bool(by_key.get("line_channel_secret") and by_key.get("line_channel_access_token")),
        },
        "telegram": {
            "bot_token": _mask(by_key.get("telegram_bot_token")),
            "configured": bool(by_key.get("telegram_bot_token")),
        },
    }


class BotSettingsBody(BaseModel):
    line_channel_id: str | None = None
    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    telegram_bot_token: str | None = None


@router.put("/settings/bots")
async def put_bot_settings(
    body: BotSettingsBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    keys_update = []
    if body.line_channel_id is not None:
        keys_update.append(("line_channel_id", body.line_channel_id))
    if body.line_channel_secret is not None and body.line_channel_secret.strip():
        keys_update.append(("line_channel_secret", body.line_channel_secret.strip()))
    if body.line_channel_access_token is not None and body.line_channel_access_token.strip():
        keys_update.append(("line_channel_access_token", body.line_channel_access_token.strip()))
    if body.telegram_bot_token is not None and body.telegram_bot_token.strip():
        keys_update.append(("telegram_bot_token", body.telegram_bot_token.strip()))
    from datetime import datetime
    now = datetime.utcnow()
    for key, value in keys_update:
        r = await db.execute(select(BotConfig).where(BotConfig.key == key))
        row = r.scalar_one_or_none()
        if row:
            row.value = value
            row.updated_at = now
        else:
            db.add(BotConfig(key=key, value=value, updated_at=now))
    await db.flush()
    return {"message": "Saved"}


@router.get("/settings/history")
async def get_history_settings(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(BotConfig).where(BotConfig.key.in_(["history_retention_days", "history_default_interval"])))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    return {
        "retention_days": int(by_key.get("history_retention_days") or "30"),
        "default_interval": by_key.get("history_default_interval") or "hour",
    }


class HistorySettingsBody(BaseModel):
    retention_days: int | None = None
    default_interval: str | None = None


@router.put("/settings/history")
async def put_history_settings(
    body: HistorySettingsBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    from datetime import datetime
    now = datetime.utcnow()
    if body.retention_days is not None and body.retention_days >= 1:
        r = await db.execute(select(BotConfig).where(BotConfig.key == "history_retention_days"))
        row = r.scalar_one_or_none()
        if row:
            row.value = str(body.retention_days)
            row.updated_at = now
        else:
            db.add(BotConfig(key="history_retention_days", value=str(body.retention_days), updated_at=now))
    if body.default_interval is not None and body.default_interval in ("minute", "hour", "day"):
        r = await db.execute(select(BotConfig).where(BotConfig.key == "history_default_interval"))
        row = r.scalar_one_or_none()
        if row:
            row.value = body.default_interval
            row.updated_at = now
        else:
            db.add(BotConfig(key="history_default_interval", value=body.default_interval, updated_at=now))
    await db.flush()
    return {"message": "Saved"}
