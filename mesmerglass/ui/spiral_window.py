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
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt
import os
from typing import Any
import logging

# FORCE QOpenGLWidget compositor (QOpenGLWindow doesn't display on some Windows systems)
# Check for environment variable override
_FORCE_WIDGET_COMPOSITOR = os.environ.get("MESMERGLASS_FORCE_WIDGET_COMPOSITOR", "1") == "1"

if _FORCE_WIDGET_COMPOSITOR:
    # Use QOpenGLWidget compositor (more compatible with Windows desktop composition)
    try:
        from ..mesmerloom.compositor import LoomCompositor
        logging.getLogger(__name__).info("[spiral.trace] LoomCompositor (QOpenGLWidget) selected - better Windows compatibility")
        _USE_WINDOW_COMPOSITOR = False
    except Exception as e:
        logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor import failed: {e}")
        # Fallback to QOpenGLWindow
        from ..mesmerloom.window_compositor import LoomWindowCompositor
        logging.getLogger(__name__).info("[spiral.trace] LoomWindowCompositor fallback import succeeded")
        _USE_WINDOW_COMPOSITOR = True
else:
    # Try QOpenGLWindow compositor first (artifact-free but may not display on some systems)
    try:
        from ..mesmerloom.window_compositor import LoomWindowCompositor
        logging.getLogger(__name__).info("[spiral.trace] LoomWindowCompositor import succeeded in spiral_window.py")
        _USE_WINDOW_COMPOSITOR = True
    except ImportError:
        # Fallback to QOpenGLWidget compositor
        try:
            from ..mesmerloom.compositor import LoomCompositor
            logging.getLogger(__name__).info("[spiral.trace] LoomCompositor fallback import succeeded in spiral_window.py")
            _USE_WINDOW_COMPOSITOR = False
        except Exception as e:
            logging.getLogger(__name__).error(f"[spiral.trace] All compositor imports failed in spiral_window.py: {e}")
            LoomCompositor = None  # type: ignore
            _USE_WINDOW_COMPOSITOR = False


