# Custom Mode Settings Reference

**Complete mapping between JSON settings, Visual Mode Creator UI, and Launcher behavior**

Last Updated: 2025-10-30

---

## Overview

Custom modes use a JSON format to store all visual settings. This document clarifies:
- What each JSON field controls
- How the Visual Mode Creator UI maps to JSON
- How the Launcher interprets each setting
- Any discrepancies or special behaviors

---

## JSON Structure

```json
{
  "version": "1.0",
  "name": "Mode Name",
  "description": "Optional description",
  "spiral": { ... },
  "media": { ... },
  "text": { ... },
  "zoom": { ... }
}
```

---

## 🌀 Spiral Settings

### `spiral.type`

**JSON Values:** `"logarithmic"`, `"quadratic"`, `"linear"`, `"sqrt"`, `"inverse"`, `"power"`, `"sawtooth"`

**Visual Mode Creator:**
- UI Control: Combo box "Spiral Type"
- Options:
  - "1 - Logarithmic" → `"logarithmic"` (ID: 1)
  - "2 - Quadratic (r²)" → `"quadratic"` (ID: 2)
  - "3 - Linear (r)" → `"linear"` (ID: 3)
  - "4 - Square Root (√r)" → `"sqrt"` (ID: 4)
  - "5 - Inverse (|r-1|)" → `"inverse"` (ID: 5)
  - "6 - Power (r⁶)" → `"power"` (ID: 6)
  - "7 - Sawtooth" → `"sawtooth"` (ID: 7)

**Launcher Interpretation:**
- Maps string name to numeric ID (1-7)
- Calls `spiral.set_spiral_type(spiral_type_id)`
- Default: `"logarithmic"` (ID: 1) if invalid/missing

**⚠️ DISCREPANCY FOUND:**
- Visual Mode Creator uses: `"inverse"`, `"power"`, `"sawtooth"` (indices 5, 6, 7)
- Launcher expects: `"cubic"`, `"power"`, `"hyperbolic"` (indices 5, 6, 7)
- **FIX NEEDED**: Update spiral_type_map in custom_visual.py

---

### `spiral.rotation_speed`

**JSON Values:** Positive float (e.g., `4.0`, `16.0`, `40.0`)

**Visual Mode Creator:**
- UI Control: Slider "Rotation Speed"
- Range: 40-400 (maps to 4.0x - 40.0x, divided by 10)
- Default: 40 → `4.0`
- Label shows: "4.0x", "16.0x", etc.

**Launcher Interpretation:**
- Reads numeric value from JSON
- If `spiral.reverse = true`, negates the value: `rotation_speed = -abs(rotation_speed)`
- Calls `spiral.set_rotation_speed(rotation_speed)`
- **Negative = counterclockwise, Positive = clockwise**

**✅ ALIGNED** - Working correctly after recent debug

---

### `spiral.opacity`

**JSON Values:** Float 0.0 - 1.0 (e.g., `0.3`, `0.8`, `1.0`)

**Visual Mode Creator:**
- UI Control: Slider "Spiral Opacity"
- Range: 0-100 (maps to 0.0 - 1.0, divided by 100)
- Default: 80 → `0.8`
- Label shows: "80%"

**Launcher Interpretation:**
- Reads float value (0.0 - 1.0)
- Calls `spiral.set_opacity(opacity)`
- **NEW**: Locks opacity to prevent intensity-based evolution
- Applied to shader as `uSpiralOpacity` uniform
- Final shader alpha: `finalColor.a *= uSpiralOpacity * uWindowOpacity`

**✅ ALIGNED** - Opacity lock prevents snapping

---

### `spiral.intensity`

**JSON Values:** Float 0.0 - 1.0 (e.g., `0.8`)

**Visual Mode Creator:**
- ⚠️ **NOT EXPOSED IN UI** - Uses slider value as proxy
- Slider "Spiral Opacity" actually sets `director.set_intensity(opacity)`
- **CONFUSING**: Opacity slider controls visual opacity AND intensity parameter

**Launcher Interpretation:**
- Reads `spiral.intensity` from JSON (defaults to `0.8` if missing)
- Calls `spiral.set_intensity(intensity)`
- Intensity affects:
  - Spiral rotation base speed (phase increment)
  - Bar width evolution
  - Contrast evolution
  - ~~Opacity evolution~~ (now locked when manually set)

