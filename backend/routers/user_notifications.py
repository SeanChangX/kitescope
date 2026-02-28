"""User-facing API: list/create/update/delete notification subscriptions (requires user JWT)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db
from models import NotificationSubscription, User, Source
from auth_admin import get_current_user, get_notification_channel_required

router = APIRouter()


@router.get("/notifications/subscriptions")
async def list_my_subscriptions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List current user's notification subscriptions with source info."""
    result = await db.execute(
        select(NotificationSubscription, Source)
        .join(Source, NotificationSubscription.source_id == Source.id)
        .where(NotificationSubscription.user_id == user.id)
        .order_by(NotificationSubscription.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": sub.id,
            "source_id": sub.source_id,
            "source_name": src.name or src.location or f"Source {src.id}",
            "threshold": sub.threshold,
            "release_threshold": sub.release_threshold,
            "channel": sub.channel,
            "cooldown_minutes": sub.cooldown_minutes,
            "enabled": sub.enabled,
            "last_notified_at": sub.last_notified_at.isoformat() if sub.last_notified_at else None,
        }
        for sub, src in rows
    ]


class CreateSubscriptionBody(BaseModel):
    source_id: int
    threshold: int = 5
    release_threshold: int | None = None
    cooldown_minutes: int = 30


@router.post("/notifications/subscriptions")
async def create_subscription(
    body: CreateSubscriptionBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    channel: str = Depends(get_notification_channel_required),
):
    """Create a notification subscription for a source. Channel is determined by login method (LINE or Telegram)."""
    result = await db.execute(select(Source).where(Source.id == body.source_id, Source.enabled == True))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    existing = await db.execute(
        select(NotificationSubscription).where(
            NotificationSubscription.user_id == user.id,
            NotificationSubscription.source_id == body.source_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Already subscribed to this source")
    sub = NotificationSubscription(
        user_id=user.id,
        source_id=body.source_id,
        threshold=max(1, min(100, body.threshold)),
        release_threshold=body.release_threshold if body.release_threshold is not None else max(0, body.threshold - 2),
        channel=channel,
        cooldown_minutes=max(1, min(1440, body.cooldown_minutes)),
        enabled=True,
    )
    db.add(sub)
    await db.flush()
    await db.refresh(sub)
    return {"id": sub.id, "message": "Subscribed"}


class UpdateSubscriptionBody(BaseModel):
    threshold: int | None = None
    release_threshold: int | None = None
    channel: str | None = None
    cooldown_minutes: int | None = None
    enabled: bool | None = None


@router.patch("/notifications/subscriptions/{sub_id}")
async def update_subscription(
    sub_id: int,
    body: UpdateSubscriptionBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a subscription (only own)."""
    result = await db.execute(
        select(NotificationSubscription).where(
            NotificationSubscription.id == sub_id,
            NotificationSubscription.user_id == user.id,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if body.threshold is not None:
        sub.threshold = max(1, min(100, body.threshold))
    if body.release_threshold is not None:
        sub.release_threshold = max(0, body.release_threshold) if body.release_threshold >= 0 else None
    if body.channel is not None:
        sub.channel = body.channel if body.channel.lower() in ("line", "telegram") else sub.channel
    if body.cooldown_minutes is not None:
        sub.cooldown_minutes = max(1, min(1440, body.cooldown_minutes))
    if body.enabled is not None:
        sub.enabled = body.enabled
    db.add(sub)
    await db.flush()
    return {"message": "Updated"}


@router.delete("/notifications/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a subscription (only own)."""
    from sqlalchemy import delete
    result = await db.execute(
        delete(NotificationSubscription).where(
            NotificationSubscription.id == sub_id,
            NotificationSubscription.user_id == user.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await db.flush()
    return {"message": "Deleted"}
