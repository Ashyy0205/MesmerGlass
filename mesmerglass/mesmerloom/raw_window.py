"""
Raw QOpenGLWindow implementation to bypass Qt's widget compositor.
This bypasses QOpenGLWidget's FBO blit that may be causing dithering artifacts.
"""

import logging
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtOpenGLWidgets import QOpenGLWindow
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGL import QOpenGLBuffer, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from OpenGL import GL
import numpy as np

logger = logging.getLogger(__name__)

class RawSpiralWindow(QOpenGLWindow):
    """Direct QOpenGLWindow implementation - bypasses QOpenGLWidget FBO blit"""
    
    def __init__(self, director, parent=None):
        super().__init__(parent)
        self.director = director
        self.program = None
        self.vao = None
        self.vbo = None
        self.ebo = None
        self.frame_count = 0
        self.internal_opacity = True  # Force internal opacity mode
        
        # Timer for animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # ~60 FPS
        
        logger.info(f"[spiral.trace] RawSpiralWindow.__init__ called: director={director}")
    
    def initializeGL(self):
        """Initialize OpenGL without Qt widget compositor"""
        logger.info("[spiral.trace] RawSpiralWindow.initializeGL called")
        
        # Print OpenGL info
        version = GL.glGetString(GL.GL_VERSION).decode()
        renderer = GL.glGetString(GL.GL_RENDERER).decode()
        logger.info(f"[spiral.trace] OpenGL version: {version}")
        logger.info(f"[spiral.trace] OpenGL renderer: {renderer}")
        
        # Check if ANGLE is being used
        if "ANGLE" in renderer:
            logger.warning("[spiral.trace] ANGLE detected - may cause D3D dithering")
        else:
            logger.info("[spiral.trace] Desktop OpenGL detected")
        
        # Setup viewport
        GL.glViewport(0, 0, self.width(), self.height())
        
        # Build shader program
        self._build_shader_program()
        
        # Setup geometry
        self._setup_geometry()
        
        # Configure OpenGL state for internal opacity
        GL.glDisable(GL.GL_BLEND)  # No blending - we do opacity in shader
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_DITHER)
        GL.glDisable(GL.GL_MULTISAMPLE)
        
        try:
            GL.glDisable(0x8C36)  # GL_SAMPLE_SHADING
        except Exception:
            pass
            
        logger.info("[spiral.trace] RawSpiralWindow.initializeGL complete")
    
    def _build_shader_program(self):
        """Build the spiral shader program"""
        vertex_shader = """
        #version 330 core
        layout (location = 0) in vec2 aPos;
        layout (location = 1) in vec2 aTexCoord;
        
        out vec2 texCoord;
        
        void main() {
            gl_Position = vec4(aPos, 0.0, 1.0);
            texCoord = aTexCoord;
        }
        """
        
        fragment_shader = """
        #version 330 core
        in vec2 texCoord;
        out vec4 fragColor;
        
        uniform float u_time;
        uniform float u_intensity;
        uniform vec2 u_resolution;
        uniform vec3 u_bg_color;
        uniform bool u_internal_opacity;
        
        // High-precision constants
        const float PI = 3.1415926535897932384626433832795;
        const float TAU = 6.2831853071795864769252867665590;
        
        void main() {
            vec2 center = vec2(0.5, 0.5);
            vec2 pos = texCoord - center;
            
            // High-precision polar coordinates
            float radius = length(pos);
            float angle = atan(pos.y, pos.x);
            
            // Normalize angle to [0, TAU]
            if (angle < 0.0) angle += TAU;
            
            // Spiral parameters
            float spiral_tightness = 8.0;
            float spiral_thickness = 0.05;
            float rotation_speed = 0.5;
            
            // Calculate spiral
            float spiral_angle = angle + u_time * rotation_speed;
            float spiral_radius = mod(spiral_angle * spiral_tightness / TAU, 1.0);
            
            // Distance to spiral
            float dist = abs(radius - spiral_radius);
            float spiral_alpha = 1.0 - smoothstep(0.0, spiral_thickness, dist);
            
            // Spiral color
            vec3 spiral_color = vec3(1.0, 0.5, 0.8);
            
            if (u_internal_opacity) {
                // Internal opacity mode: blend in shader, output alpha=1
                vec3 final_color = mix(u_bg_color, spiral_color, spiral_alpha * u_intensity);
                fragColor = vec4(final_color, 1.0);  // Force alpha=1 - no exceptions
            } else {
                // Regular mode: output with alpha
                fragColor = vec4(spiral_color, spiral_alpha * u_intensity);
            }
        }
        """
        
        self.program = QOpenGLShaderProgram()
        self.program.addShaderFromSourceCode(QOpenGLShaderProgram.ShaderTypeBit.Vertex, vertex_shader)
        self.program.addShaderFromSourceCode(QOpenGLShaderProgram.ShaderTypeBit.Fragment, fragment_shader)
        
        if not self.program.link():
            logger.error(f"[spiral.trace] Shader program link failed: {self.program.log()}")
            return False
            
        logger.info("[spiral.trace] RawSpiralWindow shader program linked successfully")
        return True
    
    def _setup_geometry(self):
        """Setup fullscreen quad geometry"""
        # Fullscreen quad vertices
        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0,  # Bottom-left
             1.0, -1.0, 1.0, 0.0,  # Bottom-right
             1.0,  1.0, 1.0, 1.0,  # Top-right
            -1.0,  1.0, 0.0, 1.0   # Top-left
        ], dtype=np.float32)
        
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
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, None)
        
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, 8)
        
        self.vao.release()
        logger.info("[spiral.trace] RawSpiralWindow geometry setup complete")
    
    def paintGL(self):
        """Render the spiral directly to window framebuffer"""
        self.frame_count += 1
        
        # Clear
        GL.glClearColor(0.2, 0.2, 0.2, 1.0)  # Dark gray background
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        if not self.program:
            return
            
        # Use shader program
        self.program.bind()
        
        # Set uniforms
        current_time = self.frame_count * 0.016  # Approximate time
        params = self.director.get_current_params()
        
        self.program.setUniformValue("u_time", current_time)
        self.program.setUniformValue("u_intensity", params.get('intensity', 0.25))
        self.program.setUniformValue("u_resolution", self.width(), self.height())
        self.program.setUniformValue("u_bg_color", 0.2, 0.2, 0.2)  # Match clear color
        self.program.setUniformValue("u_internal_opacity", self.internal_opacity)
        
        # Render fullscreen quad
        self.vao.bind()
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        self.vao.release()
        
        self.program.release()
        
        # Log every 60 frames
        if self.frame_count % 60 == 0:
            logger.info(f"[spiral.trace] RawSpiralWindow.paintGL: frame={self.frame_count}")
    
    def resizeGL(self, width, height):
        """Handle window resize"""
        GL.glViewport(0, 0, width, height)
        logger.info(f"[spiral.trace] RawSpiralWindow.resizeGL: {width}x{height}")
