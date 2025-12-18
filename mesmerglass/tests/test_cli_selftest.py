import subprocess
import sys


def test_cli_selftest_reports_background_diag():
    proc = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "selftest"],
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert proc.returncode == 0, combined
    assert "background diagnostics" in combined
