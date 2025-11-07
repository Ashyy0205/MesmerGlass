# Custom Mode vs Built-in Visual Isolation - Fix

**Date:** January 24, 2025  
**Issue:** Visual program dropdown at top of Visual Programs page was overriding custom mode settings  
**Root Cause:** Custom mode loaded but visual dropdown remained enabled and could be changed  
**Solution:** Lock visual dropdown when custom mode active, unlock for built-in visuals

---

## Problem

When loading a custom mode:
1. Custom mode loads correctly with all its settings (spiral, media, text, zoom)
2. **But:** Visual program dropdown at top of page is still **enabled**
3. User can select a different built-in visual from dropdown
4. This triggers `visualSelected` signal and could confuse the system
5. Even worse: If user clicks "Start" after changing dropdown, it loads the built-in visual **instead of** the custom mode

**Result:** Custom mode settings get overridden by built-in visual program from dropdown.

---

## Solution

### Added Visual Selector Locking

**File:** `mesmerglass/ui/pages/visual_programs.py`

```python
def lock_visual_selector(self) -> None:
    """Disable visual program dropdown when custom mode is active.
    
    Custom modes bypass the visual program selector - they load directly
    via CustomVisual. Disabling the dropdown prevents confusion and
    ensures custom mode settings aren't overridden by built-in visuals.
    """
    self.visual_combo.setEnabled(False)

def unlock_visual_selector(self) -> None:
    """Re-enable visual program dropdown when switching to built-in visuals.
    
    Built-in visuals use the dropdown selector, so it needs to be enabled
    for normal operation.
    """
    self.visual_combo.setEnabled(True)
```

### Integrated into Launcher

**File:** `mesmerglass/ui/launcher.py`

#### When Custom Mode Loads
```python
if self.visual_director.select_custom_visual(mode_file):
    # Lock MesmerLoom controls
    if self.page_mesmerloom and hasattr(self.page_mesmerloom, 'lock_controls'):
        self.page_mesmerloom.lock_controls()
    
    # NEW: Lock visual program selector
    if self.page_visual_programs and hasattr(self.page_visual_programs, 'lock_visual_selector'):
        self.page_visual_programs.lock_visual_selector()
        logging.getLogger(__name__).info("[CustomVisual] Locked visual program selector")
```

#### When Built-in Visual Starts
```python
if self.visual_director.select_visual(index):
    # Unlock MesmerLoom controls
    if self.page_mesmerloom and hasattr(self.page_mesmerloom, 'unlock_controls'):
        self.page_mesmerloom.unlock_controls()
    
    # NEW: Unlock visual program selector
    if self.page_visual_programs and hasattr(self.page_visual_programs, 'unlock_visual_selector'):
        self.page_visual_programs.unlock_visual_selector()
        logging.getLogger(__name__).info("[visual] Unlocked visual program selector")
```

---

## Complete Control Locking Matrix

### When Custom Mode Active

| Control Location | Control Type | State | Reason |
|-----------------|--------------|-------|--------|
| **Visual Programs Tab** | Visual dropdown | 🔒 **LOCKED** | Custom mode bypasses dropdown |
| **MesmerLoom Tab** | Spiral Type | 🔒 **LOCKED** | Custom mode defines spiral |
| **MesmerLoom Tab** | Spiral Width | 🔒 **LOCKED** | Custom mode defines spiral |
| **MesmerLoom Tab** | Rotation Speed | 🔒 **LOCKED** | Custom mode defines speed |
| **MesmerLoom Tab** | Opacity | 🔒 **LOCKED** | Custom mode defines opacity |
| **MesmerLoom Tab** | Media Mode | 🔒 **LOCKED** | Custom mode defines media |
| **MesmerLoom Tab** | Image Duration | 🔒 **LOCKED** | Custom mode defines cycle speed |
| **MesmerLoom Tab** | Video Duration | 🔒 **LOCKED** | Custom mode defines cycle speed |
| **MesmerLoom Tab** | Max Zoom | 🔒 **LOCKED** | Custom mode defines zoom |
| **MesmerLoom Tab** | Blend Mode | ✅ **UNLOCKED** | Global aesthetic setting |
| **MesmerLoom Tab** | Arm Color | ✅ **UNLOCKED** | Global aesthetic setting |
| **MesmerLoom Tab** | Gap Color | ✅ **UNLOCKED** | Global aesthetic setting |

### When Built-in Visual Active

| Control Location | Control Type | State | Reason |
|-----------------|--------------|-------|--------|
| **Visual Programs Tab** | Visual dropdown | ✅ **UNLOCKED** | Used to select visual |
| **MesmerLoom Tab** | All spiral controls | ✅ **UNLOCKED** | User controls settings |
| **MesmerLoom Tab** | All media controls | ✅ **UNLOCKED** | User controls settings |
| **MesmerLoom Tab** | All zoom controls | ✅ **UNLOCKED** | User controls settings |

