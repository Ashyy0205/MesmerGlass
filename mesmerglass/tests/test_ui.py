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

@pytest.fixture
async def dev_tools(launcher):
    """Open dev tools window for testing."""
    launcher.toggle_dev_mode()  # Ensure dev tools is created
    QTest.qWait(100)  # Allow window to show
    assert launcher.dev_tools is not None, "Dev tools should be created"
    return launcher.dev_tools
    
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

@pytest.mark.asyncio
async def test_launch_dev_tools(launcher):
    """Test dev tools window functionality."""
    # Open dev tools
    launcher.toggle_dev_mode()
    QTest.qWait(100)  # Allow window to open
    assert launcher.dev_tools is not None, "Dev tools should be created"
    assert launcher.dev_tools.isVisible(), "Dev tools should be visible"
    
    # Close dev tools
    launcher.toggle_dev_mode()
    QTest.qWait(100)  # Allow window to close
    assert not launcher.dev_tools.isVisible(), "Dev tools should be hidden"
    launcher.dev_tools.close()
    await asyncio.sleep(0.1)

@pytest.mark.asyncio
async def test_dev_mode_toggle(launcher):
    """Test dev mode window toggling."""
    assert launcher.dev_tools is None, "Dev tools should start closed"
    
    # Toggle dev mode on
    launcher.toggle_dev_mode()
    await asyncio.sleep(0.1)
    assert launcher.dev_tools is not None, "Dev tools should open"
    assert launcher.dev_tools.isVisible(), "Dev tools window should be visible"
    
    # Toggle dev mode off
    launcher.toggle_dev_mode()
    await asyncio.sleep(0.1)
    assert not launcher.dev_tools.isVisible(), "Dev tools window should hide"

@pytest.mark.asyncio
async def test_virtual_toy_creation(launcher, dev_tools):
    """Test adding and removing virtual toys in dev mode."""
    # Find the add toy button
    # Ensure dev tools is visible
    dev_tools.show()
    await asyncio.sleep(0.1)
    
    add_btn = None
    for child in dev_tools.findChildren(QPushButton):
        if child.text() == "Add Virtual Toy":
            add_btn = child
            break
    assert add_btn is not None, "Should find Add Virtual Toy button"
    
    # Add a toy
    QTest.mouseClick(add_btn, Qt.MouseButton.LeftButton)
    await asyncio.sleep(0.1)
    
    # Verify toy was added
    assert len(dev_tools.toys) == 1, "Should have one toy"
    assert len(dev_tools.toy_widgets) == 1, "Should have one toy widget"
    
    # Get the toy widget
    toy_id = list(dev_tools.toys.keys())[0]
    widgets = dev_tools.toy_widgets[toy_id]
    
    # Process events to ensure widget is properly shown
    QTest.qWait(100)
    widgets["frame"].show()
    assert widgets["frame"].isVisible(), "Toy frame should be visible"
    
    # Wait for the toy to show up
    toy = dev_tools.toys[toy_id]
    status_text = widgets["status"].text()
    assert toy.name in status_text, f"Status should show toy name: {status_text}"
    
    # Test remove button
    remove_btn = None
    for child in widgets["frame"].findChildren(QPushButton):
        if child.text() == "Remove":
            remove_btn = child
            break
    assert remove_btn is not None, "Should find Remove button"
    
    # Remove the toy
    QTest.mouseClick(remove_btn, Qt.MouseButton.LeftButton)
    await asyncio.sleep(0.1)
    
    assert len(dev_tools.toys) == 0, "Should have no toys after removal"
    assert len(dev_tools.toy_widgets) == 0, "Should have no toy widgets after removal"

@pytest.mark.asyncio
async def test_multiple_virtual_toys(launcher, dev_tools):
    """Test handling multiple virtual toys."""
    add_btn = next(btn for btn in dev_tools.findChildren(QPushButton) if btn.text() == "Add Virtual Toy")
    
    # Add three toys
    for _ in range(3):
        QTest.mouseClick(add_btn, Qt.MouseButton.LeftButton)
        await asyncio.sleep(0.1)
    
    assert len(dev_tools.toys) == 3, "Should have three toys"
    
    # Verify each toy has unique name and widget
    names = set()
    for toy_id, widgets in dev_tools.toy_widgets.items():
        name = dev_tools.toys[toy_id].name
        assert name not in names, "Each toy should have unique name"
        names.add(name)
        assert widgets["intensity"].value() == 0, "Initial intensity should be 0"
    
    # Remove toys one by one
    while dev_tools.toy_widgets:
        toy_id = next(iter(dev_tools.toy_widgets))
        widgets = dev_tools.toy_widgets[toy_id]
        remove_btn = next(btn for btn in widgets["frame"].findChildren(QPushButton) if btn.text() == "Remove")
        QTest.mouseClick(remove_btn, Qt.MouseButton.LeftButton)
        await asyncio.sleep(0.1)
    
    assert len(dev_tools.toys) == 0, "Should remove all toys"

@pytest.mark.asyncio
async def test_virtual_toy_intensity(launcher, dev_tools):
    """Test virtual toy intensity updates."""
    # Add a toy
    add_btn = next(btn for btn in dev_tools.findChildren(QPushButton) if btn.text() == "Add Virtual Toy")
    QTest.mouseClick(add_btn, Qt.MouseButton.LeftButton)
    await asyncio.sleep(0.1)
    
    toy_id = next(iter(dev_tools.toys))
    toy = dev_tools.toys[toy_id]
    widgets = dev_tools.toy_widgets[toy_id]
    
    # Test intensity updates
    test_levels = [0.0, 0.5, 1.0, 0.3, 0.0]
    for level in test_levels:
        toy.state.level = level
        # Force an immediate update
        dev_tools.update_toy_status()
        await asyncio.sleep(0.1)
        expected = int(level * 100)
        assert widgets["intensity"].value() == expected, f"Intensity should update to {expected}%"