**⚠️ DISCREPANCY:**
- Visual Mode Creator doesn't have separate intensity control
- Opacity slider conflates visual opacity with animation intensity
- **RECOMMENDATION**: Add separate "Intensity" slider (0-100%) in Visual Mode Creator

---

### `spiral.reverse`

**JSON Values:** Boolean `true` or `false`

**Visual Mode Creator:**
- UI Control: Checkbox "Reverse Spiral Direction"
- Default: Unchecked → `false`

**Launcher Interpretation:**
- If `true`, negates rotation_speed: `rotation_speed = -abs(rotation_speed)`
- Ensures counterclockwise rotation
- Applied before calling `spiral.set_rotation_speed()`

**✅ ALIGNED**

---

### `spiral.arm_color` & `spiral.gap_color`

**JSON Values:** ❌ **NOT STORED IN JSON**

**Visual Mode Creator:**
- UI Control: Buttons "Arm Color" and "Gap Color"
- Uses color picker dialog
- Default: Arm = white (1, 1, 1), Gap = black (0, 0, 0)
- **Applies immediately to preview spiral**

**Launcher Interpretation:**
- ❌ **NOT READ FROM JSON**
- Uses global spiral color settings from launcher UI
- Colors are session-wide, not per-mode

**⚠️ DESIGN DECISION:**
- Colors excluded from modes to keep them as global "theme" settings
- User can change spiral colors in launcher and they apply to ALL custom modes
- **RECOMMENDATION**: Document this clearly in UI (tooltip/label)

---

## 📸 Media Settings

### `media.mode`

**JSON Values:** `"images"`, `"videos"`, `"both"`, `"none"`

**Visual Mode Creator:**
- UI Control: Combo box "Media Mode"
- Options:
  - "Images & Videos" → `"both"`
  - "Images Only" → `"images"`
  - "Videos Only" → `"videos"`
- Default: "Images Only" → `"images"`

**Launcher Interpretation:**
- Reads string value
- Filters media list from ThemeBank based on mode
- `"images"` → Only .jpg, .png files
- `"videos"` → Only .mp4, .mov files
- `"both"` → All supported media
- `"none"` → No media (spiral only)

**✅ ALIGNED**

---

### `media.cycle_speed`

**JSON Values:** Integer 1-100

**Visual Mode Creator:**
- UI Control: Slider "Media Cycling Speed"
- Range: 1-100
- Default: 50 (Medium)
- Label shows: "50 (Medium) - 1.23s"
- Formula: `interval_ms = 10000 * pow(0.005, (speed-1)/99)`
- Uses QTimer with millisecond intervals (precise timing)

**Launcher Interpretation:**
- Reads integer value (1-100)
- Same formula: `interval_ms = 10000 * pow(0.005, (speed-1)/99)`
- Converts to frames: `frames = (interval_ms / 1000) * 30fps`
- Uses ActionCycler (frame-based, quantized to 33ms intervals)

**✅ ALIGNED** - After 30fps fix (was 60fps)

**Speed Examples:**
- `1` → 10000ms (10 seconds) → 300 frames
- `20` → 2000ms (2 seconds) → 60 frames
- `50` → 327ms (0.33 seconds) → 10 frames
- `66` → 108ms (0.11 seconds) → 3 frames
- `100` → 50ms (0.05 seconds) → 2 frames (minimum)

---

### `media.fade_duration`

**JSON Values:** Float 0.0-5.0 (seconds)

**Visual Mode Creator:**
- UI Control: Slider "Media Fade Duration"
- Range: 0-50 (stored as tenths, displayed as 0.0-5.0 seconds)
- Default: 5 → 0.5 seconds
- Label shows: "0.5s", "1.2s", etc.
- Applied in real-time to compositor preview

**Launcher Interpretation:**
- Reads float value (clamped to 0.0-5.0 range)
- Calls `compositor.set_fade_duration(fade_duration)`
- Enables smooth cross-fade transitions between images/videos
- Uses dual-texture rendering: old texture fades out (1.0 → 0.0 opacity), new texture fades in (0.0 → 1.0 opacity)
- Fade progress calculated as: `min(1.0, frames_elapsed / (fade_duration * 60fps))`
- `0.0` = instant switch (no fade)
- Higher values = slower, smoother transitions

**✅ ALIGNED** - Frame timing matches between VMC and Launcher (both use 60fps)