---

## Testing

### Test 1: Custom Mode Isolation
1. Launch launcher
2. Go to **Visual Programs** tab
3. Note the **visual dropdown is enabled** at top
4. Click **"Load Custom Mode"** → Select `test_deep_trance.json`
5. **Verify:**
   - ✅ Visual dropdown is now **disabled (grayed out)**
   - ✅ Spiral rotates in **reverse** (counterclockwise)
   - ✅ Custom mode settings are active
6. Try to click the visual dropdown
7. **Verify:** It doesn't respond (disabled)

### Test 2: Built-in Visual Switch
1. With custom mode still loaded (dropdown disabled)
2. Select any built-in visual from dropdown... wait, it's disabled!
3. Actually, there's no way to switch back via dropdown (this is intentional)
4. **To switch back:** Stop the custom mode first, or restart launcher
5. OR: We could add a "Stop Custom Mode" button

**Note:** This reveals a UX issue - user can't easily switch from custom mode back to built-in visual. Need to add a way to do that.

### Test 3: Start Button Behavior
1. Load custom mode (dropdown disabled)
2. Custom mode is playing
3. **Verify:** Start button is in "playing" state
4. If we could somehow re-enable dropdown (via inspector), select different visual, click Start
5. **Expected:** Built-in visual should NOT override custom mode (our locking prevents this)

---

## UX Improvement Needed

### Current Issue
Once a custom mode is loaded:
- Visual dropdown is **locked**
- No clear way to switch back to built-in visuals
- User must restart or manually stop

### Proposed Solution
Add a **"Stop Custom Mode"** button or **"Switch to Built-in"** action that:
1. Calls `visual_director.stop_current()` or similar
2. Unlocks visual dropdown
3. Unlocks MesmerLoom controls
4. Allows user to select built-in visual

This would be added to the Visual Programs page, perhaps near the custom mode load button.

---

## Files Modified

1. **`mesmerglass/ui/pages/visual_programs.py`**
   - Added `lock_visual_selector()` method
   - Added `unlock_visual_selector()` method

2. **`mesmerglass/ui/launcher.py`**
   - Modified `_on_custom_mode_requested()` to lock visual selector
   - Modified `_on_visual_start()` to unlock visual selector

---

## Architecture Notes

### Why Lock Dropdown?
- **Prevents confusion:** User can't select a different visual while custom mode is playing
- **Prevents override:** Even if Start button clicked, can't accidentally load built-in visual
- **Clear state:** Grayed-out dropdown visually indicates "custom mode active"

### Signal Flow
1. **Custom Mode Load:** `customModeRequested` signal → `_on_custom_mode_requested()` → Lock dropdown + MesmerLoom
2. **Built-in Start:** `startRequested` signal → `_on_visual_start()` → Unlock dropdown + MesmerLoom
3. **Visual Select:** `visualSelected` signal → Just logging (doesn't trigger load)

### Defense in Depth
Even with dropdown locked, the system has multiple safety layers:
1. Dropdown disabled (UI layer)
2. Visual index check in `_on_visual_start()` (logic layer)
3. VisualDirector state management (data layer)

---

## Complete Change Summary

### Previous State
- ✅ Custom modes load correctly
- ✅ Custom mode settings applied
- ❌ Visual dropdown still enabled
- ❌ User could select different visual
- ❌ Potential for settings override

### Current State
- ✅ Custom modes load correctly
- ✅ Custom mode settings applied
- ✅ Visual dropdown locked when custom mode active
- ✅ MesmerLoom controls locked when custom mode active
- ✅ All controls unlock when switching to built-in visual
- ✅ Complete isolation between custom and built-in modes

### Remaining Work
- ⏳ Add "Stop Custom Mode" button for easier switching
- ⏳ Visual indicator showing "Custom Mode: [name]" when active
- ⏳ Consider adding custom mode to dropdown as special item
- ⏳ Preserve last selected built-in visual when switching back

---

## Commit Message

```
Lock visual program dropdown for custom modes

When custom mode is loaded:
- Disable visual program dropdown (can't select built-in visuals)
- Prevent accidental override of custom mode settings
- Visual feedback (grayed out) indicates custom mode active

When built-in visual is started:
- Re-enable visual program dropdown
- Restore normal selection behavior

Completes custom mode isolation:
- Visual Programs tab: dropdown locked
- MesmerLoom tab: spiral/media/zoom controls locked
- Only global aesthetics (colors, blend mode) remain unlocked

Files:
- visual_programs.py: Add lock_visual_selector()/unlock_visual_selector()
- launcher.py: Call lock/unlock on mode switch
```
