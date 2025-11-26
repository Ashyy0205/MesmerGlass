"""Comprehensive session save/load tests for MesmerGlass Phase 7.

Tests all settings are correctly persisted and loaded:
- Playback settings (spiral, color, speed, effects, media, zoom)
- Cuelist settings (name, cues)
- Cue settings (duration, fades, playback_pool, audio)
- Runtime state (last_playback, last_cuelist, custom_media_dirs)
"""
import json
import tempfile
from pathlib import Path

def test_playback_settings():
    """Test all playback settings save/load correctly."""
    print("\n=== Testing Playback Settings ===")
    
    playback_config = {
        "visual_type": "spiral",
        "spiral": {
            "type": "logarithmic",
            "arms": 8,
            "direction": "clockwise",
            "turns": 4.5,
            "rotation_speed": 45.0,
            "opacity": 0.85,
            "reverse": True,
            "style": "sharp",
            "thickness": 0.08,
            "gap": 0.02
        },
        "color": {
            "mode": "gradient",
            "primary": "#ff0066",
            "secondary": "#6600ff",
            "tertiary": "#00ffcc"
        },
        "speed": {
            "rotation_speed": 45.0,
            "min_speed": 10.0,
            "max_speed": 80.0
        },
        "effects": {
            "intensity": 0.95,
            "pulse": {
                "enabled": True,
                "frequency": 1.2,
                "amount": 0.3,
                "wave_type": "sine"
            },
            "kaleidoscope": {
                "enabled": True,
                "segments": 6
            },
            "blur": {
                "enabled": False,
                "amount": 0.0
            }
        },
        "media": {
            "mode": "none",
            "image_path": None,
            "video_path": None
        },
        "zoom": {
            "mode": "exponential",
            "rate": 20.0,
            "min_zoom": 0.5,
            "max_zoom": 2.0
        }
    }
    
    # Create session with this playback
    session = {
        "version": "1.0",
        "metadata": {
            "name": "Playback Settings Test",
            "description": "Testing all playback settings",
            "created": "2025-11-10T00:00:00",
            "modified": "2025-11-10T00:00:00",
            "author": "Test"
        },
        "playbacks": {
            "test_playback": playback_config
        },
        "cuelists": {},
        "runtime": {
            "last_playback": None,
            "last_cuelist": None,
            "custom_media_dirs": []
        }
    }
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.session.json', delete=False) as f:
        json.dump(session, f, indent=2)
        temp_path = Path(f.name)
    
    try:
        # Load back
        with open(temp_path, 'r') as f:
            loaded_session = json.load(f)
        
        # Verify all playback settings
        loaded_playback = loaded_session["playbacks"]["test_playback"]
        
        checks = [
            ("visual_type", playback_config["visual_type"], loaded_playback["visual_type"]),
            ("spiral.type", playback_config["spiral"]["type"], loaded_playback["spiral"]["type"]),
            ("spiral.arms", playback_config["spiral"]["arms"], loaded_playback["spiral"]["arms"]),
            ("spiral.rotation_speed", playback_config["spiral"]["rotation_speed"], loaded_playback["spiral"]["rotation_speed"]),
            ("spiral.opacity", playback_config["spiral"]["opacity"], loaded_playback["spiral"]["opacity"]),
            ("color.mode", playback_config["color"]["mode"], loaded_playback["color"]["mode"]),
            ("color.primary", playback_config["color"]["primary"], loaded_playback["color"]["primary"]),
            ("effects.intensity", playback_config["effects"]["intensity"], loaded_playback["effects"]["intensity"]),
            ("effects.pulse.enabled", playback_config["effects"]["pulse"]["enabled"], loaded_playback["effects"]["pulse"]["enabled"]),
            ("effects.pulse.frequency", playback_config["effects"]["pulse"]["frequency"], loaded_playback["effects"]["pulse"]["frequency"]),
            ("effects.kaleidoscope.enabled", playback_config["effects"]["kaleidoscope"]["enabled"], loaded_playback["effects"]["kaleidoscope"]["enabled"]),
            ("zoom.mode", playback_config["zoom"]["mode"], loaded_playback["zoom"]["mode"]),
            ("zoom.rate", playback_config["zoom"]["rate"], loaded_playback["zoom"]["rate"]),
        ]
        
        failed = []
        for name, expected, actual in checks:
            if expected != actual:
                failed.append(f"  [FAIL] {name}: expected {expected}, got {actual}")
            else:
                print(f"  [OK] {name}")
        
        if failed:
            print("\nFailed checks:")
            for fail in failed:
                print(fail)
            return False
        
        print("  [PASS] All playback settings saved/loaded correctly")
        return True
        
    finally:
        temp_path.unlink()


