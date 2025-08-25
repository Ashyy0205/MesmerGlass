"""Overlay window implementation (clean, instrumented)."""

from __future__ import annotations

import time, logging, sys
from typing import Optional
from PyQt6.QtCore import Qt, QTimer, QRect, QSize
from PyQt6.QtGui import QPainter, QPixmap, QColor, QFont
from PyQt6.QtWidgets import QWidget

_IS_WIN = sys.platform.startswith("win") if hasattr(sys, 'platform') else False

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

class _VideoReader:
    def __init__(self, path: Optional[str]):
        self.path = path or ""
        self.cap = None
        self.cv2 = None
        self.fps = 30.0
        self._period = 1.0 / self.fps
        self._last_t = 0.0  # monotonic timestamp of last captured frame
        self._last_pix: Optional[QPixmap] = None
        if not self.path:
            return
        try:
            import cv2  # type: ignore
            self.cv2 = cv2
            cap = cv2.VideoCapture(self.path)
            if cap.isOpened():
                self.cap = cap
                fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
                if fps and fps > 1.0:
                    self.fps = float(fps)
                    self._period = 1.0 / self.fps
                logging.getLogger(__name__).info("[video] opened %s @ %.2f fps", self.path, self.fps)
            else:
                logging.getLogger(__name__).warning("[video] failed to open: %s", self.path)
        except Exception as e:
            logging.getLogger(__name__).warning("[video] OpenCV unavailable: %s", e)

    def read_if_due(self, now: float, target_size: QSize) -> Optional[QPixmap]:
        if self.cap is None: return self._last_pix
        if (now - self._last_t) < self._period and self._last_pix is not None: return self._last_pix
        ok, frame = self.cap.read()
        if not ok and self.cv2 is not None:
            try: self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0); ok, frame = self.cap.read()
            except Exception: ok = False
        if not ok or self.cv2 is None: return self._last_pix
        try:
            rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB); h, w, _ = rgb.shape
            if w <= 0 or h <= 0: return self._last_pix
            tw, th = target_size.width(), target_size.height()
            if tw <= 0 or th <= 0: return self._last_pix
            scale = max(tw / w, th / h); new_w = max(1, int(w * scale)); new_h = max(1, int(h * scale))
            rgb2 = self.cv2.resize(rgb, (new_w, new_h), interpolation=self.cv2.INTER_AREA)
            from PyQt6.QtGui import QImage
            qimg = QImage(rgb2.data, new_w, new_h, QImage.Format.Format_RGB888)
            self._last_pix = QPixmap.fromImage(qimg)
            # Record frame timing for performance metrics using elapsed since previous frame
            from ..engine.perf import perf_metrics  # local import to avoid heavy import at module top
            if self._last_t != 0.0:
                dt = now - self._last_t
                if dt > 0: perf_metrics.record_frame(dt)
            self._last_t = now
        except Exception:
            return self._last_pix
        return self._last_pix

class OverlayWindow(QWidget):
    def __init__(self, screen, primary_path: Optional[str], secondary_path: Optional[str],
                 primary_op: float, secondary_op: float, text: str, text_color: QColor,
                 font: QFont | str, text_scale_pct: int, flash_interval_ms: int,
                 flash_width_ms: int, fx_mode: str, fx_intensity: int) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(screen.geometry())
        self._shutting_down = False
        if _IS_WIN:
            try:  # pragma: no cover
                from ctypes import windll
                GWL_EXSTYLE = -20; WS_EX_LAYERED = 0x00080000; WS_EX_TRANSPARENT = 0x00000020; WS_EX_TOOLWINDOW = 0x00000080
                hwnd = int(self.winId()); style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
                windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            except Exception:
                pass
        # State
        self.primary_op = _clamp(primary_op, 0.0, 1.0); self.secondary_op = _clamp(secondary_op, 0.0, 1.0)
        self.text = text or ""; self.text_color = QColor(text_color) if not isinstance(text_color, QColor) else text_color
        self.overlay_font = QFont(font) if isinstance(font, QFont) else QFont(str(font) if font else "Segoe UI")
        self.text_scale_pct = int(text_scale_pct); self.fx_mode = fx_mode; self.fx_intensity = int(fx_intensity)
        self.flash_interval_ms = max(50, int(flash_interval_ms) if flash_interval_ms else 1500)
        self.flash_width_ms = max(10, int(flash_width_ms) if flash_width_ms else 200)
        self.start_time = time.time()
        # Readers
        self._primary = _VideoReader(primary_path); self._secondary = _VideoReader(secondary_path)
        # Timer
        self._timer = QTimer(self); self._timer.timeout.connect(self._on_tick); self._timer.start(16)
        self.showFullScreen(); self.show()

    def _flash_on(self, ms: int) -> bool:
        return (ms % self.flash_interval_ms) < self.flash_width_ms

    def _on_tick(self):
        if not self._shutting_down:
            self.update()

    def paintEvent(self, event):  # type: ignore[override]
        if self._shutting_down:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.TextAntialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        now = time.monotonic(); size = self.size()
        pix2 = self._secondary.read_if_due(now, size)
        if pix2 and self.secondary_op > 0.0:
            p.setOpacity(self.secondary_op); self._draw_center_cover(p, pix2, size)
        pix1 = self._primary.read_if_due(now, size)
        if pix1 and self.primary_op > 0.0:
            p.setOpacity(self.primary_op); self._draw_center_cover(p, pix1, size)
        if self.text:
            ms = int((time.time() - self.start_time) * 1000.0)
            if self._flash_on(ms):
                p.setOpacity(_clamp(self.primary_op + 0.02, 0.0, 1.0))
                f = QFont(self.overlay_font); f.setPixelSize(max(12, int(self.height() * (self.text_scale_pct / 100.0))))
                p.setFont(f); p.setPen(QColor(self.text_color)); rect = self.rect()
                if self.fx_mode.lower().startswith("breath"):
                    t = (ms % 4000) / 4000.0; depth = (self.fx_intensity / 100.0) * 0.02
                    scale = 1.0 + (depth * (0.5 - abs(t - 0.5)) * 2.0)
                    p.save(); p.translate(rect.center()); p.scale(scale, scale); p.translate(-rect.center())
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text); p.restore()
                else:
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()

    def _draw_center_cover(self, p: QPainter, pix: QPixmap, target_size: QSize):
        tw, th = target_size.width(), target_size.height(); pw, ph = pix.width(), pix.height()
        x = (tw - pw) // 2; y = (th - ph) // 2; p.drawPixmap(QRect(x, y, pw, ph), pix)

    def shutdown(self):
        self._shutting_down = True
        try:
            if getattr(self, '_timer', None):
                self._timer.stop()
                try: self._timer.deleteLater()
                except Exception: pass
        except Exception: pass
        for attr in ('_primary', '_secondary'):
            try:
                reader = getattr(self, attr, None); cap = getattr(reader, 'cap', None)
                if cap:
                    try: cap.release()
                    except Exception: pass
                if reader is not None: setattr(reader, 'cap', None)
            except Exception: pass
        try: self.hide()
        except Exception: pass
        try: self.deleteLater()
        except Exception: pass
