from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer
import logging

class SpiralDuplicateWindow(QWidget):
    def __init__(self, screen, geometry, parent=None):
        super().__init__(parent)
        self.setGeometry(geometry)
        self.setWindowTitle("Spiral Duplicate")
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.label)
        self._last_image = None
        self._timer = None  # Timer removed; will use frame signal
        self._image_source = None
        logging.getLogger(__name__).info(f"[spiral.dup] SpiralDuplicateWindow created for geometry {geometry}")

    def connect_frame_signal(self, compositor):
        # Connect to compositor's frame_drawn signal for frame-synced updates
        compositor.frame_drawn.connect(self._update_image)

    def set_image_source(self, image_source_func):
        self._image_source = image_source_func

    def _update_image(self):
        if self._image_source:
            img = self._image_source()
            if img and isinstance(img, QImage):
                if img.isNull() or img.width() == 0 or img.height() == 0:
                    logging.getLogger(__name__).warning(f"[spiral.dup] _update_image: INVALID image (null or zero size)")
                else:
                    logging.getLogger(__name__).info(f"[spiral.dup] _update_image: VALID image w={img.width()} h={img.height()} format={img.format()}")
                # --- Option A: scale image to window pixel size ---
                dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
                tw, th = max(1, int(self.width()*dpr)), max(1, int(self.height()*dpr))
                # Normalize source image DPR to 1 for pixel math
                if img.devicePixelRatio() != 1.0:
                    img = img.copy()
                    img.setDevicePixelRatio(1.0)
                # Scale to fill mirror window
                if img.width() != tw or img.height() != th:
                    img = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                pm = QPixmap.fromImage(img)
                pm.setDevicePixelRatio(dpr)
                self._last_image = img
                self.label.setPixmap(pm)
            else:
                logging.getLogger(__name__).warning(f"[spiral.dup] _update_image: No image or not QImage (type={type(img)})")

    def closeEvent(self, event):
        if self._timer:
            self._timer.stop()
        super().closeEvent(event)
        super().closeEvent(event)