**Fade Examples:**
- `0.0` → Instant switch (no fade)
- `0.5` → 30 frames (0.5 seconds at 60fps) - default, subtle blend
- `1.0` → 60 frames (1 second) - smooth, noticeable transition
- `2.0` → 120 frames (2 seconds) - slow, dream-like fade
- `5.0` → 300 frames (5 seconds) - very slow, hypnotic blend

---

### ~~`media.opacity`~~ ❌ REMOVED

**Status:** ⛔ **FIELD REMOVED** (not needed)

**Reason for removal:**
- Not implemented in compositor
- No use case identified (media blending handled by shader)
- Removed from Visual Mode Creator export (no longer in JSON)
- Removed from launcher code (no longer parsed)

**Migration:** Existing mode files with `media.opacity` will ignore the field.

---

### `media.use_theme_bank`

**JSON Values:** Boolean `true` or `false`

**Visual Mode Creator:**
- Always exports: `true` (hardcoded)
- No UI control (future feature)

**Launcher Interpretation:**
- If `true`, loads media from global `MEDIA/Images` and `MEDIA/Videos` directories
- If `false`, uses paths from `media.paths` array
- Default: `true`

**✅ ALIGNED** - ThemeBank always used

---

### `media.paths`

**JSON Values:** Array of file path strings (e.g., `["path/to/image.jpg"]`)

**Visual Mode Creator:**
- Always exports: `[]` (empty array)
- No UI control (future feature for custom media sets)

**Launcher Interpretation:**
- Only used when `media.use_theme_bank = false`
- Loads media files from specified paths
- Currently unused

**✅ ALIGNED** - Both default to empty array

---

### `media.shuffle`

**JSON Values:** Boolean `true` or `false`

**Visual Mode Creator:**
- Always exports: `false` (hardcoded)
- No UI control (future feature)

**Launcher Interpretation:**
- If `true`, randomizes media order
- If `false`, plays media in sorted filename order
- Default: `false`

**✅ ALIGNED** - No shuffle yet

---

## 📝 Text Settings

### `text.enabled`

**JSON Values:** Boolean `true` or `false`

**Visual Mode Creator:**
- UI Control: Checkbox "Enable Text Overlay"
- Default: Checked → `true`

**Launcher Interpretation:**
- Reads boolean value
- Calls `text_director.set_enabled(enabled)`
- When disabled, no text rendered

**✅ ALIGNED**

---

### `text.mode`

**JSON Values:** `"centered_sync"`, `"subtext"`

**Visual Mode Creator:**
- UI Control: Combo box "Text Display Mode"
- Options:
  - "Centered (Synced with Media)" → `"centered_sync"`
  - "Scrolling Carousel (Wallpaper)" → `"subtext"`
- Default: "Centered (Synced with Media)" → `"centered_sync"`

**Launcher Interpretation:**
- Reads string value
- Maps to SplitMode enum:
  - `"centered_sync"` → `SplitMode.CENTERED_SYNC`
  - `"subtext"` → `SplitMode.SUBTEXT`
- Calls `text_director.set_all_split_mode(mode)`

**✅ ALIGNED**

**Mode Behaviors:**
- **CENTERED_SYNC**: Text changes with each media item (synced transitions)
- **SUBTEXT**: Scrolling text grid filling screen (wallpaper effect)

---

### `text.opacity`

**JSON Values:** Float 0.0 - 1.0

**Visual Mode Creator:**
- UI Control: Slider "Text Opacity"
- Range: 0-100 (maps to 0.0 - 1.0)
- Default: 80 → `0.8`
- Label shows: "80%"

**Launcher Interpretation:**
- Reads float value (0.0 - 1.0)
- Calls `compositor.set_text_opacity(opacity)`
- Applied to text rendering

**✅ ALIGNED**

---

### `text.use_theme_bank`

**JSON Values:** Boolean `true` or `false`

**Visual Mode Creator:**
- Always exports: `true` (hardcoded)
- No UI control

**Launcher Interpretation:**
- If `true`, loads text from global text library
- If `false`, uses `text.library` array
- Default: `true`

**✅ ALIGNED**

---

### `text.library`

**JSON Values:** Array of text strings (e.g., `["Text 1", "Text 2"]`)

**Visual Mode Creator:**
- Always exports: `[]` (empty array)
- Preview uses hardcoded sample texts
- No UI control for custom text library

**Launcher Interpretation:**
- Only used when `text.use_theme_bank = false`
- Loads text phrases from array
- Currently unused

