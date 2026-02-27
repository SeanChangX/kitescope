"""MJPEG stream: HTTP GET returns multipart/x-mixed-replace (infinite) or single JPEG; extract one frame."""
import logging
import time
import httpx
import cv2
import numpy as np
from .base import BaseAdapter, FrameResult, browser_headers_for_url

log = logging.getLogger(__name__)

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
MAX_STREAM_BYTES = 2 * 1024 * 1024  # stop after 2MB if no frame found
STREAM_TIMEOUT = 15.0


def _extract_first_jpeg(data: bytes) -> bytes | None:
    start = data.find(JPEG_SOI)
    if start == -1:
        return None
    end = data.find(JPEG_EOI, start)
    if end == -1:
        return None
    return data[start : end + 2]


class MjpegAdapter(BaseAdapter):
    """Stream response and read only until the first complete JPEG so we don't wait for an infinite MJPEG stream."""

    async def fetch_frame(self) -> FrameResult | None:
        try:
            headers = browser_headers_for_url(self.url)
            timeout = httpx.Timeout(STREAM_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", self.url, headers=headers) as r:
                    if r.status_code != 200:
                        log.warning("mjpeg non-200 status=%s url=%s", r.status_code, self.url[:80])
                        return None
                    buffer = b""
                    async for chunk in r.aiter_bytes():
                        buffer += chunk
                        jpeg = _extract_first_jpeg(buffer)
                        if jpeg is not None:
                            break
                        if len(buffer) >= MAX_STREAM_BYTES:
                            log.warning("mjpeg no complete frame in first %d bytes url=%s", MAX_STREAM_BYTES, self.url[:80])
                            break
                    # exit stream context so connection closes; we only wanted one frame
            jpeg = _extract_first_jpeg(buffer)
            if jpeg is None:
                # might be a single JPEG response (no multipart)
                if buffer.lstrip().startswith(JPEG_SOI):
                    end = buffer.find(JPEG_EOI)
                    if end != -1:
                        jpeg = buffer[: end + 2]
                if jpeg is None:
                    log.warning("mjpeg no jpeg in response len=%d url=%s", len(buffer), self.url[:80])
                    return None
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                log.warning("mjpeg decode failed url=%s", self.url[:80])
                return None
            return FrameResult(frame=frame, source_id=self.source_id, timestamp=time.time())
        except Exception as e:
            log.warning("mjpeg error url=%s error=%s", self.url[:80] if self.url else "", e, exc_info=False)
            return None

    def close(self) -> None:
        pass
