import os, pytest, warnings
warnings.filterwarnings("ignore", message=".*address already in use.*")

def _probe_gl_available():
    try:
        from mesmerglass.mesmerloom.compositor import LoomCompositor, probe_available  # type: ignore
        # Prefer lightweight probe if exported
        try:
            return bool(probe_available())
        except BaseException:
            # Fallback: presence of LoomCompositor implies potential availability
            return True if LoomCompositor else False
    except BaseException:
        return False

def setup_module(module):  # noqa: D401
    os.environ["MESMERGLASS_NO_SERVER"] = "1"
    if not _probe_gl_available():
        pytest.skip("GL unavailable", allow_module_level=True)

@pytest.fixture(autouse=True)
def _no_server(monkeypatch):
    try:
        import mesmerglass.server as srv  # type: ignore
        monkeypatch.setattr(srv, "start", lambda *a, **k: None, raising=False)
    except Exception:
        pass

def test_launcher_compositor_activation(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from mesmerglass.ui.launcher import Launcher
    app = QApplication.instance() or QApplication([])
    win = Launcher("Test")
    qtbot.addWidget(win)
    comp = getattr(win, 'compositor', None)
    assert comp and getattr(comp, 'available', False)
    calls = {}
    def _req(): calls['called'] = True
    monkeypatch.setattr(comp, 'request_draw', _req)
    win._on_spiral_toggled(True)
    assert win.spiral_enabled and getattr(comp, '_active', False)
    win._on_spiral_tick()
    assert calls.get('called'), "request_draw not invoked on tick"
    win._on_spiral_toggled(False)
    assert not getattr(comp, '_active', True)
