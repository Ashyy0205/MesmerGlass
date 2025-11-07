"""
MesmerLoom QOpenGLWindow-based compositor.
Eliminates Qt widget FBO blit artifacts by using direct window rendering.
"""

import logging
import time
import os
import sys
from typing import Optional, Dict, Union
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtOpenGL import QOpenGLWindow, QOpenGLBuffer, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PyQt6.QtGui import QSurfaceFormat, QColor, QGuiApplication
from OpenGL import GL
import numpy as np

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

class LoomWindowCompositor(QOpenGLWindow):
    """
    QOpenGLWindow-based spiral compositor.
    Eliminates Qt widget FBO blit artifacts completely.
    """
    # Emit after a frame is drawn so duplicate/mirror windows can update
    frame_drawn = pyqtSignal()
    
    def __init__(self, director, parent=None):
        super().__init__(parent)
        self.director = director

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
        # VR safe mirror settings (offscreen FBO tap)
        self._vr_safe = bool(os.environ.get("MESMERGLASS_VR_SAFE") in ("1", "true", "True"))
        self._vr_fbo = None
        self._vr_tex = None
        self._vr_size = (0, 0)
        
        # Background texture support (for Visual Programs)
        self._background_texture = None
        self._background_enabled = False
        self._background_zoom = 1.0
        self._background_image_width = 1920
        self._background_image_height = 1080
        self._background_offset = [0.0, 0.0]  # XY drift offset
        self._background_kaleidoscope = False  # Kaleidoscope mirroring
        self._background_program = None  # Background shader program
        
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
        self._zoom_rate = 0.42  # Zoom rate for exponential mode
        
        # Text rendering support
        self._text_opacity = 1.0  # Global text opacity multiplier

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
            self.create()  # force platform window creation (no show)
        except Exception:
            pass
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

    def _initial_transparent_swap(self):
        """Do a one-time transparent clear/swap as soon as the surface is exposed.
        This prevents the OS from compositing an uninitialized (black) backbuffer
        before our first regular paintGL.
        """
        if self._first_transparent_swap_done:
            return
        if not self.isExposed():
            return
        # Only proceed if a context exists and can be made current early
        ctx = self.context()
        if ctx is None:
            return
        try:
            self.makeCurrent()
        except Exception:
            # Some drivers may not allow this prior to initializeGL; bail out gracefully
            return
        try:
            GL.glViewport(0, 0, max(1, self.width()), max(1, self.height()))
            GL.glClearColor(0.0, 0.0, 0.0, 0.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            try:
                # Swap immediately so DWM sees an all-transparent first frame
                ctx.swapBuffers(self)
            except Exception:
                pass
            self._first_transparent_swap_done = True
            # Restore desired opacity now that we have presented a transparent frame
            try:
                super().setOpacity(self._window_opacity)
            except Exception:
                pass
            # Ensure layered alpha is restored to fully visible
            self._set_layered_alpha(255)
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
                GL.glViewport(0, 0, max(1, self.width()), max(1, self.height()))
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
        GL.glEnableVertexAttribArray(0)  # Position
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, None)
        
        GL.glEnableVertexAttribArray(1)  # Texture coordinates
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, 8)
        
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
    
    def paintGL(self):
        """Render the spiral; if VR safe mode is enabled, render to offscreen FBO then blit to window."""
        if not self.initialized or not self.program_id or not self._active:
            return
            
        self.frame_count += 1
        
        # Setup viewport and optional VR FBO
        w_px, h_px = self.width(), self.height()
        if self._vr_safe:
            self._ensure_vr_fbo(w_px, h_px)
            if self._vr_fbo:
                GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._vr_fbo)
        GL.glViewport(0, 0, w_px, h_px)
        
        # CRITICAL FIX: Clear with transparent background for proper window transparency
        # Using alpha=0.0 makes the background completely transparent to the desktop
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)  # Transparent background - key fix!
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        # Get window size for rendering
        w_px, h_px = self.width(), self.height()
        
        # RENDER BACKGROUND FIRST (images/videos behind spiral)
        try:
            self._render_background(w_px, h_px)
        except Exception as e:
            if self.frame_count <= 3:  # Only log errors on first few frames
                logger.error(f"[visual] Background render failed: {e}")
        
        # Update zoom animation
        try:
            self.update_zoom_animation()
        except Exception:
            pass
        
        # Use spiral shader program
        GL.glUseProgram(self.program_id)
        
        # Update director and get current parameters (same as original compositor)
        try:
            # Get actual screen resolution for fullscreen overlay
            screen = self.screen()
            if screen:
                screen_size = screen.size()
                screen_w, screen_h = screen_size.width(), screen_size.height()
                # Use screen resolution for director (ensures proper fullscreen coverage)
                self.director.set_resolution(screen_w, screen_h)
                if self._trace and self.frame_count <= 3:
                    logger.info(f"[spiral.debug] Frame {self.frame_count}: Using screen resolution {screen_w}x{screen_h} (window: {w_px}x{h_px})")
            else:
                # Fallback to window size if screen detection fails
                self.director.set_resolution(w_px, h_px)
                if self._trace and self.frame_count <= 3:
                    logger.info(f"[spiral.debug] Frame {self.frame_count}: Using window resolution {w_px}x{h_px} (no screen detected)")
            
            # Use fixed dt=1/60 to match Visual Mode Creator's timing (ensures 1:1 parity)
            self.director.update(dt=1/60.0)
            uniforms = self.director.export_uniforms()
            
            # Debug: Check critical values every few frames
            if self.frame_count <= 3:  # Only first 3 frames for startup verification
                logger.info(f"[spiral.debug] Frame {self.frame_count}: intensity={uniforms.get('uIntensity', 'MISSING')}, phase={uniforms.get('uPhase', 'MISSING'):.3f}, arms={uniforms.get('uArms', 'MISSING')}")
                logger.info(f"[spiral.debug] Frame {self.frame_count}: spiralOpacity={uniforms.get('uSpiralOpacity', 'MISSING'):.3f}, resolution={uniforms.get('uResolution', 'MISSING')}")
                
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
        
        # Set core uniforms (same as original compositor approach)
        current_time = time.time() - self.t0
        
        # Use the same resolution logic as director for consistency
        screen = self.screen()
        if screen:
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
            # Debug log rotation_speed uniform value
            if k == 'rotation_speed' and self.frame_count % 120 == 0:
                logger.info(f"[rotation_speed] Sending to shader: {v}")
            if isinstance(v, int): 
                _seti(k, v)
            elif isinstance(v, (tuple, list)):
                if len(v) == 2:
                    _set2(k, v)
                elif len(v) == 3:
                    _set3(k, v)
                else:
                    _set1(k, float(v[0]) if v else 0.0)  # fallback to first element
            else: 
                _set1(k, v)
        
        # Set QOpenGLWindow-specific defaults for transparency
        _seti('uInternalOpacity', 0)  # Use window transparency mode (not internal blending)
        _set3('uBackgroundColor', (0.0, 0.0, 0.0))  # Pure black background for better contrast
        _seti('uBlendMode', getattr(self, '_blend_mode', 0))  # Default blend mode
        _seti('uTestOpaqueMode', 0)  # Normal rendering mode
        _seti('uTestLegacyBlend', 0)  # Use modern blending
        _seti('uSRGBOutput', 0)  # Let OpenGL handle sRGB
        
        # Add window-level opacity control (separate from spiral opacity)
        _set1('uWindowOpacity', getattr(self, '_window_opacity', 1.0))  # Default fully opaque
        if getattr(self, '_frame_count', 0) % 60 == 1:  # Log every 60 frames
            logger.info(f"[spiral.debug] Frame {getattr(self, '_frame_count', 0)}: uWindowOpacity={getattr(self, '_window_opacity', 1.0)}")
        
        # Enable GL blending for transparency (premultiplied alpha)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        
        # Render fullscreen quad
        self.vao.bind()
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        self.vao.release()
        
        GL.glUseProgram(0)
        
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

        # Notify listeners (duplicate/mirror windows) that a new frame is available
        try:
            self.frame_drawn.emit()
        except Exception:
            pass
    
    def resizeGL(self, width, height):
        """Handle window resize"""
        GL.glViewport(0, 0, width, height)
        if self._trace:
            logger.info(f"[spiral.trace] LoomWindowCompositor.resizeGL: {width}x{height}")
    
    def set_active(self, active: bool):
        """Enable/disable rendering"""
        self._active = active
        if self._trace:
            logger.info(f"[spiral.trace] LoomWindowCompositor.set_active: {active}")
    
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
    
    def set_background_texture(self, texture_id: int, zoom: float = 1.0, image_width: int = None, image_height: int = None) -> None:
        """Set background image texture with optional fade transition (Visual Programs support).
        
        Args:
            texture_id: OpenGL texture ID (from texture.upload_image_to_gpu)
            zoom: Zoom factor (1.0 = fit to screen, >1.0 = zoomed in)
            image_width: Original image width (for aspect ratio)
            image_height: Original image height (for aspect ratio)
        """
        # If fade is enabled and we have a current texture, start fade transition
        if self._fade_enabled and self._background_texture is not None and self._background_enabled:
            current_frame = getattr(self, '_frame_counter', 0)
            
            # Add current texture to fade queue for ghosting effect
            self._fade_queue.append({
                'texture': self._background_texture,
                'zoom': self._background_zoom,
                'width': self._background_image_width,
                'height': self._background_image_height,
                'start_frame': current_frame
            })
            
            # Also store in old texture for backward compatibility
            self._fade_old_texture = self._background_texture
            self._fade_old_zoom = self._background_zoom
            self._fade_old_width = self._background_image_width
            self._fade_old_height = self._background_image_height
            self._fade_active = True
            self._fade_progress = 0.0
            self._fade_frame_start = current_frame
            logger.info(f"[fade] Starting fade transition (duration={self._fade_duration:.2f}s, queue_size={len(self._fade_queue)})")
        
        self._background_texture = texture_id
        self._background_zoom = max(0.1, min(5.0, zoom))
        
        if image_width is not None and image_height is not None:
            self._background_image_width = max(1, image_width)
            self._background_image_height = max(1, image_height)
        
        self._background_enabled = True
        logger.info(f"[visual] Background texture set: id={texture_id}, zoom={zoom}, size={image_width}x{image_height}")
    
    def clear_background_texture(self) -> None:
        """Clear background image texture."""
        self._background_texture = None
        self._background_enabled = False
    
    def set_fade_duration(self, duration_seconds: float) -> None:
        """Set fade transition duration for media changes.
        
        Args:
            duration_seconds: Fade duration in seconds (0.0 = instant, 0.5 = half second, etc.)
        """
        self._fade_duration = max(0.0, min(5.0, duration_seconds))
        self._fade_enabled = duration_seconds > 0.0
        logger.info(f"[fade] Fade duration set to {self._fade_duration:.2f}s (enabled={self._fade_enabled})")
        logger.info("[visual] Background texture cleared")
    
    def set_background_zoom(self, zoom: float) -> None:
        """Set background zoom factor."""
        self._background_zoom = max(0.1, min(5.0, zoom))
    
    def start_zoom_animation(self, target_zoom: float = 1.5, start_zoom: float = 1.0, duration_frames: int = 48, mode: str = "exponential", rate: float = None) -> None:
        """Start duration-based zoom-in animation.
        
        Args:
            target_zoom: Final zoom level (clamped to 0.1-5.0)
            start_zoom: Starting zoom level (clamped to 0.1-5.0)
            duration_frames: Number of frames over which to animate (e.g., 48 for images, 300 for videos)
            mode: "exponential" (continuous zoom in/out), "pulse" (wave), "linear" (legacy), "falling" (zoom out)
            rate: Optional explicit zoom rate (overrides auto-calculation)
        """
        # Don't start zoom if disabled (e.g., video focus mode)
        if not self._zoom_enabled:
            return
        
        self._zoom_start = max(0.1, min(5.0, start_zoom))
        self._zoom_target = max(0.1, min(5.0, target_zoom))
        self._zoom_current = self._zoom_start
        self._zoom_duration_frames = max(1, duration_frames)
        self._zoom_elapsed_frames = 0
        self._zoom_start_time = time.time()  # Reset time for consistent speed
        
        # Store zoom mode for update calculations
        self._zoom_mode = mode if mode in ["exponential", "pulse", "linear", "falling"] else "exponential"
        
        # Set explicit zoom rate if provided, otherwise use default calculation
        if rate is not None:
            self._zoom_rate = rate
            # For exponential mode (zoom in), rate should be POSITIVE (zoom value increases)
            # Shader uses / uZoom, so LARGER zoom = shows LESS = visual zoom in
            if mode == "exponential" and self._zoom_rate < 0:
                self._zoom_rate = abs(self._zoom_rate)
            # For falling mode (zoom out), rate should be NEGATIVE (zoom value decreases)
            elif mode == "falling" and self._zoom_rate > 0:
                self._zoom_rate = -self._zoom_rate
        
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
    
    def set_zoom_target(self, target_zoom: float) -> None:
        """Set the maximum zoom target (used for future zoom animations).
        
        Args:
            target_zoom: Maximum zoom level (0.1 to 5.0)
        """
        self._zoom_target = max(0.1, min(5.0, target_zoom))
        logger.info(f"[compositor] Zoom target set to {self._zoom_target}x")
    
    def update_zoom_animation(self) -> None:
        """Update zoom animation (exponential, pulse, falling, or linear modes)."""
        if not self._zoom_animating:
            return
        
        # Increment elapsed frames
        self._zoom_elapsed_frames += 1
        elapsed_time = time.time() - self._zoom_start_time  # Use real time for consistent speed
        
        # Calculate zoom based on mode
        if self._zoom_mode == "exponential":
            # Exponential zoom IN: zoom value increases (shader divides by it)
            # With positive rate, zoom: 1.0 → 1.5 → 2.0 → 3.0
            # Shader /zoom with larger values = see LESS = visual zoom in
            import math
            self._zoom_current = self._zoom_start * math.exp(self._zoom_rate * elapsed_time)
            
            # Reset when zoom gets too large (deep zoom limit)
            if self._zoom_current > 3.0:  # Reset at 3x zoom
                self._zoom_start = 1.0
                self._zoom_current = 1.0
                self._zoom_start_time = time.time()
        
        elif self._zoom_mode == "falling":
            # Falling mode: zoom OUT (zoom value decreases)
            import math
            self._zoom_current = self._zoom_start * math.exp(self._zoom_rate * elapsed_time)  # rate should be negative
            
            # Reset when zoom gets too small (zoomed out limit)
            if self._zoom_current < 0.5:
                self._zoom_start = 1.0
                self._zoom_current = 1.0
                self._zoom_start_time = time.time()
        
        elif self._zoom_mode == "pulse":
            # Pulsing wave: scale = 1.0 + amplitude * sin(rate * time)
            # Creates repeating zoom in/out effect synced to spiral
            import math
            amplitude = 0.3  # 30% zoom variation (1.0 to 1.3)
            self._zoom_current = 1.0 + amplitude * math.sin(self._zoom_rate * elapsed_time)
        
        else:  # "linear" mode (legacy)
            # Linear interpolation from start to target over fixed duration
            progress = min(1.0, self._zoom_elapsed_frames / self._zoom_duration_frames)
            self._zoom_current = self._zoom_start + (self._zoom_target - self._zoom_start) * progress
            
            # Stop animation when complete
            if progress >= 1.0:
                self._zoom_current = self._zoom_target
                self._zoom_animating = False
        
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
                return
            
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
            if new_video and self._fade_enabled and self._background_texture is not None and self._background_enabled:
                current_frame = getattr(self, '_frame_counter', 0)
                
                # Add current texture to fade queue for ghosting effect
                self._fade_queue.append({
                    'texture': self._background_texture,
                    'zoom': self._background_zoom,
                    'width': self._background_image_width,
                    'height': self._background_image_height,
                    'start_frame': current_frame
                })
                
                # Also store in old texture for backward compatibility
                self._fade_old_texture = self._background_texture
                self._fade_old_zoom = self._background_zoom
                self._fade_old_width = self._background_image_width
                self._fade_old_height = self._background_image_height
                self._fade_active = True
                self._fade_progress = 0.0
                self._fade_frame_start = current_frame
                logger.info(f"[fade] Starting fade transition for video (duration={self._fade_duration:.2f}s, queue_size={len(self._fade_queue)})")
                
                # Force texture recreation so we don't overwrite the old texture during fade
                needs_new_texture = True
            
            if needs_new_texture:
                # Delete old texture if it exists
                if self._background_texture is not None and GL.glIsTexture(self._background_texture):
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
            
            # Update state
            self._background_image_width = width
            self._background_image_height = height
            self._background_zoom = max(0.1, min(5.0, zoom))
            self._background_enabled = True
            
        except Exception as e:
            logger.error(f"Failed to upload video frame: {e}")
    
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
    // NO FLIP in vertex shader
    vTexCoord = aTexCoord;
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

    // FINAL FLIP - right before texture sample (to match upload path)
    uv.y = 1.0 - uv.y;

    vec4 color = texture(uTexture, uv);
    
    // Apply opacity for fade transitions
    color.a = uOpacity;
    
    FragColor = color;
}
"""
    
    def _render_background(self, w_px: int, h_px: int) -> None:
        """Render background image/video texture with optional fade transition.
        
        Args:
            w_px: Viewport width
            h_px: Viewport height
        """
        if not self._background_enabled or self._background_texture is None:
            return
        
        # Update fade progress and clean up expired textures in queue
        current_frame = getattr(self, '_frame_counter', 0)
        fade_duration_frames = self._fade_duration * 60.0  # Convert seconds to frames (60 FPS)
        
        # Remove fully faded textures from queue
        self._fade_queue = [
            item for item in self._fade_queue
            if (current_frame - item['start_frame']) < fade_duration_frames
        ]
        
        # Update main fade progress if active
        if self._fade_active:
            frames_elapsed = current_frame - self._fade_frame_start
            
            if fade_duration_frames > 0:
                self._fade_progress = min(1.0, frames_elapsed / fade_duration_frames)
            else:
                self._fade_progress = 1.0
            
            # End fade when complete
            if self._fade_progress >= 1.0:
                self._fade_active = False
                self._fade_old_texture = None
                logger.debug(f"[fade] Fade complete")
        
        # Disable blending for opaque background
        was_blend_enabled = GL.glIsEnabled(GL.GL_BLEND)
        if was_blend_enabled:
            GL.glDisable(GL.GL_BLEND)
        
        # Lazily build background shader program once
        if not self._background_program or not GL.glIsProgram(self._background_program):
            self._background_program = self._build_background_program()
        
        # Use background shader
        GL.glUseProgram(self._background_program)
        
        # Set common uniforms
        loc = GL.glGetUniformLocation(self._background_program, 'uResolution')
        if loc >= 0:
            GL.glUniform2f(loc, float(w_px), float(h_px))
        
        # Render all fading textures for ghosting effect (oldest to newest)
        if self._fade_queue:
            first_layer = True
            
            for item in self._fade_queue:
                frames_elapsed = current_frame - item['start_frame']
                fade_progress = min(1.0, frames_elapsed / fade_duration_frames) if fade_duration_frames > 0 else 1.0
                opacity = 1.0 - fade_progress  # Fade out
                
                # Skip if fully faded
                if opacity <= 0.01:
                    continue
                
                # First layer renders without blending (opaque background)
                # Subsequent layers blend on top
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
                    GL.glUniform1f(loc, item['zoom'])
                
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
                
                # Draw texture
                self.vao.bind()
                GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
                
                first_layer = False
            
            # Enable blending for current texture (blend on top of all fading textures)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            
            # Render current texture (fading in if fade is active)
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._background_texture)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uTexture')
            if loc >= 0:
                GL.glUniform1i(loc, 0)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uZoom')
            if loc >= 0:
                GL.glUniform1f(loc, self._background_zoom)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uImageSize')
            if loc >= 0:
                GL.glUniform2f(loc, float(self._background_image_width), float(self._background_image_height))
            
            loc = GL.glGetUniformLocation(self._background_program, 'uOpacity')
            if loc >= 0:
                # Fade in if fade is active, otherwise full opacity
                opacity = self._fade_progress if self._fade_active else 1.0
                GL.glUniform1f(loc, opacity)
            
            # Draw current texture
            self.vao.bind()
            GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
            
            # Disable blending again
            GL.glDisable(GL.GL_BLEND)
        else:
            # No fade - render normally
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._background_texture)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uTexture')
            if loc >= 0:
                GL.glUniform1i(loc, 0)
            
            loc = GL.glGetUniformLocation(self._background_program, 'uZoom')
            if loc >= 0:
                GL.glUniform1f(loc, self._background_zoom)
            
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
        
        # Re-enable blending for spiral
        if was_blend_enabled:
            GL.glEnable(GL.GL_BLEND)
    
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
        super().showEvent(event)
        # Force window to top immediately when shown
        self.raise_()
        self.requestActivate()
        
        # Use Windows API for stronger topmost behavior and layered/click-through styles
        self._force_topmost_windows()
        self._apply_win32_layered_styles()
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
        """Ensure WS_EX_LAYERED and WS_EX_TRANSPARENT are set, and set LWA_ALPHA=255 for uniform alpha.
        Called multiple times safely (idempotent)."""
        if sys.platform != "win32" or not ctypes:
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            LWA_ALPHA = 0x02
            hwnd = int(self.winId())
            if not hwnd:
                return
            # Get/Set extended styles
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            if new_style != style:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            # Ensure alpha=255 (fully opaque) at the window level so per-pixel alpha shows through
            try:
                ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[spiral.trace] _apply_win32_layered_styles failed: {e}")

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
