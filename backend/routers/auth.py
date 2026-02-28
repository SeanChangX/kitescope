import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlparse
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
from rate_limit import rate_limit_admin_auth

router = APIRouter()

LINE_AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_PROFILE_URL = "https://api.line.me/v2/profile"

# LINE OAuth state: store generated state with timestamp; verify in callback to prevent CSRF/session mix-up
_LINE_STATE_TTL_SEC = 600
_line_states: dict[str, float] = {}


def _line_state_cleanup() -> None:
    now = time.monotonic()
    expired = [k for k, t in _line_states.items() if now - t > _LINE_STATE_TTL_SEC]
    for k in expired:
        del _line_states[k]


def _origin_from_url(url: str) -> str | None:
    """Return origin (scheme + lowercase host) from a URL, or None."""
    try:
        p = urlparse(url.strip())
        if not p.scheme or not p.netloc:
            return None
        host = p.netloc.split(":")[0].lower()
        return f"{p.scheme.lower()}://{host}"
    except Exception:
        return None


def _redirect_uri_origin(redirect_uri: str) -> str | None:
    """Return origin (scheme + lowercase host) of redirect_uri, or None if invalid."""
    return _origin_from_url(redirect_uri)


def _allowed_line_redirect_origins(by_key: dict) -> set[str]:
    """Set of allowed origins for LINE redirect_uri: env + DB public_app_url."""
    raw = (os.getenv("LINE_REDIRECT_ALLOW_ORIGINS") or os.getenv("PUBLIC_APP_URL") or "").strip()
    allowed = set()
    for s in raw.split(","):
        s = s.strip().rstrip("/")
        if s:
            o = _origin_from_url(s)
            if o:
                allowed.add(o)
    app_url = (by_key.get("public_app_url") or "").strip().rstrip("/")
    if app_url:
        o = _origin_from_url(app_url)
        if o:
            allowed.add(o)
    return allowed


def _validate_line_redirect_uri(redirect_uri: str, by_key: dict) -> None:
    """Raise HTTP 400 if redirect_uri origin is not in allowlist."""
    allowed = _allowed_line_redirect_origins(by_key)
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail="LINE redirect_uri allowlist not configured. Set PUBLIC_APP_URL or LINE_REDIRECT_ALLOW_ORIGINS.",
        )
    origin = _redirect_uri_origin(redirect_uri)
    if not origin or origin not in allowed:
        raise HTTPException(status_code=400, detail="redirect_uri origin not allowed")


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
    db: AsyncSession = Depends(get_db),
):
    """Return LINE authorization URL. redirect_uri must be the frontend callback (e.g. /auth/callback)."""
    result = await db.execute(select(BotConfig).where(BotConfig.key.in_([
        "line_channel_id", "line_channel_secret", "line_login_channel_id", "line_login_channel_secret",
        "public_app_url",
    ])))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    channel_id, _ = _line_login_credentials(by_key)
    if not channel_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="LINE not configured or redirect_uri required")
    _validate_line_redirect_uri(redirect_uri, by_key)
    _line_state_cleanup()
    state = secrets.token_urlsafe(16)
    _line_states[state] = time.monotonic()
    import urllib.parse
    params = {
        "response_type": "code",
        "client_id": channel_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "profile openid email",
    }
    url = LINE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return {"url": url, "state": state}


class LineCallbackBody(BaseModel):
    code: str
    redirect_uri: str
    state: str = ""


@router.post("/line/callback")
async def line_callback(
    body: LineCallbackBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange code for token, get profile, create/update User, return user JWT."""
    result = await db.execute(select(BotConfig).where(BotConfig.key.in_([
        "line_channel_id", "line_channel_secret", "line_login_channel_id", "line_login_channel_secret",
        "public_app_url",
    ])))
    rows = result.scalars().all()
    by_key = {r.key: r.value for r in rows}
    channel_id, channel_secret = _line_login_credentials(by_key)
    if not channel_id or not channel_secret or not body.code or not body.redirect_uri:
        raise HTTPException(status_code=400, detail="Invalid request or LINE not configured")
    _validate_line_redirect_uri(body.redirect_uri, by_key)
    _line_state_cleanup()
    if not body.state or body.state not in _line_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state, try logging in again")
    del _line_states[body.state]
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
        id_token = token_data.get("id_token")
        email_from_id_token = None
        if id_token:
            try:
                payload_b64 = id_token.split(".")[1]
                payload_b64 += "==" * (4 - len(payload_b64) % 4)
                payload_json = base64.urlsafe_b64decode(payload_b64)
                id_claims = json.loads(payload_json)
                email_from_id_token = (id_claims.get("email") or "").strip() or None
            except (IndexError, ValueError, KeyError):
                pass
    line_id = profile.get("userId") or profile.get("sub")
    display_name = (profile.get("displayName") or "").strip() or None
    picture_url = (profile.get("pictureUrl") or "").strip() or None
    email = email_from_id_token or (profile.get("email") or "").strip() or None
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
    # data-check-string: alphabetical order, values as string (match Telegram redirect)
    data_pairs = sorted((k, str(v)) for k, v in body.items())
    data_check = "\n".join(f"{k}={v}" for k, v in data_pairs)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    hash_hex = str(hash_val).strip().lower()
    if not hmac.compare_digest(expected, hash_hex):
        raise HTTPException(status_code=400, detail="Invalid Telegram data")
    # Reject old auth data (replay). Telegram: auth_date not older than 24 hours.
    auth_date = body.get("auth_date")
    if auth_date is None:
        raise HTTPException(status_code=400, detail="auth_date missing")
    try:
        auth_ts = int(auth_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid auth_date")
    now_ts = int(time.time())
    if auth_ts > now_ts + 60 or now_ts - auth_ts > 86400:
        raise HTTPException(status_code=400, detail="Telegram login expired, try again")
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
    """Return current user info if logged in; 200 with user=null when not (avoids 401 in console)."""
    if user is None:
        return {"user_id": None, "display_name": "", "avatar": "", "line_id": False, "telegram_id": False, "notification_channel": None}
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
async def admin_setup(
    body: AdminSetupBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_admin_auth),
):
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
async def admin_login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_admin_auth),
):
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