**✅ ALIGNED** - Both default to empty array

---

### `text.sync_with_media`

**JSON Values:** Boolean `true` or `false`

**Visual Mode Creator:**
- Always exports: `true` (hardcoded)
- No UI control

**Launcher Interpretation:**
- When `true` and mode is `"centered_sync"`, text changes with media
- When `false`, text changes on its own timer
- Default: `true`

**✅ ALIGNED** - Always synced for now

---

## 🔍 Zoom Settings

### `zoom.mode`

**JSON Values:** `"exponential"`, `"pulse"`, `"linear"`, `"none"`

**Visual Mode Creator:**
- UI Control: Combo box "Zoom Mode"
- Options:
  - "Exponential (Falling In)" → `"exponential"`
  - "Pulse (Wave)" → `"pulse"`
  - "Linear (Legacy)" → `"linear"`
  - "Disabled" → `"none"`
- Default: "Exponential (Falling In)" → `"exponential"`

**Launcher Interpretation:**
- Reads string value
- Calls `compositor.start_zoom_animation(mode=zoom_mode)`
- Modes:
  - `"exponential"`: Accelerating zoom (falling into image)
  - `"pulse"`: Sinusoidal wave zoom in/out
  - `"linear"`: Constant zoom rate
  - `"none"`: No zoom (static scale=1.0)

**✅ ALIGNED**

---

### `zoom.rate`

**JSON Values:** Float 0.0 - 5.0 (e.g., `0.74`)

**Visual Mode Creator:**
- UI Control: Slider "Zoom Rate"
- Range: 0-500 (maps to 0.0 - 5.0, divided by 100)
- Default: 20 → `0.2`
- Label shows: "0.200"
- **Applies immediately to preview**

**Launcher Interpretation:**
- Reads float value (0.0 - 5.0)
- Stored in `compositor._zoom_rate`
- Used in exponential/linear zoom calculations
- Higher = faster zoom

**✅ ALIGNED**

---

### ~~`zoom.duration_frames`~~ ❌ REMOVED

**Status:** ⛔ **FIELD REMOVED** (redundant)

**Reason for removal:**
- Not used by launcher (zoom duration controlled by media cycle speed)
- Zoom animation resets on each media change (tied to `media.cycle_speed`)
- Exponential/pulse zooms run indefinitely based on rate
- No meaningful way to apply fixed duration in current architecture

**Migration:** Existing mode files with `zoom.duration_frames` will ignore the field.

---

## 🚫 Excluded Settings

### Spiral Colors (arm_color, gap_color)

**Why excluded:**
- Design decision to keep colors as global "theme" settings
- Prevents per-mode color overload (easier UX)
- User can change colors in launcher, applies to all modes

**Visual Mode Creator:**
- Has color pickers in UI
- Applies to preview immediately
- **NOT exported to JSON**

**Launcher:**
- Uses global spiral color settings
- Controlled via launcher UI (not per-mode)

---

## 📊 Summary Table

