# Launcher Simplification - Changes Made

## Summary
Simplified MesmerLoom panel to remove all mode-controlled settings. The launcher now focuses on:
1. **Spiral Colors** (global, not in JSON) - Arm/Gap color pickers
2. **Custom Mode Loading** - Browse, load, reload modes
3. **Text Library** (separate tab) - Add/edit messages
4. **Audio/Device/Displays** (unchanged)

## Files Modified

### 1. `mesmerglass/ui/panel_mesmerloom.py`
**Status**: ✅ REPLACED (old backed up as `panel_mesmerloom_old.py`)

**Removed Controls:**
- ❌ Intensity/Opacity slider → Now in JSON (`spiral.opacity`, `spiral.intensity`)
- ❌ Spiral Type dropdown → Now in JSON (`spiral.type`)
- ❌ Spiral Width dropdown → Now in JSON (derived from type)
- ❌ Rotation Speed slider → Now in JSON (`spiral.rotation_speed`)
- ❌ Blend Mode dropdown → Now in JSON (render settings)
- ❌ Media Mode selector → Now in JSON (`media.mode`)
- ❌ Image/Video Duration spinboxes → Now in JSON (`media.cycle_speed`)
- ❌ Max Zoom slider → Now in JSON (`zoom.rate`)

**Kept Controls:**
- ✅ **Arm Color** button - Pick spiral arm color (global setting)
- ✅ **Gap Color** button - Pick spiral gap/background color (global setting)
- ✅ **Browse Mode** button - Select custom mode JSON file
- ✅ **Reload Mode** button - Reload current mode (Ctrl+R shortcut)
- ✅ **Recent Modes** list - Quick access to recently loaded modes
- ✅ **Current Mode** label - Shows loaded mode name

**New UI Layout:**
```
╔═══════════════════════════════════════╗
║  🎨 Spiral Colors                     ║
║  ├─ Info: Global settings (not in JSON)
║  ├─ 🌈 Arm Color (White) [Button]     ║
║  └─ ⚫ Gap Color (Black) [Button]      ║
╠═══════════════════════════════════════╣
║  📂 Custom Mode                       ║
║  ├─ Current Mode: (No mode loaded)   ║
║  ├─ [📁 Browse...] [↻ Reload]         ║
║  ├─ Recent Modes:                     ║
║  │   • speed.json                     ║
║  │   • test_deep_trance.json          ║
║  │   • sinking.json                   ║
║  └─ 💡 Tip: Create modes with VMC     ║
╚═══════════════════════════════════════╝
```

**Signal Changes:**
- Removed: `intensityChanged`, `blendModeChanged`, `rotationSpeedChanged`, `zoomSpeedChanged`, `mediaModeChanged`, `imageDurationChanged`, `videoDurationChanged`
- Kept: `armColorChanged`, `gapColorChanged`

**Method Changes:**
- Removed: `_on_intensity()`, `_on_blend_mode()`, `_on_spiral_type()`, `_on_spiral_width()`, `_on_rotation_speed()`, `_on_max_zoom()`, `_on_media_mode()`, `_on_image_duration()`, `_on_video_duration()`
- Added: `_on_browse_mode()`, `_on_reload_mode()`, `_on_recent_mode_clicked()`, `_load_mode()`, `_update_recent_modes_list()`
- Kept: `_pick_color()`, `_apply_color()`, `lock_controls()`, `unlock_controls()`

## Next Steps (TODO)

### Step 2: Remove Visual Programs Tab
- [ ] Remove import of `pages/visual_programs.py` from launcher.py
- [ ] Remove Visual Programs tab creation
- [ ] Remove from sidebar navigation
- [ ] Remove signal connections for built-in programs
- [ ] Keep only custom mode handlers

### Step 3: Remove Built-in Visual Programs from VisualDirector
- [ ] Remove `VISUAL_PROGRAMS` constant (7 hardcoded programs)
- [ ] Remove program selection/execution logic
- [ ] Keep CustomVisual class and loading logic
- [ ] Keep media cycling, text, and compositor integration

### Step 4: Update Tab Structure
Current tabs:
1. ✍️ Text (Keep)
2. 🌀 MesmerLoom (✅ Simplified)
3. 🎵 Audio (Keep)
4. 🔗 Device Sync (Keep)
5. 🎬 Visual Programs (Remove - Step 2)
6. 🖥️ Displays (Keep)

New tabs:
1. 🌀 MesmerLoom (✅ Simplified)
2. ✍️ Text
3. 🎵 Audio
4. 🔗 Device Sync
5. 🖥️ Displays

### Step 5: Documentation Updates
- [ ] Update user guide with new workflow
- [ ] Document spiral color exception (why global)
- [ ] Create migration guide for existing users
- [ ] Update launcher README

## Testing Checklist

### Basic Functionality
- [ ] Launch application without errors
- [ ] MesmerLoom tab displays correctly
- [ ] Color pickers open and work
- [ ] Colors apply to spiral
- [ ] Browse button opens file dialog
- [ ] Load custom mode successfully
- [ ] Recent modes list populates
- [ ] Click recent mode to load
- [ ] Reload button works (Ctrl+R)

### Mode Loading
- [ ] Load speed.json (30x rotation)
- [ ] Verify settings applied from JSON
- [ ] Change spiral colors (should work)
- [ ] Try to adjust mode settings (should be in JSON only)
- [ ] Load different mode
- [ ] Reload current mode
- [ ] Recent modes persists between loads

### Integration
- [ ] Custom mode works with Text tab
- [ ] Custom mode works with Audio tab
- [ ] Custom mode works with Device Sync
- [ ] Launch overlay with custom mode
- [ ] Spiral displays with correct colors
- [ ] Mode settings respected (speed, type, media, etc.)

## Benefits of This Change

✅ **Simpler UI**: 2 buttons + file picker vs. 10+ sliders/dropdowns  
✅ **No Conflicts**: JSON is single source of truth  
✅ **User Empowerment**: Create unlimited modes with Visual Mode Creator  
✅ **Clear Workflow**: Create mode → Load mode → Adjust colors → Launch  
✅ **Maintainability**: No UI controls to sync with JSON schema  
✅ **Consistency**: Visual Mode Creator preview matches launcher exactly  

## Breaking Changes

⚠️ **Users can no longer adjust these settings in the launcher UI:**
- Spiral intensity/opacity
- Spiral type
- Spiral width
- Rotation speed
- Media mode
- Image/Video duration
- Max zoom

**Migration Path:**
1. Use Visual Mode Creator to create modes with desired settings
2. Export as JSON
3. Load in launcher
4. Adjust colors as needed (global preference)

## Notes

- Old panel backed up as `panel_mesmerloom_old.py` for reference
- Signal connections in launcher.py may need updating (Step 2)
- Lock/unlock logic simplified (colors always editable)
- Recent modes stored in widget state (could persist to config file later)
