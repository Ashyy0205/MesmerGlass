# CustomVisual ThemeBank API Fix

**Date:** 2025-01-XX  
**Issue:** AttributeError when loading custom modes with `use_theme_bank=true`  
**Files Modified:** `mesmerglass/engine/custom_visual.py`

---

## Problem

When attempting to load a custom mode JSON file with `"use_theme_bank": true` in the launcher, the following error occurred:

```
AttributeError: 'ThemeBank' object has no attribute 'image_paths'
```

**Location:** `custom_visual.py` line 215 in `_apply_media_settings()`

```python
# BROKEN CODE (lines 215-221):
if self._media_mode == "images":
    self._media_paths = list(self.theme_bank.image_paths)  # ❌ FAILS
elif self._media_mode == "videos":
    self._media_paths = list(self.theme_bank.video_paths)  # ❌ FAILS
elif self._media_mode == "both":
    self._media_paths = list(self.theme_bank.image_paths) + list(self.theme_bank.video_paths)  # ❌ FAILS
```

---

## Root Cause

**API Mismatch:** CustomVisual was trying to extract all media paths from ThemeBank using non-existent attributes (`image_paths`, `video_paths`).

**ThemeBank Design:** ThemeBank is designed for **dynamic media selection**, not bulk path extraction:
- Provides images one-at-a-time via `get_image(alternate=False)` method
- Internally manages shuffling, weighting, and avoiding repetition (last 8 images)
- Does **not** expose `image_paths` or `video_paths` attributes

**CustomVisual Design Conflict:** CustomVisual was designed to work with **explicit path lists** for handpicked custom media, but incorrectly assumed ThemeBank could provide such a list.

---

## Solution

**Strategy:** Add dual-mode support to CustomVisual:
1. **ThemeBank Mode:** Use `theme_bank.get_image()` dynamically (no path list)
2. **Explicit Path Mode:** Use handpicked paths from JSON config

### Changes Made

#### 1. Added `_use_theme_bank_media` Flag (line ~96)

```python
# Media state
self._current_media_index = 0
self._media_paths: List[Path] = []
self._media_mode: str = "images"  # "images", "videos", "both", "none"
self._use_theme_bank_media = False  # NEW: Flag to use ThemeBank.get_image() instead of paths
```

#### 2. Fixed `_apply_media_settings()` (lines ~210-240)

**Before:**
```python
if use_theme_bank and self.theme_bank:
    # ❌ BROKEN: Try to extract all paths from ThemeBank
    if self._media_mode == "images":
        self._media_paths = list(self.theme_bank.image_paths)  # FAILS
```

**After:**
```python
if use_theme_bank and self.theme_bank:
    # ✅ FIXED: Set flag to use ThemeBank.get_image() dynamically
    self._use_theme_bank_media = True
    self._media_paths = []  # Empty - not used when ThemeBank active
    self.logger.debug(f"[CustomVisual] Using ThemeBank dynamic media ({self._media_mode})")
else:
    # Use explicit paths from config (handpicked custom media)
    self._use_theme_bank_media = False
    paths = media_config.get("paths", [])
    self._media_paths = [Path(p) for p in paths]
```

#### 3. Fixed `_load_current_media()` (lines ~333-365)

**Added ThemeBank path:**
```python
def _load_current_media(self) -> None:
    """Load the current media item (image or video)."""
    if self._use_theme_bank_media:
        # ✅ NEW: Use ThemeBank.get_image() directly (no path list)
        if self._media_mode in ("images", "both"):
            if self.on_change_image:
                self.on_change_image(0)  # Index ignored when using ThemeBank
                self.logger.debug("[CustomVisual] Loaded image from ThemeBank")
        
        # Trigger text change if in CENTERED_SYNC mode
        if self.text_director:
            self.text_director.on_media_change()
        return
    
    # Original explicit path list logic continues...
```

#### 4. Fixed `build_cycler()` (lines ~310-330)

**Updated cycle logic:**
```python
def cycle_media():
    """Advance to next media item."""
    if self._use_theme_bank_media:
        # ✅ NEW: ThemeBank mode - just load next image (ThemeBank handles selection)
        self._load_current_media()
    elif self._media_paths:
        # Original explicit path cycling continues...
        self._current_media_index = (self._current_media_index + 1) % len(self._media_paths)
        self._load_current_media()
```

