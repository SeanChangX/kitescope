"""go2rtc: request MJPEG stream and take first frame (go2rtc has no single-JPEG snapshot API)."""
import time
import logging
import httpx
import cv2
import numpy as np
import os
from .base import BaseAdapter, FrameResult, browser_headers_for_url

log = logging.getLogger(__name__)

GO2RTC_BASE = os.getenv("GO2RTC_BASE_URL", "http://localhost:1984")
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
MAX_STREAM_BYTES = 2 * 1024 * 1024
STREAM_TIMEOUT = 15.0


def _extract_first_jpeg(data: bytes) -> bytes | None:
    start = data.find(JPEG_SOI)
    if start == -1:
        return None
    end = data.find(JPEG_EOI, start)
    if end == -1:
        return None
    return data[start : end + 2]


class Go2rtcAdapter(BaseAdapter):
    def _stream_url(self) -> str:
        base = GO2RTC_BASE.rstrip("/")
        if base in self.url or ":1984" in self.url:
            name = self.url.rstrip("/").split("/")[-1].split("?")[0]
            return f"{base}/api/stream?src={name}"
        return f"{base}/api/stream?src={self.url}"

    async def fetch_frame(self) -> FrameResult | None:
        try:
            url = self._stream_url()
            headers = browser_headers_for_url(self.url)
            timeout = httpx.Timeout(STREAM_TIMEOUT)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url, headers=headers) as r:
                    if r.status_code != 200:
                        log.warning("go2rtc non-200 status=%s url=%s", r.status_code, url[:80])
                        return None
                    buffer = b""
                    async for chunk in r.aiter_bytes():
                        buffer += chunk
                        jpeg = _extract_first_jpeg(buffer)
                        if jpeg is not None:
                            break
                        if len(buffer) >= MAX_STREAM_BYTES:
                            log.warning("go2rtc no frame in first %d bytes url=%s", MAX_STREAM_BYTES, url[:80])
                            break
            jpeg = _extract_first_jpeg(buffer)
            if jpeg is None and buffer.lstrip().startswith(JPEG_SOI):
                end = buffer.find(JPEG_EOI)
                if end != -1:
                    jpeg = buffer[: end + 2]
            if jpeg is None:
                return None
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return None
            return FrameResult(frame=frame, source_id=self.source_id, timestamp=time.time())
        except Exception as e:
            log.warning("go2rtc error url=%s error=%s", self.url[:80] if self.url else "", e, exc_info=False)
            return None

    def close(self) -> None:
        pass
