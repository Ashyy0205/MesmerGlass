"""Centralized logging configuration for MesmerGlass.

Provides helpers to set up console and rotating file handlers with a
consistent format. Intended to be called from CLI (run.py / cli.py)
and early in GUI startup.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional


DEFAULT_LOG_FILENAME = "mesmerglass.log"


def get_default_log_dir() -> Path:
    """Return a suitable per-user log directory.

    On Windows, prefer %LOCALAPPDATA%/MesmerGlass. Else use ~/.mesmerglass.
    Falls back to cwd if neither is writable.
    """
    # Windows: %LOCALAPPDATA%\MesmerGlass
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        p = Path(local_appdata) / "MesmerGlass"
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    # Cross-platform fallback: ~/.mesmerglass
    home = Path.home()
    p = home / ".mesmerglass"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        # Last resort: current directory
        return Path.cwd()


def get_default_log_path() -> Path:
    """Default full path to the log file."""
    return get_default_log_dir() / DEFAULT_LOG_FILENAME


def _ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def setup_logging(
    *,
    level: str | int = "INFO",
    log_file: Optional[str | Path] = None,
    json_format: bool = False,
    logger_name: Optional[str] = None,
    add_console: bool = True,
) -> logging.Logger:
    """Configure logging for the application.

    - level: str or int (DEBUG/INFO/WARNING/ERROR)
    - log_file: path for rotating file handler (default: per-user dir)
    - json_format: if True, use a JSON-like key=value single-line format
    - logger_name: root logger by default; can scope to a sub-logger
    - add_console: add a console StreamHandler in addition to file handler
    """
    # Resolve level
    if isinstance(level, str):
        level = level.upper()
        level = getattr(logging, level, logging.INFO)
    else:
        level = int(level)

    # Pick logger
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()

    # Avoid duplicating handlers if called multiple times
    if not logger.handlers:
        logger.setLevel(level)

        # Formatter
        if json_format:
            fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
        else:
            fmt = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
        datefmt = "%H:%M:%S"
        formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

        # File handler (rotating)
        log_path = Path(log_file) if log_file else get_default_log_path()
        _ensure_parent(log_path)
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # If file handler fails (e.g., permissions), continue with console only
            pass

        # Console handler
        if add_console:
            console = logging.StreamHandler()
            console.setLevel(level)
            console.setFormatter(formatter)
            logger.addHandler(console)
    else:
        # If handlers already exist, just raise the level if needed
        logger.setLevel(level)

    return logger
