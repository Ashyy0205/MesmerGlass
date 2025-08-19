import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRect, QSize
from PyQt6.QtGui import QPainter, QPixmap, QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import QWidget
import logging  # add logging

# --- Optional Windows click-through fallback ---
try:
    import ctypes, sys
    _IS_WIN = sys.platform.startswith("win")
except Exception:
    _IS_WIN = False


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ------------------------
# Lightweight video reader
# ------------------------
class _VideoReader:
    """
    Minimal throttled reader around OpenCV. If OpenCV is missing or file is None,
    it just yields None frames (overlay still runs, only text shows).
    """
    def __init__(self, path: Optional[str]):
        self.path = path or ""
        self.cap = None
        self.fps = 30.0
        self._frame_period = 1.0 / self.fps
        self._last_grab_t = 0.0
        self._last_pix = None

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
                self._frame_period = 1.0 / float(self.fps)
                logging.getLogger(__name__).info("[video] opened %s @ %.2f fps", self.path, self.fps)
            else:
                logging.getLogger(__name__).warning("[video] failed to open: %s", self.path)
        except Exception as e:
            self.cv2 = None
            logging.getLogger(__name__).warning("[video] OpenCV not available: %s", e)

    def read_if_due(self, now: float, target_size: QSize) -> Optional[QPixmap]:
        """Advance only when enough time has elapsed; otherwise reuse last frame."""
        # If no capture, no frame; keep last_pix (could be None)
        if self.cap is None:
            return self._last_pix

        if (now - self._last_grab_t) < self._frame_period and self._last_pix is not None:
            return self._last_pix

        # Pull next frame
        ok, frame = self.cap.read()
        if not ok:
            # loop for simple hypnotic background; seek to start
            try:
                self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
            except Exception:
                ok = False
        if not ok:
            return self._last_pix

        # Convert BGR->RGB, resize to fit edge while preserving aspect
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        if w <= 0 or h <= 0:
            return self._last_pix

        # Scale to cover (letterbox-free)
        target_w, target_h = target_size.width(), target_size.height()
        if target_w <= 0 or target_h <= 0:
            return self._last_pix

        scale = max(target_w / w, target_h / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        resized = self.cv2.resize(rgb, (new_w, new_h), interpolation=self.cv2.INTER_AREA)

        # Convert to QPixmap
        from PyQt6.QtGui import QImage
        qimg = QImage(resized.data, new_w, new_h, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)

        self._last_pix = pix
        self._last_grab_t = now
        return self._last_pix


# -------------------
# Overlay window (UI)
# -------------------
class OverlayWindow(QWidget):
    """
    Full-screen, transparent, always-on-top overlay per screen.
    Draw order: secondary video (if any) -> primary video -> flash text on top.

    Flash timing is based on self.start_time, flash_interval_ms and flash_width_ms.
    Launcher also reads start_time for device buzz sync.
    """

    def __init__(
        self,
        screen,                         # QScreen
        primary_path: Optional[str],
        secondary_path: Optional[str],
        primary_op: float,
        secondary_op: float,
        text: str,
        text_color: QColor,
        font: QFont | str,
        text_scale_pct: int,
        flash_interval_ms: int,
        flash_width_ms: int,
        fx_mode: str,
        fx_intensity: int,
    ):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Place on the target screen, borderless and fill
        geo = screen.geometry()
        self.setGeometry(geo)

        # Windows click-through fallback (in case Qt flag isn't honored)
        if _IS_WIN:
            try:
                from ctypes import windll, wintypes
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_TOOLWINDOW = 0x00000080
                hwnd = int(self.winId())
                style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
                windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            except Exception:
                pass

        # State
        self.primary_op = _clamp(primary_op, 0.0, 1.0)
        self.secondary_op = _clamp(secondary_op, 0.0, 1.0)
        self.text = text or ""
        self.text_color = QColor(text_color) if not isinstance(text_color, QColor) else text_color
        self.font = QFont(font) if isinstance(font, QFont) else QFont(str(font) if font else "Segoe UI")
        self.text_scale_pct = int(text_scale_pct)
        self.fx_mode = fx_mode
        self.fx_intensity = int(fx_intensity)

        self.flash_interval_ms = max(50, int(flash_interval_ms) if flash_interval_ms else 1500)
        self.flash_width_ms = max(10, int(flash_width_ms) if flash_width_ms else 200)

        self.start_time = time.time()  # used by both overlay + launcher device sync

        # Readers (throttled to FPS)
        self._primary = _VideoReader(primary_path)
        self._secondary = _VideoReader(secondary_path)

        # Frame timer ~ every 16ms; actual frame stepping is throttled per reader FPS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(16)  # ~60Hz UI tick; readers decide when to advance

        self.showFullScreen()
        self.show()

    # ------------- timing/flash helpers -------------
    def _now(self) -> float:
        return time.monotonic()

    def _flash_on(self, now_ms: int) -> bool:
        return (now_ms % self.flash_interval_ms) < self.flash_width_ms

    # ------------- frame update & paint -------------
    def _on_tick(self):
        # Ask for repaint; readers will only advance if due
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Composite order: secondary -> primary -> text
        now = self._now()
        size = self.size()

        # Secondary
        pix2 = self._secondary.read_if_due(now, size)
        if pix2 and self.secondary_op > 0.0:
            p.setOpacity(_clamp(self.secondary_op, 0.0, 1.0))
            self._draw_center_cover(p, pix2, size)

        # Primary
        pix1 = self._primary.read_if_due(now, size)
        if pix1 and self.primary_op > 0.0:
            p.setOpacity(_clamp(self.primary_op, 0.0, 1.0))
            self._draw_center_cover(p, pix1, size)

        # Flash text on top
        if self.text:
            now_ms = int((time.time() - self.start_time) * 1000.0)
            show = self._flash_on(now_ms)
            if show:
                # Text opacity = primary opacity + 2% (clamped)
                text_op = _clamp(self.primary_op + 0.02, 0.0, 1.0)
                p.setOpacity(text_op)

                # Build font sized to screen height
                f = QFont(self.font)
                px = max(12, int(self.height() * (self.text_scale_pct / 100.0)))
                f.setPixelSize(px)
                p.setFont(f)

                # No outline; pure fill using text_color
                color = QColor(self.text_color)
                p.setPen(color)

                rect = self.rect()
                # Simple FX: subtle sway/scale if requested
                if self.fx_mode.lower().startswith("breath"):
                    t = (now_ms % 4000) / 4000.0
                    # scale between 0.98..1.02 by intensity
                    depth = (self.fx_intensity / 100.0) * 0.02
                    scale = 1.0 + (depth * (0.5 - abs(t - 0.5)) * 2.0)  # triangle wave
                    p.save()
                    p.translate(rect.center())
                    p.scale(scale, scale)
                    p.translate(-rect.center())
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
                    p.restore()
                else:
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)

        p.end()

    def _draw_center_cover(self, p: QPainter, pix: QPixmap, target_size: QSize):
        """Draw pixmap centered and covering the target rect (already resized)."""
        tw, th = target_size.width(), target_size.height()
        pw, ph = pix.width(), pix.height()

        x = (tw - pw) // 2
        y = (th - ph) // 2
        p.drawPixmap(QRect(x, y, pw, ph), pix)
