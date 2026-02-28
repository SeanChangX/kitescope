"""Background loop: fetch sources from backend, pull frame per source, detect, POST count."""
import asyncio
import os
import httpx
from vision.adapters import get_adapter, detect_source_type
from vision.detector import detect

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")


def _get_internal_secret() -> str:
    """INTERNAL_SECRET from env or shared file (when backend auto-generated it)."""
    v = os.getenv("INTERNAL_SECRET", "").strip()
    if v:
        return v
    path = os.getenv("INTERNAL_SECRET_FILE", "").strip()
    if path and os.path.isfile(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            pass
    return ""


INTERNAL_SECRET = _get_internal_secret()
INTERVAL_SEC = int(os.getenv("VISION_LOOP_INTERVAL_SEC", "30"))
SKIP_FRAMES = int(os.getenv("SKIP_FRAMES", "3"))
EMA_ALPHA = float(os.getenv("EMA_ALPHA", "0.3"))

_headers = {}
if INTERNAL_SECRET:
    _headers["X-Internal-Secret"] = INTERNAL_SECRET

_ema: dict[int, float] = {}


def _apply_ema(source_id: int, raw_count: float) -> float:
    prev = _ema.get(source_id)
    if prev is None:
        _ema[source_id] = raw_count
        return raw_count
    ema = EMA_ALPHA * raw_count + (1 - EMA_ALPHA) * prev
    _ema[source_id] = ema
    return ema


async def run_once():
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(f"{BACKEND_URL}/api/internal/sources", headers=_headers)
            if r.status_code != 200:
                return
            sources = r.json()
        except Exception:
            return
    for s in sources:
        sid = s["id"]
        url = s["url"]
        # Use URL to choose adapter so NVR/zms streams use MjpegAdapter even if stored type is http_snapshot
        stype = detect_source_type(url)
        interval = s.get("pull_interval_sec", 5)
        try:
            adapter_cls = get_adapter(stype)
            adapter = adapter_cls(url=url, source_id=str(sid), interval_sec=interval)
            try:
                frame_result = await adapter.fetch_frame()
                if frame_result is None:
                    continue
                raw_count, _boxes = detect(frame_result.frame)
                count = _apply_ema(sid, float(raw_count))
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{BACKEND_URL}/api/internal/counts",
                        json={"source_id": sid, "count": count},
                        headers=_headers,
                    )
            finally:
                adapter.close()
        except Exception:
            continue


async def loop():
    while True:
        await run_once()
        await asyncio.sleep(INTERVAL_SEC)
