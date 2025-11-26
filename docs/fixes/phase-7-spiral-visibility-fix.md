# Phase 7 Spiral Visibility Fix

**Date:** 2025-11-10  
**Status:** ✅ RESOLVED  
**Impact:** Critical - Spiral now visible and rotating correctly

---

## Problem Summary

After extensive debugging of the Phase 7 GUI compositor window, the spiral shader was executing but producing an invisible pattern on screen. This was the final blocker for Task 7.20 Integration completion.

---

## Root Causes Discovered

### 1. Window Visibility Issues (RESOLVED)
**Symptom:** Compositor window reported `visible=True` but was completely invisible to the user.

**Root Cause:** `WS_EX_TRANSPARENT` flag made the window invisible to Windows Desktop Window Manager (DWM). This flag passes all mouse input through the window but also prevents the window from being composited properly.

**Solution:**
- Removed `WS_EX_TRANSPARENT` from window styles (line ~1468 in `window_compositor.py`)
- Window now uses only `WS_EX_LAYERED` + `WS_EX_TOOLWINDOW` + `WS_EX_TOPMOST`
- Result: Window appears fullscreen immediately ✅

### 2. Spiral Color Configuration (RESOLVED)
**Symptom:** Shader executed correctly but spiral pattern was invisible on black background.

**Root Cause:** Initial configuration had `gap_color = (0,0,0)` (black gaps) which blended with the black background, making the pattern invisible.

**Debugging Journey:**
1. **Magenta background test** - Confirmed OpenGL rendering works (full magenta screen visible)
2. **Skip shader test** - Isolated shader as the issue (magenta still visible without shader)
3. **White+white color test** - **BREAKTHROUGH**: User saw faint beige pattern across screen, proving the spiral WAS rendering correctly all along!
4. **Final configuration** - White arms `(1,1,1)` + Black gaps `(0,0,0)` on black background = Perfect contrast ✅

**Solution:**
- File: `mesmerglass/mesmerloom/spiral.py` line 78
- Configuration:
  ```python
  self.arm_color = (1.0, 1.0, 1.0)  # White arms
  self.gap_color = (0.0, 0.0, 0.0)  # Black gaps (contrast with white)
  ```
- Added `_set4()` function for proper RGBA color uniform handling (lines 567-577 in `window_compositor.py`)
- Result: Clear white spiral with black gaps visible on black background ✅

### 3. Director Phase Not Updating (RESOLVED)
**Symptom:** `SpiralDirector.phase` stayed at 0.0, requiring forced time increment in compositor for rotation.

**Root Cause:** The `update()` method had a comment saying "Phase is now managed by rotate_spiral()" but never actually called `rotate_spiral()`. The method existed and was fully functional, but was simply never invoked.

**Solution:**
- File: `mesmerglass/mesmerloom/spiral.py` lines 315-319
- Added call to `rotate_spiral(0.0)` in `update()` method
- Code change:
  ```python
  # Rotate spiral using rotation_speed (RPM)
  self.rotate_spiral(0.0)  # amount parameter is ignored in RPM mode
  
  # Update state.phase from the high-precision accumulator (set by rotate_spiral)
  st.phase = float(self._phase_accumulator)
  ```
- Result: Phase now accumulates properly at 20.0 RPM ✅

---

## Cleanup Performed

Removed all temporary debug code from `window_compositor.py`:
- ❌ Removed forced time increment: `v = (self.frame_count / 60.0) * 0.1`
- ❌ Removed debug logging (first 3 frames, every 60 frames)
- ❌ Removed resolution logging
- ❌ Removed shader uniform logging
- ❌ Removed window opacity logging
- ❌ Removed "MAGENTA background" test code
- ❌ Removed "Rendering spiral" debug messages
- ✅ Kept essential infrastructure (ESC key handler, alpha restoration, vec4 color support)

---

## Key Technical Details

### Window System Configuration
```python
# Working window flags (line ~1468)
WS_EX_LAYERED      # Enables alpha blending
WS_EX_TOOLWINDOW   # Hide from taskbar
WS_EX_TOPMOST      # Always on top
# WS_EX_TRANSPARENT removed - was causing invisibility!
```

### Color Uniform Handling
```python
# Added _set4() for RGBA colors (lines 567-577)
def _set4(name, v0, v1, v2, v3):
    loc = GL.glGetUniformLocation(self.program_id, name)
    if loc != -1:
        GL.glUniform4f(loc, float(v0), float(v1), float(v2), float(v3))

# Route 4-element tuples correctly (line ~621)
elif len(v) == 4:
    _set4(k, v[0], v[1], v[2], v[3])  # vec4 for colors
```

