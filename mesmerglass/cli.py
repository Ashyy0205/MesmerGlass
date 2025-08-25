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
    p_ui.add_argument("--vol1", type=int, default=None, help="Set primary audio volume percent (0-100)")
    p_ui.add_argument("--vol2", type=int, default=None, help="Set secondary audio volume percent (0-100)")
    p_ui.add_argument("--displays", choices=["all", "primary", "none"], default=None, help="Quick-select displays")
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


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging before doing any work
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
    if cmd == "session":
        import json as _json
        try:
            pack = load_session_pack(args.load)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to load session pack: %s", e)
            return 1
        summary_mode = (not args.print and not args.apply) or args.summary
        if args.print:
            print(_json.dumps(pack.to_canonical_dict(), separators=(",", ":"), ensure_ascii=False))
            return 0
        if args.apply:
            # Headless apply (no event loop spin)
            from PyQt6.QtWidgets import QApplication
            from .ui.launcher import Launcher
            app = QApplication.instance() or QApplication([])
            win = Launcher("MesmerGlass", enable_device_sync_default=False)
            try:
                if hasattr(win, "apply_session_pack"):
                    win.apply_session_pack(pack)
            except Exception as e:
                logging.getLogger(__name__).error("Error applying session pack: %s", e)
                return 1
            status = {"pack": pack.name, "text": getattr(win, "text", None), "buzz_intensity": getattr(win, "buzz_intensity", None)}
            print(_json.dumps(status, ensure_ascii=False))
            try:
                win.close()
            except Exception:
                pass
            return 0
        if summary_mode:
            ti = f"{len(pack.text.items)} text" if pack.text.items else "0 text"
            ps = f"{len(pack.pulse.stages)} stages" if pack.pulse.stages else "0 stages"
            print(f"SessionPack '{pack.name}' v{pack.version} — {ti}, {ps}")
            return 0
    if cmd == "state":
        from .content.loader import load_session_state, save_session_state
        from PyQt6.QtWidgets import QApplication
        from .ui.launcher import Launcher
        target = args.file
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
        if args.apply:
            # Headless apply (no event loop spin)
            from PyQt6.QtWidgets import QApplication
            from .ui.launcher import Launcher
            app = QApplication.instance() or QApplication([])
            win = Launcher("MesmerGlass", enable_device_sync_default=False)
            try:
                if hasattr(win, "apply_session_pack"):
                    win.apply_session_pack(pack)
            except Exception as e:
                logging.getLogger(__name__).error("Error applying session pack: %s", e)
                return 1
            status = {"pack": pack.name, "text": getattr(win, "text", None), "buzz_intensity": getattr(win, "buzz_intensity", None)}
            print(_json.dumps(status, ensure_ascii=False))
            try:
                win.close()
            except Exception:
                pass
            return 0
        if summary_mode:
            ti = f"{len(pack.text.items)} text" if pack.text.items else "0 text"
            ps = f"{len(pack.pulse.stages)} stages" if pack.pulse.stages else "0 stages"
            print(f"SessionPack '{pack.name}' v{pack.version} — {ti}, {ps}")
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
        # Note: use no-show by default to avoid window popups in CI.
        app = QApplication.instance() or QApplication([])
        win = Launcher(
            "MesmerGlass",
            enable_device_sync_default=False,  # disable device sync for CLI actions to keep tests deterministic
            layout_mode=getattr(args, "layout", "tabbed"),  # pass through layout selection
        )
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
                return 1
            win.tabs.setCurrentIndex(idx)
            logging.getLogger(__name__).info("Selected tab: %s", win.tabs.tabText(idx))
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
            status = {
                "tab": win.tabs.tabText(win.tabs.currentIndex()),
                "running": bool(getattr(win, "running", False)),
                "text": getattr(win, "text", None),
                "fx_mode": getattr(win, "fx_mode", None),
                "fx_intensity": getattr(win, "fx_intensity", None),
                "vol1": getattr(win, "vol1", None),
                "vol2": getattr(win, "vol2", None),
                "displays_checked": sum(1 for i in range(win.list_displays.count()) if win.list_displays.item(i).checkState() != 0),
            }
            print(json.dumps(status))
        # Spin event loop briefly; a single-shot QTimer quits after timeout
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
