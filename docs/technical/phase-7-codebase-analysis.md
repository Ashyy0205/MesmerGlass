# Phase 7 Codebase Analysis - Complete System Architecture

**Date:** November 10, 2025  
**Purpose:** Document existing systems, data formats, and integration points for Phase 7 GUI redesign  
**Status:** COMPLETE ✅

---

## Executive Summary

This document provides a comprehensive analysis of the MesmerGlass codebase to ensure the Phase 7 GUI redesign accurately represents existing functionality and integrates cleanly with current systems.

**Key Findings:**
- **Playbacks** are stored as `.json` files (NOT `.vmode`)
- **No display settings** exist (only display selection for monitors/VR)
- **SessionRunner** (Phase 6) handles cuelist execution with cycle-synchronized transitions
- **VisualDirector** loads playback JSON files via `CustomVisual` class
- **AudioEngine** manages multi-channel audio with fade in/out
- **MediaBank** uses shared `media_bank.json` config file

---

## 1. Data Formats

### 1.1 Playback Files (`.json`)

**Location:** `mesmerglass/playbacks/*.json`  
**Created by:** Visual Mode Creator (`scripts/visual_mode_creator.py`)  
**Loaded by:** `VisualDirector.load_playback()` → `CustomVisual` class

**Structure:**
```json
{
  "version": "1.0",
  "name": "Deep Red Spiral",
  "description": "Slow logarithmic spiral with red tones",
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": 100.0,
    "opacity": 0.48,
    "reverse": true
  },
  "media": {
    "mode": "both",
    "cycle_speed": 50,
    "fade_duration": 0.0,
    "use_theme_bank": true,
    "paths": [],
    "shuffle": false,
    "bank_selections": [0]
  },
  "text": {
    "enabled": true,
    "mode": "centered_sync",
    "opacity": 0.69,
    "use_theme_bank": true,
    "library": [],
    "sync_with_media": true
  },
  "zoom": {
    "mode": "exponential",
    "rate": 0.98
  }
}
```

**Fields:**
- `spiral.type`: `logarithmic`, `quadratic`, `linear`, `sqrt`, `inverse`, `power`, `sawtooth`
- `spiral.rotation_speed`: Rotation speed in RPM (positive float)
- `spiral.opacity`: 0.0-1.0
- `spiral.reverse`: boolean
- `media.mode`: `both`, `images`, `videos`, `none`
- `media.cycle_speed`: 1-100 (higher = faster)
- `media.fade_duration`: seconds (0.0-5.0)
- `media.use_theme_bank`: boolean (if true, uses MediaBank)
- `media.bank_selections`: array of MediaBank indices
- `text.enabled`: boolean
- `text.mode`: `centered_sync`, `subtext`
- `text.opacity`: 0.0-1.0
- `text.use_theme_bank`: boolean
- `zoom.mode`: `exponential`, `pulse`, `linear`, `none`
- `zoom.rate`: 0.0-1.0

**Note:** Spiral arm/gap colors are NOT stored in playback files - they are controlled globally in the launcher.

---

### 1.2 Cuelist Files (`.cuelist.json`)

**Location:** `cuelists/*.cuelist.json`, `examples/*.cuelist.json`  
**Created by:** Manual JSON editing (Phase 7 will add Cuelist Editor)  
**Loaded by:** `Cuelist.load(path)` → `SessionRunner`

**Structure:**
```json
{
  "name": "Short Demo Session",
  "description": "15-minute demonstration session",
  "version": "1.0",
  "author": "MesmerGlass Examples",
  "loop_mode": "once",
  "cues": [
    {
      "name": "Induction",
      "duration_seconds": 300,
      "playback_pool": [
        {
          "playback": "playbacks/example_deep_red.json",
          "weight": 1.0
        }
      ],
      "selection_mode": "on_cue_start",
      "transition_in": {
        "type": "fade",
        "duration_ms": 2000
      },
      "transition_out": {
        "type": "fade",
        "duration_ms": 1500
      },
      "audio_tracks": []
    }
  ],
  "metadata": {
    "difficulty": "beginner",
    "tags": ["induction", "deepening", "demo"],
    "total_minutes": 18
  }
}
```

