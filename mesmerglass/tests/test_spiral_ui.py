import os, sys, pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

@pytest.mark.skipif('PYTEST_QT_OFFSCREEN' in os.environ and not os.environ.get('PYTEST_QT_OFFSCREEN'), reason='Qt offscreen platform unavailable')
@pytest.mark.asyncio
async def test_spiral_toggle_basic():
    """Verify spiral toggle updates state, timer, and chip text (if present)."""
    app = QApplication.instance() or QApplication([])
    from mesmerglass.ui.launcher import Launcher
    win = Launcher("MesmerGlass Test", enable_device_sync_default=False)
    # Ensure we have a chip attribute reference (naming may vary); fall back gracefully
    chip = getattr(win, 'chip_spiral', None) or getattr(win, 'spiral_status_chip', None)

    # Initial state
    assert hasattr(win, 'spiral_timer'), 'spiral_timer attribute missing'
    assert win.spiral_enabled is False
    assert not win.spiral_timer.isActive()

    # Toggle ON via handler (simulate signal)
    win._on_spiral_toggled(True)
    app.processEvents(); QTest.qWait(10)
    assert win.spiral_enabled is True
    assert win.spiral_timer.isActive() is True
    if chip:
        assert 'ON' in chip.text().upper()

    # Toggle OFF
    win._on_spiral_toggled(False)
    app.processEvents(); QTest.qWait(10)
    assert win.spiral_enabled is False
    assert win.spiral_timer.isActive() is False
    if chip:
        assert 'OFF' in chip.text().upper()

    # Cleanup
    try:
        win.close()
    except Exception:
        pass
