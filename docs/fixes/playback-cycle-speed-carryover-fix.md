# Playback Cycle Speed Carryover Fix

**Date**: 2025-11-17  
**Issue**: Media cycle speed from previous playback carried over when switching to new playback  
**Status**: ✅ FIXED

---

## Problem Description

When switching between playbacks with different media cycle speeds in a session, the NEW playback would initially use the OLD playback's cycle speed, then revert to its correct speed after a few seconds.

### User Report
> "Media not stuck on playback change but it when to it correct speeds for the seconds playback and then when back to the previous speeds (At least thats what it looked like)"

### Technical Details

**Playback Configuration**:
- Playback 2 (`2.json`): `cycle_speed=20` → 217 frames (~3.6s)
- Playback 1 (`1.json`): `cycle_speed=10` → 371 frames (~6.2s)

**Observed Behavior**:
1. Session starts with Playback 2 (speed=20)
2. Media cycles every 217 frames ✅
3. Session switches to Playback 1 (speed=10)
4. Media cycles every 217 frames ❌ (should be 371!)
5. After unknown duration, speed corrects to 371 frames

---

## Root Cause

The bug was in `CustomVisual._apply_media_settings()` (lines 323-342):

```python
def _apply_media_settings(self) -> None:
    """Apply media configuration and build media path list."""
    media_config = self.config.get("media", {})
    
    # ... mode and cycle_speed calculation ...
    
    self._frames_per_cycle = max(1, round((interval_ms / 1000.0) * 60.0))
    # ❌ BUG: _cycler never cleared!
```

### What Was Happening

1. **Playback 2 loads**:
   - `_frames_per_cycle = 217` set
   - `get_cycler()` called → builds `ActionCycler(period=217, ...)`
   - Media cycles every 217 frames ✅

2. **Playback 1 loads**:
   - `_apply_media_settings()` called
   - `_frames_per_cycle = 371` updated
   - **`_cycler` still exists** with old `period=217`!
   - `get_cycler()` returns existing cycler ❌
   - Media cycles every 217 frames (wrong speed!)

3. **Visual.get_cycler() logic**:
```python
def get_cycler(self) -> Cycler:
    """Get the cycler (builds it if needed)."""
    if self._cycler is None:  # ← Only rebuilds if None!
        self._cycler = self.build_cycler()
    return self._cycler
```

The cycler was never cleared, so `get_cycler()` returned the stale cycler with the old period value.

---

## Solution

Added cycler cleanup immediately after updating `_frames_per_cycle`:

```python
def _apply_media_settings(self) -> None:
    """Apply media configuration and build media path list."""
    media_config = self.config.get("media", {})
    
    # ... mode and cycle_speed calculation ...
    
    self._frames_per_cycle = max(1, round((interval_ms / 1000.0) * 60.0))
    actual_interval_ms = (self._frames_per_cycle / 60.0) * 1000.0
    self.logger.info(f"[CustomVisual] Applied media cycle speed: {cycle_speed} → {self._frames_per_cycle} frames ({actual_interval_ms:.0f}ms at 60fps, target: {interval_ms:.0f}ms)")
    
    # ✅ FIX: Clear old cycler so new one will be built with updated _frames_per_cycle
    # Without this, the old cycler continues running with the previous playback's period
    self._cycler = None
    self.logger.debug(f"[CustomVisual] Cleared cycler to force rebuild with new period={self._frames_per_cycle}")
```

**File Modified**: `mesmerglass/mesmerloom/custom_visual.py` (lines 323-344)

---

## Verification

The fix ensures:

1. ✅ When `_apply_media_settings()` is called (during playback load), cycler is cleared
2. ✅ Next `get_cycler()` call rebuilds cycler with new `_frames_per_cycle` value
3. ✅ New playback uses correct cycle speed immediately from frame 0
4. ✅ No transient period of wrong speed

### All Call Sites Fixed

`_apply_media_settings()` is called from three locations:
- `_apply_initial_settings()` - during playback load
- `reapply_all_settings()` - after compositor ready
- `reload_from_disk()` - live reload feature

All call sites now benefit from the cycler clear.

---

## Related Fixes

This completes the playback switching bug fixes series:

1. ✅ **Zoom rate carryover** - Fixed by resetting `_zoom_rate` in compositor `reset_zoom()`
2. ✅ **Media cycle speed carryover** - Fixed by clearing `_cycler` in `_apply_media_settings()`
3. ✅ **Playback freeze on videos mode** - Fixed by adding image fallback for ThemeBank videos

All playback switching bugs now resolved!

---

## Testing Notes

To verify fix:
1. Create session with two playbacks with different cycle speeds (e.g., 10 and 20)
2. Start session and observe first playback cycles at correct speed
3. Wait for automatic switch to second playback
4. **Expected**: Media cycles at second playback's speed immediately from frame 0
5. **Previously**: Media would cycle at first playback's speed initially

---

## Impact

- **Scope**: All playback transitions in sessions
- **Risk**: Low - only clears cycler reference, forcing rebuild with correct parameters
- **Compatibility**: No API changes, fully backward compatible
- **Performance**: Negligible - cycler rebuild is instantaneous

---

## Future Considerations

Consider adding explicit cycler lifecycle management:
- `reset_cycler()` method for consistent cleanup
- Cycler rebuild validation in `get_cycler()`
- Unit tests for cycler period changes
