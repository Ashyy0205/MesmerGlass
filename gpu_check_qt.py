import os
os.environ.setdefault("QT_OPENGL", "desktop")  # avoid ANGLE/software fallbacks

from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import glGetString, GL_VENDOR, GL_RENDERER, GL_VERSION, GL_SHADING_LANGUAGE_VERSION

# (Optional) ask for a modern profile
fmt = QSurfaceFormat()
fmt.setVersion(4, 6)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
QSurfaceFormat.setDefaultFormat(fmt)

class Probe(QOpenGLWidget):
    def initializeGL(self):
        def s(name): return glGetString(name).decode(errors="ignore")
        print("OpenGL Vendor  :", s(GL_VENDOR))
        print("OpenGL Renderer:", s(GL_RENDERER))
        print("OpenGL Version :", s(GL_VERSION))
        print("GLSL Version   :", s(GL_SHADING_LANGUAGE_VERSION))
        QApplication.instance().quit()

app = QApplication([])
w = Probe()
w.resize(1, 1)   # tiny, won’t really flash
w.show()
app.exec()
