# Custom Mode UI Control Locking - Implementation Summary

**Date:** January 24, 2025  
**Issue:** Custom modes not controlling launcher settings - launcher UI overrides mode settings  
**Solution:** Lock conflicting controls when custom mode active, unlock for built-in visuals

---

## Problem Statement

When loading a custom mode JSON (created in Visual Mode Creator), the launcher's MesmerLoom UI controls could override the mode's settings:

- **Spiral settings** (type, speed, reverse, opacity) defined in mode could be changed via sliders
- **Media settings** (cycle speed, duration) defined in mode could be adjusted via UI
- **Zoom settings** defined in mode could be modified

This meant custom modes wouldn't play identically between the **Visual Mode Creator** (where they're designed) and the **Launcher** (where they're played).

### Key Missing Feature
- **Reverse spiral** existed in Visual Mode Creator but not exposed in Launcher UI
- Custom modes with `"reverse": true` would apply it via CustomVisual, but user had no way to test reverse in launcher with built-in visuals

---

## Solution Overview

### 1. Custom Mode State Tracking
**File:** `mesmerglass/engine/visual_director.py`

Added method to detect if current visual is a custom mode:

```python
def is_custom_mode_active(self) -> bool:
    """Check if the current visual is a CustomVisual (user-created mode).
    
    Returns:
        True if current visual is CustomVisual, False otherwise
    """
    if self.current_visual is None:
        return False
    
    # Check if instance is CustomVisual
    from .custom_visual import CustomVisual
    return isinstance(self.current_visual, CustomVisual)
```

### 2. Control Locking in MesmerLoom Panel
**File:** `mesmerglass/ui/panel_mesmerloom.py`

Added two methods to lock/unlock UI controls:

#### `lock_controls()`
Disables controls that custom modes manage:
- ❌ Spiral type dropdown
- ❌ Spiral width dropdown
- ❌ Rotation speed slider
- ❌ Opacity slider (spiral intensity)
- ❌ Media mode dropdown
- ❌ Image duration spinner
- ❌ Video duration spinner
- ❌ Max zoom slider

**Still enabled:**
- ✅ Blend mode (global setting)
- ✅ Arm color button (global setting)
- ✅ Gap color button (global setting)

#### `unlock_controls()`
Re-enables all controls when switching back to built-in visual programs.

### 3. Launcher Integration
**File:** `mesmerglass/ui/launcher.py`

#### Custom Mode Load (`_on_custom_mode_requested`)
```python
if self.visual_director.select_custom_visual(mode_file):
    # Lock MesmerLoom controls so custom mode settings aren't overridden
    if self.page_mesmerloom and hasattr(self.page_mesmerloom, 'lock_controls'):
        self.page_mesmerloom.lock_controls()
        logging.getLogger(__name__).info("[CustomVisual] Locked MesmerLoom controls")
    
    # Start immediately
    self.page_visual_programs.set_playing(True, False)
    self.page_visual_programs.set_status("Playing (Custom Mode)")
```

#### Built-in Visual Start (`_on_visual_start`)
```python
if self.visual_director.select_visual(index):
    # Unlock MesmerLoom controls for built-in visuals
    # (built-in visuals don't define their own settings, so UI controls them)
    if self.page_mesmerloom and hasattr(self.page_mesmerloom, 'unlock_controls'):
        self.page_mesmerloom.unlock_controls()
        logging.getLogger(__name__).info("[visual] Unlocked MesmerLoom controls for built-in visual")
    
    self.page_visual_programs.set_playing(True, False)
```

---

## Reverse Spiral Support

### Implementation
**File:** `mesmerglass/engine/custom_visual.py` (already existed, no changes needed)

```python
def _apply_spiral_settings(self) -> None:
    """Apply spiral configuration (type, speed, opacity, reverse)."""
    # ...
    
    # Rotation speed (negative = reverse)
    rotation_speed = spiral_config.get("rotation_speed", 4.0)
    reverse = spiral_config.get("reverse", False)
    if reverse:
        rotation_speed = -abs(rotation_speed)  # Ensure negative
    if hasattr(spiral, 'set_rotation_speed'):
        spiral.set_rotation_speed(rotation_speed)
        self.logger.debug(f"[CustomVisual] Rotation speed: {rotation_speed}x")
```

**File:** `mesmerglass/mesmerloom/spiral.py` (already supported, no changes needed)

```python
def set_rotation_speed(self, speed: float):
    """Set rotation speed multiplier (negative = reverse, 4.0 = normal, up to 40.0 = very fast)."""
    # Allow negative speeds for reverse rotation
    self.rotation_speed = max(-40.0, min(40.0, float(speed)))  # Clamp to -40.0 to +40.0x
```

### Status
✅ **Reverse spiral already fully supported!**
- Visual Mode Creator can export `"reverse": true` in JSON
- CustomVisual applies negative rotation speed when `reverse: true`
- SpiralDirector handles negative speeds (counterclockwise rotation)
- **Launcher now locks controls so reverse setting isn't overridden**

---

## Test Cases

### Test 1: Custom Mode Control Locking
**File:** `test_deep_trance.json` (updated to enable reverse spiral)

```json
{
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": 2.0,
    "opacity": 0.75,
    "reverse": true  // ← CHANGED TO TRUE FOR TESTING
  }
}
```

**Steps:**
1. Launch launcher: `./.venv/bin/python run.py`
2. Go to **🌀 MesmerLoom** tab
3. Check "Enable Spiral" checkbox
4. Note that sliders/dropdowns are **enabled** (default state)
5. Go to **Visual Programs** tab
6. Click **"Load Custom Mode"**
7. Select `test_deep_trance.json`
8. **Expected Results:**
   - ✅ Mode loads without errors
   - ✅ Spiral appears and rotates **counterclockwise** (reverse)
   - ✅ Return to **🌀 MesmerLoom** tab
   - ✅ All sliders/dropdowns are now **disabled** (grayed out)
   - ✅ Color buttons remain **enabled**
9. Go to **Visual Programs** tab
10. Select a built-in visual (e.g., "Images Only")
11. Click **Start**
12. **Expected Results:**
    - ✅ Visual switches to built-in mode
    - ✅ Spiral rotates **clockwise** (normal direction)
    - ✅ MesmerLoom controls are **re-enabled**

### Test 2: Mode Creator vs Launcher Fidelity
**Create test mode in Visual Mode Creator:**
1. Set spiral to **Quadratic, 10x speed, 60% opacity, REVERSE**
2. Set media to **Images Only, cycle speed 80, 40% opacity**
3. Set text to **SUBTEXT mode, 90% opacity**
4. Set zoom to **Pulse mode, 0.2 rate**
5. Export as `fidelity_test.json`

**Play in Launcher:**
1. Load `fidelity_test.json` in launcher
2. **Verify:**
   - ✅ Spiral is quadratic shape
   - ✅ Spiral rotates **counterclockwise** (reverse)
   - ✅ Spiral rotates very fast (10x)
   - ✅ Spiral has 60% opacity (semi-transparent)
   - ✅ Images cycle quickly
   - ✅ Images have 40% opacity (faint background)
   - ✅ Text appears as scrolling wallpaper (SUBTEXT)
   - ✅ Text has 90% opacity
   - ✅ Zoom pulses in/out

**Compare:**
- Open Visual Mode Creator alongside launcher
- Load same mode in both
- Settings should match **exactly**

---

## Files Modified

1. **`mesmerglass/engine/visual_director.py`**
   - Added `is_custom_mode_active()` method

2. **`mesmerglass/ui/panel_mesmerloom.py`**
   - Added `lock_controls()` method (disables sliders/combos)
   - Added `unlock_controls()` method (re-enables controls)

3. **`mesmerglass/ui/launcher.py`**
   - Modified `_on_custom_mode_requested()` to lock controls on custom mode load
   - Modified `_on_visual_start()` to unlock controls on built-in visual start

4. **`mesmerglass/modes/test_deep_trance.json`**
   - Changed `"reverse": false` → `"reverse": true` for testing

5. **`mesmerglass/engine/custom_visual.py`** *(no changes - already correct)*
   - Already applies reverse spiral via negative rotation_speed

6. **`mesmerglass/mesmerloom/spiral.py`** *(no changes - already correct)*
   - Already supports negative rotation speeds (reverse)

---

## Visual Confirmation

### Reverse Spiral Visual Cues
**Normal (clockwise):**
```
        ___
      /     \
     |   →   |  Arms rotate clockwise
      \_____/
```

**Reverse (counterclockwise):**
```
        ___
      /     \
     |   ←   |  Arms rotate counterclockwise
      \_____/
```

Watch the spiral arms rotate. If `"reverse": true`, they should move **opposite** direction compared to built-in visuals.

### Control State Visual Cues
**Unlocked (built-in visual):**
- Sliders move smoothly when dragged
- Dropdowns expand when clicked
- Controls have normal color

**Locked (custom mode):**
- Sliders appear **grayed out**
- Dropdowns don't respond to clicks
- Controls have **disabled** appearance
- Tooltip may say "Disabled" or no response

---

## Architecture Notes

### Why Lock Instead of Hide?
- **Visibility:** User can see what settings exist, even if custom mode controls them
- **Learning:** User understands which settings are mode-defined vs global
- **Feedback:** Grayed-out controls communicate "this is controlled by the mode"

### Why Colors Stay Unlocked?
Arm color and gap color are **global aesthetic settings** that:
- Don't affect mode behavior (timing, animations, logic)
- Allow user customization without breaking mode design
- Are consistent across all modes (personal preference)

### Why Blend Mode Stays Unlocked?
Blend mode (Multiply, Screen, SoftLight) is a **global compositing setting** that:
- Doesn't affect spiral logic or media cycling
- User may want to adjust for different monitors/lighting
- Visual preference, not part of mode design

---

## Future Enhancements

1. **Visual Indicator for Custom Mode**
   - Add badge/icon to Visual Programs tab showing "Custom Mode Active"
   - Show mode name in status bar

2. **Mode Settings Preview**
   - Add read-only display of current mode settings
   - Show spiral speed, opacity, media cycle speed, etc.

3. **Quick Mode Editor**
   - Allow editing loaded mode settings without opening Mode Creator
   - Real-time preview of changes

4. **Mode Validation**
   - Check mode compatibility before loading
   - Warn if mode uses features not available in launcher

---

## Commit Message

```
Add UI control locking for custom modes

When custom mode is loaded:
- Lock MesmerLoom controls that mode defines (spiral, media, zoom)
- Prevent UI from overriding mode settings
- Keep colors/blend mode unlocked (global aesthetics)

When built-in visual is started:
- Unlock all MesmerLoom controls
- Restore user control over settings

Ensures custom modes play identically in launcher vs mode creator.
Includes reverse spiral support (already implemented, now protected).

Files:
- visual_director.py: Add is_custom_mode_active() check
- panel_mesmerloom.py: Add lock_controls()/unlock_controls()
- launcher.py: Call lock/unlock on mode/visual switch
- test_deep_trance.json: Enable reverse spiral for testing
```

---

## Ready to Test!

Run the launcher and verify:
1. ✅ Custom mode loads
2. ✅ Spiral rotates in **reverse** (counterclockwise)
3. ✅ MesmerLoom controls are **disabled**
4. ✅ Switching to built-in visual **re-enables** controls
5. ✅ Custom mode settings match Visual Mode Creator exactly
