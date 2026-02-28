"""Background worker: evaluate notification subscriptions and send LINE/Telegram when threshold + cooldown met."""
import asyncio
import os
from datetime import datetime, timedelta
from sqlalchemy import select
import httpx

from database import AsyncSessionLocal
from models import CountHistory, NotificationSubscription, User, BotConfig, Source
from notify import format_kite_notification, send_line_message, send_telegram_message, send_telegram_photo
from weather import get_weather_for_location

VISION_URL = os.getenv("VISION_URL", "http://vision:9000")

CHECK_INTERVAL_SEC = int(os.getenv("NOTIFICATION_CHECK_INTERVAL_SEC", "60"))


async def _run_once() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CountHistory.source_id, CountHistory.count)
            .order_by(CountHistory.recorded_at.desc())
        )
        rows = result.all()
        latest_by_source: dict[int, float] = {}
        for r in rows:
            if r.source_id not in latest_by_source:
                latest_by_source[r.source_id] = r.count

        subs_result = await db.execute(
            select(NotificationSubscription, User, Source)
            .join(User, NotificationSubscription.user_id == User.id)
            .join(Source, NotificationSubscription.source_id == Source.id)
            .where(NotificationSubscription.enabled == True)
            .where(User.banned == False)
        )
        subs_rows = subs_result.all()

        bot_result = await db.execute(select(BotConfig))
        bot_rows = bot_result.scalars().all()
        by_key = {r.key: r.value for r in bot_rows}
        line_token = (by_key.get("line_channel_access_token") or "").strip()
        telegram_token = (by_key.get("telegram_bot_token") or "").strip()

        now = datetime.utcnow()
        for sub, user, source in subs_rows:
            count = latest_by_source.get(sub.source_id)
            release = sub.release_threshold if sub.release_threshold is not None else max(0, sub.threshold - 2)
            if count is not None and count < release:
                sub.released_at = now
                db.add(sub)
                continue
            if count is None or count < sub.threshold:
                continue
            last = sub.last_notified_at
            if last is not None:
                if now - last < timedelta(minutes=sub.cooldown_minutes):
                    continue
                if sub.released_at is None or sub.released_at <= last:
                    continue
            place = source.name or source.location or "stream"
            weather_str = await get_weather_for_location(source.location or "")
            view_url = (by_key.get("public_app_url") or os.getenv("PUBLIC_APP_URL") or "").strip().rstrip("/") or None
            msg = format_kite_notification(int(count), place, weather_str or None, view_url)
            channel = (sub.channel or "telegram").lower()
            sent = False
            if channel == "line" and user.line_id and line_token:
                sent = await send_line_message(line_token, user.line_id, msg)
            elif (channel == "telegram" or not sent) and user.telegram_id and telegram_token:
                snapshot_bytes = None
                try:
                    async with httpx.AsyncClient(timeout=12.0) as client:
                        r = await client.get(f"{VISION_URL}/snapshot", params={"url": source.url})
                        if r.status_code == 200 and r.content:
                            snapshot_bytes = r.content
                except Exception:
                    pass
                if snapshot_bytes:
                    sent = await send_telegram_photo(telegram_token, user.telegram_id, snapshot_bytes, caption=msg)
                if not sent:
                    sent = await send_telegram_message(telegram_token, user.telegram_id, msg)
            if sent:
                sub.last_notified_at = now
                db.add(sub)
        await db.commit()


async def run_loop() -> None:
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SEC)
        try:
            await _run_once()
        except Exception:
            pass


def start_worker() -> asyncio.Task | None:
    try:
        return asyncio.create_task(run_loop())
    except Exception:
        return None