"""MesmerLoom OpenGL compositor (Step 1 minimal pipeline).

Implements:
 - Shader program build (pass-through video only)
 - Fullscreen triangle geometry
 - Neutral 1x1 fallback video texture
 - uResolution, uTime, uPhase, uVideo uniforms
 - Timer-driven repaint; safe fallback if GL unavailable
Mouse transparency & focus avoided; no parent window flag changes.
"""
from __future__ import annotations
from typing import Any, Optional
import logging, time, pathlib, os
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer

try:  # pragma: no cover - import guarded
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # type: ignore
    from PyQt6.QtGui import QOpenGLFunctions  # type: ignore
    _HAS_QT_GL = True
except Exception:  # pragma: no cover
    QOpenGLWidget = QWidget  # fallback to basic widget
    class QOpenGLFunctions:  # type: ignore
        def initializeOpenGLFunctions(self): pass
    _HAS_QT_GL = False

_SHADER_DIR = pathlib.Path(__file__).with_suffix("").parent / "shaders"

_PROBE_RETRIED = False
def probe_available() -> bool:
    """Active OpenGL availability probe.

    Strategy:
      1. If initial import succeeded (_HAS_QT_GL True) -> assume available.
      2. If it failed, attempt a one-time dynamic re-import (covers cases where
         PyQt6 was partially initialized or plugins not yet on PATH at first import).
      3. Attempt to create a tiny ephemeral QOpenGLWidget and process a few events
         to let the context initialize. Success -> True.
    Never raises; returns False on any hard failure so callers can decide to skip.
    """
    global _HAS_QT_GL, _PROBE_RETRIED
    if _HAS_QT_GL:
        return True
    if not _PROBE_RETRIED:
        _PROBE_RETRIED = True
        try:  # dynamic retry
            from PyQt6.QtOpenGLWidgets import QOpenGLWidget as _QOW  # noqa: F401
            from PyQt6.QtGui import QOpenGLFunctions as _QF  # noqa: F401
            _HAS_QT_GL = True
            return True
        except Exception:
            return False
    # If retry previously failed, last chance: attempt ephemeral widget
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # type: ignore
        app = QApplication.instance() or QApplication([])
        w = QOpenGLWidget()
        w.resize(1,1); w.show()
        for _ in range(3):
            app.processEvents()
        ok = bool(w.context())
        try: w.close()
        except Exception: pass
        if ok:
            _HAS_QT_GL = True
        return ok
    except Exception:
        return False

