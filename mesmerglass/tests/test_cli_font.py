import sys, subprocess, json, tempfile, os, pathlib


def run_cli(*args):
    return subprocess.run([sys.executable, '-m', 'mesmerglass', *args], capture_output=True, text=True)


def test_cli_set_font_path_dummy_file(tmp_path):
    # Create dummy file (not a real font but should be handled gracefully)
    fake_font = tmp_path / 'fakefont.ttf'
    fake_font.write_bytes(b'not-a-real-font')
    r = run_cli('ui', '--set-font-path', str(fake_font), '--status', '--timeout', '0.05')
    assert r.returncode == 0
    data = json.loads(r.stdout.strip().splitlines()[-1])
    # Path recorded even if family may remain default
    assert data['font_path'] == str(fake_font)
    assert 'font_family' in data
