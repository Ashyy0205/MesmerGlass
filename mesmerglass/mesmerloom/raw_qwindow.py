"""
Raw QWindow + OpenGL context implementation.
Completely bypasses Qt's widget compositor and FBO blit pipeline.
"""

import logging
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QWindow, QOpenGLContext, QSurfaceFormat
from OpenGL import GL
import numpy as np
import time

logger = logging.getLogger(__name__)

class RawOpenGLWindow(QWindow):
    """Raw QWindow with direct OpenGL context - bypasses all Qt widget compositing"""
    
    def __init__(self, director, parent=None):
        super().__init__(parent)
        self.director = director
        self.gl_context = None
        self.program = None
        self.vao = None
        self.vbo = None
        self.ebo = None
        self.frame_count = 0
        self.t0 = time.time()
        
        # Set surface type to OpenGL
        self.setSurfaceType(QWindow.SurfaceType.OpenGLSurface)
        
        # Timer for animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.render)
        
        logger.info(f"[spiral.trace] RawOpenGLWindow.__init__ called: director={director}")
    
    def initialize_gl(self):
        """Initialize raw OpenGL context"""
        logger.info("[spiral.trace] RawOpenGLWindow.initialize_gl called")
        
        # Create OpenGL context
        format = QSurfaceFormat()
        format.setVersion(3, 3)
        format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        format.setDepthBufferSize(24)
        format.setStencilBufferSize(8)
        format.setSamples(0)  # No MSAA
        format.setAlphaBufferSize(0)  # No alpha buffer
        
        self.gl_context = QOpenGLContext()
        self.gl_context.setFormat(format)
        
        if not self.gl_context.create():
            logger.error("[spiral.trace] Failed to create OpenGL context")
            return False
            
        if not self.gl_context.makeCurrent(self):
            logger.error("[spiral.trace] Failed to make OpenGL context current")
            return False
        
        # Print OpenGL info
        version = GL.glGetString(GL.GL_VERSION).decode()
        renderer = GL.glGetString(GL.GL_RENDERER).decode()
        logger.info(f"[spiral.trace] Raw OpenGL version: {version}")
        logger.info(f"[spiral.trace] Raw OpenGL renderer: {renderer}")
        
        # Build shader program
        self._build_shader_program()
        
        # Setup geometry
        self._setup_geometry()
        
        # Configure OpenGL state
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_DITHER)
        GL.glDisable(GL.GL_MULTISAMPLE)
        
        logger.info("[spiral.trace] RawOpenGLWindow.initialize_gl complete")
        return True
    
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
            vec3 bg_color = vec3(0.2, 0.2, 0.2);
            
            // Internal opacity: blend in shader, output opaque
            vec3 final_color = mix(bg_color, spiral_color, spiral_alpha * u_intensity);
            fragColor = vec4(final_color, 1.0);  // Always opaque
        }
        """
        
        # Compile vertex shader
        vs = GL.glCreateShader(GL.GL_VERTEX_SHADER)
        GL.glShaderSource(vs, vertex_shader)
        GL.glCompileShader(vs)
        
        if not GL.glGetShaderiv(vs, GL.GL_COMPILE_STATUS):
            error = GL.glGetShaderInfoLog(vs).decode()
            logger.error(f"[spiral.trace] Vertex shader compile error: {error}")
            return False
        
        # Compile fragment shader
        fs = GL.glCreateShader(GL.GL_FRAGMENT_SHADER)
        GL.glShaderSource(fs, fragment_shader)
        GL.glCompileShader(fs)
        
        if not GL.glGetShaderiv(fs, GL.GL_COMPILE_STATUS):
            error = GL.glGetShaderInfoLog(fs).decode()
            logger.error(f"[spiral.trace] Fragment shader compile error: {error}")
            return False
        
        # Link program
        self.program = GL.glCreateProgram()
        GL.glAttachShader(self.program, vs)
        GL.glAttachShader(self.program, fs)
        GL.glLinkProgram(self.program)
        
        if not GL.glGetProgramiv(self.program, GL.GL_LINK_STATUS):
            error = GL.glGetProgramInfoLog(self.program).decode()
            logger.error(f"[spiral.trace] Program link error: {error}")
            return False
        
        # Cleanup
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)
        
        logger.info("[spiral.trace] RawOpenGLWindow shader program linked successfully")
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
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        
        # Create VBO
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)
        
        # Create EBO
        self.ebo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)
        
        # Setup vertex attributes
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, GL.glvoid(0))
        
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, GL.glvoid(8))
        
        GL.glBindVertexArray(0)
        logger.info("[spiral.trace] RawOpenGLWindow geometry setup complete")
    
    def render(self):
        """Render the spiral directly to window"""
        if not self.gl_context or not self.gl_context.makeCurrent(self):
            return
            
        self.frame_count += 1
        
        # Setup viewport
        GL.glViewport(0, 0, self.width(), self.height())
        
        # Clear
        GL.glClearColor(0.2, 0.2, 0.2, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        if not self.program:
            self.gl_context.swapBuffers(self)
            return
            
        # Use shader program
        GL.glUseProgram(self.program)
        
        # Set uniforms
        current_time = (time.time() - self.t0) * 0.5
        uniforms = self.director.export_uniforms()
        
        GL.glUniform1f(GL.glGetUniformLocation(self.program, "u_time"), current_time)
        GL.glUniform1f(GL.glGetUniformLocation(self.program, "u_intensity"), uniforms.get('intensity', 0.25))
        GL.glUniform2f(GL.glGetUniformLocation(self.program, "u_resolution"), self.width(), self.height())
        
        # Render fullscreen quad
        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        
        GL.glUseProgram(0)
        
        # Swap buffers
        self.gl_context.swapBuffers(self)
        
        # Log every 60 frames
        if self.frame_count % 60 == 0:
            logger.info(f"[spiral.trace] RawOpenGLWindow.render: frame={self.frame_count}")
    
    def showEvent(self, event):
        """Initialize OpenGL when window is shown"""
        super().showEvent(event)
        if not self.gl_context:
            if self.initialize_gl():
                self.timer.start(16)  # ~60 FPS
    
    def resizeEvent(self, event):
        """Handle window resize"""
        super().resizeEvent(event)
        if self.gl_context and self.gl_context.makeCurrent(self):
            GL.glViewport(0, 0, self.width(), self.height())
            logger.info(f"[spiral.trace] RawOpenGLWindow.resizeEvent: {self.width()}x{self.height()}")
