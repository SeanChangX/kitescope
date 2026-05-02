# Minimal HTTP API for vision: health, config; background ingestion loop
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import time
from fastapi import FastAPI, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware

from vision.ingestion_loop import loop as ingestion_loop

_SNAPSHOT_CONCURRENCY = max(1, min(20, int(os.getenv("VISION_SNAPSHOT_CONCURRENCY", "8"))))

# Background CPU sampling: sample over 1s every 10s so /config returns CPU during workload, not during request
_cpu_sample: float | None = None
_cpu_sample_interval = 10
_cpu_task: asyncio.Task | None = None


def _sync_cpu_sample() -> float | None:
    """Blocking CPU sample; must be run in executor to avoid freezing the event loop."""
    try:
        import psutil
        proc = psutil.Process()
        return round(proc.cpu_percent(interval=1.0), 1)
    except Exception:
        return None


async def _cpu_sampler_loop():
    global _cpu_sample
    loop = asyncio.get_event_loop()
    while True:
        _cpu_sample = await loop.run_in_executor(None, _sync_cpu_sample)
        await asyncio.sleep(_cpu_sample_interval)
_snapshot_semaphore = asyncio.Semaphore(_SNAPSHOT_CONCURRENCY)
# Throttle "snapshot failed" log per URL to avoid flooding when YouTube/server blocks same URL repeatedly
_fail_log_throttle: dict[str, float] = {}
_fail_log_interval_sec = 300
log = logging.getLogger("vision.app")

# Silence per-request httpx INFO logs unless VISION_LOG_LEVEL=DEBUG, so the
# default WARNING/INFO output isn't drowned by every backend heartbeat and
# snapshot fetch. Set VISION_LOG_LEVEL=DEBUG to see full HTTP traffic.
if (os.getenv("VISION_LOG_LEVEL", "WARNING").upper() != "DEBUG"):
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _apply_saved_model_selection() -> None:
    """On startup, apply model selection from MODELS_DIR/.selected (written by backend on save)."""
    import os
    from vision.detector import MODELS_DIR, reload_model
    if not MODELS_DIR:
        return

    selected_path = os.path.join(MODELS_DIR, ".selected")

    def _persist_selected(name: str) -> None:
        try:
            with open(selected_path, "w") as f:
                f.write(name)
        except OSError:
            pass

    def _fallback_to_first_onnx() -> None:
        try:
            candidates = sorted(
                name for name in os.listdir(MODELS_DIR)
                if name.lower().endswith(".onnx") and os.path.isfile(os.path.join(MODELS_DIR, name))
            )
        except OSError:
            return
        for candidate in candidates:
            if reload_model(candidate):
                log.warning("Fell back to stable ONNX model on startup: %s", candidate)
                _persist_selected(candidate)
                return

    if not os.path.isfile(selected_path):
        return
    try:
        with open(selected_path) as f:
            name = (f.read() or "").strip()
        if name and reload_model(name):
            log.info("Applied saved model selection: %s", name)
        elif name:
            log.warning("Saved model selection rejected on startup: %s", name)
            _fallback_to_first_onnx()
    except OSError:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cpu_task
    _apply_saved_model_selection()
    _cpu_task = asyncio.create_task(_cpu_sampler_loop())
    task = asyncio.create_task(ingestion_loop())
    yield
    _cpu_task.cancel()
    task.cancel()
    try:
        await _cpu_task
    except asyncio.CancelledError:
        pass
    try:
        await task
    except asyncio.CancelledError:
        pass
    from vision.detector import shutdown_worker
    shutdown_worker()


