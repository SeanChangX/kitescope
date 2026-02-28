import os
import bcrypt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from fastapi import Request
from database import get_db
from models import AdminUser, User
from user_activity import update_user_activity

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-dev")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

security = HTTPBearer(auto_error=False)


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
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_user_access_token(user_id: int, channel: str = "telegram") -> str:
    """Create JWT for end-user. channel is the login method: 'line' or 'telegram', used for notification subscription."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "user", "channel": channel}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_notification_channel(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str | None:
    """Return notification channel from user JWT ('line' or 'telegram'); None if no/invalid token."""
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
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
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not credentials or credentials.credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
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
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Return User if valid user JWT present; else None. Updates last_seen/last_ip when user present."""
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
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
