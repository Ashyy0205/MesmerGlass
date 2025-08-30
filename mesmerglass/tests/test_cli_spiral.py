import sys, subprocess, re

def test_cli_spiral_basic():
    proc = subprocess.run([sys.executable, '-m', 'mesmerglass', 'spiral-test', '--duration', '1', '--screen', '1'], capture_output=True, text=True)
    rc = proc.returncode
    out = (proc.stdout + proc.stderr).lower()
    if rc == 77:
        assert 'unavailable' in out
    else:
        assert rc == 0, f"unexpected rc {rc} stdout={proc.stdout} stderr={proc.stderr}"
        assert 'mesmerloom' in out
        assert 'fps' in out
        assert 'screen' in out or 'geometry' in out, f"screen/geometry missing in output: {out}"
        m = re.search(r'fps=([0-9]+\.?[0-9]*)', out)
        assert m, f"fps missing in output: {out}"
