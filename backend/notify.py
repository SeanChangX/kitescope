"""Send messages via LINE Messaging API and Telegram Bot API."""
import httpx

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

WELCOME_MESSAGE = (
    "Welcome to KiteScope.\n"
    "Subscribe to streams to get notified when the kite count reaches your threshold. "
    "Use the Notifications page to add subscriptions.\n"
    "GitHub: https://github.com/SeanChangX/KiteScope"
)

DEFAULT_NOTIFY_FORMAT = (
    "[ Spotted {count} kites ] [ {place} ]\n"
    "Weather: {weather}\n"
    "{view_url}"
)


def format_kite_notification(
    count: int,
    place: str,
    weather: str | None = None,
    view_url: str | None = None,
    template: str | None = None,
) -> str:
    """Build a bot-style notification from template. Placeholders: {count}, {place}, {weather}, {view_url}."""
    tpl = (template or "").strip() or DEFAULT_NOTIFY_FORMAT
    weather_s = (weather or "").strip()
    view_s = (view_url or "").strip()
    text = tpl.format(
        count=int(count),
        place=(place or "").strip() or "stream",
        weather=weather_s,
        view_url=view_s,
    )
    lines = []
    for line in text.splitlines():
        s = line.rstrip()
        if s == "Weather: " or s == "Weather:":
            continue
        lines.append(s)
    return "\n".join(lines).strip()


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
