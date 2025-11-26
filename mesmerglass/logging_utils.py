"""Centralized logging configuration for MesmerGlass.

Provides helpers to set up console and rotating file handlers with a
consistent format. Intended to be called from CLI (run.py / cli.py)
and early in GUI startup.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


DEFAULT_LOG_FILENAME = "mesmerglass.log"


class LogMode(str, Enum):
    """Logging presets that affect verbosity targets."""

    QUIET = "quiet"
    NORMAL = "normal"
    PERF = "perf"


_LOG_MODE: LogMode = LogMode.NORMAL
_SPIRAL_TRACE_FLAG = "MESMERGLASS_SPIRAL_TRACE"


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


def _parse_log_mode(mode: LogMode | str | None) -> LogMode:
    if mode is None:
        return LogMode.NORMAL
    if isinstance(mode, LogMode):
        return mode
    try:
        return LogMode(mode.lower())
    except Exception:
        return LogMode.NORMAL


def set_log_mode(mode: LogMode | str | None) -> LogMode:
    """Persist the active log mode for other modules to query later."""

    global _LOG_MODE
    _LOG_MODE = _parse_log_mode(mode)
    return _LOG_MODE


def get_log_mode() -> LogMode:
    return _LOG_MODE


def is_perf_logging_enabled() -> bool:
    return _LOG_MODE is LogMode.PERF


def is_quiet_logging_enabled() -> bool:
    return _LOG_MODE is LogMode.QUIET


def _spiral_trace_allowed() -> bool:
    raw = os.environ.get(_SPIRAL_TRACE_FLAG, "")
    if raw.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return is_perf_logging_enabled()


class _SpiralTraceFilter(logging.Filter):
    """Drops spiral trace chatter unless explicitly enabled."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            message = record.getMessage()
        except Exception:
            return True
        if ("[spiral.trace]" in message or "[spiral.debug]" in message) and not _spiral_trace_allowed():
            return False
        return True


_SPIRAL_TRACE_FILTER = _SpiralTraceFilter()


def _ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _resolve_level(level: str | int) -> int:
    if isinstance(level, str):
        normalized = level.upper()
        return getattr(logging, normalized, logging.INFO)
    return int(level)


def setup_logging(
    *,
    level: str | int = "INFO",
    log_file: Optional[str | Path] = None,
    json_format: bool = False,
    logger_name: Optional[str] = None,
    log_mode: LogMode | str | None = None,
    add_console: bool = True,
) -> logging.Logger:
    """Configure logging for the application.

    - level: str or int (DEBUG/INFO/WARNING/ERROR)
    - log_file: path for rotating file handler (default: per-user dir)
    - json_format: if True, use a JSON-like key=value single-line format
    - logger_name: root logger by default; can scope to a sub-logger
    - log_mode: optional preset (quiet/normal/perf) that adjusts verbosity targets
    - add_console: add a console StreamHandler in addition to file handler
    """
    resolved_level = _resolve_level(level)
    mode = set_log_mode(log_mode) if log_mode is not None else get_log_mode()
    if mode is LogMode.PERF and resolved_level > logging.DEBUG:
        resolved_level = logging.DEBUG
    console_level = resolved_level
    if mode is LogMode.QUIET:
        console_level = max(logging.WARNING, resolved_level)

    # Pick logger
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    if all(not isinstance(f, _SpiralTraceFilter) for f in logger.filters):
        logger.addFilter(_SPIRAL_TRACE_FILTER)

    # Avoid duplicating handlers if called multiple times
    if not logger.handlers:
        logger.setLevel(resolved_level)

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
            file_handler.setLevel(resolved_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # If file handler fails (e.g., permissions), continue with console only
            pass

        # Console handler
        if add_console:
            console = logging.StreamHandler()
            console.setLevel(console_level)
            console.setFormatter(formatter)
            logger.addHandler(console)
    else:
        # If handlers already exist, just raise the level if needed
        logger.setLevel(resolved_level)
        for handler in logger.handlers:
            if isinstance(handler, (logging.handlers.RotatingFileHandler, logging.FileHandler)):
                handler.setLevel(resolved_level)
            elif isinstance(handler, logging.StreamHandler):
                handler.setLevel(console_level)
            else:
                handler.setLevel(resolved_level)

    return logger


class BurstSampler:
    """Small helper that coalesces bursts of identical log events.

    Call :meth:`record` for every event. When the configured interval elapses,
    the sampler returns the number of events that occurred within that window
    so callers can emit a single summary INFO line instead of thousands of
    per-event entries.
    """

    def __init__(self, interval_s: float = 2.0) -> None:
        self.interval_s = max(0.1, float(interval_s))
        self._next_flush = time.monotonic() + self.interval_s
        self._count = 0

    def record(self, amount: int = 1) -> Optional[int]:
        """Register *amount* events; return the total if window elapsed."""

        self._count += max(0, amount)
        now = time.monotonic()
        if now >= self._next_flush:
            total = self._count
            self._count = 0
            # Align the next flush with ``now`` so long bursts reset quickly.
            self._next_flush = now + self.interval_s
            return total
        return None

    def flush(self) -> int:
        """Force-flush and return the accumulated count."""

        total = self._count
        self._count = 0
        self._next_flush = time.monotonic() + self.interval_s
        return total


@dataclass
class PerfRecord:
    """Single timing span captured by :class:`PerfTracer`."""

    name: str
    category: str
    duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "duration_ms": round(self.duration_ms, 3),
            "metadata": self.metadata or {},
        }