#### 5. Fixed `reset()` (line ~357)

**Updated initial load check:**
```python
# Load first media item
if self._use_theme_bank_media or self._media_paths:  # ✅ FIXED: Check flag OR paths
    self._load_current_media()
```

---

## Technical Notes

### ThemeBank API (Reference)

Located in `mesmerglass/content/themebank.py`:

```python
class ThemeBank:
    """Manages multiple themes and media selection."""
    
    def get_image(self, alternate: bool = False) -> Optional[ImageData]:
        """Get next image from active theme (primary or alternate)."""
        # Returns ImageData with pixel data, width, height
        # Internally uses Shuffler for weighted random selection
        # Avoids last 8 selected images
    
    def get_text_line(self, alternate: bool = False) -> Optional[str]:
        """Get random text line from active theme."""
    
    def set_active_themes(self, primary_index: int, alt_index: Optional[int] = None):
        """Set which themes are active (1-indexed like Trance)."""
```

### Why This Fix Works

1. **Respects ThemeBank Design:** Uses `get_image()` as intended, not trying to extract internal data
2. **Preserves Explicit Path Mode:** Custom modes can still use handpicked media via `"paths": [...]` in JSON
3. **Maintains Shuffling/Weighting:** ThemeBank's internal Shuffler continues to work correctly
4. **Backward Compatible:** Existing custom modes without `use_theme_bank` still work

### Video Support Limitation

**Note:** ThemeBank currently only supports images. Videos are not implemented in ThemeBank's API.

From the code comment:
```python
# TODO: ThemeBank doesn't currently support videos - only images
# If videos are needed, would need to add get_video() method to ThemeBank
```

If `"mode": "videos"` or `"mode": "both"` is set with ThemeBank, only images will load. To use videos in custom modes, set `"use_theme_bank": false` and provide explicit `"paths": [...]` in the JSON config.

---

## Testing

### Test Custom Mode Loading

1. Launch launcher: `./.venv/bin/python run.py`
2. Go to **Visual Programs** tab
3. Click **"Load Custom Mode"**
4. Select a mode file (e.g., `test_deep_trance.json` or `sinking.json`)
5. **Expected:** Mode loads without errors, images cycle from ThemeBank
6. **Verify:** Spiral settings, text overlays, zoom animations all apply correctly

### Verify ThemeBank Media Cycling

1. Load custom mode with `"use_theme_bank": true`
2. Watch for image changes based on `cycle_speed` setting
3. **Expected:** Images cycle smoothly using ThemeBank's weighted shuffler
4. **Verify:** No repeated images within ~8 changes (ThemeBank anti-repeat system)

### Verify Explicit Path Mode Still Works

1. Create custom mode with `"use_theme_bank": false` and `"paths": ["path/to/image1.jpg", ...]`
2. Load in launcher
3. **Expected:** Only specified images cycle in order (or shuffled if `"shuffle": true`)

---

## Related Files

- `mesmerglass/engine/custom_visual.py` - Fixed CustomVisual class
- `mesmerglass/content/themebank.py` - ThemeBank API reference
- `mesmerglass/content/theme.py` - ThemeConfig dataclass (image_path, animation_path, text_line)
- `scripts/visual_mode_creator.py` - Tool that exports custom mode JSON files

---

## Future Enhancements

1. **Video Support in ThemeBank:**
   - Add `get_video()` method to ThemeBank
   - Update CustomVisual to call `get_video()` when `mode="videos"` or `mode="both"`

2. **Alternate Theme Support:**
   - Expose `alternate` parameter in custom mode JSON
   - Allow switching between primary/alternate themes dynamically

3. **Theme Switch Cooldown:**
   - Add `"switch_themes": true` option in custom mode JSON
   - Call `theme_bank.switch_themes()` periodically (respects cooldown)

---

## Commit Message

```
Fix CustomVisual ThemeBank API mismatch

- Remove broken image_paths/video_paths attribute access
- Add _use_theme_bank_media flag for dual-mode support
- Use theme_bank.get_image() dynamically when ThemeBank enabled
- Preserve explicit path list mode for handpicked custom media
- Update build_cycler(), _load_current_media(), reset() methods

Fixes AttributeError when loading custom modes with use_theme_bank=true
```
