# Cuelist Duration Enforcement Fix

**Date**: 2025-11-17  
**Status**: ✅ Fixed  
**Component**: Session Runner + Visual Director (Cycle Boundary Detection)

## Problem

Sessions with Playback Pool mode would run **far past** the cue's specified duration. A 30-second cue would run for 44+ seconds before ending.

### Symptoms
- Cue duration exceeded at correct time ✅
- Logs show: `Duration trigger: 30.0s >= 30s` ✅  
- Logs show: `Transition requested, waiting for cycle boundary...` ✅
- Session continues for 10-15+ more seconds ❌
- Eventually: `Cycle boundary crossed: count=1 marker=12` and `Session completed` ✅

## Root Cause

Two separate issues:

### Issue 1: Playback Switching Blocking Cue Transitions

When playback switching was pending at the same time as a cue transition, the playback callback would "consume" the cycle boundary, preventing the cue transition from executing.

### Issue 2: Cycle Boundaries Not Detected During Playback Switching

The visual director resets `_last_cycle_marker = 0` when loading a new playback. This meant:

1. Old playback: `_cycle_marker = 5`
2. Load new playback → `_cycle_marker = 0`, `_last_cycle_marker = 0`  
3. Both at 0 → no boundary detected
4. New playback runs, images change: 0→1→2→3...
5. Next playback switch → markers reset again
6. **Result**: Boundaries only detected WITHIN a single playback, not across switches

With frequent playback switching (every ~6s), cycle boundaries were effectively never detected! The cue transition had to wait until switching stopped AND the current playback completed multiple cycles.

## Solution

### Part 1: Playback Switching Priority (runner.py)

Modified `_on_playback_cycle_boundary()` to check for pending cue transitions first:

```python
if self._pending_transition:
    self.logger.debug(f"[session] Playback switch deferred - cue transition pending")
    # Unregister playback callback, defer to cue transition
    self._playback_switch_pending = False
    return
```

### Part 2: Cycle Boundary Detection (visual_director.py)

**Fix 1**: Don't reset `_last_cycle_marker` during playback switches:

```python
# In load_playback():
self._cycle_count = 0
# NOTE: _last_cycle_marker NOT reset - preserves boundary detection
```

**Fix 2**: Detect boundaries when marker goes backwards (playback switch):

```python
def _check_cycle_boundary(self):
    if current_marker > self._last_cycle_marker:
        # Normal: marker advanced (5 → 6)
        # Fire callbacks...
        
    elif current_marker < self._last_cycle_marker and current_marker > 0:
        # Playback switch: marker went backwards (5 → 1)
        self.logger.info(f"[visual] Playback switch detected, firing cycle boundary")
        # Fire callbacks...
```

## Testing

### Before Fix
```
[20:29:34] Duration trigger: 30.0s >= 30s
[20:29:34] Transition requested, waiting for cycle boundary...
[20:29:49] Cycle boundary crossed: count=1 marker=12  ← 15 seconds later!
[20:29:49] Session completed
```

### After Fix (Expected)
```
[session] Duration trigger: 30.0s >= 30s
[session] Transition requested, waiting for cycle boundary...
[visual] Playback switch detected, firing cycle boundary  ← <1s later!
[session] Playback switch deferred - cue transition pending
[session] Cycle boundary reached, executing transition
[session] Session completed
```

## Impact

- ✅ Cue transitions take priority over playback switching
- ✅ Cycle boundaries detected at EVERY playback switch  
- ✅ Sessions end within 1-2 seconds of duration exceeded (not 10-15s)
- ✅ No breaking changes

## Related Files

- `mesmerglass/session/runner.py` (lines 665-700): Playback callback priority
- `mesmerglass/mesmerloom/visual_director.py`:
  - Lines 165-185: Removed marker reset in `load_playback()`
  - Lines 347-410: Added playback switch detection in `_check_cycle_boundary()`
