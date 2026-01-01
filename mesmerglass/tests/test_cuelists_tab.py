"""Unit tests for the Cuelists tab delete behavior."""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QMessageBox

from mesmerglass.ui.tabs.cuelists_tab import CuelistsTab


class DummyMainApp(QWidget):
    """Minimal object providing what CuelistsTab expects."""

    def __init__(self):
        super().__init__()
        self._dirty = False

    def mark_session_dirty(self):
        self._dirty = True


def test_cuelists_tab_delete_removes_from_session(qtbot, qapp, monkeypatch):
    session = {
        "cuelists": {
            "a": {"name": "A", "cues": []},
            "b": {"name": "B", "cues": []},
        }
    }

    tab = CuelistsTab(DummyMainApp())
    qtbot.addWidget(tab)
    tab.set_session_data(session)

    assert tab.table.rowCount() == 2

    # Sorted by name: A then B
    tab.table.selectRow(0)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    tab._on_delete_selected_cuelist()

    assert "a" not in session["cuelists"]
    assert "b" in session["cuelists"]


def test_cuelists_tab_duration_shows_infinity_when_looping(qtbot, qapp):
    session = {
        "cuelists": {
            "looping": {
                "name": "Looping",
                "loop_mode": "loop",
                "cues": [
                    {"name": "Cue 1", "duration_seconds": 900},
                ],
            },
        }
    }

    tab = CuelistsTab(DummyMainApp())
    qtbot.addWidget(tab)
    tab.set_session_data(session)

    assert tab.table.rowCount() == 1
    duration_text = tab.table.item(0, 2).text()
    assert "∞" in duration_text
