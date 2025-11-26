"""Integration coverage for CueEditor session mode + audio hydration."""

import sys
import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

from mesmerglass.session.cue import AudioRole
from mesmerglass.ui.editors.cue_editor import CueEditor
from mesmerglass.ui.cue_editor_dialog import CueEditorDialog


@pytest.fixture(scope="module")
def qt_app():
    """Provide a shared QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_cue_editor_session_mode_hydrates_audio(qt_app):
    """CueEditor session mode should hydrate playback pool and audio roles."""
    session_data = {
        "version": "1.0",
        "playbacks": {
            "gentle_spiral": {"visual_type": "spiral"},
            "intense_spiral": {"visual_type": "spiral"}
        },
        "cuelists": {
            "test_cuelist": {
                "name": "Test Cuelist",
                "cues": [
                    {
                        "name": "Test Cue",
                        "duration_seconds": 12,
                        "selection_mode": "on_cue_start",
                        "playback_pool": [
                            {"playback": "gentle_spiral", "weight": 2.0,
                             "min_duration_s": 5.0, "max_duration_s": 10.0}
                        ],
                        "audio": {
                            "hypno": {
                                "file": "audio/hypno.wav",
                                "volume": 0.8,
                                "duration": 18.4
                            },
                            "background": {
                                "file": "audio/bg.wav",
                                "volume": 0.35,
                                "loop": True,
                                "duration": 60.0
                            }
                        }
                    }
                ]
            }
        }
    }

    editor = CueEditor(session_data=session_data, cuelist_key="test_cuelist", cue_index=0)

    assert editor.is_session_mode
    assert editor.playback_list.count() == 1

    label = editor.playback_list.item(0).text()
    assert "weight" in label and "5-10s" in label

    hypno_state = editor._audio_state[AudioRole.HYPNO]
    bg_state = editor._audio_state[AudioRole.BACKGROUND]
    assert hypno_state["file"].endswith("audio/hypno.wav")
    assert bg_state["file"].endswith("audio/bg.wav")
    assert editor.duration_spin.value() == 18  # rounded suggestion
    assert "Suggested duration" in editor.duration_hint_label.text()

    editor.deleteLater()


def test_cue_editor_background_warning_when_missing_loop(qt_app):
    """Background tracks that disable loop should still mark editor modified when toggled."""
    cue_data = {
        "name": "No Loop Cue",
        "duration_seconds": 30,
        "playback_pool": [
            {"playback": "demo.json", "weight": 1.0}
        ],
        "audio": {
            "hypno": {"file": "audio/h.wav", "volume": 0.9, "duration": 30.0},
            "background": {"file": "audio/bg.wav", "volume": 0.2, "loop": False}
        }
    }

    editor = CueEditor(cue_data=cue_data)
    assert not editor.is_modified
    assert editor._audio_state[AudioRole.BACKGROUND]["loop"] is False
    editor._on_volume_changed(AudioRole.BACKGROUND, 40)
    assert editor.is_modified
    assert editor._audio_state[AudioRole.BACKGROUND]["volume"] == pytest.approx(0.4)
    editor.deleteLater()


def test_cue_editor_preferred_size_honors_small_screen():
    """Preferred size clamps to available geometry so Save/Cancel remain visible."""
    preferred = CueEditor._calculate_preferred_size(QSize(1500, 800))
    assert preferred.width() == 900
    assert preferred.height() == 680

    tiny_screen = QSize(1024, 640)
    preferred_tiny = CueEditor._calculate_preferred_size(tiny_screen)
    assert preferred_tiny.width() <= tiny_screen.width()
    assert preferred_tiny.height() <= tiny_screen.height()


def test_cue_editor_dialog_preferred_size_matches_editor_logic():
    """Session dialog uses the same responsive heuristics for cramped displays."""
    tablet_screen = QSize(1366, 768)
    preferred = CueEditorDialog._calculate_preferred_size(tablet_screen)
    assert preferred.width() <= 860
    assert preferred.height() <= 648

    unspecified = CueEditorDialog._calculate_preferred_size(None)
    assert unspecified == QSize(860, 700)
