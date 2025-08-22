"""Deprecated entry point.

Historically ``python run.py`` launched the GUI and exposed a few ad-hoc
subcommands (server, test). The canonical interface is now the argparse CLI
exposed via ``python -m mesmerglass``. This file remains as a *shim* so
external docs / scripts do not break immediately. It will be removed in a
future minor release.
"""

from __future__ import annotations

import sys, warnings

def _main(argv: list[str] | None = None) -> int:
    # Emit a deprecation warning (always) – users should migrate.
    warnings.simplefilter("default", DeprecationWarning)
    warnings.warn(
        "run.py is deprecated; use 'python -m mesmerglass run' (GUI) or other subcommands. This shim will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Delegate entirely to the real CLI implementation.
    from mesmerglass.cli import main as cli_main  # local import keeps import cost minimal
    # If user ran e.g. `python run.py` with no args we want GUI (equivalent to 'run').
    args = list(argv or sys.argv[1:])
    if not args:
        args = ["run"]  # default command in new CLI
    return cli_main(args)

if __name__ == "__main__":  # pragma: no cover - exercised via subprocess in tests
    raise SystemExit(_main())
