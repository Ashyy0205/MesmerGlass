"""Extended CLI tests."""

import sys
import subprocess
from pathlib import Path


def run_cli(*args):
    python = sys.executable
    return subprocess.run([python, "-m", "mesmerglass", *args], capture_output=True, text=True)


def test_invalid_subcommand_exits_2():
    r = run_cli("nope")
    assert r.returncode == 2


def test_pulse_subcommand_short_run():
    # Should return promptly and with exit 0
    r = run_cli("pulse", "--level", "0.2", "--duration", "50")
    assert r.returncode == 0


def test_logging_flags_parse():
    r = run_cli("--log-level", "DEBUG", "--log-format", "plain", "selftest")
    assert r.returncode == 0
