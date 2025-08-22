import subprocess, sys


def _run(args: list[str]):
    return subprocess.run([sys.executable, '-m', 'mesmerglass', *args], capture_output=True, text=True, timeout=120)


def test_test_run_basic_help():
    p = _run(['test-run', 'fast'])
    assert p.returncode in (0, 5)  # allow non-zero if no tests collected in fast subset
    # don't assert on output strongly to keep stable


def test_test_run_unit_selection():
    p = _run(['test-run', 'unit', '-v'])
    assert p.returncode in (0, 5)
