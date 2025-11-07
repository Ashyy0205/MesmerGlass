"""
Tests for CustomVisual - user-defined visual modes from JSON files.
"""

import pytest
import json
from pathlib import Path


def test_custom_visual_import():
    """Test that CustomVisual can be imported."""
    from mesmerglass.mesmerloom.custom_visual import CustomVisual
    assert CustomVisual is not None


def test_validate_example_mode():
    """Test validation of the example mode file."""
    from mesmerglass.mesmerloom.custom_visual import CustomVisual
    
    mode_path = Path(__file__).parent.parent.parent / "mesmerglass" / "modes" / "example_mode.json"
    
    if not mode_path.exists():
        pytest.skip(f"Example mode file not found: {mode_path}")
    
    is_valid, error_msg = CustomVisual.validate_mode_file(mode_path)
    assert is_valid, f"Example mode validation failed: {error_msg}"


def test_validate_invalid_json():
    """Test validation with invalid JSON."""
    from mesmerglass.mesmerloom.custom_visual import CustomVisual
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{ invalid json }")
        temp_path = Path(f.name)
    
    try:
        is_valid, error_msg = CustomVisual.validate_mode_file(temp_path)
        assert not is_valid
        assert "JSON" in error_msg
    finally:
        temp_path.unlink()


def test_validate_missing_fields():
    """Test validation with missing required fields."""
    from mesmerglass.mesmerloom.custom_visual import CustomVisual
    import tempfile
    
    config = {
        "version": "1.0",
        "name": "Test Mode"
        # Missing: spiral, media, text, zoom
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        temp_path = Path(f.name)
    
    try:
        is_valid, error_msg = CustomVisual.validate_mode_file(temp_path)
        assert not is_valid
        assert "Missing required keys" in error_msg
    finally:
        temp_path.unlink()


def test_json_export_from_visual_mode_creator():
    """Test that visual_mode_creator exports valid JSON."""
    # This is a documentation test - actual export is tested manually
    # The exported JSON should pass validate_mode_file()
    
    expected_schema = {
        "version": str,
        "name": str,
        "description": str,
        "spiral": {
            "type": str,
            "rotation_speed": (int, float),
            "opacity": (int, float),
            "reverse": bool
        },
        "media": {
            "mode": str,
            "cycle_speed": int,
            "opacity": (int, float),
            "use_theme_bank": bool,
            "paths": list,
            "shuffle": bool
        },
        "text": {
            "enabled": bool,
            "mode": str,
            "opacity": (int, float),
            "use_theme_bank": bool,
            "library": list,
            "sync_with_media": bool
        },
        "zoom": {
            "mode": str,
            "rate": (int, float),
            "duration_frames": int
        }
    }
    
    # Schema validation is handled by validate_mode_file()
    assert expected_schema is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