class SpiralWindow(QWidget):  # pragma: no cover - runtime/UI centric
    def __init__(self, director, parent=None, screen_index=0, defer_timer=False):
        super().__init__(parent)
        logger = logging.getLogger(__name__)
        self._defer_timer = defer_timer  # Store for compositor initialization
        
        # Get target screen
        try:
            from PyQt6.QtWidgets import QApplication
            screens = QApplication.screens()
            screen = screens[screen_index] if 0 <= screen_index < len(screens) else screens[0]
            logger.debug(f"SpiralWindow targeting screen {screen_index}: {screen.name()}")
        except Exception as e:
            logger.warning(f"Screen assignment error: {e}")
        # Optional debug surface mode disables translucency & click-through (can help some drivers)
        self._debug_surface = bool(os.environ.get("MESMERGLASS_SPIRAL_DEBUG_SURFACE"))
        if not self._debug_surface:
            # Keep wrapper non-interactive and transparent if it ever becomes visible
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        else:
            logging.getLogger(__name__).warning("SpiralWindow: MESMERGLASS_SPIRAL_DEBUG_SURFACE enabled (no translucency/click-through)")
        self.setObjectName("SpiralWindow")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self._glwindow_attempted = False
        self._using_qglwindow = bool(_USE_WINDOW_COMPOSITOR)
        
        # Assign to target screen
        try:
            from PyQt6.QtWidgets import QApplication
            screens = QApplication.screens()
            if 0 <= screen_index < len(screens):
                self.setScreen(screens[screen_index])
                self.setGeometry(screens[screen_index].geometry())
                logger.debug(f"Assigned to screen {screen_index}: {screens[screen_index].name()}")
        except Exception as e:
            logger.debug(f"Screen assignment error: {e}")
        # Restore main compositor as child widget or window
        try:
            # For QOpenGLWindow path we DO NOT show this QWidget wrapper; keep it off-screen/hidden
            _wrapper_visible = False
            if not _USE_WINDOW_COMPOSITOR:
                _wrapper_visible = True
            if _wrapper_visible:
                self.showFullScreen()  # Make SpiralWindow itself fullscreen/top-level (fallback path only)
                self.raise_()
                self.activateWindow()
            # Log after showFullScreen
            assigned_screen = self.screen() if hasattr(self, 'screen') else None
            assigned_name = assigned_screen.name() if assigned_screen else None
            logging.getLogger(__name__).info(f"[spiral.trace] After showFullScreen: screen={assigned_name} geometry={self.geometry()} pos={self.pos()} size={self.size()}")
            
            if _USE_WINDOW_COMPOSITOR:
                # Ensure this wrapper never shows as a black/opaque window
                try:
                    self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                    self.hide()
                except Exception:
                    pass
                # Use QOpenGLWindow compositor (artifact-free)
                self.comp = LoomWindowCompositor(director)
                
                # CRITICAL: If deferring timer, set flag BEFORE initializeGL is called
                if self._defer_timer:
                    self.comp._defer_timer_start = True
                    logging.getLogger(__name__).info("[spiral.trace] Set _defer_timer_start flag on LoomWindowCompositor")

                # IMPORTANT: Do NOT reset flags here; LoomWindowCompositor has already set
                # the correct flags and applying setFlags again may recreate the native
                # window, dropping layered styles before first show and causing a black flash.
                # If needed in future, re-apply styles immediately after any flag changes.

                # Re-assert layered styles and keep alpha at 0 before first show to avoid black
                try:
                    if hasattr(self.comp, '_apply_win32_layered_styles'):
                        self.comp._apply_win32_layered_styles()
                    if hasattr(self.comp, '_set_layered_alpha'):
                        self.comp._set_layered_alpha(0)
                except Exception:
                    pass

                # Delay first show slightly so layered styles/alpha settle, then show and position
                from PyQt6.QtCore import QTimer, Qt as QtCore_Qt
                def _show_and_position():
                    try:
                        # Get target screen geometry FIRST
                        screens = QApplication.screens()
                        if 0 <= screen_index < len(screens):
                            target_screen = screens[screen_index]
                            target_geometry = target_screen.geometry()
                            
                            # CRITICAL: Set screen, geometry, and window state BEFORE showing
                            self.comp.setScreen(target_screen)
                            self.comp.setGeometry(target_geometry)
                            
                            # Use setWindowState instead of showFullScreen (more reliable on Windows)
                            self.comp.setWindowState(QtCore_Qt.WindowState.WindowFullScreen)
                            
                            logging.getLogger(__name__).info(f"[spiral.debug] QOpenGLWindow screen={target_screen.name()} geometry={target_geometry}")
                        else:
                            logging.getLogger(__name__).warning(f"[spiral.debug] Invalid screen_index {screen_index}, using default")
                            # Fallback to primary screen
                            target_screen = screens[0] if screens else None
                            if target_screen:
                                target_geometry = target_screen.geometry()
                                self.comp.setScreen(target_screen)
                                self.comp.setGeometry(target_geometry)
                                self.comp.setWindowState(QtCore_Qt.WindowState.WindowFullScreen)
                        
                        # NOW show the window (geometry already set)
                        self.comp.show()

                        # Force window to top immediately after showing
                        self.comp.raise_()
                        self.comp.requestActivate()  # QWindow method for activation

                        # Use Windows API for stronger topmost behavior
                        if hasattr(self.comp, '_force_topmost_windows'):
                            self.comp._force_topmost_windows()

                        self.comp.raise_()

                        # Present an all-transparent frame immediately after positioning
                        if hasattr(self.comp, '_initial_transparent_swap'):
                            self.comp._initial_transparent_swap()
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"[spiral.trace] _show_and_position failed: {e}")

                # Configurable initial show delay to avoid first black compose
                try:
                    delay_ms = int(os.environ.get("MESMERGLASS_FIRST_SHOW_DELAY_MS", "25"))
                except Exception:
                    delay_ms = 25
                QTimer.singleShot(delay_ms, _show_and_position)
                
                logging.getLogger(__name__).info("SpiralWindow: LoomWindowCompositor created as separate window (artifact-free)")
                
                # CRITICAL: Add delayed activation to ensure window appears on top
                from PyQt6.QtCore import QTimer
                def _ensure_top_window():
                    """Ensure window stays on top after a short delay"""
                    try:
                        self.comp.raise_()
                        self.comp.requestActivate()
                        # Use Windows API for stronger control
                        if hasattr(self.comp, '_force_topmost_windows'):
                            self.comp._force_topmost_windows()
                        logging.getLogger(__name__).info("[spiral.trace] Delayed window activation completed")
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"[spiral.trace] Delayed window activation failed: {e}")
                
                QTimer.singleShot(50, _ensure_top_window)  # Activate after 50ms
                QTimer.singleShot(200, _ensure_top_window)  # Activate again after 200ms for stubborn cases
                
                logging.getLogger(__name__).info(f"[spiral.debug] QOpenGLWindow geometry after setup: {self.comp.geometry()}")
                comp_screen = self.comp.screen()
                comp_screen_name = comp_screen.name() if comp_screen else 'None'
                logging.getLogger(__name__).info(f"[spiral.debug] QOpenGLWindow screen: {comp_screen_name}")
                logging.getLogger(__name__).info(f"[spiral.debug] Parent SpiralWindow geometry: {self.geometry()}")
                parent_screen = self.screen()
                parent_screen_name = parent_screen.name() if parent_screen else 'None'
                logging.getLogger(__name__).info(f"[spiral.debug] Parent SpiralWindow screen: {parent_screen_name}")
            else:
                # Fallback to QOpenGLWidget compositor (has FBO artifacts)
                from ..mesmerloom.compositor import LoomCompositor
                self.comp = LoomCompositor(director, parent=self)
                
                # CRITICAL: Set defer flag BEFORE adding to layout (which triggers initializeGL)
                if self._defer_timer:
                    self.comp._defer_timer_start = True
                    logging.getLogger(__name__).info("[spiral.trace] Set _defer_timer_start flag on LoomCompositor BEFORE addWidget")
                
                lay.addWidget(self.comp)  # Layout will always fit the compositor (triggers initializeGL)
                self.comp.show()
                self.comp.raise_()
                self.comp.activateWindow()
                logging.getLogger(__name__).info("SpiralWindow: LoomCompositor attached to layout (fallback - has FBO artifacts)")
            
            # CRITICAL: Skip initial update if deferring timer (complete silence until Launch)
            if not self._defer_timer:
                self.comp.update()  # Force GL context creation
                logging.getLogger(__name__).info("SpiralWindow: Initial comp.update() called")
            else:
                logging.getLogger(__name__).info("SpiralWindow: Skipped initial comp.update() (deferred until Launch)")
            
            # Diagnostic: log widget visibility and GL context
            if hasattr(self.comp, 'geometry'):
                logging.getLogger(__name__).info(f"[spiral.trace] SpiralWindow visible={self.isVisible()} comp visible={self.comp.isVisible()} comp geometry={self.comp.geometry()} size={self.comp.size()}")
            else:
                logging.getLogger(__name__).info(f"[spiral.trace] SpiralWindow visible={self.isVisible()} comp visible=True (QOpenGLWindow)")
                
            # CRITICAL: Skip delayed update if deferring timer (complete silence until Launch)
            if not self._defer_timer:
                # QTimer to force delayed update
                from PyQt6.QtCore import QTimer
                def _delayed_update():
                    self.comp.update()
                    logging.getLogger(__name__).info("SpiralWindow: QTimer forced comp.update() (delayed)")
                QTimer.singleShot(100, _delayed_update)
                logging.getLogger(__name__).info("SpiralWindow: Scheduled delayed comp.update()")
            else:
                logging.getLogger(__name__).info("SpiralWindow: Skipped delayed comp.update() (deferred until Launch)")
        except Exception as e:
            logging.getLogger(__name__).error("SpiralWindow: Compositor creation failed: %s", e)

    # Ensure launcher calls to show/raise/activate do not surface the wrapper when using QOpenGLWindow
    def showFullScreen(self):  # type: ignore[override]
        if getattr(self, '_using_qglwindow', False):
            try:
                if hasattr(self, 'comp'):
                    self.comp.showFullScreen()
                    self.comp.raise_()
                    if hasattr(self.comp, 'requestActivate'):
                        self.comp.requestActivate()
            except Exception:
                pass
            return
        return super().showFullScreen()

    def raise_(self):  # type: ignore[override]
        if getattr(self, '_using_qglwindow', False):
            try:
                if hasattr(self, 'comp'):
                    self.comp.raise_()
                    if hasattr(self.comp, 'requestActivate'):
                        self.comp.requestActivate()
            except Exception:
                pass
            return
        return super().raise_()

    def activateWindow(self):  # type: ignore[override]
        if getattr(self, '_using_qglwindow', False):
            try:
                if hasattr(self, 'comp') and hasattr(self.comp, 'requestActivate'):
                    self.comp.requestActivate()
            except Exception:
                pass
            return
        return super().activateWindow()

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
