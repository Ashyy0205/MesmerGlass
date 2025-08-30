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
    from ..mesmerloom.compositor import LoomCompositor
    logging.getLogger(__name__).info("[spiral.trace] LoomCompositor import succeeded in spiral_window.py")
except Exception as e:
    logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor import failed in spiral_window.py: {e}")
    LoomCompositor = None  # type: ignore


class SpiralWindow(QWidget):  # pragma: no cover - runtime/UI centric
    def __init__(self, director, parent=None, screen_index=0):
        # --- SpiralWindow diagnostics: compositor/screen assignment ---
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QGuiApplication
            screens = QApplication.screens()
            screen = screens[screen_index] if 0 <= screen_index < len(screens) else screens[0]
            logging.getLogger(__name__).info(f"[spiral.trace] SpiralWindow: LoomCompositor will be attached to screen={screen.name()} index={screen_index} geometry={screen.geometry()} size={screen.geometry().size()}")
            logging.getLogger(__name__).info("[spiral.trace] Available screens:")
            for idx, sc in enumerate(QGuiApplication.screens()):
                logging.getLogger(__name__).info(f"  Screen {idx}: name={sc.name()} geometry={sc.geometry()}")
            logging.getLogger(__name__).info(f"[spiral.trace] Assigned to screen index {screen_index}: {screen.name()} ({screen.geometry()})")
            logging.getLogger(__name__).info(f"[spiral.trace] Post-assignment: screen={screen.name()} geometry={self.geometry()} pos={self.pos()} size={self.size()}")
            # Fallback: forcibly move window if not on target screen
            if self.screen() != screen:
                logging.getLogger(__name__).warning(f"[spiral.trace] Fallback: forced geometry to {screen.geometry()}")
                self.setGeometry(screen.geometry())
            # DPI and availableGeometry
            try:
                dpi = screen.logicalDotsPerInch()
                avail = screen.availableGeometry()
                logging.getLogger(__name__).info(f"[spiral.trace] DPI={dpi} availableGeometry={avail}")
            except Exception as e:
                logging.getLogger(__name__).warning(f"[spiral.trace] DPI/availableGeometry error: {e}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] SpiralWindow: error logging LoomCompositor/screen assignment: {e}")
        super().__init__(parent)
        # Diagnostic: log SpiralWindow creation and window info
        logging.getLogger(__name__).info(f"[spiral.trace] SpiralWindow.__init__: screen_index={screen_index} parent={parent} winId={self.winId()} windowFlags={self.windowFlags():#x}")
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
        # Forced QScreen assignment
        try:
            from PyQt6.QtWidgets import QApplication
            screens = QApplication.screens()
            logging.getLogger(__name__).info(f"[spiral.trace] Available screens:")
            for idx, screen in enumerate(screens):
                logging.getLogger(__name__).info(f"  Screen {idx}: name={screen.name()} geometry={screen.geometry()}")
            if 0 <= screen_index < len(screens):
                self.setScreen(screens[screen_index])
                logging.getLogger(__name__).info(f"[spiral.trace] Assigned to screen index {screen_index}: {screens[screen_index].name()} ({screens[screen_index].geometry()})")
                # Log after assignment
                assigned_screen = self.screen() if hasattr(self, 'screen') else None
                assigned_name = assigned_screen.name() if assigned_screen else None
                logging.getLogger(__name__).info(f"[spiral.trace] Post-assignment: screen={assigned_name} geometry={self.geometry()} pos={self.pos()} size={self.size()}")
                # Fallback: force geometry to match screen if not fullscreen
                try:
                    geom = screens[screen_index].geometry()
                    self.setGeometry(geom)
                    logging.getLogger(__name__).info(f"[spiral.trace] Fallback: forced geometry to {geom}")
                    dpi = screens[screen_index].logicalDotsPerInch()
                    avail_geom = screens[screen_index].availableGeometry()
                    logging.getLogger(__name__).info(f"[spiral.trace] DPI={dpi} availableGeometry={avail_geom}")
                except Exception as e:
                    logging.getLogger(__name__).warning(f"[spiral.trace] Fallback geometry/DPI error: {e}")
            else:
                logging.getLogger(__name__).warning(f"[spiral.trace] Invalid screen_index {screen_index}, defaulting to primary.")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] Error assigning QScreen: {e}")
        # Diagnostic: log screen assignment and geometry
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            screen_name = screen.name() if screen else None
            logging.getLogger(__name__).info(
                f"[spiral.trace] SpiralWindow.__init__: screen={screen_name} geometry={self.geometry()} pos={self.pos()} size={self.size()}"
            )
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] SpiralWindow.__init__: error logging screen info: {e}")
        # Restore main compositor as child widget
        try:
            from ..mesmerloom.compositor import LoomCompositor
            self.showFullScreen()  # Make SpiralWindow itself fullscreen/top-level
            self.raise_()
            self.activateWindow()
            # Log after showFullScreen
            assigned_screen = self.screen() if hasattr(self, 'screen') else None
            assigned_name = assigned_screen.name() if assigned_screen else None
            logging.getLogger(__name__).info(f"[spiral.trace] After showFullScreen: screen={assigned_name} geometry={self.geometry()} pos={self.pos()} size={self.size()}")
            self.comp = LoomCompositor(director, parent=self)
            lay.addWidget(self.comp)  # Layout will always fit the compositor
            self.comp.show()
            self.comp.raise_()
            self.comp.activateWindow()
            self.comp.update()  # Force GL context creation
            logging.getLogger(__name__).info("SpiralWindow: LoomCompositor attached to layout and shown")
            # Diagnostic: log widget visibility and GL context
            logging.getLogger(__name__).info(f"[spiral.trace] SpiralWindow visible={self.isVisible()} comp visible={self.comp.isVisible()} comp geometry={self.comp.geometry()} size={self.comp.size()}")
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
    def showEvent(self, event):  # pragma: no cover
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            screen_name = screen.name() if screen else None
            logging.getLogger(__name__).info(
                f"[spiral.trace] SpiralWindow.showEvent: screen={screen_name} geometry={self.geometry()} pos={self.pos()} size={self.size()} comp_init={getattr(self.comp,'_initialized',None)} avail={getattr(self.comp,'available',None)}"
            )
            # No manual sizing needed; layout will fit the compositor
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] SpiralWindow.showEvent: error forcing comp geometry: {e}")
        return super().showEvent(event)

    def resizeEvent(self, event):  # pragma: no cover
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            screen_name = screen.name() if screen else None
            logging.getLogger(__name__).info(
                f"[spiral.trace] SpiralWindow.resizeEvent: screen={screen_name} geometry={self.geometry()} pos={self.pos()} size={self.size()} comp_init={getattr(self.comp,'_initialized',None)}"
            )
            # No manual sizing needed; layout will fit the compositor
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] SpiralWindow.resizeEvent: error forcing comp geometry: {e}")
        return super().resizeEvent(event)
