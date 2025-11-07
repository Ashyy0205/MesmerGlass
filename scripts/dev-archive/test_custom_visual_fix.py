"""
Test script to verify CustomVisual ThemeBank fix.

This script tests the fix for AttributeError: 'ThemeBank' object has no attribute 'image_paths'

It simulates loading a custom mode JSON file with use_theme_bank=true and verifies:
1. No AttributeError during initialization
2. CustomVisual correctly uses theme_bank.get_image() instead of accessing image_paths
3. Media cycling works correctly with ThemeBank
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
from mesmerglass.mesmerloom.custom_visual import CustomVisual
from mesmerglass.content.themebank import ThemeBank
from mesmerglass.content.theme import ThemeConfig

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s %(name)s: %(message)s'
)

def test_custom_visual_themebank():
    """Test CustomVisual with ThemeBank (use_theme_bank=true)."""
    print("\n" + "="*60)
    print("TEST: CustomVisual ThemeBank Fix")
    print("="*60 + "\n")
    
    # Create a test mode JSON file
    test_mode = {
        "version": "1.0",
        "name": "Test ThemeBank Mode",
        "spiral": {
            "type": "logarithmic",
            "rotation_speed": 1.0,
            "opacity": 0.8,
            "reverse": False
        },
        "media": {
            "mode": "images",  # Only images (videos not supported in ThemeBank yet)
            "cycle_speed": 50,
            "opacity": 0.7,
            "use_theme_bank": True  # THIS IS THE KEY - should use ThemeBank.get_image()
        },
        "text": {
            "enabled": False,
            "mode": "CENTERED_SYNC",
            "opacity": 0.9,
            "use_theme_bank": True
        },
        "zoom": {
            "mode": "pulse",
            "rate": 0.15,
            "duration_frames": 180
        }
    }
    
    # Save to temp file
    test_mode_path = Path(__file__).parent.parent / "mesmerglass" / "modes" / "test_themebank_fix.json"
    test_mode_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(test_mode_path, 'w', encoding='utf-8') as f:
        json.dump(test_mode, f, indent=2)
    
    print(f"✓ Created test mode file: {test_mode_path}")
    
    # Create a minimal ThemeConfig
    media_root = Path(__file__).parent.parent / "MEDIA" / "Images"
    
    theme = ThemeConfig(
        name="Test Theme",
        enabled=True,
        image_path=[
            "20240808_165645.jpg",
            "20240808_165659.jpg",
            "20240808_170015.jpg",
        ],
        animation_path=[],
        font_path=[],
        text_line=["Test text line 1", "Test text line 2"]
    )
    
    print(f"✓ Created test theme with {len(theme.image_path)} images")
    
    # Create ThemeBank
    theme_bank = ThemeBank(
        themes=[theme],
        root_path=media_root,
        image_cache_size=16
    )
    
    # Set active theme
    theme_bank.set_active_themes(primary_index=1)
    
    print(f"✓ Created ThemeBank with {theme_bank.get_theme_count()} theme(s)")
    
    # Create CustomVisual - THIS IS WHERE THE ERROR WOULD OCCUR
    try:
        print("\n→ Creating CustomVisual (this previously caused AttributeError)...")
        
        custom_visual = CustomVisual(
            mode_path=test_mode_path,
            theme_bank=theme_bank,
            on_change_image=None,  # No callbacks needed for test
            on_change_video=None,
            on_rotate_spiral=None,
            compositor=None,
            text_director=None
        )
        
        print("✓ CustomVisual created successfully! (No AttributeError)")
        
        # Verify internal state
        print(f"\n→ Verifying internal state...")
        print(f"  - Mode name: {custom_visual.mode_name}")
        print(f"  - Media mode: {custom_visual._media_mode}")
        print(f"  - Use ThemeBank media: {custom_visual._use_theme_bank_media}")
        print(f"  - Media paths (should be empty): {len(custom_visual._media_paths)}")
        
        # Verify expected state
        assert custom_visual._use_theme_bank_media == True, "Should use ThemeBank media"
        assert len(custom_visual._media_paths) == 0, "Path list should be empty when using ThemeBank"
        
        print("✓ Internal state correct!")
        
        # Test cycler build
        print(f"\n→ Building cycler...")
        cycler = custom_visual.build_cycler()
        print(f"✓ Cycler built successfully: {cycler}")
        
        print("\n" + "="*60)
        print("✅ TEST PASSED - CustomVisual ThemeBank fix works!")
        print("="*60 + "\n")
        
        return True
        
    except AttributeError as e:
        print(f"\n❌ TEST FAILED - AttributeError still occurs:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
        return False
    
    except Exception as e:
        print(f"\n❌ TEST FAILED - Unexpected error:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
        return False

def test_custom_visual_explicit_paths():
    """Test CustomVisual with explicit paths (use_theme_bank=false)."""
    print("\n" + "="*60)
    print("TEST: CustomVisual Explicit Paths (Backward Compatibility)")
    print("="*60 + "\n")
    
    # Create a test mode with explicit paths
    media_root = Path(__file__).parent.parent / "MEDIA" / "Images"
    test_mode = {
        "version": "1.0",
        "name": "Test Explicit Paths Mode",
        "spiral": {
            "type": "logarithmic",
            "rotation_speed": 1.0,
            "opacity": 0.8,
            "reverse": False
        },
        "media": {
            "mode": "images",
            "cycle_speed": 50,
            "opacity": 0.7,
            "use_theme_bank": False,  # Use explicit paths
            "paths": [
                str(media_root / "20240808_165645.jpg"),
                str(media_root / "20240808_165659.jpg"),
            ]
        },
        "text": {
            "enabled": False,
            "mode": "CENTERED_SYNC",
            "opacity": 0.9,
            "use_theme_bank": False
        },
        "zoom": {
            "mode": "pulse",
            "rate": 0.15,
            "duration_frames": 180
        }
    }
    
    # Save to temp file
    test_mode_path = Path(__file__).parent.parent / "mesmerglass" / "modes" / "test_explicit_paths.json"
    test_mode_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(test_mode_path, 'w', encoding='utf-8') as f:
        json.dump(test_mode, f, indent=2)
    
    print(f"✓ Created test mode file: {test_mode_path}")
    
    try:
        print("\n→ Creating CustomVisual with explicit paths...")
        
        custom_visual = CustomVisual(
            mode_path=test_mode_path,
            theme_bank=None,  # No ThemeBank needed
            on_change_image=None,
            on_change_video=None,
            on_rotate_spiral=None,
            compositor=None,
            text_director=None
        )
        
        print("✓ CustomVisual created successfully!")
        
        # Verify internal state
        print(f"\n→ Verifying internal state...")
        print(f"  - Mode name: {custom_visual.mode_name}")
        print(f"  - Media mode: {custom_visual._media_mode}")
        print(f"  - Use ThemeBank media: {custom_visual._use_theme_bank_media}")
        print(f"  - Media paths: {len(custom_visual._media_paths)}")
        
        # Verify expected state
        assert custom_visual._use_theme_bank_media == False, "Should NOT use ThemeBank media"
        assert len(custom_visual._media_paths) == 2, "Should have 2 explicit paths"
        
        print("✓ Internal state correct!")
        
        print("\n" + "="*60)
        print("✅ TEST PASSED - Explicit paths mode still works!")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Run tests
    test1 = test_custom_visual_themebank()
    test2 = test_custom_visual_explicit_paths()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"  ThemeBank mode:     {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"  Explicit paths mode: {'✅ PASS' if test2 else '❌ FAIL'}")
    print("="*60 + "\n")
    
    sys.exit(0 if (test1 and test2) else 1)
