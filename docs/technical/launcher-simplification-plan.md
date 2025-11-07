# Launcher Simplification Plan

## Overview
Remove hardcoded visual programs and mode-controlled settings from launcher UI.
All visual behavior (except spiral colors) is now controlled by JSON mode files created in Visual Mode Creator.

---

## Changes Summary

### REMOVED Components

#### 1. Built-in Visual Programs (7 programs)
- ❌ `VisualDirector.VISUAL_PROGRAMS` hardcoded list
- ❌ Visual Programs selector dropdown
- ❌ Start/Stop/Pause/Reset controls for built-in programs
- ❌ Progress bar for visual programs
- ❌ Visual Programs page UI
- **Reason**: All visuals now use CustomVisual loaded from JSON modes

#### 2. Mode-Controlled Settings (Now in JSON)
From MesmerLoom Tab:
- ❌ **Intensity/Opacity slider** → Controlled by `spiral.opacity` and `spiral.intensity` in JSON
- ❌ **Spiral Type dropdown** → Controlled by `spiral.type` in JSON  
- ❌ **Spiral Width dropdown** → Controlled by spiral type logic in JSON
- ❌ **Rotation Speed slider** → Controlled by `spiral.rotation_speed` in JSON
- ❌ **Blend Mode dropdown** → Controlled by render settings in JSON
- ❌ **Media Mode selector** → Controlled by `media.mode` in JSON
- ❌ **Text sync/mode controls** → Controlled by `text.*` in JSON
- ❌ **Zoom controls** → Controlled by `zoom.*` in JSON

---

## KEPT Components

### MesmerLoom Tab (Simplified)
✅ **Enable Spiral** checkbox - Global on/off toggle  
✅ **Arm Color** picker - Spiral arm color (global, not in JSON)  
✅ **Gap Color** picker - Spiral gap color (global, not in JSON)  
✅ **Custom Mode** section:
   - File picker button ("Browse...")
   - Current mode display label
   - Recent modes list (clickable)
   - Reload button (Ctrl+R)

### Other Tabs (Unchanged)
✅ **Text Tab** - Add/edit/weight text messages (library)  
✅ **Audio Tab** - Background music controls  
✅ **Device Sync Tab** - Buttplug.io device controls  
✅ **Displays Tab** - Monitor selection for overlay  

### Global Controls (Unchanged)
✅ **Launch Button** - Start/stop overlay  
✅ **Status Chips** - Overlay/device status  
✅ **Menu Bar** - Settings, help, etc.  

---

## New Simplified Tab Structure

```
┌─────────────────────────────────────┐
│  MesmerGlass                        │
├─────────────────────────────────────┤
│                                     │
│  🌀 MesmerLoom                      │  ← Simplified
│  ✍️  Text                            │
│  🎵 Audio                           │
│  🔗 Device Sync                     │
│  🖥️  Displays                        │
│                                     │
└─────────────────────────────────────┘
```

---

## New MesmerLoom Tab Layout

```
╔═══════════════════════════════════════════╗
║  🌀 Spiral Overlay                        ║
╠═══════════════════════════════════════════╣
║  ☑ Enable Spiral                          ║
╠═══════════════════════════════════════════╣
║  Spiral Colors                            ║
║  ├─ Arm Color:  [████] Pick Color         ║
║  └─ Gap Color:  [████] Pick Color         ║
╠═══════════════════════════════════════════╣
║  Custom Mode                              ║
║  ├─ Current: speed.json                   ║
║  ├─ [Browse Mode...] [↻ Reload (Ctrl+R)]  ║
║  └─ Recent Modes:                         ║
║      • speed.json                         ║
║      • test_deep_trance.json              ║
║      • sinking.json                       ║
╚═══════════════════════════════════════════╝

Note: All spiral behavior (speed, type, width, intensity,
      media cycling, text, zoom) is controlled by the
      loaded JSON mode file.
      
      Create modes with: scripts/visual_mode_creator.py
```

---

## Implementation Steps