**Cuelist Fields:**
- `name`: string
- `description`: string
- `version`: string (default "1.0")
- `author`: string
- `loop_mode`: `once`, `loop`, `ping_pong`
- `cues`: array of Cue objects
- `metadata`: dict (optional custom fields)

**Cue Fields:**
- `name`: string
- `duration_seconds`: float (how long this cue lasts)
- `playback_pool`: array of PlaybackEntry objects
- `selection_mode`: `on_cue_start`, `on_media_cycle`, `on_timed_interval`
- `transition_in`: dict (type, duration_ms)
- `transition_out`: dict (type, duration_ms)
- `audio_tracks`: array of AudioTrack objects (0-2 tracks)

**PlaybackEntry Fields:**
- `playback`: string (path to playback JSON file, relative to cuelist file)
- `weight`: float (selection probability weight)
- `min_cycles`: int (optional - minimum media cycles before switch)
- `max_cycles`: int (optional - maximum cycles before forced switch)

**AudioTrack Fields:**
- `file`: string (path to audio file, relative to cuelist file)
- `volume`: float (0.0-1.0)
- `loop`: boolean
- `fade_in_ms`: float (milliseconds)
- `fade_out_ms`: float (milliseconds)

---

### 1.3 Media Bank Configuration (`media_bank.json`)

**Location:** Project root (`media_bank.json`)  
**Created by:** Launcher MediaBank tab, Visual Mode Creator  
**Loaded by:** Launcher on init, Visual Mode Creator on init

**Structure:**
```json
[
  {
    "name": "Default Images",
    "path": "C:/Users/Ash/Desktop/MesmerGlass/MEDIA/Images",
    "type": "images"
  },
  {
    "name": "Ambient Videos",
    "path": "C:/Users/Ash/Desktop/MesmerGlass/MEDIA/Videos",
    "type": "videos"
  }
]
```

**Fields:**
- `name`: string (display name)
- `path`: string (absolute or relative path to directory)
- `type`: `images`, `videos`, `audio` (optional, inferred from path)

**Synchronization:** Single shared file edited by both Launcher and Visual Mode Creator.

---

## 2. Existing Systems & Classes

### 2.1 SessionRunner (`mesmerglass/session/runner.py`)

**Purpose:** Execute cuelist sessions with cycle-synchronized transitions

**Key Methods:**
- `start()` → bool: Start session from first cue
- `pause()` → None: Pause execution
- `resume()` → None: Resume from pause
- `stop()` → None: Stop and cleanup
- `skip_cue()` → bool: Skip to next cue
- `update(dt: float)` → None: Advance state (called every frame)

**State Machine:**
- `STOPPED` → can start
- `RUNNING` → active execution
- `PAUSED` → can resume
- `COMPLETED` → finished (ONCE mode)

**Dependencies:**
- `Cuelist` object
- `VisualDirector` (for loading playbacks, tracking cycles)
- `AudioEngine` (for audio playback)
- `SessionEventEmitter` (for UI updates)

**Integration:** Created by `SessionRunnerTab` in Phase 6

---

### 2.2 VisualDirector (`mesmerglass/mesmerloom/visual_director.py`)

**Purpose:** Orchestrate visual playback execution with ThemeBank integration

**Key Methods:**
- `load_playback(playback_path: Path)` → bool: Load playback JSON file
- `update(dt: float)` → None: Advance visual state
- `pause()` / `resume()` / `toggle_pause()`
- `get_cycle_count()` → int: Get total media cycles completed
- `register_cycle_callback(callback)` → None: Register cycle boundary callback
- `is_complete()` → bool: Check if current visual finished

**Integration:**
- Created by Launcher on init
- Wired to `LoomCompositor` for rendering
- Wired to `ThemeBank` for media/text lookup
- Used by `SessionRunner` to load playbacks and track cycles

**Note:** Built-in visual programs removed in Phase 3 - all visuals now loaded from JSON via `CustomVisual`.

---

