"""Test CLI GL debug state functionality."""

import subprocess
import sys
import pytest
from pathlib import Path

@pytest.mark.timeout(10)
def test_cli_spiral_debug_gl_state():
    """Test that --debug-gl-state flag works and shows GL state information."""
    cmd = [
        sys.executable, "-m", "mesmerglass", "spiral-test",
        "--debug-gl-state", "--duration", "1", "--intensity", "0.3"
    ]
    
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent
    )
    
    # Should succeed
    assert result.returncode == 0, f"Command failed: {result.stderr}"
    
    # Should contain debug output
    output = result.stdout
    assert "OpenGL State Debugging Mode" in output
    assert "GL_DITHER:" in output
    assert "GL_SAMPLE_ALPHA_TO_COVERAGE:" in output
    assert "GL_POLYGON_SMOOTH:" in output
    assert "GL_BLEND:" in output
    assert "GL_MULTISAMPLE:" in output
    assert "GL_DEPTH_TEST:" in output
    assert "Blend func:" in output
    assert "Viewport:" in output
    
    # Should show correct disabled states for artifact elimination
    assert "GL_DITHER: 0" in output  # Should be disabled
    assert "GL_SAMPLE_ALPHA_TO_COVERAGE: 0" in output  # Should be disabled
    assert "GL_POLYGON_SMOOTH: 0" in output  # Should be disabled
    assert "GL_BLEND: 1" in output  # Should be enabled
    assert "GL_MULTISAMPLE: 1" in output  # Should be enabled
    assert "GL_DEPTH_TEST: 0" in output  # Should be disabled

@pytest.mark.timeout(10)
def test_cli_spiral_without_debug():
    """Test that normal spiral-test doesn't show debug output."""
    cmd = [
        sys.executable, "-m", "mesmerglass", "spiral-test",
        "--duration", "1", "--intensity", "0.3"
    ]
    
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent
    )
    
    # Should succeed
    assert result.returncode == 0, f"Command failed: {result.stderr}"
    
    # Should NOT contain debug output
    output = result.stdout
    assert "OpenGL State Debugging Mode" not in output
    assert "GL_DITHER:" not in output
    assert "GL_BLEND:" not in output