### Phase 1: Remove Visual Programs Page
1. Remove `pages/visual_programs.py` import and tab creation
2. Remove Visual Programs from sidebar navigation
3. Remove signal connections for built-in programs
4. Remove `_on_visual_start`, `_on_visual_stop`, etc. handlers (keep only custom mode handlers)

### Phase 2: Simplify MesmerLoom Panel
1. Remove intensity slider and handler
2. Remove spiral type dropdown and handler  
3. Remove spiral width dropdown and handler
4. Remove rotation speed slider and handler
5. Remove blend mode dropdown and handler
6. Remove media mode selector
7. Keep only: Enable checkbox, color pickers, custom mode controls

### Phase 3: Update Control Locking Logic
1. Remove locking for removed controls
2. Update `_lock_mesmerloom_controls()` to only lock color pickers
3. Update `_unlock_mesmerloom_controls()` accordingly

### Phase 4: Clean Up Visual Director
1. Keep `VisualDirector` class (used for custom modes)
2. Remove `VISUAL_PROGRAMS` constant (7 hardcoded programs)
3. Remove visual program execution logic (keep only CustomVisual)
4. Remove program selection/switching logic

### Phase 5: Update Documentation
1. Update user guide to explain mode-only workflow
2. Document spiral color exception (why global)
3. Update launcher README
4. Add migration guide for users expecting old controls

---

## Rationale

### Why Remove Built-in Programs?
- **Redundant**: CustomVisual JSON modes can replicate all 7 programs
- **Maintenance**: Hardcoded programs are inflexible and hard to modify
- **User Control**: Mode files give users full control without code changes
- **Consistency**: Single source of truth (JSON modes)

### Why Keep Spiral Colors Global?
- **Creative Freedom**: Users want to try different color schemes on same mode
- **Quick Tweaking**: Change colors without recreating mode file
- **Separation of Concerns**: Pattern (mode) vs. Theme (colors)
- **UX**: Instant visual feedback without reload

### Why Remove Mode-Controlled Settings?
- **Confusion**: Having both UI and JSON control caused conflicts
- **Precedence Issues**: Which wins? UI or JSON?
- **Lock Logic Complexity**: Had to disable controls when mode active
- **User Expectation**: If mode file specifies settings, they should be respected

---

## Migration Path for Users

### Old Workflow:
1. Open launcher
2. Go to MesmerLoom tab
3. Adjust intensity, rotation speed, spiral type manually
4. Go to Visual Programs tab
5. Select a built-in program
6. Click Start
7. Click Launch

### New Workflow:
1. Create mode in Visual Mode Creator (or use existing)
2. Export mode JSON
3. Open launcher
4. Go to MesmerLoom tab
5. Browse and load mode file
6. (Optional) Adjust spiral colors
7. Click Launch

---

## Benefits

✅ **Simpler UI**: Fewer controls = less overwhelming  
✅ **No Conflicts**: JSON is single source of truth  
✅ **More Powerful**: Users can create unlimited custom modes  
✅ **Easier Maintenance**: No hardcoded visual programs to update  
✅ **Better UX**: Clear workflow (create mode → load mode → launch)  
✅ **Consistent**: Visual Mode Creator preview matches launcher exactly  

---

## Files to Modify

1. `mesmerglass/ui/launcher.py` - Remove visual programs tab, update sidebar
2. `mesmerglass/ui/panel_mesmerloom.py` - Simplify to colors + mode picker only
3. `mesmerglass/ui/pages/visual_programs.py` - DELETE (no longer needed)
4. `mesmerglass/engine/visual_director.py` - Remove VISUAL_PROGRAMS constant
5. `docs/user-guide/launcher.md` - Update usage docs
6. `docs/migration/visual-programs-removal.md` - NEW migration guide

---

## Testing Checklist

- [ ] Load custom mode from MesmerLoom tab
- [ ] Change spiral colors while mode active
- [ ] Reload mode with Ctrl+R
- [ ] Launch overlay with custom mode
- [ ] Verify mode settings applied correctly
- [ ] Check that removed controls are gone
- [ ] Verify Text tab still works independently
- [ ] Test mode switching (load different mode)
- [ ] Check recent modes list
- [ ] Verify no crashes on mode load/unload
