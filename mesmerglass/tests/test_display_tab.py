"""Unit tests for the Phase 7 Display tab."""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from mesmerglass.ui.tabs.display_tab import DisplayTab


class DummyDiscoveryService:
    def __init__(self, clients=None):
        self.discovered_clients = clients or []


class DummyMainApp(QWidget):
    """Minimal object providing the attributes DisplayTab expects."""

    def __init__(self, discovery_service=None):
        super().__init__()
        self.vr_discovery_service = discovery_service
        self.visual_director = None
        self.audio_engine = None
        self.compositor = None
        self.spiral_director = None
        self.text_director = None
        self.device_manager = None
        self._dirty = False

    def mark_session_dirty(self):
        self._dirty = True


def test_display_tab_renders_sections(qtbot, qapp):
    tab = DisplayTab(DummyMainApp(DummyDiscoveryService()))
    qtbot.addWidget(tab)

    texts = [tab.list_displays.item(i).text() for i in range(tab.list_displays.count())]

    assert any(text.startswith("🖥️") for text in texts), "Expected at least one monitor entry"
    assert any("VR Devices" in text for text in texts), "Missing VR devices section label"


def test_display_tab_refresh_with_clients(qtbot, qapp):
    clients = [
        {"name": "QA Headset", "ip": "10.0.0.42"},
        {"name": "Android Viewer", "ip": "10.0.0.99"},
    ]
    discovery = DummyDiscoveryService(clients)
    tab = DisplayTab(DummyMainApp(discovery))
    qtbot.addWidget(tab)

    discovery.discovered_clients = clients
    tab._refresh_vr_displays()

    vr_entries = []
    for i in range(tab.list_displays.count()):
        item = tab.list_displays.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "vr":
            vr_entries.append(data)

    assert len(vr_entries) == len(clients)
