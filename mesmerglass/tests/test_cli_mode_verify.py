import json
from pathlib import Path

from mesmerglass.cli import main as cli_main


def make_mode(tmp_path: Path, rpm: float = 4.0, reverse: bool = False, cycle_speed: int = 50) -> Path:
    data = {
        "version": "1.0",
        "name": "CLI_Verify_Test",
        "spiral": {"type": "linear", "rotation_speed": rpm, "opacity": 0.5, "reverse": reverse},
        "media": {"mode": "images", "cycle_speed": cycle_speed, "opacity": 1.0, "use_theme_bank": True},
        "text": {"enabled": False, "mode": "centered_sync", "opacity": 1.0, "use_theme_bank": True, "library": []},
        "zoom": {"mode": "none", "rate": 0.0},
    }
    p = tmp_path / "cli_verify_mode.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_cli_mode_verify_forward(tmp_path):
    mode_path = make_mode(tmp_path, rpm=4.0, reverse=False, cycle_speed=50)
    rc = cli_main(["mode-verify", "--mode", str(mode_path), "--frames", "90", "--fps", "60"])
    assert rc == 0


def test_cli_mode_verify_reverse(tmp_path):
    mode_path = make_mode(tmp_path, rpm=6.0, reverse=True, cycle_speed=20)
    rc = cli_main(["mode-verify", "--mode", str(mode_path), "--frames", "120", "--fps", "60"])
    assert rc == 0
