"""Regression tests for ThemeBank diagnostics and readiness gating."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from mesmerglass.content.theme import ThemeConfig
from mesmerglass.content.themebank import ThemeBank, ThemeBankStatus
from mesmerglass.session.runner import SessionRunner
from mesmerglass.ui.session_runner_tab import SessionRunnerTab


MINI_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDAT"
    b"\x08\xd7c````\x00\x00\x00\x05\x00\x01\xef\x82=\xb7\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:  # pragma: no cover - only runs once per session
        app = QApplication([])
    return app


def _write_sample_png(path: Path) -> Path:
    path.write_bytes(MINI_PNG)
    return path


def _themebank_status(ready: bool, *, total_images: int = 1, total_videos: int = 0) -> ThemeBankStatus:
    return ThemeBankStatus(
        themes_total=1,
        active_primary=0,
        active_alternate=None,
        total_images=total_images,
        total_videos=total_videos,
        cached_images=0,
        pending_loads=0,
        ready=ready,
        ready_reason="ok" if ready else "missing images",
        last_image_path=None,
        last_video_path=None,
    )


def test_themebank_status_ready(tmp_path):
    image_dir = tmp_path / "Images"
    image_dir.mkdir()
    _write_sample_png(image_dir / "sample.png")

    theme = ThemeConfig(
        name="Test",
        enabled=True,
        image_path=[str(image_dir / "sample.png")],
        animation_path=[],
        font_path=[],
        text_line=[],
    )
    bank = ThemeBank(themes=[theme], root_path=tmp_path, image_cache_size=8)
    bank.set_active_themes(primary_index=1)
    try:
        status = bank.get_status()
        assert status.ready is True
        assert status.total_images == 1
    finally:
        bank.shutdown()


def test_themebank_cli_stats(tmp_path):
    media_dir = tmp_path / "Images"
    media_dir.mkdir()
    _write_sample_png(media_dir / "sample.png")

    media_bank_path = tmp_path / "media_bank.json"
    media_bank_path.write_text(
        json.dumps(
            [
                {
                    "name": "Images",
                    "path": str(media_dir),
                    "type": "images",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mesmerglass",
            "themebank",
            "stats",
            "--media-bank",
            str(media_bank_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ready"] is True
    assert payload["total_images"] == 1


def test_session_runner_themebank_gate(monkeypatch):
    runner = object.__new__(SessionRunner)
    runner.logger = logging.getLogger("session-runner-test")

    class FakeBank:
        def __init__(self, status: ThemeBankStatus):
            self._status = status

        def ensure_ready(self, **_: object) -> ThemeBankStatus:
            return self._status

    class FakeVD:
        def __init__(self, bank):
            self.theme_bank = bank

    ready_runner = object.__new__(SessionRunner)
    ready_runner.logger = runner.logger
    ready_runner.visual_director = FakeVD(FakeBank(_themebank_status(True)))
    assert ready_runner._ensure_theme_bank_ready() is True

    runner.visual_director = FakeVD(FakeBank(_themebank_status(False)))
    assert runner._ensure_theme_bank_ready() is False


def test_session_runner_tab_blocks_when_themebank_missing(qapp):
    class FakeBank:
        def __init__(self, status: ThemeBankStatus):
            self._status = status

        def ensure_ready(self, **_: object) -> ThemeBankStatus:
            return self._status

    class FakeVD:
        def __init__(self, bank):
            self.theme_bank = bank

    unready_bank = FakeBank(_themebank_status(False))
    ready_bank = FakeBank(_themebank_status(True))

    tab = SessionRunnerTab(
        parent=None,
        visual_director=FakeVD(unready_bank),
        audio_engine=None,
        compositor=None,
        display_tab=None,
    )
    try:
        assert tab._check_theme_bank_ready() is False
        assert "ThemeBank not ready" in tab.status_label.text()
        tab.visual_director.theme_bank = ready_bank
        assert tab._check_theme_bank_ready() is True
    finally:
        tab.deleteLater()