import json, subprocess, sys, tempfile, pathlib, os


def _make_pack(tmpdir: pathlib.Path, name: str = "PackOne") -> pathlib.Path:
    """Create a minimal valid session pack file and return its path."""
    data = {
        "version": 1,
        "name": name,
        # Text section with both legacy secs and new style fields to exercise canonical print logic
        "text": {"items": [
            {"msg": "HELLO", "secs": 3},  # legacy secs (weight absent so kept in canonical)
            {"msg": "WORLD", "weight": 2.0, "mode": "alt"},  # weight triggers omission of secs
        ]},
        "pulse": {"stages": [
            {"mode": "wave", "intensity": 0.42, "secs": 5},
            {"mode": "flat", "intensity": 0.58, "secs": 4},
        ], "fallback": "idle"},
    }
    p = tmpdir/"pack.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _run(args: list[str], **kwargs):
    return subprocess.run([sys.executable, '-m', 'mesmerglass', *args], capture_output=True, text=True, timeout=30, **kwargs)


def test_session_cli_summary_and_explicit_match(tmp_path):
    pack = _make_pack(tmp_path)
    os.environ.setdefault("MESMERGLASS_NO_SERVER", "1")  # speed up headless operations
    r_default = _run(['session', '--load', str(pack)])
    assert r_default.returncode == 0, r_default.stderr
    assert "SessionPack" in r_default.stdout  # summary string format
    r_explicit = _run(['session', '--load', str(pack), '--summary'])
    assert r_explicit.returncode == 0, r_explicit.stderr
    # Normalize whitespace to compare (avoid trailing newlines)
    assert r_default.stdout.strip() == r_explicit.stdout.strip()


def test_session_cli_print_canonical(tmp_path):
    pack = _make_pack(tmp_path, name="PrintPack")
    r = _run(['session', '--load', str(pack), '--print'])
    assert r.returncode == 0, r.stderr
    # Should be canonical JSON (single line) – parse and validate shape
    data = json.loads(r.stdout.strip())
    assert set(data.keys()) == {"version", "name", "text", "pulse"}
    assert data["name"] == "PrintPack"
    assert len(data["text"]["items"]) == 2
    # First item keeps secs (legacy path) because weight absent; second omits secs (weight present)
    first, second = data["text"]["items"][0], data["text"]["items"][1]
    assert "secs" in first and first["msg"] == "HELLO"
    assert "secs" not in second and second["weight"] == 2.0
    # Pulse stages intensities preserved
    intensities = [st["intensity"] for st in data["pulse"]["stages"]]
    assert abs(sum(intensities) / len(intensities) - 0.5) < 1e-6  # avg 0.42 & 0.58 = 0.5


def test_session_cli_apply_status_json(tmp_path):
    pack = _make_pack(tmp_path, name="ApplyPack")
    r = _run(['session', '--load', str(pack), '--apply'])
    assert r.returncode == 0, r.stderr
    status = json.loads(r.stdout.strip())
    # Expected keys printed by CLI apply branch
    assert set(status.keys()) == {"pack", "text", "buzz_intensity"}
    assert status["pack"] == "ApplyPack"
    # Text should reflect first text item (may be HELLO)
    assert status["text"] in ("HELLO", "Hello", "HELLO ")


def test_session_cli_missing_file_error(tmp_path):
    missing = tmp_path/"nope.json"
    r = _run(['session', '--load', str(missing)])
    # Expect non-zero and error message on stderr
    assert r.returncode != 0
    assert "Failed to load" in (r.stderr or "") or "not found" in (r.stderr or "")
