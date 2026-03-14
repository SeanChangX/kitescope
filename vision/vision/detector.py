# Detection pipeline: load ONNX (YOLOv8-style) or TFLite (Edge TPU), run inference, NMS, filter by confidence
import logging
import multiprocessing as mp
import os
import time
from collections import deque
from pathlib import Path
import numpy as np
import cv2
from typing import List, Tuple, Any

log = logging.getLogger(__name__)

# Rolling window of last N inference durations (seconds) for stats
_INFERENCE_TIMES: deque = deque(maxlen=30)

MODELS_DIR = os.getenv("MODELS_DIR", "").strip().rstrip("/")
_DEFAULT_MODEL_PATH = os.getenv("MODEL_PATH", "/app/models/kite_nano.onnx")
MODEL_PATH = _DEFAULT_MODEL_PATH
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
IOU_THRESHOLD = float(os.getenv("IOU_THRESHOLD", "0.45"))

# DETECT_DEVICE: auto = use TPU if detected else CPU; cpu = force ONNX CPU; edgetpu = force Coral (fail if none)
DETECT_DEVICE_ENV = (os.getenv("DETECT_DEVICE") or "auto").strip().lower()
if DETECT_DEVICE_ENV not in ("auto", "cpu", "edgetpu"):
    DETECT_DEVICE_ENV = "auto"

def set_confidence_threshold(value: float) -> None:
    """Update confidence threshold at runtime (e.g. from admin). Clamped to 0-1."""
    global CONFIDENCE_THRESHOLD
    CONFIDENCE_THRESHOLD = max(0.0, min(1.0, value))
KITE_CLASS_ID = int(os.getenv("KITE_CLASS_ID", "0"))  # Class index to count as kite (0 for single-class)
INPUT_SIZE = int(os.getenv("DETECT_INPUT_SIZE", "640"))

_session: Any = None
_session_logged = False
_edgetpu_logged = False
_last_reload_error: str | None = None
_TPU_DETECT_CACHE_TTL_SEC = 2.0
_tpu_detect_cache_at = 0.0
_tpu_detect_cache_result: Tuple[str, List[dict]] | None = None

# Well-known install paths for the Edge TPU shared library.
_EDGETPU_LIB_CANDIDATES = [
    "/usr/lib/x86_64-linux-gnu/libedgetpu.so.1.0",
    "/usr/lib/aarch64-linux-gnu/libedgetpu.so.1.0",
    "/usr/lib/arm-linux-gnueabihf/libedgetpu.so.1.0",
    "/usr/lib/libedgetpu.so.1.0",
]

# Cached TPU detection result (type, path list)
def _detect_tpu() -> Tuple[str, List[dict]]:
    """Return detected Coral hardware devices, not just installed runtime libraries."""
    global _tpu_detect_cache_at, _tpu_detect_cache_result
    now = time.monotonic()
    if _tpu_detect_cache_result is not None and (now - _tpu_detect_cache_at) < _TPU_DETECT_CACHE_TTL_SEC:
        kind, devices = _tpu_detect_cache_result
        return kind, [dict(d) for d in devices]

    devices: List[dict] = []
    # Only check whether the runtime library *exists* on disk -- do NOT load it
    # with ctypes.CDLL.  Newer feranick libedgetpu builds start USB monitoring
    # threads on dlopen, which conflict with the probe subprocess and cause
    # SIGSEGV in the main process.
    if not any(os.path.isfile(p) for p in _EDGETPU_LIB_CANDIDATES):
        log.debug("Coral TPU not available: libedgetpu.so.1.0 not found")
        _tpu_detect_cache_at = now
        _tpu_detect_cache_result = ("cpu", [])
        return ("cpu", [])

    # USB Coral can enumerate under two VID/PID pairs depending on firmware state.
    usb_ids = {("1a6e", "089a"), ("1a6e", "089b"), ("18d1", "9302")}
    for dev_dir in Path("/sys/bus/usb/devices").glob("*"):
        vendor_file = dev_dir / "idVendor"
        product_file = dev_dir / "idProduct"
        if not vendor_file.is_file() or not product_file.is_file():
            continue
        try:
            vendor = vendor_file.read_text().strip().lower()
            product = product_file.read_text().strip().lower()
        except OSError:
            continue
        if (vendor, product) in usb_ids:
            devices.append({"type": "usb", "path": dev_dir.name})

    # PCIe / M.2 Coral commonly exposes /dev/apex_* character devices.
    for apex_dev in Path("/dev").glob("apex_*"):
        if apex_dev.exists():
            devices.append({"type": "pcie", "path": str(apex_dev)})

    if devices:
        result = ("edgetpu", devices)
    else:
        result = ("cpu", [])
    _tpu_detect_cache_at = now
    _tpu_detect_cache_result = (result[0], [dict(d) for d in result[1]])
    return result


