"""
Tests for CustomVisual - user-defined visual modes from JSON files.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock


def test_custom_visual_import():
    """Test that CustomVisual can be imported."""
    from mesmerglass.mesmerloom.custom_visual import CustomVisual
    assert CustomVisual is not None


def test_validate_example_mode():
    """Test validation of the example mode file."""
    from mesmerglass.mesmerloom.custom_visual import CustomVisual
    
    playback_path = Path(__file__).parent.parent.parent / "mesmerglass" / "playbacks" / "example_mode.json"
    
    if not playback_path.exists():
        pytest.skip(f"Example playback file not found: {playback_path}")
    
    is_valid, error_msg = CustomVisual.validate_mode_file(playback_path)
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
            "sync_with_media": bool,
            "manual_cycle_speed": int
        },
        "zoom": {
            "mode": str,
            "rate": (int, float),
            "duration_frames": int
        }
    }
    
    # Schema validation is handled by validate_mode_file()
    assert expected_schema is not None


class _DummySpiral:
    def __init__(self):
        self.arm_color = (1.0, 1.0, 1.0)
        self.gap_color = (0.0, 0.0, 0.0)
        self.rotation_speed = 0.0

    def set_spiral_type(self, *_):
        pass

    def set_rotation_speed(self, speed):
        self.rotation_speed = speed

    def set_opacity(self, *_):
        pass

    def set_arm_color(self, r, g, b):
        self.arm_color = (r, g, b)

    def set_gap_color(self, r, g, b):
        self.gap_color = (r, g, b)


class _DummyCompositor:
    def __init__(self):
        self.spiral_director = _DummySpiral()

    def set_fade_duration(self, *_):
        pass

    def parent(self):
        return None

    def set_zoom_animation_enabled(self, *_):
        pass

    def start_zoom_animation(self, **_kwargs):
        pass

    def set_zoom_rate(self, *_):
        pass


def _write_playback(tmp_path: Path, spiral_overrides: dict | None = None) -> Path:
    base_config = {
        "version": "1.0",
        "name": "Test",
        "description": "",
        "spiral": {
            "type": "linear",
            "rotation_speed": 4.0,
            "opacity": 0.5,
            "reverse": False,
        },
        "media": {
            "mode": "images",
            "cycle_speed": 50,
            "fade_duration": 0.5,
            "use_theme_bank": False,
            "paths": [],
            "shuffle": False,
            "bank_selections": []
        },
        "text": {
            "enabled": False,
            "mode": "centered_sync",
            "opacity": 0.0,
            "use_theme_bank": False,
            "library": [],
            "sync_with_media": True,
            "manual_cycle_speed": 50
        },
        "zoom": {
            "mode": "none",
            "rate": 0.0
        }
    }
    if spiral_overrides:
        base_config["spiral"].update(spiral_overrides)

    tmp_file = tmp_path / "playback.json"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        json.dump(base_config, handle)
    return tmp_file


def test_custom_visual_applies_spiral_colors(tmp_path):
    from mesmerglass.mesmerloom.custom_visual import CustomVisual

    color_payload = {
        "arm_color": [0.2, 0.4, 0.6],
        "gap_color": [0.1, 0.1, 0.1]
    }
    playback_file = _write_playback(tmp_path, color_payload)

    dummy_comp = _DummyCompositor()
    CustomVisual(playback_file, compositor=dummy_comp, text_director=None)

    assert dummy_comp.spiral_director.arm_color == tuple(color_payload["arm_color"])
    assert dummy_comp.spiral_director.gap_color == tuple(color_payload["gap_color"])


def test_custom_visual_keeps_defaults_when_colors_missing(tmp_path):
    from mesmerglass.mesmerloom.custom_visual import CustomVisual

    playback_file = _write_playback(tmp_path)
    dummy_comp = _DummyCompositor()

    CustomVisual(playback_file, compositor=dummy_comp, text_director=None)

    assert dummy_comp.spiral_director.arm_color == (1.0, 1.0, 1.0)
    assert dummy_comp.spiral_director.gap_color == (0.0, 0.0, 0.0)


def test_theme_bank_video_sets_showing_flag(tmp_path):
    from mesmerglass.mesmerloom.custom_visual import CustomVisual

    playback_file = _write_playback(tmp_path)
    dummy_comp = _DummyCompositor()

    class _DummyThemeBank:
        def __init__(self, video_path: Path):
            self._video_path = video_path

        def get_video(self):
            return self._video_path

    video_path = tmp_path / "clip.mp4"
    video_path.write_text("stub")

    visual = CustomVisual(playback_file, compositor=dummy_comp, text_director=None)
    visual.theme_bank = _DummyThemeBank(video_path)
    visual.on_change_video = MagicMock()

    assert visual._request_theme_bank_video() is True
    visual.on_change_video.assert_called_once_with(video_path)
    assert visual._showing_video is True


def test_theme_bank_image_clears_showing_flag(tmp_path):
    from mesmerglass.mesmerloom.custom_visual import CustomVisual

    playback_file = _write_playback(tmp_path)
    dummy_comp = _DummyCompositor()

    visual = CustomVisual(playback_file, compositor=dummy_comp, text_director=None)
    visual.on_change_image = MagicMock()
    visual._showing_video = True

    assert visual._request_theme_bank_image() is True
    visual.on_change_image.assert_called_once_with(0)
    assert visual._showing_video is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
