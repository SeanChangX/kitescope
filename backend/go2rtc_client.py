"""Register or ensure a stream in local go2rtc. Used to proxy non-YouTube/non-MJPEG URLs."""
import logging
import os
from urllib.parse import quote
import httpx

log = logging.getLogger(__name__)

GO2RTC_BASE = (os.getenv("GO2RTC_BASE_URL") or "http://localhost:1984").rstrip("/")


def _stream_name_from_source_id(source_id: int) -> str:
    return f"kitescope_{source_id}"


def go2rtc_stream_url(stream_name: str) -> str:
    return f"{GO2RTC_BASE}/{stream_name}"


async def register_go2rtc_stream(origin_url: str, source_id: int) -> str | None:
    """
    Register origin_url in go2rtc with name kitescope_{source_id}.
    Returns go2rtc stream URL on success, None on failure.
    """
    name = _stream_name_from_source_id(source_id)
    return await register_go2rtc_stream_by_name(origin_url, name)


async def register_go2rtc_stream_by_name(origin_url: str, stream_name: str) -> str | None:
    """
    Register origin_url in go2rtc with a custom stream name (e.g. kitescope_pending_{id}).
    Returns go2rtc stream URL on success, None on failure.
    """
    url = f"{GO2RTC_BASE}/api/streams?src={quote(origin_url, safe='')}&name={quote(stream_name, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url)
            if r.status_code in (200, 201, 204):
                log.info("go2rtc registered stream name=%s", stream_name)
                return go2rtc_stream_url(stream_name)
            log.warning("go2rtc register failed name=%s status=%s body=%s", stream_name, r.status_code, (r.text or "")[:200])
            return None
    except Exception as e:
        log.warning("go2rtc register error name=%s error=%s", stream_name, e)
        return None


async def ensure_go2rtc_stream(origin_url: str, source_id: int) -> bool:
    """
    Idempotent: ensure the stream exists in go2rtc (e.g. after go2rtc restart).
    Returns True if stream is available.
    """
    name = _stream_name_from_source_id(source_id)
    url = f"{GO2RTC_BASE}/api/streams?src={quote(origin_url, safe='')}&name={quote(name, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url)
            return r.status_code in (200, 201, 204)
    except Exception as e:
        log.warning("go2rtc ensure error name=%s error=%s", name, e)
        return False


async def delete_go2rtc_stream(stream_name: str) -> bool:
    """
    Remove a stream from go2rtc (e.g. when a pending source or approved source is deleted).
    API: DELETE /api/streams?src={stream_name}
    Returns True if delete succeeded or stream was already gone.
    """
    url = f"{GO2RTC_BASE}/api/streams?src={quote(stream_name, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(url)
            if r.status_code in (200, 204):
                log.info("go2rtc deleted stream name=%s", stream_name)
                return True
            log.warning("go2rtc delete stream name=%s status=%s", stream_name, r.status_code)
            return False
    except Exception as e:
        log.warning("go2rtc delete error name=%s error=%s", stream_name, e)
        return False