def get_detector_status() -> dict:
    """Return current detector device type and TPU info for system status API."""
    kind, devices = _detect_tpu()
    want_edgetpu = DETECT_DEVICE_ENV == "edgetpu" or (DETECT_DEVICE_ENV == "auto" and kind == "edgetpu")
    active = "edgetpu" if (want_edgetpu and kind == "edgetpu" and _tpu_worker is not None and _tpu_worker.is_alive) else "cpu"
    return {
        "detector_device": active,
        "detect_device_env": DETECT_DEVICE_ENV,
        "tpu_detected": kind == "edgetpu",
        "tpu_devices": [{"type": d.get("type"), "path": d.get("path")} for d in devices],
    }


def record_inference_duration(seconds: float) -> None:
    """Record one inference duration for rolling stats."""
    _INFERENCE_TIMES.append(seconds)


def get_inference_stats() -> dict:
    """Return rolling average inference time in ms for system status. Empty list -> None."""
    if not _INFERENCE_TIMES:
        return {"inference_speed_ms": None}
    avg_s = sum(_INFERENCE_TIMES) / len(_INFERENCE_TIMES)
    return {"inference_speed_ms": round(avg_s * 1000, 2)}


def _resolve_device_for_backend() -> str:
    """Return 'edgetpu' if we should use Coral, else 'cpu'."""
    if DETECT_DEVICE_ENV == "cpu":
        return "cpu"
    kind, _ = _detect_tpu()
    if DETECT_DEVICE_ENV == "edgetpu":
        return kind  # may be 'cpu' if no TPU
    return kind  # auto


def get_last_reload_error() -> str | None:
    return _last_reload_error


def reload_model(filename: str) -> bool:
    """Switch to model by filename under MODELS_DIR.

    Clears cached sessions so next inference loads it.  Returns True if path exists.
    """
    global MODEL_PATH, _session, _session_logged, _tpu_worker, _edgetpu_logged, _edgetpu_disabled, _last_reload_error
    _last_reload_error = None
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        _last_reload_error = "Invalid model filename"
        return False
    path = os.path.join(MODELS_DIR, filename) if MODELS_DIR else filename
    if not os.path.isfile(path):
        _last_reload_error = "Model file not found"
        return False
    MODEL_PATH = path
    _session = None
    _session_logged = False
    if _tpu_worker is not None:
        _tpu_worker.stop()
        _tpu_worker = None
        time.sleep(2)
    _edgetpu_logged = False
    _edgetpu_disabled = False
    log.info("Model will reload from %s on next inference", MODEL_PATH)
    return True


def _get_session():
    """ONNX session for CPU backend."""
    global _session, _session_logged
    if _session is not None:
        return _session
    if not MODEL_PATH or not os.path.isfile(MODEL_PATH):
        if not _session_logged:
            log.debug(
                "Detection disabled: model file not found at MODEL_PATH=%s. Upload model to enable.",
                MODEL_PATH,
            )
            _session_logged = True
        return None
    if not MODEL_PATH.lower().endswith(".onnx"):
        if not _session_logged:
            log.debug("CPU backend expects .onnx model; got %s", MODEL_PATH)
            _session_logged = True
        return None
    try:
        import onnxruntime as ort
        providers = ["CPUExecutionProvider"]
        _session = ort.InferenceSession(MODEL_PATH, providers=providers)
        log.info("Detection model loaded from %s (CPU)", MODEL_PATH)
        return _session
    except Exception as e:
        if not _session_logged:
            log.warning("Detection disabled: failed to load ONNX model from %s: %s", MODEL_PATH, e)
            _session_logged = True
        return None


# Flag set when the Edge TPU worker crashes or fails to start.
# Once set, all subsequent Edge TPU attempts in this process are skipped.
_edgetpu_disabled = False
_tpu_worker: Any = None


# ---------------------------------------------------------------------------
# Edge TPU subprocess worker
#
# libedgetpu's USB driver calls LOG(FATAL) -> abort() on a background C++
# thread when a bulk transfer fails.  Python signal handlers cannot intercept
# this because they only run on the main thread.  The only safe strategy is
# to never load libedgetpu in the main vision process.  Instead we spawn a
# dedicated worker process; if it crashes, the main process stays alive and
# falls back to CPU inference.
# ---------------------------------------------------------------------------

