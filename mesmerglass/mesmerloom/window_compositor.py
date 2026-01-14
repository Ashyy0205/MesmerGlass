"""
MesmerLoom QOpenGLWindow-based compositor.
Eliminates Qt widget FBO blit artifacts by using direct window rendering.
"""

import logging
import time
import os
import sys
from collections import deque
from typing import Any, Optional, Dict, Union, Tuple
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtOpenGL import QOpenGLWindow, QOpenGLBuffer, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PyQt6.QtGui import QSurfaceFormat, QColor, QGuiApplication, QOpenGLContext, QScreen
from OpenGL import GL
import numpy as np
from mesmerglass.logging_utils import BurstSampler
from mesmerglass.engine.perf import perf_metrics

# Windows-specific imports for forcing window to top
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020
    except ImportError:
        ctypes = None

logger = logging.getLogger(__name__)

_FADE_CLEANUP_WARN_MS = 6.0
_FADE_LAYER_WARN_MS = 10.0
_BACKGROUND_RENDER_WARN_MS = 14.0
_VIDEO_UPLOAD_WARN_MS = 8.0

class LoomWindowCompositor(QOpenGLWindow):
    """
    QOpenGLWindow-based spiral compositor.
    Eliminates Qt widget FBO blit artifacts completely.
    """
    # Emit after a frame is drawn so duplicate/mirror windows can update
    frame_drawn = pyqtSignal()
    # Emit captured RGB frames when VR streaming capture is enabled
    frame_ready = pyqtSignal(object)

    def __init__(self, director, text_director=None, is_primary=True, parent=None):
        super().__init__(parent)
        self.director = director
        self.text_director = text_director
        self.is_primary = bool(is_primary)

        # Core rendering state
        self.program_id = None
        self.vao = None
        self.vbo = None
        self.ebo = None
        self.initialized = False
        self.frame_count = 0
        self.t0 = time.time()

        # Tracing and performance
        self._trace = bool(os.environ.get("MESMERGLASS_SPIRAL_TRACE"))
        self._log_interval = 60
        self._active = True
        self.available = False

        # Compositor frame pacing instrumentation
        self._last_paint_t: float | None = None

        # GPU instrumentation (best-effort, compositor-context based)
        self._gpu_timer_supported = False
        self._gpu_query_ids: list[int] = []
        self._gpu_query_next_idx: int = 0
        self._gpu_query_in_flight_idx: int | None = None
        # Pending completed queries waiting for results: (idx, ended_at_perf_counter)
        self._gpu_query_pending: deque[tuple[int, float]] = deque()
        self._gpu_vram_last_poll_t: float = 0.0
        # VR safe mirror settings (offscreen FBO tap)
        self._vr_safe = bool(os.environ.get("MESMERGLASS_VR_SAFE") in ("1", "true", "True"))
        self._vr_fbo = None
        self._vr_tex = None
        self._vr_size = (0, 0)

        # Background texture support (for Visual Programs)
        self._background_texture = None
        self._background_enabled = False
        self._background_zoom = 1.0
        # Render-time-only multiplier for background/video zoom.
        # This allows special compositors (e.g., VR streaming) to be slightly zoomed out
        # without affecting the primary compositor's zoom animations or upload state.
        self._background_zoom_multiplier = 1.0
        self._background_image_width = 1920
        self._background_image_height = 1080
        self._background_offset = [0.0, 0.0]  # XY drift offset
        self._background_kaleidoscope = False  # Kaleidoscope mirroring
        self._background_program = None  # Background shader program
        self._background_upload_count = 0
        self._last_background_error: Optional[str] = None
        self._last_background_render_frame = -1
        self._last_background_set_timestamp = 0.0

        # Fade transition support (for smooth image/video changes)
        self._fade_enabled = False
        self._fade_duration = 0.5
        self._fade_progress = 0.0
        self._fade_active = False
        self._fade_old_texture = None
        self._fade_old_zoom = 1.0
        self._fade_old_width = 1920
        self._fade_old_height = 1080
        self._fade_frame_start = 0

        # Multi-layer ghosting support (when fade duration > cycle time)
        self._fade_queue = []  # Queue of fading textures for ghosting effect

        # Zoom animation support (duration-based)
        self._zoom_animating = False
        self._zoom_current = 1.0
        self._zoom_target = 1.5  # Max zoom target
        self._zoom_start = 1.0
        self._zoom_duration_frames = 0
        self._zoom_elapsed_frames = 0
        self._zoom_start_time = time.time()  # Real time start (for consistent speed)
        self._zoom_enabled = True  # Can be disabled for video focus mode
        self._zoom_mode = "exponential"  # Zoom animation mode
        self._zoom_rate_default = 0.42
        self._zoom_rate = self._zoom_rate_default  # Zoom rate for exponential mode

        # Text rendering support
        self._text_opacity = 1.0  # Global text opacity multiplier
        self._text_textures: list[tuple[int, int, int, float, float, float, float]] = []
        self._text_program = None
        self._text_log_counter = 0
        self._virtual_screen_size: Optional[tuple[int, int]] = None
        self._text_texture_sampler = BurstSampler(interval_s=2.0)
        self._text_trace = bool(os.environ.get("MESMERGLASS_TEXT_TRACE"))
        self._fade_perf_sampler = BurstSampler(interval_s=1.5)
        self._fade_perf_next_log = 0.0
        self._fade_perf_last: Optional[dict[str, Any]] = None
        self._video_upload_sampler = BurstSampler(interval_s=1.5)
        self._video_upload_next_log = 0.0
        self._video_perf_last: Optional[dict[str, Any]] = None
        self._target_screen: Optional[QScreen] = None
        self._last_screen_geometry: Optional[tuple[int, int, int, int]] = None
        self._last_native_geometry: Optional[tuple[int, int, int, int]] = None
        self._last_physical_size: Optional[tuple[int, int]] = None
        # Frame capture flags. VR and Home preview are independent.
        self._vr_capture_enabled = False  # flipped on when VR streaming attaches
        self._preview_capture_enabled = False  # flipped on when Home preview is visible
        # Capture throttling (used by both GUI preview and VR streaming).
        self._capture_interval_s = 1.0 / 15.0
        self._capture_last_t = 0.0

        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        # Track first exposure to trigger an immediate styled repaint
        self._first_expose_handled = False
        # One-time guard for an initial transparent swap to avoid first black frame
        self._first_transparent_swap_done = False
        # Start fully transparent; restore after first transparent swap
        self._window_opacity = 1.0
        try:
            super().setOpacity(0.0)
        except Exception:
            pass

        # Set window properties for overlay behavior
        try:
            # WindowTransparentForInput may not exist on older Qt; guard it
            flags = (Qt.WindowType.FramelessWindowHint |
                     Qt.WindowType.WindowStaysOnTopHint |
                     Qt.WindowType.Tool |
                     Qt.WindowType.BypassWindowManagerHint)
            if hasattr(Qt.WindowType, "WindowTransparentForInput"):
                flags |= Qt.WindowType.WindowTransparentForInput  # default to click-through
            self.setFlags(flags)
        except Exception:
            # Fallback to basic flags
            try:
                self.setFlags(Qt.WindowType.FramelessWindowHint |
                              Qt.WindowType.WindowStaysOnTopHint |
                              Qt.WindowType.Tool)
            except Exception:
                pass

        # Establish a transparent base color for the QWindow backbuffer (enables per-pixel alpha)
        try:
            self.setColor(QColor(0, 0, 0, 0))  # Transparent window background
        except Exception:
            pass

        # Configure surface format for transparency support
        format = QSurfaceFormat()
        format.setVersion(3, 3)
        format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        format.setDepthBufferSize(24)
        format.setStencilBufferSize(8)
        format.setSamples(0)  # No MSAA to avoid artifacts
        format.setAlphaBufferSize(8)  # Enable alpha buffer for transparency
        format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        self.setFormat(format)

        # Ensure the native window is created so we can apply styles BEFORE first show/paint
        try:
            logger.info("[spiral.trace] Calling self.create() to force platform window creation...")
            self.create()  # force platform window creation (no show)
            # Check if isWindow() method exists before calling (Qt base class may not be ready)
            is_window = self.isWindow() if hasattr(self, 'isWindow') else "N/A"
            logger.info(f"[spiral.trace] Window created - winId: {self.winId()}, isWindow: {is_window}")
        except Exception as e:
            logger.error(f"[spiral.trace] Failed to create window: {e}")
        # Apply styles immediately if possible (reduces initial black frame risk)
        try:
            self._apply_win32_layered_styles()
            self._refresh_win32_styles()
            # Start per-window alpha at 0 so the window is fully transparent until first swap
            self._set_layered_alpha(0)
        except Exception:
            pass

        logger.info(f"[spiral.trace] LoomWindowCompositor.__init__ called: director={director}")
        # Apply layered/click-through styles ASAP after native handle exists
        try:
            QTimer.singleShot(0, self._apply_win32_layered_styles)
        except Exception:
            pass

    def _log_text_debug(self, message: str) -> None:
        """Emit noisy text diagnostics at DEBUG unless text trace is forced."""
        if self._text_trace:
            logger.info(message)
        else:
            logger.debug(message)

    def _initial_transparent_swap(self):
        """Do a one-time transparent clear/swap as soon as the surface is exposed.
        This prevents the OS from compositing an uninitialized (black) backbuffer
        before our first regular paintGL.
        """
        logger.info("[spiral.trace] _initial_transparent_swap called")
        if self._first_transparent_swap_done:
            logger.info("[spiral.trace] _initial_transparent_swap: already done, skipping")
            return
        if not self.isExposed():
            logger.info("[spiral.trace] _initial_transparent_swap: not exposed, skipping")
            return
        # Only proceed if a context exists and can be made current early
        ctx = self.context()
        if ctx is None:
            logger.info("[spiral.trace] _initial_transparent_swap: no context, skipping")
            return
        try:
            self.makeCurrent()
        except Exception as e:
            # Some drivers may not allow this prior to initializeGL; bail out gracefully
            logger.info(f"[spiral.trace] _initial_transparent_swap: makeCurrent failed: {e}")
            return
        try:
            phys_w, phys_h = self._physical_window_size()
            GL.glViewport(0, 0, phys_w, phys_h)
            GL.glClearColor(0.0, 0.0, 0.0, 0.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            try:
                # Swap immediately so DWM sees an all-transparent first frame
                ctx.swapBuffers(self)
            except Exception:
                pass
            self._first_transparent_swap_done = True
            logger.info("[spiral.trace] _initial_transparent_swap: swap complete, restoring alpha...")
            # Restore desired opacity now that we have presented a transparent frame
            try:
                super().setOpacity(self._window_opacity)
            except Exception:
                pass
            # Ensure layered alpha is restored to fully visible
            self._set_layered_alpha(255)
            logger.info("[spiral.trace] _initial_transparent_swap: alpha restored to 255")
        finally:
            try:
                self.doneCurrent()
            except Exception:
                pass
    
    def _force_topmost_windows(self):
        """Force window to topmost using Windows API"""
        if sys.platform == "win32" and ctypes:
            try:
                # Get the window handle
                hwnd = int(self.winId())
                if hwnd:
                    # Set window to topmost using Windows API
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                    )
                    logger.info(f"[spiral.trace] Window forced to topmost using Win32 API: hwnd={hwnd}")
                    return True
            except Exception as e:
                logger.warning(f"[spiral.trace] Failed to force topmost using Win32 API: {e}")
        return False

    def _apply_native_geometry(self, rect: Optional[tuple[int, int, int, int]]):
        """Apply geometry via the native window manager when Qt hints are ignored."""
        if rect is None:
            return
        if sys.platform == "win32" and ctypes:
            x, y, w, h = rect
            try:
                hwnd = int(self.winId())
                if hwnd:
                    ctypes.windll.user32.SetWindowPos(
                        hwnd,
                        HWND_TOPMOST,
                        int(x),
                        int(y),
                        int(max(1, w)),
                        int(max(1, h)),
                        SWP_SHOWWINDOW | SWP_FRAMECHANGED,
                    )
                    logger.info(
                        f"[spiral.trace] Native geometry applied via SetWindowPos: {w}x{h} at ({x},{y})"
                    )
                    return
            except Exception as exc:
                logger.warning(f"[spiral.trace] Native geometry application failed: {exc}")
        # Non-Windows platforms fall back to Qt-managed geometry

    def _get_native_geometry(self) -> Optional[tuple[int, int, int, int]]:
        """Return current native window rect as (x, y, w, h)."""
        if sys.platform == "win32" and ctypes:
            try:
                hwnd = int(self.winId())
                if not hwnd:
                    return None
                rect = ctypes.wintypes.RECT()
                if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top
                    return (int(rect.left), int(rect.top), int(width), int(height))
            except Exception as exc:
                logger.warning(f"[spiral.trace] Failed to query native geometry: {exc}")
        return None

    @staticmethod
    def _screen_native_rect(screen: Optional[QScreen]) -> Optional[tuple[int, int, int, int]]:
        """Return native (physical pixel) geometry for a QScreen if available."""
        if screen is None:
            return None
        try:
            geom = screen.geometry()
            # Prefer Qt's nativeGeometry when available; otherwise compute using DPI scale
            if hasattr(screen, "nativeGeometry"):
                native = screen.nativeGeometry()
                return (native.x(), native.y(), native.width(), native.height())

            dpr = getattr(screen, 'devicePixelRatio', lambda: 1.0)()
            # Fallback using DPI scale since devicePixelRatio for QScreen may be missing
            if dpr in (0.0, 1.0):
                # Try logical DPI vs base 96
                logical_dpi = getattr(screen, 'logicalDotsPerInch', lambda: 96.0)()
                dpr = max(1.0, logical_dpi / 96.0)
            width = int(round(geom.width() * dpr))
            height = int(round(geom.height() * dpr))
            return (geom.x(), geom.y(), width, height)
        except Exception as exc:
            logger.warning(f"[spiral.trace] Failed to compute native rect: {exc}")
            return None

    @staticmethod
    def _screen_physical_size(screen: Optional[QScreen]) -> Optional[tuple[int, int]]:
        """Return (width, height) in physical pixels for the provided screen."""
        if screen is None:
            return None
        try:
            size = screen.size()
            if hasattr(screen, "nativeGeometry"):
                native = screen.nativeGeometry()
                return (native.width(), native.height())
            dpr = getattr(screen, "devicePixelRatio", lambda: 1.0)()
            if dpr in (0.0, 1.0):
                logical_dpi = getattr(screen, "logicalDotsPerInch", lambda: 96.0)()
                dpr = max(1.0, logical_dpi / 96.0)
            return (
                int(max(1, round(size.width() * dpr))),
                int(max(1, round(size.height() * dpr))),
            )
        except Exception as exc:
            logger.warning(f"[spiral.trace] Failed to compute physical screen size: {exc}")
            return None

    def _physical_window_size(self) -> tuple[int, int]:
        """Return current window size in physical pixels (logical * DPR)."""
        try:
            dpr = float(getattr(self, "devicePixelRatioF", lambda: 1.0)())
        except Exception:
            dpr = 1.0
        width = int(max(1, round(self.width() * dpr)))
        height = int(max(1, round(self.height() * dpr)))
        physical = (width, height)
        self._last_physical_size = physical
        return physical


    def fit_to_screen(self, screen: Optional[QScreen] = None):
        """Resize/move the compositor so it fully covers the requested screen.

        Returns the QRect that was applied, or None if no screen was available.
        """
        try:
            if screen is None:
                screen = self._target_screen or self.screen() or QGuiApplication.primaryScreen()
        except Exception:
            screen = None

        if screen is None:
            logger.warning("[spiral.trace] fit_to_screen called without an available screen; skipping")
            return None

        self._target_screen = screen
        geometry = screen.geometry()
        logical_rect = (geometry.x(), geometry.y(), geometry.width(), geometry.height())
        native_target = self._screen_native_rect(screen) or logical_rect
        physical_size = self._screen_physical_size(screen)

        try:
            if hasattr(self, "setScreen"):
                self.setScreen(screen)
        except Exception as exc:
            logger.warning(f"[spiral.trace] Failed to bind compositor to screen '{screen.name()}': {exc}")

        try:
            self.setGeometry(geometry)
            self._last_screen_geometry = logical_rect
            self._last_native_geometry = native_target
            logger.info(
                f"[spiral.trace] fit_to_screen logical geometry {geometry.width()}x{geometry.height()} "
                f"at ({geometry.x()}, {geometry.y()}) on '{screen.name()}', physical={physical_size}"
            )
        except Exception as exc:
            logger.error(f"[spiral.trace] Failed to set geometry for screen '{screen.name()}': {exc}")

        # Ensure the OS-level window matches these coordinates even if Qt hints are ignored.
        self._apply_native_geometry(native_target)
        self._force_topmost_windows()

        native_rect = self._get_native_geometry()
        if native_rect:
            x, y, w, h = native_rect
            logger.info(
                f"[spiral.trace] Native window rect now {w}x{h} at ({x},{y}); native_target={native_target}"
            )
            if (x, y, w, h) != native_target:
                logger.warning(
                    f"[spiral.trace] Native rect mismatch detected (native={(x,y,w,h)}); reapplying "
                    f"geometry {native_target}"
                )
                self._apply_native_geometry(native_target)
        else:
            logger.info("[spiral.trace] Native geometry unavailable (non-Windows or handle missing)")
        return geometry
    
    def initializeGL(self):
        """Initialize OpenGL resources"""
        logger.info("[spiral.trace] LoomWindowCompositor.initializeGL called")
        # Re-assert layered styles after GL init (some drivers recreate surfaces)
        self._apply_win32_layered_styles()
        try:
            # Print OpenGL info
            version = GL.glGetString(GL.GL_VERSION).decode()
            renderer = GL.glGetString(GL.GL_RENDERER).decode()
            vendor = GL.glGetString(GL.GL_VENDOR).decode()
            logger.info(f"[spiral.trace] OpenGL version: {version}")
            logger.info(f"[spiral.trace] OpenGL renderer: {renderer}")
            logger.info(f"[spiral.trace] OpenGL vendor: {vendor}")
            try:
                logger.info(f"[spiral.trace] Window format alphaBufferSize={self.format().alphaBufferSize()}")
            except Exception:
                pass
            
            # Build shader program
            self._build_shader_program()

            # GPU instrumentation setup (timers + best-effort VRAM)
            self._init_gpu_instrumentation()
            try:
                # Populate VRAM metrics as soon as the GL context is valid.
                # Otherwise they won't appear until the first paintGL.
                self._gpu_vram_poll()
            except Exception:
                pass
            
            # Setup geometry
            self._setup_geometry()
            
            # Configure OpenGL state for transparency
            GL.glEnable(GL.GL_BLEND)         # Enable blending for transparency
            # Use premultiplied alpha blending to match spiral.frag output
            GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
            GL.glDisable(GL.GL_DEPTH_TEST)   # No depth testing needed
            GL.glDisable(GL.GL_DITHER)       # Disable dithering completely
            GL.glDisable(GL.GL_MULTISAMPLE)  # Disable multisampling
            
            # Disable any legacy smoothing
            try:
                GL.glDisable(GL.GL_POLYGON_SMOOTH)
                GL.glDisable(GL.GL_LINE_SMOOTH)
                GL.glDisable(GL.GL_POINT_SMOOTH)
                GL.glDisable(0x8C36)  # GL_SAMPLE_SHADING
            except Exception:
                pass
            # Mark compositor as available after successful GL init
            try:
                self.available = True
            except Exception:
                pass
            
            # One-time transparent clear/swap before any regular paint to avoid initial black
            try:
                phys_w, phys_h = self._physical_window_size()
                GL.glViewport(0, 0, phys_w, phys_h)
                GL.glClearColor(0.0, 0.0, 0.0, 0.0)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT)
                ctx = self.context()
                if ctx is not None:
                    ctx.swapBuffers(self)
                    self._first_transparent_swap_done = True
                    self._set_layered_alpha(255)
                    try:
                        super().setOpacity(self._window_opacity)
                    except Exception:
                        pass
            except Exception:
                # Non-fatal; continue
                pass

            # Start animation timer
            self.timer.start(16)  # ~60 FPS
            
            self.initialized = True
            self.available = True
            
            logger.info("[spiral.trace] LoomWindowCompositor.initializeGL complete")
            print("MesmerLoom: QOpenGLWindow initialized - no FBO blit artifacts!")
            
        except Exception as e:
            logger.error(f"[spiral.trace] LoomWindowCompositor.initializeGL failed: {e}")
            self.available = False
    
    def _build_shader_program(self):
        """Build the spiral shader program using the same shader files as the original compositor"""
        logger.info("[spiral.trace] Building spiral shader program...")
        
        # Load shader files (same as original compositor)
        vertex_shader = self._load_text("fullscreen_quad.vert")
        # Restore original spiral shader now that we know the issue
        fragment_shader = self._load_text("spiral.frag")
        
        # Debug: Check shader content
        if self._trace:
            logger.info(f"[spiral.debug] Vertex shader length: {len(vertex_shader)} chars")
            logger.info(f"[spiral.debug] Fragment shader length: {len(fragment_shader)} chars")
        
        # Use raw OpenGL shader compilation (same as existing compositor)
        vs_id = self._compile_shader(vertex_shader, GL.GL_VERTEX_SHADER)
        fs_id = self._compile_shader(fragment_shader, GL.GL_FRAGMENT_SHADER)
        
        self.program_id = GL.glCreateProgram()
        if not self.program_id:
            raise RuntimeError("glCreateProgram returned 0")
            
        GL.glAttachShader(self.program_id, vs_id)
        GL.glAttachShader(self.program_id, fs_id)
        GL.glLinkProgram(self.program_id)
        
        if not GL.glGetProgramiv(self.program_id, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(self.program_id).decode("utf-8", "ignore")
            raise RuntimeError(f"Shader program link failed: {log}")
            
        GL.glDeleteShader(vs_id)
        GL.glDeleteShader(fs_id)
            
        logger.info("[spiral.trace] Spiral shader program linked successfully")
    
    def _load_text(self, filename: str) -> str:
        """Load shader file (same as original compositor)"""
        import pathlib
        shader_dir = pathlib.Path(__file__).with_suffix("").parent / "shaders"
        shader_path = shader_dir / filename
        return shader_path.read_text(encoding="utf-8")
    
    def _compile_shader(self, src: str, stype) -> int:
        """Compile a single shader (copied from existing compositor)"""
        sid = GL.glCreateShader(stype)
        if not sid:
            raise RuntimeError("glCreateShader returned 0 / None")
        
        GL.glShaderSource(sid, src)
        GL.glCompileShader(sid)
        if not GL.glGetShaderiv(sid, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(sid).decode("utf-8", "ignore")
            raise RuntimeError(f"Shader compile failed: {log}")
        return sid
    
    def _setup_geometry(self):
        """Setup fullscreen quad geometry"""
        logger.info("[spiral.trace] Setting up fullscreen quad geometry...")
        
        # Fullscreen quad vertices (position + texture coordinates)
        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0,  # Bottom-left
             1.0, -1.0, 1.0, 0.0,  # Bottom-right
             1.0,  1.0, 1.0, 1.0,  # Top-right
            -1.0,  1.0, 0.0, 1.0   # Top-left
        ], dtype=np.float32)
        
        # Triangle indices for two triangles forming a quad
        indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)
        
        # Create VAO
        self.vao = QOpenGLVertexArrayObject()
        self.vao.create()
        self.vao.bind()
        
        # Create VBO
        self.vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self.vbo.create()
        self.vbo.bind()
        self.vbo.allocate(vertices.tobytes(), vertices.nbytes)
        
        # Create EBO
        self.ebo = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
        self.ebo.create()
        self.ebo.bind()
        self.ebo.allocate(indices.tobytes(), indices.nbytes)
        
        # Setup vertex attributes
        import ctypes
        GL.glEnableVertexAttribArray(0)  # Position
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, ctypes.c_void_p(0))
        
        GL.glEnableVertexAttribArray(1)  # Texture coordinates
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, ctypes.c_void_p(8))
        
        self.vao.release()
        logger.info("[spiral.trace] Geometry setup complete")

    # --- VR safe FBO helpers ---
    def _ensure_vr_fbo(self, w: int, h: int) -> None:
        """Create or resize the offscreen FBO used to mirror frames to VR."""
        try:
            if not self._vr_safe:
                return
            if self._vr_fbo is not None and self._vr_size == (w, h):
                return
            # Delete prior
            if self._vr_tex is not None:
                try: GL.glDeleteTextures(1, [int(self._vr_tex)])
                except Exception: pass
                self._vr_tex = None
            if self._vr_fbo is not None:
                try: GL.glDeleteFramebuffers(1, [int(self._vr_fbo)])
                except Exception: pass
                self._vr_fbo = None
            # Create texture and FBO
            self._vr_tex = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._vr_tex)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, int(w), int(h), 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
            self._vr_fbo = GL.glGenFramebuffers(1)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._vr_fbo)
            GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, self._vr_tex, 0)
            status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
            if status != GL.GL_FRAMEBUFFER_COMPLETE:
                logger.warning(f"[vr] VR FBO incomplete 0x{int(status):04X}; disabling vr-safe mode")
                try: GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
                except Exception: pass
                self._vr_safe = False
                return
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            self._vr_size = (w, h)
        except Exception as e:
            logger.warning(f"[vr] Failed to (re)create VR FBO: {e}")
            self._vr_safe = False

    def vr_fbo_info(self):
        """Return (fbo, w, h) if VR safe mode FBO is available, else None."""
        if self._vr_safe and self._vr_fbo:
            w, h = self._vr_size
            return int(self._vr_fbo), int(w), int(h)
        return None
    
    def _force_repaint(self):
        """Force repaint even when window is not focused.
        
        Qt OpenGL widgets may not update when not focused. This method
        forces both update() (schedules repaint) and attempts to ensure
        the compositor continues rendering on all windows regardless of focus.
        """
        # Schedule repaint (Qt will call paintGL when ready)
        self.update()
        
        # CRITICAL: Also request an explicit update on the window surface
        # This ensures unfocused/background windows continue to render
        try:
            # Force Qt to recognize this window needs repainting
            self.requestUpdate()
        except Exception:
            pass  # Not all Qt versions support this
        
        # Additional fallback: Explicitly repaint now if possible
        try:
            # If the window is visible but not active, force immediate repaint
            if self.isVisible() and not self.isActive():
                # Try to force immediate GL swap (bypasses Qt's focus checks)
                ctx = self.context()
                if ctx and ctx.isValid():
                    # This schedules a swap for next frame
                    pass  # update() already scheduled it
        except Exception:
            pass

    # ------------------------------------------------------------------
    # GPU instrumentation (context-based, no OS GPU preference required)
    def _init_gpu_instrumentation(self) -> None:
        self._gpu_timer_supported = False
        self._gpu_query_ids = []
        self._gpu_query_next_idx = 0
        self._gpu_query_in_flight_idx = None
        self._gpu_query_pending.clear()
        self._gpu_vram_last_poll_t = 0.0

        try:
            # TIME_ELAPSED query is core in modern GL and is the most reliable
            # per-app GPU work measurement we can get from OpenGL.
            # Use a small ring so we can keep sampling even if results lag a frame or two.
            ids = GL.glGenQueries(4)
            if isinstance(ids, int):
                # PyOpenGL may return a single int in some edge cases; still usable.
                self._gpu_query_ids = [int(ids)]
            else:
                self._gpu_query_ids = [int(x) for x in ids]
            self._gpu_timer_supported = len(self._gpu_query_ids) >= 1
        except Exception:
            self._gpu_timer_supported = False
            self._gpu_query_ids = []

    def _gpu_timer_poll_result(self) -> None:
        if not self._gpu_timer_supported:
            return
        if not self._gpu_query_pending:
            return

        now = time.perf_counter()
        # Drain a few results per frame (avoid long loops).
        # Rotate when not ready so one stuck query doesn't block all others.
        for _ in range(min(4, len(self._gpu_query_pending))):
            idx, ended_at = self._gpu_query_pending[0]
            # Drop stale queries (driver/context hiccups) to prevent permanent blockage.
            if now - ended_at > 0.5:
                self._gpu_query_pending.popleft()
                continue
            try:
                qid = self._gpu_query_ids[idx]
                avail = GL.glGetQueryObjectiv(qid, GL.GL_QUERY_RESULT_AVAILABLE)
                available = int(avail[0]) if hasattr(avail, "__len__") else int(avail)
                if not available:
                    # Not ready yet; rotate to the back.
                    self._gpu_query_pending.rotate(-1)
                    continue

                # Prefer 64-bit nanoseconds if supported
                if hasattr(GL, "glGetQueryObjectui64v"):
                    ns = GL.glGetQueryObjectui64v(qid, GL.GL_QUERY_RESULT)
                else:
                    ns = GL.glGetQueryObjectuiv(qid, GL.GL_QUERY_RESULT)

                ns_val = int(ns[0]) if hasattr(ns, "__len__") else int(ns)
                gpu_ms = float(ns_val) / 1_000_000.0
                perf_metrics.record_gpu_time_ms(gpu_ms)
            except Exception:
                # Drop this query from the queue on error so we don't get stuck.
                self._gpu_query_pending.popleft()
            else:
                # Successful read: remove this query from the queue.
                self._gpu_query_pending.popleft()

    def _gpu_timer_begin(self) -> None:
        if not self._gpu_timer_supported or not self._gpu_query_ids:
            return
        if self._gpu_query_in_flight_idx is not None:
            return
        try:
            # Pick the next query ID that isn't pending.
            n = len(self._gpu_query_ids)
            idx = None
            for _ in range(n):
                cand = self._gpu_query_next_idx % n
                self._gpu_query_next_idx = (self._gpu_query_next_idx + 1) % n
                if all(p[0] != cand for p in self._gpu_query_pending):
                    idx = cand
                    break
            if idx is None:
                return

            qid = self._gpu_query_ids[idx]
            GL.glBeginQuery(GL.GL_TIME_ELAPSED, qid)
            self._gpu_query_in_flight_idx = idx
        except Exception:
            self._gpu_query_in_flight_idx = None

    def _gpu_timer_end(self) -> None:
        if not self._gpu_timer_supported:
            return
        if self._gpu_query_in_flight_idx is None:
            return
        try:
            GL.glEndQuery(GL.GL_TIME_ELAPSED)
            # Mark completed query as pending for result polling.
            self._gpu_query_pending.append((self._gpu_query_in_flight_idx, time.perf_counter()))
        except Exception:
            pass
        finally:
            self._gpu_query_in_flight_idx = None

    def _gpu_vram_poll(self) -> None:
        # Poll at most ~1 Hz.
        now = time.perf_counter()
        if now - self._gpu_vram_last_poll_t < 1.0:
            return
        self._gpu_vram_last_poll_t = now

        # NVX_gpu_memory_info
        try:
            GL_GPU_MEMORY_INFO_DEDICATED_VIDMEM_NVX = 0x9047
            GL_GPU_MEMORY_INFO_CURRENT_AVAILABLE_VIDMEM_NVX = 0x9049
            total_kb = int(GL.glGetIntegerv(GL_GPU_MEMORY_INFO_DEDICATED_VIDMEM_NVX))
            free_kb = int(GL.glGetIntegerv(GL_GPU_MEMORY_INFO_CURRENT_AVAILABLE_VIDMEM_NVX))
            perf_metrics.set_gpu_vram_mb(
                total_mb=float(total_kb) / 1024.0,
                free_mb=float(free_kb) / 1024.0,
            )
            return
        except Exception:
            pass

        # ATI_meminfo (free only, no total)
        try:
            GL_TEXTURE_FREE_MEMORY_ATI = 0x87FC
            vals = GL.glGetIntegerv(GL_TEXTURE_FREE_MEMORY_ATI)
            # Returns 4 ints; first is free texture memory in kB.
            free_kb = int(vals[0]) if hasattr(vals, "__len__") else int(vals)
            perf_metrics.set_gpu_vram_mb(total_mb=None, free_mb=float(free_kb) / 1024.0)
        except Exception:
            perf_metrics.set_gpu_vram_mb(total_mb=None, free_mb=None)
    
    def paintGL(self):
        """Render the spiral; if VR safe mode is enabled, render to offscreen FBO then blit to window."""
        if not self.initialized or not self.program_id or not self._active:
            return

        # Qt can recreate the underlying GL context (e.g., monitor changes, driver events).
        # In that case, previously created GL object IDs (including programs) become invalid
        # for the new context. Guard glUseProgram to avoid GL_INVALID_VALUE spam and try
        # to rebuild resources on the fly.
        try:
            if not GL.glIsProgram(int(self.program_id)):
                logger.error(
                    f"[spiral.trace] paintGL: program_id {self.program_id} is not valid; attempting GL reinitialize"
                )
                try:
                    # Best-effort cleanup of the stale handle (may already be invalid).
                    try:
                        GL.glDeleteProgram(int(self.program_id))
                    except Exception:
                        pass
                    self.program_id = None
                    # Rebuild program + geometry + state in the current context.
                    self.initializeGL()
                except Exception as exc:
                    logger.error(f"[spiral.trace] paintGL: GL reinitialize failed: {exc}")
                    return

                if not self.program_id:
                    return
                if not GL.glIsProgram(int(self.program_id)):
                    logger.error(
                        f"[spiral.trace] paintGL: program_id still invalid after reinit ({self.program_id}); skipping frame"
                    )
                    return
        except Exception:
            # If glIsProgram isn't available/throws for any reason, fall back to the existing
            # behavior (glUseProgram will be attempted below).
            pass
            
        now_t = time.perf_counter()
        if self._last_paint_t is not None:
            perf_metrics.record_frame(now_t - self._last_paint_t)
        self._last_paint_t = now_t

        # GPU timing: read previous result and begin a new timer query.
        self._gpu_timer_poll_result()
        self._gpu_timer_begin()

        self.frame_count += 1
        
        # Setup viewport and optional VR FBO (physical pixels)
        w_px, h_px = self._physical_window_size()
        try:
            dpr = float(self.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        
        # DEBUG: Log window dimensions and DPI scaling (first 20 frames only)
        if self.frame_count <= 20 and (self._text_trace or logger.isEnabledFor(logging.DEBUG)):
            primary_flag = getattr(self, "is_primary", True)
            self._log_text_debug(
                f"[Text] DEBUG: paintGL() start - window dimensions: {w_px}x{h_px} devicePixelRatio={dpr:.2f} (is_primary={primary_flag})"
            )
        
        if self._vr_safe:
            self._ensure_vr_fbo(w_px, h_px)
            if self._vr_fbo:
                GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._vr_fbo)
        GL.glViewport(0, 0, w_px, h_px)
        
        # Clear with solid black if no background, transparent if background enabled
        # This ensures spiral is always visible even without media
        if self._background_enabled:
            GL.glClearColor(0.0, 0.0, 0.0, 0.0)  # Transparent - background will show
        else:
            GL.glClearColor(0.0, 0.0, 0.0, 1.0)  # BLACK background for spiral visibility
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        # Get window size for rendering
        try:
            self._render_background(w_px, h_px)
            self._last_background_error = None
        except Exception as e:
            self._last_background_error = str(e)
            logger.error(f"[visual] Background render failed: {e}")

        self.update_zoom_animation()
        
        # Use spiral shader program
        GL.glUseProgram(self.program_id)
        
        # Update director and get current parameters (same as original compositor)
        try:
            # Get actual screen resolution for fullscreen overlay
            screen = self.screen()
            if screen:
                physical_screen = self._screen_physical_size(screen)
                if physical_screen:
                    screen_w, screen_h = physical_screen
                else:
                    screen_size = screen.size()
                    screen_w, screen_h = screen_size.width(), screen_size.height()
                # Use screen resolution for director (ensures proper fullscreen coverage)
                self.director.set_resolution(screen_w, screen_h)
                if self._trace and self.frame_count <= 3:
                    logger.info(f"[spiral.debug] Frame {self.frame_count}: Using screen resolution {screen_w}x{screen_h} (window: {w_px}x{h_px})")
            else:
                # Fallback to window size if screen detection fails
                self.director.set_resolution(w_px, h_px)
            
            # Use fixed dt=1/60 to match Visual Mode Creator's timing (ensures 1:1 parity)
            self.director.update(dt=1/60.0)
            uniforms = self.director.export_uniforms()
                
        except Exception as e:
            logger.warning(f"[spiral.trace] Director update failed: {e}")
            uniforms = {'uIntensity': 0.5}
        
        # Set uniforms using the same approach as original compositor
        def _set1(name, val):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc != -1:  # -1 means not found; 0+ are valid locations
                try:
                    GL.glUniform1f(loc, float(val))
                except GL.GLError:
                    pass  # Silently ignore invalid uniforms
        def _seti(name, val):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc != -1:
                try:
                    GL.glUniform1i(loc, int(val))
                except GL.GLError:
                    pass
        def _set2(name, val: tuple):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc != -1:
                try:
                    GL.glUniform2f(loc, float(val[0]), float(val[1]))
                except GL.GLError:
                    pass
        def _set3(name, val: tuple):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc != -1:
                try:
                    GL.glUniform3f(loc, float(val[0]), float(val[1]), float(val[2]))
                except GL.GLError:
                    pass
        def _set4(name, v0, v1, v2, v3):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc != -1:
                try:
                    GL.glUniform4f(loc, float(v0), float(v1), float(v2), float(v3))
                except GL.GLError:
                    pass
        
        # Set core uniforms (same as original compositor approach)
        current_time = time.time() - self.t0
        
        # Use the same resolution logic as director for consistency, but allow a virtual override.
        if getattr(self, "_virtual_screen_size", None):
            try:
                vw, vh = self._virtual_screen_size
                _set2('uResolution', (float(vw), float(vh)))
            except Exception:
                _set2('uResolution', (float(w_px), float(h_px)))
        else:
            screen = self.screen()
            if screen:
                physical_screen = self._screen_physical_size(screen)
                if physical_screen:
                    screen_w, screen_h = physical_screen
                else:
                    screen_size = screen.size()
                    screen_w, screen_h = screen_size.width(), screen_size.height()
                _set2('uResolution', (float(screen_w), float(screen_h)))
            else:
                # Fallback to window size if screen detection fails
                _set2('uResolution', (float(w_px), float(h_px)))
        
        _set1('uTime', current_time)  # Override director time for consistency (same as original)
        
        # Set ALL director uniforms (same as original compositor)
        for k, v in uniforms.items():
            # Skip uTime and uResolution as we set them manually above (same as original)
            if k in ('uTime', 'uResolution'):
                continue
            if isinstance(v, int): 
                _seti(k, v)
            elif isinstance(v, (tuple, list)):
                if len(v) == 2:
                    _set2(k, v)
                elif len(v) == 3:
                    _set3(k, v)
                elif len(v) == 4:
                    _set4(k, v[0], v[1], v[2], v[3])  # vec4 for colors
                else:
                    _set1(k, float(v[0]) if v else 0.0)  # fallback to first element
            else: 
                _set1(k, v)
        
        # Set QOpenGLWindow-specific defaults for transparency
        _seti('uInternalOpacity', 0)  # Use window transparency mode (not internal blending)
        _set3('uBackgroundColor', (0.0, 0.0, 0.0))  # Pure black background for better contrast
        _seti('uBlendMode', getattr(self, '_blend_mode', 0))  # Default blend mode
        _seti('uTestOpaqueMode', 0)  # Normal rendering mode (transparency enabled)
        _seti('uTestLegacyBlend', 0)  # Use modern blending
        _seti('uSRGBOutput', 0)  # Let OpenGL handle sRGB
        
        # Add window-level opacity control (separate from spiral opacity)
        window_opacity_value = getattr(self, '_window_opacity', 1.0)
        _set1('uWindowOpacity', window_opacity_value)
        
        # Enable GL blending for transparency (premultiplied alpha)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        
        
        # Render fullscreen quad
        self.vao.bind()
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        self.vao.release()
        
        GL.glUseProgram(0)
        
        # === RENDER TEXT OVERLAY (after spiral, before VR blit) ===
        if self.text_director:
            try:
                # Update text director state (frame counting, text cycling) ONLY on primary compositor
                # Secondary compositors share the same text_director but don't advance its state
                if self.is_primary:
                    self.text_director.update()
                
                # Render the text textures to screen (all compositors render their own textures)
                self._render_text_overlays(w_px, h_px)
                
            except Exception as e:
                if self.frame_count <= 3:  # Only log errors on first few frames
                    logger.error(f"[text] Text rendering failed: {e}", exc_info=True)
        
        # Log performance every 60 frames
        if self._trace and self.frame_count % self._log_interval == 0:
            logger.info(f"[spiral.trace] LoomWindowCompositor.paintGL: frame={self.frame_count} resolution={w_px}x{h_px} uniforms_count={len(uniforms)}")
            if self.frame_count % (self._log_interval * 4) == 0:  # Extra debug every 240 frames
                logger.info(f"[spiral.trace] Director uniforms: {list(uniforms.keys())}")
                logger.info(f"[spiral.trace] Key values: uIntensity={uniforms.get('uIntensity', 'MISSING')}, uPhase={uniforms.get('uPhase', 'MISSING')}, uBarWidth={uniforms.get('uBarWidth', 'MISSING')}")
        
        # If rendering to offscreen FBO, blit it to the window default framebuffer now
        if self._vr_safe and self._vr_fbo:
            try:
                GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self._vr_fbo)
                GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
                GL.glBlitFramebuffer(0, 0, w_px, h_px, 0, 0, w_px, h_px, GL.GL_COLOR_BUFFER_BIT, GL.GL_NEAREST)
                GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, 0)
                GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
            except Exception:
                pass

        # GPU timing end (exclude readPixels/capture sync work)
        self._gpu_timer_end()
        self._gpu_vram_poll()

        # Capture frame for VR streaming / GUI preview BEFORE swapping buffers (GL context is current here)
        try:
            if getattr(self, '_vr_capture_enabled', False) or getattr(self, '_preview_capture_enabled', False):
                now = time.time()
                interval = getattr(self, '_capture_interval_s', 0.0)
                if interval > 0.0 and (now - getattr(self, '_capture_last_t', 0.0)) < interval:
                    raise RuntimeError("capture throttled")
                self._capture_last_t = now

                # Read pixels from the current framebuffer.
                # Do NOT crop here: VR uses a dedicated square compositor surface.
                pixels = GL.glReadPixels(0, 0, w_px, h_px, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                frame = np.frombuffer(pixels, dtype=np.uint8).reshape(h_px, w_px, 3)
                # Flip vertically (GL origin is bottom-left) and force contiguous memory.
                # A non-contiguous view (negative strides) can render as black/garbage in QImage.
                frame = np.flipud(frame).copy()
                # Emit frame data to VR streaming handler
                self.frame_ready.emit(frame)
        except Exception as e:
            if self.frame_count <= 3:
                logger.error(f"[VR] Frame capture failed: {e}")

        # Notify listeners (duplicate/mirror windows) that a new frame is available
        try:
            self.frame_drawn.emit()
        except Exception:
            pass
    
    def resizeGL(self, width, height):
        """Handle window resize"""
        ctx = self.context()
        if ctx is None:
            logger.warning("[spiral.trace] resizeGL called without a valid context; skipping viewport update")
            return

        made_current = False
        try:
            if QOpenGLContext.currentContext() is not ctx:
                try:
                    self.makeCurrent()
                    made_current = True
                except Exception as exc:
                    logger.warning(f"[spiral.trace] resizeGL failed to make context current: {exc}")
                    return

            phys_w, phys_h = self._physical_window_size()
            try:
                GL.glViewport(0, 0, phys_w, phys_h)
            except Exception as exc:
                logger.error(f"[spiral.trace] glViewport failed during resize: {exc}")
                return
            if self._trace:
                logger.info(
                    f"[spiral.trace] LoomWindowCompositor.resizeGL: logical={width}x{height} physical={phys_w}x{phys_h}"
                )
        finally:
            if made_current:
                try:
                    ctx.doneCurrent()
                except Exception:
                    pass
    
    def set_active(self, active: bool):
        """Enable/disable rendering"""
        self._active = active
        if self._trace:
            logger.info(f"[spiral.trace] LoomWindowCompositor.set_active: {active}")

    def _set_capture_interval(self, max_fps: int) -> None:
        try:
            fps = int(max_fps)
        except Exception:
            fps = 15
        fps = max(1, min(60, fps))
        self._capture_interval_s = 1.0 / float(fps)
        self._capture_last_t = 0.0

    def set_preview_capture_enabled(self, enabled: bool, max_fps: int = 15) -> None:
        """Enable capture for the Home tab preview (independent of VR streaming)."""
        self._set_capture_interval(max_fps)
        self._preview_capture_enabled = bool(enabled)

    def set_vr_capture_enabled(self, enabled: bool, max_fps: int = 30) -> None:
        """Enable capture for VR streaming (independent of Home preview)."""
        self._set_capture_interval(max_fps)
        self._vr_capture_enabled = bool(enabled)

    def set_capture_enabled(self, enabled: bool, max_fps: int = 15) -> None:
        """Backward compatible alias: controls Home preview capture."""
        self.set_preview_capture_enabled(enabled, max_fps=max_fps)
    
    def set_intensity(self, intensity: float):
        """Set spiral intensity"""
        try:
            self.director.set_intensity(intensity)
        except Exception as e:
            logger.warning(f"[spiral.trace] Failed to set intensity: {e}")
    
    def setWindowOpacity(self, opacity: float):
        """Set window-level opacity (0.0-1.0) for the entire overlay"""
        opacity = max(0.0, min(1.0, opacity))  # Clamp to valid range
        self._window_opacity = opacity
        try:
            # Apply to native window only after first transparent swap has occurred
            if getattr(self, '_first_transparent_swap_done', False):
                super().setOpacity(opacity)
        except Exception:
            pass
        logger.info(f"[spiral.trace] setWindowOpacity({opacity}) - window transparency enabled, stored as {self._window_opacity}")
        self.update()  # Trigger repaint with new opacity
    
    def set_blend_mode(self, mode: int):
        """Set blend mode (for compatibility)"""
        logger.info(f"[spiral.trace] set_blend_mode({mode}) called - not implemented for QOpenGLWindow")
    
    def set_render_scale(self, scale: float):
        """Set render scale (for compatibility)"""
        logger.info(f"[spiral.trace] set_render_scale({scale}) called - not implemented for QOpenGLWindow")
    
    # ===== Background Texture Support (for Visual Programs) =====
    
    def upload_image_to_gpu(self, image_data, generate_mipmaps: bool = False) -> int:
        """Upload ImageData to GPU texture in the compositor's OpenGL context.
        
        Args:
            image_data: ImageData object with RGBA pixel data
            generate_mipmaps: Whether to generate mipmaps
            
        Returns:
            OpenGL texture ID
        """
        # CRITICAL: Make context current before any GL operations
        previous_ctx = QOpenGLContext.currentContext()
        previous_surface = previous_ctx.surface() if previous_ctx else None
        try:
            self.makeCurrent()
        except Exception as e:
            logger.error(f"[visual] Failed to make context current for texture upload: {e}")
            raise

        try:
            # Generate new texture
            texture_id = GL.glGenTextures(1)
            
            # Bind texture
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
            
            # Set texture parameters
            GL.glTexParameteri(
                GL.GL_TEXTURE_2D,
                GL.GL_TEXTURE_MIN_FILTER,
                GL.GL_LINEAR_MIPMAP_LINEAR if generate_mipmaps else GL.GL_LINEAR,
            )
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            
            # Wrap mode: clamp to edge
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            
            # Upload pixel data (RGBA8)
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                GL.GL_RGBA8,
                image_data.width,
                image_data.height,
                0,
                GL.GL_RGBA,
                GL.GL_UNSIGNED_BYTE,
                image_data.data,
            )
            
            # Generate mipmaps if requested
            if generate_mipmaps:
                GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
            
            # Unbind
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            
            logger.info(
                f"[visual] Uploaded texture {texture_id} in compositor context: {image_data.width}x{image_data.height}"
            )
            return texture_id
        finally:
            self._restore_previous_context(previous_ctx, previous_surface)
        
    def get_background_debug_state(self) -> Dict[str, Union[bool, int, float, tuple]]:
        """Return lightweight diagnostics for CLI/tests without needing GL access."""
        return {
            "enabled": bool(self._background_enabled),
            "texture_id": int(self._background_texture or 0),
            "image_size": (int(self._background_image_width), int(self._background_image_height)),
            "zoom": float(self._background_zoom),
            "fade_queue": len(self._fade_queue),
            "fade_active": bool(self._fade_active),
            "last_error": self._last_background_error,
            "last_render_frame": int(self._last_background_render_frame),
            "last_set_timestamp": float(self._last_background_set_timestamp),
            "uploads": int(self._background_upload_count),
        }
    
    def set_background_texture(self, texture_id: int, zoom: float = 1.0, image_width: int = None, image_height: int = None) -> None:
        """Set background image texture with optional fade transition (Visual Programs support).
        
        Args:
            texture_id: OpenGL texture ID (from texture.upload_image_to_gpu)
            zoom: Zoom factor (1.0 = fit to screen, >1.0 = zoomed in)
            image_width: Original image width (for aspect ratio)
            image_height: Original image height (for aspect ratio)
        """
        previous_ctx = QOpenGLContext.currentContext()
        previous_surface = previous_ctx.surface() if previous_ctx else None
        ctx_acquired = False
        try:
            self.makeCurrent()
            ctx_acquired = True
        except Exception as exc:
            logger.warning(f"[visual] Failed to make context current in set_background_texture: {exc}")
        
        if ctx_acquired:
            try:
                # CRITICAL: Delete old texture BEFORE replacing it (memory leak fix!)
                if self._background_texture is not None and self._background_texture != texture_id:
                    # If fade is enabled, DON'T delete yet - it will be deleted after fade completes
                    if not (self._fade_enabled and self._background_enabled):
                        try:
                            if GL.glIsTexture(self._background_texture):
                                GL.glDeleteTextures([self._background_texture])
                                logger.debug(f"[visual] Deleted old texture {self._background_texture} (no fade)")
                        except Exception as e:
                            logger.warning(f"[visual] Failed to delete old texture: {e}")
            finally:
                self._restore_previous_context(previous_ctx, previous_surface)
        
        # If fade is enabled and we have a current texture, start fade transition
        if self._fade_enabled and self._background_texture is not None and self._background_enabled:
            start_frame = self.frame_count

            # Add current texture to fade queue for ghosting effect
            self._fade_queue.append({
                'texture': self._background_texture,
                'zoom': self._background_zoom,
                'width': self._background_image_width,
                'height': self._background_image_height,
                'start_frame': start_frame
            })
            
            # Also store in old texture for backward compatibility
            self._fade_old_texture = self._background_texture
            self._fade_old_zoom = self._background_zoom
            self._fade_old_width = self._background_image_width
            self._fade_old_height = self._background_image_height
            self._fade_active = True
            self._fade_progress = 0.0
            self._fade_frame_start = start_frame
            logger.info(f"[fade] Starting fade transition (duration={self._fade_duration:.2f}s, queue_size={len(self._fade_queue)})")
        
        self._background_texture = texture_id
        self._background_zoom = max(0.1, min(5.0, zoom))
        
        if image_width is not None and image_height is not None:
            self._background_image_width = max(1, image_width)
            self._background_image_height = max(1, image_height)
        
        self._background_enabled = True
        self._background_upload_count += 1
        self._last_background_set_timestamp = time.time()
        logger.info(f"[visual] Background texture set: id={texture_id}, zoom={zoom}, size={image_width}x{image_height}")
        
        # CRITICAL: Force immediate repaint to show the new image
        # This ensures the image appears even if the window is not focused
        self.update()
        try:
            self.requestUpdate()
        except Exception:
            pass
    
    def clear_background_texture(self) -> None:
        """Clear background image texture."""
        previous_ctx = QOpenGLContext.currentContext()
        previous_surface = previous_ctx.surface() if previous_ctx else None
        ctx_acquired = False
        try:
            self.makeCurrent()
            ctx_acquired = True
        except Exception as exc:
            logger.warning(f"[visual] Failed to make context current in clear_background_texture: {exc}")
        if ctx_acquired:
            try:
                if self._background_texture is not None and GL.glIsTexture(self._background_texture):
                    GL.glDeleteTextures([self._background_texture])
            except Exception as exc:
                logger.warning(f"[visual] Failed to delete background texture: {exc}")
            finally:
                self._restore_previous_context(previous_ctx, previous_surface)
        self._background_texture = None
        self._background_enabled = False
        self._last_background_render_frame = -1
        self._last_background_set_timestamp = 0.0
    
    def set_fade_duration(self, duration_seconds: float) -> None:
        """Set fade transition duration for media changes.
        
        Args:
            duration_seconds: Fade duration in seconds (0.0 = instant, 0.5 = half second, etc.)
        """
        try:
            value = float(duration_seconds)
        except (TypeError, ValueError):
            value = 0.0

        value = max(0.0, value)
        self._fade_duration = value
        self._fade_enabled = value > 0.0
        if not self._fade_enabled:
            self._fade_queue.clear()
            self._fade_active = False
            logger.info("[fade] Disabled (instant transitions)")
        else:
            logger.info(f"[fade] Enabled (duration={self._fade_duration:.2f}s)")
    
    def set_background_zoom(self, zoom: float) -> None:
        """Set background zoom factor."""
        self._background_zoom = max(0.1, min(5.0, zoom))

    def set_background_zoom_multiplier(self, multiplier: float) -> None:
        """Set a per-compositor multiplier applied to background/video zoom.

        Applied at render time only (via the uZoom uniform), so it won't interfere with
        the zoom animator or the base zoom recorded on fade layers.

        - multiplier < 1.0 => zoom out (media appears smaller)
        - multiplier > 1.0 => zoom in
        """
        try:
            value = float(multiplier)
        except Exception:
            return
        self._background_zoom_multiplier = max(0.05, min(20.0, value))
    
    def start_zoom_animation(self, target_zoom: float = 1.5, start_zoom: float = 1.0, duration_frames: int = 48, mode: str = "exponential", rate: float = None) -> None:
        """Start duration-based zoom-in animation.
        
        Args:
            target_zoom: Final zoom level (clamped to 0.1-5.0)
            start_zoom: Starting zoom level (clamped to 0.1-5.0)
            duration_frames: Number of frames over which to animate (e.g., 48 for images, 300 for videos)
            mode: "exponential" (continuous zoom in). Other legacy modes are treated as exponential.
            rate: Optional explicit zoom rate (overrides auto-calculation)
        """
        # Don't start zoom if disabled (e.g., video focus mode)
        if not self._zoom_enabled:
            return
        
        normalized_mode = "exponential" if mode == "exponential" else "exponential"

        normalized_start = max(0.1, min(5.0, start_zoom))
        normalized_target = max(0.1, min(5.0, target_zoom))

        # Treat (start_zoom -> target_zoom) as a requested multiplier.
        # For the "illusion" behavior: restart each media item at a stable baseline
        # (typically 1.0) and keep motion constant so it never appears to pause.
        requested_factor = normalized_target / max(0.001, normalized_start)

        self._zoom_start = normalized_start
        self._zoom_target = normalized_target

        # If start is too close to target, the zoom delta is imperceptible.
        if abs(self._zoom_target - self._zoom_start) < 0.02:
            if abs(self._zoom_target - 1.5) < 0.02:
                self._zoom_start = 1.0
            elif abs(self._zoom_target - 1.0) < 0.02:
                self._zoom_start = 1.5
            else:
                self._zoom_start = 1.0

        self._zoom_current = self._zoom_start
        self._zoom_duration_frames = max(1, duration_frames)
        self._zoom_elapsed_frames = 0
        # Use a monotonic clock so system time adjustments and FPS spikes don't affect zoom timing.
        now = time.perf_counter()
        self._zoom_start_time = now
        self._zoom_last_time = now
        self._zoom_duration_seconds = max(1e-3, self._zoom_duration_frames / 60.0)
        
        # Store zoom mode for update calculations
        self._zoom_mode = normalized_mode
        
        # For exponential we want CONSTANT speed; _zoom_rate is log-rate-per-second.
        if normalized_mode == "exponential":
            duration_s = float(getattr(self, "_zoom_duration_seconds", 0.0) or 0.0)
            if duration_s <= 0.0:
                duration_s = max(1e-3, float(self._zoom_duration_frames or 1) / 60.0)

            if rate is not None:
                self._zoom_rate = float(rate)
            else:
                import math
                factor = float(requested_factor)
                if factor <= 0.0:
                    factor = 1.0
                if abs(factor - 1.0) < 1e-6:
                    factor = 1.5
                self._zoom_rate = math.log(factor) / duration_s

            if self._zoom_rate < 0:
                self._zoom_rate = abs(self._zoom_rate)
            logger.info(
                f"[zoom] Starting {normalized_mode} zoom start={self._zoom_start:.3f} target={self._zoom_target:.3f} "
                f"log_rate={self._zoom_rate:.3f}/s (duration={duration_s:.2f}s)"
            )
        elif rate is not None:
            self._zoom_rate = float(rate)
        
        self._background_zoom = self._zoom_current
        self._zoom_animating = True
    
    def set_zoom_animation_enabled(self, enabled: bool) -> None:
        """Enable or disable zoom animations.
        
        Args:
            enabled: True to enable zoom animations, False to disable
        """
        self._zoom_enabled = enabled
        if not enabled:
            # Reset zoom to 1.0 when disabling
            self._zoom_animating = False
            self._zoom_current = 1.0
            self._zoom_target = 1.0
            self._background_zoom = 1.0
        logger.info(f"[compositor] Zoom animations {'enabled' if enabled else 'disabled'}")
    
    def reset_zoom(self) -> None:
        """Reset zoom animation to initial state (zoom=1.0, no animation).
        
        Used when switching playbacks to prevent zoom carryover from previous playback.
        """
        self._zoom_animating = False
        self._zoom_current = 1.0
        self._zoom_frame = 0
        self._background_zoom = 1.0
        self._zoom_rate = getattr(self, '_zoom_rate_default', 0.42)
        self._zoom_start_time = 0.0
        logger.debug(f"[compositor] Zoom animation reset to 1.0 (stopped, rate cleared)")
    
    def set_zoom_target(self, target_zoom: float) -> None:
        """Set the maximum zoom target (used for future zoom animations).
        
        Args:
            target_zoom: Maximum zoom level (0.1 to 5.0)
        """
        self._zoom_target = max(0.1, min(5.0, target_zoom))
        logger.info(f"[compositor] Zoom target set to {self._zoom_target}x")
    
    def update_zoom_animation(self) -> None:
        """Update zoom animation (exponential mode)."""
        if not self._zoom_animating:
            return
        
        # Increment elapsed frames
        self._zoom_elapsed_frames += 1

        # Treat any legacy mode as exponential.
        if self._zoom_mode != "exponential":
            self._zoom_mode = "exponential"

        if self._zoom_mode == "exponential":
            import math
            now = time.perf_counter()
            last = float(getattr(self, "_zoom_last_time", 0.0) or now)
            dt = max(0.0, now - last)
            dt = min(dt, 0.10)
            self._zoom_last_time = now

            current = float(getattr(self, "_zoom_current", 1.0) or 1.0)
            current = max(0.001, current)
            rate = float(getattr(self, "_zoom_rate", 0.0) or 0.0)
            self._zoom_current = current * math.exp(rate * dt)
        else:
            return
        
        # Clamp to safe range
        self._zoom_current = max(0.1, min(5.0, self._zoom_current))
        
        # Update background zoom
        self._background_zoom = self._zoom_current
    
    def set_background_video_frame(self, frame_data, width: int, height: int, zoom: float = 1.0, new_video: bool = False) -> None:
        """Update background with video frame (efficient GPU upload).
        
        Args:
            frame_data: RGB frame data as numpy array (shape: height x width x 3, dtype=uint8)
            width: Frame width in pixels
            height: Frame height in pixels
            zoom: Zoom factor (1.0 = fit to screen, >1.0 = zoomed in)
            new_video: True if this is the first frame of a new video (triggers fade transition)
        """
        try:
            from OpenGL import GL
            import numpy as np
            
            # Check if OpenGL context is ready
            if not self.initialized:
                if not getattr(self, "_video_upload_init_warned", False):
                    logger.warning("[video.upload] Ignoring frame: compositor not initialized yet")
                    self._video_upload_init_warned = True
                return

            previous_ctx = QOpenGLContext.currentContext()
            previous_surface = previous_ctx.surface() if previous_ctx else None

            if new_video:
                self._pending_video_upload_log = True

            try:
                if not self.isExposed():
                    logger.debug("[video.upload] Skipping frame upload; window not exposed")
                    return

                if not self.isVisible():
                    logger.debug("[video.upload] Skipping frame upload; window not visible")
                    return

                if not int(self.winId()):
                    logger.debug("[video.upload] Skipping frame upload; winId not ready")
                    return

                ctx = self.context()
                surface = ctx.surface() if ctx else None
                if ctx is None or surface is None:
                    logger.debug("[video.upload] Skipping frame upload; GL context missing")
                    return

                if not ctx.makeCurrent(surface):
                    logger.warning("[video.upload] Failed to make GL context current; dropping frame")
                    return

                if new_video or (self.frame_count % 180 == 0):
                    logger.debug(
                        "[video.upload] frame=%dx%d zoom=%.2f new_video=%s background_enabled=%s",
                        width,
                        height,
                        zoom,
                        new_video,
                        self._background_enabled,
                    )
                
                # Ensure frame data is correct format
                if not isinstance(frame_data, np.ndarray):
                    logger.error("frame_data must be numpy array")
                    return
                
                if frame_data.shape != (height, width, 3):
                    logger.error(f"frame_data shape mismatch: expected ({height}, {width}, 3), got {frame_data.shape}")
                    return
                
                if frame_data.dtype != np.uint8:
                    logger.error(f"frame_data dtype mismatch: expected uint8, got {frame_data.dtype}")
                    return

                if not frame_data.flags.c_contiguous:
                    if not getattr(self, "_video_upload_copy_warned", False):
                        logger.warning("[video.upload] frame_data not contiguous; copying buffer for GL upload")
                        self._video_upload_copy_warned = True
                    frame_data = np.ascontiguousarray(frame_data)
                
                # DOUBLE FLIP (matches LoomCompositor line 1276):
                # 1. Flip data here: top-left -> bottom-left  
                # 2. Shader flips again: bottom-left -> top-left
                # Result: Original orientation preserved (which is what we want!)
                # NO DATA FLIP - test if videos are already correct
                frame_data_flipped = frame_data
                
                # Create or reuse texture
                needs_new_texture = (
                    self._background_texture is None or 
                    not GL.glIsTexture(self._background_texture) or
                    self._background_image_width != width or 
                    self._background_image_height != height
                )
                
                # Trigger fade transition if this is a new video and we have existing content
                old_texture_enqueued_for_fade = False
                if new_video and self._fade_enabled and self._background_texture is not None and self._background_enabled:
                    start_frame = self.frame_count

                    # Add current texture to fade queue for ghosting effect
                    self._fade_queue.append({
                        'texture': self._background_texture,
                        'zoom': self._background_zoom,
                        'width': self._background_image_width,
                        'height': self._background_image_height,
                        'start_frame': start_frame
                    })
                    
                    # Also store in old texture for backward compatibility
                    self._fade_old_texture = self._background_texture
                    self._fade_old_zoom = self._background_zoom
                    self._fade_old_width = self._background_image_width
                    self._fade_old_height = self._background_image_height
                    self._fade_active = True
                    self._fade_progress = 0.0
                    self._fade_frame_start = start_frame
                    logger.info(f"[fade] Starting fade transition for video (duration={self._fade_duration:.2f}s, queue_size={len(self._fade_queue)})")
                    
                    # Force texture recreation so we don't overwrite the old texture during fade
                    needs_new_texture = True
                    old_texture_enqueued_for_fade = True
                
                upload_mode = "reuse"
                upload_start = time.perf_counter()
                prev_unpack_alignment = GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT)
                try:
                    GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)

                    if needs_new_texture:
                        # Delete old texture if it exists and is NOT currently queued for fade
                        if (
                            self._background_texture is not None
                            and GL.glIsTexture(self._background_texture)
                            and not old_texture_enqueued_for_fade
                        ):
                            GL.glDeleteTextures([self._background_texture])
                        
                        # Generate new texture
                        self._background_texture = GL.glGenTextures(1)
                        GL.glBindTexture(GL.GL_TEXTURE_2D, self._background_texture)
                        
                        # Set texture parameters
                        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
                        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
                        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
                        
                        # Upload initial frame data (flipped)
                        GL.glTexImage2D(
                            GL.GL_TEXTURE_2D,
                            0,  # Mipmap level
                            GL.GL_RGB,  # Internal format
                            width,
                            height,
                            0,  # Border
                            GL.GL_RGB,  # Format
                            GL.GL_UNSIGNED_BYTE,
                            frame_data_flipped
                        )
                        upload_mode = "glTexImage2D(new)"
                        logger.debug(f"Created video texture {self._background_texture} ({width}x{height})")
                    else:
                        # Reuse existing texture (faster)
                        GL.glBindTexture(GL.GL_TEXTURE_2D, self._background_texture)
                        GL.glTexSubImage2D(
                            GL.GL_TEXTURE_2D,
                            0,  # Mipmap level
                            0, 0,  # Offset
                            width,
                            height,
                            GL.GL_RGB,
                            GL.GL_UNSIGNED_BYTE,
                            frame_data_flipped
                        )
                        upload_mode = "glTexSubImage2D(reuse)"
                finally:
                    GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, prev_unpack_alignment)

                upload_ms = (time.perf_counter() - upload_start) * 1000.0
                if upload_ms >= _VIDEO_UPLOAD_WARN_MS:
                    self._record_video_upload_perf(upload_mode, upload_ms, width, height)
                
                # Update state
                self._background_image_width = width
                self._background_image_height = height
                # Important: video uploads happen every frame. If we overwrite
                # _background_zoom here while a compositor-driven zoom animation is
                # active, the animation will appear to "zoom once then stop".
                if not getattr(self, "_zoom_animating", False):
                    self._background_zoom = max(0.1, min(5.0, zoom))
                self._background_enabled = True

                if getattr(self, "_pending_video_upload_log", False):
                    logger.info(
                        "[video.upload] First frame applied %dx%d zoom=%.2f texture=%s",
                        width,
                        height,
                        self._background_zoom,
                        self._background_texture,
                    )
                    self._pending_video_upload_log = False
            finally:
                self._restore_previous_context(previous_ctx, previous_surface)
        except Exception:
            logger.exception("Failed to upload video frame; dropping to keep compositor alive")
    
    def set_text_opacity(self, opacity: float) -> None:
        """Set global text opacity (0.0 to 1.0). Affects all text elements."""
        self._text_opacity = max(0.0, min(1.0, opacity))
        logger.info(f"[Text] Global text opacity set to {self._text_opacity:.2f}")
    
    def get_text_opacity(self) -> float:
        """Get current global text opacity."""
        return getattr(self, '_text_opacity', 1.0)
    
    def _build_background_program(self) -> int:
        """Build shader program for background image/video rendering."""
        # Simple vertex shader (fullscreen quad)
        vs_src = """#version 330 core
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

out vec2 vTexCoord;

void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    // Flip Y coordinate (OpenGL texture origin is bottom-left, images are top-left)
    vTexCoord = vec2(aTexCoord.x, 1.0 - aTexCoord.y);
}
"""
        
        # Fragment shader with zoom, aspect ratio, and kaleidoscope support
        fs_src = self._background_fs_source()
        
        # Compile and link
        vs = self._compile_shader(vs_src, GL.GL_VERTEX_SHADER)
        fs = self._compile_shader(fs_src, GL.GL_FRAGMENT_SHADER)
        
        prog = GL.glCreateProgram()
        GL.glAttachShader(prog, vs)
        GL.glAttachShader(prog, fs)
        GL.glLinkProgram(prog)
        
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(prog).decode('utf-8', 'ignore')
            raise RuntimeError(f"Background program link failed: {log}")
        
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)
        
        logger.info(f"[visual] Built background shader program: {prog}")
        return int(prog)

    @staticmethod
    def _background_fs_source() -> str:
        """Return background fragment shader source.

        Exposed for testing so we can validate it without requiring a GL context.
        """
        return """#version 330 core
in vec2 vTexCoord;
out vec4 FragColor;

uniform sampler2D uTexture;
uniform vec2 uResolution;
uniform float uZoom;
uniform vec2 uOffset;
uniform int uKaleidoscope;
uniform vec2 uImageSize;
uniform float uOpacity;  // Opacity for fade transitions (0.0-1.0)

void main() {
    // Compute aspects once
    float windowAspect = uResolution.x / uResolution.y;
    float imageAspect = uImageSize.x / uImageSize.y;

    vec2 uv = vTexCoord;

    // Aspect-ratio-preserving fit (letterbox/pillarbox)
    if (imageAspect > windowAspect) {
        float scale = windowAspect / imageAspect;
        uv.y = (uv.y - 0.5) / scale + 0.5;
    } else {
        float scale = imageAspect / windowAspect;
        uv.x = (uv.x - 0.5) / scale + 0.5;
    }

    // Apply offset
    uv += uOffset;

    // Apply zoom around center
    vec2 center = vec2(0.5, 0.5);
    uv = center + (uv - center) / uZoom;

    // Wrap for tiling
    uv = fract(uv);

    // Kaleidoscope mirroring
    if (uKaleidoscope == 1) {
        vec2 quadrant = floor(uv * 2.0);
        vec2 tileUV = fract(uv * 2.0);
        if (mod(quadrant.x, 2.0) == 1.0) tileUV.x = 1.0 - tileUV.x;
        if (mod(quadrant.y, 2.0) == 1.0) tileUV.y = 1.0 - tileUV.y;
        uv = tileUV;
    }

    // Sample texture (NO Y-FLIP - image data is already in correct orientation)
    vec4 color = texture(uTexture, uv);
    
    // Apply fade opacity for transitions (match LoomCompositor behavior)
    color.a = uOpacity;
    
    FragColor = color;
}
"""

    def _record_fade_perf_event(self, stage: str, duration_ms: float, *, queue_size: int, layers_drawn: int = 0) -> None:
        """Throttle fade perf warnings so we only log actionable spikes."""
        self._fade_perf_last = {
            "stage": stage,
            "duration_ms": duration_ms,
            "queue_size": queue_size,
            "layers_drawn": layers_drawn,
        }
        self._fade_perf_sampler.record()
        now = time.monotonic()
        if now >= self._fade_perf_next_log:
            burst = max(1, self._fade_perf_sampler.flush())
            payload = self._fade_perf_last or {}
            self._fade_perf_next_log = now + 1.0
            logger.warning(
                "[fade.perf] events=%d stage=%s last=%.2fms queue=%d layers=%d",
                burst,
                payload.get("stage", stage),
                payload.get("duration_ms", duration_ms),
                payload.get("queue_size", queue_size),
                payload.get("layers_drawn", layers_drawn),
            )

    def _record_video_upload_perf(self, mode: str, duration_ms: float, width: int, height: int) -> None:
        """Throttle noisy video upload logs while preserving last spike info."""
        self._video_perf_last = {
            "mode": mode,
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
        }
        self._video_upload_sampler.record()
        now = time.monotonic()
        if now >= self._video_upload_next_log:
            burst = max(1, self._video_upload_sampler.flush())
            payload = self._video_perf_last or {}
            self._video_upload_next_log = now + 1.0
            logger.warning(
                "[video.upload.perf] events=%d mode=%s size=%dx%d last=%.2fms",
                burst,
                payload.get("mode", mode),
                payload.get("width", width),
                payload.get("height", height),
                payload.get("duration_ms", duration_ms),
            )
    
    def _render_background(self, w_px: int, h_px: int) -> None:
        """Render background image/video texture with optional fade transition.
        
        Args:
            w_px: Viewport width
            h_px: Viewport height
        """
        if not self._background_enabled or self._background_texture is None:
            return
        
        # CRITICAL: Ensure GL context is current before any GL operations
        # This is essential for lazy shader building and texture binding
        try:
            self.makeCurrent()
        except Exception as e:
            logger.warning(f"[visual] Failed to make context current in _render_background: {e}")
            return
        
        render_start = time.perf_counter()
        now = time.monotonic()  # Legacy support for queues created before frame-based timing
        current_frame = self.frame_count
        fade_duration_frames = max(0.0, self._fade_duration) * 60.0

        def _resolve_start_frame(item: dict[str, Any]) -> int:
            start_frame = item.get('start_frame')
            if start_frame is not None:
                return int(start_frame)
            # Fallback for old entries that only have start_time (seconds)
            start_time = item.get('start_time')
            if start_time is None:
                return current_frame
            elapsed_seconds = max(0.0, now - start_time)
            return max(0, current_frame - int(elapsed_seconds * 60.0))
        
        # Remove fully faded textures from queue
        # CRITICAL: Delete expired textures before removing from queue (memory leak fix!)
        cleanup_start = time.perf_counter()
        textures_to_delete = []
        new_queue = []
        for item in self._fade_queue:
            start_frame = _resolve_start_frame(item)
            frames_elapsed = current_frame - start_frame
            if fade_duration_frames > 0.0 and frames_elapsed < fade_duration_frames:
                new_queue.append(item)
            else:
                # Texture has faded out - delete it
                textures_to_delete.append(item['texture'])
        
        self._fade_queue = new_queue
        
        # Delete expired textures
        for texture_id in textures_to_delete:
            try:
                if GL.glIsTexture(texture_id):
                    GL.glDeleteTextures([texture_id])
                    logger.debug(f"[visual] Deleted expired fade texture {texture_id}")
            except Exception as e:
                logger.warning(f"[visual] Failed to delete expired fade texture: {e}")
        cleanup_ms = (time.perf_counter() - cleanup_start) * 1000.0
        if cleanup_ms >= _FADE_CLEANUP_WARN_MS:
            self._record_fade_perf_event("cleanup", cleanup_ms, queue_size=len(self._fade_queue))
        
        # Log fade state periodically for debugging
        if self.frame_count % 10 == 0 and (self._fade_queue or self._fade_active):
            logger.info(
                "[fade] State: queue_size=%d, fade_active=%s, fade_progress=%.2f",
                len(self._fade_queue),
                self._fade_active,
                self._fade_progress,
            )
        
        # Update main fade progress if active
        if self._fade_active:
            frames_elapsed = current_frame - getattr(self, '_fade_frame_start', current_frame)
            if fade_duration_frames > 0.0:
                self._fade_progress = min(1.0, frames_elapsed / fade_duration_frames)
            else:
                self._fade_progress = 1.0

            # End fade when complete
            if self._fade_progress >= 1.0:
                self._fade_active = False
                # CRITICAL: Delete old texture after fade completes (memory leak fix!)
                if self._fade_old_texture is not None:
                    try:
                        if GL.glIsTexture(self._fade_old_texture):
                            GL.glDeleteTextures([self._fade_old_texture])
                            logger.debug(f"[visual] Deleted old texture {self._fade_old_texture} after fade")
                    except Exception as e:
                        logger.warning(f"[visual] Failed to delete old fade texture: {e}")
                self._fade_old_texture = None
                elapsed_seconds = frames_elapsed / 60.0
                logger.info(f"[fade] Fade complete after {elapsed_seconds:.2f}s")
        
        # Track prior blend state so we can restore spiral's premultiplied configuration afterwards
        prev_blend_enabled = GL.glIsEnabled(GL.GL_BLEND)
        prev_src_rgb = GL.glGetIntegerv(GL.GL_BLEND_SRC_RGB)
        prev_dst_rgb = GL.glGetIntegerv(GL.GL_BLEND_DST_RGB)
        prev_src_alpha = GL.glGetIntegerv(GL.GL_BLEND_SRC_ALPHA)
        prev_dst_alpha = GL.glGetIntegerv(GL.GL_BLEND_DST_ALPHA)

        fade_active_now = bool(self._fade_queue or self._fade_active)
        if fade_active_now:
            # Begin fade stacks with blending disabled so first layer stamps opaque base
            GL.glDisable(GL.GL_BLEND)
        elif prev_blend_enabled:
            # No fade layers to composite—render background opaquely for optimal throughput
            GL.glDisable(GL.GL_BLEND)
        
        # Lazily build background shader program once
        if not self._background_program or not GL.glIsProgram(self._background_program):
            try:
                self._background_program = self._build_background_program()
            except Exception as e:
                logger.error(f"[visual] Failed to build background shader: {e}")
                return
        
        # Use background shader
        GL.glUseProgram(self._background_program)

        zoom_multiplier = float(getattr(self, "_background_zoom_multiplier", 1.0) or 1.0)
        zoom_multiplier = max(0.05, min(20.0, zoom_multiplier))
        
        # Set common uniforms
        loc = GL.glGetUniformLocation(self._background_program, 'uResolution')
        if loc >= 0:
            GL.glUniform2f(loc, float(w_px), float(h_px))
        
        # Render all fading textures for ghosting effect (oldest to newest)
        if self._fade_queue:
            fade_layers_start = time.perf_counter()
            layers_drawn = 0
            first_layer = True

            for item in list(self._fade_queue):
                start_frame = _resolve_start_frame(item)
                frames_elapsed = current_frame - start_frame
                fade_progress = min(1.0, frames_elapsed / fade_duration_frames) if fade_duration_frames > 0 else 1.0
                opacity = 1.0 - fade_progress  # Fade out old texture

                if opacity <= 0.01 or not GL.glIsTexture(item['texture']):
                    continue

                if not first_layer:
                    GL.glEnable(GL.GL_BLEND)
                    GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glBindTexture(GL.GL_TEXTURE_2D, item['texture'])

                loc = GL.glGetUniformLocation(self._background_program, 'uTexture')
                if loc >= 0:
                    GL.glUniform1i(loc, 0)

                loc = GL.glGetUniformLocation(self._background_program, 'uZoom')
                if loc >= 0:
                    GL.glUniform1f(loc, float(item['zoom']) * zoom_multiplier)

                loc = GL.glGetUniformLocation(self._background_program, 'uOffset')
                if loc >= 0:
                    offset = getattr(self, '_background_offset', [0.0, 0.0])
                    GL.glUniform2f(loc, offset[0], offset[1])

                loc = GL.glGetUniformLocation(self._background_program, 'uKaleidoscope')
                if loc >= 0:
                    kaleidoscope = getattr(self, '_background_kaleidoscope', False)
                    GL.glUniform1i(loc, 1 if kaleidoscope else 0)

                loc = GL.glGetUniformLocation(self._background_program, 'uImageSize')
                if loc >= 0:
                    GL.glUniform2f(loc, float(item['width']), float(item['height']))

                loc = GL.glGetUniformLocation(self._background_program, 'uOpacity')
                if loc >= 0:
                    GL.glUniform1f(loc, opacity)

                self.vao.bind()
                GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
                self.vao.release()

                layers_drawn += 1
                first_layer = False

            # Remove invalid or completed fade textures (mirrors LoomCompositor)
            self._fade_queue = [
                item for item in self._fade_queue
                if GL.glIsTexture(item['texture'])
                and fade_duration_frames > 0.0
                and (current_frame - _resolve_start_frame(item)) < fade_duration_frames
            ]

            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._background_texture)

            loc = GL.glGetUniformLocation(self._background_program, 'uTexture')
            if loc >= 0:
                GL.glUniform1i(loc, 0)

            loc = GL.glGetUniformLocation(self._background_program, 'uZoom')
            if loc >= 0:
                GL.glUniform1f(loc, float(self._background_zoom) * zoom_multiplier)

            loc = GL.glGetUniformLocation(self._background_program, 'uOffset')
            if loc >= 0:
                offset = getattr(self, '_background_offset', [0.0, 0.0])
                GL.glUniform2f(loc, offset[0], offset[1])

            loc = GL.glGetUniformLocation(self._background_program, 'uKaleidoscope')
            if loc >= 0:
                kaleidoscope = getattr(self, '_background_kaleidoscope', False)
                GL.glUniform1i(loc, 1 if kaleidoscope else 0)

            loc = GL.glGetUniformLocation(self._background_program, 'uImageSize')
            if loc >= 0:
                GL.glUniform2f(loc, float(self._background_image_width), float(self._background_image_height))

            loc = GL.glGetUniformLocation(self._background_program, 'uOpacity')
            if loc >= 0:
                opacity = self._fade_progress if self._fade_active else 1.0
                GL.glUniform1f(loc, opacity)

            self.vao.bind()
            GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
            self.vao.release()

            layer_ms = (time.perf_counter() - fade_layers_start) * 1000.0
            if layer_ms >= _FADE_LAYER_WARN_MS:
                self._record_fade_perf_event("layers", layer_ms, queue_size=len(self._fade_queue), layers_drawn=layers_drawn)
        else:
            # No fade - render normally
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._background_texture)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uTexture')
            if loc >= 0:
                GL.glUniform1i(loc, 0)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uZoom')
            if loc >= 0:
                GL.glUniform1f(loc, float(self._background_zoom) * zoom_multiplier)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uOffset')
            if loc >= 0:
                offset = getattr(self, '_background_offset', [0.0, 0.0])
                GL.glUniform2f(loc, offset[0], offset[1])
            
            loc = GL.glGetUniformLocation(self._background_program, 'uKaleidoscope')
            if loc >= 0:
                kaleidoscope = getattr(self, '_background_kaleidoscope', False)
                GL.glUniform1i(loc, 1 if kaleidoscope else 0)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uImageSize')
            if loc >= 0:
                GL.glUniform2f(loc, float(self._background_image_width), float(self._background_image_height))
            
            loc = GL.glGetUniformLocation(self._background_program, 'uOpacity')
            if loc >= 0:
                GL.glUniform1f(loc, 1.0)  # Full opacity
            
            # Draw fullscreen quad
            self.vao.bind()
            GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        
        # Restore prior blend state for spiral rendering
        if prev_blend_enabled:
            GL.glEnable(GL.GL_BLEND)
        else:
            GL.glDisable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(prev_src_rgb, prev_dst_rgb, prev_src_alpha, prev_dst_alpha)
        total_bg_ms = (time.perf_counter() - render_start) * 1000.0
        if total_bg_ms >= _BACKGROUND_RENDER_WARN_MS:
            self._record_fade_perf_event("total", total_bg_ms, queue_size=len(self._fade_queue))
        self._last_background_render_frame = self.frame_count
    
    def cleanup(self):
        """Clean up OpenGL resources"""
        try:
            if self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass
            
        try:
            if self.vao and self.vao.isCreated():
                self.vao.destroy()
        except Exception:
            pass
        try:
            if self.vbo and self.vbo.isCreated():
                self.vbo.destroy()
        except Exception:
            pass
        try:
            if self.ebo and self.ebo.isCreated():
                self.ebo.destroy()
        except Exception:
            pass
        try:
            if self.program_id:
                GL.glDeleteProgram(self.program_id)
                self.program_id = None
        except Exception:
            pass
            
        self.available = False
        logger.info("[spiral.trace] LoomWindowCompositor cleaned up")

    # --- Duplicate/mirror support: read the current framebuffer as QImage ---
    def get_framebuffer_image(self):  # parity with widget compositor API
        """Return a QImage of the current window framebuffer for duplication.

        Uses QOpenGLWindow.grabFramebuffer() which handles the correct buffer
        selection internally on this platform window type.
        """
        try:
            # Ensure window is exposed and initialized; otherwise grabbing may fail
            if not self.isExposed() or not self.initialized or not self.available:
                return None
            img = self.grabFramebuffer()  # QImage
            try:
                # Normalize DPR similar to widget compositor logic
                dpr = getattr(self, 'devicePixelRatioF', lambda: 1.0)()
                if hasattr(img, 'setDevicePixelRatio'):
                    img.setDevicePixelRatio(float(dpr))
            except Exception:
                pass
            if img and not img.isNull():
                logger.info(f"[spiral.trace] window get_framebuffer_image: VALID {img.width()}x{img.height()} dpr={getattr(img,'devicePixelRatio',lambda:1.0)():.2f}")
                return img
            logger.warning("[spiral.trace] window get_framebuffer_image: null image")
            return None
        except Exception as e:
            logger.error(f"[spiral.trace] window get_framebuffer_image error: {e}")
            return None
    
    def closeEvent(self, event):
        """Handle window close"""
        self.cleanup()
        super().closeEvent(event)
    
    def showEvent(self, event):
        """Handle window show - ensure it appears on top immediately"""
        if self._target_screen is not None:
            try:
                self.fit_to_screen(self._target_screen)
            except Exception as exc:
                logger.warning(f"[spiral.trace] fit_to_screen during showEvent failed: {exc}")
        elif self._last_screen_geometry is not None:
            try:
                x, y, w, h = self._last_screen_geometry
                self.setGeometry(x, y, w, h)
            except Exception:
                pass
            self._apply_native_geometry(self._last_native_geometry or self._last_screen_geometry)
            native_rect = self._get_native_geometry()
            logger.info(
                f"[spiral.trace] showEvent reapplied cached logical={self._last_screen_geometry} "
                f"native_target={self._last_native_geometry}, native_current={native_rect}"
            )
        logger.info("[spiral.trace] ===== COMPOSITOR SHOWEVENT TRIGGERED =====")
        logger.info(f"[spiral.trace] Event accepted: {event.isAccepted()}")
        logger.info(f"[spiral.trace] Window visible: {self.isVisible()}")
        logger.info(f"[spiral.trace] Window size: {self.width()}x{self.height()}")
        logger.info(f"[spiral.trace] Window position: ({self.x()}, {self.y()})")
        logger.info(f"[spiral.trace] Window ID: {self.winId()}")
        
        super().showEvent(event)
        # Force window to top immediately when shown
        self.raise_()
        self.requestActivate()
        
        # Use Windows API for stronger topmost behavior and layered/click-through styles
        self._force_topmost_windows()
        self._apply_win32_layered_styles()
        
        # CRITICAL FIX: If transparent swap already happened, restore alpha immediately
        if self._first_transparent_swap_done:
            logger.info("[spiral.trace] Transparent swap already done, restoring alpha to 255 immediately")
            self._set_layered_alpha(255)
        else:
            # Keep layered alpha at 0 until transparent swap done
            try:
                self._set_layered_alpha(0)
                self._refresh_win32_styles()
            except Exception:
                pass
            # Schedule the initial transparent swap ASAP
            try:
                QTimer.singleShot(0, self._initial_transparent_swap)
            except Exception:
                pass
        
        # Refresh styles to apply changes
        self._refresh_win32_styles()
        # Optionally schedule a one-time sneaky click to force OS composite refresh
        try:
            # Enabled by default; set MESMERGLASS_SNEAKY_CLICK=0/false/off to disable.
            if os.environ.get("MESMERGLASS_SNEAKY_CLICK", "1") not in ("0", "false", "False", "off"):
                # Default delay 250ms after show (1/4 second);
                # configurable via MESMERGLASS_SNEAKY_CLICK_DELAY_MS
                try:
                    delay_ms = int(os.environ.get("MESMERGLASS_SNEAKY_CLICK_DELAY_MS", "250"))
                except Exception:
                    delay_ms = 250
                delay_ms = max(0, min(5000, delay_ms))
                QTimer.singleShot(delay_ms, self._sneaky_click_bottom)
        except Exception:
            pass
        
        logger.info("[spiral.trace] LoomWindowCompositor.showEvent: Window activated and raised to top")

    def keyPressEvent(self, event):
        """Handle keyboard input - ESC to hide compositor"""
        from PyQt6.QtCore import Qt
        if event.key() == Qt.Key.Key_Escape:
            logger.info("[compositor] ESC pressed - hiding compositor")
            self.set_active(False)
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def exposeEvent(self, event):
        """On first exposure, re-apply styles and schedule a repaint to avoid black frame."""
        super().exposeEvent(event)
        if not self.isExposed():
            return
        # Refresh styles each time we get exposed (robust against OS transitions)
        self._apply_win32_layered_styles()
        self._force_topmost_windows()
        self._refresh_win32_styles()
        # Perform a one-time transparent clear/swap before any normal paint to avoid initial black
        self._initial_transparent_swap()
        if not self._first_expose_handled:
            self._first_expose_handled = True
            try:
                QTimer.singleShot(0, self.update)
            except Exception:
                pass

    def _refresh_win32_styles(self):
        """Force Windows to re-evaluate styles without moving/resizing/showing."""
        if sys.platform != "win32" or not ctypes:
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
            try:
                ctypes.windll.user32.UpdateWindow(hwnd)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[spiral.trace] _refresh_win32_styles failed: {e}")

    def _set_layered_alpha(self, alpha: int):
        """Set per-window layered alpha (0..255) if WS_EX_LAYERED is active."""
        if sys.platform != "win32" or not ctypes:
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            LWA_ALPHA = 0x02
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, int(max(0, min(255, alpha))), LWA_ALPHA)
        except Exception as e:
            logger.warning(f"[spiral.trace] _set_layered_alpha({alpha}) failed: {e}")

    def _apply_win32_layered_styles(self):
        """Ensure WS_EX_LAYERED is set for per-pixel alpha blending.
        NOTE: WS_EX_TRANSPARENT removed - it makes window invisible on some systems.
        Click-through is handled by Qt's WindowTransparentForInput flag instead.
        Called multiple times safely (idempotent)."""
        if sys.platform != "win32" or not ctypes:
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            # WS_EX_TRANSPARENT = 0x00000020  # REMOVED - causes invisibility issues
            WS_EX_TOOLWINDOW = 0x00000080
            LWA_ALPHA = 0x02
            hwnd = int(self.winId())
            if not hwnd:
                return
            # Get/Set extended styles - ONLY layered and toolwindow
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = style | WS_EX_LAYERED | WS_EX_TOOLWINDOW  # Removed WS_EX_TRANSPARENT
            if new_style != style:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            # Ensure alpha=255 (fully opaque) at the window level so per-pixel alpha shows through
            try:
                ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[spiral.trace] _apply_win32_layered_styles failed: {e}")

    def _restore_previous_context(self, previous_ctx: Optional[QOpenGLContext], previous_surface) -> None:
        """Restore whichever context/surface pair owned GL before makeCurrent()."""
        try:
            if previous_ctx and previous_surface:
                previous_ctx.makeCurrent(previous_surface)
            else:
                current_ctx = self.context()
                if current_ctx:
                    current_ctx.doneCurrent()
        except Exception as exc:
            logger.debug(f"[Text] Context restore skipped: {exc}")

    # ===== TEXT OVERLAY RENDERING =====
    
    def add_text_texture(self, texture_data: 'np.ndarray', x: float = 0.5, y: float = 0.5, 
                        alpha: float = 1.0, scale: float = 1.0):
        """Add a text overlay texture.
        
        Args:
            texture_data: RGBA image data (numpy array from TextRenderer)
            x: Horizontal position (0.0 = left, 1.0 = right, 0.5 = center)
            y: Vertical position (0.0 = bottom, 1.0 = top, 0.5 = center)
            alpha: Text opacity (0.0 - 1.0)
            scale: Text scale multiplier
        
        Returns:
            Index of added texture (for updating/removing)
        """
        from OpenGL import GL
        import numpy as np
        
        if not self.initialized:
            logger.warning("[Text] Cannot add text texture: compositor not initialized")
            return -1
        
        previous_ctx = QOpenGLContext.currentContext()
        previous_surface = previous_ctx.surface() if previous_ctx else None
        self.makeCurrent()
        try:
            height, width = texture_data.shape[:2]

            tex_id = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)

            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                GL.GL_RGBA,
                width,
                height,
                0,
                GL.GL_RGBA,
                GL.GL_UNSIGNED_BYTE,
                texture_data,
            )

            text_info = (tex_id, width, height, x, y, alpha, scale)
            self._text_textures.append(text_info)

            logger.debug(
                f"[Text] Added texture {tex_id} ({width}x{height}) at pos=({x:.2f}, {y:.2f}) alpha={alpha:.2f} scale={scale:.2f}"
            )

            summary_count = self._text_texture_sampler.record()
            if summary_count:
                logger.info(
                    "[Text] Added %d textures in last %.1fs (active=%d)",
                    summary_count,
                    self._text_texture_sampler.interval_s,
                    len(self._text_textures),
                )

            return len(self._text_textures) - 1
        finally:
            self._restore_previous_context(previous_ctx, previous_surface)

    def set_virtual_screen_size(self, width: Optional[int], height: Optional[int]) -> None:
        """Override the logical screen size used for text scaling."""
        if width and height and width > 0 and height > 0:
            self._virtual_screen_size = (int(width), int(height))
        else:
            self._virtual_screen_size = None

    def get_target_screen_size(self) -> tuple[int, int]:
        """Return virtual override when set, otherwise window size."""
        if self._virtual_screen_size:
            return self._virtual_screen_size
        width = int(self.width()) if self.width() else 0
        height = int(self.height()) if self.height() else 0
        if width <= 0 or height <= 0:
            return (1920, 1080)
        return (width, height)
    
    def update_text_transform(self, index: int, x: float = None, y: float = None, 
                             alpha: float = None, scale: float = None):
        """Update text transform properties.
        
        Args:
            index: Text texture index (from add_text_texture)
            x, y: New position (None = keep current)
            alpha: New opacity (None = keep current)
            scale: New scale (None = keep current)
        """
        if index < 0 or index >= len(self._text_textures):
            return
        
        tex_id, width, height, old_x, old_y, old_alpha, old_scale = self._text_textures[index]
        
        new_x = x if x is not None else old_x
        new_y = y if y is not None else old_y
        new_alpha = alpha if alpha is not None else old_alpha
        new_scale = scale if scale is not None else old_scale
        
        self._text_textures[index] = (tex_id, width, height, new_x, new_y, new_alpha, new_scale)
    
    def remove_text_texture(self, index: int):
        """Remove a text texture.
        
        Args:
            index: Text texture index (from add_text_texture)
        """
        from OpenGL import GL
        
        if index < 0 or index >= len(self._text_textures):
            return
        
        previous_ctx = QOpenGLContext.currentContext()
        previous_surface = previous_ctx.surface() if previous_ctx else None
        self.makeCurrent()
        try:
            tex_id = self._text_textures[index][0]
            if GL.glIsTexture(tex_id):
                GL.glDeleteTextures([tex_id])

            self._text_textures.pop(index)
            logger.debug(f"[Text] Removed texture {tex_id}")
        finally:
            self._restore_previous_context(previous_ctx, previous_surface)
    
    def clear_text_textures(self):
        """Remove all text textures."""
        from OpenGL import GL
        
        if not self.initialized:
            return
        
        previous_ctx = QOpenGLContext.currentContext()
        previous_surface = previous_ctx.surface() if previous_ctx else None
        self.makeCurrent()
        try:
            for tex_id, _, _, _, _, _, _ in self._text_textures:
                if GL.glIsTexture(tex_id):
                    GL.glDeleteTextures([tex_id])

            self._text_textures.clear()
            logger.debug("[Text] Cleared all text textures")
        finally:
            self._restore_previous_context(previous_ctx, previous_surface)

    def _render_text_overlays(self, screen_width: int, screen_height: int):
        """Render all text overlays on top of everything.
        
        Called from paintGL() after spiral rendering.
        
        Args:
            screen_width: Screen width in logical pixels
            screen_height: Screen height in logical pixels
        """
        from OpenGL import GL
        
        # Throttled logging
        self._text_log_counter += 1
        
        if not self._text_textures:
            # Log once per session if no textures (helps debug)
            if self._text_log_counter == 1:
                logger.info("[Text] No text textures to render")
            return
        
        # Guard: skip if invalid dimensions
        if screen_width <= 0 or screen_height <= 0:
            if self.frame_count <= 20:
                logger.warning(f"[Text] DEBUG: Invalid window dimensions: {screen_width}x{screen_height} - skipping text render (is_primary={self.is_primary})")
            return
        
        target_width, target_height = self.get_target_screen_size()
        if target_width <= 0 or target_height <= 0:
            if self.frame_count <= 20:
                logger.warning("[Text] DEBUG: Invalid target screen size - skipping text render")
            return
        
        # Get device pixel ratio for proper scaling
        dpr = self.devicePixelRatioF()
        device_width = max(1, int(screen_width * dpr))
        device_height = max(1, int(screen_height * dpr))
        
        # DEBUG: Log dimensions being used for text rendering (first 20 frames)
        if self.frame_count <= 20 and (self._text_trace or logger.isEnabledFor(logging.DEBUG)):
            self._log_text_debug(
                f"[Text] DEBUG: Rendering {len(self._text_textures)} text texture(s) on {screen_width}x{screen_height} logical, "
                f"{device_width}x{device_height} device pixels, virtual target {target_width}x{target_height}, DPR={dpr:.2f} (is_primary={self.is_primary})"
            )
        
        # Build text shader if needed
        if self._text_program is None:
            try:
                self._text_program = self._build_text_shader()
                logger.info(f"[Text] Built text shader program: {self._text_program}")
            except Exception as e:
                logger.error(f"[Text] Failed to build text shader: {e}", exc_info=True)
                return
        
        # Verify program is valid
        if not GL.glIsProgram(self._text_program):
            logger.error(f"[Text] Invalid text program: {self._text_program}")
            self._text_program = None
            return
        
        # Use text shader
        GL.glUseProgram(self._text_program)
        
        # DEBUG: Log GL state (first 5 frames only, once per compositor)
        if (
            self.frame_count <= 5
            and self._text_log_counter <= 5
            and (self._text_trace or logger.isEnabledFor(logging.DEBUG))
        ):
            import ctypes
            active_program = GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM)
            active_texture = GL.glGetIntegerv(GL.GL_ACTIVE_TEXTURE)
            blend_src = GL.glGetIntegerv(GL.GL_BLEND_SRC_ALPHA)
            blend_dst = GL.glGetIntegerv(GL.GL_BLEND_DST_ALPHA)
            self._log_text_debug(
                f"[Text] DEBUG: GL state - program={active_program} texture_unit={active_texture} blend={blend_src}/{blend_dst} (is_primary={self.is_primary})"
            )
        
        # Disable depth test for text overlay (render on top)
        GL.glDisable(GL.GL_DEPTH_TEST)
        
        # Use premultiplied alpha blending for proper transparency
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        
        # Render each text texture
        for idx, (tex_id, tex_width, tex_height, x, y, alpha, scale) in enumerate(self._text_textures):
            # Skip invisible text
            if alpha < 0.01:
                continue
            
            # Re-bind shader and blending for each texture
            GL.glUseProgram(self._text_program)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
            
            # Calculate quad size using DEVICE pixels (not logical pixels)
            # This ensures consistent rendering across different DPI settings
            text_display_width = tex_width * scale
            text_display_height = tex_height * scale
            
            # Convert to normalized device coordinates using the virtual target dimensions
            quad_width = (text_display_width / target_width) * 2.0
            quad_height = (text_display_height / target_height) * 2.0
            
            # SAFETY: Clamp quad sizes to prevent runaway geometry
            # Valid NDC range is [-2, 2] but we clamp to [-3, 3] for safety margin
            quad_width = max(-3.0, min(3.0, quad_width))
            quad_height = max(-3.0, min(3.0, quad_height))
            
            # DEBUG: Log text quad calculations (first 20 frames only)
            if self.frame_count <= 20 and (self._text_trace or logger.isEnabledFor(logging.DEBUG)):
                self._log_text_debug(
                    f"[Text] DEBUG: Text {idx} quad: tex={tex_width}x{tex_height} scale={scale:.2f} "
                    f"display={text_display_width:.0f}x{text_display_height:.0f} "
                    f"device={device_width}x{device_height} "
                    f"quad_ndc={quad_width:.4f}x{quad_height:.4f} (is_primary={self.is_primary})"
                )
            
            # Convert position from (0-1) to NDC (-1 to 1)
            # Input x,y is the CENTER of the quad
            center_x = (x * 2.0 - 1.0)
            center_y = (y * 2.0 - 1.0)
            
            # Convert from center to top-left corner
            quad_x = center_x - quad_width * 0.5
            quad_y = center_y - quad_height * 0.5
            
            # Set uniforms
            loc = GL.glGetUniformLocation(self._text_program, 'uPosition')
            if loc >= 0:
                GL.glUniform2f(loc, quad_x, quad_y)
            
            loc = GL.glGetUniformLocation(self._text_program, 'uSize')
            if loc >= 0:
                GL.glUniform2f(loc, quad_width, quad_height)
            
            loc = GL.glGetUniformLocation(self._text_program, 'uAlpha')
            if loc >= 0:
                final_alpha = alpha * self._text_opacity
                GL.glUniform1f(loc, final_alpha)
            
            # Bind texture
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            loc = GL.glGetUniformLocation(self._text_program, 'uTexture')
            if loc >= 0:
                GL.glUniform1i(loc, 0)
            
            # Draw quad using Qt VAO wrapper
            self.vao.bind()
            GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
            self.vao.release()
        
        GL.glUseProgram(0)
    
    def _build_text_shader(self) -> int:
        """Build shader program for text overlay rendering.
        
        Returns:
            OpenGL program ID
        """
        from OpenGL import GL
        
        vs_src = """
#version 330 core

layout(location = 0) in vec2 aPosition;
layout(location = 1) in vec2 aTexCoord;

out vec2 vTexCoord;

uniform vec2 uPosition;
uniform vec2 uSize;

void main() {
    vec2 quadPos = (aPosition + 1.0) * 0.5;
    vec2 pos = uPosition + quadPos * uSize;
    gl_Position = vec4(pos, 0.0, 1.0);
    vTexCoord = vec2(aTexCoord.x, 1.0 - aTexCoord.y);
}
"""
        
        fs_src = """
#version 330 core

in vec2 vTexCoord;
out vec4 FragColor;

uniform sampler2D uTexture;
uniform float uAlpha;

void main() {
    vec4 texColor = texture(uTexture, vTexCoord);
    FragColor = vec4(texColor.rgb, texColor.a * uAlpha);
}
"""
        
        # Compile shaders
        vs = self._compile_shader(vs_src, GL.GL_VERTEX_SHADER)
        fs = self._compile_shader(fs_src, GL.GL_FRAGMENT_SHADER)
        
        # Link program
        prog = GL.glCreateProgram()
        GL.glAttachShader(prog, vs)
        GL.glAttachShader(prog, fs)
        GL.glLinkProgram(prog)
        
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(prog).decode('utf-8', 'ignore')
            raise RuntimeError(f"Text shader program link failed: {log}")
        
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)
        
        logger.info(f"[Text] Built text shader program: {prog}")
        return int(prog)
    
    def _compile_shader(self, src: str, shader_type: int) -> int:
        """Compile a shader from source.
        
        Args:
            src: Shader source code
            shader_type: GL_VERTEX_SHADER or GL_FRAGMENT_SHADER
        
        Returns:
            Compiled shader ID
        """
        from OpenGL import GL
        
        shader = GL.glCreateShader(shader_type)
        GL.glShaderSource(shader, src)
        GL.glCompileShader(shader)
        
        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(shader).decode('utf-8', 'ignore')
            shader_name = "vertex" if shader_type == GL.GL_VERTEX_SHADER else "fragment"
            raise RuntimeError(f"Text {shader_name} shader compilation failed: {log}")
        
        return shader

    # --- Optional: sneaky click to trigger OS composition refresh ---
    def _sneaky_click_bottom(self):  # pragma: no cover - platform interaction
        if sys.platform != "win32" or not ctypes:
            return
        if getattr(self, "_sneaky_clicked", False):
            return
        try:
            # Resolve target: PRIMARY screen, bottom-left origin. Click at (100, 0) by default
            # relative to availableGeometry (avoids taskbar). Users can override via:
            # MESMERGLASS_SNEAKY_CLICK_OFFSET_X and _Y (bottom-left origin).
            primary = QGuiApplication.primaryScreen()
            screen = primary or self.screen()
            if screen is None:
                return
            # Work area to avoid taskbar/start
            try:
                geom = screen.availableGeometry()
            except Exception:
                geom = screen.geometry()
            # Read offsets (bottom-left origin: y=0 is bottom edge)
            try:
                off_x = int(os.environ.get("MESMERGLASS_SNEAKY_CLICK_OFFSET_X", "100"))
            except Exception:
                off_x = 100
            try:
                off_y = int(os.environ.get("MESMERGLASS_SNEAKY_CLICK_OFFSET_Y", "0"))
            except Exception:
                off_y = 0
            # Clamp within the work area, keep a 2px inset
            left = geom.x() + 2
            right = geom.x() + geom.width() - 2
            bottom = geom.y() + geom.height() - 2
            top = geom.y() + 2
            target_x = max(left, min(right, geom.x() + off_x))
            # Convert bottom-left y (0 at bottom) to screen coords (top-left origin)
            target_y = max(top, min(bottom, bottom - off_y))

            # Save current cursor pos
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

            # Move to target and click
            ctypes.windll.user32.SetCursorPos(int(target_x), int(target_y))
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

            # Restore cursor
            ctypes.windll.user32.SetCursorPos(pt.x, pt.y)
            self._sneaky_clicked = True
            logger.info("[spiral.trace] Performed sneaky click at bottom of screen to refresh composition")
        except Exception as e:
            logger.warning(f"[spiral.trace] _sneaky_click_bottom failed: {e}")


def probe_window_available() -> bool:
    """Check if QOpenGLWindow support is available"""
    try:
        from PyQt6.QtOpenGL import QOpenGLWindow
        return True
    except ImportError:
        return False
