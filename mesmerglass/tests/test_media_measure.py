import json
import subprocess
import sys
from pathlib import Path


def run_cli_json(args: list[str]) -> dict:
    """Run the mesmerglass CLI with JSON output and return parsed dict."""
    cmd = [
        str(Path.cwd() / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "mesmerglass",
        "--log-level",
        "ERROR",
    ] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=Path.cwd())
    assert proc.returncode == 0, f"CLI exited with {proc.returncode}: stderr={proc.stderr} stdout={proc.stdout}"
    assert proc.stdout.strip(), "Expected JSON on stdout, got empty output"
    return json.loads(proc.stdout)


def test_media_measure_vmc_fallback_timer_produces_samples():
    """
    Ensure the vmc measurement path yields non-zero samples even when the VMC
    media list is empty or timers are inactive. The CLI should fall back to an
    internal QTimer to measure the expected mapping interval. Keep it fast.
    """
    out = run_cli_json([
        "media-measure",
        "--mode",
        "vmc",
        "--speeds",
        "50",
        "--cycles",
        "2",
        "--json",
    ])
    rows = out.get("rows", [])
    assert rows and isinstance(rows, list), f"Unexpected rows: {rows}"
    r = rows[0]
    # Expect a positive average close to the expected interval mapping
    assert r.get("vmc_avg_ms", 0.0) > 0.0, f"vmc_avg_ms should be > 0, got {r}"
    assert r.get("expected_ms", 0.0) > 0.0, f"expected_ms should be > 0, got {r}"
    # Allow broad tolerance; we only assert non-zero functionality here
    assert abs(r["vmc_avg_ms"] - r["expected_ms"]) < (r["expected_ms"] * 0.25), r
