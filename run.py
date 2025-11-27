"""Legacy entry point for launching the MesmerGlass GUI or CLI."""

from __future__ import annotations

from pathlib import Path
import sys
import os


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    
    # Check for --debug flag BEFORE any imports that use logging
    if "--debug" in args:
        os.environ["MESMERGLASS_DEBUG"] = "1"
        args.remove("--debug")
    
    if args:
        candidate = Path(args[0])
        if candidate.exists() and candidate.is_file():
            if len(args) == 1:
                from mesmerglass.cli import run_instruction_file

                return run_instruction_file(str(candidate))
            from mesmerglass.cli import main as cli_main

            return cli_main(["instructions", *args])
        from mesmerglass.cli import main as cli_main

        return cli_main(args)
    _launch_gui()
    return 0


def _launch_gui() -> None:
    from mesmerglass.app import run as run_gui

    run_gui()
    
    if args:
        candidate = Path(args[0])
        if candidate.exists() and candidate.is_file():
            if len(args) == 1:
                from mesmerglass.cli import run_instruction_file

                return run_instruction_file(str(candidate))
            from mesmerglass.cli import main as cli_main

            return cli_main(["instructions", *args])
        from mesmerglass.cli import main as cli_main

        return cli_main(args)
    _launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
