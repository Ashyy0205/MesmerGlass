from PyQt6.QtWidgets import QApplication
from mesmerglass.ui.launcher import Launcher

def test_menu_install_idempotent():
    app = QApplication.instance() or QApplication([])
    win = Launcher("MesmerGlass", enable_device_sync_default=False)
    # First call already done in __init__, call again explicitly
    win._install_menu_bar()
    before = []
    mb = getattr(win, 'menuBar', None)
    if callable(mb):
        bar = win.menuBar()
        before = [a.text() for a in bar.actions()]
    # Call again; should not duplicate
    win._install_menu_bar()
    after = []
    if callable(mb):
        bar = win.menuBar()
        after = [a.text() for a in bar.actions()]
    assert before == after
    try:
        win.close()
    except Exception:
        pass