### 2.3 CustomVisual (`mesmerglass/mesmerloom/custom_visual.py`)

**Purpose:** Load and apply user-defined playback configurations

**Key Methods:**
- `__init__(playback_path, theme_bank, compositor, text_director, ...)`
- `_load_playback_file()` → None: Read JSON file
- `_apply_spiral_settings()` → None: Configure spiral
- `_apply_media_settings()` → None: Configure media cycling
- `_apply_text_settings()` → None: Configure text system
- `reload_from_disk()` → bool: Live reload JSON file

**Integration:**
- Instantiated by `VisualDirector.load_playback()`
- Reads playback JSON files
- Applies settings to `LoomCompositor`, `SpiralDirector`, `TextDirector`

---

### 2.4 AudioEngine (`mesmerglass/engine/audio.py`)

**Purpose:** Multi-channel audio playback with fade in/out

**Key Methods:**
- `__init__(num_channels: int = 2)`: Initialize audio system
- `load_channel(channel: int, file_path: str)` → bool: Load audio file
- `fade_in_and_play(channel, fade_ms, volume, loop)` → bool: Play with fade
- `fade_out_and_stop(channel, fade_ms)` → bool: Stop with fade
- `is_playing(channel)` → bool: Check playback state
- `cleanup()` → None: Release resources

**Supported Formats:** MP3, WAV, OGG

**Integration:**
- Created by Launcher on init (`self.audio = Audio2()`)
- Passed to `SessionRunner` for cue audio playback
- Also used by Launcher's AudioPage for manual audio control

**Note:** `Audio2` is the legacy dual-track system. `AudioEngine` is the new multi-channel system for SessionRunner.

---

### 2.5 LoomCompositor (`mesmerglass/mesmerloom/compositor.py`, `window_compositor.py`)

**Purpose:** OpenGL rendering of spiral + media + text

**Key Methods:**
- `set_background_texture(texture_id, zoom, width, height)`: Set media texture
- `start_zoom_animation(start_zoom, duration_frames, mode)`: Start zoom
- `set_active(active: bool)`: Enable/disable rendering
- `set_intensity(intensity: float)`: Set spiral intensity
- `update()`: Render next frame

**Integration:**
- Created by Launcher on init
- Wired to `VisualDirector`, `SessionRunner`
- Renders to OpenGL window or offscreen FBO (for VR)

---

### 2.6 Display Management (Launcher)

**Purpose:** Select output displays (monitors and VR devices)

**Location:** `mesmerglass/ui/launcher.py` → `_page_displays()`

**UI Structure:**
```
┌─────────────────────────────────────┐
│ <b>Monitors</b>                     │
│ [ ] 🖥️ Display1  1920x1080         │
│ [✓] 🖥️ Display2  1920x1080         │
│ ─────────────────────────────────── │
│ <b>VR Devices (Wireless)</b>        │
│ [✓] 🥽 Oculus Go (192.168.1.105)   │
│ [ ] 🥽 Quest 2 (192.168.1.106)     │
│ [Refresh VR Devices]                │
└─────────────────────────────────────┘
```

**Implementation:**
- `QListWidget` with checkable items
- Monitor items: `data={"type": "monitor", "screen": QScreen}`
- VR items: `data={"type": "vr", "client": {...}}`
- No "settings" - just selection of where to output

**VR Discovery:**
- UDP broadcast on port 5556
- VR devices send "VR_HEADSET_HELLO:<device_name>"
- Server responds with "VR_SERVER_INFO:5555"
- Auto-refresh every 2 seconds

**Launch Behavior:**
- User checks monitors and/or VR devices
- Clicks "Launch" button
- Launcher creates overlays for selected monitors
- Starts VR streaming if VR devices selected
- If only VR selected (no monitors), creates minimized compositor

**Note:** There are NO display "settings" like resolution, refresh rate, or aspect ratio configuration. The system uses native display properties automatically.

---

## 3. Current Launcher UI Structure

### 3.1 Main Window (`mesmerglass/ui/launcher.py`)

**Architecture:** QTabWidget with side tabs

