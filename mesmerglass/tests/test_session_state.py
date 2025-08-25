import json, tempfile, os, sys, subprocess, pathlib
from mesmerglass.ui.launcher import Launcher
from PyQt6.QtWidgets import QApplication

_APP = None

_LAUNCHER_HOLD = []  # prevent premature GC of Qt objects during tests
from mesmerglass.content.loader import save_session_state, load_session_state


def _make_launcher():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    win = Launcher("MesmerGlass", enable_device_sync_default=False)
    _LAUNCHER_HOLD.append(win)
    return win


def test_session_state_roundtrip():
    win = _make_launcher()
    # Mutate some fields
    win.primary_path = "P1.mp4"; win.primary_op = 0.9
    win.secondary_path = "P2.mp4"; win.secondary_op = 0.4
    win.audio1_path = "A1.mp3"; win.audio2_path = "A2.mp3"; win._set_vols(0.7, 0.3)
    win.fx_mode = "Breath + Sway"; win.fx_intensity = 55
    st = win.capture_session_state()
    assert st is not None
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td)/"state.json"
        save_session_state(st, p)
        loaded = load_session_state(p)
        assert loaded.video["primary"]["path"] == "P1.mp4"
        win2 = _make_launcher()
        win2.apply_session_state(loaded)
        assert win2.primary_path == "P1.mp4"
        assert abs(win2.vol1 - 0.7) < 1e-6


def test_state_cli_save_and_print():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td)/"snap.json"
        # Save
        r = subprocess.run([sys.executable, '-m', 'mesmerglass', 'state', '--save', '--file', str(path)], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        assert path.is_file()
        # Print
        r2 = subprocess.run([sys.executable, '-m', 'mesmerglass', 'state', '--print', '--file', str(path)], capture_output=True, text=True, timeout=30)
        assert r2.returncode == 0, r2.stderr
        data = json.loads(r2.stdout.strip())
        assert data.get('kind') == 'session_state'


def test_state_cli_apply():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td)/"snap.json"
        # Create save first
        r = subprocess.run([sys.executable, '-m', 'mesmerglass', 'state', '--save', '--file', str(path)], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        # Apply it
        r2 = subprocess.run([sys.executable, '-m', 'mesmerglass', 'state', '--apply', '--file', str(path)], capture_output=True, text=True, timeout=30)
        assert r2.returncode == 0, r2.stderr
        out = r2.stdout.strip()
        assert 'video_primary' in out
