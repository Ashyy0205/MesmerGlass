"""Tests for the Phase 7 MainApplication window."""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from mesmerglass.ui.main_application import MainApplication


class DummyDiscoveryService:
    """Lightweight stand-in for the MesmerVisor discovery server."""

    def __init__(self, discovery_port: int, streaming_port: int):
        self.discovery_port = discovery_port
        self.streaming_port = streaming_port
        self.started = False
        self.discovered_clients = []

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.started = False
        return True


def _fake_engine_setup(self):
    """Populate the attributes referenced by tabs without heavy GL setup."""
    self.spiral_director = None
    self.compositor = None
    self.text_renderer = None
    self.text_director = None
    self.theme_bank = None
    self.visual_director = None
    self.audio_engine = None
    self.device_manager = None


def test_main_application_initializes_display_tab(qtbot, qapp, monkeypatch):
    """Ensure MainApplication boots with tabs + discovery service in place."""
    monkeypatch.setattr("mesmerglass.mesmervisor.streaming_server.DiscoveryService", DummyDiscoveryService)
    monkeypatch.setattr(MainApplication, "_initialize_engines", _fake_engine_setup)

    window = MainApplication()
    qtbot.addWidget(window)

    assert window.vr_discovery_service.started is True
    assert window.tabs.count() >= 3
    assert window.display_tab.list_displays.count() >= 1

    window.vr_discovery_service.stop()
    window.close()


def test_main_application_refreshes_vr_clients(qtbot, qapp, monkeypatch):
    """Ensure VR discovery clients surface inside the Display tab list."""
    monkeypatch.setattr("mesmerglass.mesmervisor.streaming_server.DiscoveryService", DummyDiscoveryService)
    monkeypatch.setattr(MainApplication, "_initialize_engines", _fake_engine_setup)

    window = MainApplication()
    qtbot.addWidget(window)

    sample_clients = [
        {"name": "QA Headset", "ip": "10.0.0.42"},
        {"name": "Android Viewer", "ip": "10.0.0.99"},
    ]
    window.vr_discovery_service.discovered_clients = sample_clients
    window._refresh_vr_displays()

    vr_items = []
    for i in range(window.display_tab.list_displays.count()):
        item = window.display_tab.list_displays.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "vr":
            vr_items.append(data)

    assert len(vr_items) == len(sample_clients)

    window.vr_discovery_service.stop()
    window.close()