def _edgetpu_worker_fn(model_path: str, device: str, pipe) -> None:
    """Entry point for the Edge TPU worker subprocess (runs in a spawn context)."""
    import numpy as _np
    try:
        from tflite_runtime.interpreter import Interpreter, load_delegate
        delegate = load_delegate("libedgetpu.so.1.0", {"device": device})
        interpreter = Interpreter(
            model_path=model_path, experimental_delegates=[delegate],
        )
        interpreter.allocate_tensors()

        inp_detail = interpreter.get_input_details()[0]
        out_detail = interpreter.get_output_details()[0]

        pipe.send("ready")
    except Exception as exc:
        pipe.send(f"error:{exc}")
        return

    while True:
        try:
            msg = pipe.recv()
        except EOFError:
            break
        if msg is None:
            break

        blob = msg
        try:
            # Quantize input: blob arrives as uint8 [0,255] HWC from main process.
            qp = inp_detail.get("quantization_parameters") or {}
            scales, zeros = qp.get("scales"), qp.get("zero_points")
            in_dtype = inp_detail["dtype"]

            if in_dtype == _np.uint8:
                if scales is not None and len(scales) and zeros is not None and len(zeros):
                    s, z = float(scales[0]), int(zeros[0])
                    if s == 1.0 and z == 0:
                        blob = blob.astype(_np.uint8)
                    else:
                        blob = _np.clip(_np.rint(blob.astype(_np.float32) / 255.0 / s + z), 0, 255).astype(_np.uint8)
                else:
                    blob = blob.astype(_np.uint8)
            elif in_dtype == _np.int8:
                if scales is not None and len(scales) and zeros is not None and len(zeros):
                    s, z = float(scales[0]), int(zeros[0])
                    blob = _np.clip(_np.rint(blob.astype(_np.float32) / 255.0 / s + z), -128, 127).astype(_np.int8)
                else:
                    blob = (blob.astype(_np.int16) - 128).astype(_np.int8)
            else:
                blob = blob.astype(_np.float32) / 255.0

            interpreter.set_tensor(inp_detail["index"], blob)
            interpreter.invoke()
            output = interpreter.get_tensor(out_detail["index"]).copy()

            # Dequantize output to float32
            out_dtype = out_detail["dtype"]
            if out_dtype in (_np.uint8, _np.int8):
                oq = out_detail.get("quantization_parameters", {})
                sc, zp = oq.get("scales"), oq.get("zero_points")
                if sc is not None and len(sc) and zp is not None and len(zp):
                    output = (output.astype(_np.float32) - float(zp[0])) * float(sc[0])

            pipe.send(output)
        except Exception:
            pipe.send(None)
            break


class _EdgeTPUWorker:
    """Manages Edge TPU inference in an isolated subprocess."""

    def __init__(self) -> None:
        self._process: Any = None
        self._pipe: Any = None
        self._alive = False
        self._model_path: str | None = None

    @property
    def is_alive(self) -> bool:
        return self._alive and self._process is not None and self._process.is_alive()

    def start(self, model_path: str, retries: int = 3) -> bool:
        device = (os.getenv("DETECT_EDGETPU_DEVICE") or "").strip() or "usb"
        for attempt in range(1, retries + 1):
            self.stop()
            if attempt > 1:
                time.sleep(3)
                log.info("Edge TPU worker retry %d/%d after USB recovery delay", attempt, retries)
            ctx = mp.get_context("spawn")
            parent_conn, child_conn = ctx.Pipe()
            self._pipe = parent_conn
            self._process = ctx.Process(
                target=_edgetpu_worker_fn,
                args=(model_path, device, child_conn),
                daemon=True,
            )
            self._process.start()
            child_conn.close()
            try:
                if self._pipe.poll(timeout=30):
                    msg = self._pipe.recv()
                    if msg == "ready":
                        self._alive = True
                        self._model_path = model_path
                        log.info("Edge TPU worker started for %s (pid %s)", model_path, self._process.pid)
                        return True
                    log.warning("Edge TPU worker attempt %d failed: %s", attempt, msg)
                else:
                    log.warning("Edge TPU worker attempt %d timed out", attempt)
            except Exception as exc:
                log.warning("Edge TPU worker attempt %d error: %s", attempt, exc)
        self.stop()
        return False

    def infer(self, blob: Any, timeout: float = 10.0) -> Any:
        if not self.is_alive:
            return None
        try:
            self._pipe.send(blob)
            if self._pipe.poll(timeout=timeout):
                result = self._pipe.recv()
                if result is None:
                    self._alive = False
                return result
            log.warning("Edge TPU inference timed out")
            self._alive = False
            return None
        except (BrokenPipeError, EOFError, OSError) as exc:
            log.warning("Edge TPU worker pipe error: %s", exc)
            self._alive = False
            return None

    def stop(self) -> None:
        if self._pipe is not None:
            try:
                self._pipe.send(None)
            except Exception:
                pass
            try:
                self._pipe.close()
            except Exception:
                pass
        if self._process is not None:
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=2)
        self._process = None
        self._pipe = None
        self._alive = False
        self._model_path = None


