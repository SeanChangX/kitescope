"""Get or create SECRET_KEY and INTERNAL_SECRET; persist in DB or shared file for first-run."""
import os
import secrets
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import BotConfig

SECRET_KEY_BOT_CONFIG_KEY = "secret_key"

# INTERNAL_SECRET: when env not set, read/write shared file (INTERNAL_SECRET_FILE) so vision can share it.
_internal_secret_file_path = os.getenv("INTERNAL_SECRET_FILE", "").strip()


def ensure_internal_secret_file() -> None:
    """If INTERNAL_SECRET not set and INTERNAL_SECRET_FILE set, create file with random secret if missing."""
    if os.getenv("INTERNAL_SECRET", "").strip():
        return
    if not _internal_secret_file_path:
        return
    if os.path.isfile(_internal_secret_file_path):
        return
    try:
        with open(_internal_secret_file_path, "w") as f:
            f.write(secrets.token_hex(32))
    except OSError:
        pass


def get_internal_secret() -> str:
    """Return INTERNAL_SECRET: env, or content of INTERNAL_SECRET_FILE (for backend/vision)."""
    v = os.getenv("INTERNAL_SECRET", "").strip()
    if v:
        return v
    if _internal_secret_file_path and os.path.isfile(_internal_secret_file_path):
        try:
            with open(_internal_secret_file_path) as f:
                return f.read().strip()
        except OSError:
            pass
    return ""


async def get_or_create_secret_key(db: AsyncSession) -> str:
    """Return SECRET_KEY from BotConfig, or generate and store one. Caller should commit."""
    result = await db.execute(select(BotConfig).where(BotConfig.key == SECRET_KEY_BOT_CONFIG_KEY))
    row = result.scalar_one_or_none()
    if row and (row.value or "").strip():
        return row.value.strip()
    key = secrets.token_hex(32)
    db.add(BotConfig(key=SECRET_KEY_BOT_CONFIG_KEY, value=key))
    await db.flush()
    return key
