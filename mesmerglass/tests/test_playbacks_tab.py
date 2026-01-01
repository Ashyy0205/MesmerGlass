"""Unit tests for the Playbacks tab delete behavior."""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QMessageBox

from mesmerglass.ui.tabs.playbacks_tab import PlaybacksTab


class DummyMainApp(QWidget):
    """Minimal object providing what PlaybacksTab expects."""

    def __init__(self):
        super().__init__()
        self._dirty = False

    def mark_session_dirty(self):
        self._dirty = True


def _session_with_playbacks():
    return {
        "playbacks": {
            "a": {"name": "A", "description": ""},
            "b": {"name": "B", "description": ""},
        },
        "cuelists": {},
    }


def test_playbacks_tab_delete_removes_from_session(qtbot, qapp, monkeypatch):
    session = _session_with_playbacks()

    tab = PlaybacksTab(DummyMainApp())
    qtbot.addWidget(tab)
    tab.set_session_data(session)

    # Switch to list view so we can select a row.
    tab.radio_list.setChecked(True)
    assert tab.table.rowCount() == 2

    # Select the first row (sorted by name: A then B).
    tab.table.selectRow(0)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    tab._on_delete_selected_playback()

    assert "a" not in session["playbacks"]
    assert "b" in session["playbacks"]


def test_playbacks_tab_delete_blocks_when_referenced(qtbot, qapp, monkeypatch):
    session = {
        "playbacks": {"a": {"name": "A"}},
        "cuelists": {
            "main": {
                "cues": [
                    {"playback_pool": [{"playback": "a", "weight": 1.0}]},
                ]
            }
        },
    }

    tab = PlaybacksTab(DummyMainApp())
    qtbot.addWidget(tab)
    tab.set_session_data(session)

    tab.radio_list.setChecked(True)
    tab.table.selectRow(0)

    warned = {"called": False}

    def _warn(*args, **kwargs):
        warned["called"] = True
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", _warn)
    # Even if user would say yes, referenced delete should block before confirm.
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    tab._on_delete_selected_playback()

    assert warned["called"] is True
    assert "a" in session["playbacks"]
