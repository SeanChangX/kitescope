# RTSP: OpenCV VideoCapture in thread to avoid blocking event loop
import asyncio
import time
import cv2
import numpy as np
from .base import BaseAdapter, FrameResult


def _read_rtsp_frame(url: str) -> np.ndarray | None:
    cap = cv2.VideoCapture(url)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = cap.read()
        if not ret or frame is None:
            return None
        return frame
    finally:
        cap.release()


class RtspAdapter(BaseAdapter):
    async def fetch_frame(self) -> FrameResult | None:
        try:
            frame = await asyncio.to_thread(_read_rtsp_frame, self.url)
            if frame is None:
                return None
            return FrameResult(frame=frame, source_id=self.source_id, timestamp=time.time())
        except Exception:
            return None

    def close(self) -> None:
        pass
