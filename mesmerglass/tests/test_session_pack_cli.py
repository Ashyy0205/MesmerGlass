import json, sys, subprocess


def _run(*args):
    return subprocess.run([sys.executable, "-m", "mesmerglass", *args], capture_output=True, text=True)


SAMPLE = {"version": 1, "name": "CLI Pack", "text": {"items": [{"msg": "Focus", "secs": 5}]}, "pulse": {"stages": [{"mode": "wave", "intensity": 0.25, "secs": 10}], "fallback": "idle"}}


def _write(tmp_path):
    p = tmp_path / "pack.json"
    p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return p


def test_session_summary(tmp_path):
    p = _write(tmp_path)
    r = _run("session", "--load", str(p), "--summary")
    assert r.returncode == 0
    assert "CLI Pack" in r.stdout


def test_session_print(tmp_path):
    p = _write(tmp_path)
    r = _run("session", "--load", str(p), "--print")
    data = json.loads(r.stdout)
    assert data["name"] == "CLI Pack"


def test_session_apply(tmp_path):
    p = _write(tmp_path)
    r = _run("session", "--load", str(p), "--apply")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["pack"] == "CLI Pack"
    assert data["text"] == "Focus"
    assert 0 <= data["buzz_intensity"] <= 1


def test_session_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json }", encoding="utf-8")
    r = _run("session", "--load", str(bad), "--summary")
    assert r.returncode == 1