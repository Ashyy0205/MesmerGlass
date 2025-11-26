"""
Tests for CLI cuelist command (Phase 5).

Tests cover:
- Cuelist validation (--validate)
- Cuelist printing (--print)
- Cuelist execution (headless)
- Error handling (missing files, invalid structure)
- JSON output formats
"""

import pytest
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock


# Get path to Python interpreter in venv
PYTHON_EXE = sys.executable


class TestCLICuelistValidation:
    """Test cuelist validation command."""
    
    @pytest.fixture
    def test_cuelist_path(self, tmp_path):
        """Create a test cuelist with valid structure."""
        # Create playback file
        playback_file = tmp_path / "test_playback.json"
        playback_file.write_text(json.dumps({
            "name": "Test Playback",
            "version": "1.0",
            "spiral": {"type": 3, "rotation_speed": 30.0},
            "media": {"mode": "none"},
            "text": {"enabled": False}
        }))

        hypno_audio = tmp_path / "hypno.wav"
        hypno_audio.write_bytes(b"stub")
        bg_audio = tmp_path / "background.wav"
        bg_audio.write_bytes(b"stub")
        
        # Create cuelist file
        cuelist_file = tmp_path / "test_cuelist.json"
        cuelist_data = {
            "name": "Test Cuelist",
            "description": "Test cuelist for CLI",
            "version": "1.0",
            "author": "Test",
            "loop_mode": "once",
            "cues": [
                {
                    "name": "Test Cue",
                    "duration_seconds": 10.0,
                    "playback_pool": [
                        {
                            "playback": str(playback_file.name),
                            "weight": 1.0
                        }
                    ],
                    "selection_mode": "on_cue_start",
                    "transition_in": {"type": "none", "duration_ms": 0},
                    "transition_out": {"type": "none", "duration_ms": 0},
                    "audio": {
                        "hypno": {
                            "file": hypno_audio.name,
                            "volume": 0.8,
                            "duration": 10.0
                        },
                        "background": {
                            "file": bg_audio.name,
                            "volume": 0.3,
                            "loop": True,
                            "duration": 60.0
                        }
                    }
                }
            ]
        }
        cuelist_file.write_text(json.dumps(cuelist_data))
        return cuelist_file
    
    def test_validate_valid_cuelist(self, test_cuelist_path):
        """Valid cuelist passes validation."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(test_cuelist_path), "--validate"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "PASSED" in result.stdout
    
    def test_validate_json_output(self, test_cuelist_path):
        """Validation can output JSON."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(test_cuelist_path), "--validate", "--json"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert "cuelist" in data
        assert "errors" in data
        assert len(data["errors"]) == 0
        assert "warnings" in data
        assert len(data["warnings"]) == 0
    
    def test_validate_missing_playback(self, tmp_path):
        """Validation fails for missing playback file."""
        cuelist_file = tmp_path / "bad_cuelist.json"
        cuelist_data = {
            "name": "Bad Cuelist",
            "version": "1.0",
            "cues": [
                {
                    "name": "Bad Cue",
                    "duration_seconds": 10.0,
                    "playback_pool": [
                        {
                            "playback": "nonexistent.json",
                            "weight": 1.0
                        }
                    ]
                }
            ]
        }
        cuelist_file.write_text(json.dumps(cuelist_data))
        
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(cuelist_file), "--validate", "--json"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1  # Validation failure
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert "warnings" in data

    def test_validate_warns_missing_background(self, tmp_path):
        """Cuelists without background audio emit warnings but remain valid."""
        playback_file = tmp_path / "playback.json"
        playback_file.write_text(json.dumps({"name": "Test", "version": "1.0"}))
        hypno_audio = tmp_path / "hypno.wav"
        hypno_audio.write_bytes(b"stub")

        cuelist_file = tmp_path / "warn_cuelist.json"
        cuelist_file.write_text(json.dumps({
            "name": "Warn",
            "version": "1.0",
            "cues": [
                {
                    "name": "Cue",
                    "duration_seconds": 15,
                    "playback_pool": [{"playback": playback_file.name, "weight": 1.0}],
                    "audio": {
                        "hypno": {"file": hypno_audio.name, "volume": 0.9}
                    }
                }
            ]
        }))

        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(cuelist_file), "--validate", "--json"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert any("background" in warn for warn in data["warnings"])


