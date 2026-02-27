def detect_source_type(url: str) -> str:
    """Mirror vision adapter logic: infer source type from URL."""
    u = (url or "").lower().strip()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube_live"
    if u.startswith("rtsp://"):
        return "rtsp"
    if "go2rtc" in u or ":1984" in u:
        return "go2rtc"
    if "mjpeg" in u or "/video" in u or ".mjpg" in u or "stream.mjpg" in u:
        return "mjpeg"
    if "/zms" in u or "/cgi-bin/" in u or "thi-vms" in u:
        return "mjpeg"
    return "http_snapshot"


def should_proxy_via_go2rtc(source_type: str) -> bool:
    """True when source should be registered with local go2rtc and consumed via go2rtc (RTSP, generic HTTP)."""
    return (source_type or "").strip().lower() in ("rtsp", "http_snapshot")


def is_browser_only_stream(url: str) -> bool:
    """True if URL likely serves MJPEG/multipart in browser but often fails when server-proxied (e.g. ZoneMinder zms, NVR CGI)."""
    if not url:
        return False
    u = url.lower()
    return "/zms" in u or "/cgi-bin/" in u or "thi-vms" in u or "mjpeg" in u or "multipart" in u