**Tabs:**
1. **Display** - Select monitors/VR devices, Launch/Stop button
2. **Audio** - Load audio files (Track 1, Track 2), volume sliders
3. **Device** - Buttplug.io device control, intensity slider
4. **MesmerLoom** - Load playback JSON files, spiral controls (intensity, colors, type, width)
5. **Text** - Text message library (add/edit/remove messages)
6. **Session Runner** - Load cuelist, start/pause/stop, real-time progress
7. **Performance** - FPS stats, memory usage, frame timing
8. **DevTools** - Debug tools (separate window)

**Key Components:**
- `self.audio`: `Audio2` instance (dual-track audio)
- `self.compositor`: `LoomCompositor` instance
- `self.visual_director`: `VisualDirector` instance
- `self.spiral_director`: `SpiralDirector` instance
- `self.theme_bank`: `ThemeBank` instance (media/text management)
- `self.overlays`: list of `OverlayWindow` instances (fullscreen overlays per monitor)
- `self.vr_bridge`: `VrBridge` instance (OpenVR/OpenXR integration)

---

### 3.2 SessionRunnerTab (`mesmerglass/ui/session_runner_tab.py`)

**Purpose:** Load and execute cuelist sessions (Phase 6)

**UI Sections:**
1. **Header:** Load/Save cuelist buttons
2. **Info:** Cuelist name, description, duration, loop mode
3. **Timeline:** Visual progress bar, cycle count, elapsed time
4. **Controls:** Start/Pause/Stop/Skip buttons
5. **Cue List:** Table of cues with name, duration, playbacks, audio

**Key Features:**
- Real-time progress updates (20 Hz)
- Highlight current cue in list
- Start/Pause/Stop/Skip controls
- Event-driven UI updates via `SessionEventEmitter`

**Integration:**
- Creates `SessionRunner` instance on start
- Passes `visual_director`, `audio_engine`, `compositor` to SessionRunner
- Registers event callbacks for UI updates

---

### 3.3 MesmerLoom Panel (`mesmerglass/ui/panel_mesmerloom.py`)

**Purpose:** Load playback JSON files and control spiral

**UI Sections:**
1. **Current Playback:** Display name, reload button
2. **Recent Playbacks:** List of last 10 loaded playbacks
3. **Browse Playback:** File dialog to load .json playback
4. **Spiral Controls:** Intensity, arms, type, width sliders
5. **Spiral Colors:** Arm color, gap color pickers
6. **Media Bank:** List of media directories with checkboxes

**Key Features:**
- Live reload playback from disk
- Recent playbacks list (last 10)
- Spiral intensity linked to global control
- Media Bank integration (select which directories to use)

**Integration:**
- Loads playback via `parent.visual_director.load_playback(path)`
- Updates spiral via `self.director.set_intensity(...)`, etc.
- Reads/writes `media_bank.json`

---

## 4. Key Integration Points for Phase 7

### 4.1 Home Tab Integration

**Session Controls:**
- Wire to existing `SessionRunner` (Phase 6)
- Use `SessionRunnerTab` logic for Start/Pause/Stop/Skip
- Real-time progress updates via `SessionEventEmitter`

**Visual Preview:**
- Embed `LoomCompositor` widget (existing compositor view)
- Already implemented in Phase 6 SessionRunnerTab

**Cuelist Contents:**
- Display cues from loaded `Cuelist` object
- Show name, duration from `Cue` objects

**Media Bank:**
- Read/write `media_bank.json` (project root)
- Use existing MediaBank logic from Launcher

---

### 4.2 Cuelists Tab Integration

**Data Source:**
- Scan filesystem for `*.cuelist.json` files
- Use `Cuelist.load(path)` to read metadata
- Parse JSON directly for fast preview (avoid full validation)

**Table Columns:**
- Name: `cuelist.name`
- Duration: `cuelist.total_duration()` (sum of cue durations)
- # Cues: `len(cuelist.cues)`
- Modified: File modification timestamp

**Actions:**
- **Run:** Load into SessionRunner (same as Home tab)
- **Duplicate:** Copy .cuelist.json file with new name
- **Export:** Copy .cuelist.json to user-selected location

