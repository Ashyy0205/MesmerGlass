import json, os, tempfile
from pathlib import Path
from PyQt6.QtWidgets import QApplication
import os
from mesmerglass.ui.launcher import Launcher
from mesmerglass.content.loader import load_session_pack


def test_session_pack_path_persistence(tmp_path: Path):
    # Create a minimal fake session pack file (reuse existing test pack if present)
    pack_file = Path('test_pack.json')
    if not pack_file.exists():
        data = {"kind":"session_pack","version":1,"name":"TestPack","text":{"items":[{"t":"HELLO"}]},"pulse":{"stages":[]}}
        pf = tmp_path/"temp_pack.json"
        pf.write_text(json.dumps(data), encoding='utf-8')
        pack_file = pf

    os.environ.setdefault("MESMERGLASS_NO_SERVER", "1")
    app = QApplication.instance() or QApplication([])
    win = Launcher("MesmerGlass", enable_device_sync_default=False)
    pack = load_session_pack(str(pack_file))
    # simulate UI load path assignment
    win.current_pack_path = str(pack_file)
    if hasattr(win, 'apply_session_pack'):
        win.apply_session_pack(pack)

    state = win.capture_session_state()
    assert state is not None
    # pack path stored under textfx.pack_path in JSON dict
    state_json = state.to_json_dict()
    assert state_json.get('textfx', {}).get('pack_path') == str(pack_file)

    # Apply state to fresh launcher; current_pack_path may carry over only if set directly later.
    win2 = Launcher("MesmerGlass", enable_device_sync_default=False)
    win2.apply_session_state(state)
    # State apply currently updates current_pack_path from textfx.pack_path
    assert getattr(win2, 'current_pack_path', None) == str(pack_file)
    # But state values (e.g., buzz_intensity) should match
    assert getattr(win2, 'buzz_intensity', None) == getattr(win, 'buzz_intensity', None)

    try:
        win.close(); win2.close()
    except Exception:
        pass
