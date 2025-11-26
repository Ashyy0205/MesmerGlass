"""Tests for spiral text sync policy in PlaybackEditor."""

from PyQt6 import QtWidgets
import pytest

from mesmerglass.ui.editors import playback_editor
from mesmerglass.ui.editors.playback_editor import PlaybackEditor


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app


class DummyDirector:
    """Minimal stub exposing the text API touched by the editor."""

    def __init__(self):
        self.enabled = True
        self.opacity = 1.0
        self.mode_history = []
        self.sync_args = None

    def set_enabled(self, value):
        self.enabled = value

    def set_all_split_mode(self, mode):
        self.mode_history.append(mode)

    def configure_sync(self, sync_with_media, frames_per_text):
        self.sync_args = {
            "sync": sync_with_media,
            "frames": frames_per_text,
        }


@pytest.fixture()
def editor(qapp, monkeypatch):
    monkeypatch.setattr(playback_editor, "PREVIEW_AVAILABLE", False)
    monkeypatch.setattr(
        playback_editor.QMessageBox,
        "question",
        lambda *_, **__: QtWidgets.QMessageBox.StandardButton.No,
    )
    dlg = PlaybackEditor()
    stub = DummyDirector()
    dlg.text_director = stub
    yield dlg
    dlg.close()


def test_carousel_forces_manual(editor):
    mode_combo = editor.text_mode_combo
    assert mode_combo.currentIndex() == 0
    assert editor.text_sync_check.isChecked()
    assert not editor.text_speed_slider.isEnabled()

    mode_combo.setCurrentIndex(1)

    assert not editor.text_sync_check.isEnabled()
    assert not editor.text_sync_check.isChecked()
    assert editor.text_speed_slider.isEnabled()

    mode_combo.setCurrentIndex(0)

    assert editor.text_sync_check.isEnabled()
    assert editor.text_sync_check.isChecked()


def test_manual_slider_updates_director(editor):
    editor.text_mode_combo.setCurrentIndex(1)
    slider = editor.text_speed_slider
    slider.setValue(80)

    editor._apply_text_sync_settings()

    assert editor.text_director.sync_args is not None
    assert not editor.text_director.sync_args["sync"]
    assert editor.text_director.sync_args["frames"] > 0
