# Minimal HTTP API for vision: health, config; background ingestion loop
from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

from vision.ingestion_loop import loop as ingestion_loop

# Allow a few concurrent snapshots so YouTube (slow) and NVR (fast) can run in parallel; cap to avoid overload
_snapshot_semaphore = asyncio.Semaphore(4)
log = logging.getLogger("vision.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(ingestion_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="KiteScope Vision", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vision"}


@app.get("/config")
async def config():
    from vision.detector import _get_session, MODEL_PATH
    return {
        "model_path": os.getenv("MODEL_PATH", "/app/models/kite_nano.onnx"),
        "model_loaded": _get_session() is not None,
        "model_exists": os.path.isfile(MODEL_PATH) if MODEL_PATH else False,
        "confidence_threshold": float(os.getenv("CONFIDENCE_THRESHOLD", "0.5")),
        "skip_frames": int(os.getenv("SKIP_FRAMES", "3")),
    }


@app.get("/snapshot")
async def snapshot(url: str = "", overlay: bool = False, t: str = ""):
    """Fetch one frame from stream URL and return as JPEG. overlay=1 draws detection boxes. t=tick for YouTube seek (sec = tick*5)."""
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    from fastapi.responses import Response
    from urllib.parse import urlparse
    from vision.snapshot import fetch_snapshot_jpeg, fetch_snapshot_jpeg_with_overlay
    try:
        s = (t or "").strip()
        tick = int(s) if s.lstrip("-").isdigit() else 0
    except (ValueError, TypeError):
        tick = 0
    seek_sec = max(0, tick * 5)
    try:
        p = urlparse(url)
        url_safe = f"{p.scheme}://{p.netloc}{p.path or '/'}" if p.netloc else url[:60]
    except Exception:
        url_safe = url[:60] if url else ""
    async with _snapshot_semaphore:
        log.info("snapshot request url=%s overlay=%s seek_sec=%s", url_safe, overlay, seek_sec)
        if overlay:
            data, det_count = await fetch_snapshot_jpeg_with_overlay(url, seek_sec)
        else:
            data = await fetch_snapshot_jpeg(url, seek_sec)
            det_count = 0
        if data is None and seek_sec > 0:
            log.info("snapshot failed at seek_sec=%s, retrying from start (loop)", seek_sec)
            if overlay:
                data, det_count = await fetch_snapshot_jpeg_with_overlay(url, 0)
            else:
                data = await fetch_snapshot_jpeg(url, 0)
                det_count = 0
    if data is None:
        log.warning("snapshot failed to fetch frame url=%s", url_safe)
        raise HTTPException(status_code=502, detail="Failed to fetch frame")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"X-Detection-Count": str(det_count)},
    )
