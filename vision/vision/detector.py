# Detection pipeline: load ONNX (YOLOv8-style), run inference, NMS, filter by confidence
import logging
import os
import numpy as np
import cv2
from typing import List, Tuple

log = logging.getLogger(__name__)

MODEL_PATH = os.getenv("MODEL_PATH", "/app/models/kite_nano.onnx")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
IOU_THRESHOLD = float(os.getenv("IOU_THRESHOLD", "0.45"))
KITE_CLASS_ID = int(os.getenv("KITE_CLASS_ID", "0"))  # Class index to count as kite (0 for single-class)
INPUT_SIZE = int(os.getenv("DETECT_INPUT_SIZE", "640"))

_session = None
_session_logged = False


def _get_session():
    global _session, _session_logged
    if _session is not None:
        return _session
    if not MODEL_PATH or not os.path.isfile(MODEL_PATH):
        if not _session_logged:
            log.warning(
                "Detection disabled: model file not found at MODEL_PATH=%s. Put kite_nano.onnx there (e.g. docker cp kite_nano.onnx <vision_container>:/app/models/).",
                MODEL_PATH,
            )
            _session_logged = True
        return None
    try:
        import onnxruntime as ort
        providers = ["CPUExecutionProvider"]
        _session = ort.InferenceSession(MODEL_PATH, providers=providers)
        log.info("Detection model loaded from %s", MODEL_PATH)
        return _session
    except Exception as e:
        if not _session_logged:
            log.warning("Detection disabled: failed to load ONNX model from %s: %s", MODEL_PATH, e)
            _session_logged = True
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


def _postprocess(
    output: np.ndarray,
    gain: float,
    pad: Tuple[float, float, float, float],
    orig_wh: Tuple[int, int],
) -> List[Tuple[float, float, float, float]]:
    """YOLOv8 output (1, C, N) -> list of (x1, y1, x2, y2) in original image coords."""
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


def detect(frame: np.ndarray) -> Tuple[int, List[Tuple[float, float, float, float]]]:
    """
    Returns (count, list of (x1, y1, x2, y2) boxes in image coordinates).
    If no model or error, returns (0, []).
    """
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
