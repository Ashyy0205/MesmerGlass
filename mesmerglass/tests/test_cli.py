import sys
import subprocess
import sys
from pathlib import Path

from mesmerglass import cli


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


def test_logging_flags_after_subcommand_run():
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--log-level", "DEBUG", "--log-format", "json", "--log-mode", "perf"])
    assert args.command == "run"
    assert args.log_level == "DEBUG"
    assert args.log_format == "json"
    assert args.log_mode == "perf"


def test_logging_flags_after_other_subcommand():
    parser = cli.build_parser()
    args = parser.parse_args(["ui", "--log-file", "custom.log", "--timeout", "1.5"])
    assert args.command == "ui"
    assert args.log_file.endswith("custom.log")
    assert args.timeout == 1.5
