import io
import json
import os
import re
import zipfile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func, or_
from pydantic import BaseModel

from datetime import datetime
from database import get_db
from models import Source, PendingSource, User, AdminUser, BotConfig, CountHistory, NotificationSubscription
from auth_admin import get_current_admin
from utils import should_proxy_via_go2rtc
from go2rtc_client import register_go2rtc_stream_by_name, delete_go2rtc_stream
from notify import DEFAULT_NOTIFY_FORMAT
from secret_config import get_internal_secret

router = APIRouter()

# Vision stats history (last 60 points, 1 per minute). Persisted in backend so refresh keeps history.
_VISION_STATS_HISTORY: list[dict] = []
_VISION_HISTORY_MAX = 60

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
    result = await db.execute(
        select(PendingSource, User)
        .outerjoin(User, PendingSource.user_id == User.id)
        .order_by(PendingSource.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": p.id,
            "url": p.url,
            "type": p.type,
            "name": p.name,
            "location": p.location,
            "user_id": p.user_id,
            "submitted_by": (u.display_name or u.email or f"User #{p.user_id}").strip() if u else None,
            "created_at": p.created_at.isoformat(),
        }
        for p, u in rows
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


_USER_SORT_COLUMNS = {
    "id": User.id,
    "display_name": User.display_name,
    "email": User.email,
    "last_seen": User.last_seen,
    "banned": User.banned,
    "created_at": User.created_at,
}


def _user_search_filter(q: str):
    """Build filter for user search: display_name, email, or id (if q is numeric). Escapes LIKE wildcards."""
    q = (q or "").strip()
    if not q:
        return None
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    conditions = [
        User.display_name.like(pattern),
        User.email.like(pattern),
    ]
    if q.isdigit():
        conditions.append(User.id == int(q))
    return or_(*conditions)


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc",
    q: str | None = None,
):
    """List users with pagination, sort, and optional search (q: name, email, or id)."""
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    order_asc = order.lower() == "asc"
    col = _USER_SORT_COLUMNS.get(sort_by) or User.created_at
    order_col = col.asc() if order_asc else col.desc()
    where = _user_search_filter(q or "")
    base = select(User)
    if where is not None:
        base = base.where(where)
    count_q = select(func.count()).select_from(User)
    if where is not None:
        count_q = count_q.where(where)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0
    result = await db.execute(
        base.order_by(order_col).limit(limit).offset(offset)
    )
    rows = result.scalars().all()
    out = []
    for r in rows:
        channels = []
        if r.line_id:
            channels.append("line")
        if r.telegram_id:
            channels.append("telegram")
        channel = ",".join(channels) if channels else ""
        out.append({
            "id": r.id,
            "display_name": r.display_name,
            "email": r.email,
            "avatar": r.avatar,
            "last_seen": (r.last_seen.isoformat() + "Z") if r.last_seen else None,
            "last_ip": r.last_ip,
            "banned": r.banned,
            "created_at": r.created_at.isoformat(),
            "channel": channel,
        })
    return {"items": out, "total": total}


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


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.banned = False
    db.add(user)
    await db.flush()
    return {"message": "User unbanned"}


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
    await db.execute(delete(NotificationSubscription).where(NotificationSubscription.user_id == user_id))
    await db.execute(update(PendingSource).where(PendingSource.user_id == user_id).values(user_id=None))
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
            "login_channel_id": by_key.get("line_login_channel_id") or "",
            "login_channel_secret": _mask(by_key.get("line_login_channel_secret")),
            "configured": bool(by_key.get("line_channel_secret") and by_key.get("line_channel_access_token")),
        },
        "telegram": {
            "bot_token": _mask(by_key.get("telegram_bot_token")),
            "configured": bool(by_key.get("telegram_bot_token")),
        },
        "public_app_url": (by_key.get("public_app_url") or "").strip().rstrip("/"),
    }


