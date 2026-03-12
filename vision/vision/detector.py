# Detection pipeline: load ONNX (YOLOv8-style) or TFLite (Edge TPU), run inference, NMS, filter by confidence
import logging
import os
import time
from collections import deque
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
_edgetpu_interpreter: Any = None
_edgetpu_logged = False

# Cached TPU detection result (type, path list)
_tpu_info: Tuple[str, List[dict]] | None = None


def _detect_tpu() -> Tuple[str, List[dict]]:
    """Return ('edgetpu', list of device dicts) if Coral is available, else ('cpu', [])."""
    global _tpu_info
    if _tpu_info is not None:
        return _tpu_info
    try:
        from pycoral.utils.edgetpu import list_edge_tpus
        devices = list_edge_tpus()
        if devices:
            _tpu_info = ("edgetpu", devices)
            return _tpu_info
    except Exception as e:
        log.debug("Coral TPU not available: %s", e)
    _tpu_info = ("cpu", [])
    return _tpu_info


def get_detector_status() -> dict:
    """Return current detector device type and TPU info for system status API."""
    kind, devices = _detect_tpu()
    want_edgetpu = DETECT_DEVICE_ENV == "edgetpu" or (DETECT_DEVICE_ENV == "auto" and kind == "edgetpu")
    active = "edgetpu" if (want_edgetpu and kind == "edgetpu" and _edgetpu_interpreter is not None) else "cpu"
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
    kind, _ = _detect_tpu()
    if DETECT_DEVICE_ENV == "cpu":
        return "cpu"
    if DETECT_DEVICE_ENV == "edgetpu":
        return kind  # may be 'cpu' if no TPU
    return kind  # auto


def reload_model(filename: str) -> bool:
    """Switch to model by filename under MODELS_DIR. Clears cached session so next inference loads it. Returns True if path exists."""
    global MODEL_PATH, _session, _session_logged, _edgetpu_interpreter, _edgetpu_logged
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return False
    path = os.path.join(MODELS_DIR, filename) if MODELS_DIR else filename
    if not os.path.isfile(path):
        return False
    MODEL_PATH = path
    _session = None
    _session_logged = False
    _edgetpu_interpreter = None
    _edgetpu_logged = False
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


def _get_edgetpu_interpreter():
    """TFLite interpreter with Edge TPU delegate. Returns None if no TPU or model not .tflite."""
    global _edgetpu_interpreter, _edgetpu_logged
    if _edgetpu_interpreter is not None:
        return _edgetpu_interpreter
    if not MODEL_PATH or not os.path.isfile(MODEL_PATH):
        if not _edgetpu_logged:
            log.debug("Edge TPU: no model file at %s", MODEL_PATH)
            _edgetpu_logged = True
        return None
    if not MODEL_PATH.lower().endswith(".tflite"):
        if not _edgetpu_logged:
            log.debug("Edge TPU backend expects .tflite model; got %s", MODEL_PATH)
            _edgetpu_logged = True
        return None
    backend = _resolve_device_for_backend()
    if backend != "edgetpu":
        return None
    try:
        from pycoral.utils.edgetpu import list_edge_tpus
        from pycoral.utils.edgetpu import make_interpreter
        devices = list_edge_tpus()
        if not devices:
            if not _edgetpu_logged:
                log.warning("Edge TPU requested but no Coral device detected")
                _edgetpu_logged = True
            return None
        # Use first device; for multiple TPUs we could use device path from env (e.g. DETECT_EDGETPU_DEVICE=usb:0)
        device = os.getenv("DETECT_EDGETPU_DEVICE", "").strip() or None
        _edgetpu_interpreter = make_interpreter(MODEL_PATH, device=device)
        _edgetpu_interpreter.allocate_tensors()
        log.info("Detection model loaded from %s (Edge TPU)", MODEL_PATH)
        return _edgetpu_interpreter
    except Exception as e:
        if not _edgetpu_logged:
            log.warning("Edge TPU load failed for %s: %s", MODEL_PATH, e)
            _edgetpu_logged = True
        return None


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
    interpreter = _get_edgetpu_interpreter()
    if interpreter is None:
        return None
    try:
        blob, gain, pad, orig_wh = _preprocess_tflite(frame)
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        inp = input_details[0]
        # TFLite input: HWC (1, H, W, C). Edge TPU models often uint8 [0,255] or quantized.
        if inp["dtype"] == np.uint8:
            qparams = inp.get("quantization_parameters") or {}
            scales = qparams.get("scales")
            zero_points = qparams.get("zero_points")
            if scales is not None and zero_points is not None:
                scale = float(scales[0]) if hasattr(scales, "__getitem__") else float(scales)
                zero = int(zero_points[0]) if hasattr(zero_points, "__getitem__") else int(zero_points)
                blob = (blob.astype(np.float32) / 255.0 / scale + zero).clip(0, 255).astype(np.uint8)
            else:
                blob = blob.astype(np.uint8)
        else:
            blob = (blob.astype(np.float32) / 255.0)
        interpreter.set_tensor(inp["index"], blob)
        interpreter.invoke()
        out_tensor = interpreter.get_tensor(output_details[0]["index"])
        # Dequantize if needed
        out_details = output_details[0]
        if out_details["dtype"] == np.uint8:
            q = out_details.get("quantization_parameters", {})
            scales = q.get("scales")
            zero_points = q.get("zero_points")
            if scales is not None and zero_points is not None:
                out_tensor = (out_tensor.astype(np.float32) - zero_points) * scales
        # YOLOv8 TFLite often (1, 8400, 84) -> transpose to (1, 84, 8400) for _postprocess
        if out_tensor.ndim == 3 and out_tensor.shape[1] > out_tensor.shape[2]:
            out_tensor = np.transpose(out_tensor, (0, 2, 1))
        boxes = _postprocess(out_tensor, gain, pad, orig_wh)
        return len(boxes), boxes
    except Exception:
        return None  # Signal failure so caller can fall back to CPU


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
        # Fallback to CPU when Edge TPU inference failed (exception or no interpreter)
    count, boxes = _run_onnx(frame)
    record_inference_duration(time.perf_counter() - t0)
    return count, boxes
