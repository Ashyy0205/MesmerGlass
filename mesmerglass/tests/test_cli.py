import sys
import subprocess
import sys
from pathlib import Path


def run_cmd(args):
    python = sys.executable
    result = subprocess.run([python, "-m", "mesmerglass", *args], capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def test_help_exits_zero():
    code, out, err = run_cmd(["--help"])  # Should not error
    assert code == 0
    assert "MesmerGlass CLI" in out


def test_selftest_exits_zero():
    code, out, err = run_cmd(["selftest"])  # Should be fast and succeed
    assert code == 0
