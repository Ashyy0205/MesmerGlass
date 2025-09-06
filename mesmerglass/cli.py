"""MesmerGlass command-line interface.

Argparse-based CLI that mirrors/extends run.py commands and initializes
structured logging early. Exposed via ``python -m mesmerglass``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Optional

# Suppress pygame support prompt so JSON outputs (e.g. session --print) remain clean.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from .engine.buttplug_server import ButtplugServer
from .engine.pulse import PulseEngine
from .logging_utils import setup_logging, get_default_log_path
from .devtools.virtual_toy import VirtualToy  # dev-only, used by 'toy' subcommand
from .content.loader import load_session_pack  # session packs
import subprocess, sys, warnings, pathlib
from mesmerglass.mesmerloom.compositor import LoomCompositor

class GLUnavailableError(RuntimeError):
    pass


def _add_logging_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set log level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=str(get_default_log_path()),
        help="Path to log file (default: per-user MesmerGlass directory)",
    )
    parser.add_argument(
        "--log-format",
        choices=["plain", "json"],
        default="plain",
        help="Log format (plain or json)",
    )


async def _cli_pulse(level: float, duration_ms: int, port: int) -> int:
    """Send a single pulse using PulseEngine. Returns process exit code."""
    log = logging.getLogger(__name__)
    engine = PulseEngine()
    engine.start()
    # Give engine a moment to connect; keep short to avoid delays.
    await asyncio.sleep(0.6)
    log.info("CLI pulse level=%.2f duration_ms=%d", level, duration_ms)
    engine.pulse(level, duration_ms)
    await asyncio.sleep(duration_ms / 1000.0 + 0.2)
    engine.stop()
    return 0



def _cli_server(port: int) -> int:
    server = ButtplugServer(port=port)
    log = logging.getLogger(__name__)
    log.info("Starting Buttplug server on port %s", port)
    server.start()
    try:
        while True:
            input("Press Enter to refresh device list or Ctrl+C to quit...")
            devices = server.get_device_list()
            for dev in devices.devices:
                log.info(" - %s (index=%s)", dev.name, dev.index)
    except KeyboardInterrupt:
        log.info("Shutting down server...")
    finally:
        server.stop()
    return 0


def selftest() -> int:
    """Fast import-and-init smoke test. Returns exit code."""
    try:
        import PyQt6  # noqa: F401  # Ensure UI deps import
        from .engine import audio, video, pulse  # noqa: F401
        logging.getLogger(__name__).info("Selftest OK: imports succeeded")
        return 0
    except Exception as e:
        logging.getLogger(__name__).error("Selftest failed: %s", e)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MesmerGlass CLI")
    _add_logging_args(parser)
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("run", help="Start the GUI (default)")

    p_pulse = sub.add_parser("pulse", help="Send a single pulse (alias: 'test')")
    p_pulse.add_argument("--level", type=float, default=0.5, help="Pulse intensity 0..1")
    p_pulse.add_argument("--duration", type=int, default=500, help="Duration in ms")
    p_pulse.add_argument("--port", type=int, default=12345, help="Buttplug server port")

    # Alias for backward compatibility (was 'test' in run.py)
    p_test_alias = sub.add_parser("test", help=argparse.SUPPRESS)
    p_test_alias.add_argument("--level", type=float, default=0.5)
    p_test_alias.add_argument("--duration", type=int, default=500)
    p_test_alias.add_argument("--port", type=int, default=12345)

    p_srv = sub.add_parser("server", help="Start a local Buttplug server")
    p_srv.add_argument("--port", type=int, default=12345)

    p_ui = sub.add_parser("ui", help="Drive basic UI navigation for testing")
    # Query/Navigation
    p_ui.add_argument("--list-tabs", action="store_true", help="List top-level tab names and exit")
    p_ui.add_argument("--tab", type=str, default=None, help="Select a tab by name (case-insensitive) or index")
    # Layout selection
    p_ui.add_argument("--layout", choices=["tabbed", "sidebar"], default="tabbed", help="Choose UI layout")

    # Setters
    p_ui.add_argument("--set-text", type=str, default=None, help="Set overlay text")
    p_ui.add_argument("--set-text-scale", type=int, default=None, help="Set text scale percent (0-100)")
    p_ui.add_argument("--set-fx-mode", type=str, default=None, help="Set FX mode by name")
    p_ui.add_argument("--set-fx-intensity", type=int, default=None, help="Set FX intensity (0-100)")
    p_ui.add_argument("--set-font-path", type=str, default=None, help="Load a custom font file (ttf/otf) headlessly and update font family")
    p_ui.add_argument("--vol1", type=int, default=None, help="Set primary audio volume percent (0-100)")
    p_ui.add_argument("--vol2", type=int, default=None, help="Set secondary audio volume percent (0-100)")
    p_ui.add_argument("--displays", choices=["all", "primary", "none"], default=None, help="Quick-select displays")
    p_ui.add_argument("--load-state", type=str, default=None, help="Load a previously saved session state JSON before applying other options")
    # Actions
    p_ui.add_argument("--launch", action="store_true", help="Launch overlays")
    p_ui.add_argument("--stop", action="store_true", help="Stop overlays and audio")
    p_ui.add_argument("--status", action="store_true", help="Print status as JSON")
    # Session control
    p_ui.add_argument("--timeout", type=float, default=0.3, help="Seconds to keep the event loop alive (default: 0.3)")
    p_ui.add_argument("--show", action="store_true", help="Show the main window (default: hidden)")

    # dev-only: virtual toy simulator to drive tests or local dev without hardware
    p_toy = sub.add_parser("toy", help="Run a deterministic virtual toy simulator (dev-only)")
    p_toy.add_argument("--name", type=str, default="Virtual Test Toy")
    p_toy.add_argument("--port", type=int, default=12345)
    p_toy.add_argument("--latency-ms", type=int, default=0)
    p_toy.add_argument("--map", choices=["linear", "ease"], default="linear")
    p_toy.add_argument("--gain", type=float, default=1.0)
    p_toy.add_argument("--gamma", type=float, default=1.0)
    p_toy.add_argument("--offset", type=float, default=0.0)
    p_toy.add_argument("--run-for", type=float, default=5.0, help="Seconds to run before exiting")

    sub.add_parser("selftest", help="Quick environment/import check")
    # MesmerLoom spiral visual test (Phase 2 real implementation)
    p_spiral = sub.add_parser("spiral-test", help="Run a bounded MesmerLoom spiral render test")
    p_spiral.add_argument("--video", type=str, default="none", help="Video path or 'none' for neutral")
    p_spiral.add_argument("--intensity", type=float, default=0.75, help="Initial intensity 0..1 (default: 0.75)")
    p_spiral.add_argument("--blend", choices=["multiply","screen","softlight"], default="multiply", help="Blend mode (default: multiply)")
    p_spiral.add_argument("--duration", type=float, default=5.0, help="Seconds to run (default: 5)")
    p_spiral.add_argument("--render-scale", choices=["1.0","0.85","0.75"], default="1.0", help="Render scale (default: 1.0)")
    p_spiral.add_argument("--supersampling", type=int, choices=[1,4,9,16], default=4, help="Anti-aliasing samples: 1=none, 4=2x2, 9=3x3, 16=4x4 (default: 4)")
    p_spiral.add_argument("--precision", choices=["low","medium","high"], default="high", help="Floating-point precision level (default: high)")
    p_spiral.add_argument("--debug-gl-state", action="store_true", help="Print OpenGL state information for debugging")
    p_spiral.add_argument("--test-opaque", action="store_true", help="Render fully opaque with blending off to test compositor artifacts")
    p_spiral.add_argument("--test-offscreen", action="store_true", help="Render to RGBA16F FBO and save to PNG for artifact isolation")
    p_spiral.add_argument("--test-legacy-blend", action="store_true", help="Use legacy alpha blending instead of premultiplied (for comparison)")
    p_spiral.add_argument("--disable-srgb", action="store_true", help="Disable sRGB framebuffer for gamma-incorrect blending test")
    p_spiral.add_argument("--internal-opacity", action="store_true", help="Use internal opacity blending with opaque window (bypasses DWM dithering)")
    p_spiral.add_argument("--proof-window-opacity", type=float, metavar="0.0-1.0", help="Proof test: Set window opacity (will show DWM dithering)")
    p_spiral.add_argument("--check-window-flags", action="store_true", help="Check Windows API flags (WS_EX_LAYERED) for DWM dithering diagnosis")
    p_spiral.add_argument("--force", action="store_true", help="Bypass GL availability probe and attempt to run anyway")
    p_spiral.add_argument("--screen", type=int, default=0, help="Screen index to target for spiral overlay (default: 0)")
    p_spiral.add_argument("--raw-window", action="store_true", help="Use QOpenGLWindow instead of QOpenGLWidget (bypasses Qt FBO blit)")
    p_spiral.add_argument("--desktop-gl", action="store_true", help="Force desktop OpenGL (no ANGLE/D3D)")
    p_spiral.add_argument("--no-msaa", action="store_true", help="Disable all MSAA/multisampling")
    p_spiral.add_argument("--debug-gl-info", action="store_true", help="Print detailed OpenGL implementation info")
    p_spiral.add_argument("--test-offscreen-png", action="store_true", help="Render to RGBA16F FBO and save PNG (isolation test)")
    p_spiral.add_argument("--no-overlays", action="store_true", help="Disable all overlays/widgets (pure GL window)")
    p_spiral.add_argument("--window-test", action="store_true", help="Use raw QWindow + OpenGL context (bypasses all Qt widgets)")
    p_spiral.add_argument("--move-scale-test", action="store_true", help="Test if artifacts are screen-fixed or content-fixed (drag/scale window)")

    # Test runner integration (wraps previous run_tests.py functionality)
    p_tr = sub.add_parser("test-run", help="Run pytest with selection shortcuts (replaces run_tests.py)")
    p_tr.add_argument("type", choices=["all","fast","slow","unit","integration","bluetooth"], nargs="?", default="all")
    p_tr.add_argument("-v","--verbose", action="store_true")
    p_tr.add_argument("-c","--coverage", action="store_true")

    # Session pack subcommand
    p_sess = sub.add_parser("session", help="Load and inspect/apply a session pack")
    p_sess.add_argument("--load", required=True, help="Path to session pack JSON file")
    g = p_sess.add_mutually_exclusive_group()
    g.add_argument("--print", action="store_true", help="Print canonical JSON and exit")
    g.add_argument("--apply", action="store_true", help="Apply pack to headless launcher and print status JSON")
    g.add_argument("--summary", action="store_true", help="Print concise summary (default)")

    # Runtime session state (save/load current UI configuration)
    p_state = sub.add_parser("state", help="Save or apply runtime UI/device/audio/text settings")
    act = p_state.add_mutually_exclusive_group(required=True)
    act.add_argument("--save", action="store_true", help="Capture current defaults (headless) and write to file")
    act.add_argument("--apply", action="store_true", help="Apply a saved state file (headless)")
    act.add_argument("--print", action="store_true", help="Print a saved state file as canonical JSON")
    p_state.add_argument("--file", required=True, help="Target state JSON file (input or output depending on action)")
    p_state.add_argument("--from-live", action="store_true", help="(Reserved) Capture from a running instance (not yet implemented)")

    return parser

def cmd_spiral_test(args) -> None:
    """Run bounded MesmerLoom spiral render with systematic artifact isolation.

    Exit codes:
      0 success
      77 OpenGL unavailable (import/probe/context failure)
      1 unexpected error
    """
    import sys, time as _time
    
    # Test 2: Force desktop OpenGL (no ANGLE) - set BEFORE any Qt imports
    if getattr(args, 'desktop_gl', False):
        import os
        os.environ['QT_OPENGL'] = 'desktop'
        # Also try the attribute method
        try:
            from PyQt6.QtCore import QCoreApplication, Qt
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True)
            print("TEST MODE 2: Desktop OpenGL forced (no ANGLE/D3D)")
            print("If clean on desktop GL but not default → ANGLE/D3D dithering")
            print("----------------------------------------------------------------------")
        except ImportError:
            pass
    
    # Test 3: Disable MSAA/multisampling - set BEFORE QApplication
    if getattr(args, 'no_msaa', False):
        try:
            from PyQt6.QtGui import QSurfaceFormat
            fmt = QSurfaceFormat()
            fmt.setSamples(0)
            QSurfaceFormat.setDefaultFormat(fmt)
            print("TEST MODE 3: MSAA/multisampling disabled")  
            print("If artifacts persist → not MSAA/coverage related")
            print("----------------------------------------------------------------------")
        except ImportError:
            pass
    
    # Imports
    try:
        from .mesmerloom.spiral import SpiralDirector as LoomDirector
        from .mesmerloom.compositor import LoomCompositor, probe_available
    except Exception as e:
        print("MesmerLoom spiral-test: GL unavailable: import failure", e)
        sys.exit(77)
    try:
        # Probe
        if not getattr(args, 'force', False):
            probe_ok = True
            try:
                if 'probe_available' in locals() and callable(probe_available):
                    probe_ok = bool(probe_available())
            except Exception:
                probe_ok = False
            if not probe_ok:
                print("MesmerLoom spiral-test: probe inconclusive; attempting context anyway...")
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        import logging
        
        # B) Force opaque default framebuffer (no alpha buffer)
        try:
            from PyQt6.QtOpenGL import QSurfaceFormat
            fmt = QSurfaceFormat()
            fmt.setAlphaBufferSize(0)  # Force no alpha - prevents Qt compositing artifacts
            fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
            QSurfaceFormat.setDefaultFormat(fmt)
            logging.getLogger(__name__).info("[spiral.trace] QSurfaceFormat configured: alphaBufferSize=0")
        except ImportError:
            try:
                from PyQt6.QtGui import QSurfaceFormat
                fmt = QSurfaceFormat()
                fmt.setAlphaBufferSize(0)
                fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
                QSurfaceFormat.setDefaultFormat(fmt)
                logging.getLogger(__name__).info("[spiral.trace] QSurfaceFormat configured: alphaBufferSize=0 (via QtGui)")
            except ImportError as e:
                logging.getLogger(__name__).warning(f"[spiral.trace] Could not configure QSurfaceFormat: {e}")
        
        app = QApplication.instance() or QApplication([])
        director = LoomDirector(seed=7)
        try:
            director.set_intensity(max(0.0, min(1.0, float(getattr(args, "intensity", 0.75)))))
            # Set supersampling level for anti-aliasing
            director.set_supersampling(getattr(args, "supersampling", 4))
            # Set precision level
            director.set_precision(getattr(args, "precision", "high"))
        except Exception:
            pass
        
        # Test 1: Choose compositor implementation based on test mode
        if getattr(args, 'window_test', False):
            # Use raw QWindow to bypass ALL Qt widget compositing
            try:
                from .mesmerloom.raw_qwindow import RawOpenGLWindow
                comp = RawOpenGLWindow(director)
                comp.resize(1920, 1080)
                print("ISOLATION TEST: Raw QWindow + OpenGL context")
                print("Bypasses ALL Qt widget/FBO compositing completely")
                print("If artifacts disappear → Qt widget pipeline was the culprit")
                print("----------------------------------------------------------------------")
            except ImportError as e:
                print(f"Raw QWindow test unavailable: {e}")
                print("Falling back to regular QOpenGLWidget...")
                comp = LoomCompositor(director)
                comp.resize(640, 360)
        else:
            # Use QOpenGLWindow by default (artifact-free)
            try:
                from .mesmerloom.window_compositor import LoomWindowCompositor
                comp = LoomWindowCompositor(director)
                comp.resize(1920, 1080)
                print("DEFAULT: QOpenGLWindow compositor (artifact-free)")
                print("Direct window rendering - no Qt widget FBO blit artifacts")
                print("----------------------------------------------------------------------")
            except ImportError as e:
                print(f"QOpenGLWindow compositor unavailable: {e}")
                print("Falling back to QOpenGLWidget (has FBO blit artifacts)...")
                # Fallback to regular QOpenGLWidget implementation
                comp = LoomCompositor(director)
                comp.resize(640, 360)
        
        # Configure window transparency based on mode
        internal_opacity = getattr(sys.modules.get(__name__), '_internal_opacity_mode', False)
        proof_window_opacity = getattr(args, 'proof_window_opacity', None)
        check_flags = getattr(args, 'check_window_flags', False)
        
        # Check if this is a QOpenGLWindow or QOpenGLWidget
        is_window_compositor = hasattr(comp, 'setFlags')  # QOpenGLWindow has setFlags, QWidget has setAttribute
        
        if proof_window_opacity is not None:
            # Proof test: Use window-level opacity (will show DWM dithering)
            proof_opacity = max(0.0, min(1.0, proof_window_opacity))
            if not is_window_compositor:
                comp.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            comp.setWindowOpacity(proof_opacity)
            logging.getLogger(__name__).info(f"[spiral.trace] PROOF TEST: Window opacity set to {proof_opacity} (expect DWM dithering)")
        elif internal_opacity:
            # Internal opacity mode: Force truly opaque window to bypass DWM dithering
            comp.setWindowOpacity(1.0)
            if not is_window_compositor:
                comp.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
                comp.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
                comp.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            logging.getLogger(__name__).info("[spiral.trace] Window set to TRULY opaque for internal opacity mode")
        else:
            # Standard mode: Use translucent window (subject to DWM dithering)
            if not is_window_compositor:
                comp.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            comp.setWindowOpacity(1.0)  # Let shader handle alpha blending
        comp.set_active(True)
        # Store debug flag for compositor to use
        if getattr(args, 'debug_gl_state', False):
            print("OpenGL State Debugging Mode")
            print("-" * 30)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._debug_gl_state = True
        
        if getattr(args, 'test_opaque', False):
            print("TEST MODE: Fully opaque rendering with blending disabled")
            print("If artifacts disappear → compositor/layered-window issue")
            print("-" * 50)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._test_opaque_mode = True
            
        if getattr(args, 'test_offscreen', False):
            print("TEST MODE: Offscreen RGBA16F rendering to isolate shader artifacts")
            print("Will save to spiral_test_output.png for inspection")
            print("-" * 50)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._test_offscreen_mode = True
            
        if getattr(args, 'test_legacy_blend', False):
            print("TEST MODE: Using legacy alpha blending (for comparison)")
            print("This may show compositor artifacts that premultiplied alpha fixes")
            print("-" * 50)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._test_legacy_blend = True
            
        if getattr(args, 'disable_srgb', False):
            print("TEST MODE: sRGB framebuffer disabled (gamma-incorrect blending)")
            print("Testing if artifacts are related to gamma correction")
            print("-" * 50)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._disable_srgb_framebuffer = True
            
        if getattr(args, 'test_offscreen_png', False):
            print("ISOLATION TEST: Offscreen RGBA16F PNG render")
            print("Clean PNG = presentation issue, Dirty PNG = shader/math issue")
            print("Will save to spiral_offscreen_test.png")
            print("-" * 50)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._test_offscreen_png = True
            
        if getattr(args, 'no_overlays', False):
            print("ISOLATION TEST: No overlays/widgets (pure GL window)")
            print("Tests if Qt widgets/overlays trigger compositor artifacts")
            print("-" * 50)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._no_overlays_mode = True
            
        if getattr(args, 'move_scale_test', False):
            print("ISOLATION TEST: Move/Scale Pattern Check")
            print("Drag and scale the window during the test:")
            print("• Pattern fixed to screen → post-render (compositor/driver/monitor)")
            print("• Pattern scales with content → your rendering path")
            print("-" * 50)
            
        if getattr(args, 'internal_opacity', False):
            print("SOLUTION MODE: Internal opacity blending with opaque window")
            print("This bypasses Windows DWM dithering by keeping window opaque")
            print("Opacity blending happens inside the shader: mix(bgColor, spiralColor, opacity)")
            print("-" * 70)
            # Set module-level flag for compositor to detect
            import sys
            sys.modules[__name__]._internal_opacity_mode = True
            
        # Debug OpenGL implementation info
        if getattr(args, 'debug_gl_info', False):
            def print_gl_info():
                try:
                    from OpenGL import GL
                    version = GL.glGetString(GL.GL_VERSION)
                    renderer = GL.glGetString(GL.GL_RENDERER) 
                    vendor = GL.glGetString(GL.GL_VENDOR)
                    print(f"OpenGL Version: {version.decode() if version else 'Unknown'}")
                    print(f"OpenGL Renderer: {renderer.decode() if renderer else 'Unknown'}")
                    print(f"OpenGL Vendor: {vendor.decode() if vendor else 'Unknown'}")
                    
                    # Check for ANGLE
                    if renderer and b"ANGLE" in renderer:
                        print("⚠️  ANGLE detected - using D3D backend (may cause dithering)")
                    else:
                        print("✅ Desktop OpenGL detected")
                    
                    # Test 3: Check multisampling status
                    try:
                        multisample_enabled = GL.glIsEnabled(GL.GL_MULTISAMPLE)
                        sample_buffers = GL.glGetIntegerv(GL.GL_SAMPLE_BUFFERS)
                        samples = GL.glGetIntegerv(GL.GL_SAMPLES)
                        print(f"GL_MULTISAMPLE enabled: {multisample_enabled}")
                        print(f"Sample buffers: {sample_buffers}")
                        print(f"Samples: {samples}")
                        
                        # Disable multisampling for test
                        if getattr(args, 'no_msaa', False):
                            GL.glDisable(GL.GL_MULTISAMPLE)
                            try:
                                GL.glDisable(0x8C36)  # GL_SAMPLE_SHADING
                            except Exception:
                                pass
                            print("✅ Multisampling disabled for test")
                            
                    except Exception as e:
                        print(f"Could not query/disable multisampling: {e}")
                        
                except Exception as e:
                    print(f"Could not query OpenGL info: {e}")
            
            # Schedule GL info print after context is ready
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, print_gl_info)
            
        def check_window_layered_status(widget):
            """Check if window has WS_EX_LAYERED flag (indicates DWM will dither)"""
            try:
                hwnd = int(widget.winId())
                from ctypes import windll, wintypes
                GetWindowLongPtr = windll.user32.GetWindowLongPtrW
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                ex = GetWindowLongPtr(hwnd, GWL_EXSTYLE)
                is_layered = bool(ex & WS_EX_LAYERED)
                print(f"Windows API Check: WS_EX_LAYERED = {is_layered}")
                print(f"Extended Style = 0x{ex:08X}")
                if is_layered:
                    print("⚠️  WARNING: Window is layered - DWM will apply dithering!")
                    print("   Fix: Ensure WA_TranslucentBackground=False and windowOpacity=1.0")
                else:
                    print("✅ GOOD: Window is opaque - no DWM dithering expected")
                return is_layered
            except Exception as e:
                print(f"Could not check window flags: {e}")
                return None
        # Assign to requested screen if available
        try:
            screens = app.screens()
            screen_idx = getattr(args, "screen", 0)
            if screens and 0 <= screen_idx < len(screens):
                comp.setScreen(screens[screen_idx])
        except Exception as e:
            print(f"spiral-test: could not assign to screen {getattr(args, 'screen', 0)}: {e}")
        comp.showFullScreen()
        # Process events to allow initializeGL to run regardless of force.
        cycles = 20 if not getattr(args, 'force', False) else 8  # Increased wait cycles
        for i in range(cycles):
            app.processEvents()
            if getattr(comp, 'available', False):
                break
            if i % 5 == 0:  # Debug every 5th cycle
                logging.getLogger(__name__).info(f"[spiral.trace] Waiting for GL context... cycle {i+1}/{cycles}, available={getattr(comp, 'available', False)}")
        if not getattr(comp, 'available', False):
            logging.getLogger(__name__).error(f"[spiral.trace] GL context check failed: available={getattr(comp, 'available', None)}, initialized={getattr(comp, '_initialized', None)}")
            print("MesmerLoom spiral-test: GL unavailable: context failure")
            print("Try running with --force to bypass this check")
            sys.exit(77)
            
        # Check Windows API flags for DWM dithering diagnosis
        if check_flags or internal_opacity:
            print("\n" + "="*50)
            print("WINDOWS API DIAGNOSTIC CHECK")
            print("="*50)
            try:
                check_window_layered_status(comp)
            except Exception as e:
                print(f"Could not check window layered status: {e}")
            
            # B) Verify framebuffer has no alpha (for QOpenGLWidget)
            try:
                if hasattr(comp, 'format'):
                    alpha_size = comp.format().alphaBufferSize()
                    print(f"OpenGL alphaBufferSize = {alpha_size}")
                    if alpha_size > 0:
                        print("⚠️  WARNING: Framebuffer has alpha channel - may cause Qt compositing artifacts!")
                        print("   Fix: Ensure QSurfaceFormat.setAlphaBufferSize(0) before QApplication")
                    else:
                        print("✅ GOOD: Framebuffer is opaque (no alpha channel)")
                else:
                    print("✅ QOpenGLWindow: No widget framebuffer (direct rendering)")
            except Exception as e:
                print(f"Could not check framebuffer format: {e}")
                
            print("="*50 + "\n")
        # Configure and run loop
        blend_map = {"multiply": 0, "screen": 1, "softlight": 2}
        try:
            comp.set_blend_mode(blend_map.get(getattr(args, 'blend', 'multiply').lower(), 0))
        except Exception:
            pass
        try:
            comp.set_render_scale(float(getattr(args, 'render_scale', '1.0')))
        except Exception:
            pass
        dur = max(0.1, float(getattr(args, 'duration', 5.0)))
        t0 = _time.perf_counter(); last = t0; frames = 0
        target_frame = 1.0 / 60.0
        while True:
            now = _time.perf_counter(); elapsed = now - t0
            if elapsed >= dur:
                break
            dt = now - last; last = now
            # The compositor automatically handles director updates and uniform setting in paintGL
            app.processEvents()
            frames += 1
            # Frame pacing (~60fps) to avoid runaway CPU loop on headless
            frame_spent = _time.perf_counter() - now
            remaining = target_frame - frame_spent
            if remaining > 0:
                try:
                    import time as __t; __t.sleep(remaining)
                except Exception:
                    pass
        total = max(1e-6, _time.perf_counter() - t0)
        if frames == 0:
            print("MesmerLoom spiral-test: GL unavailable: no frames")
            sys.exit(77)
        fps = frames / total
        print(f"MesmerLoom spiral-test duration={dur:.2f}s frames={frames} avg_frame_ms={(total/frames*1000.0 if frames else 0):.2f} fps={fps:.1f}")
        try:
            comp.close()
        except Exception:
            pass
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        print("MesmerLoom spiral-test: error:", e)
        sys.exit(1)

def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging before doing any work
    # Suppress pygame support prompt globally for all commands (ensures JSON-only stdout for tests)
    import os as _os_global
    _os_global.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    setup_logging(
        level=args.log_level,
        log_file=args.log_file,
        json_format=(args.log_format == "json"),
        add_console=True,
    )

    cmd = args.command or "run"
    if cmd == "run":
        # Import app lazily so that commands like 'session' don't trigger pygame/audio init
        # which would emit banners on stdout and break JSON parsing in tests.
        from .app import run as run_gui  # local import
        run_gui()
        return 0
    if cmd == "selftest":
        return selftest()
    if cmd == "spiral-test":
        cmd_spiral_test(args)  # exits via sys.exit inside handler
        return 0  # not reached
    if cmd == "session":
        import json as _json
        import os as _os
        _os.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
        pack_path = getattr(args, "load", None)
        if not pack_path or not os.path.exists(pack_path):
            msg = f"Error: session pack file not found: {pack_path}"
            print(msg)
            print(msg, file=sys.stderr)
            return 1
        try:
            from .content.loader import load_session_pack
            pack = load_session_pack(pack_path)
        except Exception as e:
            msg = f"Error: failed to load session pack: {e}"
            print(msg)
            print(msg, file=sys.stderr)
            return 1
        # If no mutually exclusive flag is set, default to summary
        if not (args.print or args.apply or args.summary):
            args.summary = True
        if args.print:
            try:
                print(_json.dumps(pack.to_canonical_dict(), ensure_ascii=False, separators=(",", ":")))
            except Exception as e:
                print(f"Error: failed to encode session pack as JSON: {e}")
                return 1
            return 0
        if args.apply:
            from PyQt6.QtWidgets import QApplication
            from .ui.launcher import Launcher
            import sys as _sys, io as _io
            app = QApplication.instance() or QApplication([])
            _real_stdout = _sys.stdout
            _sys.stdout = _io.StringIO()
            try:
                win = Launcher("MesmerGlass", enable_device_sync_default=False)
            finally:
                _sys.stdout = _real_stdout
            try:
                if hasattr(win, "apply_session_pack"):
                    win.apply_session_pack(pack)
            except Exception as e:
                print(f"Error: failed to apply session pack: {e}")
                return 1
            status = {"pack": pack.name, "text": getattr(win, "text", None), "buzz_intensity": getattr(win, "buzz_intensity", None)}
            print(_json.dumps(status, ensure_ascii=False))
            try:
                win.close()
            except Exception:
                pass
            return 0
        if args.summary:
            ti = f"{len(pack.text.items)} text" if hasattr(pack, 'text') and hasattr(pack.text, 'items') and pack.text.items else "0 text"
            ps = f"{len(pack.pulse.stages)} stages" if hasattr(pack, 'pulse') and hasattr(pack.pulse, 'stages') and pack.pulse.stages else "0 stages"
            print(f"SessionPack '{pack.name}' v{pack.version} — {ti}, {ps}")
            return 0
    if cmd == "state":
        from .content.loader import load_session_state, save_session_state
        from PyQt6.QtWidgets import QApplication
        from .ui.launcher import Launcher
        target = args.file
        # Suppress server for rapid headless state capture/apply
        import os as _os
        _os.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
        if args.save:
            app = QApplication.instance() or QApplication([])
            win = Launcher("MesmerGlass", enable_device_sync_default=False)
            st = win.capture_session_state()
            if st is None:
                logging.getLogger(__name__).error("Failed to capture session state")
                return 1
            try:
                save_session_state(st, target)
            except Exception as e:
                logging.getLogger(__name__).error("Failed to save state: %s", e)
                return 1
            return 0
        if args.print:
            try:
                st = load_session_state(target)
            except Exception as e:
                logging.getLogger(__name__).error("Failed to load state: %s", e)
                return 1
            import json as _json
            print(_json.dumps(st.to_json_dict(), ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.apply:
            try:
                st = load_session_state(target)
            except Exception as e:
                logging.getLogger(__name__).error("Failed to load state: %s", e)
                return 1
            app = QApplication.instance() or QApplication([])
            win = Launcher("MesmerGlass", enable_device_sync_default=False)
            win.apply_session_state(st)
            # Provide a minimal status JSON for callers
            import json as _json
            status = {
                "video_primary": getattr(win, "primary_path", None),
                "vol1": getattr(win, "vol1", None),
                "fx_mode": getattr(win, "fx_mode", None),
                "buzz_intensity": getattr(win, "buzz_intensity", None),
            }
            print(_json.dumps(status, ensure_ascii=False, separators=(",", ":")))
            try:
                win.close()
            except Exception:
                pass
            return 0
    if cmd == "test":  # backward compatibility alias
        warnings.warn("'test' subcommand is deprecated; use 'pulse' instead", DeprecationWarning, stacklevel=2)
        cmd = "pulse"
    if cmd == "pulse":
        return asyncio.run(_cli_pulse(args.level, args.duration, args.port))
    if cmd == "test-run":
        # Re-implement logic from legacy run_tests.py script.
        python_cmd = sys.executable  # prefer current interpreter (inside venv if active)
        cmdline = [python_cmd, "-m", "pytest"]
        if args.verbose:
            cmdline.extend(["-v","-s"])
        if args.coverage:
            cmdline.extend(["--cov=mesmerglass","--cov-report=term","--cov-report=html"])
        t = args.type
        if t == "fast": cmdline.extend(["-m","not slow"])
        elif t == "slow": cmdline.extend(["-m","slow"])
        elif t == "integration": cmdline.extend(["-m","integration"])
        elif t == "bluetooth": cmdline.extend(["-m","bluetooth"])
        elif t == "unit": cmdline.extend(["-m","not integration and not bluetooth"])
        cmdline.append("mesmerglass/tests")
        # If we are already running inside pytest (detected via env var) avoid executing
        # the full test suite recursively; just collect quickly. This prevents hang/timeouts
        # in CI where test-run is itself tested.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            cmdline.extend(["--maxfail","1","--collect-only"])
        logging.getLogger(__name__).info("Running tests: %s", " ".join(cmdline))
        return subprocess.run(cmdline).returncode
    if cmd == "server":
        return _cli_server(args.port)
    if cmd == "ui":
        # Minimal Qt session to drive tab operations without side effects.
        # Import here to avoid unnecessary Qt init for non-UI subcommands.
        from PyQt6.QtWidgets import QApplication
        from .ui.launcher import Launcher
        # For pure status queries (no launch/show) force suppress server to keep fast & isolated
        if args.status and not (args.launch or args.show):
            os.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
        _pure_status = bool(args.status and not (args.launch or args.show))
        # If pure status: capture stdout and temporarily remove console log handlers to avoid
        # contaminating JSON output (tests expect first printed line to be JSON)
        import sys as _sys, io as _io, logging as _logging
        _captured_buf = None; _removed_handlers = []
        if _pure_status:
            _captured_buf = _io.StringIO(); _real_stdout = _sys.stdout; _sys.stdout = _captured_buf
            root_logger = _logging.getLogger()
            for h in list(root_logger.handlers):
                if isinstance(h, _logging.StreamHandler):
                    root_logger.removeHandler(h); _removed_handlers.append(h)
        # Note: use no-show by default to avoid window popups in CI.
        app = QApplication.instance() or QApplication([])
        win = Launcher(
            "MesmerGlass",
            enable_device_sync_default=False,  # disable device sync for CLI actions to keep tests deterministic
            layout_mode=getattr(args, "layout", "tabbed"),  # pass through layout selection
        )
        if _pure_status:
            # Discard any captured construction noise (pygame banner, etc.)
            _sys.stdout = _real_stdout
        if getattr(args, "show", False):
            win.show()
        # Perform actions
        if args.list_tabs:
            names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
            for n in names:
                print(n)
            # No need to run event loop for just listing
            win.close()
            return 0
        if args.tab is not None:
            target = args.tab.strip()
            # Try index
            idx = None
            if target.isdigit():
                i = int(target)
                if 0 <= i < win.tabs.count():
                    idx = i
            if idx is None:
                # Name match (case-insensitive)
                for i in range(win.tabs.count()):
                    if win.tabs.tabText(i).lower() == target.lower():
                        idx = i; break
            if idx is None:
                logging.getLogger(__name__).error("Unknown tab: %s", target)
                win.close()
            win.tabs.setCurrentIndex(idx)
            logging.getLogger(__name__).info("Selected tab: %s", win.tabs.tabText(idx))
        # Load state first if requested (so subsequent setters override)
        loaded_state_font_path = None
        if getattr(args, 'load_state', None):
            try:
                from .content.loader import load_session_state
                st = load_session_state(args.load_state)
            except Exception as e:
                # Fallback: accept minimal dict state (tests may omit kind/version)
                st = None
                try:
                    import json as _json
                    with open(args.load_state, 'r', encoding='utf-8') as fh:
                        raw = _json.load(fh)
                    if isinstance(raw, dict):
                        st = raw  # pass raw dict directly to launcher (it can handle dict)
                        logging.getLogger(__name__).warning("Using raw dict session state fallback (missing metadata): %s", args.load_state)
                    else:
                        raise ValueError("State JSON not an object")
                except Exception as e2:
                    logging.getLogger(__name__).error("Failed to load state: %s (%s / fallback %s)", args.load_state, e, e2)
                    st = None
            if st is not None:
                try:
                    win.apply_session_state(st)
                except Exception:
                    logging.getLogger(__name__).error("State apply failed: %s", args.load_state)
                # Extract font path (supports object or dict forms)
                try:
                    if isinstance(st, dict):
                        fp = (st.get('textfx') or {}).get('font_path')
                    else:
                        fp = getattr(st, 'textfx', {}).get('font_path') if hasattr(st, 'textfx') else None
                    if fp and not getattr(win, 'current_font_path', None):
                        win.current_font_path = fp
                    loaded_state_font_path = fp
                except Exception:
                    pass
        # Apply setters
        if args.set_text is not None:
            win.text = args.set_text
            try:
                win.page_textfx.set_text(args.set_text)  # best-effort sync to UI if available
            except Exception:
                pass
        if args.set_text_scale is not None:
            win.text_scale_pct = max(0, min(100, int(args.set_text_scale)))
        if args.set_fx_mode is not None:
            win.fx_mode = args.set_fx_mode
        if args.set_fx_intensity is not None:
            win.fx_intensity = max(0, min(100, int(args.set_fx_intensity)))
        if getattr(args, "set_font_path", None):
            # Headless font load; best-effort (invalid fonts are ignored but path is recorded)
            try:
                from PyQt6.QtGui import QFontDatabase, QFont
                fp = args.set_font_path
                fam = None
                if os.path.isfile(fp):  # only attempt load if file exists
                    fid = QFontDatabase.addApplicationFont(fp)
                    if fid != -1:
                        fams = QFontDatabase.applicationFontFamilies(fid)
                        if fams:
                            fam = fams[0]
                win.current_font_path = fp
                if fam:
                    try:
                        # Preserve size if already set
                        size = getattr(win, 'text_font', None).pointSize() if getattr(win, 'text_font', None) else 24
                        win.text_font = QFont(fam, size)
                    except Exception:
                        pass
                try:
                    if hasattr(win, 'page_textfx') and hasattr(win.page_textfx, 'update_font_label'):
                        win.page_textfx.update_font_label(fam or '(default)')
                except Exception:
                    pass
            except Exception:
                pass  # silent failure keeps CLI deterministic
        if args.vol1 is not None or args.vol2 is not None:
            v1 = win.vol1 if args.vol1 is None else max(0, min(100, int(args.vol1))) / 100.0
            v2 = win.vol2 if args.vol2 is None else max(0, min(100, int(args.vol2))) / 100.0
            # Use the launcher's helper to also update audio engine
            try:
                win._set_vols(v1, v2)
            except Exception:
                win.vol1, win.vol2 = v1, v2
        if args.displays is not None:
            if args.displays == "all":
                win._select_all_displays()
            elif args.displays == "primary":
                win._select_primary_display()
            else:
                # none
                for i in range(win.list_displays.count()):
                    win.list_displays.item(i).setCheckState(0)
        # Actions
        if args.launch:
            win.launch()
        if args.stop:
            win.stop_all()
        # Status as JSON (printed before the event loop runs for deterministic tests)
        if args.status:
            import json
            # Prefer explicit UI label for font family (reflects state even if QFont not applied)
            ui_font_family = None
            try:
                if hasattr(win, 'page_textfx') and hasattr(win.page_textfx, 'lab_font_family'):
                    ui_font_family = win.page_textfx.lab_font_family.text()
            except Exception:
                pass
            # Fallback: if current_font_path still None but state had one
            font_path_val = getattr(win, "current_font_path", None) or loaded_state_font_path
            status = {
                "tab": win.tabs.tabText(win.tabs.currentIndex()),
                "running": bool(getattr(win, "running", False)),
                "text": getattr(win, "text", None),
                "fx_mode": getattr(win, "fx_mode", None),
                "fx_intensity": getattr(win, "fx_intensity", None),
                "font_path": font_path_val,
                "font_family": ui_font_family or (
                    getattr(getattr(win, 'text_font', None), 'family', lambda: None)() if getattr(win, 'text_font', None) else None
                ),
                "vol1": getattr(win, "vol1", None),
                "vol2": getattr(win, "vol2", None),
                "displays_checked": sum(1 for i in range(win.list_displays.count()) if win.list_displays.item(i).checkState() != 0),
            }
            print(json.dumps(status))
            # Restore console handlers if removed
            if _pure_status and _removed_handlers:
                root_logger = _logging.getLogger()
                for h in _removed_handlers:
                    root_logger.addHandler(h)
        # If only requesting status and not launching/showing, skip event loop to exit fast
        if not (args.launch or args.show) and args.status and not any([
            args.set_text, args.set_text_scale, args.set_fx_mode, args.set_fx_intensity,
            args.set_font_path, args.vol1, args.vol2, args.displays, args.tab, args.load_state
        ]):
            try: win.close()
            except Exception: pass
            return 0
        # Otherwise spin event loop briefly; a single-shot QTimer quits after timeout
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(int(max(0.0, args.timeout) * 1000), app.quit)
        app.exec()
        try:
            win.close()
        except Exception:
            pass
        return 0
    if cmd == "toy":
        # Minimal async runner for the toy
        async def _run_toy() -> int:
            toy = VirtualToy(
                name=args.name,
                port=args.port,
                latency_ms=args.latency_ms,
                mapping=args.map,  # type: ignore[arg-type]
                gain=args.gain,
                gamma=args.gamma,
                offset=args.offset,
            )
            ok = await toy.connect()
            if not ok:
                return 1
            listen_task = asyncio.create_task(toy.start_listening())
            try:
                await asyncio.sleep(max(0.0, float(args.run_for)))
                return 0
            finally:
                listen_task.cancel()
                await toy.disconnect()
        return asyncio.run(_run_toy())

    parser.print_help()
    return 2


if __name__ == "__main__":  # Allow direct module execution
    raise SystemExit(main())
