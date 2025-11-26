"""PlaybackEditor text sync policy tests."""

import pytest

pytest.importorskip("PyQt6")

from mesmerglass.ui.editors import playback_editor


@pytest.fixture(autouse=True)
def disable_preview(monkeypatch):
    """Avoid heavy preview setup during UI tests."""
    monkeypatch.setattr(playback_editor, "PREVIEW_AVAILABLE", False)


@pytest.fixture()
def editor(qtbot):
    dlg = playback_editor.PlaybackEditor()
    qtbot.addWidget(dlg)
    return dlg


def test_carousel_forces_manual_speed(editor):
    editor.text_mode_combo.setCurrentIndex(1)  # Scrolling carousel

    assert not editor.text_sync_check.isEnabled()
    assert not editor.text_sync_check.isChecked()
    assert editor.text_speed_slider.isEnabled()


def test_centered_mode_restores_preference(editor):
    editor.text_sync_check.setChecked(False)
    editor.text_mode_combo.setCurrentIndex(1)  # Force carousel

    assert not editor.text_sync_check.isEnabled()

    editor.text_mode_combo.setCurrentIndex(0)
    assert editor.text_sync_check.isEnabled()
    assert not editor.text_sync_check.isChecked()

    editor.text_sync_check.setChecked(True)
    editor.text_mode_combo.setCurrentIndex(1)
    editor.text_mode_combo.setCurrentIndex(0)
    assert editor.text_sync_check.isChecked()


def test_export_never_sets_sync_for_carousel(editor):
    editor.text_mode_combo.setCurrentIndex(0)
    editor.text_sync_check.setChecked(True)
    centered = editor._build_config_dict()
    assert centered["text"]["sync_with_media"] is True

    editor.text_mode_combo.setCurrentIndex(1)
    carousel = editor._build_config_dict()
    assert carousel["text"]["sync_with_media"] is False
