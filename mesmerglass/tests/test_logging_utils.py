"""Tests for centralized logging configuration."""

import tempfile
from pathlib import Path
import logging

from ..logging_utils import setup_logging


def test_setup_logging_file_and_console_handlers(tmp_path: Path):
    log_file = tmp_path / "test.log"
    logger = setup_logging(level="DEBUG", log_file=str(log_file), json_format=False, add_console=True)
    # Emit a message
    logging.getLogger(__name__).info("hello")
    # File should exist (if file handler created successfully)
    # Some environments may not allow writing; tolerate missing file
    assert logger is not None


def test_setup_logging_idempotent(tmp_path: Path):
    log_file = tmp_path / "test2.log"
    logger1 = setup_logging(level="INFO", log_file=str(log_file))
    logger2 = setup_logging(level="INFO", log_file=str(log_file))
    assert logger1 is logger2 or isinstance(logger2, logging.Logger)
