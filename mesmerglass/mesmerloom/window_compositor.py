"""
MesmerLoom QOpenGLWindow-based compositor.
Eliminates Qt widget FBO blit artifacts by using direct window rendering.
"""

import logging
import time
import os
from typing import Optional, Dict, Union
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtOpenGL import QOpenGLWindow, QOpenGLBuffer, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PyQt6.QtGui import QSurfaceFormat
from OpenGL import GL
import numpy as np

logger = logging.getLogger(__name__)

class LoomWindowCompositor(QOpenGLWindow):
    """
    QOpenGLWindow-based spiral compositor.
    Eliminates Qt widget FBO blit artifacts completely.
    """
    
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
        
        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        
        # Set window properties for overlay behavior
        self.setFlags(Qt.WindowType.FramelessWindowHint | 
                     Qt.WindowType.WindowStaysOnTopHint |
                     Qt.WindowType.Tool)
        
        # Configure surface format for maximum compatibility
        format = QSurfaceFormat()
        format.setVersion(3, 3)
        format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        format.setDepthBufferSize(24)
        format.setStencilBufferSize(8)
        format.setSamples(0)  # No MSAA to avoid artifacts
        format.setAlphaBufferSize(0)  # No alpha buffer for opaque presentation
        format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        self.setFormat(format)
        
        logger.info(f"[spiral.trace] LoomWindowCompositor.__init__ called: director={director}")
    
    def initializeGL(self):
        """Initialize OpenGL resources"""
        logger.info("[spiral.trace] LoomWindowCompositor.initializeGL called")
        
        try:
            # Print OpenGL info
            version = GL.glGetString(GL.GL_VERSION).decode()
            renderer = GL.glGetString(GL.GL_RENDERER).decode()
            vendor = GL.glGetString(GL.GL_VENDOR).decode()
            logger.info(f"[spiral.trace] OpenGL version: {version}")
            logger.info(f"[spiral.trace] OpenGL renderer: {renderer}")
            logger.info(f"[spiral.trace] OpenGL vendor: {vendor}")
            
            # Build shader program
            self._build_shader_program()
            
            # Setup geometry
            self._setup_geometry()
            
            # Configure optimal OpenGL state
            GL.glDisable(GL.GL_BLEND)        # No blending - we do opacity in shader
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
    
    def paintGL(self):
        """Render the spiral directly to window - no FBO blit!"""
        if not self.initialized or not self.program_id or not self._active:
            return
            
        self.frame_count += 1
        
        # Setup viewport
        GL.glViewport(0, 0, self.width(), self.height())
        
        # Clear with background color
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)  # Pure black background
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        # Use shader program
        GL.glUseProgram(self.program_id)
        
        # Get window size for fallback
        w_px, h_px = self.width(), self.height()
        
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
            
            self.director.update()
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
            if loc >= 0: 
                GL.glUniform1f(loc, float(val))
        def _seti(name, val):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc >= 0: 
                GL.glUniform1i(loc, int(val))
        def _set2(name, val: tuple):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc >= 0: 
                GL.glUniform2f(loc, float(val[0]), float(val[1]))
        def _set3(name, val: tuple):
            loc = GL.glGetUniformLocation(self.program_id, name)
            if loc >= 0: 
                GL.glUniform3f(loc, float(val[0]), float(val[1]), float(val[2]))
        
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
        
        # Set QOpenGLWindow-specific defaults (same as original compositor)
        _seti('uInternalOpacity', 1)  # Use internal opacity blending for QOpenGLWindow
        _set3('uBackgroundColor', (0.0, 0.0, 0.0))  # Pure black background for better contrast
        _seti('uBlendMode', getattr(self, '_blend_mode', 0))  # Default blend mode
        _seti('uTestOpaqueMode', 0)  # Normal rendering mode
        _seti('uTestLegacyBlend', 0)  # Use modern blending
        _seti('uSRGBOutput', 0)  # Let OpenGL handle sRGB
        
        # Disable GL blending for opaque internal blending (same as original)
        GL.glDisable(GL.GL_BLEND)
        
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
        """Set window opacity (for compatibility with QWidget interface)"""
        # QOpenGLWindow doesn't support window opacity the same way as QWidget
        # For now, just log and ignore - we use internal opacity in shader
        logger.info(f"[spiral.trace] setWindowOpacity({opacity}) called on QOpenGLWindow - using internal opacity")
    
    def set_blend_mode(self, mode: int):
        """Set blend mode (for compatibility)"""
        logger.info(f"[spiral.trace] set_blend_mode({mode}) called - not implemented for QOpenGLWindow")
    
    def set_render_scale(self, scale: float):
        """Set render scale (for compatibility)"""
        logger.info(f"[spiral.trace] set_render_scale({scale}) called - not implemented for QOpenGLWindow")
    
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
    
    def closeEvent(self, event):
        """Handle window close"""
        self.cleanup()
        super().closeEvent(event)


def probe_window_available() -> bool:
    """Check if QOpenGLWindow support is available"""
    try:
        from PyQt6.QtOpenGL import QOpenGLWindow
        return True
    except ImportError:
        return False
