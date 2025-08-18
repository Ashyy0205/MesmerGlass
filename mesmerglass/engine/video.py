import time, threading, cv2
from typing import Optional
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QPixmap

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
            print(f"[video] failed to open: {path}")
            self.cap = None; return
        self.path = path
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 0 else 30.0
        self.frame_interval = 1.0 / self.fps
        self.last_ts = 0.0
        print(f"[video] opened {path} @ {self.fps:.2f} fps")

    def close(self):
        if self.cap: self.cap.release(); self.cap = None

    def read_next_if_due(self):
        if not self.cap: return
        now = time.time()
        if now - self.last_ts < self.frame_interval: return
        self.last_ts = now
        ret, frame = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret: return
        import cv2 as _cv2
        frame = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
        with self.lock: self.frame_rgb = frame

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

