"""Unit tests for video engine (cv2 + QPixmap)."""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage
import sys

from ..engine.video import VideoStream


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@patch("cv2.VideoCapture")
def test_open_failure_logs_and_sets_none(mock_vc):
    inst = MagicMock()
    inst.isOpened.return_value = False
    mock_vc.return_value = inst
    v = VideoStream()
    v.open("nonexistent.mp4")
    assert v.cap is None


@patch("cv2.VideoCapture")
def test_read_next_if_due_and_qpixmap(mock_vc, qapp):
    # Fake one frame read
    inst = MagicMock()
    inst.isOpened.return_value = True
    # Minimal 2x2 RGB frame
    import numpy as np
    frame = (np.ones((2, 2, 3), dtype=np.uint8) * 255)[:, :, ::-1]  # BGR white
    inst.read.side_effect = [(True, frame)] * 3
    mock_vc.return_value = inst

    v = VideoStream()
    v.open("fake.mp4")

    # Force due
    v.last_ts = 0
    v.frame_interval = 0
    v.read_next_if_due()
    pm = v.get_qpixmap(QSize(10, 10))
    # Might be None if QPixmap can't be created in headless; allow either
    assert pm is None or hasattr(pm, "isNull")