class TestCLICuelistPrint:
    """Test cuelist print command."""
    
    @pytest.fixture
    def simple_cuelist(self, tmp_path):
        """Create a simple cuelist for printing."""
        playback_file = tmp_path / "playback.json"
        playback_file.write_text(json.dumps({"name": "Test", "version": "1.0"}))
        
        cuelist_file = tmp_path / "cuelist.json"
        cuelist_data = {
            "name": "Print Test Cuelist",
            "description": "Test for print command",
            "version": "1.0",
            "author": "Test Author",
            "loop_mode": "loop",
            "cues": [
                {
                    "name": "Cue One",
                    "duration_seconds": 30.0,
                    "playback_pool": [
                        {"playback": playback_file.name, "weight": 2.0}
                    ]
                },
                {
                    "name": "Cue Two",
                    "duration_seconds": 60.0,
                    "playback_pool": [
                        {"playback": playback_file.name, "weight": 1.0}
                    ]
                }
            ]
        }
        cuelist_file.write_text(json.dumps(cuelist_data))
        return cuelist_file
    
    def test_print_human_readable(self, simple_cuelist):
        """Print outputs human-readable format by default."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(simple_cuelist), "--print"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Print Test Cuelist" in result.stdout
        assert "Cue One" in result.stdout
        assert "Cue Two" in result.stdout
        assert "loop" in result.stdout.lower()
    
    def test_print_json_output(self, simple_cuelist):
        """Print can output JSON."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(simple_cuelist), "--print", "--json"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["name"] == "Print Test Cuelist"
        assert len(data["cues"]) == 2
        assert data["cues"][0]["name"] == "Cue One"


class TestCLICuelistExecution:
    """Test cuelist execution command."""
    
    @pytest.fixture
    def executable_cuelist(self, tmp_path):
        """Create a minimal executable cuelist."""
        playback_file = tmp_path / "playback.json"
        playback_file.write_text(json.dumps({
            "name": "Test",
            "version": "1.0",
            "spiral": {"type": 3, "rotation_speed": 30.0},
            "media": {"mode": "none"}
        }))
        
        cuelist_file = tmp_path / "exec_cuelist.json"
        cuelist_data = {
            "name": "Execution Test",
            "version": "1.0",
            "loop_mode": "once",
            "cues": [
                {
                    "name": "Quick Cue",
                    "duration_seconds": 2.0,
                    "playback_pool": [
                        {"playback": playback_file.name, "weight": 1.0}
                    ]
                }
            ]
        }
        cuelist_file.write_text(json.dumps(cuelist_data))
        return cuelist_file
    
    def test_execute_headless(self, executable_cuelist):
        """Execute cuelist in headless mode."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(executable_cuelist), "--execute", "--duration", "1.0"],
            capture_output=True,
            text=True,
            timeout=10  # Prevent hanging
        )
        
        assert result.returncode == 0
        assert "Starting cuelist session" in result.stdout
        assert "Session completed" in result.stdout
    
    def test_execute_with_duration_override(self, executable_cuelist):
        """Duration can be overridden for testing."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(executable_cuelist), "--duration", "0.5"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        assert result.returncode == 0
        # Should complete quickly due to duration override


class TestCLICuelistErrorHandling:
    """Test error handling in CLI cuelist command."""
    
    def test_missing_cuelist_file(self, tmp_path):
        """Error when cuelist file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.json"
        
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(nonexistent), "--validate"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1
        assert "not found" in result.stdout.lower() or "error" in result.stdout.lower()
    
    def test_invalid_json(self, tmp_path):
        """Error when cuelist JSON is malformed."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ invalid json }")
        
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--load", str(bad_file), "--validate"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 1


class TestCLICuelistHelp:
    """Test CLI help and usage."""
    
    def test_cuelist_help(self):
        """cuelist --help shows usage."""
        result = subprocess.run(
            [PYTHON_EXE, "-m", "mesmerglass", "cuelist", "--help"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "--load" in result.stdout
        assert "--validate" in result.stdout
        assert "--print" in result.stdout
        assert "--execute" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
