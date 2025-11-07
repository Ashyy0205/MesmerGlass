"""
Test Workflow: Create mode in visual_mode_creator → Export to JSON → Import in launcher

This script will:
1. Create a sample JSON mode file programmatically
2. Show how to load it in the launcher
3. Verify the mode loads correctly

Moved to scripts/dev-archive as a developer-only utility.
"""

import json
from pathlib import Path
from datetime import datetime

# Create a test mode with distinctive settings
test_mode = {
    "version": "1.0",
    "name": "Test Deep Trance",
    "description": "Test mode created for validation - slow spiral, subtext, zoom pulse",
    
    "spiral": {
        "type": "logarithmic",  # Smooth, classic spiral
        "rotation_speed": 2.0,  # Moderate speed
        "opacity": 0.75,
        "reverse": False
    },
    
    "media": {
        "mode": "images",  # Images only
        "cycle_speed": 30,  # Medium speed
        "opacity": 0.6,  # Partially transparent
        "use_theme_bank": True,
        "paths": [],
        "shuffle": False
    },
    
    "text": {
        "enabled": True,
        "mode": "subtext",  # Scrolling wallpaper mode
        "opacity": 0.8,
        "use_theme_bank": True,
        "library": [],
        "sync_with_media": True
    },
    
    "zoom": {
        "mode": "pulse",  # Zoom in/out cycling
        "rate": 0.15,
        "duration_frames": 180
    }
}

# Save to modes directory
modes_dir = Path(__file__).parents[2] / "mesmerglass" / "modes"
modes_dir.mkdir(parents=True, exist_ok=True)

output_file = modes_dir / "test_deep_trance.json"

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(test_mode, f, indent=2, ensure_ascii=False)

print("=" * 80)
print("TEST MODE CREATED")
print("=" * 80)
print(f"\n✅ Created: {output_file}")
print(f"   Size: {output_file.stat().st_size} bytes")
print(f"\nMode Summary:")
print(f"  Name: {test_mode['name']}")
print(f"  Spiral: {test_mode['spiral']['type']} @ {test_mode['spiral']['rotation_speed']}x speed")
print(f"  Media: {test_mode['media']['mode']} (speed={test_mode['media']['cycle_speed']})")
print(f"  Text: {test_mode['text']['mode']} ({'enabled' if test_mode['text']['enabled'] else 'disabled'})")
print(f"  Zoom: {test_mode['zoom']['mode']} @ {test_mode['zoom']['rate']} rate")

print("\n" + "=" * 80)
print("TESTING IN LAUNCHER")
print("=" * 80)
print("\nSteps to test:")
print("1. Run: python -m mesmerglass run")
print("2. Open MesmerLoom panel and load: test_deep_trance.json")
print("3. Verify spiral/text/zoom/media as described above")