---

### 4.3 Cues Tab Integration

**Data Source:**
- Load all .cuelist.json files
- Extract cues from each cuelist
- Flatten into single list for browsing

**Table Columns:**
- Name: `cue.name`
- # Playbacks: `len(cue.playback_pool)`
- # Audio: `len(cue.audio_tracks)`
- Modified: Cuelist file modification timestamp

**Display Details (in editor, not details panel):**
- Playback pool: `cue.playback_pool` (array of PlaybackEntry)
- Audio tracks: `cue.audio_tracks` (array of AudioTrack)
- Selection mode: `cue.selection_mode`

---

### 4.4 Playbacks Tab Integration

**Data Source:**
- Scan `mesmerglass/playbacks/` for `*.json` files
- Use `CustomVisual.validate_mode_file(path)` for validation
- Parse JSON directly for metadata

**Grid Display:**
- Preview thumbnails: Generate or use placeholder icons
- Name: `playback["name"]` from JSON

**Details Display:**
- Spiral: `playback["spiral"]` dict (type, rotation_speed, opacity, reverse)
- Media: `playback["media"]` dict (mode, cycle_speed, fade_duration)
- Text: `playback["text"]` dict (enabled, mode, opacity)
- Zoom: `playback["zoom"]` dict (mode, rate)

---

### 4.5 Display Tab Integration

**Monitor Selection:**
- Use `QGuiApplication.screens()` to enumerate monitors
- Display name, resolution from `QScreen` object
- No "settings" to configure - just select which monitors to use

**VR Device Selection:**
- Use existing VR discovery service
- Display discovered VR clients from UDP broadcast
- Auto-refresh every 2 seconds

**Implementation:**
- Reuse existing `Launcher._page_displays()` logic
- `QListWidget` with checkable items
- Data attached to each item: `{"type": "monitor", "screen": QScreen}` or `{"type": "vr", "client": {...}}`

**Note:** NO display settings panel - just selection of outputs.

---

### 4.6 File Menu & Session Management

**New Session:**
- Reset all state (clear cuelist, stop playback)
- Clear SessionRunner

**Open Session (NEW feature):**
- Load `.session.json` file containing:
  ```json
  {
    "cuelist_path": "cuelists/my_session.cuelist.json",
    "display_selection": ["Display1", "VR:192.168.1.105"],
    "media_bank_paths": [...],
    "spiral_settings": {...}
  }
  ```
- Restore cuelist, display selection, media bank

**Save Session (NEW feature):**
- Serialize current state to `.session.json`
- Save cuelist path, display selection, media bank paths

**Import/Export Cuelist:**
- Import: Copy .cuelist.json file into project
- Export: Copy .cuelist.json file to user location

---

## 5. Migration Strategy

### 5.1 Phase 6 → Phase 7 Transition

**Preserve Existing Systems:**
- ✅ SessionRunner (Phase 6) - wire into Home tab
- ✅ VisualDirector - use for loading playbacks
- ✅ AudioEngine - use for cue audio playback
- ✅ LoomCompositor - embed in Home tab visual preview
- ✅ Display selection - reuse Launcher._page_displays() logic
- ✅ MediaBank - use shared `media_bank.json`

**Replace UI Components:**
- ❌ Launcher tabs → Vertical tab sidebar
- ❌ SessionRunnerTab as separate tab → Home tab section
- ❌ MesmerLoom panel → Playbacks tab + Playback Editor
- ❌ Displays page → Display tab (simplified)
- ❌ Audio page → Removed (audio managed by cues)
- ❌ Text page → Removed (text managed by playbacks)

**New UI Components:**
- 🆕 Main application window with vertical tabs
- 🆕 Home tab (session controls + preview + cuelist + media bank)
- 🆕 Cuelists tab (browse .cuelist.json files)
- 🆕 Cues tab (browse cues from all cuelists)
- 🆕 Playbacks tab (browse .json playback files)
- 🆕 Cuelist Editor window (edit .cuelist.json)
- 🆕 Cue Editor window (edit cue properties)
- 🆕 Playback Editor window (edit .json playback files)

