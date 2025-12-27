"""Platform-specific paths and first-run helpers.

Goal: keep user-created data (sessions, etc.) out of temp / install folders.

We intentionally avoid extra dependencies (e.g. platformdirs) and rely on
standard Windows environment variables.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def is_windows() -> bool:
    return os.name == "nt"


def is_frozen() -> bool:
    # PyInstaller sets sys.frozen; other freezers may too.
    return bool(getattr(sys, "frozen", False))


def get_user_data_dir(app_name: str = "MesmerGlass") -> Path:
    """Return a persistent per-user data directory.

    Windows: %APPDATA%\\MesmerGlass
    """
    if is_windows():
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name

    # Fallback for other OSes (not currently a primary target).
    return Path.home() / f".{app_name.lower()}"


def get_sessions_dir(app_name: str = "MesmerGlass") -> Path:
    return get_user_data_dir(app_name) / "sessions"


def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ps_single_quote(value: str) -> str:
    # PowerShell single-quoted string escaping: '' inside '...'
    return "'" + value.replace("'", "''") + "'"


def ensure_windows_start_menu_shortcut(
    *,
    app_name: str = "MesmerGlass",
    shortcut_name: str | None = None,
) -> None:
    """Create a Start Menu shortcut for frozen Windows builds.

    Creates:
      %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\<app_name>\\<shortcut>.lnk

    Idempotent: no-op if it already exists.
    """
    if not is_windows() or not is_frozen():
        return

    try:
        start_menu = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        programs_dir = start_menu / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        group_dir = programs_dir / app_name
        ensure_dir(group_dir)

        if shortcut_name is None:
            shortcut_name = app_name

        lnk_path = group_dir / f"{shortcut_name}.lnk"
        if lnk_path.exists():
            return

        exe_path = Path(sys.executable)
        target = str(exe_path)
        working_dir = str(exe_path.parent)
        icon = f"{target},0"

        ps = (
            "$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut({_ps_single_quote(str(lnk_path))}); "
            f"$Shortcut.TargetPath = {_ps_single_quote(target)}; "
            f"$Shortcut.WorkingDirectory = {_ps_single_quote(working_dir)}; "
            f"$Shortcut.IconLocation = {_ps_single_quote(icon)}; "
            "$Shortcut.Save();"
        )

        startupinfo = None
        creationflags = 0
        if is_windows():
            # Hide the PowerShell window in GUI apps.
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        if lnk_path.exists():
            logger.info("Start Menu shortcut created: %s", lnk_path)
        else:
            logger.warning("Start Menu shortcut creation attempted but link missing: %s", lnk_path)

    except Exception as exc:
        # Never break app startup over shortcut creation.
        logger.warning("Start Menu shortcut creation failed: %s", exc)
