"""Fetch one frame from a URL and return as JPEG bytes; optional overlay with detection boxes."""
import cv2
from vision.adapters import get_adapter, detect_source_type
from vision.detector import detect

_OVERLAY_BOX_COLOR_BGR = (80, 0, 255)  # Theme red (#ff0050) in OpenCV BGR order.
_OVERLAY_FILL_ALPHA = 0.12  # 12% tint.
_OVERLAY_CORNER_THICKNESS = 2
_OVERLAY_CORNER_RATIO = 0.24
_OVERLAY_CORNER_MIN_PX = 8


def _draw_corner_box(frame, x1: int, y1: int, x2: int, y2: int) -> None:
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(frame.shape[1] - 1, x2)
    y2 = min(frame.shape[0] - 1, y2)
    if x2 <= x1 or y2 <= y1:
        return

    # Fill box with low-opacity theme color.
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), _OVERLAY_BOX_COLOR_BGR, -1)
    cv2.addWeighted(overlay, _OVERLAY_FILL_ALPHA, frame, 1 - _OVERLAY_FILL_ALPHA, 0, frame)

    w = x2 - x1
    h = y2 - y1
    corner = max(_OVERLAY_CORNER_MIN_PX, int(min(w, h) * _OVERLAY_CORNER_RATIO))
    corner = min(corner, max(1, w // 2), max(1, h // 2))

    c = _OVERLAY_BOX_COLOR_BGR
    t = _OVERLAY_CORNER_THICKNESS
    # Top-left
    cv2.line(frame, (x1, y1), (x1 + corner, y1), c, t)
    cv2.line(frame, (x1, y1), (x1, y1 + corner), c, t)
    # Top-right
    cv2.line(frame, (x2 - corner, y1), (x2, y1), c, t)
    cv2.line(frame, (x2, y1), (x2, y1 + corner), c, t)
    # Bottom-left
    cv2.line(frame, (x1, y2 - corner), (x1, y2), c, t)
    cv2.line(frame, (x1, y2), (x1 + corner, y2), c, t)
    # Bottom-right
    cv2.line(frame, (x2 - corner, y2), (x2, y2), c, t)
    cv2.line(frame, (x2, y2 - corner), (x2, y2), c, t)


async def fetch_snapshot_jpeg(url: str, seek_offset_sec: float = 0) -> bytes | None:
    stype = detect_source_type(url)
    adapter_cls = get_adapter(stype)
    adapter = adapter_cls(url=url, source_id="preview", interval_sec=5, seek_offset_sec=seek_offset_sec)
    try:
        frame_result = await adapter.fetch_frame()
        if frame_result is None:
            return None
        _, buf = cv2.imencode(".jpg", frame_result.frame)
        return buf.tobytes()
    finally:
        adapter.close()


async def fetch_snapshot_jpeg_with_overlay(url: str, seek_offset_sec: float = 0) -> tuple[bytes | None, int]:
    """Fetch one frame, run detection, draw boxes. Returns (JPEG bytes, count) for this frame."""
    stype = detect_source_type(url)
    adapter_cls = get_adapter(stype)
    adapter = adapter_cls(url=url, source_id="preview", interval_sec=5, seek_offset_sec=seek_offset_sec)
    try:
        frame_result = await adapter.fetch_frame()
        if frame_result is None:
            return None, 0
        frame = frame_result.frame
        count, boxes = detect(frame)
        for (x1, y1, x2, y2) in boxes:
            _draw_corner_box(frame, int(x1), int(y1), int(x2), int(y2))
        _, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes(), count
    finally:
        adapter.close()
