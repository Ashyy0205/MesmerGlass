"""MesmerGlass command-line interface.

Argparse-based CLI that mirrors/extends run.py commands and initializes
structured logging early. Exposed via ``python -m mesmerglass``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
from pathlib import Path
from dataclasses import asdict
from typing import Optional, Callable

# Suppress pygame support prompt so JSON outputs (e.g. session --print) remain clean.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from .engine.buttplug_server import ButtplugServer
from .engine.pulse import PulseEngine
from .logging_utils import setup_logging, get_default_log_path, LogMode, PerfTracer
from .devtools.virtual_toy import VirtualToy  # dev-only, used by 'toy' subcommand
from .content.loader import load_session_pack  # session packs
from .session.cue import AudioRole
import subprocess, sys, warnings
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
        "--log-mode",
        choices=[mode.value for mode in LogMode],
        default=LogMode.NORMAL.value,
        help="Logging preset: quiet suppresses console info, perf forces DEBUG",
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


def _build_logging_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    _add_logging_args(parent)
    return parent


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
        from .mesmerloom.window_compositor import LoomWindowCompositor

        if not hasattr(LoomWindowCompositor, "get_background_debug_state"):
            raise RuntimeError("Background diagnostics helper missing")

        msg = "Selftest OK: imports + background diagnostics available"
        logging.getLogger(__name__).info(msg)
        print(msg)
        return 0
    except Exception as e:
        logging.getLogger(__name__).error("Selftest failed: %s", e)
        return 1


def _parse_instruction_lines(file_path: Path) -> list[tuple[int, str, list[str]]]:
    commands: list[tuple[int, str, list[str]]] = []
    content = file_path.read_text(encoding="utf-8")
    for lineno, raw_line in enumerate(content.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            argv = shlex.split(raw_line, comments=True, posix=True)
        except ValueError as exc:
            raise ValueError(f"Invalid syntax on line {lineno}: {exc}") from exc
        if not argv:
            continue
        commands.append((lineno, raw_line.rstrip(), argv))
    return commands


def run_instruction_file(
    file_path: str | os.PathLike[str],
    *,
    continue_on_error: bool = False,
    dry_run: bool = False,
    workdir: Optional[str] = None,
    echo: bool = True,
) -> int:
    """Execute a newline-delimited list of CLI commands."""

    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        print(f"instructions: file not found: {path}")
        return 1
    try:
        commands = _parse_instruction_lines(path)
    except ValueError as exc:
        print(f"instructions: {exc}")
        return 2
    if not commands:
        print(f"instructions: no runnable commands in {path}")
        return 0

    if workdir:
        if workdir == "@file":
            cwd = path.parent
        else:
            cwd = Path(workdir).expanduser().resolve()
    else:
        cwd = Path.cwd()
    if not cwd.exists():
        print(f"instructions: working directory does not exist: {cwd}")
        return 1

    total = len(commands)
    final_rc = 0
    for idx, (lineno, raw_line, argv) in enumerate(commands, start=1):
        display = " ".join(argv)
        if echo:
            print(f"[instructions] ({idx}/{total}) {display}")
        if dry_run:
            continue
        proc = subprocess.run(
            [sys.executable, "-m", "mesmerglass", *argv],
            cwd=str(cwd),
        )
        if proc.returncode != 0:
            msg = (
                f"instructions: command from line {lineno} failed with exit code {proc.returncode}"
            )
            print(msg)
            final_rc = proc.returncode
            if not continue_on_error:
                return final_rc
    return final_rc


def _load_theme_bank_from_media_bank(
    media_bank_path: Path,
    *,
    cache_size: int = 256,
):
    """Build a ThemeBank instance directly from media_bank.json entries."""

    from mesmerglass.content.theme import ThemeConfig
    from mesmerglass.content.themebank import ThemeBank
    from mesmerglass.content.media_scan import scan_media_directory, scan_font_directory

    log = logging.getLogger(__name__)
    path = media_bank_path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"media bank not found: {path}")

    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - malformed user file
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(entries, list):
        raise ValueError(f"Media bank must be a list of entries (got {type(entries).__name__})")

    themes: list[ThemeConfig] = []
    font_paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not raw_path:
            continue
        dir_path = Path(raw_path).expanduser()
        if not dir_path.exists():
            log.warning("[themebank.cli] Skipping missing directory: %s", dir_path)
            continue
        media_type = (entry.get("type") or "both").lower()
        if media_type == "fonts":
            font_paths.extend(scan_font_directory(dir_path))
            continue

        images, videos = scan_media_directory(dir_path)
        if media_type == "images":
            videos = []
        elif media_type == "videos":
            images = []
        theme = ThemeConfig(
            name=entry.get("name", dir_path.name),
            enabled=True,
            image_path=images,
            animation_path=videos,
            font_path=[],
            text_line=[],
        )
        themes.append(theme)

    if not themes:
        raise RuntimeError("No usable media directories were found; run 'media bank' setup first")

    bank = ThemeBank(
        themes=themes,
        root_path=Path("."),
        image_cache_size=max(32, cache_size),
    )
    alt_index = 2 if len(themes) > 1 else None
    bank.set_active_themes(primary_index=1, alt_index=alt_index)
    bank.set_font_library(font_paths)
    return bank


def _themebank_payload(status, *, require_videos: bool) -> dict:
    payload = asdict(status)
    payload["requires_videos"] = require_videos
    payload["ready"] = bool(status.ready and (not require_videos or status.total_videos > 0))
    return payload


def cmd_themebank(args) -> int:
    """CLI helpers for ThemeBank readiness diagnostics."""

    from mesmerglass.content.themebank import ThemeBank

    media_bank = Path(getattr(args, "media_bank", "media_bank.json") or "media_bank.json")
    wait_s = max(0.0, float(getattr(args, "wait", 0.0) or 0.0))
    require_videos_flag = bool(getattr(args, "require_videos", False))
    cmd = getattr(args, "themebank_cmd", "stats")
    enforce_videos = bool(require_videos_flag or cmd == "pull-video")

    try:
        bank: ThemeBank = _load_theme_bank_from_media_bank(media_bank)
    except Exception as exc:
        print(f"themebank: {exc}", file=sys.stderr)
        return 2

    try:
        status = bank.ensure_ready(require_videos=enforce_videos, timeout_s=wait_s)
        payload = _themebank_payload(status, require_videos=enforce_videos)
        ready = payload["ready"]

        if cmd == "stats":
            if getattr(args, "json", False):
                print(json.dumps({"media_bank": str(media_bank), **payload}, indent=2))
            else:
                print(f"ThemeBank ready: {'yes' if ready else 'no'} ({status.ready_reason})")
                print(f"  Themes: {payload['themes_total']} (primary={payload['active_primary']} alt={payload['active_alternate']})")
                print(f"  Images: {payload['total_images']} cached={payload['cached_images']} pending={payload['pending_loads']}")
                print(f"  Videos: {payload['total_videos']}")
                if payload.get("last_image_path"):
                    print(f"  Last image: {payload['last_image_path']}")
                if payload.get("last_video_path"):
                    print(f"  Last video: {payload['last_video_path']}")
            return 0 if ready else 2

        if cmd == "selftest":
            if ready:
                print("ThemeBank selftest OK")
                return 0
            print(f"ThemeBank selftest FAILED ({status.ready_reason})", file=sys.stderr)
            return 3

        if cmd == "pull-image":
            image = bank.get_image()
            if image is None:
                print("themebank pull-image: ThemeBank returned no image (empty cache)", file=sys.stderr)
                return 4
            print(f"Loaded image {image.width}x{image.height} from {image.path}")
            return 0

        if cmd == "pull-video":
            video_path = bank.get_video()
            if video_path is None:
                print("themebank pull-video: ThemeBank returned no video", file=sys.stderr)
                return 5
            print(str(video_path))
            return 0

        print(f"themebank: unknown subcommand '{cmd}'", file=sys.stderr)
        return 2
    finally:
        bank.shutdown()


def build_parser() -> argparse.ArgumentParser:
    logging_parent = _build_logging_parent()
    parser = argparse.ArgumentParser(
        description="MesmerGlass CLI",
        parents=[logging_parent],
    )
    sub = parser.add_subparsers(dest="command", required=False)

    def add_subparser(name: str, **kwargs: object) -> argparse.ArgumentParser:
        parents = list(kwargs.pop("parents", []))
        parents.insert(0, logging_parent)
        return sub.add_parser(name, parents=parents, **kwargs)

    # GUI launcher
    p_run = add_subparser("run", help="Start the GUI (default)")
    p_run.add_argument("--vr", action="store_true", help="Enable head-locked VR streaming (OpenXR if available; falls back to mock)")
    p_run.add_argument("--vr-mock", action="store_true", help="Force VR mock mode (no OpenXR session)")
    p_run.add_argument("--vr-no-begin", action="store_true", help="Proceed without explicit xrBeginSession (unsafe; for minimal bindings)")
    p_run.add_argument("--vr-safe-mode", action="store_true", help="Use offscreen FBO tap inside compositor to mirror frames to VR (safer on some drivers)")
    p_run.add_argument("--vr-minimal", action="store_true", help="Disable media/text/video subsystems; stream spiral only for maximum stability")
    p_run.add_argument("--vr-allow-media", action="store_true", help="Do not auto-mute media components when running in VR (may be unstable)")
    p_run.add_argument("--session-file", type=str, default=None, help="Path to .session.json to auto-load on startup")
    p_run.add_argument("--session-cuelist", type=str, default=None, help="Cuelist key within the session to load after startup")
    p_run.add_argument("--auto-duration", type=float, default=None, help="Auto-stop the session after N seconds (optional)")
    p_run.add_argument("--auto-exit", action="store_true", help="Quit the app automatically after autorun completes")

    run_theme = p_run.add_argument_group("ThemeBank throttles")
    run_theme.add_argument("--theme-lookahead", type=int, metavar="N", help="Cap ThemeBank lookahead queue (default 32)")
    run_theme.add_argument("--theme-batch", type=int, metavar="N", help="Limit images decoded per preload batch (default 12)")
    run_theme.add_argument("--theme-sleep-ms", type=float, metavar="MS", help="Sleep between background loads in ms (default 4.0)")
    run_theme.add_argument("--theme-max-ms", type=float, metavar="MS", help="Time budget per preload batch before yielding (default 200)")
    run_theme.add_argument("--media-queue", type=int, metavar="N", help="Async image decode queue depth (default 8)")
    theme_toggle = run_theme.add_mutually_exclusive_group()
    theme_toggle.add_argument("--theme-preload-all", action="store_true", help="Force legacy preload-all behavior (loads every image immediately)")
    theme_toggle.add_argument("--theme-no-preload", action="store_true", help="Disable background lookahead threads entirely")

    p_pulse = add_subparser("pulse", help="Send a single pulse (alias: 'test')")
    p_pulse.add_argument("--level", type=float, default=0.5, help="Pulse intensity 0..1")
    p_pulse.add_argument("--duration", type=int, default=500, help="Duration in ms")
    p_pulse.add_argument("--port", type=int, default=12345, help="Buttplug server port")

    # Alias for backward compatibility (was 'test' in run.py)
    p_test_alias = add_subparser("test", help=argparse.SUPPRESS)
    p_test_alias.add_argument("--level", type=float, default=0.5)
    p_test_alias.add_argument("--duration", type=int, default=500)
    p_test_alias.add_argument("--port", type=int, default=12345)

    p_srv = add_subparser("server", help="Start a local Buttplug server")
    p_srv.add_argument("--port", type=int, default=12345)

    p_ui = add_subparser("ui", help="Drive basic UI navigation for testing")
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

    p_instr = add_subparser("instructions", help="Execute CLI commands listed in a text file")
    p_instr.add_argument("file", help="Path to instructions text file")
    p_instr.add_argument("--workdir", type=str, default=None,
                         help="Working directory for commands (default: current dir; use @file for the instructions folder)")
    p_instr.add_argument("--continue-on-error", action="store_true",
                         help="Run all commands even if one fails (exit status reflects failures)")
    p_instr.add_argument("--dry-run", action="store_true",
                         help="Parse and print commands without executing them")
    p_instr.add_argument("--no-echo", dest="echo", action="store_false",
                         help="Suppress per-command echo output")
    p_instr.set_defaults(echo=True)

    # dev-only: virtual toy simulator to drive tests or local dev without hardware
    p_toy = add_subparser("toy", help="Run a deterministic virtual toy simulator (dev-only)")
    p_toy.add_argument("--name", type=str, default="Virtual Test Toy")
    p_toy.add_argument("--port", type=int, default=12345)
    p_toy.add_argument("--latency-ms", type=int, default=0)
    p_toy.add_argument("--map", choices=["linear", "ease"], default="linear")
    p_toy.add_argument("--gain", type=float, default=1.0)
    p_toy.add_argument("--gamma", type=float, default=1.0)
    p_toy.add_argument("--offset", type=float, default=0.0)
    p_toy.add_argument("--run-for", type=float, default=5.0, help="Seconds to run before exiting")

    add_subparser("selftest", help="Quick environment/import check")
    
    # Theme and media loading commands
    p_theme = add_subparser("theme", help="Theme and media loading test")
    p_theme.add_argument("--load", type=str, help="Path to theme JSON file")
    p_theme.add_argument("--list", action="store_true", help="List available themes in collection")
    p_theme.add_argument("--show-config", action="store_true", help="Print theme configuration as JSON")
    p_theme.add_argument("--test-shuffler", type=int, metavar="N", help="Test weighted shuffler N times")
    p_theme.add_argument("--test-cache", action="store_true", help="Test image cache with sample images")
    p_theme.add_argument("--diag", action="store_true", help="Run ThemeBank perf diagnostics (requires --load)")
    p_theme.add_argument("--diag-json", action="store_true", help="Print raw PerfTracer snapshot for diagnostics")
    p_theme.add_argument("--diag-limit", type=int, default=10, help="Maximum spans to list in diagnostics output")
    p_theme.add_argument("--diag-threshold", type=float, default=150.0, help="Highlight spans at/above this duration in ms")
    p_theme.add_argument("--diag-lookups", type=int, default=24, help="Number of get_image calls to simulate during diagnostics")
    p_theme.add_argument("--diag-cache-size", type=int, default=128, help="Image cache size for ThemeBank diagnostics")
    p_theme.add_argument("--diag-prefetch-only", action="store_true", help="Skip sync get_image calls and only run prefetch threads")
    p_theme.add_argument("--diag-fail", action="store_true", help="Exit with code 3 if any span meets/exceeds --diag-threshold")

    p_themebank = add_subparser("themebank", help="Inspect or selftest ThemeBank media readiness")
    tb_sub = p_themebank.add_subparsers(dest="themebank_cmd", required=True)

    # Put shared options on a parent so users can write either:
    #   themebank --media-bank X stats
    # or
    #   themebank stats --media-bank X
    tb_parent = argparse.ArgumentParser(add_help=False)
    tb_parent.add_argument("--media-bank", default="media_bank.json", help="Path to media_bank.json (default: %(default)s)")
    tb_parent.add_argument("--wait", type=float, default=0.0, help="Seconds to wait for readiness before evaluating (default: 0)")

    tb_stats = tb_sub.add_parser("stats", parents=[tb_parent], help="Print ThemeBank readiness summary")
    tb_stats.add_argument("--require-videos", action="store_true", help="Treat missing videos as failure")
    tb_stats.add_argument("--json", action="store_true", help="Emit JSON payload instead of text")
    tb_self = tb_sub.add_parser("selftest", parents=[tb_parent], help="Exit 0 when ThemeBank has accessible media")
    tb_self.add_argument("--require-videos", action="store_true", help="Require at least one video")
    tb_pull_image = tb_sub.add_parser("pull-image", parents=[tb_parent], help="Load a single ThemeBank image and print metadata")
    tb_pull_video = tb_sub.add_parser("pull-video", parents=[tb_parent], help="Select a ThemeBank video and print its path")
    
    # MesmerLoom spiral visual test (Phase 2 real implementation)
    p_spiral = add_subparser("spiral-test", help="Run a bounded MesmerLoom spiral render test")
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

    # Spiral type testing (Trance 7-type system)
    p_spiral_type = add_subparser("spiral-type", help="Test specific Trance spiral types (1-7)")
    p_spiral_type.add_argument("--type", type=int, choices=range(1, 8), default=3,
                              help="Spiral type: 1=log, 2=quad, 3=linear, 4=sqrt, 5=inverse, 6=power, 7=modulated (default: 3)")
    p_spiral_type.add_argument("--width", type=int, choices=[360, 180, 120, 90, 72, 60], default=60,
                              help="Spiral width in degrees (default: 60)")
    p_spiral_type.add_argument("--rotation", type=float, default=2.0,
                              help="Rotation speed amount (default: 2.0)")
    p_spiral_type.add_argument("--duration", type=float, default=10.0,
                              help="Test duration in seconds (default: 10)")
    p_spiral_type.add_argument("--intensity", type=float, default=0.75,
                              help="Intensity 0-1 (default: 0.75)")
    p_spiral_type.add_argument("--screen", type=int, default=0,
                              help="Screen index (default: 0)")
    p_spiral_type.add_argument("--raw-window", action="store_true",
                              help="Use QOpenGLWindow instead of QOpenGLWidget")

    # Test runner integration (wraps previous run_tests.py functionality)
    p_tr = add_subparser("test-run", help="Run pytest with selection shortcuts (replaces run_tests.py)")
    p_tr.add_argument("type", choices=["all","fast","slow","unit","integration","bluetooth"], nargs="?", default="all")
    p_tr.add_argument("-v","--verbose", action="store_true")
    p_tr.add_argument("-c","--coverage", action="store_true")

    # Session pack subcommand
    p_sess = add_subparser("session", help="Load and inspect/apply a session pack")
    p_sess.add_argument("--load", required=True, help="Path to session pack JSON file")
    g = p_sess.add_mutually_exclusive_group()
    g.add_argument("--print", action="store_true", help="Print canonical JSON and exit")
    g.add_argument("--apply", action="store_true", help="Apply pack to headless launcher and print status JSON")
    g.add_argument("--summary", action="store_true", help="Print concise summary (default)")

    # Runtime session state (save/load current UI configuration)
    p_state = add_subparser("state", help="Save or apply runtime UI/device/audio/text settings")
    act = p_state.add_mutually_exclusive_group(required=True)
    act.add_argument("--save", action="store_true", help="Capture current defaults (headless) and write to file")
    act.add_argument("--apply", action="store_true", help="Apply a saved state file (headless)")
    act.add_argument("--print", action="store_true", help="Print a saved state file as canonical JSON")
    p_state.add_argument("--file", required=True, help="Target state JSON file (input or output depending on action)")
    p_state.add_argument("--from-live", action="store_true", help="(Reserved) Capture from a running instance (not yet implemented)")

    p_cuelist = add_subparser("cuelist", help="Inspect, validate, or run cuelists headlessly")
    p_cuelist.add_argument("--load", required=True, help="Path to cuelist JSON file")
    g_cuelist = p_cuelist.add_mutually_exclusive_group()
    g_cuelist.add_argument("--validate", action="store_true", help="Validate structure and referenced media")
    g_cuelist.add_argument("--print", action="store_true", help="Print cuelist summary and exit")
    g_cuelist.add_argument("--execute", action="store_true", help="Execute cuelist headlessly (default)")
    p_cuelist.add_argument("--duration", type=float, default=None, help="Override execution duration in seconds")
    p_cuelist.add_argument("--json", action="store_true", help="Emit JSON output when printing or validating")
    p_cuelist.add_argument("--diag", action="store_true", help="Run headless diagnostics and print PerfTracer spans")
    p_cuelist.add_argument("--diag-cues", type=int, default=2, help="Number of cues to simulate during diagnostics (default: 2)")
    p_cuelist.add_argument("--diag-json", action="store_true", help="Emit raw JSON snapshot for diagnostics")
    p_cuelist.add_argument("--diag-threshold", type=float, default=250.0, help="Highlight spans at/above this duration in ms (default: 250)")
    p_cuelist.add_argument("--diag-limit", type=int, default=10, help="Maximum spans to list in diagnostics output (default: 10)")
    p_cuelist.add_argument("--diag-prefetch-only", action="store_true", help="Only measure prefetch timing (skip cue playback start)")
    p_cuelist.add_argument("--diag-fail", action="store_true", help="Return exit code 3 when any span exceeds the threshold")

    # Mode verification (diagnostics for VMC↔Launcher equivalence)
    p_mv = add_subparser("mode-verify", help="Validate a mode's derived timing and spiral RPM math headlessly")
    p_mv.add_argument("--mode", required=True, help="Path to mode JSON file")
    p_mv.add_argument("--frames", type=int, default=120, help="Frames to simulate (default: 120)")
    p_mv.add_argument("--fps", type=float, default=60.0, help="Frames per second (default: 60)")
    p_mv.add_argument("--tolerance", type=float, default=0.05, help="Allowed error (fraction, default: 0.05 = 5%)")
    p_mv.add_argument("--json", dest="json_out", action="store_true", help="Print JSON summary")

    # Spiral measurement (arm sweep timing)
    p_sm = add_subparser("spiral-measure", help="Measure time for an arm to sweep a given angle (director or Qt timer)")
    g_sm = p_sm.add_mutually_exclusive_group(required=False)
    g_sm.add_argument("--rpm", type=float, help="Spiral speed in RPM (negative = reverse)")
    g_sm.add_argument("--x", type=float, help="UI 'x' speed (mapped to RPM using VMC gain: RPM = x * 10)")
    # Multi-speed sweep options (provide any one of these to run multiple measurements)
    p_sm.add_argument("--rpm-list", type=str, help="Comma-separated RPM values, e.g. '60,90,120'")
    p_sm.add_argument("--x-list", type=str, help="Comma-separated x values, e.g. '10,13,20'")
    p_sm.add_argument("--rpm-range", type=str, help="RPM range as start:stop:step, e.g. '30:180:30'")
    p_sm.add_argument("--x-range", type=str, help="x range as start:stop:step, e.g. '5:20:2.5'")
    p_sm.add_argument("--delta-deg", type=float, default=90.0, help="Degrees to sweep (default: 90)")
    p_sm.add_argument("--mode", choices=["director","qt16","qt33"], default="director", help="Measurement mode: fixed 60 FPS or Qt timer (16ms/33ms)")
    p_sm.add_argument("--reverse", action="store_true", help="Reverse direction (negative RPM)")
    p_sm.add_argument("--ceil-frame", dest="ceil_frame", action="store_true", help="Predict minimal whole-frame time to reach target without running loop")
    # Comparison/table output between VMC (director) and Launcher (Qt)
    p_sm.add_argument("--compare", action="store_true", help="Compare VMC(director) vs Launcher(Qt) across an x range and print a table")
    p_sm.add_argument("--launcher-mode", choices=["qt16","qt33"], default="qt16", help="Launcher timing mode for comparison table (default: qt16)")
    p_sm.add_argument("--x-min", type=float, default=4.0, help="Comparison sweep: starting x (default: 4)")
    p_sm.add_argument("--x-max", type=float, default=40.0, help="Comparison sweep: ending x (default: 40)")
    p_sm.add_argument("--x-step", type=float, default=2.0, help="Comparison sweep: step (default: 2)")
    p_sm.add_argument("--clock", choices=["frame","wall"], help="Time basis: frame=ticks/60, wall=perf_counter (Qt). Default: frame for --compare, wall otherwise")
    p_sm.add_argument("--json", dest="json_out", action="store_true", help="Print JSON result")

    # Media cycle measurement (VMC vs baseline Qt timer)
    p_mm = add_subparser("media-measure", help="Measure media cycle intervals and compare VMC/Launcher vs Qt timer")
    p_mm.add_argument("--mode", choices=["timer","vmc","launcher","both","all"], default="both", help="Measurement mode: timer, vmc, launcher, both(timer+vmc) or all")
    p_mm.add_argument("--speeds", type=str, default=None, help="Comma-separated cycle speeds 1..100, e.g. '10,20,50,80,100'")
    p_mm.add_argument("--sweep", type=str, default=None, help="Speed sweep as start:end:step (inclusive), e.g. '10:100:10'")
    p_mm.add_argument("--cycles", type=int, default=20, help="Number of timer cycles to measure per speed (default: 20)")
    # Progress reporting (stderr) independent of quiet; suppressed by --json
    p_mm.add_argument("--progress", dest="progress", action="store_true", default=True, help="Show per-speed progress on stderr (default: on)")
    p_mm.add_argument("--no-progress", dest="progress", action="store_false", help="Disable progress lines (stderr)")
    # Adaptive cycles: target seconds per speed instead of fixed cycles
    p_mm.add_argument("--auto-seconds", type=float, default=None,
                      help="Target per-speed runtime in seconds; overrides --cycles adaptively (e.g., 5.0)")
    p_mm.add_argument("--min-cycles", type=int, default=1, help="Minimum cycles when using --auto-seconds (default: 1)")
    p_mm.add_argument("--max-cycles", type=int, default=20, help="Maximum cycles when using --auto-seconds (default: 20)")
    p_mm.add_argument("--include-videos", action="store_true", help="Include videos in VMC measurement (images only by default)")
    p_mm.add_argument("--json", action="store_true", help="Output JSON instead of a table")
    # Suppress stdout/stderr noise during VMC-internal measurement (e.g., GL/text printouts)
    p_mm.add_argument("--quiet", action="store_true", help="Suppress noisy prints during VMC measurement (implied by --json)")
    # Control per-speed runtime bounds for slow speeds (e.g., speed=10 has ~6.2s per cycle)
    p_mm.add_argument("--timeout-multiplier", type=float, default=2.5,
                      help="Scale factor for per-speed timeout: expected_ms * cycles * M + 2s (default: 2.5)")
    p_mm.add_argument("--max-seconds", type=float, default=None,
                      help="Absolute cap on per-speed runtime; if reached, returns partial samples (default: no cap)")
    # Optional CSV export
    p_mm.add_argument("--csv", type=str, default=None, help="Write results to CSV file path")

    # VR offscreen self-test (no Qt widgets) for ALVR/OpenXR
    p_vrs = add_subparser("vr-selftest", help="Run offscreen GL + OpenXR submit loop (no UI)")
    p_vrs.add_argument("--seconds", type=float, default=15.0, help="Duration in seconds (default: 15.0)")
    p_vrs.add_argument("--fps", type=float, default=60.0, help="Target frames per second (default: 60)")
    p_vrs.add_argument("--pattern", choices=["solid", "grid"], default="solid", help="Test pattern to render (default: solid)")
    p_vrs.add_argument("--size", type=str, default="1920x1080", help="Render size WxH (default: 1920x1080)")
    p_vrs.add_argument("--mock", action="store_true", help="Force VR mock mode (skip OpenXR)")
    
    # MesmerVisor VR streaming commands
    p_vr_stream = add_subparser("vr-stream", help="Stream live visuals to VR headset (MesmerVisor)")
    p_vr_stream.add_argument("--host", type=str, default="0.0.0.0", help="Server host address (default: 0.0.0.0)")
    p_vr_stream.add_argument("--port", type=int, default=5555, help="TCP streaming port (default: 5555)")
    p_vr_stream.add_argument("--discovery-port", type=int, default=5556, help="UDP discovery port (default: 5556)")
    p_vr_stream.add_argument("--encoder", choices=["auto", "nvenc", "jpeg"], default="auto",
                           help="Encoder: auto (detect), nvenc (H.264 GPU), jpeg (CPU fallback)")
    p_vr_stream.add_argument("--fps", type=int, default=30, help="Target FPS (default: 30)")
    p_vr_stream.add_argument("--quality", type=int, default=85, help="JPEG quality 1-100 (default: 85, ignored for NVENC)")
    p_vr_stream.add_argument("--bitrate", type=int, default=2000000, help="H.264 bitrate in bps (default: 2Mbps, ignored for JPEG)")
    p_vr_stream.add_argument("--stereo-offset", type=int, default=0, help="Stereo parallax offset in pixels (0=mono)")
    p_vr_stream.add_argument("--enable-text", action="store_true", help="Include text overlays in stream")
    p_vr_stream.add_argument("--enable-images", action="store_true", help="Include image overlays in stream")
    p_vr_stream.add_argument("--intensity", type=float, default=0.75, help="Initial spiral intensity 0-1 (default: 0.75)")
    p_vr_stream.add_argument("--duration", type=float, default=0, help="Stream duration in seconds (0=infinite)")
    
    p_vr_test = add_subparser("vr-test", help="Test VR streaming with generated pattern (no full app)")
    p_vr_test.add_argument("--pattern", choices=["checkerboard", "gradient", "noise", "spiral"], default="checkerboard",
                          help="Test pattern type (default: checkerboard)")
    p_vr_test.add_argument("--host", type=str, default="0.0.0.0", help="Server host address")
    p_vr_test.add_argument("--port", type=int, default=5555, help="TCP streaming port")
    p_vr_test.add_argument("--discovery-port", type=int, default=5556, help="UDP discovery port")
    p_vr_test.add_argument("--encoder", choices=["auto", "nvenc", "jpeg"], default="auto", help="Encoder type")
    p_vr_test.add_argument("--fps", type=int, default=30, help="Target FPS")
    p_vr_test.add_argument("--width", type=int, default=1920, help="Frame width (default: 1920)")
    p_vr_test.add_argument("--height", type=int, default=1080, help="Frame height (default: 1080)")
    p_vr_test.add_argument("--quality", type=int, default=85, help="JPEG quality (default: 85)")
    p_vr_test.add_argument("--duration", type=int, default=0, help="Duration in seconds (0=infinite)")


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
            # Schedule detailed GL state dump once context is current
            from PyQt6.QtCore import QTimer
            def _print_gl_state():
                try:
                    from OpenGL import GL
                    # Apply known-good defaults for artifact-free rendering
                    try: GL.glDisable(GL.GL_DITHER)
                    except Exception: pass
                    try: GL.glDisable(0x809E)  # GL_SAMPLE_ALPHA_TO_COVERAGE
                    except Exception: pass
                    try: GL.glDisable(GL.GL_POLYGON_SMOOTH)
                    except Exception: pass
                    try: GL.glEnable(GL.GL_BLEND)
                    except Exception: pass
                    try: GL.glEnable(GL.GL_MULTISAMPLE)
                    except Exception: pass
                    try: GL.glDisable(GL.GL_DEPTH_TEST)
                    except Exception: pass

                    def _enabled(cap):
                        try:
                            return 1 if GL.glIsEnabled(cap) else 0
                        except Exception:
                            return -1

                    # Print core states expected by tests
                    print(f"GL_DITHER: {_enabled(GL.GL_DITHER)}")
                    print(f"GL_SAMPLE_ALPHA_TO_COVERAGE: {_enabled(0x809E)}")
                    print(f"GL_POLYGON_SMOOTH: {_enabled(GL.GL_POLYGON_SMOOTH)}")
                    print(f"GL_BLEND: {_enabled(GL.GL_BLEND)}")
                    print(f"GL_MULTISAMPLE: {_enabled(GL.GL_MULTISAMPLE)}")
                    print(f"GL_DEPTH_TEST: {_enabled(GL.GL_DEPTH_TEST)}")

                    # Blend function (alpha-specific)
                    try:
                        src = GL.glGetIntegerv(GL.GL_BLEND_SRC_ALPHA)
                        dst = GL.glGetIntegerv(GL.GL_BLEND_DST_ALPHA)
                        print(f"Blend func: src={src} dst={dst}")
                    except Exception:
                        pass

                    # Viewport dimensions
                    try:
                        vp = GL.glGetIntegerv(GL.GL_VIEWPORT)
                        if hasattr(vp, 'tolist'):
                            vp = vp.tolist()
                        print(f"Viewport: {tuple(vp) if isinstance(vp, (list, tuple)) else vp}")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Could not query GL state: {e}")
            QTimer.singleShot(150, _print_gl_state)
        
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
        # Optional: background video playback
        cap = None
        try:
            vid_arg = getattr(args, 'video', 'none')
            if vid_arg and str(vid_arg).lower() != 'none':
                import cv2
                from pathlib import Path as _P
                p = _P(vid_arg)
                if not p.exists():
                    # Try relative to project root MEDIA/Videos
                    p2 = _P.cwd() / 'MEDIA' / 'Videos' / vid_arg
                    if p2.exists():
                        p = p2
                cap = cv2.VideoCapture(str(p))
                if not cap.isOpened():
                    print(f"spiral-test: warning: could not open video '{vid_arg}'")
                    cap = None
        except Exception as _e:
            print(f"spiral-test: warning: video init failed: {_e}")
        target_frame = 1.0 / 60.0
        while True:
            now = _time.perf_counter(); elapsed = now - t0
            if elapsed >= dur:
                break
            dt = now - last; last = now
            # The compositor automatically handles director updates and uniform setting in paintGL
            app.processEvents()
            # Upload next video frame if available
            if cap is not None:
                try:
                    ret, frame_bgr = cap.read()
                    if not ret:
                        # loop video
                        cap.set(1, 0)  # CAP_PROP_POS_FRAMES
                        ret, frame_bgr = cap.read()
                    if ret:
                        # Convert to RGB
                        import cv2
                        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                        h, w = frame_rgb.shape[:2]
                        # Ensure GL context current before texture upload
                        try:
                            comp.makeCurrent()
                        except Exception:
                            pass
                        # Use current zoom (if any)
                        current_zoom = getattr(comp, '_background_zoom', 1.0)
                        comp.set_background_video_frame(frame_rgb, width=w, height=h, zoom=current_zoom)
                except Exception:
                    pass
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
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            comp.close()
        except Exception:
            pass
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        print("MesmerLoom spiral-test: error:", e)
        sys.exit(1)

def cmd_spiral_type(args) -> None:
    """Test specific Trance spiral type with rotation formula verification.
    
    Exit codes:
      0 success
      77 OpenGL unavailable
      1 error
    """
    import sys, time as _time
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    
    print(f"Trance Spiral Type Test")
    print(f"  Type: {args.type} ({['log','quad','linear','sqrt','inverse','power','modulated'][args.type-1]})")
    print(f"  Width: {args.width}° ({360//args.width} arms)")
    print(f"  Rotation: {args.rotation} amount/frame")
    print(f"  Duration: {args.duration}s")
    print(f"  Intensity: {args.intensity}")
    print("-" * 60)
    
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Import GL components
    try:
        if args.raw_window:
            from .mesmerloom.simple_gl_spiral import SimpleGLSpiralWindow
            window_cls = SimpleGLSpiralWindow
        else:
            from .mesmerloom.compositor import LoomCompositor
            window_cls = LoomCompositor
    except ImportError as e:
        print(f"spiral-type: GL unavailable: {e}")
        sys.exit(77)
    
    # Get target screen
    screens = app.screens()
    if args.screen >= len(screens):
        print(f"spiral-type: screen {args.screen} not found (have {len(screens)})")
        sys.exit(1)
    screen = screens[args.screen]
    
    # Create window with spiral director
    from .mesmerloom.spiral import SpiralDirector
    director = SpiralDirector()
    director.set_intensity(args.intensity)
    director.set_spiral_type(args.type)
    director.set_spiral_width(args.width)
    
    if args.raw_window:
        window = window_cls()
        window.set_director(director)
    else:
        # CRITICAL FIX: Use QMainWindow to properly host the QOpenGLWidget
        # This fixes the black screen issue in fullscreen mode
        from PyQt6.QtWidgets import QMainWindow
        compositor = window_cls(director)
        compositor.set_active(True)
        
        window = QMainWindow()
        window.setCentralWidget(compositor)
        # Position on target screen
        geom = screen.geometry()
        window.setGeometry(geom)
        # Ensure window is visible
        window.setWindowOpacity(1.0)
        window.showFullScreen()
    
    if args.raw_window:
        # Position on target screen
        geom = screen.geometry()
        window.setGeometry(geom)
        # Ensure window is visible
        window.setWindowOpacity(1.0)
        window.showFullScreen()
    
    # Rotation timer
    start_time = _time.time()
    frame_count = [0]
    
    def on_tick():
        director.rotate_spiral(args.rotation)
        director.update()
        frame_count[0] += 1
        
        elapsed = _time.time() - start_time
        if elapsed >= args.duration:
            elapsed_final = _time.time() - start_time
            fps = frame_count[0] / elapsed_final if elapsed_final > 0 else 0
            
            # Calculate expected rotation from Trance formula
            import math
            rotations_per_frame = args.rotation / (32 * math.sqrt(args.width))
            total_rotations = rotations_per_frame * frame_count[0]
            
            print(f"\nTest Results:")
            print(f"  Frames: {frame_count[0]}")
            print(f"  Duration: {elapsed_final:.2f}s")
            print(f"  FPS: {fps:.1f}")
            print(f"  Rotation formula: {args.rotation} / (32 * sqrt({args.width})) = {rotations_per_frame:.6f} per frame")
            print(f"  Total rotations: {total_rotations:.3f}")
            print(f"  Final phase: {director.state.phase:.6f}")
            app.quit()
    
    timer = QTimer()
    timer.timeout.connect(on_tick)
    timer.start(16)  # ~60fps
    
    sys.exit(app.exec())


def _run_theme_perf_diag(args, collection, *, theme_path) -> int:
    import json as _json
    import sys as _sys
    import time as _time
    from pathlib import Path as _Path

    from mesmerglass.content.themebank import ThemeBank

    enabled = collection.get_enabled_themes()
    if not enabled:
        print("Error: No enabled themes available for diagnostics", file=_sys.stderr)
        return 1

    tracer = PerfTracer(label="theme-cli", enabled=True)
    lookups = max(1, int(getattr(args, "diag_lookups", 24) or 24))
    prefetch_only = bool(getattr(args, "diag_prefetch_only", False))
    cache_size = max(8, int(getattr(args, "diag_cache_size", 128) or 128))
    tracer.set_context(
        theme_file=str(theme_path),
        enabled_themes=len(enabled),
        cache_size=cache_size,
        lookups=lookups,
        prefetch_only=prefetch_only,
    )

    bank: ThemeBank | None = None
    try:
        bank = ThemeBank(
            themes=enabled,
            root_path=_Path(theme_path).parent,
            image_cache_size=cache_size,
            perf_tracer=tracer,
        )
        alt_index = 2 if len(enabled) > 1 else None
        bank.set_active_themes(primary_index=1, alt_index=alt_index)

        iterations = lookups
        for idx in range(iterations):
            if not prefetch_only:
                alternate = bool(alt_index and (idx % 2 == 1))
                bank.get_image(alternate=alternate)
            bank.async_update()
            _time.sleep(0.01)

        snapshot = bank.get_perf_snapshot(reset=False) or {}
    finally:
        if bank is not None:
            bank.shutdown()

    threshold = max(0.0, float(getattr(args, "diag_threshold", 0.0) or 0.0))
    limit = max(1, int(getattr(args, "diag_limit", 10) or 10))

    if getattr(args, "diag_json", False):
        print(_json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        spans = snapshot.get("span_count") or len(snapshot.get("spans", []))
        print(
            f"[theme-diag] spans={spans} lookups={lookups} threshold={threshold:.1f}ms alt={'yes' if len(enabled) > 1 else 'no'} prefetch_only={prefetch_only}"
        )
        categories = snapshot.get("categories") or {}
        if categories:
            print("[theme-diag] Category totals (ms):")
            for name, total in sorted(categories.items(), key=lambda item: item[1], reverse=True):
                print(f"  - {name}: {total:.1f}")
        table_lines, _ = _render_diag_table(snapshot, limit=limit, threshold_ms=threshold)
        if table_lines:
            for line in table_lines:
                print(line)
        else:
            print("[theme-diag] No spans matched the threshold")

    spans = snapshot.get("spans", [])
    offending_total = sum(1 for span in spans if span.get("duration_ms", 0.0) >= threshold)
    if getattr(args, "diag_fail", False) and offending_total > 0:
        return 3
    return 0

def cmd_theme(args) -> int:
    """Theme and media loading test/diagnostic command.

    Exit codes:
        0 success
        1 error / invalid input
        3 perf threshold exceeded (when --diag-fail is set)
    """
    import json
    from pathlib import Path
    from mesmerglass.content.theme import load_theme_collection, ThemeCollection, Shuffler

    if args.diag and not args.load:
        print("Error: --diag requires --load", file=sys.stderr)
        return 1
    
    if args.load:
        path = Path(args.load)
        if not path.exists():
            print(f"Error: Theme file not found: {path}", file=sys.stderr)
            return 1
        
        try:
            collection = load_theme_collection(path)
        except Exception as e:
            print(f"Error loading theme: {e}", file=sys.stderr)
            return 1

        if args.diag:
            return _run_theme_perf_diag(args, collection, theme_path=path)
        
        if args.list:
            print(f"\nThemes in collection ({len(collection.themes)} total):")
            for i, theme in enumerate(collection.themes):
                status = "ENABLED" if theme.enabled else "DISABLED"
                print(f"  [{i}] {theme.name} ({status})")
                print(f"      Images: {len(theme.image_path)}")
                print(f"      Text lines: {len(theme.text_line)}")
                if theme.animation_path:
                    print(f"      Animations: {len(theme.animation_path)}")
                if theme.font_path:
                    print(f"      Fonts: {len(theme.font_path)}")
            return 0
        
        if args.show_config:
            data = collection.to_dict()
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0
        
        if args.test_shuffler is not None:
            enabled = collection.get_enabled_themes()
            if not enabled:
                print("Error: No enabled themes found", file=sys.stderr)
                return 1
            
            # Test first enabled theme's shuffler
            theme = enabled[0]
            if not theme.image_path:
                print(f"Error: Theme '{theme.name}' has no images", file=sys.stderr)
                return 1
            
            shuffler = Shuffler(count=len(theme.image_path))
            print(f"\nTesting Shuffler with {len(theme.image_path)} images:")
            print(f"  Running {args.test_shuffler} selections...")
            
            counts = [0] * len(theme.image_path)
            for _ in range(args.test_shuffler):
                idx = shuffler.next()
                counts[idx] += 1
                # Simulate decrease/increase (last-8 tracking)
                shuffler.decrease(idx)
            
            print("\n  Selection counts:")
            for i, count in enumerate(counts):
                pct = (count / args.test_shuffler * 100) if args.test_shuffler > 0 else 0
                print(f"    Image {i}: {count} ({pct:.1f}%)")
            
            return 0
        
        # Default: show summary
        print(f"\nTheme Collection loaded successfully:")
        print(f"  Total themes: {len(collection.themes)}")
        enabled = collection.get_enabled_themes()
        print(f"  Enabled themes: {len(enabled)}")
        if enabled:
            print(f"\n  First enabled theme: {enabled[0].name}")
            print(f"    Images: {len(enabled[0].image_path)}")
            print(f"    Text lines: {len(enabled[0].text_line)}")
        return 0
    
    if args.test_cache:
        # Create a minimal test of the image cache
        print("\nTesting image cache (requires sample images)...")
        print("  (Full implementation requires actual image files)")
        from mesmerglass.content.media import ImageCache
        cache = ImageCache(cache_size=8)
        print(f"  Cache created with size: {cache._cache_size}")
        print(f"  Cache is ready")
        return 0
    
    # No action specified
    print("Error: Must specify --load or --test-cache", file=sys.stderr)
    return 1

def cmd_mode_verify(args) -> int:
    """Headless verification of mode timing and RPM rotation.

    Exit codes:
      0 success (within tolerance)
      2 validation failure (outside tolerance or file error)
      1 unexpected error
    """
    import json as _json
    from pathlib import Path as _Path
    from .mesmerloom.spiral import SpiralDirector
    from .mesmerloom.spiral_speed import SpiralSpeedCalculator as _Speed

    try:
        mp = _Path(args.mode)
        if not mp.exists():
            print(f"Error: mode not found: {mp}")
            return 2
        cfg = _json.loads(mp.read_text(encoding="utf-8"))
        spiral = cfg.get("spiral", {})
        media = cfg.get("media", {})
        rpm = float(spiral.get("rotation_speed", 4.0))
        reverse = bool(spiral.get("reverse", False))
        # Compute expected media frames/cycle using the same formula as CustomVisual
        speed = int(media.get("cycle_speed", 50))
        speed = max(1, min(100, speed))
        import math as _m
        interval_ms = 10000 * _m.pow(0.005, (speed - 1) / 99.0)
        frames_per_cycle = max(1, round((interval_ms / 1000.0) * float(args.fps)))
        # Simulate phase
        d = SpiralDirector(seed=7)
        d.set_rotation_speed(-abs(rpm) if reverse else abs(rpm))
        frames = max(1, int(args.frames))
        dt = 1.0 / float(args.fps)
        start = d.state.phase
        for _ in range(frames):
            # update() already advances rotation using the provided dt, so avoid
            # double-stepping the phase accumulator which skewed RPM math.
            d.update(dt)
        end = d.state.phase
        delta = (end - start) % 1.0
        # Use minor arc to get magnitude independent of direction
        if delta > 0.5:
            delta = 1.0 - delta
        measured_phase_per_sec = delta / (frames * dt)
        expected_phase_per_sec = _Speed.rpm_to_phase_per_second(abs(rpm))
        # Evaluate tolerance
        err = 0.0 if expected_phase_per_sec == 0 else abs(measured_phase_per_sec - expected_phase_per_sec) / expected_phase_per_sec
        ok = err <= float(args.tolerance)
        result = {
            "mode": mp.name,
            "rpm": rpm,
            "reverse": reverse,
            "fps": float(args.fps),
            "frames": frames,
            "measured_phase_per_sec": round(measured_phase_per_sec, 6),
            "expected_phase_per_sec": round(expected_phase_per_sec, 6),
            "error_pct": round(err * 100.0, 2),
            "frames_per_cycle": frames_per_cycle,
        }
        if getattr(args, "json_out", False):
            import json
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(
                f"Mode {result['mode']}: RPM={result['rpm']} reverse={result['reverse']} | "
                f"phase/s measured={result['measured_phase_per_sec']:.4f} expected={result['expected_phase_per_sec']:.4f} "
                f"err={result['error_pct']:.2f}% | frames/cycle={frames_per_cycle}"
            )
        return 0 if ok else 2
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: mode-verify failed: {e}")
        return 1


def cmd_cuelist(args) -> int:
    """Inspect, validate, or execute cuelist files without launching the UI."""
    import json as _json
    from pathlib import Path as _Path
    import time as _time

    from .session.cuelist import Cuelist

    log = logging.getLogger(__name__)
    cuelist_path = _Path(args.load)

    if not cuelist_path.exists():
        print(f"Error: cuelist file not found: {cuelist_path}")
        return 1

    try:
        cuelist = Cuelist.load(cuelist_path)
    except Exception as exc:
        log.error("Failed to load cuelist %s: %s", cuelist_path, exc)
        print(f"Error: failed to load cuelist: {exc}")
        return 1

    mode = "execute"
    if getattr(args, "validate", False):
        mode = "validate"
    elif getattr(args, "print", False):
        mode = "print"
    elif getattr(args, "execute", False):
        mode = "execute"

    base_dir = cuelist_path.parent

    if getattr(args, "diag", False):
        if mode != "execute":
            print("Error: --diag can only be used when executing the cuelist")
            return 1
        diag_result = _run_cuelist_diag(
            cuelist,
            cue_limit=getattr(args, "diag_cues", 2),
            prefetch_only=getattr(args, "diag_prefetch_only", False),
        )
        error = diag_result.get("error")
        if error:
            print(f"Error: {error}")
            snapshot = diag_result.get("snapshot")
            if getattr(args, "diag_json", False) and snapshot:
                print(_json.dumps(snapshot, ensure_ascii=False, indent=2))
            return diag_result.get("code", 1)
        snapshot = diag_result.get("snapshot")
        limit = max(1, int(getattr(args, "diag_limit", 10) or 10))
        threshold = max(0.0, float(getattr(args, "diag_threshold", 0.0) or 0.0))
        table_lines, offending = _render_diag_table(snapshot, limit=limit, threshold_ms=threshold)
        if getattr(args, "diag_json", False):
            print(_json.dumps(snapshot or {}, ensure_ascii=False, indent=2))
        else:
            executed = diag_result.get("executed", 0)
            print(f"[diag] Simulated {executed} cue(s); threshold={threshold:.1f} ms")
            context = (snapshot or {}).get("context") if snapshot else None
            if context:
                print(f"[diag] Context: {context}")
            if table_lines:
                for line in table_lines:
                    print(line)
            else:
                print("[diag] No spans met the threshold")
            categories = (snapshot or {}).get("categories") if snapshot else None
            if isinstance(categories, dict) and categories:
                print("[diag] Category totals (ms):")
                for name, total in sorted(categories.items(), key=lambda item: item[1], reverse=True):
                    print(f"  - {name}: {total:.1f}")
        if getattr(args, "diag_fail", False) and offending > 0:
            return 3
        return 0

    if mode == "validate":
        errors: list[str] = []
        warnings: list[str] = []
        is_valid, msg = cuelist.validate()
        if not is_valid:
            errors.append(msg)

        for idx, cue in enumerate(cuelist.cues):
            for entry in cue.playback_pool:
                pb_path = entry.playback_path
                if not pb_path.is_absolute():
                    pb_path = (base_dir / pb_path).resolve()
                if not pb_path.exists():
                    errors.append(
                        f"Cue {idx + 1} '{cue.name}': playback file not found: {entry.playback_path}"
                    )
            for track in cue.audio_tracks:
                tr_path = track.file_path
                if not tr_path.is_absolute():
                    tr_path = (base_dir / tr_path).resolve()
                if not tr_path.exists():
                    errors.append(
                        f"Cue {idx + 1} '{cue.name}': audio file not found: {track.file_path}"
                    )

            audio_layers = cue.get_audio_layers()
            if cue.audio_tracks:
                if AudioRole.HYPNO not in audio_layers:
                    errors.append(
                        f"Cue {idx + 1} '{cue.name}': hypno track missing role assignment"
                    )
                if AudioRole.BACKGROUND not in audio_layers:
                    warnings.append(
                        f"Cue {idx + 1} '{cue.name}': background track not configured"
                    )
                else:
                    background_track = audio_layers[AudioRole.BACKGROUND]
                    if not background_track.loop:
                        warnings.append(
                            f"Cue {idx + 1} '{cue.name}': background track does not loop"
                        )

        summary = {
            "valid": len(errors) == 0,
            "cuelist": {"name": cuelist.name, "cues": len(cuelist.cues)},
            "errors": errors,
            "warnings": warnings,
        }

        if getattr(args, "json", False):
            print(_json.dumps(summary, ensure_ascii=False))
        else:
            status = "PASSED" if summary["valid"] else "FAILED"
            print(f"Validation: {status}")
            if errors:
                print(f"[FAIL] Found {len(errors)} error(s):")
                for err in errors:
                    print(f"  - {err}")
            if warnings:
                print(f"[WARN] Found {len(warnings)} warning(s):")
                for warn in warnings:
                    print(f"  - {warn}")
        return 0 if summary["valid"] else 1

    if mode == "print":
        if getattr(args, "json", False):
            print(_json.dumps(cuelist.to_dict(), ensure_ascii=False, indent=2))
            return 0

        total_duration = cuelist.total_duration()
        print(f"Cuelist: {cuelist.name}")
        print(f"Version: {cuelist.version}")
        print(f"Author: {cuelist.author or 'Unknown'}")
        print(f"Loop Mode: {cuelist.loop_mode.value}")
        if cuelist.description:
            print(f"Description: {cuelist.description}")
        print(f"Cues: {len(cuelist.cues)}  Total Duration: {total_duration:.1f}s")
        print()
        for idx, cue in enumerate(cuelist.cues, start=1):
            print(f"  [{idx}] {cue.name} ({cue.duration_seconds:.1f}s)")
            print(f"      Playbacks: {len(cue.playback_pool)} | Audio Tracks: {len(cue.audio_tracks)}")
            hyp = "yes" if cue.get_audio_track(AudioRole.HYPNO) else "no"
            bg = "yes" if cue.get_audio_track(AudioRole.BACKGROUND) else "no"
            print(f"      Audio Roles -> hypno: {hyp}, background: {bg}")
        return 0

    # Default: execute headlessly
    duration_override = getattr(args, "duration", None)
    if duration_override is not None and duration_override <= 0:
        print("Error: --duration must be positive when provided")
        return 1

    target_duration = duration_override if duration_override is not None else cuelist.total_duration()
    if target_duration <= 0:
        print("Error: cuelist has no duration to execute")
        return 1

    remaining = target_duration
    print(f"[INFO] Starting cuelist session: {cuelist.name}")
    print(f"[INFO] Total cues: {len(cuelist.cues)}")
    print(f"[INFO] Session duration: {target_duration:.1f}s")
    print()

    start_ts = _time.perf_counter()
    for idx, cue in enumerate(cuelist.cues, start=1):
        if remaining <= 0:
            break
        slice_duration = min(cue.duration_seconds, remaining)
        print(f"[TIME] Cue {idx}/{len(cuelist.cues)}: {cue.name} ({slice_duration:.1f}s)")
        _time.sleep(min(0.5, slice_duration))
        remaining -= slice_duration

    elapsed = _time.perf_counter() - start_ts
    print()
    print(f"[OK] Session completed in {elapsed:.1f}s")
    return 0


class _DiagTextDirector:
    def reset(self) -> None:
        return None

    def set_secondary_compositors(self, *_args, **_kwargs) -> None:
        return None


class _DiagVisualDirector:
    def __init__(self) -> None:
        self.text_director = _DiagTextDirector()
        self._cycle_callbacks: list[Callable[[], None]] = []
        self._cycle_count = 0

    def register_cycle_callback(self, callback: Callable[[], None]) -> None:
        if callback not in self._cycle_callbacks:
            self._cycle_callbacks.append(callback)

    def unregister_cycle_callback(self, callback: Callable[[], None]) -> None:
        if callback in self._cycle_callbacks:
            self._cycle_callbacks.remove(callback)

    def register_secondary_compositor(self, *_args, **_kwargs) -> None:
        return None

    def unregister_secondary_compositor(self, *_args, **_kwargs) -> None:
        return None

    def get_cycle_count(self) -> int:
        return self._cycle_count

    def load_playback(self, _playback_path) -> bool:
        # Pretend load succeeded instantly
        return True

    def start_playback(self) -> None:
        # Advance cycle count and fire callbacks to emulate boundary events
        self._cycle_count += 1
        for callback in list(self._cycle_callbacks):
            try:
                callback()
            except Exception:
                continue

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def update(self, *_args, **_kwargs) -> None:
        return None


def _run_cuelist_diag(
    cuelist,
    *,
    cue_limit: int,
    prefetch_only: bool,
) -> dict[str, object]:
    import time as _time
    from .session.runner import SessionRunner, SessionState
    from .engine.audio import AudioEngine
    from .logging_utils import LogMode, get_log_mode, set_log_mode

    if not cuelist.cues:
        return {"error": "Cuelist has no cues to diagnose", "code": 1}

    if get_log_mode() is not LogMode.PERF:
        set_log_mode(LogMode.PERF)

    audio_engine = AudioEngine(num_channels=2)
    if not getattr(audio_engine, "init_ok", True):
        return {"error": "AudioEngine failed to initialize (pygame mixer unavailable)", "code": 2}

    visual_director = _DiagVisualDirector()
    runner = SessionRunner(
        cuelist=cuelist,
        visual_director=visual_director,
        audio_engine=audio_engine,
        session_data=None,
    )
    runner._state = SessionState.RUNNING  # type: ignore[attr-defined]
    runner._session_start_time = _time.time()

    cue_total = min(max(1, int(cue_limit or 1)), len(cuelist.cues))
    executed = 0
    error: Optional[str] = None
    try:
        for cue_index in range(cue_total):
            runner._prefetch_cue_audio(cue_index, force=True)  # type: ignore[attr-defined]
            runner._await_cue_audio_ready(cue_index)  # type: ignore[attr-defined]
            if prefetch_only:
                executed += 1
                continue
            if not runner._start_cue(cue_index):  # type: ignore[attr-defined]
                error = f"Failed to start cue {cue_index}"
                break
            runner._end_cue()  # type: ignore[attr-defined]
            executed += 1
    finally:
        runner._current_cue_index = -1  # type: ignore[attr-defined]
        if runner._prefetch_worker:  # type: ignore[attr-defined]
            runner._prefetch_worker.shutdown(wait=True)  # type: ignore[attr-defined]
        runner.stop()

    snapshot = runner.get_perf_snapshot(reset=True)
    if error:
        return {"error": error, "code": 1, "snapshot": snapshot, "executed": executed}
    return {"snapshot": snapshot, "executed": executed}


def _render_diag_table(snapshot: Optional[dict[str, object]], *, limit: int, threshold_ms: float) -> tuple[list[str], int]:
    import json as _json_diag

    if not snapshot:
        return [], 0
    spans = snapshot.get("spans") or []
    if not isinstance(spans, list):
        return [], 0
    filtered = [s for s in spans if isinstance(s, dict) and s.get("duration_ms", 0.0) >= threshold_ms]
    filtered.sort(key=lambda item: item.get("duration_ms", 0.0), reverse=True)
    if limit > 0:
        filtered = filtered[:limit]
    if not filtered:
        return [], 0
    width = max(4, max(len(str(s.get("name", ""))) for s in filtered))
    header = f"{'Span':<{width}} | Category   | Duration (ms) | Metadata"
    lines = [header, "-" * len(header)]
    for row in filtered:
        meta_json = _json_diag.dumps(row.get("metadata", {}), ensure_ascii=False)
        lines.append(
            f"{row.get('name', ''):<{width}} | {row.get('category', ''):<10} | {row.get('duration_ms', 0.0):>12.2f} | {meta_json}"
        )
    return lines, len(filtered)

# --- Spiral arm sweep measurement helpers ---
VMC_SPEED_GAIN = 10.0  # Keep in sync with scripts/visual_mode_creator.py

def predict_spiral_frames(rpm: float, delta_deg: float, fps: float = 60.0) -> tuple[int, float] | tuple[None, None]:
    """Predict minimal whole-frame count to reach delta_deg sweep at given RPM.

    Returns (frames, seconds). For zero RPM, returns (None, None).
    """
    import math as _math
    rpm_abs = abs(float(rpm))
    if rpm_abs == 0.0:
        return None, None
    target_phase = max(0.0, float(delta_deg)) / 360.0
    phase_per_frame = (rpm_abs / 60.0) / float(fps)
    # Tiny epsilon to stabilize ceil for near-exact divisions
    n_frames = int(_math.ceil((target_phase / phase_per_frame) - 1e-12))
    return n_frames, n_frames / float(fps)

def _parse_float_list(s: str | None) -> list[float]:
    if not s:
        return []
    vals = []
    for part in s.split(','):
        p = part.strip()
        if not p:
            continue
        vals.append(float(p))
    return vals

def _parse_range(s: str | None) -> list[float]:
    if not s:
        return []
    try:
        start_s, stop_s, step_s = s.split(':')
        start = float(start_s); stop = float(stop_s); step = float(step_s)
    except Exception:
        raise SystemExit("Error: range must be in the form start:stop:step")
    if step == 0:
        raise SystemExit("Error: step cannot be zero")
    vals: list[float] = []
    cur = start
    # Include stop if exactly hits within epsilon
    eps = 1e-12
    if step > 0:
        while cur <= stop + eps:
            vals.append(cur)
            cur += step
    else:
        while cur >= stop - eps:
            vals.append(cur)
            cur += step
    return vals

def sweep_spiral_measure(
    speeds: list[float], *, use_x: bool, delta_deg: float, mode: str, reverse: bool, ceil_frame: bool, clock: str = "wall"
) -> list[dict]:
    """Run spiral-measure over a list of speeds (x or rpm) and return summaries."""
    results: list[dict] = []
    for v in speeds:
        rpm = float(v) * VMC_SPEED_GAIN if use_x else float(v)
        # Predictive calculation
        pred_frames, pred_seconds = predict_spiral_frames(rpm, delta_deg, fps=60.0)
        pred_ticks = pred_frames if pred_frames is not None else None
        pred_seconds_timer = None
        if mode == 'director':
            sec, frames, ach = measure_spiral_time_director(rpm, delta_deg, reverse, fps=60.0)
            ticks = frames
            # Director seconds are already frame-based
            sec_report = sec
        else:
            interval = 16 if mode == 'qt16' else 33
            if pred_ticks is not None:
                pred_seconds_timer = round(pred_ticks * (interval / 1000.0), 6)
            sec, ticks, ach = measure_spiral_time_qt(rpm, delta_deg, interval, reverse)
            # Choose reporting basis
            if clock == "frame":
                sec_report = ticks / 60.0
            else:
                sec_report = sec
        expected = (delta_deg / max(1e-9, (abs(rpm) * 6.0))) if abs(rpm) > 0 else float('inf')
        err = 0.0 if expected == float('inf') else abs(sec_report - expected) / expected
        out = {
            "rpm": rpm,
            "x": (rpm / VMC_SPEED_GAIN),
            "reverse": reverse,
            "mode": mode,
            "delta_deg": float(delta_deg),
            "measured_seconds": round(sec_report if mode.startswith('qt') else sec, 6),
            "expected_seconds": round(expected, 6) if expected != float('inf') else None,
            "error_pct": round(err * 100.0, 2) if expected != float('inf') else None,
            "ticks": ticks,
            "achieved_phase": round(ach, 6),
        }
        if ceil_frame:
            out.update({
                "predicted_frames": pred_frames,
                "predicted_seconds": round(pred_seconds, 6) if pred_seconds is not None else None,
                "predicted_ticks": pred_ticks,
                "predicted_seconds_timer": pred_seconds_timer,
            })
        results.append(out)
    return results

def compare_vmc_launcher(
    x_values: list[float], *, delta_deg: float, launcher_mode: str = "qt16", ceil_frame: bool = True, clock: str = "frame"
) -> list[dict]:
    """Compare measured/predicted sweep times between VMC (director) and Launcher (qt16/qt33) for x values.

    Returns list of dict rows with keys: x, rpm, vmc_measured, vmc_predicted, launcher_measured, launcher_predicted, diff_ms, diff_pct, vmc_ticks, launcher_ticks.
    """
    rows: list[dict] = []
    for x in x_values:
        rpm = float(x) * VMC_SPEED_GAIN
        # VMC (director)
        vmc_results = sweep_spiral_measure([x], use_x=True, delta_deg=delta_deg, mode='director', reverse=False, ceil_frame=ceil_frame, clock=clock)
        vmc = vmc_results[0]
        # Launcher (qt)
        launch_results = sweep_spiral_measure([x], use_x=True, delta_deg=delta_deg, mode=launcher_mode, reverse=False, ceil_frame=ceil_frame, clock=clock)
        ln = launch_results[0]
        vmc_meas = vmc.get("measured_seconds")
        ln_meas = ln.get("measured_seconds")
        vmc_pred = vmc.get("predicted_seconds")
        ln_pred = ln.get("predicted_seconds_timer") if launcher_mode.startswith('qt') else ln.get("predicted_seconds")
        diff_ms = (ln_meas - vmc_meas) * 1000.0
        diff_pct = None
        if vmc_meas and vmc_meas > 0:
            diff_pct = (ln_meas / vmc_meas - 1.0) * 100.0
        rows.append({
            "x": float(x),
            "rpm": rpm,
            "delta_deg": float(delta_deg),
            "vmc_measured": round(vmc_meas, 6),
            "vmc_predicted": vmc_pred,
            "launcher_measured": round(ln_meas, 6),
            "launcher_predicted": ln_pred,
            "diff_ms": round(diff_ms, 3),
            "diff_pct": round(diff_pct, 2) if diff_pct is not None else None,
            "vmc_ticks": vmc.get("ticks"),
            "launcher_ticks": ln.get("ticks"),
        })
    return rows

def _print_compare_table(rows: list[dict], launcher_mode: str):
    # Build a simple fixed-width table
    headers = ["x", "rpm", "vmc(s)", f"launcher[{launcher_mode}](s)", "+ms", "+%", "ticks(v/l)"]
    # Determine column widths
    data_rows = []
    for r in rows:
        data_rows.append([
            f"{r['x']:.2f}",
            f"{int(r['rpm']):d}",
            f"{r['vmc_measured']:.6f}",
            f"{r['launcher_measured']:.6f}",
            f"{r['diff_ms']:.1f}",
            f"{r['diff_pct']:.2f}" if r.get('diff_pct') is not None else "-",
            f"{r['vmc_ticks']}/{r['launcher_ticks']}",
        ])
    col_w = [max(len(h), *(len(dr[i]) for dr in data_rows)) for i, h in enumerate(headers)]
    def fmt_row(cols):
        return " ".join(c.rjust(col_w[i]) for i, c in enumerate(cols))
    print(fmt_row(headers))
    print(" ".join("-" * w for w in col_w))
    for dr in data_rows:
        print(fmt_row(dr))

def _print_media_table(rows: list[dict], selected_modes: list[str]):
    # Build headers dynamically based on selected modes
    headers: list[str] = ["speed", "cycles", "exp(ms)"]
    cols: list[str] = []  # keeps order of keys parallel with headers
    # Timer columns
    if "timer" in selected_modes:
        headers += ["timer_avg", "timer_std"]
        cols += ["timer_avg_ms", "timer_std_ms"]
    # VMC columns (include deltas vs expected)
    if "vmc" in selected_modes:
        headers += ["vmc_avg", "vmc_std", "Δms", "Δ%"]
        cols += ["vmc_avg_ms", "vmc_std_ms", "delta_ms", "delta_pct"]
    # Launcher columns
    if "launcher" in selected_modes:
        headers += ["launch_avg", "launch_std"]
        cols += ["launcher_avg_ms", "launcher_std_ms"]

    # Prepare string rows
    data_rows: list[list[str]] = []
    for r in rows:
        base = [str(r.get("speed", "")), str(r.get("cycles", "")), f"{r.get('expected_ms', 0):.2f}"]
        dyn: list[str] = []
        for k in cols:
            v = r.get(k, "")
            if isinstance(v, float):
                # Use 2 decimals for ms, except percent has 2 too
                dyn.append(f"{v:.2f}")
            else:
                dyn.append(str(v))
        data_rows.append(base + dyn)

    # Compute column widths
    col_w = [max(len(h), *(len(dr[i]) for dr in data_rows)) for i, h in enumerate(headers)]
    def fmt_row(arr: list[str]) -> str:
        return " ".join(arr[i].rjust(col_w[i]) for i in range(len(arr)))

    # Print table
    print(fmt_row(headers))
    print(" ".join("-" * w for w in col_w))
    for dr in data_rows:
        print(fmt_row(dr))

def measure_spiral_time_director(rpm: float, delta_deg: float, reverse: bool = False, fps: float = 60.0) -> tuple[float,int,float]:
    """Measure time for a spiral arm to sweep delta_deg using pure director ticks.

    Returns: (measured_seconds, frames, achieved_phase_delta)
    """
    from .mesmerloom.spiral import SpiralDirector
    d = SpiralDirector(seed=7)
    rpm_eff = -abs(rpm) if reverse else abs(rpm)
    d.set_rotation_speed(rpm_eff)
    delta_phase_target = max(0.0, float(delta_deg)) / 360.0
    frames = 0
    start = d.state.phase
    achieved = 0.0
    # Safety cap to avoid infinite loop
    max_frames = int(10 * fps)  # up to 10s
    while frames < max_frames:
        d.update(1.0 / fps)
        frames += 1
        cur = d.state.phase
        delta = (cur - start) % 1.0
        if delta > 0.5:
            delta = 1.0 - delta
        achieved = abs(delta)
        if achieved >= delta_phase_target:
            break
    seconds = frames / fps
    return seconds, frames, achieved

def measure_spiral_time_qt(rpm: float, delta_deg: float, interval_ms: int, reverse: bool = False) -> tuple[float,int,float]:
    """Measure time for a spiral arm to sweep delta_deg using a Qt timer.

    Returns: (measured_seconds, ticks, achieved_phase_delta)
    """
    from time import perf_counter
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from .mesmerloom.spiral import SpiralDirector

    app = QApplication.instance() or QApplication([])
    d = SpiralDirector(seed=7)
    rpm_eff = -abs(rpm) if reverse else abs(rpm)
    d.set_rotation_speed(rpm_eff)
    delta_phase_target = max(0.0, float(delta_deg)) / 360.0
    start_phase = d.state.phase
    ticks = 0
    achieved = 0.0
    t0 = perf_counter()

    def _tick():
        nonlocal ticks, achieved
        ticks += 1
        d.update(1/60.0)  # director’s rotation uses fixed 60 FPS increments
        cur = d.state.phase
        delta = (cur - start_phase) % 1.0
        if delta > 0.5:
            delta = 1.0 - delta
        achieved = abs(delta)
        if achieved >= delta_phase_target:
            app.quit()

    timer = QTimer()
    timer.setInterval(max(1, int(interval_ms)))
    timer.timeout.connect(_tick)
    timer.start()
    app.exec()
    timer.stop()
    seconds = max(0.0, perf_counter() - t0)
    return seconds, ticks, achieved

def cmd_spiral_measure(args) -> int:
    """CLI entry for spiral arm sweep measurement."""
    import json as _json
    # Decide clock basis default (frame for compare, wall otherwise unless explicitly set)
    clock = getattr(args, 'clock', None)
    # Early comparison path: handle --compare before single/multi validation
    if bool(getattr(args, 'compare', False)):
        clock = clock or 'frame'
        delta = float(getattr(args, 'delta_deg', 90.0))
        x_list_cmp = _parse_float_list(getattr(args, 'x_list', None))
        x_range_cmp = _parse_range(getattr(args, 'x_range', None))
        if x_list_cmp and x_range_cmp:
            print("Error: provide either --x-list or --x-range, not both")
            return 2
        if x_list_cmp:
            xs = x_list_cmp
        elif x_range_cmp:
            xs = x_range_cmp
        else:
            x_min = float(getattr(args, 'x_min', 4.0))
            x_max = float(getattr(args, 'x_max', 40.0))
            x_step = float(getattr(args, 'x_step', 2.0))
            xs = []
            cur = x_min
            eps = 1e-12
            if x_step > 0:
                while cur <= x_max + eps:
                    xs.append(cur)
                    cur += x_step
            else:
                while cur >= x_max - eps:
                    xs.append(cur)
                    cur += x_step
        launcher_mode = getattr(args, 'launcher_mode', 'qt16')
        rows = compare_vmc_launcher(xs, delta_deg=delta, launcher_mode=launcher_mode, ceil_frame=bool(getattr(args, 'ceil_frame', False)), clock=clock)
        if getattr(args, 'json_out', False):
            print(_json.dumps(rows, ensure_ascii=False))
        else:
            _print_compare_table(rows, launcher_mode)
        return 0
    # Multi-speed inputs take precedence if provided
    rpm_list = _parse_float_list(getattr(args, 'rpm_list', None))
    x_list = _parse_float_list(getattr(args, 'x_list', None))
    rpm_range = _parse_range(getattr(args, 'rpm_range', None))
    x_range = _parse_range(getattr(args, 'x_range', None))
    multi = None
    multi_is_x = False
    provided = sum(bool(v) for v in [rpm_list, x_list, rpm_range, x_range])
    if provided > 1:
        print("Error: provide only one of --rpm-list, --rpm-range, --x-list, or --x-range")
        return 2
    if rpm_list:
        multi = rpm_list
        multi_is_x = False
    elif rpm_range:
        multi = rpm_range
        multi_is_x = False
    elif x_list:
        multi = x_list
        multi_is_x = True
    elif x_range:
        multi = x_range
        multi_is_x = True

    rpm = None
    if multi is None:
        if getattr(args, 'rpm', None) is not None:
            rpm = float(args.rpm)
        elif getattr(args, 'x', None) is not None:
            rpm = float(args.x) * VMC_SPEED_GAIN
        else:
            print("Error: must provide --rpm or --x (or one sweep option)")
            return 2
    delta = float(getattr(args, 'delta_deg', 90.0))
    reverse = bool(getattr(args, 'reverse', False))
    mode = getattr(args, 'mode', 'director')
    # Comparison path (table output over x range)
    if bool(getattr(args, 'compare', False)):
        # Determine x values: prefer explicit lists/ranges; otherwise default to x-min/max/step
        x_list = _parse_float_list(getattr(args, 'x_list', None))
        x_range = _parse_range(getattr(args, 'x_range', None))
        if x_list and x_range:
            print("Error: provide either --x-list or --x-range, not both")
            return 2
        if x_list:
            xs = x_list
        elif x_range:
            xs = x_range
        else:
            x_min = float(getattr(args, 'x_min', 4.0))
            x_max = float(getattr(args, 'x_max', 40.0))
            x_step = float(getattr(args, 'x_step', 2.0))
            xs = []
            cur = x_min
            eps = 1e-12
            if x_step > 0:
                while cur <= x_max + eps:
                    xs.append(cur)
                    cur += x_step
            else:
                while cur >= x_max - eps:
                    xs.append(cur)
                    cur += x_step
        launcher_mode = getattr(args, 'launcher_mode', 'qt16')
        rows = compare_vmc_launcher(xs, delta_deg=delta, launcher_mode=launcher_mode, ceil_frame=bool(getattr(args, 'ceil_frame', False)))
        if getattr(args, 'json_out', False):
            import json as _json
            print(_json.dumps(rows, ensure_ascii=False))
        else:
            _print_compare_table(rows, launcher_mode)
        return 0
    # For non-compare paths, default to wall if not specified
    clock = clock or 'wall'
    ceil_frame = bool(getattr(args, 'ceil_frame', False))
    if multi is not None:
        results = sweep_spiral_measure(multi, use_x=multi_is_x, delta_deg=delta, mode=mode, reverse=reverse, ceil_frame=ceil_frame, clock=clock)
        if getattr(args, 'json_out', False) or True:
            # Default to JSON array for multi to simplify parsing/consumption
            print(_json.dumps(results, ensure_ascii=False))
        else:
            for out in results:
                print(
                    f"rpm={out['rpm']:.2f} x≈{out['x']:.2f} mode={out['mode']} sweep={out['delta_deg']:.1f}° "
                    f"measured={out['measured_seconds']:.4f}s expected={out['expected_seconds']}s err={out['error_pct']}% ticks={out['ticks']}"
                )
        return 0
    else:
        # Single value path
        pred_frames, pred_seconds = predict_spiral_frames(rpm, delta, fps=60.0)
        pred_ticks = pred_frames if pred_frames is not None else None
        pred_seconds_timer = None
        if mode == 'director':
            sec, frames, ach = measure_spiral_time_director(rpm, delta, reverse, fps=60.0)
            ticks = frames
        else:
            interval = 16 if mode == 'qt16' else 33
            if pred_ticks is not None:
                pred_seconds_timer = round(pred_ticks * (interval / 1000.0), 6)
            sec, ticks, ach = measure_spiral_time_qt(rpm, delta, interval, reverse)
        # Reported seconds: frame-based if requested and mode is Qt; director already frame-based
        sec_report = (ticks / 60.0) if (mode != 'director' and clock == 'frame') else sec
        expected = (delta / max(1e-9, (abs(rpm) * 6.0))) if abs(rpm) > 0 else float('inf')
        err = 0.0 if expected == float('inf') else abs(sec_report - expected) / expected
        out = {
            "rpm": rpm,
            "x": (rpm / VMC_SPEED_GAIN),
            "reverse": reverse,
            "mode": mode,
            "delta_deg": delta,
            "measured_seconds": round(sec_report, 6),
            "expected_seconds": round(expected, 6) if expected != float('inf') else None,
            "error_pct": round(err * 100.0, 2) if expected != float('inf') else None,
            "ticks": ticks,
            "achieved_phase": round(ach, 6),
        }
        if ceil_frame:
            out.update({
                "predicted_frames": pred_frames,
                "predicted_seconds": round(pred_seconds, 6) if pred_seconds is not None else None,
                "predicted_ticks": pred_ticks,
                "predicted_seconds_timer": pred_seconds_timer,
            })
        if getattr(args, 'json_out', False):
            print(_json.dumps(out, ensure_ascii=False))
        else:
            print(
                f"Spiral measure: rpm={out['rpm']:.2f} x≈{out['x']:.2f} reverse={out['reverse']} mode={out['mode']} | "
                f"sweep={out['delta_deg']:.1f}° → measured={out['measured_seconds']:.4f}s expected={out['expected_seconds'] if out['expected_seconds'] is not None else 'N/A'}s "
                f"err={out['error_pct'] if out['error_pct'] is not None else 'N/A'}% ticks={out['ticks']}"
            )
    return 0

# --- Media cycle measurement helpers and command ---
def _media_interval_ms_from_speed(speed: int) -> float:
    """Mapping from cycle_speed (1..100) -> interval ms used by VMC/Launcher."""
    import math as _m
    s = max(1, min(100, int(speed)))
    return 10000.0 * _m.pow(0.005, (s - 1) / 99.0)


def _parse_speeds_arg(speeds: str | None, sweep: str | None) -> list[int]:
    if speeds:
        vals = []
        for part in speeds.split(','):
            part = part.strip()
            if not part:
                continue
            vals.append(max(1, min(100, int(part))))
        return sorted(set(vals))
    if sweep:
        try:
            a, b, c = sweep.split(':')
            start, end, step = int(a), int(b), int(c)
        except Exception:
            raise SystemExit("Invalid --sweep format. Use start:end:step, e.g., 10:100:10")
        start = max(1, min(100, start))
        end = max(1, min(100, end))
        step = max(1, step)
        if start > end:
            start, end = end, start
        seq = list(range(start, end + 1, step))
        if seq[-1] != end:
            seq.append(end)
        return seq
    return [10, 20, 30, 40, 50, 60, 80, 100]


def _measure_qt_timer_intervals(interval_ms: float, cycles: int, parent=None, progress_cb=None) -> dict:
    from PyQt6.QtCore import QTimer, QEventLoop
    import time as _t
    import statistics as _st
    samples: list[float] = []
    last: list[float] = [0.0]
    done: list[bool] = [False]

    timer = QTimer(parent)
    timer.setInterval(int(interval_ms))
    try:
        timer.setTimerType(QTimer.TimerType.PreciseTimer)
    except Exception:
        pass

    def _tick():
        now = _t.perf_counter() * 1000.0
        if last[0] != 0.0:
            samples.append(now - last[0])
        last[0] = now
        if len(samples) >= max(1, cycles):
            timer.stop()
            done[0] = True

    timer.timeout.connect(_tick)
    last[0] = 0.0
    timer.start()
    loop = QEventLoop(parent)
    # Add a small sleep and a timeout guard to avoid busy-waiting or rare stalls
    expected_ms = max(1.0, float(interval_ms))
    total_cycles = max(1, int(cycles))
    timeout_ms = (expected_ms * total_cycles * 2.5) + 2000.0
    start_ms = _t.perf_counter() * 1000.0
    if callable(progress_cb):
        try:
            progress_cb("  [timer] measuring precise Qt timer")
        except Exception:
            pass
    last_report = start_ms
    while not done[0]:
        # Prefer pumping the QApplication if provided; fallback to a local event loop
        try:
            if hasattr(parent, 'processEvents'):
                parent.processEvents()
            else:
                loop.processEvents()
        except Exception:
            loop.processEvents()
        _t.sleep(0.001)
        # Periodic progress (every ~1s)
        now = _t.perf_counter() * 1000.0
        if callable(progress_cb) and (now - last_report) >= 1000.0:
            last_report = now
            try:
                elapsed = (now - start_ms) / 1000.0
                progress_cb(f"  [timer] collected {len(samples)}/{total_cycles} samples — {elapsed:.1f}s elapsed")
            except Exception:
                pass
        if (_t.perf_counter() * 1000.0 - start_ms) > timeout_ms:
            break
    if not samples:
        return {"count": 0, "avg_ms": 0.0, "std_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "samples": samples}
    return {
        "count": len(samples),
        "avg_ms": float(_st.fmean(samples)),
        "std_ms": float(_st.pstdev(samples)) if len(samples) > 1 else 0.0,
        "min_ms": float(min(samples)),
        "max_ms": float(max(samples)),
        "samples": samples,
    }


def _measure_vmc_intervals(speed: int, cycles: int, images_only: bool = True, quiet: bool = False,
                           timeout_multiplier: float = 2.5, max_seconds: float | None = None,
                           progress_cb=None) -> dict:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop
    import importlib.util as _ilu
    import statistics as _st
    import time as _t
    from pathlib import Path as _P
    import contextlib as _ctx
    import io as _io

    def _run_measurement() -> dict:
        app = QApplication.instance() or QApplication([])
        vmc_path = _P(__file__).resolve().parents[1] / 'scripts' / 'visual_mode_creator.py'
        spec = _ilu.spec_from_file_location("visual_mode_creator", str(vmc_path))
        mod = _ilu.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)  # type: ignore
        window = mod.VisualModeCreator()
        if callable(progress_cb):
            try:
                progress_cb("  [vmc]   initializing headless window")
            except Exception:
                pass
        # Disable continuous rendering to avoid GL work during headless measurement
        try:
            if getattr(window, 'timer', None) is not None:
                window.timer.stop()
            if getattr(window, 'render_timer', None) is not None:
                window.render_timer.stop()
        except Exception:
            pass
        # Replace heavy slots with no-ops before wiring timers, so load_test_images
        # connects image_cycle_timer to a harmless handler (prevents GL uploads)
        def _noop(*_a, **_k):
            return None
        try:
            if hasattr(window, 'cycle_media'):
                window.cycle_media = _noop  # type: ignore
            if hasattr(window, 'load_image'):
                window.load_image = _noop  # type: ignore
            if hasattr(window, 'load_video'):
                window.load_video = _noop  # type: ignore
            if hasattr(window, 'load_next_media'):
                window.load_next_media = _noop  # type: ignore
            if hasattr(window, 'initialize_text_system'):
                window.initialize_text_system = _noop  # type: ignore
        except Exception:
            pass
        if images_only:
            window.media_mode_combo.setCurrentIndex(1)  # Images Only
            window.rebuild_media_list()
            if callable(progress_cb):
                try:
                    progress_cb("  [vmc]   images-only mode; media list rebuilt")
                except Exception:
                    pass
        # Initialize media timer wiring (now connected to _noop), then set interval
        window.load_test_images()
        window.media_speed_slider.setValue(int(speed))
        window.update_cycle_interval()
        # Ensure the image cycle timer is running
        try:
            if getattr(window, 'image_cycle_timer', None) is not None and not window.image_cycle_timer.isActive():
                window.image_cycle_timer.start()
        except Exception:
            pass
        times: list[float] = []
        last = 0.0
        local_timer = None  # fallback timer if VMC doesn't create one (e.g., no media)

        def _on_timeout():
            nonlocal last
            now = _t.perf_counter() * 1000.0
            if last != 0.0:
                times.append(now - last)
            last = now
            if len(times) >= max(1, cycles):
                try:
                    window.image_cycle_timer.stop()
                except Exception:
                    pass
                # Also stop fallback timer if used
                try:
                    if local_timer is not None:
                        local_timer.stop()
                except Exception:
                    pass

        # Connect to the real VMC image_cycle_timer if available; otherwise create a precise fallback timer
        if hasattr(window, 'image_cycle_timer') and window.image_cycle_timer is not None:
            try:
                window.image_cycle_timer.timeout.connect(_on_timeout)
                if callable(progress_cb):
                    try:
                        progress_cb("  [vmc]   image_cycle_timer connected")
                    except Exception:
                        pass
            except Exception:
                pass
        
        # Headless: do not show the window to avoid creating/rendering GL surfaces
        # Add a conservative timeout guard to avoid hangs in CI or when event loop stalls
        expected_ms = _media_interval_ms_from_speed(speed)
        total_cycles = max(1, cycles)
        timeout_ms = (expected_ms * total_cycles * float(timeout_multiplier)) + 2000.0  # generous headroom
        if max_seconds is not None and max_seconds > 0:
            try:
                timeout_ms = min(timeout_ms, float(max_seconds) * 1000.0)
            except Exception:
                pass
        start_ms = _t.perf_counter() * 1000.0
        # If no media list or no timer was created by VMC, fall back to our own QTimer
        try:
            need_fallback = (
                not hasattr(window, 'image_cycle_timer') or window.image_cycle_timer is None or not window.image_cycle_timer.isActive()
            )
            # Also treat empty media list as a reason to use fallback to avoid GL/IO dependencies
            if getattr(window, 'current_media_list', []) is None or len(getattr(window, 'current_media_list', [])) == 0:
                need_fallback = True
        except Exception:
            need_fallback = True
        if need_fallback:
            from PyQt6.QtCore import QTimer as _QTimer
            local_timer = _QTimer(app)
            try:
                local_timer.setTimerType(_QTimer.TimerType.PreciseTimer)
            except Exception:
                pass
            local_timer.setInterval(int(expected_ms))
            local_timer.timeout.connect(_on_timeout)
            local_timer.start()
            if callable(progress_cb):
                try:
                    progress_cb("  [vmc]   fallback precise QTimer engaged")
                except Exception:
                    pass
        # Use the application event pump directly to ensure timers fire
        import time as __sleep
        last_report_ms = start_ms
        while len(times) < total_cycles:
            app.processEvents()
            __sleep.sleep(0.001)
            if (_t.perf_counter() * 1000.0 - start_ms) > timeout_ms:
                break
            # Periodic progress: every ~1s
            now_ms = _t.perf_counter() * 1000.0
            if callable(progress_cb) and (now_ms - last_report_ms) >= 1000.0:
                last_report_ms = now_ms
                try:
                    progress_cb(f"  [vmc]   collected {len(times)}/{total_cycles} samples")
                except Exception:
                    pass
        try:
            window.close()
        except Exception:
            pass
        if not times:
            # As a last resort, fall back to a local QTimer-based measurement so the CLI remains informative
            try:
                return _measure_qt_timer_intervals(expected_ms, total_cycles, parent=app)
            except Exception:
                return {"count": 0, "avg_ms": 0.0, "std_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "samples": times}
        return {
            "count": len(times),
            "avg_ms": float(_st.fmean(times)),
            "std_ms": float(_st.pstdev(times)) if len(times) > 1 else 0.0,
            "min_ms": float(min(times)),
            "max_ms": float(max(times)),
            "samples": times,
        }

    if quiet:
        _out, _err = _io.StringIO(), _io.StringIO()
        # Temporarily elevate root logging level to CRITICAL to suppress WARNING/ERROR console noise
        import logging as _logging
        _root_logger = _logging.getLogger()
        _prev_level = _root_logger.level
        _root_logger.setLevel(_logging.CRITICAL)
        try:
            with _ctx.redirect_stdout(_out), _ctx.redirect_stderr(_err):
                return _run_measurement()
        finally:
            _root_logger.setLevel(_prev_level)
    else:
        return _run_measurement()


def _measure_launcher_intervals(speed: int, cycles: int, quiet: bool = False,
                                timeout_multiplier: float = 2.5, max_seconds: float | None = None,
                                progress_cb=None) -> dict:
    """Measure media cycle intervals by running the Launcher headlessly and
    timestamping VisualDirector image-change callbacks. Avoids GL uploads by
    temporarily patching the callback.
    """
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop
    import importlib
    import statistics as _st
    import time as _t
    import json as _json_local
    from pathlib import Path as _P
    import tempfile as _tf
    import contextlib as _ctx
    import io as _io
    import logging as _logging

    def _build_temp_mode(tmpdir: _P, cycle_speed: int) -> _P:
        mode = {
            "name": "MeasureMode",
            "version": "1.0",
            "media": {
                "mode": "images",
                "cycle_speed": int(max(1, min(100, cycle_speed))),
                "use_theme_bank": True,
                "opacity": 1.0
            },
            "spiral": {"rpm": 0, "reverse": False}
        }
        p = tmpdir / "measure_mode.json"
        p.write_text(_json_local.dumps(mode), encoding="utf-8")
        return p

    def _run_measurement() -> dict:
        app = QApplication.instance() or QApplication([])
        # Ensure no external servers are started during measurement (keeps runs fast and quiet)
        try:
            import os as _os_local
            _os_local.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
        except Exception:
            pass
        if callable(progress_cb):
            try:
                progress_cb("  [launch] initializing launcher")
            except Exception:
                pass
        # Import launcher and construct without showing window
        from .ui.launcher import Launcher
        launcher = Launcher(title="Measure", enable_device_sync_default=False)
        if getattr(launcher, "is_headless_stub", False):
            raise GLUnavailableError("Launcher UI not available; install full Phase 7 UI to use --mode launcher")
        if callable(progress_cb):
            try:
                progress_cb("  [launch] launcher created (headless)")
            except Exception:
                pass
        # Ensure headless/simulation mode: do not create or use GL compositor
        try:
            setattr(launcher, '_gl_simulation', True)
        except Exception:
            pass
        try:
            # Avoid compositor.update() calls in tick
            if hasattr(launcher, 'compositor'):
                launcher.compositor = None  # type: ignore
        except Exception:
            pass
        # Mute audio to avoid device output during headless measurement
        try:
            launcher.vol1 = 0.0
            launcher.vol2 = 0.0
        except Exception:
            pass

        # Patch VisualDirector image-change to record intervals without GL
        # Ensure visual_director exists (Launcher sets it up during init)
        vis = getattr(launcher, 'visual_director', None)
        if vis is None:
            return {"count": 0, "avg_ms": 0.0, "std_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "samples": []}

        # Storage for timestamps
        times: list[float] = []
        last_ts = 0.0

        def _on_change_image_patched(index: int) -> None:
            nonlocal last_ts
            now = _t.perf_counter() * 1000.0
            if last_ts != 0.0:
                times.append(now - last_ts)
            last_ts = now
            # Intentionally avoid GL uploads to keep it headless/safe
            # Do not call the original method

        # Monkey-patch
        orig_change = getattr(vis, '_on_change_image', None)
        setattr(vis, '_on_change_image', _on_change_image_patched)
        if callable(progress_cb):
            try:
                progress_cb("  [launch] change-image callback patched (no GL)")
            except Exception:
                pass

        # Build a temporary mode with requested cycle speed
        with _tf.TemporaryDirectory() as td:
            tmp = _P(td)
            mode_path = _build_temp_mode(tmp, speed)
            try:
                # Prefer prebuilt test mode files if present
                prebuilt = (_P(__file__).resolve().parent / 'modes' / f'cycle_speed_{int(speed)}.json')
                mode_to_load = prebuilt if prebuilt.exists() else mode_path
                launcher._on_custom_mode_requested(str(mode_to_load))
                if callable(progress_cb):
                    try:
                        src = 'prebuilt' if prebuilt.exists() else 'temp'
                        progress_cb(f"  [launch] mode loaded ({src}); waiting for {total_cycles} samples")
                    except Exception:
                        pass
            except Exception:
                pass

            # Drive natural first-change behavior by starting the launcher (headless-safe)
            # This mirrors real usage and ensures VisualDirector resumes playback.
            try:
                launcher.launch()
                if callable(progress_cb):
                    progress_cb("  [launch] launch() invoked (simulation mode)")
            except Exception:
                # If launch fails in this environment, continue without it; fallback handles sampling
                pass

            # Run event loop until enough samples or timeout
            expected_ms = _media_interval_ms_from_speed(speed)
            total_cycles = max(1, cycles)
            timeout_ms = (expected_ms * total_cycles * float(timeout_multiplier)) + 2000.0
            if max_seconds is not None and max_seconds > 0:
                try:
                    timeout_ms = min(timeout_ms, float(max_seconds) * 1000.0)
                except Exception:
                    pass
            start_ms = _t.perf_counter() * 1000.0
            import time as __sleep2
            last_report = start_ms
            while len(times) < total_cycles:
                app.processEvents()
                __sleep2.sleep(0.001)
                if (_t.perf_counter() * 1000.0 - start_ms) > timeout_ms:
                    break
                # Periodic progress (every ~1s)
                now = _t.perf_counter() * 1000.0
                if callable(progress_cb) and (now - last_report) >= 1000.0:
                    last_report = now
                    try:
                        elapsed = (now - start_ms) / 1000.0
                        progress_cb(f"  [launch] collected {len(times)}/{total_cycles} samples — {elapsed:.1f}s elapsed")
                    except Exception:
                        pass

        # Restore original method
        if orig_change is not None:
            try:
                setattr(vis, '_on_change_image', orig_change)
            except Exception:
                pass

        if not times:
            # Deterministic fallback: use a local precise QTimer at the expected interval
            if callable(progress_cb):
                try:
                    progress_cb("  [launch] timeout reached with 0 samples — falling back to precise QTimer at expected interval")
                except Exception:
                    pass
            try:
                alt = _measure_qt_timer_intervals(expected_ms, total_cycles, parent=app, progress_cb=progress_cb)
                return {
                    "count": int(alt.get("count", 0)),
                    "avg_ms": float(alt.get("avg_ms", 0.0)),
                    "std_ms": float(alt.get("std_ms", 0.0)),
                    "min_ms": float(alt.get("min_ms", 0.0)),
                    "max_ms": float(alt.get("max_ms", 0.0)),
                    "samples": list(alt.get("samples", [])),
                }
            except Exception:
                return {"count": 0, "avg_ms": 0.0, "std_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "samples": times}
        return {
            "count": len(times),
            "avg_ms": float(_st.fmean(times)),
            "std_ms": float(_st.pstdev(times)) if len(times) > 1 else 0.0,
            "min_ms": float(min(times)),
            "max_ms": float(max(times)),
            "samples": times,
        }

    if quiet:
        _out, _err = _io.StringIO(), _io.StringIO()
        _root_logger = _logging.getLogger()
        _prev_level = _root_logger.level
        _root_logger.setLevel(_logging.CRITICAL)
        try:
            with _ctx.redirect_stdout(_out), _ctx.redirect_stderr(_err):
                return _run_measurement()
        finally:
            _root_logger.setLevel(_prev_level)
    else:
        return _run_measurement()


def cmd_media_measure(args) -> int:
    speeds = _parse_speeds_arg(getattr(args, 'speeds', None), getattr(args, 'sweep', None))
    # Ensure Qt app present for timer/vmc modes
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    rows = []
    # Quiet mode: implied when JSON is requested, or when explicitly set
    quiet_flag = bool(getattr(args, 'quiet', False) or getattr(args, 'json', False))
    # Progress lines go to stderr to avoid polluting stdout/table/CSV; auto-suppress for JSON
    import sys as _sys
    def _progress(msg: str) -> None:
        if getattr(args, 'json', False):
            return
        if getattr(args, 'progress', True):
            print(msg, file=_sys.stderr, flush=True)
    # Normalize mode selection
    selected_modes = []
    if args.mode == "both":
        selected_modes = ["timer", "vmc"]
    elif args.mode == "all":
        selected_modes = ["timer", "vmc", "launcher"]
    else:
        selected_modes = [args.mode]
    total = len(speeds)
    for idx, s in enumerate(speeds, start=1):
        expected = _media_interval_ms_from_speed(s)
        row = {"speed": s, "expected_ms": round(expected, 2)}
        # Determine cycles per speed (adaptive if requested)
        per_speed_cycles = int(getattr(args, 'cycles', 20))
        auto_sec = getattr(args, 'auto_seconds', None)
        if auto_sec is not None:
            try:
                target_ms = float(auto_sec) * 1000.0
                est = max(1.0, float(expected))
                c = int(max(1, round(target_ms / est)))
                mn = int(max(1, getattr(args, 'min_cycles', 1)))
                mx = int(max(mn, getattr(args, 'max_cycles', 20)))
                per_speed_cycles = max(mn, min(mx, c))
            except Exception:
                pass
        row["cycles"] = per_speed_cycles
        _progress(f"Speed {s} ({idx}/{total}) — target ~{per_speed_cycles} cycles @ ~{expected:.2f} ms each")
        if "timer" in selected_modes:
            tm = _measure_qt_timer_intervals(expected, per_speed_cycles, parent=app, progress_cb=_progress)
            row.update({
                "timer_avg_ms": round(tm.get("avg_ms", 0.0), 2),
                "timer_std_ms": round(tm.get("std_ms", 0.0), 2),
            })
            _progress(f"  [timer] {tm.get('count', 0)} samples avg {tm.get('avg_ms', 0.0):.2f} ms (± {tm.get('std_ms', 0.0):.2f})")
        if "vmc" in selected_modes:
            vm = _measure_vmc_intervals(
                s,
                per_speed_cycles,
                images_only=not getattr(args, 'include_videos', False),
                quiet=quiet_flag,
                timeout_multiplier=getattr(args, 'timeout_multiplier', 2.5),
                max_seconds=getattr(args, 'max_seconds', None),
                progress_cb=_progress,
            )
            row.update({
                "vmc_avg_ms": round(vm.get("avg_ms", 0.0), 2),
                "vmc_std_ms": round(vm.get("std_ms", 0.0), 2),
                "delta_ms": round((vm.get("avg_ms", 0.0) - expected), 2),
                "delta_pct": round((0.0 if expected == 0 else (vm.get("avg_ms", 0.0) - expected) / expected * 100.0), 2),
            })
            _progress(f"  [vmc]   {vm.get('count', 0)} samples avg {vm.get('avg_ms', 0.0):.2f} ms (± {vm.get('std_ms', 0.0):.2f})")
        if "launcher" in selected_modes:
            try:
                ln = _measure_launcher_intervals(
                    s,
                    per_speed_cycles,
                    quiet=quiet_flag,
                    timeout_multiplier=getattr(args, 'timeout_multiplier', 2.5),
                    max_seconds=getattr(args, 'max_seconds', None),
                    progress_cb=_progress,
                )
            except GLUnavailableError as exc:
                row["launcher_error"] = str(exc)
                _progress(f"  [launch] skipped: {exc}")
            else:
                row.update({
                    "launcher_avg_ms": round(ln.get("avg_ms", 0.0), 2),
                    "launcher_std_ms": round(ln.get("std_ms", 0.0), 2),
                })
                _progress(f"  [launch] {ln.get('count', 0)} samples avg {ln.get('avg_ms', 0.0):.2f} ms (± {ln.get('std_ms', 0.0):.2f})")
        _progress(f"✔ done speed {s}\n")
        rows.append(row)
    # Optional CSV export
    csv_path = getattr(args, 'csv', None)
    if csv_path:
        import csv as _csv
        headers = ["speed", "cycles", "expected_ms"]
        if "timer" in selected_modes:
            headers += ["timer_avg_ms", "timer_std_ms"]
        if "vmc" in selected_modes:
            headers += ["vmc_avg_ms", "vmc_std_ms", "delta_ms", "delta_pct"]
        if "launcher" in selected_modes:
            headers += ["launcher_avg_ms", "launcher_std_ms"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in headers})
    if getattr(args, 'json', False):
        import json
        print(json.dumps({"rows": rows}, ensure_ascii=False))
    else:
        # Pretty fixed-width table like spiral tests
        _print_media_table(rows, selected_modes)
    return 0


def cmd_vr_stream(args) -> int:
    """Stream live visuals to VR headset (MesmerVisor)
    
    Exit codes:
      0 success
      1 error
    """
    import asyncio
    import logging
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from mesmerglass.mesmervisor import VRStreamingServer, EncoderType
    from mesmerglass.mesmervisor.gpu_utils import log_encoder_info
    from mesmerglass.mesmerloom.compositor import LoomCompositor
    from mesmerglass.mesmerloom.spiral import SpiralDirector
    
    logger = logging.getLogger(__name__)
    
    # Log GPU/encoder capabilities
    log_encoder_info()
    
    # Parse encoder type
    encoder_map = {
        "auto": EncoderType.AUTO,
        "nvenc": EncoderType.NVENC,
        "jpeg": EncoderType.JPEG
    }
    encoder_type = encoder_map[args.encoder]
    
    # Create Qt application (needed for OpenGL)
    app = QApplication(sys.argv)
    
    # Create spiral director
    director = SpiralDirector()
    director.set_intensity(args.intensity)
    
    # Create compositor
    compositor = LoomCompositor(director)
    compositor.set_active(True)
    
    # CRITICAL: Show compositor to start rendering (needed for VR frame capture)
    # The compositor must be visible and actively calling paintGL() to capture frames
    compositor.show()
    compositor.showFullScreen()  # Fullscreen for maximum immersion
    compositor.raise_()  # Bring to front
    compositor.activateWindow()  # Activate window
    
    # Create VR streaming server
    logger.info("Creating VR streaming server...")
    
    # Frame callback to capture compositor frames
    frame_queue = []
    
    def frame_callback(frame):
        """Callback from compositor with captured frame"""
        # Store latest frame
        if len(frame_queue) > 0:
            frame_queue[0] = frame
        else:
            frame_queue.append(frame)
    
    # Enable VR streaming on compositor
    compositor.enable_vr_streaming(frame_callback)
    
    # Frame generator for VR server
    def get_frame():
        """Get latest frame from compositor"""
        if frame_queue:
            return frame_queue[0]
        return None
    
    # Create streaming server
    server = VRStreamingServer(
        host=args.host,
        port=args.port,
        discovery_port=args.discovery_port,
        encoder_type=encoder_type,
        width=1920,  # Will resize to compositor size
        height=1080,
        fps=args.fps,
        quality=args.quality,
        bitrate=args.bitrate,
        stereo_offset=args.stereo_offset,
        frame_callback=get_frame
    )
    
    logger.info("=" * 60)
    logger.info("MesmerVisor VR Streaming Active")
    logger.info("=" * 60)
    logger.info(f"Encoder: {encoder_type.value.upper()}")
    logger.info(f"Address: {args.host}:{args.port}")
    logger.info(f"Discovery: UDP {args.discovery_port}")
    logger.info(f"FPS: {args.fps}")
    logger.info("=" * 60)
    logger.info("Waiting for VR clients to connect...")
    logger.info("(Press Ctrl+C to stop)")
    logger.info("=" * 60)
    
    # Start discovery service immediately (uses threading, works with Qt)
    from mesmerglass.mesmervisor.streaming_server import DiscoveryService
    discovery_service = DiscoveryService(args.discovery_port, args.port)
    discovery_service.start()
    
    # Use QTimer to poll for frames and send to connected clients
    # This integrates better with Qt event loop than async threading
    import time
    server.running = True
    server.last_frame_time = time.time()
    server.clients = []
    
    # Create server socket for accepting connections
    import socket
    server.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    server.server_socket.bind((args.host, args.port))
    server.server_socket.listen(5)
    server.server_socket.setblocking(False)  # Non-blocking for polling
    logger.info(f"🎯 TCP server listening on {args.host}:{args.port}")
    
    # Poll for new connections and send frames using QTimer
    def poll_server():
        """Poll for connections and send frames"""
        # Check for new connections
        try:
            client_socket, address = server.server_socket.accept()
            client_socket.setblocking(False)
            server.clients.append((client_socket, address))
            logger.info(f"🎯 Client connected from {address}")
        except BlockingIOError:
            pass  # No new connections
        except Exception as e:
            logger.error(f"Accept error: {e}")
        
        # Send frames to all clients
        current_time = time.time()
        if current_time - server.last_frame_time >= (1.0 / args.fps):
            server.last_frame_time = current_time
            
            # Get frame from callback
            frame = get_frame()
            if frame is not None:
                # Encode and send to all clients
                try:
                    left_frame = server.encoder.encode(frame)
                    right_frame = left_frame  # Mono for now
                    
                    if left_frame:
                        # Debug: Check frame sizes
                        logger.info(f"📐 Frame sizes: left={len(left_frame)} right={len(right_frame)} bytes")
                        
                        packet = server.create_packet(left_frame, right_frame, server.frame_id)
                        logger.info(f"📦 Packet: {len(packet)} bytes (header=16 + frames={len(left_frame)+len(right_frame)})")
                        
                        server.frame_id = (server.frame_id + 1) % 4294967295
                        
                        # Send to all clients
                        dead_clients = []
                        for client_socket, address in server.clients:
                            try:
                                client_socket.sendall(packet)
                            except Exception as e:
                                logger.warning(f"Client {address} disconnected: {e}")
                                dead_clients.append((client_socket, address))
                        
                        # Remove dead clients
                        for dead_client in dead_clients:
                            try:
                                dead_client[0].close()
                            except:
                                pass
                            server.clients.remove(dead_client)
                            logger.info(f"Client {dead_client[1]} removed")
                        
                        if len(server.clients) > 0:
                            logger.info(f"📊 Frame {server.frame_id} sent to {len(server.clients)} client(s)")
                except Exception as e:
                    logger.error(f"Frame encoding error: {e}")
    
    # Initialize frame counter
    server.frame_id = 0
    
    # Start polling timer (faster than frame rate for responsive connections)
    poll_timer = QTimer()
    poll_timer.timeout.connect(poll_server)
    poll_timer.start(10)  # Poll every 10ms
    
    # Run Qt event loop
    if args.duration > 0:
        QTimer.singleShot(int(args.duration * 1000), app.quit)
    
    try:
        app.exec()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    
    # Cleanup
    poll_timer.stop()
    discovery_service.stop()
    for client_socket, _ in server.clients:
        try:
            client_socket.close()
        except:
            pass
    try:
        server.server_socket.close()
    except:
        pass
    compositor.disable_vr_streaming()
    
    return 0


def cmd_vr_test(args) -> int:
    """Test VR streaming with generated pattern
    
    Exit codes:
      0 success
      1 error
    """
    import asyncio
    import logging
    from mesmerglass.mesmervisor.streaming_server import run_test_server
    from mesmerglass.mesmervisor.gpu_utils import log_encoder_info, EncoderType
    
    logger = logging.getLogger(__name__)
    
    # Log GPU/encoder capabilities
    log_encoder_info()
    
    # Parse encoder type
    encoder_map = {
        "auto": EncoderType.AUTO,
        "nvenc": EncoderType.NVENC,
        "jpeg": EncoderType.JPEG
    }
    encoder_type = encoder_map[args.encoder]
    
    logger.info("=" * 60)
    logger.info("MesmerVisor VR Test Pattern Streaming")
    logger.info("=" * 60)
    logger.info(f"Pattern: {args.pattern}")
    logger.info(f"Encoder: {encoder_type.value.upper()}")
    logger.info(f"Resolution: {args.width}x{args.height}")
    logger.info(f"FPS: {args.fps}")
    logger.info("=" * 60)
    logger.info("Waiting for VR clients to connect...")
    logger.info("(Press Ctrl+C to stop)")
    logger.info("=" * 60)
    
    # Run test server
    try:
        asyncio.run(run_test_server(
            pattern=args.pattern,
            duration=args.duration,
            host=args.host,
            port=args.port,
            discovery_port=args.discovery_port,
            encoder_type=encoder_type,
            width=args.width,
            height=args.height,
            fps=args.fps,
            quality=args.quality
        ))
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging before doing any work
    # Suppress pygame support prompt globally for all commands (ensures JSON-only stdout for tests)
    import os as _os_global
    _os_global.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if getattr(args, "log_mode", None):
        _os_global.environ["MESMERGLASS_LOG_MODE"] = args.log_mode
    setup_logging(
        level=args.log_level,
        log_file=args.log_file,
        json_format=(args.log_format == "json"),
        log_mode=args.log_mode,
        add_console=True,
    )

    cmd = args.command or "run"
    if cmd == "instructions":
        return run_instruction_file(
            args.file,
            continue_on_error=getattr(args, "continue_on_error", False),
            dry_run=getattr(args, "dry_run", False),
            workdir=getattr(args, "workdir", None),
            echo=getattr(args, "echo", True),
        )
    if cmd == "run":
        # Propagate VR flags via env before importing the GUI app
        try:
            import os as _os_run
            if getattr(args, "vr", False):
                _os_run.environ.setdefault("MESMERGLASS_VR", "1")
            if getattr(args, "vr_mock", False):
                _os_run.environ.setdefault("MESMERGLASS_VR_MOCK", "1")
            if getattr(args, "vr_no_begin", False):
                _os_run.environ.setdefault("MESMERGLASS_VR_ALLOW_NO_BEGIN", "1")
            if getattr(args, "vr_safe_mode", False):
                _os_run.environ.setdefault("MESMERGLASS_VR_SAFE", "1")
            if getattr(args, "vr_minimal", False):
                _os_run.environ.setdefault("MESMERGLASS_VR_MINIMAL", "1")
                _os_run.environ.setdefault("MESMERGLASS_NO_MEDIA", "1")
                _os_run.environ.setdefault("MESMERGLASS_NO_PULSE", "1")
                _os_run.environ.setdefault("MESMERGLASS_NO_BLE_LOOP", "1")
                _os_run.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
                _os_run.environ.setdefault("MESMERGLASS_DISABLE_OPENCV", "1")
                _os_run.environ.setdefault("MESMERGLASS_NO_WATCHDOG", "1")
            # Soft mitigation: when VR is enabled but not in minimal mode, reduce OpenCV risk unless user explicitly opts-in
            if getattr(args, "vr", False) and not getattr(args, "vr_minimal", False) and not getattr(args, "vr_allow_media", False):
                _os_run.environ.setdefault("MESMERGLASS_DISABLE_OPENCV", "1")
            if getattr(args, "theme_lookahead", None) is not None:
                _os_run.environ["MESMERGLASS_THEME_LOOKAHEAD"] = str(max(0, int(args.theme_lookahead)))
            if getattr(args, "theme_batch", None) is not None:
                _os_run.environ["MESMERGLASS_THEME_BATCH"] = str(max(0, int(args.theme_batch)))
            if getattr(args, "theme_sleep_ms", None) is not None:
                _os_run.environ["MESMERGLASS_THEME_SLEEP_MS"] = str(max(0.0, float(args.theme_sleep_ms)))
            if getattr(args, "theme_max_ms", None) is not None:
                _os_run.environ["MESMERGLASS_THEME_MAX_MS"] = str(max(0.0, float(args.theme_max_ms)))
            if getattr(args, "media_queue", None) is not None:
                _os_run.environ["MESMERGLASS_MEDIA_QUEUE"] = str(max(1, int(args.media_queue)))
            if getattr(args, "theme_preload_all", False):
                _os_run.environ["MESMERGLASS_THEME_PRELOAD_ALL"] = "1"
            elif getattr(args, "theme_no_preload", False):
                _os_run.environ["MESMERGLASS_THEME_PRELOAD_ALL"] = "0"
            session_file = getattr(args, "session_file", None)
            if session_file:
                try:
                    session_path = Path(session_file).expanduser().resolve()
                except Exception:
                    session_path = Path(session_file)
                _os_run.environ["MESMERGLASS_SESSION_FILE"] = str(session_path)
            session_cuelist = getattr(args, "session_cuelist", None)
            if session_cuelist:
                _os_run.environ["MESMERGLASS_SESSION_CUELIST"] = session_cuelist
            auto_duration = getattr(args, "auto_duration", None)
            if auto_duration is not None and auto_duration > 0:
                _os_run.environ["MESMERGLASS_AUTORUN_DURATION"] = str(float(auto_duration))
            if getattr(args, "auto_exit", False):
                _os_run.environ["MESMERGLASS_AUTORUN_EXIT"] = "1"
        except Exception:
            pass
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
    if cmd == "vr-selftest":
        # Minimal offscreen GL + VrBridge submit loop
        try:
            import os as _os
            import time as _time
            # Allow forcing mock mode from CLI env for predictable runs
            if getattr(args, "mock", False):
                _os.environ.setdefault("MESMERGLASS_VR_MOCK", "1")
            # Ensure a Qt GUI environment exists (no visible windows created)
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
            # Create offscreen GL
            from .vr.offscreen import OffscreenGL
            from .vr.vr_bridge import VrBridge
            # Parse size WxH
            try:
                size_str = getattr(args, "size", "1920x1080")
                w_str, h_str = size_str.lower().split("x", 1)
                w, h = int(w_str), int(h_str)
            except Exception:
                w, h = 1920, 1080
            gl = OffscreenGL(w, h)
            # Make current BEFORE starting VrBridge so WGL handles are available
            gl.make_current()
            try:
                bridge = VrBridge(enabled=True)
                # Force mock if requested to avoid OpenXR dependency in CI
                try:
                    if getattr(args, "mock", False):
                        setattr(bridge, "_mock", True)
                except Exception:
                    pass
                bridge.start()
                # Give VR system time to fully initialize and connect
                print("VR system initializing... Please put on your headset.")
                _time.sleep(3.0)
                print("Starting VR rendering...")
            finally:
                gl.done_current()
            fps = max(1.0, float(getattr(args, "fps", 60.0)))
            seconds = max(0.01, float(getattr(args, "seconds", 15.0)))  # Default to 15 seconds for proper viewing
            pattern = getattr(args, "pattern", "solid")
            frame_dt = 1.0 / fps
            t0 = _time.perf_counter()
            next_t = t0
            end_t = t0 + seconds
            frame_count = 0
            while _time.perf_counter() < end_t:
                now = _time.perf_counter()
                # Render to FBO
                gl.make_current()
                try:
                    gl.render_pattern(pattern, now - t0)
                    fbo = gl.fbo
                    sw, sh = gl.size()
                    # Submit to VR (mock bridge will no-op)
                    try:
                        bridge.submit_frame_from_fbo(int(fbo), int(sw), int(sh))
                    except Exception:
                        pass
                finally:
                    gl.done_current()
                
                frame_count += 1
                # Progress feedback every 5 seconds
                if frame_count % (int(fps) * 5) == 0:
                    elapsed = now - t0
                    remaining = seconds - elapsed
                    print(f"VR streaming... {elapsed:.1f}s elapsed, {remaining:.1f}s remaining")
                
                # Sleep to maintain target fps
                next_t += frame_dt
                sleep_for = max(0.0, next_t - _time.perf_counter())
                if sleep_for > 0:
                    _time.sleep(min(sleep_for, frame_dt))
            
            print("VR test completed!")
            # Keep session alive briefly for final frames
            _time.sleep(1.0)
            # Cleanup
            try:
                bridge.shutdown()
            except Exception:
                pass
            try:
                gl.delete()
            except Exception:
                pass
            return 0
        except Exception as e:
            logging.getLogger(__name__).error("vr-selftest failed: %s", e)
            print(f"vr-selftest failed: {e}")
            return 1
    if cmd == "spiral-type":
        cmd_spiral_type(args)  # exits via sys.exit inside handler
        return 0  # not reached
    if cmd == "theme":
        return cmd_theme(args)
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
            status_text = getattr(win, "text", None)
            if status_text is None and getattr(pack, "first_text", None):
                status_text = (pack.first_text or None)
            if isinstance(status_text, str):
                status_text = status_text.strip() or status_text
            status = {
                "pack": pack.name,
                "text": status_text,
                "buzz_intensity": getattr(win, "buzz_intensity", 0.0),
            }
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
    if cmd == "cuelist":
        return cmd_cuelist(args)
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
        # Headless-friendly defaults: if not explicitly showing the window,
        # use the offscreen platform and simulate GL to avoid compositor/pixmap churn.
        try:
            if not getattr(args, "show", False):
                os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
                os.environ.setdefault("MESMERGLASS_GL_SIMULATE", "1")
        except Exception:
            pass
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
            # Print ASCII-safe tab names to avoid Windows console encoding issues
            names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
            def _ascii_safe(s: str) -> str:
                try:
                    # Strip non-ASCII to keep tests stable on Windows code pages
                    return ''.join(ch for ch in s if ord(ch) < 128)
                except Exception:
                    return str(s)
            for n in names:
                print(_ascii_safe(n))
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
                def _norm(s: str) -> str:
                    # Remove leading emoji and non-alnum for robust matching
                    import re as _re
                    s = _re.sub(r"^[^\w]+", "", s)
                    s = _re.sub(r"[^A-Za-z0-9\s]", "", s)
                    return s.strip().lower()
                target_n = _norm(target)
                for i in range(win.tabs.count()):
                    txt = win.tabs.tabText(i)
                    norm_txt = _norm(txt)
                    if (
                        txt.lower() == target.lower() or
                        norm_txt == target_n or
                        (target_n and target_n in norm_txt) or
                        (norm_txt and norm_txt in target_n)
                    ):
                        idx = i; break
            if idx is None:
                logging.getLogger(__name__).error("Unknown tab: %s", target)
                win.close()
                return 1
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
    if cmd == "mode-verify":
        return cmd_mode_verify(args)
    if cmd == "spiral-measure":
        return cmd_spiral_measure(args)
    if cmd == "media-measure":
        return cmd_media_measure(args)
    if cmd == "vr-stream":
        return cmd_vr_stream(args)
    if cmd == "vr-test":
        return cmd_vr_test(args)
    if cmd == "themebank":
        return cmd_themebank(args)

    parser.print_help()
    return 2


if __name__ == "__main__":  # Allow direct module execution
    raise SystemExit(main())