def _letterbox(img: np.ndarray, new_shape: Tuple[int, int] = (640, 640)) -> Tuple[np.ndarray, float, Tuple[float, float, float, float]]:
    """Resize with aspect ratio, pad to new_shape. Returns (padded_img, gain, (pad_top, pad_left, pad_bottom, pad_right))."""
    h, w = img.shape[:2]
    r = min(new_shape[0] / h, new_shape[1] / w)
    new_unpad = (round(w * r), round(h * r))
    resized = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    dw = (new_shape[1] - new_unpad[0]) / 2
    dh = (new_shape[0] - new_unpad[1]) / 2
    top, bottom = round(dh - 0.1), round(dh + 0.1)
    left, right = round(dw - 0.1), round(dw + 0.1)
    out = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return out, r, (top, left, bottom, right)


def _preprocess(frame: np.ndarray) -> Tuple[np.ndarray, float, Tuple[float, float, float, float], Tuple[int, int]]:
    lb, gain, pad = _letterbox(frame, (INPUT_SIZE, INPUT_SIZE))
    pad_top, pad_left, pad_bottom, pad_right = pad
    # HWC -> CHW, normalize 0-1
    blob = np.transpose(lb.astype(np.float32) / 255.0, (2, 0, 1))
    blob = np.expand_dims(blob, axis=0)
    orig_h, orig_w = frame.shape[:2]
    return blob, gain, pad, (orig_w, orig_h)


def _preprocess_tflite(frame: np.ndarray) -> Tuple[np.ndarray, float, Tuple[float, float, float, float], Tuple[int, int]]:
    """Same letterbox as ONNX; TFLite expects HWC (1, H, W, C)."""
    lb, gain, pad = _letterbox(frame, (INPUT_SIZE, INPUT_SIZE))
    orig_h, orig_w = frame.shape[:2]
    # (H, W, C) -> (1, H, W, C)
    blob = np.expand_dims(lb, axis=0)
    return blob, gain, pad, (orig_w, orig_h)


def _postprocess(
    output: np.ndarray,
    gain: float,
    pad: Tuple[float, float, float, float],
    orig_wh: Tuple[int, int],
) -> List[Tuple[float, float, float, float]]:
    """YOLOv8 output (1, C, N) or (1, N, C) -> list of (x1, y1, x2, y2) in original image coords."""
    out = np.squeeze(output)
    if out.ndim == 2:
        out = out.T
    else:
        out = np.transpose(out)
    rows = out.shape[0]
    pad_top, pad_left, _, _ = pad
    orig_w, orig_h = orig_wh
    boxes = []
    scores = []
    # Output layout: first 4 = x_center, y_center, w, h (in letterbox coords); rest = class scores
    num_classes = out.shape[1] - 4
    for i in range(rows):
        if num_classes == 1:
            score = float(out[i, 4])
            class_id = 0
        else:
            class_scores = out[i, 4:]
            class_id = int(np.argmax(class_scores))
            if class_id != KITE_CLASS_ID:
                continue
            score = float(class_scores[class_id])
        if score < CONFIDENCE_THRESHOLD:
            continue
        xc, yc, w, h = out[i, 0], out[i, 1], out[i, 2], out[i, 3]
        # Letterbox to original: subtract pad, divide by gain
        xc = (xc - pad_left) / gain
        yc = (yc - pad_top) / gain
        w = w / gain
        h = h / gain
        x1 = max(0, xc - w / 2)
        y1 = max(0, yc - h / 2)
        x2 = min(orig_w, xc + w / 2)
        y2 = min(orig_h, yc + h / 2)
        boxes.append([x1, y1, x2 - x1, y2 - y1])
        scores.append(score)
    if not boxes:
        return []
    indices = cv2.dnn.NMSBoxes(boxes, scores, CONFIDENCE_THRESHOLD, IOU_THRESHOLD)
    result = []
    for i in np.array(indices).flatten():
        x1, y1, w, h = boxes[i]
        result.append((float(x1), float(y1), float(x1 + w), float(y1 + h)))
    return result


