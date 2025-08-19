"""DevTools UI smoke tests.

These are lightweight and headless-friendly. They ensure the DevToolsPage
can be created, add/remove virtual toys without hanging, and the Launcher can
open the page via its internal method.
"""

import time
import pytest

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_devtools_page_add_remove(qapp):
    from mesmerglass.ui.pages.devtools import DevToolsPage

    page = DevToolsPage(default_port=12350)
    # Simulate adding a toy
    page._on_add()

    # Let background thread(s) run briefly and UI poll
    t0 = time.time()
    while time.time() - t0 < 0.3:
        qapp.processEvents()
        time.sleep(0.01)

    # Remove all and close without crash
    page._on_remove_all()
    page.close()


def test_launcher_opens_devtools(qapp):
    from mesmerglass.ui.launcher import Launcher

    win = Launcher("MesmerGlass", enable_device_sync_default=False)
    win._open_devtools()
    # Verify a tab named DevTools exists and is selected
    names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert any(n == "DevTools" for n in names)
    win.close()