| Setting | JSON Field | VMC UI Control | Launcher Method | Status |
|---------|-----------|----------------|-----------------|--------|
| **Spiral Type** | `spiral.type` | Combo box | `set_spiral_type(id)` | ⚠️ Name mismatch |
| **Rotation Speed** | `spiral.rotation_speed` | Slider (40-400) | `set_rotation_speed(float)` | ✅ Aligned |
| **Spiral Opacity** | `spiral.opacity` | Slider (0-100%) | `set_opacity(float)` | ✅ Aligned |
| **Spiral Intensity** | `spiral.intensity` | ❌ Not exposed | `set_intensity(float)` | ⚠️ Missing UI |
| **Reverse** | `spiral.reverse` | Checkbox | Negates speed | ✅ Aligned |
| **Arm/Gap Color** | ❌ Not stored | Color pickers | Global settings | ✅ By design |
| **Media Mode** | `media.mode` | Combo box | Filters media list | ✅ Aligned |
| **Cycle Speed** | `media.cycle_speed` | Slider (1-100) | ActionCycler period | ✅ Aligned (30fps fix) |
| **Fade Duration** | `media.fade_duration` | Slider (0.0-5.0s) | Cross-fade timing | ✅ Aligned (60fps) |
| ~~**Media Opacity**~~ | ~~`media.opacity`~~ | ~~Slider (0-100%)~~ | ❌ **REMOVED** | ⛔ Not needed |
| **Use ThemeBank** | `media.use_theme_bank` | Hardcoded true | Loads MEDIA dirs | ✅ Aligned |
| **Media Paths** | `media.paths` | ❌ Not exposed | Custom media list | ✅ Aligned (unused) |
| **Shuffle** | `media.shuffle` | ❌ Not exposed | Randomize order | ✅ Aligned (unused) |
| **Text Enabled** | `text.enabled` | Checkbox | `set_enabled(bool)` | ✅ Aligned |
| **Text Mode** | `text.mode` | Combo box | `set_all_split_mode()` | ✅ Aligned |
| **Text Opacity** | `text.opacity` | Slider (0-100%) | `set_text_opacity(float)` | ✅ Aligned |
| **Text ThemeBank** | `text.use_theme_bank` | Hardcoded true | Uses global library | ✅ Aligned |
| **Text Library** | `text.library` | ❌ Not exposed | Custom text list | ✅ Aligned (unused) |
| **Text Sync** | `text.sync_with_media` | Hardcoded true | Change with media | ✅ Aligned |
| **Zoom Mode** | `zoom.mode` | Combo box | `start_zoom_animation()` | ✅ Aligned |
| **Zoom Rate** | `zoom.rate` | Slider (0-500) | `_zoom_rate` | ✅ Aligned |
| ~~**Zoom Duration**~~ | ~~`zoom.duration_frames`~~ | ~~Hardcoded 180~~ | ❌ **REMOVED** | ⛔ Redundant |

---

## 🛠️ Fixes Needed

### 1. Spiral Type Name Mismatch (CRITICAL)

**Issue:** Visual Mode Creator and Launcher use different names for spiral types 5-7.

**Current:**
```python
# visual_mode_creator.py
spiral_type_names = ["", "logarithmic", "quadratic", "linear", "sqrt", "inverse", "power", "sawtooth"]

# custom_visual.py
spiral_type_map = {
    "logarithmic": 1,
    "quadratic": 2,
    "linear": 3,
    "sqrt": 4,
    "cubic": 5,      # ← Mismatch!
    "power": 6,      # ← Mismatch!
    "hyperbolic": 7  # ← Mismatch!
}
```

**Fix:** Update `custom_visual.py` to match Visual Mode Creator names.

---

### 2. Missing Intensity UI Control

**Issue:** `spiral.intensity` is exported but not exposed in Visual Mode Creator UI.

**Current Behavior:** Opacity slider sets intensity (conflated controls).

**Recommendation:** Add separate "Intensity" slider (0-100%) in Visual Mode Creator.

---

### 3. Zoom Duration Field Unused

**Status:** ✅ **RESOLVED** - Field removed from JSON schema (not needed)

---

### 4. ~~Media Opacity Not Implemented~~

**Status:** ✅ **RESOLVED** - Field removed from JSON schema (no compositor implementation needed)

---

## 📝 Documentation Improvements

### Visual Mode Creator UI

Add tooltips/labels:
- "Spiral colors are global settings (not saved per-mode)"
- "ThemeBank media is used by default"
- "Text syncs with media transitions"

### Launcher UI

Add info text when loading custom modes:
- "Using global spiral colors"
- "Loaded X images, Y videos from ThemeBank"

### JSON Schema Documentation

Create `mode-schema.json` with full JSON Schema validation.

---

## 🎯 Recommendations

1. **Fix spiral type name mismatch** (high priority)
2. **Add intensity slider** to Visual Mode Creator
3. ~~**Implement media opacity** in compositor~~ ✅ RESOLVED (field removed)
4. ~~**Remove unused duration_frames** field~~ ✅ RESOLVED (field removed)
5. **Add JSON schema validation** for mode files
6. **Add tooltips** explaining global vs. per-mode settings
7. **Document cycle_speed formula** (exponential curve rationale)

---

## 📖 Related Documentation

- [docs/cli.md](../cli.md) - CLI commands for mode loading
- [docs/technical/spiral-overlay.md](spiral-overlay.md) - Spiral parameter details
- [docs/technical/cli-interface.md](cli-interface.md) - CLI design
- [scripts/visual_mode_creator.py](../../scripts/visual_mode_creator.py) - Mode creator source
- [mesmerglass/engine/custom_visual.py](../../mesmerglass/engine/custom_visual.py) - Mode loader source
