from __future__ import annotations
"""MesmerLoom OpenGL compositor (Step 1 minimal pipeline).

Implements:
 - Shader program build (pass-through video only)
 - Fullscreen triangle geometry
 - Neutral 1x1 fallback video texture
 - uResolution, uTime, uPhase, uVideo uniforms
 - Timer-driven repaint; safe fallback if GL unavailable
Mouse transparency & focus avoided; no parent window flag changes.
"""
from typing import Any, Optional
import logging, time, pathlib, os
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer
try:  # Set a conservative default surface format early (can be disabled via env)
    from PyQt6.QtGui import QSurfaceFormat  # type: ignore
    if not os.environ.get("MESMERGLASS_NO_SURFACE_FMT"):
        _fmt = QSurfaceFormat()
        # Request 3.3 core; most modern drivers (including ANGLE) can satisfy or downgrade gracefully.
        _fmt.setVersion(3, 3)
        try:
            _fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        except Exception:  # pragma: no cover - older Qt
            pass
        QSurfaceFormat.setDefaultFormat(_fmt)
except Exception:  # pragma: no cover
    pass

try:  # pragma: no cover - import guarded
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # type: ignore
    try:
        from PyQt6.QtOpenGL import QOpenGLFunctions  # type: ignore
    except ImportError:
        class QOpenGLFunctions:
            def initializeOpenGLFunctions(self): pass
    _HAS_QT_GL = True
except Exception:  # pragma: no cover
    QOpenGLWidget = QWidget  # fallback to basic widget
    class QOpenGLFunctions:  # type: ignore
        def initializeOpenGLFunctions(self): pass
    _HAS_QT_GL = False

_SHADER_DIR = pathlib.Path(__file__).with_suffix("").parent / "shaders"

_PROBE_RETRIED = False
def probe_available() -> bool:
    """Return True if OpenGL widget support is (or is forced to be) available.

    Simplified after earlier indentation issues. The intent for tests is:
      * If MESMERGLASS_GL_SIMULATE=1 -> treat as available (headless CI path).
      * If PyQt6 OpenGL modules imported successfully -> available.
      * Else, one dynamic retry import; on failure return False.
    Never raises.
    """
    global _HAS_QT_GL, _PROBE_RETRIED
    if os.environ.get("MESMERGLASS_GL_SIMULATE") == "1":
        return True
    if os.environ.get("MESMERGLASS_GL_ASSUME") == "1":
        return True
    if _HAS_QT_GL:
        return True
    if not _PROBE_RETRIED:
        _PROBE_RETRIED = True
        try:
            from PyQt6.QtOpenGLWidgets import QOpenGLWidget as _QOW  # noqa: F401
            from PyQt6.QtGui import QOpenGLFunctions as _QF  # noqa: F401
            _HAS_QT_GL = True
            return True
        except Exception:
            return False
    return False

