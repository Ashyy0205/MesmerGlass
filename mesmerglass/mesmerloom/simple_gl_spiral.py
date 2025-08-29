"""Ultra-minimal spiral GL widget used strictly for diagnostics.

Key goals:
 - Avoid use of QOpenGLFunctions (missing in current PyQt6 build).
 - Use the smallest possible shader pair (GLSL 130) and a fullscreen triangle via gl_VertexID.
 - Expose .available and ._initialized like the main compositor so existing probe logic works.
 - Provide verbose trace logging when MESMERGLASS_SPIRAL_TRACE=1.
"""
import os, time, logging
from typing import Optional

try:  # Import QOpenGLWidget only; some builds omit ancillary helpers
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # type: ignore
    _IMPORT_OK = True
except Exception as _err:  # pragma: no cover
    logging.getLogger(__name__).error("SpiralSimpleGL: QOpenGLWidget import failed: %s", _err)
    QOpenGLWidget = object  # type: ignore
    _IMPORT_OK = False

class SpiralSimpleGL(QOpenGLWidget):  # pragma: no cover (runtime visual component)
    def __init__(self, director, parent=None):
        try:
            super().__init__(parent)
        except Exception as e:  # base became 'object' if import failed
            logging.getLogger(__name__).error("SpiralSimpleGL: base init failed (%s) import_ok=%s", e, _IMPORT_OK)
            raise
        # Attribute initialization
        self.director = director
        self._program = None  # type: Optional[int]
        self._vao = None  # type: Optional[int]
        self._t0 = time.time()
        self._active = True
        self.available = False
        self._initialized = False
        self._trace = bool(os.environ.get("MESMERGLASS_SPIRAL_TRACE"))
        try:
            from PyQt6.QtCore import Qt
            # Explicitly disable translucency to rule out compositing issues
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.showFullScreen()
        except Exception:
            pass
        self.setWindowTitle("SpiralSimpleGL Diagnostic")

    def showEvent(self, event):
        super().showEvent(event)
        # Force widget itself to fullscreen and topmost, regardless of parent
        try:
            from PyQt6.QtCore import Qt
            self.showFullScreen()
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.setWindowFlag(Qt.WindowType.Tool, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setWindowOpacity(1.0)
            self.activateWindow()
            self.raise_()
        except Exception as e:
            print(f"[spiral.diag] showEvent: window flags error: {e}")
        # Get screen geometry and forcibly resize widget
        screen = self.screen() if hasattr(self, 'screen') else None
        if screen:
            screen_geom = screen.geometry()
            self.setGeometry(screen_geom)
            self.resize(screen_geom.width(), screen_geom.height())
            print(f"[spiral.diag] showEvent: screen_geom={screen_geom} widget_geom={self.geometry()}")
        else:
            print(f"[spiral.diag] showEvent: no screen, widget_geom={self.geometry()}")
        # Log viewport size
        print(f"[spiral.diag] showEvent: viewport will be set to {self.width()}x{self.height()}")

    def resizeGL(self, w, h):
        from OpenGL.GL import glViewport
        glViewport(0, 0, w, h)
        # Force widget to fullscreen on every resizeGL
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen:
                screen_geom = screen.geometry()
                self.setGeometry(screen_geom)
                self.resize(screen_geom.width(), screen_geom.height())
                print(f"[spiral.diag] resizeGL: forced fullscreen screen_geom={screen_geom} widget_geom={self.geometry()} size={self.size()}")
            else:
                print(f"[spiral.diag] resizeGL: no screen, widget_geom={self.geometry()} size={self.size()}")
        except Exception as e:
            print(f"[spiral.diag] resizeGL: error forcing fullscreen: {e}")
        print(f"[spiral.diag] resizeGL: viewport set to {w}x{h}")
import os, time, logging
from typing import Optional

try:  # Import QOpenGLWidget only; some builds omit ancillary helpers
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # type: ignore
    _IMPORT_OK = True
except Exception as _err:  # pragma: no cover
    logging.getLogger(__name__).error("SpiralSimpleGL: QOpenGLWidget import failed: %s", _err)
    QOpenGLWidget = object  # type: ignore
    _IMPORT_OK = False


class SpiralSimpleGL(QOpenGLWidget):  # pragma: no cover (runtime visual component)
    def __init__(self, director, parent=None):
        try:
            super().__init__(parent)
        except Exception as e:  # base became 'object' if import failed
            logging.getLogger(__name__).error("SpiralSimpleGL: base init failed (%s) import_ok=%s", e, _IMPORT_OK)
            raise
        # Attribute initialization
        self.director = director
        self._program = None  # type: Optional[int]
        self._vao = None  # type: Optional[int]
        self._t0 = time.time()
        self._active = True
        self.available = False
        self._initialized = False
        self._trace = bool(os.environ.get("MESMERGLASS_SPIRAL_TRACE"))
        try:
            from PyQt6.QtCore import Qt
            # Explicitly disable translucency to rule out compositing issues
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.showFullScreen()
        except Exception:
            pass
        self.setWindowTitle("SpiralSimpleGL Diagnostic")

    # ---- API parity shims ----
    def set_active(self, a: bool):
        self._active = bool(a)
    def set_uniforms_from_director(self, uniforms):  # not needed here
        pass
    def request_draw(self):
        if self.available and self._active:
            try:
                self.update()
            except Exception:
                pass

    # ---- GL lifecycle ----
    def initializeGL(self):  # pragma: no cover
        if self._trace:
            logging.getLogger(__name__).info("[spiral.trace] SpiralSimpleGL.initializeGL begin")
        from OpenGL import GL
        # Use VBO and attribute pointer for fullscreen quad
        vs_src = (
            "#version 130\n"
            "in vec2 aPos;\n"
            "void main() {\n"
            "  gl_Position = vec4(aPos, 0.0, 1.0);\n"
            "}" )
        fs_src = (
            "#version 130\nout vec4 FragColor;\n"
            "void main(){ FragColor=vec4(1.0,0.0,1.0,1.0); }" )
        def _compile(src, st):
            sid = GL.glCreateShader(st); GL.glShaderSource(sid, src); GL.glCompileShader(sid)
            if not GL.glGetShaderiv(sid, GL.GL_COMPILE_STATUS):
                raise RuntimeError(GL.glGetShaderInfoLog(sid).decode('utf-8','ignore'))
            return sid
        try:
            vs = _compile(vs_src, GL.GL_VERTEX_SHADER)
            fs = _compile(fs_src, GL.GL_FRAGMENT_SHADER)
            prog = GL.glCreateProgram(); GL.glAttachShader(prog, vs); GL.glAttachShader(prog, fs)
            GL.glBindAttribLocation(prog, 0, "aPos")
            GL.glLinkProgram(prog)
            if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
                raise RuntimeError(GL.glGetProgramInfoLog(prog).decode('utf-8','ignore'))
            GL.glDeleteShader(vs); GL.glDeleteShader(fs)
            # Set up VAO and VBO for quad
            vao = GL.glGenVertexArrays(1)
            GL.glBindVertexArray(vao)
            quad_vertices = [
                -1.0, -1.0,
                 1.0, -1.0,
                -1.0,  1.0,
                 1.0,  1.0
            ]
            if getattr(self, 'trace', False):
                logging.getLogger(__name__).info(f"[spiral.diag] quad_vertices (NDC): {quad_vertices}")
            import numpy as np
            quad_vbo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, quad_vbo)
            arr = np.array(quad_vertices, dtype=np.float32)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, arr.nbytes, arr, GL.GL_STATIC_DRAW)
            GL.glEnableVertexAttribArray(0)
            GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, 0, None)
            self._vao = vao
            self._vbo = quad_vbo
            self._program = prog
            self.available = True
            self._initialized = True
            if self._trace:
                try:
                    from OpenGL.GL import glGetString, GL_RENDERER, GL_VERSION
                    r = glGetString(GL_RENDERER); v = glGetString(GL_VERSION)
                except Exception:
                    r = v = b'?'
                # Dump a few GL state values
                try:
                    fb_draw = GL.glGetIntegerv(GL.GL_DRAW_FRAMEBUFFER_BINDING)
                    fb_read = GL.glGetIntegerv(GL.GL_READ_FRAMEBUFFER_BINDING)
                    cur_prog = GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM)
                    vp = GL.glGetIntegerv(GL.GL_VIEWPORT)
                except Exception:
                    fb_draw = fb_read = cur_prog = -1; vp = (-1,-1,-1,-1)
                logging.getLogger(__name__).info(
                    "[spiral.trace] SpiralSimpleGL.initializeGL success program=%s renderer=%s version=%s drawFB=%s readFB=%s curProg=%s viewport=%s",
                    prog, r, v, fb_draw, fb_read, cur_prog, vp)
            # Start internal animation timer to ensure repaints even if director not driving
            try:
                from PyQt6.QtCore import QTimer
                self._anim_timer = QTimer(self)
                self._anim_timer.timeout.connect(self.request_draw)
                self._anim_timer.start(33)  # ~30 FPS
            except Exception as t_err:  # pragma: no cover
                if self._trace:
                    logging.getLogger(__name__).warning(f"[spiral.trace] anim timer create failed: {t_err}")
        except Exception as e:
            logging.getLogger(__name__).error("SpiralSimpleGL initializeGL failed: %s", e)
            self.available = False
            self._initialized = False

    def paintGL(self):  # pragma: no cover
        if not (self._program and self._active):
            return
        from OpenGL import GL
        w, h = self.width(), self.height()
        if self._trace:
            logging.getLogger(__name__).info("[spiral.diag] paintGL: begin w=%d h=%d", w, h)
        GL.glViewport(0, 0, w, h)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_BLEND)
        # Set clear color to magenta for unmistakable background
        GL.glClearColor(1.0, 0.0, 1.0, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        if self._trace:
            logging.getLogger(__name__).info("[spiral.diag] paintGL: after clear")
        if self._vao is not None:
            try:
                GL.glBindVertexArray(self._vao)
            except Exception:
                logging.getLogger(__name__).warning("[spiral.diag] VAO bind failed")
        GL.glUseProgram(self._program)
        t = time.time() - self._t0
        loc = GL.glGetUniformLocation(self._program, 'uTime')
        if loc >= 0:
            GL.glUniform1f(loc, t)
        loc = GL.glGetUniformLocation(self._program, 'uRes')
        if loc >= 0:
            GL.glUniform2f(loc, float(w), float(h))
        # Bind VAO and draw fullscreen quad
        if self._vao is not None:
            GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        if self._trace:
            logging.getLogger(__name__).info(
                f"[spiral.diag] paintGL: after quad draw (VBO/attrib) viewport=({w},{h})")
        GL.glUseProgram(0)
        if self._vao is not None:
            try:
                GL.glBindVertexArray(0)
            except Exception:
                logging.getLogger(__name__).warning("[spiral.diag] VAO unbind failed")
        if self._trace:
            fc = getattr(self, '_frame_count', 0) + 1
            self._frame_count = fc
            logging.getLogger(__name__).info("[spiral.diag] paintGL: end frame=%d t=%.2f", fc, t)