---

### 5.2 File Menu Implementation

**New Session:**
```python
def new_session():
    # Stop current session
    if self.session_runner and self.session_runner.is_running():
        self.session_runner.stop()
    
    # Clear state
    self.current_cuelist = None
    self.current_session_path = None
    
    # Reset UI
    self.home_tab.clear_cuelist()
    self.session_runner = None
```

**Open Session:**
```python
def open_session():
    path = QFileDialog.getOpenFileName(..., "Session Files (*.session.json)")
    if path:
        session_data = json.load(open(path))
        
        # Load cuelist
        cuelist_path = Path(session_data["cuelist_path"])
        self.current_cuelist = Cuelist.load(cuelist_path)
        
        # Restore display selection
        self.display_tab.set_selection(session_data["display_selection"])
        
        # Restore media bank
        media_bank = json.load(open("media_bank.json"))
        # ... update media bank ...
        
        # Update UI
        self.home_tab.load_cuelist(self.current_cuelist)
```

**Save Session:**
```python
def save_session():
    path = QFileDialog.getSaveFileName(..., "Session Files (*.session.json)")
    if path:
        session_data = {
            "cuelist_path": str(self.current_cuelist_path),
            "display_selection": self.display_tab.get_selection(),
            "media_bank_paths": json.load(open("media_bank.json")),
            "spiral_settings": {
                "intensity": self.compositor.get_intensity(),
                # ...
            }
        }
        json.dump(session_data, open(path, 'w'), indent=2)
```

---

## 6. Critical Corrections for Wireframes

### 6.1 Remove Details Panels

**REMOVE from all tabs:**
- ❌ Cuelists Tab → Details panel (cuelist metadata shown in table)
- ❌ Cues Tab → Details panel (cue details shown in Cue Editor)
- ❌ Playbacks Tab → Details panel (playback details shown in Playback Editor)

**Reason:** User requested editor windows for editing, not read-only details panels.

---

### 6.2 Fix File Extensions

**CHANGE throughout wireframes:**
- ❌ `.vmode` files → ✅ `.json` files
- ❌ "deep_spiral.vmode" → ✅ "deep_spiral.json"
- ❌ "Playback Name (vmode)" → ✅ "Playback Name (json)"

**Correct locations:**
- ✅ `mesmerglass/playbacks/*.json`
- ✅ `cuelists/*.cuelist.json`

---

### 6.3 Remove Display Settings

**REMOVE from Display Tab:**
- ❌ "Display Settings" section with resolution, fullscreen, FPS dropdowns
- ❌ Checkboxes for "Fullscreen Mode", "Always on Top", "Show FPS Counter"
- ❌ "Target FPS" dropdown

**Reason:** These settings don't exist in the codebase. Display tab only selects outputs (monitors/VR), no configuration.

**KEEP in Display Tab:**
- ✅ Monitor list with checkboxes
- ✅ VR devices list with checkboxes
- ✅ Refresh button
- ✅ Display info (resolution, refresh rate) - read-only, from QScreen object

---

## 7. Success Criteria

Phase 7 is correctly implemented when:

1. ✅ All playback references use `.json` extension (not `.vmode`)
2. ✅ Cuelists/Cues/Playbacks tabs have NO details panels (only tables)
3. ✅ Display tab has NO settings section (only output selection)
4. ✅ Home tab wires to existing SessionRunner (Phase 6)
5. ✅ VisualDirector loads playbacks via `CustomVisual`
6. ✅ AudioEngine handles cue audio tracks
7. ✅ MediaBank uses shared `media_bank.json`
8. ✅ Display selection reuses Launcher logic (monitors + VR discovery)
9. ✅ All editor windows (Cuelist, Cue, Playback) are popup modals
10. ✅ Session management (New/Open/Save) implemented in File menu

---

**Next Steps:**
1. Update `gui-wireframes-v2.md` with corrections
2. Update `phase-7-gui-redesign-plan-v2.md` with migration strategy
3. Begin Phase 7.1 implementation (Main Window Framework)
