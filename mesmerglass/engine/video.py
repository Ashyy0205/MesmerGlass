import time, threading, cv2, logging
from typing import Optional
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QPixmap
from .perf import perf_metrics  # lightweight import

class VideoStream:
    def __init__(self, path: Optional[str] = None):
        self.cap = None
        self.path = None
        self.fps = 30.0
        self.frame_interval = 1.0 / self.fps
        self.last_ts = 0.0
        self.lock = threading.Lock()
        self.frame_rgb = None
        if path:
            self.open(path)

    def open(self, path: str):
        self.close()
        self.cap = cv2.VideoCapture(path)
        if not self.cap or not self.cap.isOpened():
            logging.getLogger(__name__).error("video failed to open: %s", path)
            self.cap = None
            return
        self.path = path
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        # Handle cases where fps may be a mock or non-numeric; fall back to 30.0
        try:
            fps_val = float(fps)
        except Exception:
            fps_val = 0.0
        self.fps = fps_val if fps_val and fps_val > 0 else 30.0
        self.frame_interval = 1.0 / self.fps
        self.last_ts = 0.0
        logging.getLogger(__name__).info("video opened %s @ %.2f fps", path, self.fps)

    def close(self):
        if self.cap: self.cap.release(); self.cap = None

    def read_next_if_due(self):
        if not self.cap: return
        now = time.time()
        if now - self.last_ts < self.frame_interval: return
        # Compute dt before updating last timestamp for metrics
        dt = None if self.last_ts == 0 else (now - self.last_ts)
        self.last_ts = now
        ret, frame = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret: return
        import cv2 as _cv2
        frame = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
        with self.lock: self.frame_rgb = frame
        if dt is not None:
            # Record frame time (seconds) for performance dashboard
            perf_metrics.record_frame(dt)

    def get_qpixmap(self, target_size: QSize) -> Optional[QPixmap]:
        with self.lock:
            fr = None if self.frame_rgb is None else self.frame_rgb.copy()
        if fr is None: return None
        h, w, ch = fr.shape
        qimg = QImage(fr.data, w, h, w * ch, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        if pix.isNull(): return None
        if target_size.isValid():
            pix = pix.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return pix

