"""
LINE Messaging API webhook: receive follow/message events.
When a user adds the bot (follow), send welcome message if they already have an account (LINE Login) but had not added the bot before.
"""
import base64
import hmac
import hashlib
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, BotConfig
from notify import send_line_message, WELCOME_MESSAGE_TEMPLATE

log = logging.getLogger(__name__)

router = APIRouter()


def _verify_line_signature(body: bytes, channel_secret: str, signature_header: str | None) -> bool:
    if not channel_secret or not signature_header:
        return False
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature_header)


@router.post("/line")
async def line_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    LINE Messaging API webhook. Configure this URL in LINE Developers Console (Messaging API tab).
    On 'follow' event: if we have a user with this line_id and welcome_sent_at is null, send welcome and set it.
    """
    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    result = await db.execute(
        select(BotConfig).where(
            BotConfig.key.in_(["line_channel_secret", "line_channel_access_token", "public_app_url"])
        )
    )
    by_key = {r.key: r.value for r in result.scalars().all()}
    channel_secret = (by_key.get("line_channel_secret") or "").strip()
    if not _verify_line_signature(body, channel_secret, signature):
        log.warning("LINE webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    import json
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = payload.get("events") or []
    token = (by_key.get("line_channel_access_token") or "").strip()
    view_url = (by_key.get("public_app_url") or "").strip().rstrip("/") or "https://kitescope.example.com"
    welcome_text = WELCOME_MESSAGE_TEMPLATE.format(view_url=view_url)

    for event in events:
        if event.get("type") != "follow":
            continue
        source = event.get("source") or {}
        user_id = source.get("userId")
        if not user_id:
            continue
        result = await db.execute(select(User).where(User.line_id == user_id))
        user = result.scalar_one_or_none()
        if not user or user.welcome_sent_at is not None:
            continue
        if token:
            sent = await send_line_message(token, user_id, welcome_text)
            if sent:
                from datetime import datetime
                user.welcome_sent_at = datetime.utcnow()
                db.add(user)
                log.info("LINE welcome sent on follow for user_id=%s", user.id)

    await db.commit()
    return {}
