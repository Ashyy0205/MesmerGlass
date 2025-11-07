"""Tests for theme CLI command."""

import pytest
import subprocess
import sys
import json
from pathlib import Path


@pytest.fixture
def sample_theme_path():
    """Path to sample theme fixture."""
    return Path(__file__).parent / "fixtures" / "sample_theme.json"


def test_theme_load_summary(sample_theme_path):
    """Test theme loading with default summary output."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme", "--load", str(sample_theme_path)],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0
    assert "Theme Collection loaded successfully" in result.stdout
    assert "Total themes: 3" in result.stdout
    assert "Enabled themes: 2" in result.stdout
    assert "test_theme_1" in result.stdout


def test_theme_list(sample_theme_path):
    """Test theme listing."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme", "--load", str(sample_theme_path), "--list"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0
    assert "Themes in collection (3 total):" in result.stdout
    assert "test_theme_1 (ENABLED)" in result.stdout
    assert "test_theme_2 (DISABLED)" in result.stdout
    assert "test_theme_3 (ENABLED)" in result.stdout
    assert "Images: 3" in result.stdout  # test_theme_1
    assert "Images: 5" in result.stdout  # test_theme_3


def test_theme_show_config(sample_theme_path):
    """Test theme JSON output."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme", "--load", str(sample_theme_path), "--show-config"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0
    
    # Parse JSON output
    data = json.loads(result.stdout)
    assert "theme_map" in data
    assert "test_theme_1" in data["theme_map"]
    assert "test_theme_2" in data["theme_map"]
    assert "test_theme_3" in data["theme_map"]
    
    theme1 = data["theme_map"]["test_theme_1"]
    assert theme1["enabled"] == True
    assert len(theme1["image_path"]) == 3
    assert len(theme1["text_line"]) == 3


def test_theme_test_shuffler(sample_theme_path):
    """Test weighted shuffler."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme", "--load", str(sample_theme_path), "--test-shuffler", "50"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0
    assert "Testing Shuffler with 3 images:" in result.stdout
    assert "Running 50 selections..." in result.stdout
    assert "Selection counts:" in result.stdout
    assert "Image 0:" in result.stdout
    assert "Image 1:" in result.stdout
    assert "Image 2:" in result.stdout


def test_theme_test_cache():
    """Test image cache creation."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme", "--test-cache"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0
    assert "Testing image cache" in result.stdout
    assert "Cache created with size:" in result.stdout
    assert "Cache is ready" in result.stdout


def test_theme_missing_file():
    """Test error handling for missing file."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme", "--load", "nonexistent.json"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_theme_no_action():
    """Test error when no action specified."""
    result = subprocess.run(
        [sys.executable, "-m", "mesmerglass", "theme"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 1
    assert "Must specify --load or --test-cache" in result.stderr
