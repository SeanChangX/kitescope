import os
import bcrypt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import AdminUser, User
from user_activity import update_user_activity

# Set at startup from env or auto-generated (persisted in DB). No predictable default.
_runtime_secret_key: str = ""

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

# HttpOnly cookie names (XSS cannot read these)
ADMIN_COOKIE = "kitescope_admin_token"
USER_COOKIE = "kitescope_user_token"

COOKIE_MAX_AGE = 60 * 24 * 60  # 24 hours in seconds
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1").strip().lower() in ("1", "true", "yes")


def cookie_params() -> dict:
    """Common kwargs for set_cookie (HttpOnly, SameSite=Lax)."""
    return {
        "httponly": True,
        "max_age": COOKIE_MAX_AGE,
        "samesite": "lax",
        "secure": COOKIE_SECURE,
    "path": "/",
}


def _bearer_from_request(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    return auth[7:].strip()


def get_admin_token(request: Request) -> str | None:
    """Token from HttpOnly cookie or Authorization header (cookie preferred for XSS safety)."""
    return request.cookies.get(ADMIN_COOKIE) or _bearer_from_request(request)


def get_user_token(request: Request) -> str | None:
    """Token from HttpOnly cookie or Authorization header."""
    return request.cookies.get(USER_COOKIE) or _bearer_from_request(request)


def set_secret_key(key: str) -> None:
    global _runtime_secret_key
    _runtime_secret_key = key or ""


def get_secret_key() -> str:
    """JWT signing key: env SECRET_KEY, or value set at startup (from DB / auto-generated). No weak fallback."""
    key = os.getenv("SECRET_KEY") or _runtime_secret_key
    if not (key and key.strip()):
        raise RuntimeError("SECRET_KEY not set; ensure backend started after init_db and secret was set")
    return key.strip()


def hash_password(password: str) -> str:
    # bcrypt truncates at 72 bytes; pass only first 72 bytes to avoid encoding issues
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8")[:72],
            hashed.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "exp": expire, "type": "admin"}
    return jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)


def create_user_access_token(user_id: int, channel: str = "telegram") -> str:
    """Create JWT for end-user. channel is the login method: 'line' or 'telegram', used for notification subscription."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "user", "channel": channel}
    return jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)


def get_notification_channel(
    request: Request,
) -> str | None:
    """Return notification channel from user JWT ('line' or 'telegram'); None if no/invalid token."""
    token = get_user_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "user":
            return None
        ch = (payload.get("channel") or "").lower()
        return ch if ch in ("line", "telegram") else None
    except (JWTError, ValueError):
        return None


def get_notification_channel_required(
    channel: str | None = Depends(get_notification_channel),
) -> str:
    """Return notification channel from JWT; 401 if missing (e.g. old token without channel)."""
    if channel:
        return channel
    raise HTTPException(status_code=401, detail="Re-login required to set notification channel")


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    token = get_admin_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username or payload.get("type") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin


async def require_first_run_setup(db: AsyncSession) -> bool:
    result = await db.execute(select(AdminUser).limit(1))
    return result.scalar_one_or_none() is None


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Return User if valid user JWT present; else None. Updates last_seen/last_ip when user present."""
    token = get_user_token(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "user":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        user_id = int(user_id)
    except (JWTError, ValueError):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.banned:
        return None
    client_ip = request.client.host if request.client else None
    await update_user_activity(db, user.id, client_ip)
    return user


async def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user
