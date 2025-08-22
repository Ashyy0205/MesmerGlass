import subprocess, sys, re, pathlib

def test_run_py_deprecation_smoke():
    """Invoke legacy run.py and assert it exits 0 and warns about deprecation.
    GUI should start and exit quickly because we pass no args (shim maps to 'run').
    We only check for the deprecation text; we don't need to spin a full Qt loop here.
    """
    # Use -c to import run.py in a subprocess for isolation
    root = pathlib.Path(__file__).resolve().parents[2]
    cmd = [sys.executable, str(root / 'run.py')]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
    combo = proc.stdout + proc.stderr
    assert 'deprecated' in combo.lower(), combo

def test_pulse_alias_warning():
    """Ensure 'test' alias maps to pulse and warns."""
    proc = subprocess.run([sys.executable, '-m', 'mesmerglass', 'test', '--level', '0.1', '--duration', '10'], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert 'deprecated' in (proc.stderr.lower()+proc.stdout.lower())

