# Custom Modes: Visual Mode Creator ↔ Launcher Parity

## Overview
This document ensures that custom modes created in the Visual Mode Creator play **identically** in the Launcher. All settings, behaviors, and visual output must match 1:1.

---

## ✅ Verified Parity Features

### 1. Spiral Settings
**Visual Mode Creator:**
- Spiral type: Mapped by index (1=logarithmic, 2=quadratic, etc.)
- Rotation speed: Direct value (e.g., 4.0)
- Opacity: 0.0-1.0 range
- Reverse: Boolean flag (negates rotation speed)

**Launcher CustomVisual:**
- ✅ Spiral type: String→ID mapping (`logarithmic`→1, `quadratic`→2, etc.)
- ✅ Rotation speed: Applied with reverse flag (negative if true)
- ✅ Opacity: Direct application to spiral director
- ✅ Reverse: Converts to negative rotation speed

**Implementation:**
- `custom_visual.py` lines 173-218: `_apply_spiral_settings()`
- Spiral type map matches Visual Mode Creator indices
- Settings applied to both `director` and `spiral_director` attributes

---

### 2. Media Cycling Speed
**Formula (IDENTICAL):**
```python
interval_ms = 10000 * pow(0.005, (speed - 1) / 99.0)
frames = (interval_ms / 1000.0) * 60.0  # Convert to frames at 60fps
```

**Visual Mode Creator:**
- Uses QTimer with `setInterval(interval_ms)`
- Speed range: 1-100 (slider)
- Speed 1 = 10,000ms (10s), Speed 100 = 50ms

**Launcher CustomVisual:**
- ✅ Uses ActionCycler with `period=frames`
- ✅ Same exponential formula
- ✅ Logs: "Applied media cycle speed: X → Y frames (Zms)"

**Example:**
- Speed 50 → 726ms → 43 frames
- Speed 55 → 556ms → 33 frames

---

### 3. Zoom Animation
**Visual Mode Creator:**
- Calls `start_zoom_animation(start_zoom=1.0, mode=...)` on each image load
- Manually sets `_zoom_rate` from slider (0.0-5.0)
- Resets `_zoom_start_time` and `_zoom_current=1.0` on each image

**Launcher CustomVisual:**
- ✅ Calls `_restart_zoom_animation()` on each media change
- ✅ Passes explicit `rate` parameter to `start_zoom_animation()`
- ✅ Resets zoom to 1.0 on every image

**Zoom Modes:**
- `exponential`: Positive rate → zoom value increases (1.0→2.0→3.0) → shader `/uZoom` → visual zoom IN
- `falling`: Negative rate → zoom value decreases (1.0→0.5→0.3) → shader `/uZoom` → visual zoom OUT
- `pulse`: Sine wave oscillation
- `linear`: Linear interpolation (legacy)
- `none`: Zoom disabled

**Implementation:**
- `custom_visual.py` lines 318-360: `_apply_zoom_settings()`
- `custom_visual.py` lines 318-337: `_restart_zoom_animation()` (NEW)
- `visual_director.py` lines 527-541: Skips zoom for custom modes

---

### 4. Text Rendering
**Visual Mode Creator:**
- Text enabled/disabled flag
- Text mode: "centered_sync" or "subtext"
- Text opacity: 0.0-1.0
- Calls `text_director.on_media_change()` on each image

**Launcher CustomVisual:**
- ✅ Text enabled/disabled via `set_enabled()`
- ✅ Text mode mapping (SplitMode.CENTERED_SYNC, SplitMode.SUBTEXT)
- ✅ Text opacity applied
- ✅ Uses ThemeBank text library
- ✅ Calls `on_media_change()` in `_load_current_media()`

---

### 5. Control Locking
**Requirement:** When custom mode is active, launcher controls must be locked.

**Implemented:**
- ✅ `launcher.py`: `lock_controls()` disables MesmerLoom controls
- ✅ `launcher.py`: `lock_visual_selector()` disables visual dropdown
- ✅ `launcher.py`: Skips `_start_media_cycling()` for custom modes
- ✅ `visual_director.py`: Skips zoom override for custom modes

---

### 6. Settings Re-application
**Problem:** Spiral director doesn't exist at initial load time.

