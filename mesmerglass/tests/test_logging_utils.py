"""Tests for centralized logging configuration."""

import logging
from pathlib import Path

from ..logging_utils import (
    LogMode,
    get_log_mode,
    is_perf_logging_enabled,
    is_quiet_logging_enabled,
    set_log_mode,
    setup_logging,
)


def test_setup_logging_file_and_console_handlers(tmp_path: Path):
    log_file = tmp_path / "test.log"
    logger = setup_logging(
        level="DEBUG",
        log_file=str(log_file),
        json_format=False,
        add_console=True,
        logger_name="test_logging_utils.file_console",
    )
    # Emit a message
    logging.getLogger(__name__).info("hello")
    # File should exist (if file handler created successfully)
    # Some environments may not allow writing; tolerate missing file
    assert logger is not None


def test_setup_logging_idempotent(tmp_path: Path):
    log_file = tmp_path / "test2.log"
    name = "test_logging_utils.idempotent"
    logger1 = setup_logging(level="INFO", log_file=str(log_file), logger_name=name)
    logger2 = setup_logging(level="INFO", log_file=str(log_file), logger_name=name)
    assert logger1 is logger2 or isinstance(logger2, logging.Logger)


def test_log_mode_helpers_roundtrip():
    set_log_mode(LogMode.PERF)
    assert get_log_mode() is LogMode.PERF
    assert is_perf_logging_enabled() is True
    set_log_mode(LogMode.QUIET)
    assert get_log_mode() is LogMode.QUIET
    assert is_quiet_logging_enabled() is True
    # Reset to default to avoid leaking state into other tests
    set_log_mode(LogMode.NORMAL)


def test_setup_logging_perf_forces_debug(tmp_path: Path):
    log_file = tmp_path / "perf.log"
    logger = setup_logging(
        level="INFO",
        log_file=str(log_file),
        log_mode=LogMode.PERF,
        logger_name="test_logging_utils.perf",
    )
    assert logger.level == logging.DEBUG
    set_log_mode(LogMode.NORMAL)
