# YouTube Live: yt-dlp to get stream URL, FFmpeg to read one frame
import asyncio
import subprocess
import time
import cv2
import numpy as np
from .base import BaseAdapter, FrameResult

# Total timeout for one frame (yt-dlp + ffmpeg). Prevents one bad URL from holding snapshot semaphore forever.
YT_FETCH_TIMEOUT_SEC = 35


class _YtdlpSilentLogger:
    """Suppress yt-dlp stderr/log (e.g. 'Sign in to confirm you're not a bot') when server has no cookies."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def _get_stream_url(url: str) -> str | None:
    try:
        import yt_dlp
        # Prefer 1080p or lower to reduce decode CPU vs 4K (detection resizes to 640 anyway).
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "logger": _YtdlpSilentLogger(),
            "format": "bestvideo[height<=1080][vcodec!=none]/best[height<=1080]/best",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            live_url = info.get("url")
            if live_url:
                return live_url
            formats = info.get("formats") or []
            for f in reversed(formats):
                if f.get("vcodec") != "none" and f.get("url"):
                    return f["url"]
            return None
    except Exception:
        return None


def _ffmpeg_one_frame(stream_url: str, seek_sec: float = 0) -> np.ndarray | None:
    try:
        args = ["ffmpeg", "-y", "-loglevel", "error"]
        if seek_sec > 0:
            args.extend(["-ss", str(seek_sec)])
        args.extend(["-i", stream_url, "-vframes", "1", "-f", "mjpeg", "pipe:1"])
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=20,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        arr = np.frombuffer(proc.stdout, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


async def fetch_frame_async(url: str, seek_sec: float = 0) -> np.ndarray | None:
    async def _run() -> np.ndarray | None:
        stream_url = await asyncio.to_thread(_get_stream_url, url)
        if not stream_url:
            return None
        return await asyncio.to_thread(_ffmpeg_one_frame, stream_url, seek_sec)

    try:
        return await asyncio.wait_for(_run(), timeout=YT_FETCH_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        return None


class YoutubeLiveAdapter(BaseAdapter):
    async def fetch_frame(self) -> FrameResult | None:
        try:
            frame = await fetch_frame_async(self.url, self.seek_offset_sec)
            if frame is None:
                return None
            return FrameResult(frame=frame, source_id=self.source_id, timestamp=time.time())
        except Exception:
            return None

    def close(self) -> None:
        pass
