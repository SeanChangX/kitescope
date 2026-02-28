"""Send messages via LINE Messaging API and Telegram Bot API."""
import httpx

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def format_kite_notification(
    count: int,
    place: str,
    weather: str | None = None,
    view_url: str | None = None,
) -> str:
    """Build a bot-style notification: short lines, no indent."""
    lines = [f"Spotted {int(count)} kites at {place}."]
    if weather:
        lines.append(f"Weather: {weather}.")
    if view_url and view_url.strip():
        lines.append(f"View live: {view_url.strip()}")
    return "\n".join(lines)


TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_URL = "https://api.telegram.org/bot{token}/sendPhoto"


async def send_line_message(channel_access_token: str, user_id: str, text: str) -> bool:
    if not channel_access_token or not user_id or not text.strip():
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                LINE_PUSH_URL,
                headers={"Authorization": f"Bearer {channel_access_token}", "Content-Type": "application/json"},
                json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
            )
            return r.status_code == 200
    except Exception:
        return False


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id or not text.strip():
        return False
    try:
        url = TELEGRAM_SEND_URL.format(token=bot_token)
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text[:4096]})
            return r.status_code == 200
    except Exception:
        return False


async def send_telegram_photo(bot_token: str, chat_id: str, image_bytes: bytes, caption: str | None = None) -> bool:
    if not bot_token or not chat_id or not image_bytes:
        return False
    try:
        url = TELEGRAM_PHOTO_URL.format(token=bot_token)
        async with httpx.AsyncClient(timeout=15.0) as client:
            files = {"photo": ("snapshot.jpg", image_bytes, "image/jpeg")}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption[:1024]
            r = await client.post(url, data=data, files=files)
            return r.status_code == 200
    except Exception:
        return False
