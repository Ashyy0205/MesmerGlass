#!/usr/bin/env python3
"""
Quick offscreen test to isolate spiral shader artifacts.
Renders to RGBA16F FBO and saves to PNG for inspection.
"""

import sys
import numpy as np
import struct
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
import OpenGL.GL as GL

# Import spiral components
sys.path.insert(0, '.')
from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.mesmerloom.compositor import LoomCompositor

class OffscreenTest(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.director = SpiralDirector(seed=7)
        self.director.set_intensity(0.2)  # Low intensity to trigger artifacts
        self.director.set_supersampling(16)  # Max quality
        self.director.set_precision("high")
        self.fbo = None
        self.compositor = None
        self.resize(512, 512)  # Smaller for quick test
        
    def initializeGL(self):
        print("Initializing offscreen test...")
        # Create RGBA16F framebuffer
        format = QOpenGLFramebufferObjectFormat()
        format.setInternalTextureFormat(GL.GL_RGBA16F)
        format.setSamples(0)  # No MSAA on FBO
        self.fbo = QOpenGLFramebufferObject(512, 512, format)
        
        if not self.fbo.isValid():
            print("ERROR: Failed to create RGBA16F FBO")
            return
            
        print(f"Created RGBA16F FBO: {self.fbo.texture()}")
        
        # Create compositor
        self.compositor = LoomCompositor(self.director, parent=self)
        
    def render_and_save(self):
        if not self.fbo or not self.compositor:
            print("ERROR: FBO or compositor not ready")
            return
            
        # Bind FBO and render
        self.fbo.bind()
        GL.glViewport(0, 0, 512, 512)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        
        # Disable blending for clean capture
        GL.glDisable(GL.GL_BLEND)
        
        # Render spiral (simulate compositor paintGL)
        if hasattr(self.compositor, '_program') and self.compositor._program:
            GL.glUseProgram(self.compositor._program)
            
            # Set basic uniforms
            def _set1(name, val):
                loc = GL.glGetUniformLocation(self.compositor._program, name)
                if loc >= 0: GL.glUniform1f(loc, float(val))
            def _seti(name, val):
                loc = GL.glGetUniformLocation(self.compositor._program, name)
                if loc >= 0: GL.glUniform1i(loc, int(val))
                
            _set1('uTime', 1.0)
            _set1('uIntensity', 0.2)
            _seti('uTestOpaqueMode', 1)  # Force opaque
            
            # Set resolution
            loc = GL.glGetUniformLocation(self.compositor._program, 'uResolution')
            if loc >= 0: GL.glUniform2f(loc, 512.0, 512.0)
            
            # Export director uniforms
            uniforms = self.director.export_uniforms()
            for k, v in uniforms.items():
                if isinstance(v, int):
                    _seti(k, v)
                else:
                    _set1(k, v)
            
            # Draw fullscreen quad
            if hasattr(self.compositor, '_draw_fullscreen_quad'):
                self.compositor._draw_fullscreen_quad()
        
        # Read pixels as float
        GL.glFinish()
        data = GL.glReadPixels(0, 0, 512, 512, GL.GL_RGBA, GL.GL_FLOAT)
        
        # Convert to numpy array and flip Y
        img_array = np.frombuffer(data, dtype=np.float32).reshape(512, 512, 4)
        img_array = np.flipud(img_array)  # OpenGL Y is flipped
        
        # Save raw data and analysis
        np.save('spiral_offscreen_raw.npy', img_array)
        
        # Check for artifacts by analyzing variance in areas that should be smooth
        center_region = img_array[200:300, 200:300, :3]  # Center 100x100 region
        variance = np.var(center_region)
        
        print(f"Center region variance: {variance:.6f}")
        print("Saved spiral_offscreen_raw.npy")
        print("If variance > 0.001 → potential artifacts present")
        print("If variance < 0.001 → smooth gradients (good)")
        
        # Simple text-based visualization
        print("\nCenter region intensity pattern (first 10x10):")
        sample = center_region[:10, :10, 0]  # Red channel sample
        for row in sample:
            line = "".join("█" if x > 0.1 else "░" if x > 0.01 else " " for x in row)
            print(line)
        
        self.fbo.release()

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    
    test = OffscreenTest()
    test.show()
    
    # Process events to initialize GL
    for _ in range(10):
        app.processEvents()
    
    if test.compositor and hasattr(test.compositor, 'available') and test.compositor.available:
        test.render_and_save()
        print("Offscreen test completed")
    else:
        print("ERROR: Compositor not available")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
