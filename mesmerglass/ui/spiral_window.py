"""Top-level spiral window container that hosts the Loom Compositor.

Some environments (notably certain Windows driver / Qt combinations) fail to
create a valid OpenGL context when a raw QOpenGLWidget is used directly as a
top-level transparent, always-on-top window. Wrapping the compositor inside a
plain QWidget (or QMainWindow) often resolves this because Qt can create the
native window first, then set up the child GL surface.

This wrapper exposes a minimal facade so existing launcher logic can treat it
similar to the compositor: .set_uniforms_from_director(), .request_draw(),
and .set_active(). Availability is proxied from the inner compositor.
"""
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt
import os
from typing import Any
import logging

try:
    from ..mesmerloom.compositor import Compositor as LoomCompositor
    logging.getLogger(__name__).info("[spiral.trace] LoomCompositor import succeeded in spiral_window.py")
except Exception as e:
    logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor import failed in spiral_window.py: {e}")
    LoomCompositor = None  # type: ignore


class SpiralWindow(QWidget):  # pragma: no cover - runtime/UI centric
    def __init__(self, director, parent=None):
        super().__init__(parent)
        # Optional debug surface mode disables translucency & click-through (can help some drivers)
        self._debug_surface = bool(os.environ.get("MESMERGLASS_SPIRAL_DEBUG_SURFACE"))
        if not self._debug_surface:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            logging.getLogger(__name__).warning("SpiralWindow: MESMERGLASS_SPIRAL_DEBUG_SURFACE enabled (no translucency/click-through)")
        self.setObjectName("SpiralWindow")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self._glwindow_attempted = False
        # Restore main compositor as child widget
        try:
            from ..mesmerloom.compositor import Compositor as LoomCompositor
            self.showFullScreen()  # Make SpiralWindow itself fullscreen/top-level
            comp = LoomCompositor(director, parent=self)
            comp.resize(self.width(), self.height())
            comp.show()
            comp.raise_()
            comp.update()  # Force GL context creation
            logging.getLogger(__name__).info("SpiralWindow: forced showFullScreen, LoomCompositor show/raise/update for GL context")
            self.comp = comp  # redirect facade
            # QTimer to force delayed update
            from PyQt6.QtCore import QTimer
            def _delayed_update():
                self.comp.update()
                logging.getLogger(__name__).info("SpiralWindow: QTimer forced comp.update() (delayed)")
            QTimer.singleShot(100, _delayed_update)
        except Exception as e:
            logging.getLogger(__name__).error("SpiralWindow: LoomCompositor creation failed: %s", e)

    # Facade methods -------------------------------------------------
    def set_active(self, active: bool):
        if self.comp and hasattr(self.comp, 'set_active'):
            try: self.comp.set_active(active)
            except Exception: pass

    def set_uniforms_from_director(self, uniforms: dict[str, Any]):
        if self.comp and hasattr(self.comp, 'set_uniforms_from_director'):
            try: self.comp.set_uniforms_from_director(uniforms)
            except Exception: pass

    def request_draw(self):
        if self.comp and hasattr(self.comp, 'request_draw'):
            try: self.comp.request_draw()
            except Exception: pass

    # Properties -----------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(getattr(self.comp, 'available', False))

    @property
    def _initialized(self) -> bool:  # used by probe logs
        return bool(getattr(self.comp, '_initialized', False))

    @property
    def _program(self):  # used by probe logs
        return getattr(self.comp, '_program', None)

    # ---------------- CPU fallback spiral (very simple) ----------------
    def _enable_cpu_fallback(self):
        if getattr(self, '_cpu_fallback_active', False):
            return
        self._cpu_fallback_active = True
        # Hide GL compositor widget if present
        try:
            if self.comp:
                self.comp.hide()
        except Exception:
            pass
        # Simple animation timer to rotate spiral subtly
        try:
            from PyQt6.QtCore import QTimer as _QT
            self._cpu_anim_phase = 0.0
            def _anim():
                self._cpu_anim_phase = (self._cpu_anim_phase + 0.07) % (3.14159*2)
                try: self.update()
                except Exception: pass
            self._cpu_timer = _QT(self); self._cpu_timer.timeout.connect(_anim); self._cpu_timer.start(50)
        except Exception:
            pass
        self.update()

    def paintEvent(self, ev):  # pragma: no cover
        # If fallback active, draw a very simple spiral approximation
        if getattr(self, '_cpu_fallback_active', False):
            from PyQt6.QtGui import QPainter, QPen, QColor
            import math
            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                w,h = self.width(), self.height()
                cx, cy = w/2.0, h/2.0
                arms = 4
                base_color = QColor(120, 230, 200, 180)
                pen = QPen(base_color); pen.setWidth(2)
                p.setPen(pen)
                turns = 6
                max_r = min(w,h)/2.3
                steps = 1000
                phase = float(getattr(self, '_cpu_anim_phase', 0.0))
                for a in range(arms):
                    prev = None
                    arm_phase = phase + a * 2*math.pi/arms
                    for i in range(steps):
                        t = i/steps * turns * 2*math.pi
                        r = (i/steps) * max_r
                        theta = t + arm_phase
                        x = int(cx + math.cos(theta)*r)
                        y = int(cy + math.sin(theta)*r)
                        if prev is not None:
                            p.drawLine(prev[0], prev[1], x, y)
                        prev = (x,y)
                # Overlay hint text
                p.setPen(QPen(QColor(255,255,255,220)))
                p.drawText(16, 28, "Spiral (CPU Fallback)")
                p.setPen(QPen(QColor(255,255,255,160)))
                p.drawText(16, 46, "OpenGL context not created")
            finally:
                p.end()
            return
        # Else default QWidget paint (do nothing); GL child will handle its own paint
        return super().paintEvent(ev)

    # Event logging -------------------------------------------------
    def showEvent(self, ev):  # pragma: no cover
        try:
            logging.getLogger(__name__).info(
                "SpiralWindow showEvent (fullscreen) size=%dx%d comp_init=%s avail=%s", self.width(), self.height(), getattr(self.comp,'_initialized',None), getattr(self.comp,'available',None)
            )
            # Force child LoomCompositor to match parent geometry
            if hasattr(self, 'comp') and self.comp:
                self.comp.setGeometry(self.geometry())
                self.comp.resize(self.width(), self.height())
                logging.getLogger(__name__).info(
                    "SpiralWindow showEvent: forced comp geometry to %s size=%s", self.comp.geometry(), self.comp.size()
                )
        except Exception as e:
            logging.getLogger(__name__).warning(f"SpiralWindow showEvent: error forcing comp geometry: {e}")
        return super().showEvent(ev)

    def resizeEvent(self, ev):  # pragma: no cover
        try:
            logging.getLogger(__name__).debug(
                "SpiralWindow resizeEvent size=%dx%d comp_init=%s", self.width(), self.height(), getattr(self.comp,'_initialized',None)
            )
            # Force child SpiralSimpleGL to match parent geometry
            if hasattr(self, 'comp') and self.comp:
                self.comp.setGeometry(self.geometry())
                self.comp.resize(self.width(), self.height())
                logging.getLogger(__name__).debug(
                    "SpiralWindow resizeEvent: forced comp geometry to %s size=%s", self.comp.geometry(), self.comp.size()
                )
        except Exception as e:
            logging.getLogger(__name__).warning(f"SpiralWindow resizeEvent: error forcing comp geometry: {e}")
        return super().resizeEvent(ev)