app = FastAPI(title="KiteScope Vision", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vision"}


@app.get("/config")
async def config():
    from vision.detector import (
        _get_session,
        get_detector_status,
        get_inference_stats,
        MODEL_PATH,
        CONFIDENCE_THRESHOLD,
    )
    from vision.ingestion_loop import INGESTION_CONCURRENCY
    status = get_detector_status()
    # Only touch the ONNX session here; avoid constructing the Edge TPU interpreter
    # from a status endpoint to reduce native-library instability when models switch.
    onnx_loaded = _get_session() is not None
    inference_stats = get_inference_stats()
    configured_model_architecture = (
        "tflite" if MODEL_PATH.lower().endswith(".tflite")
        else "onnx" if MODEL_PATH.lower().endswith(".onnx")
        else None
    )
    active_model_path = None
    if status["detector_device"] == "cpu" and configured_model_architecture == "onnx":
        active_model_path = MODEL_PATH
    elif status["detector_device"] == "edgetpu" and configured_model_architecture == "tflite":
        active_model_path = MODEL_PATH
    # CPU from background sampler (reflects workload). RAM from current process
    process_stats = {"cpu_percent": _cpu_sample, "memory_percent": None, "memory_mb": None}
    try:
        import psutil
        proc = psutil.Process()
        process_stats["memory_percent"] = round(proc.memory_percent(), 2)
        process_stats["memory_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass
    return {
        "model_path": MODEL_PATH,
        "active_model_path": active_model_path,
        "model_architecture": configured_model_architecture,
        "active_model_architecture": (
            configured_model_architecture if active_model_path else None
        ),
        "model_loaded": onnx_loaded or (status["detector_device"] == "edgetpu" and active_model_path is not None),
        "model_exists": os.path.isfile(MODEL_PATH) if MODEL_PATH else False,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "skip_frames": int(os.getenv("SKIP_FRAMES", "3")),
        "ingestion_concurrency": INGESTION_CONCURRENCY,
        "detector_device": status["detector_device"],
        "detect_device_env": status["detect_device_env"],
        "tpu_detected": status["tpu_detected"],
        "tpu_devices": status["tpu_devices"],
        "inference_speed_ms": inference_stats.get("inference_speed_ms"),
        "cpu_percent": process_stats.get("cpu_percent"),
        "memory_percent": process_stats.get("memory_percent"),
        "memory_mb": process_stats.get("memory_mb"),
    }


@app.post("/config")
async def update_config(
    body: dict = Body(None),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    """Internal: update detection config (e.g. confidence_threshold). Requires X-Internal-Secret."""
    from vision.ingestion_loop import INTERNAL_SECRET
    from vision.detector import set_confidence_threshold
    if not INTERNAL_SECRET or x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = body or {}
    if "confidence_threshold" in data:
        try:
            v = float(data["confidence_threshold"])
            set_confidence_threshold(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="confidence_threshold must be a number")
    return {"ok": True}


@app.post("/reload-model")
async def reload_model_endpoint(
    model: str = "",
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    """Internal: switch detection model by filename (under MODELS_DIR). Requires X-Internal-Secret."""
    from vision.ingestion_loop import INTERNAL_SECRET
    from vision.detector import get_last_reload_error, reload_model
    if not INTERNAL_SECRET or x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    name = (model or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="model query required")
    if not await asyncio.to_thread(reload_model, name):
        raise HTTPException(status_code=400, detail=get_last_reload_error() or "Model reload failed")
    return {"ok": True, "model_path": name, "restarting": False}


@app.get("/snapshot")
async def snapshot(url: str = "", overlay: bool = False, t: str = "", verify_tls: str = "1"):
    """Fetch one frame from stream URL and return as JPEG. overlay=1 draws detection boxes. t=tick for YouTube seek (sec = tick*5). verify_tls=0 disables TLS cert verification (only for trusted sources with expired certs)."""
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
    verify = (verify_tls or "1").strip() not in ("0", "false", "False", "no", "")
    try:
        p = urlparse(url)
        url_safe = f"{p.scheme}://{p.netloc}{p.path or '/'}" if p.netloc else url[:60]
    except Exception:
        url_safe = url[:60] if url else ""
    async with _snapshot_semaphore:
        log.debug("snapshot request url=%s overlay=%s seek_sec=%s verify_tls=%s", url_safe, overlay, seek_sec, verify)
        if overlay:
            data, det_count = await fetch_snapshot_jpeg_with_overlay(url, seek_sec, verify_tls=verify)
        else:
            data = await fetch_snapshot_jpeg(url, seek_sec, verify_tls=verify)
            det_count = 0
        if data is None and seek_sec > 0:
            log.info("snapshot failed at seek_sec=%s, retrying from start (loop)", seek_sec)
            if overlay:
                data, det_count = await fetch_snapshot_jpeg_with_overlay(url, 0, verify_tls=verify)
            else:
                data = await fetch_snapshot_jpeg(url, 0, verify_tls=verify)
                det_count = 0
    if data is None:
        now = time.monotonic()
        if now - _fail_log_throttle.get(url_safe, 0) >= _fail_log_interval_sec:
            _fail_log_throttle[url_safe] = now
            log.warning("snapshot failed to fetch frame url=%s (throttled: same URL logged at most once per %ss)", url_safe, _fail_log_interval_sec)
        raise HTTPException(status_code=502, detail="Failed to fetch frame")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"X-Detection-Count": str(det_count)},
    )
