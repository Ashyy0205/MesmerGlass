"""Test suite for UI components and features."""

import os
import sys
import pytest
from PyQt6.QtWidgets import (
    QApplication, QPushButton, QSlider, QLabel,
    QWidget, QLineEdit, QComboBox, QGroupBox,
    QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtGui import QColor
import asyncio

# Create QApplication instance for tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

@pytest.fixture
async def launcher(qapp):
    """Create a launcher window for testing."""
    from mesmerglass.ui.launcher import Launcher
    window = Launcher("MesmerGlass Test")
    window.show()  # Ensure window is visible for UI tests
    window._build_ui()  # Explicitly build UI
    window.show()  # Make sure UI is visible
    QTest.qWait(100)  # Give widgets time to initialize
    yield window
    # Cleanup
    if window.running:
        window.stop_all()
    window.close()
    await asyncio.sleep(0.1)  # Allow time for cleanup

# Dev Tools UI has been removed; no dev_tools fixture.
    
# ---------- Media Tests ----------
@pytest.mark.asyncio
async def test_media_controls(launcher):
    """Test video selection and opacity controls."""
    # Select the Media tab first
    launcher.tabs.setCurrentIndex(0)  # Media tab is first
    QTest.qWait(100)  # Allow tab to activate
    
    # Find sliders in the Media page container
    media_tab = launcher.tabs.currentWidget().widget()
    
    # Find sliders in card groupboxes
    primary_card = next(c for c in media_tab.findChildren(QGroupBox)
                       if c.title() == "Primary video")
    secondary_card = next(c for c in media_tab.findChildren(QGroupBox)
                         if c.title() == "Secondary video")
    
    primary_slider = next(s for s in primary_card.findChildren(QSlider))
    secondary_slider = next(s for s in secondary_card.findChildren(QSlider))
    
    # Test opacity controls
    test_values = [0, 50, 100]
    for val in test_values:
        primary_slider.setValue(val)
        assert launcher.primary_op == val/100.0, f"Primary opacity should be {val}%"
        
        secondary_slider.setValue(val)
        assert launcher.secondary_op == val/100.0, f"Secondary opacity should be {val}%"

@pytest.mark.asyncio
async def test_text_and_effects(launcher):
    """Test text settings and effects controls."""
    # Select Text tab
    text_fx_idx = next(i for i, n in enumerate(
        [launcher.tabs.tabText(i) for i in range(launcher.tabs.count())]
    ) if "Text" in n)
    launcher.tabs.setCurrentIndex(text_fx_idx)
    QTest.qWait(100)  # Allow tab to activate
    
    # Get text fx page
    text_fx_page = launcher.tabs.currentWidget().widget()
    
    # Find text input
    text_group = next(g for g in text_fx_page.findChildren(QGroupBox)
                     if g.title() == "Text & FX")
    text_input = next(w for w in text_group.findChildren(QLineEdit))
    text_input.setText("TEST TEXT")
    QTest.qWait(100)  # Allow signals to propagate
    assert launcher.text == "TEST TEXT", "Text should update"
    
    # Test effect mode selection
    effect_combo = next(w for w in text_group.findChildren(QComboBox)
                       if w.parent().findChild(QLabel).text() == "FX style")
    effect_modes = ["Breath + Sway", "Shimmer", "Tunnel", "Subtle"]
    for mode in effect_modes:
        effect_combo.setCurrentText(mode)
        QTest.qWait(100)  # Allow signals to propagate
        assert launcher.fx_mode == mode, f"Effect mode should be {mode}"
    
    # Test effect intensity
    intensity_slider = next(w for w in text_group.findChildren(QSlider)
                          if w.parent().findChild(QLabel).text() == "FX intensity")
    test_values = [0, 50, 100]
    for val in test_values:
        intensity_slider.setValue(val)
        assert launcher.fx_intensity == val, f"Effect intensity should be {val}"

@pytest.mark.asyncio
async def test_audio_controls(launcher):
    """Test audio file loading and volume controls."""
    # Create test audio files
    test_files = []
    for i in range(2):
        path = os.path.join(os.path.dirname(__file__), f"test_audio_{i}.wav")
        with open(path, "wb") as f:
            f.write(b"RIFF    WAVEfmt     ")  # Minimal valid WAV header
        test_files.append(path)
    
    # Select Audio tab
    audio_idx = next(i for i, n in enumerate(
        [launcher.tabs.tabText(i) for i in range(launcher.tabs.count())]
    ) if "Audio" in n)
    launcher.tabs.setCurrentIndex(audio_idx)
    QTest.qWait(100)  # Allow tab to activate
    
    # Test loading audio files
    launcher.audio1_path = test_files[0]
    launcher.audio2_path = test_files[1]
    
    # Get audio page
    audio_page = launcher.tabs.currentWidget().widget()
    
    # Test volume controls
    primary_audio = next(g for g in audio_page.findChildren(QGroupBox)
                        if g.title() == "Primary audio")
    vol1_slider = next(w for w in primary_audio.findChildren(QSlider))
    
    secondary_audio = next(g for g in audio_page.findChildren(QGroupBox)
                          if g.title() == "Secondary audio")
    vol2_slider = next(w for w in secondary_audio.findChildren(QSlider))
    
    test_values = [0, 50, 100]
    for val in test_values:
        vol1_slider.setValue(val)
        assert abs(launcher.vol1 - val/100.0) < 0.01, f"Audio 1 volume should be {val}%"
        
        vol2_slider.setValue(val)
        assert abs(launcher.vol2 - val/100.0) < 0.01, f"Audio 2 volume should be {val}%"
    
    # Cleanup test files
    for path in test_files:
        try:
            os.remove(path)
        except:
            pass

@pytest.mark.asyncio
async def test_launch_and_overlay(launcher):
    """Test launch/stop functionality and overlay display."""
    # Select first display
    if launcher.list_displays.count() > 0:
        item = launcher.list_displays.item(0)
        item.setCheckState(Qt.CheckState.Checked)
    QTest.qWait(100)  # Allow display selection to register
        
    # Launch overlay
    launcher.launch()
    QTest.qWait(100)  # Allow overlay to appear
    assert launcher.running, "Should be running after launch"
    assert len(launcher.overlays) > 0, "Should create overlay window"
    
    # Check overlay properties
    overlay = launcher.overlays[0]
    assert overlay.isVisible(), "Overlay should be visible"
    assert overlay.primary_op == launcher.primary_op, "Overlay should inherit primary opacity"
    assert overlay.text == launcher.text, "Overlay should show launcher text"
    
    # Stop everything
    launcher.stop_all()
    QTest.qWait(100)  # Allow cleanup
    assert not launcher.running, "Should stop running"
    
    # Force cleanup any remaining overlays
    for overlay in launcher.overlays[:]:  # Copy list to avoid modification during iteration
        overlay.close()
        overlay.deleteLater()
    launcher.overlays.clear()
    QTest.qWait(100)  # Allow window cleanup
    
    assert len(launcher.overlays) == 0, "Should close all overlays"

# Dev Tools UI tests removed.

# Dev mode toggle tests removed.

# Dev Tools virtual toy UI creation tests removed.

# Dev Tools multi virtual toy tests removed.

# Dev Tools virtual toy intensity tests removed.