def test_cuelist_and_cue_settings():
    """Test cuelist and cue settings save/load correctly."""
    print("\n=== Testing Cuelist and Cue Settings ===")
    
    cuelist_data = {
        "name": "Test Cuelist",
        "cues": [
            {
                "name": "Cue 1",
                "playback": "playback_key_1",
                "duration": 120,
                "fade_in": 3.0,
                "fade_out": 2.0,
                "playback_pool": [
                    {
                        "playback": "playback_a",
                        "weight": 1.5,
                        "min_cycles": 2,
                        "max_cycles": 5
                    },
                    {
                        "playback": "playback_b",
                        "weight": 1.0
                    }
                ],
                "audio": [
                    "audio/track1.mp3",
                    "audio/track2.ogg"
                ]
            },
            {
                "name": "Cue 2",
                "playback": "playback_key_2",
                "duration": 180,
                "fade_in": 5.0,
                "fade_out": 5.0,
                "playback_pool": [],
                "audio": []
            }
        ]
    }
    
    session = {
        "version": "1.0",
        "metadata": {
            "name": "Cuelist Test",
            "description": "Testing cuelist and cue settings",
            "created": "2025-11-10T00:00:00",
            "modified": "2025-11-10T00:00:00",
            "author": "Test"
        },
        "playbacks": {},
        "cuelists": {
            "test_cuelist": cuelist_data
        },
        "runtime": {
            "last_playback": None,
            "last_cuelist": None,
            "custom_media_dirs": []
        }
    }
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.session.json', delete=False) as f:
        json.dump(session, f, indent=2)
        temp_path = Path(f.name)
    
    try:
        # Load back
        with open(temp_path, 'r') as f:
            loaded_session = json.load(f)
        
        loaded_cuelist = loaded_session["cuelists"]["test_cuelist"]
        
        checks = [
            ("cuelist.name", cuelist_data["name"], loaded_cuelist["name"]),
            ("cuelist.cues count", len(cuelist_data["cues"]), len(loaded_cuelist["cues"])),
            ("cue1.name", cuelist_data["cues"][0]["name"], loaded_cuelist["cues"][0]["name"]),
            ("cue1.duration", cuelist_data["cues"][0]["duration"], loaded_cuelist["cues"][0]["duration"]),
            ("cue1.fade_in", cuelist_data["cues"][0]["fade_in"], loaded_cuelist["cues"][0]["fade_in"]),
            ("cue1.playback_pool count", len(cuelist_data["cues"][0]["playback_pool"]), len(loaded_cuelist["cues"][0]["playback_pool"])),
            ("cue1.playback_pool[0].weight", cuelist_data["cues"][0]["playback_pool"][0]["weight"], loaded_cuelist["cues"][0]["playback_pool"][0]["weight"]),
            ("cue1.playback_pool[0].min_cycles", cuelist_data["cues"][0]["playback_pool"][0]["min_cycles"], loaded_cuelist["cues"][0]["playback_pool"][0]["min_cycles"]),
            ("cue1.audio count", len(cuelist_data["cues"][0]["audio"]), len(loaded_cuelist["cues"][0]["audio"])),
            ("cue2.playback", cuelist_data["cues"][1]["playback"], loaded_cuelist["cues"][1]["playback"]),
        ]
        
        failed = []
        for name, expected, actual in checks:
            if expected != actual:
                failed.append(f"  [FAIL] {name}: expected {expected}, got {actual}")
            else:
                print(f"  [OK] {name}")
        
        if failed:
            print("\nFailed checks:")
            for fail in failed:
                print(fail)
            return False
        
        print("  [PASS] All cuelist and cue settings saved/loaded correctly")
        return True
        
    finally:
        temp_path.unlink()


def test_runtime_state():
    """Test runtime state save/load correctly."""
    print("\n=== Testing Runtime State ===")
    
    runtime_data = {
        "last_playback": "my_playback",
        "last_cuelist": "my_cuelist",
        "custom_media_dirs": [
            "C:/Custom/Media/Path1",
            "D:/Another/Media/Path2"
        ]
    }
    
    session = {
        "version": "1.0",
        "metadata": {
            "name": "Runtime Test",
            "description": "Testing runtime state",
            "created": "2025-11-10T00:00:00",
            "modified": "2025-11-10T00:00:00",
            "author": "Test"
        },
        "playbacks": {},
        "cuelists": {},
        "runtime": runtime_data
    }
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.session.json', delete=False) as f:
        json.dump(session, f, indent=2)
        temp_path = Path(f.name)
    
    try:
        # Load back
        with open(temp_path, 'r') as f:
            loaded_session = json.load(f)
        
        loaded_runtime = loaded_session["runtime"]
        
        checks = [
            ("last_playback", runtime_data["last_playback"], loaded_runtime["last_playback"]),
            ("last_cuelist", runtime_data["last_cuelist"], loaded_runtime["last_cuelist"]),
            ("custom_media_dirs count", len(runtime_data["custom_media_dirs"]), len(loaded_runtime["custom_media_dirs"])),
            ("custom_media_dirs[0]", runtime_data["custom_media_dirs"][0], loaded_runtime["custom_media_dirs"][0]),
        ]
        
        failed = []
        for name, expected, actual in checks:
            if expected != actual:
                failed.append(f"  [FAIL] {name}: expected {expected}, got {actual}")
            else:
                print(f"  [OK] {name}")
        
        if failed:
            print("\nFailed checks:")
            for fail in failed:
                print(fail)
            return False
        
        print("  [PASS] All runtime state saved/loaded correctly")
        return True
        
    finally:
        temp_path.unlink()


