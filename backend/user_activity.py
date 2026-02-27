"""Update user last_seen and last_ip when they hit APIs. Call from auth dependency when user is present."""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import User


async def update_user_activity(db: AsyncSession, user_id: int, client_ip: str | None) -> None:
    if not user_id or not client_ip:
        return
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return
    user.last_seen = datetime.utcnow()
    user.last_ip = (client_ip or "")[:64]
    db.add(user)
    await db.flush()
