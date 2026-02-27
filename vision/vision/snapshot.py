"""Fetch one frame from a URL and return as JPEG bytes; optional overlay with detection boxes."""
import cv2
from vision.adapters import get_adapter, detect_source_type
from vision.detector import detect


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
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        _, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes(), count
    finally:
        adapter.close()
