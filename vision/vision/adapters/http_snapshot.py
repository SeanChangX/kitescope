import logging
import time
import httpx
import cv2
import numpy as np
from urllib.parse import urlparse
from .base import BaseAdapter, FrameResult, browser_headers_for_url

log = logging.getLogger(__name__)


def _url_for_log(url: str) -> str:
    """Return a short, safe URL for logging (host + path, no query)."""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path or '/'}"
    except Exception:
        return "(invalid url)"


class HttpSnapshotAdapter(BaseAdapter):
    async def fetch_frame(self) -> FrameResult | None:
        try:
            headers = browser_headers_for_url(self.url)
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(self.url, headers=headers)
                content_type = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                log.debug(
                    "http_snapshot response url=%s status=%s content_type=%s size=%d",
                    _url_for_log(self.url),
                    r.status_code,
                    content_type,
                    len(r.content),
                )
                if r.status_code != 200:
                    preview = (r.text or (r.content.decode("utf-8", errors="replace") if r.content else ""))[:200]
                    log.warning(
                        "http_snapshot non-200 url=%s status=%s content_type=%s body_preview=%s",
                        _url_for_log(self.url), r.status_code, content_type, preview,
                    )
                    return None
                if "image" not in content_type and content_type not in ("", "application/octet-stream"):
                    log.warning(
                        "http_snapshot not image url=%s content_type=%s body_start=%s",
                        _url_for_log(self.url),
                        content_type,
                        (r.content[:80].decode("utf-8", errors="replace") if r.content else "").replace("\n", " "),
                    )
                arr = np.frombuffer(r.content, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    log.warning("http_snapshot decode failed url=%s content_type=%s size=%d", _url_for_log(self.url), content_type, len(r.content))
                    return None
                return FrameResult(frame=frame, source_id=self.source_id, timestamp=time.time())
        except Exception as e:
            log.warning("http_snapshot error url=%s error=%s", _url_for_log(self.url), e, exc_info=False)
            return None

    def close(self) -> None:
        pass
