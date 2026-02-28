import hashlib
import hmac
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import httpx

from database import get_db
from models import AdminUser, User, BotConfig
from auth_admin import (
    hash_password,
    verify_password,
    create_access_token,
    create_user_access_token,
    require_first_run_setup,
    get_current_admin,
    get_current_user_optional,
    get_notification_channel,
)

router = APIRouter()

LINE_AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_PROFILE_URL = "https://api.line.me/v2/profile"


def _line_login_credentials(by_key: dict) -> tuple[str, str]:
    """Return (channel_id, channel_secret) for LINE Login. Prefer line_login_* when set (separate LINE Login channel)."""
    login_id = (by_key.get("line_login_channel_id") or "").strip()
    login_secret = (by_key.get("line_login_channel_secret") or "").strip()
    if login_id and login_secret:
        return login_id, login_secret
    return (by_key.get("line_channel_id") or "").strip(), (by_key.get("line_channel_secret") or "").strip()


@router.get("/line/login-url")
async def line_login_url(
    redirect_uri: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Return LINE authorization URL. redirect_uri must be the frontend callback (e.g. /auth/callback)."""
    result = await db.execute(select(BotConfig).where(BotConfig.key.in_([
        "line_channel_id", "line_channel_secret", "line_login_channel_id", "line_login_channel_secret",
    ])))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    channel_id, _ = _line_login_credentials(by_key)
    if not channel_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="LINE not configured or redirect_uri required")
    import urllib.parse
    params = {
        "response_type": "code",
        "client_id": channel_id,
        "redirect_uri": redirect_uri,
        "state": state or "line",
        "scope": "profile openid email",
    }
    url = LINE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return {"url": url}


class LineCallbackBody(BaseModel):
    code: str
    redirect_uri: str


@router.post("/line/callback")
async def line_callback(
    body: LineCallbackBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange code for token, get profile, create/update User, return user JWT."""
    result = await db.execute(select(BotConfig).where(BotConfig.key.in_([
        "line_channel_id", "line_channel_secret", "line_login_channel_id", "line_login_channel_secret",
    ])))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    channel_id, channel_secret = _line_login_credentials(by_key)
    if not channel_id or not channel_secret or not body.code or not body.redirect_uri:
        raise HTTPException(status_code=400, detail="Invalid request or LINE not configured")
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_r = await client.post(
            LINE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": body.code,
                "redirect_uri": body.redirect_uri,
                "client_id": channel_id,
                "client_secret": channel_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_r.status_code != 200:
            raise HTTPException(status_code=400, detail="LINE token exchange failed")
        token_data = token_r.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access token")
        profile_r = await client.get(LINE_PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"})
        if profile_r.status_code != 200:
            raise HTTPException(status_code=400, detail="LINE profile failed")
        profile = profile_r.json()
    line_id = profile.get("userId") or profile.get("sub")
    display_name = (profile.get("displayName") or "").strip() or None
    picture_url = (profile.get("pictureUrl") or "").strip() or None
    email = (profile.get("email") or "").strip() or None
    if not line_id:
        raise HTTPException(status_code=400, detail="No LINE user ID")
    result = await db.execute(select(User).where(User.line_id == line_id))
    user = result.scalar_one_or_none()
    if user:
        if display_name:
            user.display_name = display_name
        if picture_url:
            user.avatar = picture_url
        if email is not None:
            user.email = email or ""
        db.add(user)
    else:
        user = User(line_id=line_id, display_name=display_name or "", avatar=picture_url or "", email=email or "")
        db.add(user)
    await db.flush()
    await db.refresh(user)
    if user.banned:
        raise HTTPException(status_code=403, detail="Account is banned")
    token = create_user_access_token(user.id, "line")
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@router.get("/telegram/bot-username")
async def telegram_bot_username(db: AsyncSession = Depends(get_db)):
    """Return Telegram bot username for Login Widget (e.g. MyKiteScopeBot)."""
    result = await db.execute(select(BotConfig).where(BotConfig.key == "telegram_bot_token"))
    row = result.scalar_one_or_none()
    if not row or not row.value:
        return {"bot_username": ""}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"https://api.telegram.org/bot{row.value.strip()}/getMe")
            if r.status_code != 200:
                return {"bot_username": ""}
            data = r.json()
            return {"bot_username": (data.get("result") or {}).get("username") or ""}
    except Exception:
        return {"bot_username": ""}


class TelegramAuthBody(BaseModel):
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    photo_url: str = ""
    auth_date: int = 0
    hash: str = ""


@router.post("/telegram/verify")
async def telegram_verify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Verify Telegram Login Widget data and create/update User, return user JWT."""
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body required")
    hash_val = body.pop("hash", None)
    if not hash_val:
        raise HTTPException(status_code=400, detail="hash missing")
    result = await db.execute(select(BotConfig).where(BotConfig.key == "telegram_bot_token"))
    row = result.scalar_one_or_none()
    if not row or not row.value:
        raise HTTPException(status_code=400, detail="Telegram not configured")
    bot_token = row.value.strip()
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(body.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, hash_val):
        raise HTTPException(status_code=400, detail="Invalid Telegram data")
    user_id_raw = body.get("id")
    if user_id_raw is None:
        raise HTTPException(status_code=400, detail="id missing")
    try:
        telegram_id = str(int(user_id_raw))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid id")
    first_name = str(body.get("first_name") or "")
    last_name = str(body.get("last_name") or "")
    username = str(body.get("username") or "")
    photo_url = str(body.get("photo_url") or "")
    display_name = f"{first_name} {last_name}".strip() or username or "User"
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.display_name = display_name
        if photo_url:
            user.avatar = photo_url
        db.add(user)
    else:
        user = User(telegram_id=telegram_id, display_name=display_name, avatar=photo_url)
        db.add(user)
    await db.flush()
    await db.refresh(user)
    if user.banned:
        raise HTTPException(status_code=403, detail="Account is banned")
    token = create_user_access_token(user.id, "telegram")
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@router.get("/me")
async def auth_me(
    user: User | None = Depends(get_current_user_optional),
    channel: str | None = Depends(get_notification_channel),
):
    """Return current user info if logged in with user token; else 401."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    notification_channel = channel
    if not notification_channel:
        if user.line_id and not user.telegram_id:
            notification_channel = "line"
        elif user.telegram_id:
            notification_channel = "telegram"
    return {
        "user_id": user.id,
        "display_name": user.display_name or "",
        "avatar": user.avatar or "",
        "line_id": user.line_id is not None,
        "telegram_id": user.telegram_id is not None,
        "notification_channel": notification_channel,
    }


@router.get("/admin/setup-status")
async def admin_setup_status(db: AsyncSession = Depends(get_db)):
    """Call before login: if setup_required, show setup form instead of login."""
    setup_required = await require_first_run_setup(db)
    return {"setup_required": setup_required}


class AdminSetupBody(BaseModel):
    username: str
    password: str


@router.post("/admin/setup")
async def admin_setup(body: AdminSetupBody, db: AsyncSession = Depends(get_db)):
    """First-run only: create the first admin account."""
    if not await require_first_run_setup(db):
        raise HTTPException(status_code=400, detail="Admin already exists")
    if not body.username or len(body.username) < 2:
        raise HTTPException(status_code=400, detail="Username too short")
    if not body.password or len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    admin = AdminUser(
        username=body.username.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(admin)
    await db.flush()
    token = create_access_token(admin.username)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/admin/login")
async def admin_login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    if await require_first_run_setup(db):
        raise HTTPException(status_code=400, detail="Setup required first. Call GET /api/auth/admin/setup-status")
    result = await db.execute(select(AdminUser).where(AdminUser.username == form.username))
    admin = result.scalar_one_or_none()
    if not admin or not verify_password(form.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(admin.username)
    return {"access_token": token, "token_type": "bearer"}


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/admin/change-password")
async def admin_change_password(
    body: ChangePasswordBody,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    if not verify_password(body.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    admin.password_hash = hash_password(body.new_password)
    db.add(admin)
    await db.flush()
    return {"message": "Password updated"}
