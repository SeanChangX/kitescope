# Pluggable adapters: http_snapshot, mjpeg, rtsp, go2rtc, youtube_live
from .base import BaseAdapter, FrameResult

__all__ = ["BaseAdapter", "FrameResult", "detect_source_type", "get_adapter"]

def detect_source_type(url: str) -> str:
    url_lower = url.lower().strip()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube_live"
    if url_lower.startswith("rtsp://"):
        return "rtsp"
    if "go2rtc" in url_lower or ":1984" in url_lower:
        return "go2rtc"
    if "mjpeg" in url_lower or "/video" in url_lower or ".mjpg" in url_lower or "stream.mjpg" in url_lower:
        return "mjpeg"
    # ZoneMinder zms, NVR CGI streams return multipart/x-mixed-replace (infinite MJPEG)
    if "/zms" in url_lower or "/cgi-bin/" in url_lower or "thi-vms" in url_lower:
        return "mjpeg"
    return "http_snapshot"


def get_adapter(source_type: str):
    if source_type == "http_snapshot":
        from .http_snapshot import HttpSnapshotAdapter
        return HttpSnapshotAdapter
    if source_type == "mjpeg":
        from .mjpeg import MjpegAdapter
        return MjpegAdapter
    if source_type == "go2rtc":
        from .go2rtc import Go2rtcAdapter
        return Go2rtcAdapter
    if source_type == "rtsp":
        from .rtsp import RtspAdapter
        return RtspAdapter
    if source_type == "youtube_live":
        from .youtube_live import YoutubeLiveAdapter
        return YoutubeLiveAdapter
    from .http_snapshot import HttpSnapshotAdapter
    return HttpSnapshotAdapter
