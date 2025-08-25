import json, tempfile, os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from mesmerglass.ui.launcher import Launcher


def test_session_font_path_persistence(tmp_path: Path):
    os.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
    app = QApplication.instance() or QApplication([])
    win = Launcher("MesmerGlass", enable_device_sync_default=False)
    # Simulate user-chosen font path (file may not be a valid font; persistence only)
    fake_font = tmp_path/"dummy_font.ttf"; fake_font.write_bytes(b"not a real font")
    win.current_font_path = str(fake_font)
    st = win.capture_session_state(); assert st
    d = st.to_json_dict()
    assert d.get('textfx', {}).get('font_path') == str(fake_font)
    # Apply to new launcher and ensure path carried over even if load fails
    win2 = Launcher("MesmerGlass", enable_device_sync_default=False)
    win2.apply_session_state(st)
    assert getattr(win2, 'current_font_path', None) == str(fake_font)
    try:
        win.close(); win2.close()
    except Exception:
        pass