class _PerfSpan:
    __slots__ = ("_tracer", "_name", "_category", "_metadata", "_start_ns", "_active")

    def __init__(self, tracer: "PerfTracer", name: str, category: str, metadata: dict[str, Any]) -> None:
        self._tracer = tracer
        self._name = name
        self._category = category
        self._metadata = metadata
        self._start_ns: Optional[int] = None
        self._active = tracer.enabled

    def __enter__(self) -> "_PerfSpan":  # pragma: no cover - trivial
        if self._active:
            self._start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:  # pragma: no cover - trivial
        if not self._active or self._start_ns is None:
            return
        duration_ms = (time.perf_counter_ns() - self._start_ns) / 1_000_000.0
        self._tracer._records.append(  # pylint: disable=protected-access
            PerfRecord(self._name, self._category, duration_ms, dict(self._metadata))
        )

    def annotate(self, **metadata: Any) -> "_PerfSpan":
        if metadata:
            self._metadata.update(metadata)
        return self


class _NoopSpan:
    __slots__: tuple[str, ...] = ()

    def __enter__(self) -> "_NoopSpan":  # pragma: no cover - trivial
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:  # pragma: no cover - trivial
        return None

    def annotate(self, **_metadata: Any) -> "_NoopSpan":  # pragma: no cover - trivial
        return self


_NOOP_SPAN = _NoopSpan()


class PerfTracer:
    """Lightweight timeline collector for cue-level diagnostics."""

    def __init__(self, label: str, *, enabled: Optional[bool] = None) -> None:
        self.label = label
        self.enabled = is_perf_logging_enabled() if enabled is None else bool(enabled)
        self._records: list[PerfRecord] = []
        self._context: dict[str, Any] = {}

    @staticmethod
    def noop_span() -> _NoopSpan:
        return _NOOP_SPAN

    def set_context(self, **metadata: Any) -> None:
        if metadata:
            self._context.update(metadata)

    def span(
        self,
        name: str,
        *,
        category: str = "misc",
        metadata: Optional[dict[str, Any]] = None,
    ) -> _PerfSpan | _NoopSpan:
        if not self.enabled:
            return _NOOP_SPAN
        return _PerfSpan(self, name, category, metadata or {})

    def snapshot(self) -> dict[str, Any]:
        spans = [record.to_dict() for record in self._records]
        by_category: dict[str, float] = {}
        for record in self._records:
            by_category[record.category] = by_category.get(record.category, 0.0) + record.duration_ms
        return {
            "label": self.label,
            "context": dict(self._context),
            "spans": spans,
            "categories": {k: round(v, 3) for k, v in by_category.items()},
            "span_count": len(spans),
        }

    def top_spans(self, *, limit: int = 10, threshold_ms: float = 0.0) -> list[dict[str, Any]]:
        filtered = [r for r in self._records if r.duration_ms >= threshold_ms]
        filtered.sort(key=lambda rec: rec.duration_ms, reverse=True)
        return [rec.to_dict() for rec in filtered[:limit]]

    def clear(self) -> None:
        """Drop all recorded spans but keep context metadata intact."""

        self._records.clear()

    def consume(self) -> dict[str, Any]:
        """Return a snapshot and immediately clear recorded spans."""

        snapshot = self.snapshot()
        self.clear()
        return snapshot

    def dump_table(
        self,
        *,
        limit: int = 10,
        threshold_ms: float = 0.0,
    ) -> list[str]:
        """Return human-readable table lines for the longest spans."""

        rows = self.top_spans(limit=limit, threshold_ms=threshold_ms)
        width = max((len(r["name"]) for r in rows), default=4)
        lines = [f"Span{' ' * (width - 4)} | Category | Duration (ms) | Metadata"]
        lines.append("-" * (len(lines[0]) + 8))
        for row in rows:
            meta = json.dumps(row.get("metadata", {}), ensure_ascii=False)
            lines.append(
                f"{row['name']:<{width}} | {row['category']:<8} | {row['duration_ms']:>11.2f} | {meta}"
            )
        return lines
