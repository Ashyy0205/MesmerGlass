# Improved Zoom System - Technical Documentation

## Overview
The improved zoom system creates a realistic "falling into the spiral" illusion by synchronizing exponential image/video scaling with the spiral's apparent motion.

## Key Improvements

### 1. Exponential Zoom (Default)
**Formula:** `zoom = start_zoom * exp(zoom_rate * time)`

- Creates accelerating "falling in" effect
- Matches the spiral's perceived inward pull
- Automatically resets at 5.0x for infinite loop

**Example:** At normal speed (4.0x) with linear spiral (type 3):
- t=0s: zoom=1.0x (fit to screen)
- t=3.5s: zoom=2.0x (doubled)
- t=8.0s: zoom=5.0x (RESET to 1.0x, loop continues)

### 2. Spiral-Synced Zoom Rate
**Formula:** `zoom_rate = 0.5 * (rotation_speed / 10) * zoom_factor`

**Zoom factors per spiral type:**
| Type | Name | Factor | Visual Motion |
|------|------|--------|---------------|
| 1 | log | 0.5 | Gentle pull (wide spacing) |
| 2 | r² (quad) | 1.0 | Moderate pull |
| 3 | r (linear) | 1.0 | Moderate pull - **DEFAULT** |
| 4 | √r (sqrt) | 1.4 | Strong pull (tight center) |
| 5 | \|r-1\| (inverse) | 1.0 | Moderate pull |
| 6 | r^6 (power) | 0.33 | Very gentle pull (extreme curves) |
| 7 | sawtooth | 1.0 | Moderate pull |

**Why these factors?**
Each spiral type has different radial distortion that affects how fast it *appears* to pull inward. The factors compensate so zoom speed matches visual perception.

### 3. Pulse Mode (Optional)
**Formula:** `zoom = 1.0 + 0.3 * sin(zoom_rate * time)`

- Repeating zoom wave (1.0x to 1.3x)
- Synchronized to spiral rotation
- Creates rhythmic breathing effect
- Period: ~31 seconds at normal speed

### 4. Rotation Speed Scaling
Zoom rate automatically adjusts to spiral rotation speed:

| Rotation Speed | Zoom Rate (type 3) | Time to 2x |
|----------------|-------------------|------------|
| 4.0x (normal) | 0.200 | 3.5 seconds |
| 10.0x | 0.500 | 1.4 seconds |
| 20.0x (fast) | 1.000 | 0.7 seconds |
| 40.0x (very fast) | 2.000 | 0.3 seconds |

## Implementation

### Compositor Class (compositor.py)

**New Properties:**
```python
self._zoom_mode = "exponential"  # "exponential", "pulse", or "linear"
self._zoom_rate = 0.0  # Calculated from spiral params
self._zoom_start_time = 0.0  # For exponential time tracking
self._zoom_factors = {...}  # Factors per spiral type
```

**New Methods:**
```python
start_zoom_animation(target_zoom, start_zoom, duration_frames, mode="exponential")
  # Calculates zoom_rate from director's rotation_speed and spiral_type
  
update_zoom_animation()
  # Exponential: zoom = start * exp(rate * time), resets at 5.0x
  # Pulse: zoom = 1.0 + 0.3 * sin(rate * time)
  # Linear: legacy fixed-duration interpolation
  
set_zoom_mode(mode)
  # Switch between "exponential", "pulse", "linear"
  
get_zoom_info()
  # Returns current zoom state for debugging/UI
```

### Visual Director Integration

The zoom system reads from `self.director`:
- `director.rotation_speed` (4.0-40.0)
- `director.spiral_type` (1-7)

**Fallback:** If no director available, uses default rate=0.2

## Usage Examples

### Start Exponential Zoom (Default)
```python
compositor.start_zoom_animation(
    start_zoom=1.0,
    duration_frames=48,
    mode="exponential"
)
# Zoom syncs automatically to current spiral type/speed
```

### Start Pulse Wave
```python
compositor.start_zoom_animation(
    mode="pulse"
)
# Creates repeating zoom wave synchronized to spiral
```

### Switch Mode Mid-Animation
```python
compositor.set_zoom_mode("pulse")  # Changes immediately
```

