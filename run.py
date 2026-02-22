"""Legacy entry point for launching the MesmerGlass GUI or CLI."""

from __future__ import annotations

from pathlib import Path
import sys
import os


def _maybe_reexec_into_venv() -> None:
    """Ensure we launch the GUI under the project's venv when present.

    On Windows, accidentally running under the Microsoft Store Python can lead to
    native crashes (e.g., Qt/OpenGL access violations) due to mismatched wheels.
    """
    if getattr(sys, "frozen", False):
        return
    if os.environ.get("MESMERGLASS_NO_REEXEC", "0") in ("1", "true", "True", "yes"):
        return
    if os.environ.get("MESMERGLASS_REEXEC", "0") in ("1",):
        return

    if os.name != "nt":
        return

    project_root = Path(__file__).resolve().parent
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return

    exe = str(Path(sys.executable).resolve())
    exe_lower = exe.lower()
    venv_lower = str(venv_python).lower()
    # Already in the intended venv.
    if exe_lower == venv_lower or "\\.venv\\scripts\\python.exe" in exe_lower:
        return

    os.environ["MESMERGLASS_REEXEC"] = "1"
    os.execv(str(venv_python), [str(venv_python), str(project_root / "run.py"), *sys.argv[1:]])


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    force_gui = False
    
    # Check for --debug flag BEFORE any imports that use logging
    if "--debug" in args:
        os.environ["MESMERGLASS_DEBUG"] = "1"
        args.remove("--debug")

    # Special GUI test harness: show a live volume panel inside the normal app.
    if "--volume-test" in args:
        args.remove("--volume-test")
        os.environ["MESMERGLASS_VOLUME_TEST"] = "1"
        force_gui = True
    
    if args and not force_gui:
        candidate = Path(args[0])
        if candidate.exists() and candidate.is_file():
            if len(args) == 1:
                from mesmerglass.cli import run_instruction_file

                return run_instruction_file(str(candidate))
            from mesmerglass.cli import main as cli_main

            return cli_main(["instructions", *args])
        from mesmerglass.cli import main as cli_main

        return cli_main(args)

    # GUI path: prefer running under the workspace venv if available.
    _maybe_reexec_into_venv()
    _launch_gui()
    return 0


def _launch_gui() -> None:
    from mesmerglass.app import run as run_gui

    run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
