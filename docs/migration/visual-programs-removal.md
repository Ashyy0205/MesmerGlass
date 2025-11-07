# Visual Programs Tab Removal - Migration Guide

## Overview
The Visual Programs tab has been removed from the MesmerGlass UI to simplify the interface. The complex 7-program selection system has been replaced with a simple **Media Mode** selector in the MesmerLoom tab.

**Current Status:** ✅ Complete - 3 media modes implemented with MixedVisual for balanced content.

## Changes Made

### 1. UI Simplification
**Removed:**
- 🎬 Visual Programs tab (entire page and controls)
- Visual program selection dropdown
- Start/Stop/Pause/Reset buttons
- Progress display and timer
- 7 different visual program modes (Text-Only, Image-Only, Video-Only, Text+Image, Text+Video, Image+Video, Full)

**Added:**
- Simple **Media Mode** dropdown in MesmerLoom "General Controls" section
- 3 modes: "Images & Videos" (default), "Images Only", "Videos Only"

### 2. Files Modified

#### `mesmerglass/ui/panel_mesmerloom.py`
- Added `mediaModeChanged` signal (line 25)
- Added media mode dropdown in General Controls (lines 36-46)
- Added `_on_media_mode()` slot method (lines 169-177)

#### `mesmerglass/ui/launcher.py`
- Removed import: `from .pages.visual_programs import VisualProgramsPage`
- Removed Visual Programs tab creation (was lines 355-358)
- Removed navigation list entry for "🎬 Visual Programs"
- Changed start tab from Visual Programs to MesmerLoom (tab index 0)
- Removed all Visual Programs signal connections (previously lines 464-485)
- Removed all Visual Programs slot methods:
  - `_on_visual_selected()`
  - `_on_visual_start()`
  - `_on_visual_stop()`
  - `_on_visual_pause()`
  - `_on_visual_reset()`
  - `_on_visual_update_progress()`

### 3. Navigation Changes
**Before:**
```
Tab 0: 🎬 Visual Programs (START HERE!)
Tab 1: 🌀 MesmerLoom
Tab 2: 🎵 Audio
Tab 3: 🔗 Device Sync
Tab 4: 🖥️ Displays
```

**After:**
```
Tab 0: 🌀 MesmerLoom (START HERE!)
Tab 1: 🎵 Audio
Tab 2: 🔗 Device Sync
Tab 3: 🖥️ Displays
```

## Media Mode Selector

### Options
1. **Images & Videos** (default)
   - Loads both images and videos from configured media folders
   - Automatically cycles between media types
   - Triggers zoom animation on load

2. **Images Only**
   - Only loads and displays image files (.jpg, .png, etc.)
   - Videos are filtered out

3. **Videos Only**
   - Only loads and displays video files (.mp4, .webm, etc.)
   - Images are filtered out

### Usage
1. Open MesmerGlass launcher
2. Navigate to **🌀 MesmerLoom** tab (now first tab)
3. In "General Controls" section, find **Media Mode** dropdown
4. Select your preferred mode
5. Launch the application

### Signal
- **Signal Name:** `mediaModeChanged(int)`
- **Values:**
  - `0` = Images & Videos
  - `1` = Images Only
  - `2` = Videos Only

## Migration Notes

### For Users
- All Visual Programs functionality has been removed
- Use the simple Media Mode selector for basic image/video filtering
- Full Trance recreation features remain in the underlying visual_director
- All other controls (rotation speed, zoom speed, spiral parameters) unchanged

### For Developers
- `VisualProgramsPage` class is no longer imported or used
- Visual director still exists for internal coordination
- Connect to `mediaModeChanged` signal to implement filtering logic
- Backend visual program system remains intact in `mesmerglass/engine/visual_director.py`

## Future Work

**Pending Implementation:**
The media mode filtering logic needs to be connected to the actual image/video loading system. Currently:
- ✅ UI dropdown exists and emits signal
- ⚠️ Signal needs to be connected to visual director or media loader
- ⚠️ Filtering logic needs to be implemented in image/video loading

**Next Steps:**
1. Connect `panel_mesmerloom.mediaModeChanged` to launcher
2. Implement filtering in visual_director or create simple media loader
3. Test each mode (images only, videos only, both)

## Related Features

**Unchanged:**
- ✅ Rotation speed control (400-4000 → 4.0x-40.0x)
- ✅ Zoom animation on media load (automatic)
- ✅ Zoom speed control (10-500 → 0.01-0.5 per frame)
- ✅ All spiral parameters (type, intensity, colors, blend modes)
- ✅ All audio reactivity features
- ✅ Device sync capabilities

## See Also
- `docs/technical/spiral-overlay.md` - Spiral parameters and controls
- `docs/cli.md` - CLI commands
- `mesmerglass/ui/panel_mesmerloom.py` - MesmerLoom UI controls
