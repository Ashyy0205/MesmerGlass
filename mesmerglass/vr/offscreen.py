"""Offscreen OpenGL helper for VR self-tests.

Creates a QOpenGLContext bound to a QOffscreenSurface and manages a simple
RGBA8 FBO for rendering test patterns without any Qt widgets or windows.

Usage contract:
- Create OffscreenGL(width, height)
- Call make_current()
- Each frame: render_pattern(name, t_seconds) which draws into the FBO
- Submit the FBO id via VrBridge.submit_frame_from_fbo(fbo, w, h)
- Call done_current() when yielding the context; delete() on shutdown

Patterns implemented without shaders (for maximum compatibility):
- solid: color cycles over time via glClearColor
- grid: coarse grid drawn using glScissor + glClear to avoid fixed-function draws
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QOpenGLContext, QOffscreenSurface

try:
    from OpenGL import GL
except Exception as _e:  # pragma: no cover
    GL = None  # type: ignore


@dataclass
class OffscreenGL:
    width: int
    height: int

    def __post_init__(self) -> None:
        if GL is None:
            raise RuntimeError("PyOpenGL not available")
        # Create context and offscreen surface
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        # No need for depth/stencil/MSAA for simple test patterns
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        self.ctx = QOpenGLContext()
        self.ctx.setFormat(fmt)
        ok = self.ctx.create()
        if not ok:
            raise RuntimeError("Failed to create QOpenGLContext")
        self.surf = QOffscreenSurface()
        self.surf.setFormat(fmt)
        self.surf.create()
        if not self.surf.isValid():
            raise RuntimeError("Failed to create QOffscreenSurface")
        # Make current once to allocate GL objects
        self.make_current()
        try:
            self._fbo = GL.glGenFramebuffers(1)
            self._tex = GL.glGenTextures(1)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            # RGBA8 is widely supported; sRGB is not required for test patterns
            GL.glTexImage2D(
                GL.GL_TEXTURE_2D,
                0,
                GL.GL_RGBA8,
                int(self.width),
                int(self.height),
                0,
                GL.GL_RGBA,
                GL.GL_UNSIGNED_BYTE,
                None,
            )
            GL.glFramebufferTexture2D(
                GL.GL_FRAMEBUFFER,
                GL.GL_COLOR_ATTACHMENT0,
                GL.GL_TEXTURE_2D,
                self._tex,
                0,
            )
            status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
            if status != GL.GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError(f"Offscreen FBO incomplete: 0x{int(status):04X}")
        finally:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            self.done_current()

    def make_current(self) -> None:
        self.ctx.makeCurrent(self.surf)

    def done_current(self) -> None:
        self.ctx.doneCurrent()

    @property
    def fbo(self) -> int:
        return int(self._fbo)

    def size(self) -> Tuple[int, int]:
        return int(self.width), int(self.height)

    # ----------------- rendering -----------------
    def _prep_draw(self) -> None:
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        GL.glViewport(0, 0, int(self.width), int(self.height))
        # Default: disable depth/stencil; enable premultiplied-friendly blend
        try: GL.glDisable(GL.GL_DEPTH_TEST)
        except Exception: pass
        try: GL.glDisable(GL.GL_STENCIL_TEST)
        except Exception: pass
        try: GL.glDisable(GL.GL_DITHER)
        except Exception: pass
        try: GL.glEnable(GL.GL_BLEND)
        except Exception: pass
        try: GL.glBlendFuncSeparate(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        except Exception: pass

    def render_pattern(self, name: str, t_seconds: float) -> None:
        """Draw a simple pattern into the FBO.

        name:
          - 'solid': time-varying color via glClear
          - 'grid': coarse grid via scissor-clears
        """
        self._prep_draw()
        n = (name or "solid").lower()
        if n == "grid":
            self._render_grid(t_seconds)
        else:
            self._render_solid(t_seconds)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)

    def _render_solid(self, t: float) -> None:
        import math
        r = 0.5 + 0.5 * math.sin(t * 1.7)
        g = 0.5 + 0.5 * math.sin(t * 2.3 + 1.0)
        b = 0.5 + 0.5 * math.sin(t * 2.9 + 2.0)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glClearColor(r, g, b, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

    def _render_grid(self, t: float) -> None:
        # Draw alternating stripes using scissor rectangles (no shaders)
        GL.glEnable(GL.GL_SCISSOR_TEST)
        W, H = int(self.width), int(self.height)
        # Background
        GL.glScissor(0, 0, W, H)
        GL.glClearColor(0.05, 0.05, 0.06, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        # Vertical stripes
        cols = 12
        stripe_w = max(1, W // cols)
        for i in range(cols):
            x = i * stripe_w
            if i % 2 == 0:
                GL.glScissor(x, 0, stripe_w // 2, H)
                GL.glClearColor(0.15, 0.15, 0.18, 1.0)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        # Horizontal stripes
        rows = 8
        stripe_h = max(1, H // rows)
        for j in range(rows):
            y = j * stripe_h
            if j % 2 == 0:
                GL.glScissor(0, y, W, stripe_h // 2)
                GL.glClearColor(0.12, 0.12, 0.14, 1.0)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glDisable(GL.GL_SCISSOR_TEST)

    # ----------------- teardown -----------------
    def delete(self) -> None:
        if GL is None:
            return
        self.make_current()
        try:
            try:
                GL.glDeleteFramebuffers(1, [int(self._fbo)])
            except Exception:
                pass
            try:
                GL.glDeleteTextures(1, [int(self._tex)])
            except Exception:
                pass
        finally:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            self.done_current()