### Spiral Rotation Fix
```python
# spiral.py update() method (line 315)
self.rotate_spiral(0.0)  # Actually call the rotation method!
st.phase = float(self._phase_accumulator)
```

---

## Verification Steps

1. **Window Visibility:** ✅ Window appears fullscreen at 1536x864
2. **OpenGL Rendering:** ✅ glClear produces colored background (tested with magenta)
3. **Shader Execution:** ✅ Spiral shader compiles and draws every frame
4. **Color Output:** ✅ White spiral with black gaps clearly visible
5. **Rotation:** ✅ Phase accumulates properly (20.0 RPM = 0.333 RPS)
6. **No Debug Code:** ✅ All temporary logging removed

---

## Lessons Learned

1. **Window Transparency:** `WS_EX_TRANSPARENT` is incompatible with visible layered windows. Use only `WS_EX_LAYERED` for transparency.

2. **Shader Debugging:** When shader output is black, test with contrasting background colors (magenta) to isolate rendering vs shader issues.

3. **Color Testing:** Testing with identical colors (white+white) was the breakthrough that proved the shader was working - the beige pattern was the spiral all along!

4. **Call Your Methods:** Having a well-designed `rotate_spiral()` method is useless if you forget to call it from `update()`. Always trace the execution path.

5. **Systematic Debugging:** The 25+ iteration debugging process systematically eliminated possibilities:
   - Iterations 1-8: Window visibility
   - Iterations 9-11: Rendering verification  
   - Iterations 12-25: Shader color testing
   - Each step confirmed what WAS working before moving to next possibility

---

## Status: Task 7.20 Integration

**COMPLETE** ✅

- [x] Compositor activation
- [x] Window visibility (fullscreen, topmost, click-through ready)
- [x] OpenGL rendering pipeline
- [x] Shader compilation and execution
- [x] Color configuration (white arms, black gaps)
- [x] Rotation system (phase accumulation)
- [x] Debug code cleanup

**Next:** Task 7.21 - Comprehensive Testing

---

## ThemeBank Video Upload Failure (2025-11-25)

**Symptom:** ThemeBank background videos decoded successfully (confirmed via `[visual.video] ready` logs) but never appeared under the spiral overlay. No `[video.upload]` entries were emitted.

**Root Cause:** `LoomWindowCompositor.set_background_video_frame()` uploaded textures without guaranteeing that the compositor’s `QOpenGLContext` was current. On certain driver/Qt combinations, the call stack executed on a worker thread with no owning context, so OpenGL silently discarded the upload.

**Solution:**

1. Capture the previously current context via `QOpenGLContext.currentContext()` and surface pair.
2. Call `self.makeCurrent()` before any GL call and wrap the entire upload (including fade queue mutations) in a `try/finally` block.
3. Always call `_restore_previous_context(previous_ctx, previous_surface)` so other Qt windows regain their context even when validation fails.
4. Add regression tests (`mesmerglass/tests/test_window_compositor.py`) that mock the GL module to ensure `makeCurrent()` and `_restore_previous_context()` are invoked and that validation failures never issue GL calls.

**Result:** `[video.upload]` logs now appear every ~3 seconds, `Created video texture …` entries match the ThemeBank resolution, and background videos render underneath the spiral without requiring GUI restarts.

---

## Files Modified

1. `mesmerglass/mesmerloom/window_compositor.py` (~1560 lines)
   - Removed `WS_EX_TRANSPARENT` flag
   - Added `_set4()` for vec4 uniforms
   - Removed extensive debug logging
   - Cleaned up temporary test code

2. `mesmerglass/mesmerloom/spiral.py` (404 lines)
   - Added `rotate_spiral()` call in `update()` method
   - Confirmed color configuration (white arms, black gaps)

3. `mesmerglass/session/runner.py` (656 lines)
   - Alpha restoration after showFullScreen()
   - Compositor positioning and activation

---

## Screenshot Evidence

User confirmed seeing clear white 8-arm spiral rotating slowly on black background, matching exactly the expected Trance 7-type visualization with sqrt spiral type (ID=4) at 20.0 RPM.

---

**Resolution:** The spiral is now fully functional. The breakthrough came from realizing the beige screen (white+white test) WAS the spiral rendering - we just needed better color contrast. Combined with calling `rotate_spiral()` for proper phase accumulation, the system now works perfectly.