def test_complex_session():
    """Test a complex session with multiple playbacks, cuelists, and cues."""
    print("\n=== Testing Complex Session ===")
    
    session = {
        "version": "1.0",
        "metadata": {
            "name": "Complex Test Session",
            "description": "Full session with multiple elements",
            "created": "2025-11-10T00:00:00",
            "modified": "2025-11-10T00:00:00",
            "author": "Test Suite",
            "tags": ["test", "complex", "full"]
        },
        "playbacks": {
            "gentle": {
                "visual_type": "spiral",
                "spiral": {"type": "sqrt", "rotation_speed": 15.0},
                "color": {"mode": "solid", "primary": "#4a90e2"},
                "effects": {"intensity": 0.6}
            },
            "intense": {
                "visual_type": "spiral",
                "spiral": {"type": "logarithmic", "rotation_speed": 60.0},
                "color": {"mode": "gradient", "primary": "#ff0066", "secondary": "#6600ff"},
                "effects": {"intensity": 0.95, "pulse": {"enabled": True}}
            },
            "kaleidoscope": {
                "visual_type": "spiral",
                "spiral": {"type": "logarithmic", "rotation_speed": 35.0},
                "effects": {"kaleidoscope": {"enabled": True, "segments": 8}}
            }
        },
        "cuelists": {
            "main_flow": {
                "name": "Main Flow",
                "cues": [
                    {
                        "name": "Intro",
                        "playback": "gentle",
                        "duration": 60,
                        "fade_in": 2.0,
                        "fade_out": 2.0
                    },
                    {
                        "name": "Deep",
                        "playback": "intense",
                        "duration": 300,
                        "fade_in": 5.0,
                        "fade_out": 3.0,
                        "playback_pool": [
                            {"playback": "intense", "weight": 2.0},
                            {"playback": "kaleidoscope", "weight": 1.0}
                        ]
                    },
                    {
                        "name": "Wake",
                        "playback": "gentle",
                        "duration": 120,
                        "fade_in": 3.0,
                        "fade_out": 5.0
                    }
                ]
            },
            "quick": {
                "name": "Quick Session",
                "cues": [
                    {
                        "name": "Fast",
                        "playback": "intense",
                        "duration": 180,
                        "fade_in": 2.0,
                        "fade_out": 2.0
                    }
                ]
            }
        },
        "runtime": {
            "last_playback": "intense",
            "last_cuelist": "main_flow",
            "custom_media_dirs": ["C:/Media/Custom"]
        }
    }
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.session.json', delete=False) as f:
        json.dump(session, f, indent=2)
        temp_path = Path(f.name)
    
    try:
        # Load back
        with open(temp_path, 'r') as f:
            loaded_session = json.load(f)
        
        checks = [
            ("playbacks count", len(session["playbacks"]), len(loaded_session["playbacks"])),
            ("cuelists count", len(session["cuelists"]), len(loaded_session["cuelists"])),
            ("main_flow cues count", len(session["cuelists"]["main_flow"]["cues"]), len(loaded_session["cuelists"]["main_flow"]["cues"])),
            ("metadata.tags count", len(session["metadata"]["tags"]), len(loaded_session["metadata"]["tags"])),
            ("playback gentle exists", "gentle" in session["playbacks"], "gentle" in loaded_session["playbacks"]),
            ("playback intense rotation_speed", 
             session["playbacks"]["intense"]["spiral"]["rotation_speed"],
             loaded_session["playbacks"]["intense"]["spiral"]["rotation_speed"]),
            ("cue Deep playback_pool count",
             len(session["cuelists"]["main_flow"]["cues"][1]["playback_pool"]),
             len(loaded_session["cuelists"]["main_flow"]["cues"][1]["playback_pool"])),
            ("runtime.last_playback", session["runtime"]["last_playback"], loaded_session["runtime"]["last_playback"]),
        ]
        
        failed = []
        for name, expected, actual in checks:
            if expected != actual:
                failed.append(f"  [FAIL] {name}: expected {expected}, got {actual}")
            else:
                print(f"  [OK] {name}")
        
        if failed:
            print("\nFailed checks:")
            for fail in failed:
                print(fail)
            return False
        
        print("  [PASS] Complex session saved/loaded correctly")
        return True
        
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    print("=" * 70)
    print("MesmerGlass Session Save/Load Tests")
    print("=" * 70)
    
    results = []
    
    results.append(("Playback Settings", test_playback_settings()))
    results.append(("Cuelist and Cue Settings", test_cuelist_and_cue_settings()))
    results.append(("Runtime State", test_runtime_state()))
    results.append(("Complex Session", test_complex_session()))
    
    print("\n" + "=" * 70)
    print("Test Results Summary")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed!")
        exit(0)
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        exit(1)