def _run_onnx(frame: np.ndarray) -> Tuple[int, List[Tuple[float, float, float, float]]]:
    session = _get_session()
    if session is None:
        return 0, []
    try:
        blob, gain, pad, orig_wh = _preprocess(frame)
        inp = session.get_inputs()[0]
        out_name = session.get_outputs()[0].name
        outputs = session.run([out_name], {inp.name: blob})
        boxes = _postprocess(outputs[0], gain, pad, orig_wh)
        return len(boxes), boxes
    except Exception:
        return 0, []


def _run_edgetpu(frame: np.ndarray) -> Tuple[int, List[Tuple[float, float, float, float]]] | None:
    global _tpu_worker, _edgetpu_disabled, _edgetpu_logged

    if _edgetpu_disabled:
        return None
    if not MODEL_PATH or not MODEL_PATH.lower().endswith(".tflite"):
        return None

    if _tpu_worker is None:
        _tpu_worker = _EdgeTPUWorker()

    if not _tpu_worker.is_alive:
        if not _tpu_worker.start(MODEL_PATH):
            if not _edgetpu_logged:
                log.warning("Edge TPU worker failed to start; falling back to CPU")
                _edgetpu_logged = True
            _edgetpu_disabled = True
            return None

    blob, gain, pad, orig_wh = _preprocess_tflite(frame)
    out_tensor = _tpu_worker.infer(blob)

    if out_tensor is None:
        log.warning("Edge TPU worker crashed or timed out; disabling for this session")
        _edgetpu_disabled = True
        _tpu_worker.stop()
        return None

    if out_tensor.ndim == 3 and out_tensor.shape[1] > out_tensor.shape[2]:
        out_tensor = np.transpose(out_tensor, (0, 2, 1))

    # Ultralytics-exported TFLite models output coordinates normalized to [0, 1].
    # _postprocess expects absolute letterbox-pixel coords.  Detect the
    # normalized case (coordinate max < 2) and rescale only the bbox rows.
    squeezed = np.squeeze(out_tensor)
    if squeezed.ndim == 2:
        if squeezed.shape[0] < squeezed.shape[1]:
            coord_max = float(squeezed[:4, :].max())
            if coord_max < 2.0 and coord_max > 0:
                squeezed[:4, :] *= INPUT_SIZE
        else:
            coord_max = float(squeezed[:, :4].max())
            if coord_max < 2.0 and coord_max > 0:
                squeezed[:, :4] *= INPUT_SIZE
        out_tensor = np.expand_dims(squeezed, 0)

    boxes = _postprocess(out_tensor, gain, pad, orig_wh)
    return len(boxes), boxes


def _runtime_fallback_to_onnx() -> bool:
    """When Edge TPU fails at runtime, auto-switch to an ONNX model in memory.

    Does NOT overwrite .selected so the user's explicit model choice persists
    across container restarts.  The retry logic in the worker will re-attempt
    the Edge TPU model on the next startup.
    """
    global MODEL_PATH, _session, _session_logged
    if not MODELS_DIR:
        return False
    try:
        candidates = sorted(
            name for name in os.listdir(MODELS_DIR)
            if name.lower().endswith(".onnx") and os.path.isfile(os.path.join(MODELS_DIR, name))
        )
    except OSError:
        return False
    if not candidates:
        log.warning("Edge TPU disabled but no ONNX fallback model found in %s", MODELS_DIR)
        return False
    MODEL_PATH = os.path.join(MODELS_DIR, candidates[0])
    _session = None
    _session_logged = False
    log.warning("Edge TPU failed at runtime; auto-switched to ONNX model: %s (in-memory only, .selected preserved)", candidates[0])
    return True


def shutdown_worker() -> None:
    """Cleanly stop the Edge TPU worker.  Called from the lifespan shutdown."""
    global _tpu_worker
    if _tpu_worker is not None:
        log.info("Shutting down Edge TPU worker")
        _tpu_worker.stop()
        _tpu_worker = None


def detect(frame: np.ndarray) -> Tuple[int, List[Tuple[float, float, float, float]]]:
    """
    Returns (count, list of (x1, y1, x2, y2) boxes in image coordinates).
    If no model or error, returns (0, []).
    Uses Edge TPU when DETECT_DEVICE allows and a .tflite model is loaded; otherwise ONNX CPU.
    """
    t0 = time.perf_counter()
    backend = _resolve_device_for_backend()
    if backend == "edgetpu":
        result = _run_edgetpu(frame)
        if result is not None:
            count, boxes = result
            record_inference_duration(time.perf_counter() - t0)
            return count, boxes
        if _edgetpu_disabled and MODEL_PATH and MODEL_PATH.lower().endswith(".tflite"):
            _runtime_fallback_to_onnx()
    count, boxes = _run_onnx(frame)
    record_inference_duration(time.perf_counter() - t0)
    return count, boxes
