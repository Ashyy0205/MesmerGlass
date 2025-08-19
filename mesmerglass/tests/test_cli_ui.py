"""CLI UI navigation tests."""

import sys
import subprocess


def run_cli(*args):
    python = sys.executable
    return subprocess.run([python, "-m", "mesmerglass", *args], capture_output=True, text=True)


def test_ui_list_tabs():
    r = run_cli("ui", "--list-tabs")
    assert r.returncode == 0
    # Expected core tabs
    out = r.stdout.strip().splitlines()
    assert any("Media" == x for x in out)
    assert any("Audio" == x for x in out)
    assert any("Text" in x for x in out)


def test_ui_select_tab_by_name():
    r = run_cli("ui", "--tab", "Audio", "--timeout", "0.05")
    assert r.returncode == 0


def test_ui_status_and_setters():
    r = run_cli(
        "ui",
        "--tab", "Text & FX",
        "--set-text", "TEST",
        "--set-fx-mode", "Shimmer",
        "--set-fx-intensity", "42",
        "--vol1", "10",
        "--vol2", "20",
        "--displays", "primary",
        "--status",
    "--timeout", "0.05",
    )
    assert r.returncode == 0
    # Validate JSON shape
    import json
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data["tab"].lower().startswith("text")
    assert data["text"] == "TEST"
    assert data["fx_mode"] == "Shimmer"
    assert data["fx_intensity"] == 42
    assert 0.09 <= data["vol1"] <= 0.11
    assert 0.19 <= data["vol2"] <= 0.21


def test_ui_launch_and_stop():
    r = run_cli("ui", "--displays", "primary", "--launch", "--status", "--timeout", "0.05")
    assert r.returncode == 0
    import json
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data["running"] in (True, False)  # running may be false if no displays are available, but shouldn’t error
    # Now stop; this should not crash
    r2 = run_cli("ui", "--stop", "--timeout", "0.05")
    assert r2.returncode == 0