class Compositor(QOpenGLWidget):  # type: ignore[misc]
    def __init__(self, director, parent=None):
        super().__init__(parent)
        self.director = director
        self._initialized = False
        self._program = None
        self._vao = None; self._vbo = None
        self._tex_video = None
        self._blend_mode = 0
        self._render_scale = 1.0
        self._t0 = time.time()
        self._uniforms_cache: dict[str, float | int] | None = None
        self._active = False
        # Availability starts False and flips True only after a successful GL init + program link.
        # (Do not mark unavailable again for minor/non-fatal issues.)
        self.available = False
        self._announced_available = False
        # Mouse transparency (no window flag changes)
        try: self.setAttribute(getattr(type(self), 'WA_TransparentForMouseEvents'))
        except Exception: pass
        try: self.setFocusPolicy(0)
        except Exception: pass
        self._timer: QTimer | None = None

    def set_blend_mode(self, m: int): self._blend_mode = m
    def set_render_scale(self, s: float): self._render_scale = s
    def set_opacity(self, f: float): self._spiral_opacity = max(0.0, min(1.0, f)) if hasattr(self,'_spiral_opacity') else None
    def set_color_params(self, arm_rgba, gap_rgba, color_mode:int, gradient_params:dict):
        self._arm_rgba = arm_rgba; self._gap_rgba = gap_rgba; self._color_mode = color_mode; self._gradient_params = gradient_params
    def set_arm_count(self, n: int): self._arm_count = int(max(2, min(8, n)))

    # ---- New lightweight wiring methods (Step 3 extension) ----
    def set_active(self, active: bool):
        self._active = bool(active)
    def set_uniforms_from_director(self, uniforms: dict[str, float | int]):
        # Cache externally provided uniforms (already evolved at caller)
        self._uniforms_cache = dict(uniforms)
    def request_draw(self):
        if not (self.available and self._active):
            return
        try:
            self.update()
        except Exception:
            # Non-fatal; keep availability state
            pass

    # ---------------- GL lifecycle ----------------
    def initializeGL(self):  # pragma: no cover
        if not _HAS_QT_GL:
            self.available = False
            return
        self.gl = QOpenGLFunctions(); self.gl.initializeOpenGLFunctions()
        try:
            self._program = self._build_program()
            if not self._program:
                raise RuntimeError("Shader program link returned 0")
            self._setup_geometry()
            self._create_fallback_texture()
            self._start_timer()
            self._initialized = True
            self.available = True
            if not self._announced_available:
                print("MesmerLoom: GL OK — context+program linked (available=True)")
                self._announced_available = True
            logging.getLogger(__name__).info("MesmerLoom GL initialized")
        except Exception as e:  # pragma: no cover
            # Only a hard initialization failure marks unavailable.
            self.available = False
            logging.getLogger(__name__).error("GL init failed: %s", e)

    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(16)

    # ---------------- Shaders ----------------
    def _load_text(self, name: str) -> str:
        path = _SHADER_DIR / name
        with open(path, 'r', encoding='utf-8') as f: return f.read()

    def _compile_shader(self, src: str, stype) -> int:
        from OpenGL import GL
        sid = GL.glCreateShader(stype)
        GL.glShaderSource(sid, src)
        GL.glCompileShader(sid)
        if not GL.glGetShaderiv(sid, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(sid).decode('utf-8','ignore')
            raise RuntimeError(f"Shader compile failed: {log}")
        return sid

    def _build_program(self) -> int:
        from OpenGL import GL
        vs = self._compile_shader(self._load_text('fullscreen_quad.vert'), GL.GL_VERTEX_SHADER)
        fs = self._compile_shader(self._load_text('spiral.frag'), GL.GL_FRAGMENT_SHADER)
        prog = GL.glCreateProgram(); GL.glAttachShader(prog, vs); GL.glAttachShader(prog, fs); GL.glLinkProgram(prog)
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(prog).decode('utf-8','ignore')
            raise RuntimeError(f"Program link failed: {log}")
        GL.glDeleteShader(vs); GL.glDeleteShader(fs)
        return prog

    # ---------------- Geometry ----------------
    def _setup_geometry(self):
        from OpenGL import GL; import array
        data = [ -1.0,-1.0, 0.0,0.0,  3.0,-1.0, 2.0,0.0,  -1.0,3.0, 0.0,2.0 ]
        arr = array.array('f', data)
        self._vao = GL.glGenVertexArrays(1); self._vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(arr)*4, arr.tobytes(), GL.GL_STATIC_DRAW)
        stride = 4*4
        GL.glEnableVertexAttribArray(0); GL.glVertexAttribPointer(0,2,GL.GL_FLOAT,False,stride, None)
        from ctypes import c_void_p
        GL.glEnableVertexAttribArray(1); GL.glVertexAttribPointer(1,2,GL.GL_FLOAT,False,stride, c_void_p(8))
        GL.glBindVertexArray(0)

    # ---------------- Fallback video texture ----------------
    def _create_fallback_texture(self):
        from OpenGL import GL; import numpy as np
        self._tex_video = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex_video)
        pix = np.array([128,128,128,255], dtype=np.uint8)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA,1,1,0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,pix)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    # ---------------- Paint ----------------
    def paintGL(self):  # pragma: no cover
        if not (_HAS_QT_GL and self._initialized and self._program):
            try: self.director.update()
            except Exception: pass
            return
        if not self._active:
            return  # active gate
        from OpenGL import GL
        # If caller provided a pre-evolved uniform cache, use that; else evolve now
        if self._uniforms_cache is None:
            try: self.director.update()
            except Exception: pass
            uniforms = self.director.export_uniforms()
        else:
            uniforms = self._uniforms_cache
            # clear after use to avoid stale reuse if ticking stops
            self._uniforms_cache = None
        w,h = self.width(), self.height()
        GL.glViewport(0,0,w,h)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(self._program)
        # Uniforms (core + director exported set)
        t = time.time() - self._t0
        def _set1(name, val: float):
            loc = GL.glGetUniformLocation(self._program, name)
            if loc >= 0: GL.glUniform1f(loc, float(val))
        def _seti(name, val: int):
            loc = GL.glGetUniformLocation(self._program, name)
            if loc >= 0: GL.glUniform1i(loc, int(val))
        loc = GL.glGetUniformLocation(self._program,'uResolution')
        if loc >=0: GL.glUniform2f(loc, float(w), float(h))
        _set1('uTime', t)
        # Director uniforms
        for k,v in uniforms.items():
            if isinstance(v, int): _seti(k, v)
            else: _set1(k, v)
        _seti('uBlendMode', getattr(self, '_blend_mode', 0))
        # Texture
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex_video or 0)
        loc = GL.glGetUniformLocation(self._program,'uVideo')
        if loc >=0: GL.glUniform1i(loc, 0)
        # Draw
        GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
