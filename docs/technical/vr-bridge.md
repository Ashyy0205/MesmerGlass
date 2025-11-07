# VR Bridge (OpenXR + Mock)

This document describes the minimal VR output path used to stream MesmerGlass frames to a head‑mounted display.

## Overview

- Module: `mesmerglass/vr/vr_bridge.py`
- API:
  - `VrBridge(enabled: bool = False)`
  - `start()` → bool (True if OpenXR session initialized, False for mock)
  - `submit_frame_from_fbo(source_fbo: int, src_w: int, src_h: int)`
  - `shutdown()`
- Graphics: OpenGL via `XR_KHR_opengl_enable` (future binding). Currently scaffolds and falls back to a mock mode when OpenXR binding cannot be established.

## How it works

- When `--vr` is passed to `python -m mesmerglass run`, the CLI sets `MESMERGLASS_VR=1` (and `MESMERGLASS_VR_MOCK=1` if `--vr-mock` is also set) before launching the GUI.
- The `Launcher` reads these flags, creates a `VrBridge`, and connects the main spiral compositor’s `frame_drawn` signal to a submit slot.
- On startup, if no GL context is current (typical before the Qt compositor exists), the bridge defers session creation.
- When the compositor is created, we briefly make its GL context current and bind the OpenXR session to that exact context (share group).
- On each drawn frame:
  - The compositor GL context is current already (or made current temporarily).
  - The VR‑safe offscreen FBO (if enabled) or default framebuffer is blitted to each eye’s swapchain.
  - Any exceptions are swallowed and logged at debug level.

## Compositor sources

- QOpenGLWindow compositor (artifact‑free path): uses default framebuffer (FBO 0).
- QOpenGLWidget compositor (fallback path): uses `defaultFramebufferObject()`.
- Pixel dimensions use the compositor size multiplied by `devicePixelRatioF()`.

## Mock vs OpenXR

- If the `openxr` Python package is not present, the bridge runs in mock mode.
- If a graphics binding cannot be created initially (no current GL context), the bridge defers session creation and retries once the compositor context is current.
- You can force mock mode with `--vr-mock`.

## Swapchain formats

- The bridge enumerates runtime‑supported swapchain formats and prefers `GL_SRGB8_ALPHA8` when available, otherwise `GL_RGBA8` or `GL_RGBA16F`, with a final fallback to the runtime’s first choice.
- Selected format and a short list of advertised formats are logged at INFO to aid runtime compatibility debugging.

## Visibility diagnostics

- Set `MESMERGLASS_VR_DEBUG_SOLID=1` to bypass blitting and clear each swapchain image to a solid green. This validates that the XR swapchain is visible to the runtime even if your compositor’s blit path were failing.
- If `locate_views` returns 0 views, a one‑time warning suggests checking the active OpenXR runtime in SteamVR settings.

## Testing

- Parser: `python -m mesmerglass --help` shows `run --vr` and `run --vr-mock`.
- Manual: launch with `--vr`; confirm logs show `[vr] VrBridge initialized` and per‑frame submissions when the spiral is drawing.
- OpenXR: to integrate with ALVR or a native OpenXR runtime, implement `_build_opengl_binding()` to pass the correct WGL/GL handles to the runtime.

## Limitations and next steps

- The OpenXR context binding on Windows via Qt requires native handles; the scaffold intentionally runs in mock mode until this is implemented.
- Future: add a CLI subcommand to sanity‑check XR availability and enumerate runtimes.
