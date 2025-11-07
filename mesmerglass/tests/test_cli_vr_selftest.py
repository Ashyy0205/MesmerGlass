import sys, subprocess, os, time


def run_cli(args, timeout=30):
    """Run `python -m mesmerglass` with args and return (code, out, err)."""
    cmd = [sys.executable, "-m", "mesmerglass"] + list(args)
    env = os.environ.copy()
    # Ensure tests run headless and fast
    env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", e.stderr or "timeout"


def test_cli_selftest_smoke():
    code, out, err = run_cli(["selftest"])  # quick import smoke test
    assert code == 0, f"selftest failed: code={code}\nstdout:\n{out}\nstderr:\n{err}"


def test_cli_vr_selftest_mock_fast():
    # Use mock mode to avoid OpenXR dependency and keep CI deterministic
    code, out, err = run_cli(["vr-selftest", "--mock", "--seconds", "0.5", "--fps", "30"])  # short, fast
    assert code == 0, f"vr-selftest --mock failed: code={code}\nstdout:\n{out}\nstderr:\n{err}"
import os
import sys
import subprocess


def run_cli(args, env=None):
    cmd = [sys.executable, "-m", "mesmerglass"] + list(args)
    proc = subprocess.run(cmd, env=env or os.environ.copy(), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_help_runs():
    code, out, err = run_cli(["--help"])  # should print help and exit 0
    assert code == 0
    assert "MesmerGlass CLI" in out


def test_vr_selftest_mock_quick():
    env = os.environ.copy()
    env["MESMERGLASS_VR_MOCK"] = "1"  # ensure OpenXR not required in CI
    code, out, err = run_cli(["vr-selftest", "--seconds", "0.1", "--fps", "10", "--pattern", "solid"], env=env)
    # Expect a clean exit
    assert code == 0, f"stdout={out}\nstderr={err}"
