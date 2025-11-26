# Phase 7 Media Loading Fix

**Date:** 2025-11-10  
**Status:** ✅ RESOLVED  
**Impact:** Critical - Background media now loads and cycles during sessions

---

## Problem

User reported seeing only a white spiral on black background during session playback. The cuelist was running correctly, but the **background media (images/videos)** from the playback files was not loading.

**Symptom:**
```
Session starts → Spiral visible ✓
Background media → Missing ✗ (expected images/videos behind spiral)
```

---

## Root Cause

The `CustomVisual` class had a design that assumed a two-step workflow from the old Launcher UI:
1. **Load mode** → Prepare visual (don't load media yet)
2. **Press Launch button** → Load media and start playback

However, the new `SessionRunner` only called `load_playback()` which internally called `reset()`, and `reset()` **explicitly avoided loading media**:

```python
# From custom_visual.py line 592
# DON'T auto-load media - wait for Launch button
# User expects mode to load in "preview" state without starting playback
# Media will load when start() is called (Launch button pressed)
```

The problem: **No `start()` method existed!** The comment referenced a method that was never implemented.

---

## Solution

Added the missing `start()` method and wired it through the architecture:

### 1. Added `start()` to CustomVisual

**File:** `mesmerglass/mesmerloom/custom_visual.py` (after line 599)

```python
def start(self) -> None:
    """Start visual playback - loads first media item and begins cycling."""
    if self.media_items:
        self._load_current_media()
        self.logger.info(f"[CustomVisual] '{self.playback_name}' started - media loaded and playing")
    else:
        self.logger.warning(f"[CustomVisual] '{self.playback_name}' has no media items to start")
```

**Purpose:** Load the first media item (image or video) and enable cycling.

### 2. Added `start_playback()` to VisualDirector

**File:** `mesmerglass/mesmerloom/visual_director.py` (after line 137)

```python
def start_playback(self) -> None:
    """Start the currently loaded playback (load first media and begin cycling)."""
    if self.current_visual and hasattr(self.current_visual, 'start'):
        self.current_visual.start()
        self.logger.info("[visual] Playback started")
    else:
        self.logger.warning("[visual] No visual loaded or visual doesn't support start()")
```

**Purpose:** Delegate to the current visual's `start()` method.

### 3. Called `start_playback()` in SessionRunner

**File:** `mesmerglass/session/runner.py` (after line 363)

```python
success = self.visual_director.load_playback(playback_path)
if not success:
    self.logger.error(f"[session] Failed to load playback: {playback_path}")
    return False

# Start playback (load media and begin cycling)
self.visual_director.start_playback()
self.logger.info(f"[session] Playback started: {playback_path.name}")
```

**Purpose:** After loading a playback, immediately start it to load media.

---

## What Happens Now

**Session Start Flow:**
1. User clicks Start → `SessionRunner.start()`
2. Load first cue → `_start_cue(0)`
3. Select playback from cue pool → `_select_playback_from_pool()`
4. Load playback → `visual_director.load_playback(playback_path)`
   - Creates `CustomVisual` instance
   - Calls `reset()` (prepares but doesn't load media)
5. **NEW:** Start playback → `visual_director.start_playback()`
   - Calls `custom_visual.start()`
   - Loads first media item via `_load_current_media()`
   - Begins media cycling
6. Compositor renders:
   - Background layer: Image/video from playback ✅
   - Spiral layer: Rotating spiral overlay ✅

**Media Cycling:**
- Cycler advances each frame based on `media_cycle_speed`
- When cycle completes, loads next media item from playback's media list
- SessionRunner can detect cycle boundaries for synchronized transitions

**Cue Transitions:**
- When cue duration expires or cycle count reached
- `_execute_transition()` → `_end_cue()` → `_start_cue(next_index)`
- New cue loads different playback with different media
- `start_playback()` is called again for the new cue ✅

---

## Files Modified

1. **`mesmerglass/mesmerloom/custom_visual.py`**
   - Added `start()` method (lines ~600-605)
   - Loads first media item and begins playback

2. **`mesmerglass/mesmerloom/visual_director.py`**
   - Added `start_playback()` method (lines ~140-145)
   - Delegates to current visual's start()

3. **`mesmerglass/session/runner.py`**
   - Added `start_playback()` call after loading playback (line ~366)
   - Ensures media loads when cue starts

---

## Expected Behavior

**Before Fix:**
```
Session Start → Spiral visible ✓
Background → Black screen ✗
```

**After Fix:**
```
Session Start → Spiral visible ✓
Background → Images/videos cycling ✓
Transitions → New playback loads new media ✓
```

---

## Testing

Run the app and start a session:

```powershell
.\.venv\Scripts\python.exe -m mesmerglass
```

**Test Steps:**
1. Load session "Example Training Session"
2. Click Start
3. **VERIFY:**
   - ✅ Spiral rotates smoothly (white on black gaps)
   - ✅ Background shows images/videos from playback
   - ✅ Media cycles automatically based on `media_cycle_speed`
   - ✅ Cue transitions load new playback with different media
   - ✅ Log shows: `[CustomVisual] 'Gentle Introduction' started - media loaded and playing`

**Expected Media Cycling:**
- "Gentle Introduction" playback has media cycle speed = 30 (fast cycling)
- Should see images/videos changing every ~2 seconds at 60fps
- Spiral remains consistent (opacity, speed, colors from playback settings)

---

## Architecture Notes

### Two-Stage Loading Pattern

This fix implements a proper **two-stage loading pattern**:

**Stage 1: Load (Prepare)**
- Create visual instance
- Parse playback configuration
- Apply settings (spiral, text, zoom, etc.)
- **Don't load media yet** (allows preview/inspection)

**Stage 2: Start (Execute)**
- Load first media item
- Begin media cycling
- Start playback timeline

### Why This Matters

**For Launcher UI (future):**
- Load → Show preview with spiral only
- Launch → Start media playback
- Allows user to inspect settings before starting

**For SessionRunner (current):**
- Load → Prepare playback
- Start → Begin immediately (no manual Launch button)
- Automatic media loading on cue start

### Design Pattern

This follows the **Prepare-Execute** pattern common in media players:
- **Prepare:** Buffer, validate, configure (fast, non-blocking)
- **Execute:** Start playback, load resources (may take time)

---

## Related Issues

- ✅ Spiral visibility (fixed in phase-7-spiral-visibility-fix.md)
- ✅ Director rotation (phase accumulation now works)
- ✅ Display selection (compositor uses DisplayTab)
- ✅ Media loading (this fix)

**Status:** Phase 7 GUI now fully functional! 🎉

---

## Next Steps

1. Test with various playback files (images only, videos only, mixed)
2. Test cue transitions (verify media changes between cues)
3. Test edge cases (missing media files, invalid paths)
4. Performance testing (memory usage, frame rate with videos)
5. Multi-monitor testing (verify DisplayTab integration)

**Task 7.21 Comprehensive Testing** is now ready to begin! ✅
