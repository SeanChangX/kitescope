from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np

# Headers that mimic a browser so servers (e.g. NVR/camera pages) accept the request.
# No "br" in Accept-Encoding to avoid Brotli issues with some NVRs.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-origin",
}


def browser_headers_for_url(url: str) -> dict:
    """Return browser-like headers. No Referer to mimic opening URL in new tab (many NVRs accept this)."""
    return dict(BROWSER_HEADERS)


@dataclass
class FrameResult:
    frame: np.ndarray
    source_id: str
    timestamp: float


class BaseAdapter(ABC):
    def __init__(self, url: str, source_id: str, interval_sec: int = 5, seek_offset_sec: float = 0):
        self.url = url
        self.source_id = source_id
        self.interval_sec = interval_sec
        self.seek_offset_sec = seek_offset_sec

    @abstractmethod
    async def fetch_frame(self) -> Optional[FrameResult]:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
