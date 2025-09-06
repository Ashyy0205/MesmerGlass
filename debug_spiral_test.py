#!/usr/bin/env python3
"""
Quick spiral debug test - minimal window with simplified shader
to isolate the spiral pattern calculation issue.
"""

import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QSurfaceFormat
import OpenGL.GL as GL

class DebugSpiralWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.program_id = None
        self.frame_count = 0
        self.setFixedSize(600, 600)
        
        # Set up timer for animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # ~60 FPS
        
    def initializeGL(self):
        # Simple debug vertex shader
        vertex_source = """
        #version 330 core
        layout (location = 0) in vec2 position;
        layout (location = 1) in vec2 texCoord;
        out vec2 vUV;
        void main() {
            gl_Position = vec4(position, 0.0, 1.0);
            vUV = texCoord;
        }
        """
        
        # Simplified debug fragment shader - just show the spiral pattern as grayscale
        fragment_source = """
        #version 330 core
        in vec2 vUV;
        out vec4 FragColor;
        
        uniform vec2 uResolution;
        uniform float uTime;
        uniform float uPhase;
        uniform float uBarWidth;
        uniform int uArms;
        
        const float PI = 3.14159265359;
        const float TWO_PI = 6.28318530718;
        
        float calculateSpiralPattern(vec2 p, float twist, float phase, int arms) {
            // Calculate polar coordinates  
            float r = length(p);
            float angle = atan(p.y, p.x);
            
            // Spiral calculation
            float spiralCoord;
            if (r < 1e-6) {
                spiralCoord = phase; // avoid division by zero at center
            } else {
                spiralCoord = angle * float(arms) / TWO_PI + phase;
            }
            
            // Return fractional part
            return spiralCoord - floor(spiralCoord);
        }
        
        void main() {
            // Convert UV to centered coordinates [-1, 1]
            vec2 p = (vUV * 2.0 - 1.0);
            
            // Apply aspect ratio correction
            p.x *= uResolution.x / uResolution.y;
            
            // Calculate spiral pattern
            float pattern = calculateSpiralPattern(p, 0.0, uPhase, uArms);
            
            // Convert to bar pattern
            float halfWidth = uBarWidth * 0.5;
            float bar = smoothstep(0.5 - halfWidth, 0.5 - halfWidth + 0.01, pattern) -
                       smoothstep(0.5 + halfWidth - 0.01, 0.5 + halfWidth, pattern);
            
            // Debug output: show bar as grayscale (should be alternating black/white stripes)
            FragColor = vec4(vec3(bar), 1.0);
        }
        """
        
        # Compile and link shaders
        vs_id = self._compile_shader(vertex_source, GL.GL_VERTEX_SHADER)
        fs_id = self._compile_shader(fragment_source, GL.GL_FRAGMENT_SHADER)
        
        self.program_id = GL.glCreateProgram()
        GL.glAttachShader(self.program_id, vs_id)
        GL.glAttachShader(self.program_id, fs_id)
        GL.glLinkProgram(self.program_id)
        
        if not GL.glGetProgramiv(self.program_id, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(self.program_id).decode("utf-8", "ignore")
            raise RuntimeError(f"Shader program link failed: {log}")
        
        GL.glDeleteShader(vs_id)
        GL.glDeleteShader(fs_id)
        
        # Create fullscreen quad
        vertices = [
            # positions    # texCoords
            -1.0, -1.0,    0.0, 0.0,
             1.0, -1.0,    1.0, 0.0,
             1.0,  1.0,    1.0, 1.0,
            -1.0,  1.0,    0.0, 1.0
        ]
        
        indices = [0, 1, 2, 2, 3, 0]
        
        import numpy as np
        vertices = np.array(vertices, dtype=np.float32)
        indices = np.array(indices, dtype=np.uint32)
        
        # Create VAO/VBO/EBO
        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        self.ebo = GL.glGenBuffers(1)
        
        GL.glBindVertexArray(self.vao)
        
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)
        
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)
        
        # Position attribute
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, None)
        GL.glEnableVertexAttribArray(0)
        
        # Texture coordinate attribute
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 16, 8)
        GL.glEnableVertexAttribArray(1)
        
        GL.glBindVertexArray(0)
        
    def _compile_shader(self, source, shader_type):
        shader = GL.glCreateShader(shader_type)
        GL.glShaderSource(shader, source)
        GL.glCompileShader(shader)
        
        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(shader).decode("utf-8", "ignore")
            raise RuntimeError(f"Shader compile failed: {log}")
        
        return shader
        
    def paintGL(self):
        if not self.program_id:
            return
            
        self.frame_count += 1
        
        GL.glViewport(0, 0, self.width(), self.height())
        GL.glClearColor(0.1, 0.1, 0.1, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        GL.glUseProgram(self.program_id)
        
        # Set uniforms
        current_time = time.time() * 0.5  # Slow animation
        phase = current_time * 0.2  # Slow phase change
        
        GL.glUniform2f(GL.glGetUniformLocation(self.program_id, "uResolution"), 
                      float(self.width()), float(self.height()))
        GL.glUniform1f(GL.glGetUniformLocation(self.program_id, "uTime"), current_time)
        GL.glUniform1f(GL.glGetUniformLocation(self.program_id, "uPhase"), phase)
        GL.glUniform1f(GL.glGetUniformLocation(self.program_id, "uBarWidth"), 0.5)
        GL.glUniform1i(GL.glGetUniformLocation(self.program_id, "uArms"), 8)
        
        # Draw
        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        
        GL.glUseProgram(0)
        
        # Log every 60 frames
        if self.frame_count % 60 == 0:
            print(f"Debug spiral frame {self.frame_count}: phase={phase:.3f}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set OpenGL format
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    
    widget = DebugSpiralWidget()
    widget.setWindowTitle("Debug Spiral Pattern - Should show black/white rotating stripes")
    widget.show()
    
    print("Debug spiral test running...")
    print("You should see rotating black/white spiral stripes.")
    print("If you see solid grey or alternating grey/black, the spiral calculation is broken.")
    print("Close window to exit.")
    
    sys.exit(app.exec())
