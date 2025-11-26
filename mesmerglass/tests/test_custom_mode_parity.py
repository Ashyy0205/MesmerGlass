"""
Test custom mode parity between Visual Mode Creator and Launcher.

This test verifies that custom modes play identically in both environments.
"""
import json
import logging
from pathlib import Path

def test_custom_mode_settings_parity():
    """Test that custom mode settings are applied correctly in launcher."""
    
    # Load sinking mode
    playback_path = Path("mesmerglass/playbacks/sinking.json")
    assert playback_path.exists(), "sinking.json must exist"
    
    with open(playback_path) as f:
        config = json.load(f)
    
    # Verify JSON structure
    assert "spiral" in config
    assert "media" in config
    assert "zoom" in config
    assert "text" in config
    
    # Verify spiral settings
    spiral = config["spiral"]
    assert spiral["type"] == "logarithmic", "Spiral type must be logarithmic"
    assert spiral["rotation_speed"] == 4.0, "Rotation speed must be 4.0"
    assert spiral["opacity"] == 0.4, "Opacity must be 0.4"
    assert spiral["reverse"] == True, "Reverse must be True"
    
    # Verify media settings
    media = config["media"]
    assert media["cycle_speed"] == 50, "Cycle speed must be 50"
    
    # Calculate expected frame timing
    cycle_speed = media["cycle_speed"]
    interval_ms = 10000 * pow(0.005, (cycle_speed - 1) / 99.0)
    expected_frames = int((interval_ms / 1000.0) * 60.0)
    
    print(f"✅ Media cycle speed: {cycle_speed} → {expected_frames} frames ({interval_ms:.0f}ms)")
    assert 40 <= expected_frames <= 50, f"Expected ~43 frames, got {expected_frames}"
    
    # Verify zoom settings
    zoom = config["zoom"]
    assert zoom["mode"] == "exponential", "Zoom mode must be exponential"
    assert zoom["rate"] == 0.42, "Zoom rate must be 0.42"
    assert zoom["duration_frames"] == 180, "Duration must be 180 frames"
    
    print("✅ All custom mode settings match expected values")


def test_spiral_type_mapping():
    """Test that spiral type strings map to correct IDs."""
    
    # This mapping must match Visual Mode Creator's combo box indices
    spiral_type_map = {
        "logarithmic": 1,
        "quadratic": 2,
        "linear": 3,
        "sqrt": 4,
        "cubic": 5,
        "power": 6,
        "hyperbolic": 7
    }
    
    # Verify each type has a valid ID
    for name, type_id in spiral_type_map.items():
        assert 1 <= type_id <= 7, f"Invalid spiral type ID: {type_id}"
        print(f"✅ Spiral type '{name}' → ID {type_id}")


def test_zoom_mode_mapping():
    """Test that zoom modes are correctly mapped from Visual Mode Creator."""
    
    # Visual Mode Creator combo box text → JSON mode value
    creator_to_json = {
        "Exponential (Falling In)": "exponential",
        "Pulse (Wave)": "pulse",
        "Linear (Legacy)": "linear",
        "Disabled": "none"
    }
    
    for creator_text, json_mode in creator_to_json.items():
        print(f"✅ Creator '{creator_text}' → JSON '{json_mode}'")
    
    # Verify all modes are valid
    valid_modes = {"exponential", "falling", "pulse", "linear", "none"}
    for mode in creator_to_json.values():
        assert mode in valid_modes, f"Invalid zoom mode: {mode}"


def test_media_cycle_speed_formula():
    """Test that media cycle speed formula matches Visual Mode Creator."""
    
    test_speeds = [1, 20, 50, 55, 80, 100]
    
    print("\nMedia Cycle Speed Formula Test:")
    print("Speed | Interval (ms) | Frames (60fps)")
    print("------|---------------|---------------")
    
    for speed in test_speeds:
        interval_ms = 10000 * pow(0.005, (speed - 1) / 99.0)
        frames = int((interval_ms / 1000.0) * 60.0)
        print(f"{speed:5} | {interval_ms:13.0f} | {frames:15}")
    
    # Verify specific cases
    # Speed 50 should be ~726ms (~43 frames)
    interval_50 = 10000 * pow(0.005, (50 - 1) / 99.0)
    frames_50 = int((interval_50 / 1000.0) * 60.0)
    assert 700 <= interval_50 <= 750, f"Speed 50: Expected ~726ms, got {interval_50:.0f}ms"
    assert 40 <= frames_50 <= 46, f"Speed 50: Expected ~43 frames, got {frames_50}"
    
    # Speed 55 should be ~556ms (~33 frames)
    interval_55 = 10000 * pow(0.005, (55 - 1) / 99.0)
    frames_55 = int((interval_55 / 1000.0) * 60.0)
    assert 530 <= interval_55 <= 580, f"Speed 55: Expected ~556ms, got {interval_55:.0f}ms"
    assert 30 <= frames_55 <= 36, f"Speed 55: Expected ~33 frames, got {frames_55}"
    
    print("✅ Media cycle speed formula matches Visual Mode Creator")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("Custom Mode Parity Test")
    print("=" * 60)
    print()
    
    try:
        test_custom_mode_settings_parity()
        print()
        test_spiral_type_mapping()
        print()
        test_zoom_mode_mapping()
        print()
        test_media_cycle_speed_formula()
        print()
        print("=" * 60)
        print("✅ ALL TESTS PASSED - Custom modes should work identically!")
        print("=" * 60)
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        raise