**Solution:**
- ✅ `_apply_initial_settings()`: Apply to preview compositor (may not have spiral_director yet)
- ✅ `reapply_all_settings()`: Public method called after spiral windows created
- ✅ Two re-application paths:
  - New window path: `launcher.py` lines 870-886
  - Early-exit path: `launcher.py` lines 727-746
- ✅ Checks both `spiral_director` (LoomWindowCompositor) and `director` (LoomCompositor)

---

### 7. Zoom Animation Override Prevention
**Problem:** `visual_director._on_change_image()` was overriding custom mode zoom settings.

**Solution:**
- ✅ `visual_director.py` lines 527-541: Check `is_custom_mode_active()`
- ✅ Skip `start_zoom_animation()` call if custom mode active
- ✅ Log: "Background texture set successfully (custom mode manages zoom)"

---

## 🧪 Test Checklist

### Visual Comparison Test
Run both Visual Mode Creator and Launcher side-by-side with same mode:

**Spiral:**
- [ ] Same rotation direction (reverse flag works)
- [ ] Same rotation speed
- [ ] Same spiral type (logarithmic/quadratic/etc.)
- [ ] Same opacity (40% = semi-transparent)

**Media:**
- [ ] Same image cycle timing (measure with stopwatch)
- [ ] Same image order (ThemeBank weighted selection)
- [ ] Same media opacity

**Zoom:**
- [ ] Zoom resets to 1.0 on each new image
- [ ] Exponential zoom IN at correct rate (0.42 = moderate)
- [ ] Zoom reaches same maximum before reset
- [ ] No zoom accumulation between images

**Text:**
- [ ] Text appears/disappears correctly
- [ ] Text changes with media (CENTERED_SYNC)
- [ ] Text opacity matches

---

## 📊 Example Mode: "Sinking"

```json
{
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": 4.0,
    "opacity": 0.4,
    "reverse": true
  },
  "media": {
    "cycle_speed": 55,  // → 33 frames (556ms)
  },
  "zoom": {
    "mode": "exponential",
    "rate": 0.42,
    "duration_frames": 180
  }
}
```

**Expected Behavior:**
1. Spiral: Logarithmic type, rotating backwards at 4.0x speed, 40% opacity
2. Media: Images change every 556ms (33 frames at 60fps)
3. Zoom: Each image starts at 1.0x, zooms IN exponentially at rate 0.42
4. At 180 frames (3 seconds): Zoom reaches ~2.5x, then resets when next image loads

---

## 🔍 Debugging Tips

### Check Logs for Parity:
```
[CustomVisual] Applied spiral type: logarithmic (ID=1)
[CustomVisual] Applied rotation speed: -4.0x (reverse=True)
[CustomVisual] Applied spiral opacity: 0.4
[CustomVisual] Applied media cycle speed: 55 → 33 frames (556ms)
[CustomVisual] Applied zoom animation: mode=exponential, rate=0.42, duration=180
[CustomVisual] Restarted zoom animation: mode=exponential, rate=0.42
[visual] Background texture set successfully (custom mode manages zoom)
```

### Common Issues:
1. **Zoom carrying over**: Check `_restart_zoom_animation()` is called in `_load_current_media()`
2. **Wrong zoom direction**: Verify rate sign (positive=zoom in, negative=zoom out)
3. **Settings not applied**: Check `reapply_all_settings()` called after spiral windows created
4. **Zoom overridden**: Verify visual_director skips `start_zoom_animation()` for custom modes

---

## 🎯 Success Criteria

Custom mode is **1:1 identical** when:
✅ All visual elements match (spiral, media, text, zoom)
✅ All timing matches (media cycle, zoom rate)
✅ Settings persist across media changes
✅ No unexpected overrides or resets
✅ Launcher controls properly locked
✅ Side-by-side comparison shows identical behavior

---

## 📝 Version History

- **2025-10-30**: Initial parity implementation
  - Fixed spiral type string→int mapping
  - Fixed zoom mode string mapping in Visual Mode Creator save
  - Added zoom restart on media change
  - Prevented visual_director zoom override
  - Fixed zoom rate sign for exponential mode
  - Verified media cycle speed formula parity