class Compositor(QOpenGLWidget):  # type: ignore[misc]
    def __init__(self, director, parent=None):
        import logging
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.__init__ called: director={director} parent={parent}")
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
        self.available = False
        self._announced_available = False
        try:
            self.setAttribute(getattr(type(self), 'WA_TransparentForMouseEvents'))
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.__init__ setAttribute failed: {e}")
        try:
            self.setFocusPolicy(0)
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.__init__ setFocusPolicy failed: {e}")
        self._timer = None  # type: ignore[assignment]
        self._trace = bool(os.environ.get("MESMERGLASS_SPIRAL_TRACE"))
        # Force spiral intensity to 1.0 for diagnostic visibility
        try:
            if hasattr(self.director, 'set_intensity'):
                self.director.set_intensity(1.0)
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor: failed to set intensity: {e}")
        self._draw_count = 0
        self._watermark = os.environ.get("MESMERGLASS_SPIRAL_WATERMARK", "1") != "0"
        sim_flag = os.environ.get("MESMERGLASS_GL_SIMULATE") == "1"
        force_flag = os.environ.get("MESMERGLASS_GL_FORCE") == "1"
        test_or_ci = bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI"))
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.__init__ sim_flag={sim_flag} force_flag={force_flag} test_or_ci={test_or_ci}")
        if sim_flag and not force_flag:
            if test_or_ci:
                try:
                    self.available = True; self._initialized = True
                    self._program = 1; self._vao = 1; self._vbo = 1
                    self._start_timer()
                except Exception as e:
                    logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor.__init__ simulation mode error: {e}")
                if not self._announced_available:
                    print("MesmerLoom: GL SIMULATION MODE (early) active")
                    self._announced_available = True
            else:
                if not self._announced_available:
                    logging.getLogger(__name__).warning(
                        "Ignoring MESMERGLASS_GL_SIMULATE=1 outside test/CI (set MESMERGLASS_GL_FORCE=1 to suppress this warning)."
                    )
                    self._announced_available = True
        # (No optimistic probe marking; availability flips on real initializeGL)
        # Force context creation attempt
        try:
            self.makeCurrent()
            logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.__init__: makeCurrent called")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.__init__: makeCurrent failed: {e}")
        try:
            self.update()
            logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.__init__: update called")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.__init__: update failed: {e}")

    def showEvent(self, event):
        import logging
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.showEvent: visible={self.isVisible()} mapped={self.isVisible()} size={self.size()}")
        super().showEvent(event)
        try:
            self.makeCurrent()
            logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.showEvent: makeCurrent called")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.showEvent: makeCurrent failed: {e}")
        try:
            self.update()
            logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.showEvent: update called")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.showEvent: update failed: {e}")

    def resizeEvent(self, event):
        import logging
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.resizeEvent: size={self.size()}")
        super().resizeEvent(event)
        try:
            self.update()
            logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.resizeEvent: update called")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] LoomCompositor.resizeEvent: update failed: {e}")

    def event(self, event):
        import logging
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.event: type={event.type()} visible={self.isVisible()} size={self.size()}")
        return super().event(event)

    # ---- Manual context force attempt (experimental) ----
    def force_init_context(self) -> bool:
        """Attempt to eagerly trigger GL context creation.

        Some systems fail to initialize QOpenGLWidget when embedded in a
        translucent, always-on-top container early. Calling makeCurrent()
        can force the backing framebuffer/context allocation. Safe to call
        multiple times. Returns True if initialized (or simulation) after call.
        """
        if self._initialized or not _HAS_QT_GL:
            return self._initialized
        try:
            if self._trace:
                logging.getLogger(__name__).info("[spiral.trace] force_init_context: invoking makeCurrent()")
            self.makeCurrent()
            # If Qt hasn't called initializeGL yet it should now; if still not, call manually.
            if not self._initialized:
                try:
                    super().initializeGL()  # may be no-op / double guarded internally
                except Exception:
                    pass
            self.doneCurrent()
        except Exception as e:
            if self._trace:
                logging.getLogger(__name__).warning("[spiral.trace] force_init_context failed: %s", e)
        return self._initialized
    
    def _build_program(self) -> int:
        """Attempt to build the primary spiral shader program.
        
        Raises on failure so caller can attempt fallback.
        """
        from OpenGL import GL
        shader_dir = _SHADER_DIR
        vs_path = shader_dir / 'fullscreen_quad.vert'
        fs_path = shader_dir / 'spiral.frag'
        print(f"[spiral.trace] Vertex shader path: {vs_path}")
        print(f"[spiral.trace] Fragment shader path: {fs_path}")
        vs_src = self._load_text('fullscreen_quad.vert')
        fs_src = self._load_text('spiral.frag')
        try:
            vs = self._compile_shader(vs_src, GL.GL_VERTEX_SHADER)
        except Exception as e:
            print(f"[spiral.trace] Vertex shader compile error: {e}")
            raise
        try:
            fs = self._compile_shader(fs_src, GL.GL_FRAGMENT_SHADER)
        except Exception as e:
            print(f"[spiral.trace] Fragment shader compile error: {e}")
            raise
        prog = GL.glCreateProgram(); GL.glAttachShader(prog, vs); GL.glAttachShader(prog, fs); GL.glLinkProgram(prog)
        print(f"[spiral.trace] GL program ID: {prog}")
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(prog).decode('utf-8','ignore')
            print(f"[spiral.trace] Program link failed: {log}")
            raise RuntimeError(f"Program link failed: {log}")
        GL.glDeleteShader(vs); GL.glDeleteShader(fs)
        return prog
    
    def _build_fallback_program(self) -> Optional[int]:
        """Build a minimal guaranteed-low-spec shader pair.
        
        This allows tests to proceed (exercising wiring & phase evolution) even on
        environments that reject the main GLSL 330 core shaders. Uses GLSL 130
        (widely available on older drivers) and omits all spiral uniforms – it
        just fills with a solid gray that modulates slightly with time.
        Returns program id or None on failure.
        """
        try:  # pragma: no cover - only exercised on problematic environments
            from OpenGL import GL
            vs_src = """#version 130\nin vec2 aPos; in vec2 aUV; out vec2 vUV; void main(){ vUV=aUV; gl_Position=vec4(aPos,0.0,1.0);}"""
            fs_src = """#version 130\nin vec2 vUV; out vec4 FragColor; uniform float uTime; void main(){ FragColor = vec4(0.0,1.0,0.0,1.0); }"""
            try:
                vs = self._compile_shader(vs_src, GL.GL_VERTEX_SHADER)
            except Exception as e:
                print(f"[spiral.trace] Fallback vertex shader compile error: {e}")
                raise
            try:
                fs = self._compile_shader(fs_src, GL.GL_FRAGMENT_SHADER)
            except Exception as e:
                print(f"[spiral.trace] Fallback fragment shader compile error: {e}")
                raise
            prog = GL.glCreateProgram(); GL.glAttachShader(prog, vs); GL.glAttachShader(prog, fs); GL.glLinkProgram(prog)
            if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
                log = GL.glGetProgramInfoLog(prog).decode('utf-8','ignore')
                print(f"[spiral.trace] Fallback program link failed: {log}")
                raise RuntimeError(log)
            GL.glDeleteShader(vs); GL.glDeleteShader(fs)
            logging.getLogger(__name__).warning("MesmerLoom: using fallback GL program (solid green)")
            return prog
        except Exception as e:  # pragma: no cover
            logging.getLogger(__name__).error("Fallback GL program build failed: %s", e)
            return None

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
            if self._trace:
                logging.getLogger(__name__).debug("[spiral.trace] request_draw skipped available=%s active=%s", self.available, self._active)
            return
        try:
            if self._trace:
                logging.getLogger(__name__).debug("[spiral.trace] request_draw queued")
            self.update()
        except Exception:
            # Non-fatal; keep availability state
            pass

    # ---------------- GL lifecycle ----------------
    def initializeGL(self):  # pragma: no cover
        import logging
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL called: self={self}")
        if self._trace:
            logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL trace enabled")
        if not _HAS_QT_GL:
            self.available = False
            logging.getLogger(__name__).warning("[spiral.trace] initializeGL aborted: no QT GL")
            return
        debug = bool(os.environ.get("MESMERGLASS_GL_DEBUG"))
        try:
            self.gl = QOpenGLFunctions(); self.gl.initializeOpenGLFunctions()
            logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL OpenGLFunctions initialized")
            try:
                logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.initializeGL compiling main shader program...")
                self._program = self._build_program()
                logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL _build_program succeeded: program={self._program}")
            except Exception as primary_err:
                logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor.initializeGL _build_program failed: {primary_err}")
                # Attempt fallback shader path
                try:
                    logging.getLogger(__name__).info("[spiral.trace] LoomCompositor.initializeGL compiling fallback shader program...")
                    self._program = self._build_fallback_program()
                except Exception as fallback_err:
                    logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor.initializeGL _build_fallback_program failed: {fallback_err}")
                    raise primary_err
                if not self._program:
                    raise primary_err
                logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL fallback program used: program={self._program}")
            if not self._program:
                raise RuntimeError("Shader program link returned 0")
            self._setup_geometry()
            logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL geometry setup complete")
            # Spiral overlay does not use video textures; skip fallback texture creation
            # Defensive: only set uniforms if program is valid and uniform location is found
            self._start_timer()
            logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL timer started")
            self._initialized = True
            self.available = True
            logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.initializeGL success program={self._program}")
            if not self._announced_available:
                print("MesmerLoom: GL OK — program linked (fallback=%s)" % ("yes" if 'fallback' in (logging.getLogger(__name__).handlers[0].__dict__ if logging.getLogger(__name__).handlers else {}) else "no"))
                self._announced_available = True
            if debug:
                try:
                    from OpenGL import GL
                    v = GL.glGetString(GL.GL_VERSION)
                    r = GL.glGetString(GL.GL_RENDERER)
                    logging.getLogger(__name__).info(f"GL_VERSION={v} RENDERER={r}")
                except Exception as e:
                    logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor.initializeGL GL version/renderer query failed: {e}")
            logging.getLogger(__name__).info(f"MesmerLoom GL initialized (fallback={'yes' if 'warning' in [h.level for h in logging.getLogger(__name__).handlers] else 'no'})")
        except Exception as e:  # pragma: no cover
            self.available = False
            logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor.initializeGL exception: {e}")
            if debug:
                import traceback; traceback.print_exc()
            # Simulation fallback: allow tests to proceed without a real context
            if os.environ.get("MESMERGLASS_GL_SIMULATE") == "1":  # pragma: no cover - environment driven
                try:
                    self._program = 1  # dummy non-zero sentinel
                    self._vao = 1
                    logging.getLogger(__name__).info("[spiral.trace] initializeGL begin (requesting context)")
                    self._vbo = 1
                    self._start_timer()
                except Exception as e:
                    logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor.initializeGL simulation fallback error: {e}")
                self.available = True
                self._initialized = True
                if not self._announced_available:
                    print("MesmerLoom: GL SIMULATION MODE active (no real context)")
                    self._announced_available = True
                logging.getLogger(__name__).warning("MesmerLoom running in simulated GL mode (no real rendering)")
                logging.getLogger(__name__).warning("[spiral.trace] initializeGL simulation fallback engaged")

    def paintGL(self):  # pragma: no cover
        import logging
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.paintGL called: self={self} initialized={self._initialized} program={self._program}")
        if not (_HAS_QT_GL and self._initialized and self._program):
            try: self.director.update()
            except Exception: pass
            if self._trace:
                logging.getLogger(__name__).debug(f"[spiral.trace] paintGL skipped not-initialized avail={self.available} active={self._active}")
            return
        if not self._active:
            if self._trace:
                logging.getLogger(__name__).debug("[spiral.trace] paintGL inactive draw suppressed")
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
        self._draw_count += 1
        # Log all uniform values for diagnosis
        uniform_log = {k: round(float(v),4) if isinstance(v,(int,float)) else v for k,v in uniforms.items()}
        logging.getLogger(__name__).info(f"[spiral.trace] LoomCompositor.paintGL frame={self._draw_count} active={self._active} uniforms={uniform_log}")
        # Additional spiral parameter logging in trace mode
        if self._trace:
            st = getattr(self.director, 'state', None)
            if st:
                logging.getLogger(__name__).info(
                    f"[spiral.trace] frame: opacity={getattr(st, 'opacity', None):.3f} "
                    f"bar_width={getattr(st, 'bar_width', None):.3f} "
                    f"twist={getattr(st, 'twist', None):.3f} "
                    f"contrast={getattr(st, 'contrast', None):.3f} "
                    f"vignette={getattr(st, 'vignette', None):.3f} "
                    f"chromatic_shift={getattr(st, 'chromatic_shift', None):.3f} "
                    f"intensity={getattr(st, 'intensity', None):.3f} "
                )
                # Tune spiral parameters for clear spiral stripes
                uniforms['uTwist'] = 0.3
                uniforms['uBarWidth'] = 0.3
                uniforms['uPhase'] = time.time() % 1.0
                uniforms['uContrast'] = 1.0  # Maximum contrast
                uniforms['uOpacity'] = 1.0  # Maximum opacity
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
        # Draw
        self._draw_fullscreen_quad()

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

    # (Removed duplicate _build_program definition lower in file)

    # ---------------- Geometry ----------------
    def _setup_geometry(self):
        import logging
        logging.info('[spiral.trace] _setup_geometry called')
        print('[spiral.trace] _setup_geometry called')
        from OpenGL import GL
        import array
        import ctypes
        arr = array.array('f', [
            -1.0, -1.0, 0.0, 0.0,  # bottom left
             1.0, -1.0, 1.0, 0.0,  # bottom right
             1.0,  1.0, 1.0, 1.0,  # top right
            -1.0,  1.0, 0.0, 1.0   # top left
        ])
        indices = array.array('I', [0, 1, 2, 2, 3, 0])
        print('[spiral.trace] Vertex array:', arr.tolist())
        print('[spiral.trace] Indices array:', indices.tolist())
        logging.info('[spiral.trace] Vertex array: %s', arr.tolist())
        logging.info('[spiral.trace] Indices array: %s', indices.tolist())
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        self._ebo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(arr)*4, arr.tobytes(), GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, len(indices)*4, indices.tobytes(), GL.GL_STATIC_DRAW)
        stride = 4*4  # 4 floats per vertex: x, y, u, v
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, False, stride, ctypes.c_void_p(8))
        GL.glBindVertexArray(0)
        import logging
        try:
            # ...existing code...
            logging.getLogger(__name__).info("[spiral.trace] Draw call executing")
            err = self.gl.glGetError()
            if err != 0:
                logging.getLogger(__name__).error(f"[spiral.trace] OpenGL error after draw call: {err}")
        except Exception as e:
            logging.getLogger(__name__).error(f"[spiral.trace] Exception in paintGL: {e}")
        from OpenGL import GL; import array
        # Fullscreen quad: 4 vertices, 2 triangles
        # Vertex format: x, y, u, v
        data = [
            -1.0, -1.0, 0.0, 0.0,  # bottom left
             1.0, -1.0, 1.0, 0.0,  # bottom right
             1.0,  1.0, 1.0, 1.0,  # top right
            -1.0,  1.0, 0.0, 1.0   # top left
        ]
        arr = array.array('f', data)
        import array
        import ctypes
        from OpenGL import GL
        # Fullscreen quad vertex data: [x, y, u, v] for each vertex
        arr = array.array('f', [
            -1.0, -1.0, 0.0, 0.0,  # bottom left
             1.0, -1.0, 1.0, 0.0,  # bottom right
             1.0,  1.0, 1.0, 1.0,  # top right
            -1.0,  1.0, 0.0, 1.0   # top left
        ])
        indices = array.array('I', [0, 1, 2, 2, 3, 0])
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        self._ebo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(arr)*4, arr.tobytes(), GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, len(indices)*4, indices.tobytes(), GL.GL_STATIC_DRAW)
        import array
        import ctypes
        from OpenGL import GL
        arr = array.array('f', [
            -1.0, -1.0, 0.0, 0.0,  # bottom left
             1.0, -1.0, 1.0, 0.0,  # bottom right
             1.0,  1.0, 1.0, 1.0,  # top right
            -1.0,  1.0, 0.0, 1.0   # top left
        ])
        indices = array.array('I', [0, 1, 2, 2, 3, 0])
        print("[spiral.trace] Vertex array:", arr.tolist())
        print("[spiral.trace] Indices array:", indices.tolist())
        stride = 4*4  # 4 floats per vertex: x, y, u, v
        # Attribute 0: position (x, y) at offset 0
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, stride, ctypes.c_void_p(0))
        # Attribute 1: UV (u, v) at offset 8 bytes (2 floats)
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, False, stride, ctypes.c_void_p(8))
        print("[spiral.trace] Vertex array:", arr.tolist())
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

    def _draw_fullscreen_quad(self):
        from OpenGL import GL
        # Draw fullscreen quad (6 indices)
        GL.glBindVertexArray(self._vao)
        GL.glDrawElements(GL.GL_TRIANGLES, 6, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
        # Optional GPU watermark overlay using QPainter (after GL commands)
        if self._watermark:
            try:
                from PyQt6.QtGui import QPainter, QColor, QFont
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                f = QFont(); f.setPointSize(10); p.setFont(f)
                p.setPen(QColor(255,255,255,160))
                p.drawText(10, 18, "Spiral (GPU)")
                p.end()
            except Exception:
                pass