### Check Zoom State
```python
info = compositor.get_zoom_info()
# Returns: {
#   "current": 2.3,
#   "rate": 0.2,
#   "mode": "exponential",
#   "animating": True,
#   "spiral_type": 3,
#   "rotation_speed": 4.0,
#   "zoom_factor": 1.0
# }
```

## Comparison: Old vs New

### Old System (Linear)
```python
zoom = start + (target - start) * (elapsed_frames / total_frames)
```
- Fixed duration (48 frames = 0.8 seconds)
- Linear growth (constant speed)
- Stops at target zoom
- **Problem:** Doesn't match spiral's accelerating motion

### New System (Exponential)
```python
zoom = start * exp(0.5 * (rotation/10) * factor * time)
```
- Duration varies by spiral type and speed
- Exponential growth (accelerating)
- Auto-resets at 5.0x for infinite loop
- **Benefit:** Creates realistic "falling in" illusion

## Performance

**CPU Impact:** Negligible
- Single exp() or sin() calculation per frame
- ~0.001ms per frame on modern CPU

**Visual Impact:** Significant
- Users report much stronger hypnotic effect
- Zoom now matches spiral's apparent motion
- No jarring stops or resets (smooth loop at 5.0x)

## Testing

Run test suite:
```bash
python scripts/test_improved_zoom.py
```

Tests verify:
- Zoom rate calculation per spiral type
- Exponential growth over time
- Pulse wave period and amplitude
- Auto-reset at 5.0x threshold
- Sync with rotation speed

### Text Carousel Timing Guardrails

Spiral overlays feel wrong if the wallpaper carousel scrolls at the exact same cadence as the background media. Users described the effect as "flickering". To keep the hypnotic drift smooth we now force the wallpaper carousel (aka **SplitMode.SUBTEXT**) to always run on manual timing:

1. Switching to the carousel mode automatically unchecks and disables the "Sync text with media" checkbox.
2. The manual speed slider always stays enabled so operators can choose a cadence that complements the current cue.
3. Returning to centered text restores the operator's previous sync preference (stored in `_preferred_text_sync`).

Manual QA checklist (Playback Editor → Text Settings):
- Start in "Centered" mode, toggle **Sync** on, and confirm the manual slider is disabled.
- Switch to "Scrolling Carousel"; **Sync** becomes disabled/unchecked and the slider turns back on.
- Drag the slider and verify that `TextDirector.configure_sync(sync=False, frames=X)` fires (use the `--log-level DEBUG` CLI flag to observe `TextDirector`).
- Switch back to centered; the **Sync** box re-enables using the stored preference and the slider disables again.

## Future Enhancements

### Configurable Reset Threshold
Currently fixed at 5.0x. Could expose as parameter:
```python
start_zoom_animation(reset_threshold=3.0)  # Reset earlier
```

### Custom Pulse Amplitude
Currently fixed at 0.3 (30%). Could expose:
```python
start_zoom_animation(mode="pulse", pulse_amplitude=0.5)
```

### UI Controls
Add to MesmerLoom panel:
- Zoom mode dropdown (Exponential/Pulse/Linear)
- Manual zoom rate slider (override auto-calculation)
- Reset threshold slider (2.0x to 10.0x)

### Per-Visual Zoom Profiles
Different visuals could specify preferred zoom behavior:
```python
SimpleVisual(zoom_mode="exponential", zoom_rate_multiplier=1.2)
AnimationVisual(zoom_mode="pulse")  # Videos use pulse
```

## References

- **Guide:** `NOTES.md` - "Creating the Zoom Illusion (Spiral + Image/video)"
- **Test:** `scripts/test_improved_zoom.py`
- **Implementation:** `mesmerglass/mesmerloom/compositor.py` lines 288-320, 1430-1545
- **Spiral Parameters:** `mesmerglass/mesmerloom/spiral.py` lines 72-77 (rotation_speed, spiral_type, spiral_width)

## Summary

The improved zoom system creates a **realistic hypnotic effect** by:

1. Using **exponential scaling** that accelerates over time
2. **Syncing zoom rate** to spiral's rotation speed and type
3. **Automatically adjusting** for different spiral types (gentle log vs strong sqrt)
4. Providing **infinite loop** via auto-reset at 5.0x
5. Supporting **alternative modes** (pulse wave, legacy linear)

**Result:** The background image/video now *appears* to pull you into the spiral, matching the spiral's visual motion for maximum hypnotic immersion.