@router.get("/settings/notify-format")
async def get_notify_format(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    result = await db.execute(select(BotConfig).where(BotConfig.key == "notify_format_template"))
    row = result.scalar_one_or_none()
    value = (row.value or "").strip() if row else ""
    return {"format": value or DEFAULT_NOTIFY_FORMAT}


class NotifyFormatBody(BaseModel):
    format: str | None = None


@router.put("/settings/notify-format")
async def put_notify_format(
    body: NotifyFormatBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    now = datetime.utcnow()
    value = (body.format or "").strip() or ""
    r = await db.execute(select(BotConfig).where(BotConfig.key == "notify_format_template"))
    row = r.scalar_one_or_none()
    if row:
        row.value = value
        row.updated_at = now
    else:
        db.add(BotConfig(key="notify_format_template", value=value, updated_at=now))
    await db.flush()
    return {"message": "Saved"}


# Detection model upload/select/delete; shared with vision via MODELS_DIR (e.g. volume mount)
MODELS_DIR = os.getenv("MODELS_DIR", "data/models")
SELECTED_MODEL_FILE = ".selected"  # Filename under MODELS_DIR; vision reads this on startup
VISION_SELECTED_MODEL_KEY = "vision_selected_model"
VISION_CONFIDENCE_THRESHOLD_KEY = "vision_confidence_threshold"

_ALLOWED_MODEL_NAME = re.compile(r"^[a-zA-Z0-9_.-]+\.(onnx|tflite)$")


def _safe_model_filename(name: str) -> str | None:
    """Return basename if it matches allowed pattern (.onnx or .tflite) else None."""
    base = os.path.basename(name).strip()
    return base if _ALLOWED_MODEL_NAME.match(base) else None


def _models_dir_ensure() -> str:
    os.makedirs(MODELS_DIR, exist_ok=True)
    return MODELS_DIR


def _list_model_filenames() -> list[str]:
    """Return sorted list of .onnx and .tflite filenames in MODELS_DIR. Best-effort."""
    try:
        names = [f for f in os.listdir(MODELS_DIR)
                 if (f.endswith(".onnx") or f.endswith(".tflite")) and _ALLOWED_MODEL_NAME.match(f)
                 and os.path.isfile(os.path.join(MODELS_DIR, f))]
        names.sort()
        return names
    except OSError:
        return []


@router.get("/settings/models")
async def get_models(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """List uploaded .onnx and .tflite model filenames, current selection, and confidence threshold."""
    _models_dir_ensure()
    models = []
    try:
        for f in os.listdir(MODELS_DIR):
            if (f.endswith(".onnx") or f.endswith(".tflite")) and _ALLOWED_MODEL_NAME.match(f):
                models.append(f)
    except OSError:
        pass
    models.sort()
    r = await db.execute(select(BotConfig).where(BotConfig.key.in_([VISION_SELECTED_MODEL_KEY, VISION_CONFIDENCE_THRESHOLD_KEY])))
    rows = r.scalars().all()
    by_key = {row.key: row.value for row in rows}
    selected = (by_key.get(VISION_SELECTED_MODEL_KEY) or "").strip() or None
    if selected and selected not in models:
        selected = None
    # Sync DB selection to .selected file so vision applies it on restart (e.g. after backup restore)
    selected_file_path = os.path.join(MODELS_DIR, SELECTED_MODEL_FILE)
    if selected:
        try:
            with open(selected_file_path) as f:
                current = (f.read() or "").strip()
            if current != selected:
                with open(selected_file_path, "w") as f:
                    f.write(selected)
        except OSError:
            try:
                with open(selected_file_path, "w") as f:
                    f.write(selected)
            except OSError:
                pass
    try:
        confidence_threshold = float(by_key.get(VISION_CONFIDENCE_THRESHOLD_KEY) or "0.5")
    except (TypeError, ValueError):
        confidence_threshold = 0.5
    return {"models": models, "selected": selected, "confidence_threshold": confidence_threshold}


@router.post("/settings/models/upload")
async def upload_model(
    file: UploadFile = File(...),
    _: None = Depends(_admin_only),
):
    """Upload an ONNX or TFLite model file. Returns new filename (may be uniquified)."""
    _models_dir_ensure()
    name = _safe_model_filename(file.filename or "")
    if not name:
        raise HTTPException(status_code=400, detail="Invalid or missing filename; use a .onnx or .tflite file")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    path = os.path.join(MODELS_DIR, name)
    if os.path.isfile(path):
        base, ext = os.path.splitext(name)
        for i in range(1, 100):
            name = f"{base}_{i}{ext}"
            path = os.path.join(MODELS_DIR, name)
            if not os.path.isfile(path):
                break
    with open(path, "wb") as f:
        f.write(content)
    return {"filename": name}


@router.delete("/settings/models/{filename:path}")
async def delete_model(
    filename: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """Remove an uploaded model file. If it was selected, selection is cleared."""
    safe = _safe_model_filename(filename)
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid model filename")
    path = os.path.join(MODELS_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Model not found")
    r = await db.execute(select(BotConfig).where(BotConfig.key == VISION_SELECTED_MODEL_KEY))
    row = r.scalar_one_or_none()
    selected = (row.value or "").strip() if row else ""
    if selected == safe:
        raise HTTPException(status_code=409, detail="Cannot delete the model currently in use")
    try:
        os.remove(path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "Deleted"}


class ModelSelectedBody(BaseModel):
    selected: str | None = None
    confidence_threshold: float | None = None


@router.put("/settings/models")
async def put_model_selected(
    body: ModelSelectedBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """Set selected model and/or confidence threshold; tell vision to apply. Empty selected clears selection."""
    import httpx

    def _model_arch(name: str | None) -> str | None:
        if not name:
            return None
        lower = name.lower()
        if lower.endswith(".onnx"):
            return "onnx"
        if lower.endswith(".tflite"):
            return "tflite"
        return None

    selected = (body.selected or "").strip() or None
    confidence_threshold = body.confidence_threshold
    if selected:
        safe = _safe_model_filename(selected)
        if not safe:
            raise HTTPException(status_code=400, detail="Invalid model filename")
        path = os.path.join(MODELS_DIR, safe)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Model file not found")
        selected = safe
    now = datetime.utcnow()
    r = await db.execute(select(BotConfig).where(BotConfig.key == VISION_SELECTED_MODEL_KEY))
    row = r.scalar_one_or_none()
    previous_selected = (row.value or "").strip() if row else ""
    previous_arch = _model_arch(previous_selected or None)
    selected_arch = _model_arch(selected)
    if row:
        row.value = selected or ""
        row.updated_at = now
    else:
        db.add(BotConfig(key=VISION_SELECTED_MODEL_KEY, value=selected or "", updated_at=now))
    await db.flush()
    vision_url = os.getenv("VISION_URL", "http://vision:9000").rstrip("/")
    secret = get_internal_secret()
    switching = bool(selected and selected != previous_selected)
    if selected:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{vision_url}/reload-model",
                    params={"model": selected},
                    headers={"X-Internal-Secret": secret} if secret else None,
                )
                if r.status_code != 200:
                    raise HTTPException(status_code=502, detail="Vision reload failed: " + (r.text or str(r.status_code)))
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail="Vision service unreachable: " + str(e))
    if confidence_threshold is not None:
        v = max(0.0, min(1.0, float(confidence_threshold)))
        now_confidence = datetime.utcnow()
        r = await db.execute(select(BotConfig).where(BotConfig.key == VISION_CONFIDENCE_THRESHOLD_KEY))
        row = r.scalar_one_or_none()
        if row:
            row.value = str(v)
            row.updated_at = now_confidence
        else:
            db.add(BotConfig(key=VISION_CONFIDENCE_THRESHOLD_KEY, value=str(v), updated_at=now_confidence))
        await db.flush()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{vision_url}/config",
                    json={"confidence_threshold": v},
                    headers={"X-Internal-Secret": secret} if secret else None,
                )
                if r.status_code != 200:
                    raise HTTPException(status_code=502, detail="Vision config update failed: " + (r.text or str(r.status_code)))
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail="Vision service unreachable: " + str(e))
    # Persist selection only after runtime apply succeeds so the restart file does
    # not get ahead of the DB transaction on failure.
    _models_dir_ensure()
    selected_file_path = os.path.join(MODELS_DIR, SELECTED_MODEL_FILE)
    try:
        with open(selected_file_path, "w") as f:
            f.write(selected or "")
    except OSError as e:
        raise HTTPException(status_code=500, detail="Failed to persist selected model: " + str(e))
    return {
        "message": "Saved and switching" if switching else ("Saved and applied" if (selected or confidence_threshold is not None) else "Saved"),
        "switching": switching,
        "selected": selected or "",
        "selected_architecture": selected_arch,
        "previous_architecture": previous_arch,
    }


@router.get("/system/status")
async def get_system_status(_: None = Depends(_admin_only)):
    """Return vision service config, detector status, and persisted stats history for admin system page."""
    import httpx
    global _VISION_STATS_HISTORY
    vision_url = os.getenv("VISION_URL", "http://vision:9000").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{vision_url}/config")
            if r.status_code != 200:
                return {
                    "vision_reachable": False,
                    "vision_error": r.text or str(r.status_code),
                    "vision": None,
                    "history": _VISION_STATS_HISTORY[-_VISION_HISTORY_MAX:],
                }
            try:
                data = r.json()
            except Exception as e:
                return {
                    "vision_reachable": False,
                    "vision_error": f"Invalid JSON: {e!s}",
                    "vision": None,
                    "history": _VISION_STATS_HISTORY[-_VISION_HISTORY_MAX:],
                }
            # Append at most once per minute so history persists across page refreshes
            now_ms = round(datetime.utcnow().timestamp() * 1000)
            if not _VISION_STATS_HISTORY or (now_ms - _VISION_STATS_HISTORY[-1]["t"]) >= 50_000:
                snapshot = {
                    "t": now_ms,
                    "inference_speed_ms": data.get("inference_speed_ms"),
                    "cpu_percent": data.get("cpu_percent"),
                    "memory_percent": data.get("memory_percent"),
                }
                _VISION_STATS_HISTORY.append(snapshot)
                if len(_VISION_STATS_HISTORY) > _VISION_HISTORY_MAX:
                    _VISION_STATS_HISTORY = _VISION_STATS_HISTORY[-_VISION_HISTORY_MAX:]
            return {
                "vision_reachable": True,
                "vision": data,
                "history": _VISION_STATS_HISTORY,
            }
    except httpx.RequestError as e:
        return {
            "vision_reachable": False,
            "vision_error": str(e),
            "vision": None,
            "history": _VISION_STATS_HISTORY[-_VISION_HISTORY_MAX:],
        }


class BotSettingsBody(BaseModel):
    line_channel_id: str | None = None
    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    line_login_channel_id: str | None = None
    line_login_channel_secret: str | None = None
    telegram_bot_token: str | None = None
    public_app_url: str | None = None


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
    if body.line_login_channel_id is not None:
        keys_update.append(("line_login_channel_id", body.line_login_channel_id.strip()))
    if body.line_login_channel_secret is not None and body.line_login_channel_secret.strip():
        keys_update.append(("line_login_channel_secret", body.line_login_channel_secret.strip()))
    if body.telegram_bot_token is not None and body.telegram_bot_token.strip():
        keys_update.append(("telegram_bot_token", body.telegram_bot_token.strip()))
    if body.public_app_url is not None:
        keys_update.append(("public_app_url", (body.public_app_url or "").strip().rstrip("/")))
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
    result = await db.execute(select(BotConfig).where(BotConfig.key.in_([
        "history_retention_days", "history_default_interval", "history_guest_hours", "history_guest_days",
    ])))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    guest_hours = 24
    try:
        if by_key.get("history_guest_hours") is not None:
            guest_hours = max(1, min(8760, int(by_key.get("history_guest_hours") or "24")))
        else:
            guest_hours = max(1, min(365, int(by_key.get("history_guest_days") or "1"))) * 24
    except (TypeError, ValueError):
        pass
    return {
        "retention_days": int(by_key.get("history_retention_days") or "30"),
        "default_interval": by_key.get("history_default_interval") or "hour",
        "guest_hours": guest_hours,
    }


class HistorySettingsBody(BaseModel):
    retention_days: int | None = None
    default_interval: str | None = None
    guest_hours: int | None = None


@router.put("/settings/history")
async def put_history_settings(
    body: HistorySettingsBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    now = datetime.utcnow()
    if body.retention_days is not None and body.retention_days >= 1:
        r = await db.execute(select(BotConfig).where(BotConfig.key == "history_retention_days"))
        row = r.scalar_one_or_none()
        if row:
            row.value = str(body.retention_days)
            row.updated_at = now
        else:
            db.add(BotConfig(key="history_retention_days", value=str(body.retention_days), updated_at=now))
    if body.default_interval is not None and body.default_interval in ("minute", "hour", "day", "5min", "10min", "30min"):
        r = await db.execute(select(BotConfig).where(BotConfig.key == "history_default_interval"))
        row = r.scalar_one_or_none()
        if row:
            row.value = body.default_interval
            row.updated_at = now
        else:
            db.add(BotConfig(key="history_default_interval", value=body.default_interval, updated_at=now))
    if body.guest_hours is not None and 1 <= body.guest_hours <= 8760:
        r = await db.execute(select(BotConfig).where(BotConfig.key == "history_guest_hours"))
        row = r.scalar_one_or_none()
        if row:
            row.value = str(body.guest_hours)
            row.updated_at = now
        else:
            db.add(BotConfig(key="history_guest_hours", value=str(body.guest_hours), updated_at=now))
    await db.flush()
    return {"message": "Saved"}


@router.post("/history/clear")
async def clear_history(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """Delete all count_history records. Irreversible."""
    result = await db.execute(delete(CountHistory))
    await db.flush()
    return {"message": "Cleared", "deleted": result.rowcount}


_BACKUP_VERSION = 1
_BOT_KEYS = (
    "line_channel_id", "line_channel_secret", "line_channel_access_token",
    "line_login_channel_id", "line_login_channel_secret", "telegram_bot_token",
    "public_app_url",
)
# Include secret_key in backup/restore so migration carries JWT key; never exposed in GET /settings/bots
_BOT_KEYS_BACKUP = _BOT_KEYS + ("secret_key",)


@router.get("/settings/backup")
async def backup_settings(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """Export admin usernames, sources, pending_sources, users, notification subscriptions, bot config, history settings. Excludes count_history."""
    admin_rows = (await db.execute(select(AdminUser))).scalars().all()
    source_rows = (await db.execute(select(Source).order_by(Source.id))).scalars().all()
    pending_rows = (await db.execute(select(PendingSource).order_by(PendingSource.id))).scalars().all()
    user_rows = (await db.execute(select(User).order_by(User.id))).scalars().all()
    sub_rows = (await db.execute(select(NotificationSubscription).order_by(NotificationSubscription.id))).scalars().all()
    bot_rows = (await db.execute(select(BotConfig).where(BotConfig.key.in_(_BOT_KEYS_BACKUP)))).scalars().all()
    history_rows = (await db.execute(select(BotConfig).where(BotConfig.key.in_([
        "history_retention_days", "history_default_interval", "history_guest_hours", "history_guest_days",
        "notify_format_template", VISION_SELECTED_MODEL_KEY, VISION_CONFIDENCE_THRESHOLD_KEY,
    ])))).scalars().all()
    by_key = {r.key: r.value for r in history_rows}
    guest_hours = 24
    try:
        if by_key.get("history_guest_hours") is not None:
            guest_hours = max(1, min(8760, int(by_key.get("history_guest_hours") or "24")))
        else:
            guest_hours = max(1, min(365, int(by_key.get("history_guest_days") or "1"))) * 24
    except (TypeError, ValueError):
        pass
    payload = {
        "version": _BACKUP_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "admin_usernames": [r.username for r in admin_rows],
        "sources": [
            {"id": r.id, "url": r.url, "type": r.type, "name": r.name or "", "location": r.location or "",
             "enabled": r.enabled, "direct_embed": r.direct_embed, "pull_interval_sec": r.pull_interval_sec,
             "origin_url": r.origin_url, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()}
            for r in source_rows
        ],
        "pending_sources": [
            {"id": r.id, "url": r.url, "type": r.type or "", "name": r.name or "", "location": r.location or "",
             "user_id": r.user_id, "created_at": r.created_at.isoformat()}
            for r in pending_rows
        ],
        "users": [
            {"id": r.id, "line_id": r.line_id, "telegram_id": r.telegram_id, "display_name": r.display_name or "",
             "avatar": r.avatar or "", "email": r.email or "", "banned": r.banned,
             "last_seen": r.last_seen.isoformat() if r.last_seen else None, "last_ip": r.last_ip or "",
             "welcome_sent_at": r.welcome_sent_at.isoformat() if r.welcome_sent_at else None,
             "created_at": r.created_at.isoformat()}
            for r in user_rows
        ],
        "notification_subscriptions": [
            {"id": r.id, "user_id": r.user_id, "source_id": r.source_id, "threshold": r.threshold,
             "release_threshold": r.release_threshold, "channel": r.channel, "cooldown_minutes": r.cooldown_minutes,
             "enabled": r.enabled, "last_notified_at": r.last_notified_at.isoformat() if r.last_notified_at else None,
             "released_at": r.released_at.isoformat() if r.released_at else None, "created_at": r.created_at.isoformat()}
            for r in sub_rows
        ],
        "bot_config": [{"key": r.key, "value": r.value} for r in bot_rows],
        "history_settings": {
            "retention_days": int(by_key.get("history_retention_days") or "30"),
            "default_interval": by_key.get("history_default_interval") or "hour",
            "guest_hours": guest_hours,
        },
        "notify_format": by_key.get("notify_format_template") or "",
        "vision_selected_model": by_key.get(VISION_SELECTED_MODEL_KEY) or "",
        "vision_confidence_threshold": by_key.get(VISION_CONFIDENCE_THRESHOLD_KEY) or "",
        "model_filenames": _list_model_filenames(),
    }
    model_filenames = payload["model_filenames"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(payload, indent=2, ensure_ascii=False))
        for fname in model_filenames:
            path = os.path.join(MODELS_DIR, fname)
            if os.path.isfile(path):
                try:
                    with open(path, "rb") as fp:
                        zf.writestr(fname, fp.read())
                except OSError:
                    pass
    buf.seek(0)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=kitescope-backup-{date_str}.zip"},
    )


class RestoreBody(BaseModel):
    backup: dict


@router.post("/settings/restore")
async def restore_settings(
    body: RestoreBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_admin_only),
):
    """Restore from backup JSON only. Upload backup.json (e.g. extracted from the backup ZIP). Models must be re-uploaded in Model settings."""
    data = body.backup
    if not isinstance(data, dict) or data.get("version") != _BACKUP_VERSION:
        raise HTTPException(status_code=400, detail="Invalid or unsupported backup format")
    sources = data.get("sources")
    pending_sources = data.get("pending_sources")
    users = data.get("users")
    subs = data.get("notification_subscriptions")
    bot_config = data.get("bot_config")
    history_settings = data.get("history_settings") or {}
    if not isinstance(sources, list) or not isinstance(users, list):
        raise HTTPException(status_code=400, detail="Backup must include sources and users lists")
    if not isinstance(pending_sources, list):
        pending_sources = []
    if not isinstance(subs, list):
        subs = []
    if not isinstance(bot_config, list):
        bot_config = []
    # Delete in dependency order
    await db.execute(delete(NotificationSubscription))
    await db.execute(delete(CountHistory))
    await db.execute(delete(Source))
    await db.execute(delete(PendingSource))
    await db.execute(delete(User))
    await db.flush()
    # Insert sources with same ids
    for row in sources:
        if not isinstance(row, dict) or "id" not in row:
            continue
        db.add(Source(
            id=row["id"],
            url=row.get("url", ""),
            type=row.get("type", "http_snapshot"),
            name=row.get("name", ""),
            location=row.get("location", ""),
            enabled=row.get("enabled", True),
            direct_embed=row.get("direct_embed", False),
            pull_interval_sec=int(row.get("pull_interval_sec", 5)),
            origin_url=row.get("origin_url"),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")) if row.get("updated_at") else datetime.utcnow(),
        ))
    await db.flush()
    # Insert users with same ids
    for row in users:
        if not isinstance(row, dict) or "id" not in row:
            continue
        last_seen = None
        if row.get("last_seen"):
            try:
                last_seen = datetime.fromisoformat(str(row["last_seen"]).replace("Z", "+00:00"))
            except Exception:
                pass
        welcome_sent_at = None
        if row.get("welcome_sent_at"):
            try:
                welcome_sent_at = datetime.fromisoformat(str(row["welcome_sent_at"]).replace("Z", "+00:00"))
            except Exception:
                pass
        db.add(User(
            id=row["id"],
            line_id=row.get("line_id"),
            telegram_id=row.get("telegram_id"),
            display_name=row.get("display_name", ""),
            avatar=row.get("avatar", ""),
            email=row.get("email", ""),
            banned=row.get("banned", False),
            last_seen=last_seen,
            last_ip=row.get("last_ip", ""),
            welcome_sent_at=welcome_sent_at,
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row.get("created_at") else datetime.utcnow(),
        ))
    await db.flush()
    # Insert pending_sources (only if user_id is null or exists in restored users)
    user_ids = {r["id"] for r in users if isinstance(r, dict) and "id" in r}
    for row in pending_sources:
        if not isinstance(row, dict) or "id" not in row or "url" not in row:
            continue
        uid = row.get("user_id")
        if uid is not None and uid not in user_ids:
            continue
        db.add(PendingSource(
            id=row["id"],
            url=row["url"],
            type=row.get("type", ""),
            name=row.get("name", ""),
            location=row.get("location", ""),
            user_id=uid,
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row.get("created_at") else datetime.utcnow(),
        ))
    await db.flush()
    # Insert notification_subscriptions (only if user_id and source_id exist in restored data)
    source_ids = {r["id"] for r in sources if isinstance(r, dict) and "id" in r}
    for row in subs:
        if not isinstance(row, dict) or row.get("user_id") not in user_ids or row.get("source_id") not in source_ids:
            continue
        last_nt = None
        if row.get("last_notified_at"):
            try:
                last_nt = datetime.fromisoformat(str(row["last_notified_at"]).replace("Z", "+00:00"))
            except Exception:
                pass
        released_at = None
        if row.get("released_at"):
            try:
                released_at = datetime.fromisoformat(str(row["released_at"]).replace("Z", "+00:00"))
            except Exception:
                pass
        db.add(NotificationSubscription(
            id=row.get("id"),
            user_id=row["user_id"],
            source_id=row["source_id"],
            threshold=int(row.get("threshold", 5)),
            release_threshold=int(row["release_threshold"]) if row.get("release_threshold") is not None else None,
            channel=row.get("channel", "telegram"),
            cooldown_minutes=int(row.get("cooldown_minutes", 30)),
            enabled=row.get("enabled", True),
            last_notified_at=last_nt,
            released_at=released_at,
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row.get("created_at") else datetime.utcnow(),
        ))
    await db.flush()
    # Upsert bot_config
    now = datetime.utcnow()
    for item in bot_config:
        if not isinstance(item, dict) or item.get("key") not in _BOT_KEYS_BACKUP:
            continue
        key, value = item.get("key"), item.get("value", "")
        r = await db.execute(select(BotConfig).where(BotConfig.key == key))
        existing = r.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.updated_at = now
        else:
            db.add(BotConfig(key=key, value=value, updated_at=now))
    await db.flush()
    # History settings
    if isinstance(history_settings, dict):
        rd = history_settings.get("retention_days")
        if rd is not None and int(rd) >= 1:
            r = await db.execute(select(BotConfig).where(BotConfig.key == "history_retention_days"))
            row = r.scalar_one_or_none()
            if row:
                row.value = str(int(rd))
                row.updated_at = now
            else:
                db.add(BotConfig(key="history_retention_days", value=str(int(rd)), updated_at=now))
        di = history_settings.get("default_interval")
        if di in ("minute", "hour", "day", "5min", "10min", "30min"):
            r = await db.execute(select(BotConfig).where(BotConfig.key == "history_default_interval"))
            row = r.scalar_one_or_none()
            if row:
                row.value = di
                row.updated_at = now
            else:
                db.add(BotConfig(key="history_default_interval", value=di, updated_at=now))
        gh = history_settings.get("guest_hours")
        if gh is not None:
            val = max(1, min(8760, int(gh)))
            r = await db.execute(select(BotConfig).where(BotConfig.key == "history_guest_hours"))
            row = r.scalar_one_or_none()
            if row:
                row.value = str(val)
                row.updated_at = now
            else:
                db.add(BotConfig(key="history_guest_hours", value=str(val), updated_at=now))
        else:
            gd = history_settings.get("guest_days")
            if gd is not None:
                val = max(1, min(8760, max(1, min(365, int(gd))) * 24))
                r = await db.execute(select(BotConfig).where(BotConfig.key == "history_guest_hours"))
                row = r.scalar_one_or_none()
                if row:
                    row.value = str(val)
                    row.updated_at = now
                else:
                    db.add(BotConfig(key="history_guest_hours", value=str(val), updated_at=now))
    notify_format = data.get("notify_format")
    if notify_format is not None:
        v = (notify_format if isinstance(notify_format, str) else "").strip()
        r = await db.execute(select(BotConfig).where(BotConfig.key == "notify_format_template"))
        row = r.scalar_one_or_none()
        if row:
            row.value = v
            row.updated_at = now
        else:
            db.add(BotConfig(key="notify_format_template", value=v, updated_at=now))
    vsm = data.get("vision_selected_model")
    if vsm is not None:
        v = (vsm if isinstance(vsm, str) else "").strip()
        if v and not _safe_model_filename(v):
            v = ""
        r = await db.execute(select(BotConfig).where(BotConfig.key == VISION_SELECTED_MODEL_KEY))
        row = r.scalar_one_or_none()
        if row:
            row.value = v
            row.updated_at = now
        else:
            db.add(BotConfig(key=VISION_SELECTED_MODEL_KEY, value=v, updated_at=now))
    vct = data.get("vision_confidence_threshold")
    if vct is not None:
        try:
            v = str(max(0.0, min(1.0, float(vct))))
        except (TypeError, ValueError):
            v = "0.5"
        r = await db.execute(select(BotConfig).where(BotConfig.key == VISION_CONFIDENCE_THRESHOLD_KEY))
        row = r.scalar_one_or_none()
        if row:
            row.value = v
            row.updated_at = now
        else:
            db.add(BotConfig(key=VISION_CONFIDENCE_THRESHOLD_KEY, value=v, updated_at=now))
    # Sync .selected so vision uses this model name after user re-uploads the file
    selected = data.get("vision_selected_model")
    if isinstance(selected, str) and _safe_model_filename(selected.strip()):
        try:
            _models_dir_ensure()
            with open(os.path.join(MODELS_DIR, SELECTED_MODEL_FILE), "w") as fp:
                fp.write(selected.strip())
        except OSError:
            pass
    await db.flush()
    return {"message": "Restored"}
