# Phase 7: Complete GUI Redesign - Vertical Tab Application

**Status**: 📋 **PLANNED**  
**Target Start**: After Phase 6 completion  
**Estimated Duration**: 6-7 weeks  
**📐 Wireframes**: See `docs/technical/gui-wireframes-v2.md` (corrected - no details panels, .json extensions)  
**🔍 Codebase Analysis**: See `docs/technical/phase-7-codebase-analysis.md` for complete integration details

---

## 🎯 Vision

Transform MesmerGlass into a **vertical-tab application** for managing visual trance sessions **with ALL existing features preserved**:

1. **Vertical tab sidebar** - Home, Cuelists, Cues, Playbacks, Display, Audio, Device, MesmerLoom, Text, Performance, DevTools
2. **Popup editor windows** - Cuelist Editor, Cue Editor, Playback Editor (NO details panels on tabs)
3. **Home tab mission control** - Session execution + live preview + media bank
4. **Complete workflow** - Create .json playbacks → Build cues → Assemble cuelists → Execute sessions
5. **Session management** - Save/load complete session state (.session.json)
6. **ALL existing features** - Wire to Phase 6 SessionRunner, VisualDirector, AudioEngine, MediaBank, Device controls, Spiral controls, Text library, Performance metrics, DevTools

---

## 🔗 Key Integration Points (from Codebase Analysis)

### Existing Systems to Wire
- ✅ **SessionRunner** (`mesmerglass/session/runner.py`) - Phase 6 cuelist execution
- ✅ **VisualDirector** (`mesmerglass/mesmerloom/visual_director.py`) - Loads `.json` playbacks via CustomVisual
- ✅ **AudioEngine** (`mesmerglass/engine/audio.py`) - Multi-channel audio with fade in/out
- ✅ **LoomCompositor** (`mesmerglass/mesmerloom/compositor.py`) - OpenGL rendering
- ✅ **MediaBank** (`media_bank.json`) - Shared media directory configuration
- ✅ **Display Selection** (`Launcher._page_displays()`) - Monitor/VR device selection

### Data Formats (Already Exist)
- ✅ **Playback files**: `mesmerglass/playbacks/*.json` (NOT .vmode)
- ✅ **Cuelist files**: `cuelists/*.cuelist.json`, `examples/*.cuelist.json`
- ✅ **Media Bank**: `media_bank.json` (project root)
- 🆕 **Session files**: `.session.json` (NEW in Phase 7)

---

## 🖼️ Layout Overview

```
┌───────────────────────────────────────────────────────────────┐
│ ☰ File                                     [MesmerGlass]      │
├────────┬──────────────────────────────────────────────────────┤
│  🏠   │                                                      │
│ Home   │                [TAB CONTENT AREA]                    │
│────────│                                                      │
│  📝   │                                                      │
│Cuelists│                                                      │
│────────│                                                      │
│  🎬   │                                                      │
│  Cues  │                                                      │
│────────│                                                      │
│  🎨   │                                                      │
│Playback│                                                      │
│────────│                                                      │
│  🖥️   │                                                      │
│Display │                                                      │
│────────│                                                      │
│  🎵   │                                                      │
│ Audio  │                                                      │
│────────│                                                      │
│  🔗   │                                                      │
│ Device │                                                      │
│────────│                                                      │
│  🌀   │                                                      │
│MesmerLm│                                                      │
│────────│                                                      │
│  📝   │                                                      │
│  Text  │                                                      │
│────────│                                                      │
│  📊   │                                                      │
│  Perf  │                                                      │
│────────│                                                      │
│  🛠️   │                                                      │
│DevTools│                                                      │
├────────┴──────────────────────────────────────────────────────┤
│ Status: Ready | Session: None | Display: Monitor 1           │
└───────────────────────────────────────────────────────────────┘
```

**📐 See `gui-wireframes-v2.md` for detailed mockups of:**
- All 11 tabs (Home, Cuelists, Cues, Playbacks, Display, Audio, Device, MesmerLoom, Text, Performance, DevTools)
- All 3 editor windows (Cuelist Editor, Cue Editor, Playback Editor)
- All dialogs (Playback Selector, Audio File Selector, Device Selector)
- Complete navigation flows
- Existing data formats

---

## 📋 Phase 7 Task Breakdown

### Task 7.1: Main Window Framework (3 days)

#### 7.1.1 Create Main Application Window
- [ ] **New file:** `mesmerglass/ui/main_application.py`
- [ ] Vertical tab bar (80px wide sidebar)
- [ ] File menu (☰) with New/Open/Save session, Import/Export, Exit
- [ ] Status bar (session status, output display)
- [ ] Window minimum size: 1024x768
- [ ] Dark theme

#### 7.1.2 Implement Vertical Tab System
- [ ] QTabWidget configured for vertical tabs
- [ ] Tab icons + labels
- [ ] Tab switching
- [ ] Remember last active tab

#### 7.1.3 Create Base Tab Class
- [ ] **New file:** `mesmerglass/ui/tabs/base_tab.py`
- [ ] Standard interface for all tabs
- [ ] Lifecycle methods (on_show, on_hide, on_update)

---

### Task 7.2: Home Tab (4 days)

#### 7.2.1 Session Controls Panel
- [ ] **New file:** `mesmerglass/ui/tabs/home_tab.py`
- [ ] Cuelist dropdown (scan for .cuelist.json files)
- [ ] Browse button to load cuelist
- [ ] Start/Pause/Stop/Skip buttons
- [ ] Progress bar, status, cycle count
- [ ] **Wire to SessionRunner** (reuse Phase 6 SessionRunnerTab logic):
  ```python
  from mesmerglass.session.runner import SessionRunner
  from mesmerglass.session.cuelist import Cuelist
  
  # Load cuelist
  cuelist = Cuelist.load(path)
  
  # Create SessionRunner (Phase 6 system)
  self.session_runner = SessionRunner(
      cuelist=cuelist,
      visual_director=self.visual_director,  # From parent
      audio_engine=self.audio_engine,        # From parent
      compositor=self.compositor             # From parent
  )
  
  # Start session
  self.session_runner.start()
  ```

#### 7.2.2 Visual Preview Widget
- [ ] Embed existing `LoomCompositor` widget (~400x300)
- [ ] Fullscreen toggle button (show compositor in separate window)
- [ ] Live update during session (compositor already renders continuously)
- [ ] **Integration:** Use `self.compositor` from parent (created by Launcher)

#### 7.2.3 Cuelist Contents Display
- [ ] Show selected cuelist's cues
- [ ] Display: name, duration (from `Cue` objects)
- [ ] Total duration (`cuelist.total_duration()`) and loop mode
- [ ] **Data source:** `cuelist.cues` array

#### 7.2.4 Media Bank Panel
- [ ] List media directories (Images, Videos, Audio)
- [ ] Browse/Remove buttons for each path
- [ ] Add path buttons
- [ ] Rescan button
- [ ] Total counts display
- [ ] **Wire to existing MediaBank**:
  ```python
  import json
  from pathlib import Path
  
  # Load MediaBank config (shared file at project root)
  config_path = Path(__file__).parent.parent.parent / "media_bank.json"
  with open(config_path, 'r') as f:
      media_bank = json.load(f)
  
  # media_bank structure:
  # [
  #   {"name": "Default Images", "path": "C:/...MEDIA/Images", "type": "images"},
  #   {"name": "Ambient Videos", "path": "C:/...MEDIA/Videos", "type": "videos"}
  # ]
  
  # Save MediaBank config
  with open(config_path, 'w') as f:
      json.dump(media_bank, f, indent=2)
  ```

---

### Task 7.3: Cuelists Tab (3 days)

#### 7.3.1 Cuelist List View
- [ ] **New file:** `mesmerglass/ui/tabs/cuelists_tab.py`
- [ ] Table of all .cuelist.json files
- [ ] Columns: Name, Duration, # Cues, Modified, Actions
- [ ] Search box
- [ ] Sort by column
- [ ] Double-click to edit (opens Cuelist Editor window)
- [ ] **Data discovery**:
  ```python
  from pathlib import Path
  from mesmerglass.session.cuelist import Cuelist
  
  # Scan for cuelist files
  cuelist_dir = Path(__file__).parent.parent.parent / "cuelists"
  examples_dir = Path(__file__).parent.parent.parent / "examples"
  
  cuelist_files = []
  cuelist_files.extend(cuelist_dir.glob("*.cuelist.json"))
  cuelist_files.extend(examples_dir.glob("*.cuelist.json"))
  
  # Load metadata (no full validation for speed)
  for path in cuelist_files:
      cuelist = Cuelist.load(path)
      # Display: cuelist.name, cuelist.total_duration(), len(cuelist.cues)
  ```

#### 7.3.2 NO Details Panel
- [ ] **REMOVED** - User requested editors only, no read-only details
- [ ] All viewing/editing happens in Cuelist Editor window

#### 7.3.3 New Cuelist Button
- [ ] "+ New Cuelist" button
- [ ] Opens Cuelist Editor window (blank cuelist)

---

### Task 7.4: Cues Tab (3 days)

#### 7.4.1 Cue List View
- [ ] **New file:** `mesmerglass/ui/tabs/cues_tab.py`
- [ ] Table of all cues from cuelist files
- [ ] Columns: Name, # Playbacks, # Audio, Modified, Actions
- [ ] Search box
- [ ] Double-click to edit (opens Cue Editor window)
- [ ] **Data extraction**:
  ```python
  # Extract cues from all cuelists
  all_cues = []
  for cuelist_path in cuelist_files:
      cuelist = Cuelist.load(cuelist_path)
      for cue in cuelist.cues:
          all_cues.append({
              "name": cue.name,
              "playback_count": len(cue.playback_pool),
              "audio_count": len(cue.audio_tracks),
              "cuelist_path": cuelist_path,
              "cue_object": cue
          })
  ```

#### 7.4.2 NO Details Panel
- [ ] **REMOVED** - User requested editors only
- [ ] All cue viewing/editing happens in Cue Editor window

#### 7.4.3 New Cue Button
- [ ] "+ New Cue" button
- [ ] Opens Cue Editor window (blank cue)

---

### Task 7.5: Playbacks Tab (3 days)

#### 7.5.1 Playback Grid View
- [ ] **New file:** `mesmerglass/ui/tabs/playbacks_tab.py`
- [ ] Grid of .json playback files (NOT .vmode)
- [ ] Preview thumbnails (generate or placeholder)
- [ ] Search box
- [ ] Double-click to edit (opens Playback Editor window)
- [ ] **Data discovery**:
  ```python
  from pathlib import Path
  from mesmerglass.mesmerloom.custom_visual import CustomVisual
  
  # Scan for playback files
  playback_dir = Path(__file__).parent.parent.parent / "mesmerglass" / "playbacks"
  playback_files = list(playback_dir.glob("*.json"))
  
  # Validate each playback
  valid_playbacks = []
  for path in playback_files:
      is_valid, error = CustomVisual.validate_mode_file(path)
      if is_valid:
          # Parse JSON for metadata
          with open(path, 'r') as f:
              config = json.load(f)
          valid_playbacks.append({
              "name": config.get("name", path.stem),
              "path": path,
              "config": config
          })
  ```

#### 7.5.2 NO Details Panel
- [ ] **REMOVED** - User requested editors only
- [ ] All playback viewing/editing happens in Playback Editor window

#### 7.5.3 New Playback Button
- [ ] "+ New Playback" button
- [ ] Opens Playback Editor window (blank playback)

---

### Task 7.6: Display Tab (2 days)

#### 7.6.1 Display Selection List
- [ ] **New file:** `mesmerglass/ui/tabs/display_tab.py`
- [ ] **Reuse existing code** from `Launcher._page_displays()`
- [ ] Integration:
  ```python
  from PySide6.QtGui import QGuiApplication
  from mesmerglass.vr.vr_client import VRClient
  
  # Get physical monitors
  for i, screen in enumerate(QGuiApplication.screens()):
      geometry = screen.geometry()
      # Add to QListWidget with checkbox
      item_text = f"Monitor {i+1}: {screen.name()} ({geometry.width()}x{geometry.height()})"
  
  # Auto-discover VR displays
  vr_client = VRClient()
  if vr_client.is_available():
      vr_item_text = f"VR: {vr_client.get_device_name()}"
  ```
- [ ] Checkboxes for selection
- [ ] Refresh button (re-scan displays)

#### 7.6.2 NO Display Settings
- [ ] **REMOVED** - Display settings do not exist in codebase
- [ ] No fullscreen checkbox, FPS dropdown, etc.
- [ ] Display tab ONLY selects output targets

---

### Task 7.7: Cuelist Editor Window (4 days)

#### 7.7.1 Create Cuelist Editor Window
- [ ] **New file:** `mesmerglass/ui/windows/cuelist_editor.py`
- [ ] Modal QDialog window
- [ ] Properties form: name, description, loop_mode dropdown
- [ ] Cues table: #, Name, Duration, # Playbacks, # Audio, Actions
- [ ] **Save to .cuelist.json**:
  ```python
  from mesmerglass.session.cuelist import Cuelist
  
  # Build cuelist object
  cuelist = Cuelist(
      name=self.name_input.text(),
      description=self.description_input.toPlainText(),
      loop_mode=self.loop_mode_dropdown.currentText(),
      cues=self.cues_list  # List of Cue objects
  )
  
  # Save to file
  cuelist.save(cuelist_path)
  ```

#### 7.7.2 Cue Management
- [ ] "Add Existing Cue" button - select from cues
- [ ] "Create New Cue" button - opens Cue Editor (returns Cue object)
- [ ] Edit button - opens Cue Editor (pass existing Cue)
- [ ] Delete button - remove from cues list
- [ ] Move Up/Down buttons - reorder cues array

#### 7.7.3 Save
- [ ] Save / Cancel / Save & Close buttons
- [ ] Write to `cuelists/<name>.cuelist.json`
- [ ] Validate with `Cuelist.validate()`

---

### Task 7.8: Cue Editor Window (5 days)

#### 7.8.1 Create Cue Editor Window
- [ ] **New file:** `mesmerglass/ui/windows/cue_editor.py`
- [ ] Modal QDialog window
- [ ] Properties form: name, description, duration_ms
- [ ] Playback pool table: playback (.json), weight slider, min/max cycles
- [ ] Audio tracks table: file (.mp3/.wav), volume slider, fade in/out ms
- [ ] **Build Cue object**:
  ```python
  from mesmerglass.session.cue import Cue, PlaybackEntry, AudioTrack
  
  # Build playback pool
  playback_pool = []
  for row in self.playback_table:
      playback_pool.append(PlaybackEntry(
          playback=row.playback_path,  # Path to .json playback
          weight=row.weight_slider.value(),
          min_cycles=row.min_cycles_spinbox.value(),
          max_cycles=row.max_cycles_spinbox.value()
      ))
  
  # Build audio tracks
  audio_tracks = []
  for row in self.audio_table:
      audio_tracks.append(AudioTrack(
          file=row.file_path,  # Path to audio file
          volume=row.volume_slider.value(),
          fade_in_ms=row.fade_in_spinbox.value(),
          fade_out_ms=row.fade_out_spinbox.value()
      ))
  
  # Build cue
  cue = Cue(
      name=self.name_input.text(),
      description=self.description_input.toPlainText(),
      duration_ms=self.duration_spinbox.value(),
      selection_mode=self.selection_mode_dropdown.currentText(),
      interval_ms=self.interval_spinbox.value() if self.selection_mode == "on_timed_interval" else None,
      playback_pool=playback_pool,
      audio_tracks=audio_tracks
  )
  ```

#### 7.8.2 Playback Pool Management
- [ ] "Add Playback" button - opens playback selector dialog (shows .json files)
- [ ] Delete button - remove row
- [ ] Weight sliders (auto-normalize to 100%)
- [ ] Min/Max cycle spinboxes

#### 7.8.3 Audio Track Management
- [ ] "Add Audio Track" button - opens file browser (filter .mp3/.wav)
- [ ] Delete button - remove row
- [ ] Volume sliders (0.0-1.0)
- [ ] Fade in/out spinboxes (milliseconds)

#### 7.8.4 Selection Mode
- [ ] Selection mode dropdown: on_cue_start, on_media_cycle, on_timed_interval
- [ ] Interval spinbox (enabled only if timed mode)

#### 7.8.5 Save
- [ ] Save / Cancel / Save & Close buttons
- [ ] Return Cue object to Cuelist Editor

---

### Task 7.9: Playback Editor Window (4 days)

#### 7.9.1 Create Playback Editor Window
- [ ] **New file:** `mesmerglass/ui/windows/playback_editor.py`
- [ ] Modal QDialog window with split view: Controls | Live Preview
- [ ] Properties form: name (shown in tabs)
- [ ] Live preview area (embedded LoomCompositor)
- [ ] **Save to .json playback**:
  ```python
  # Build playback JSON (matches CustomVisual format)
  playback_config = {
      "version": "1.0",
      "spiral": {
          "type": self.spiral_type_dropdown.currentText(),
          "rotation_speed": self.rotation_speed_slider.value(),  # RPM
          "arm_colors": [color.name() for color in self.arm_colors],
          "gap_colors": [color.name() for color in self.gap_colors]
      },
      "media": {
          "mode": self.media_mode_dropdown.currentText(),  # "none"/"images"/"videos"/"theme_bank"
          "use_theme_bank": self.media_mode == "theme_bank",
          "paths": [str(p) for p in self.media_paths] if self.media_mode in ["images", "videos"] else [],
          "bank_selections": self.bank_selections if self.use_theme_bank else {},
          "fade_duration": self.fade_duration_slider.value()
      },
      "text": {
          "mode": self.text_mode_dropdown.currentText(),  # "none"/"cycle"/"spiral"
          "cycle_frames": self.cycle_frames_spinbox.value(),
          "split": self.split_mode_dropdown.currentText()
      },
      "zoom": {
          "mode": self.zoom_mode_dropdown.currentText(),  # "static"/"pulse"/"breath"
          "rate": self.zoom_rate_slider.value()
      }
  }
  
  # Save to mesmerglass/playbacks/<name>.json
  playback_path = Path("mesmerglass/playbacks") / f"{name}.json"
  with open(playback_path, 'w') as f:
      json.dump(playback_config, f, indent=2)
  ```

#### 7.9.2 Spiral Controls
- [ ] Type dropdown (Standard, Logarithmic, etc. - see existing spiral types)
- [ ] Rotation speed slider (RPM values)
- [ ] Arm colors (3 color pickers)
- [ ] Gap colors (3 color pickers)

#### 7.9.3 Media Controls
- [ ] Mode dropdown: none, images, videos, theme_bank
- [ ] Directory browser (if images/videos mode)
- [ ] Theme bank selector (if theme_bank mode)
- [ ] Fade duration slider

#### 7.9.4 Text Controls
- [ ] Mode dropdown: none, cycle, spiral
- [ ] Cycle frames spinbox
- [ ] Split mode dropdown

#### 7.9.5 Zoom Controls
- [ ] Mode dropdown: static, pulse, breath
- [ ] Rate slider

#### 7.9.6 Live Preview
- [ ] Embed LoomCompositor (reuse self.compositor from parent)
- [ ] Auto-update on control changes
- [ ] Load playback via `VisualDirector.load_playback(temp_path)`

#### 7.9.7 Save
- [ ] Save / Cancel / Save & Close buttons
- [ ] Write to `mesmerglass/playbacks/<name>.json`
- [ ] Validate with `CustomVisual.validate_mode_file()`

---

### Task 7.10: File Menu and Session Management (3 days)

#### 7.10.1 Implement File Menu
- [ ] New Session - resets state
- [ ] Open Session - loads .session.json
- [ ] Save Session - saves current state
- [ ] Save Session As - saves to new file
- [ ] Import Cuelist - imports .cuelist.json
- [ ] Export Cuelist - exports selected cuelist
- [ ] Exit - closes with save prompt
- [ ] **Session format**:
  ```python
  # Session .json format
  session_config = {
      "version": "1.0",
      "cuelist_paths": [str(p) for p in loaded_cuelists],
      "playback_paths": [str(p) for p in loaded_playbacks],
      "selected_displays": [display_id for display_id in selected_displays],
      "active_cuelist": str(active_cuelist_path) if active_cuelist else None
  }
  
  # Save session
  with open(session_path, 'w') as f:
      json.dump(session_config, f, indent=2)
  
  # Load session
  with open(session_path, 'r') as f:
      session_config = json.load(f)
  for cuelist_path in session_config["cuelist_paths"]:
      # Load cuelist into Cuelists tab
  ```

#### 7.10.2 Session Manager
- [ ] **New file:** `mesmerglass/session/session_manager.py`
- [ ] Methods: new(), save(), save_as(), load()
- [ ] Track current session file path
- [ ] Dirty state tracking (prompt on close)

#### 7.10.3 Recent Sessions
- [ ] Track 10 recent sessions
- [ ] Show in File menu
- [ ] Store in `QSettings` or separate config file

---

### Task 7.11: Dialogs (2 days)

#### 7.11.1 Playback Selector Dialog
- [ ] **New file:** `mesmerglass/ui/dialogs/playback_selector.py`
- [ ] List all .json playback files (NOT .vmode)
- [ ] Search box
- [ ] Radio button selection
- [ ] Show preview (optional)
- [ ] Add Selected / Cancel buttons
- [ ] **Data source**:
  ```python
  playback_dir = Path("mesmerglass/playbacks")
  playback_files = list(playback_dir.glob("*.json"))
  ```

#### 7.11.2 Audio File Selector Dialog
- [ ] **New file:** `mesmerglass/ui/dialogs/audio_file_selector.py`
- [ ] File browser for audio files (.mp3/.wav)
- [ ] Shows duration (via audio library)
- [ ] Preview button (optional)
- [ ] Add Selected / Cancel buttons

---

### Task 7.12: Integration and Migration (5 days)

#### 7.12.1 Wire Existing Systems
- [ ] Home tab → SessionRunner (Phase 6 complete, reuse exact API)
- [ ] Home tab → MediaBank (load/save media_bank.json)
- [ ] Display tab → Display management (reuse Launcher._page_displays())
- [ ] Playback Editor → VisualDirector (call load_playback() for preview)
- [ ] All tabs → Existing data formats (.cuelist.json, playback .json)
- [ ] **No API changes** - all systems already work, just wire them up

#### 7.12.2 Data Discovery on Startup
- [ ] Scan for .cuelist.json files:
  ```python
  cuelist_dir = Path("cuelists")
  cuelist_files = list(cuelist_dir.glob("*.cuelist.json"))
  # Populate Cuelists tab
  ```
- [ ] Scan for .json playback files:
  ```python
  playback_dir = Path("mesmerglass/playbacks")
  playback_files = list(playback_dir.glob("*.json"))
  # Populate Playbacks tab
  ```
- [ ] Load media_bank.json:
  ```python
  with open("media_bank.json", 'r') as f:
      media_bank = json.load(f)
  ```

#### 7.12.3 Launch New UI
- [ ] Update `mesmerglass/__main__.py` to launch MainWindow instead of Launcher
- [ ] Test all workflows: load cuelist → start session → edit playback → save session

---

### Task 7.14: Audio Tab (2 days)

#### 7.14.1 Port Existing Audio Page
- [ ] **New file:** `mesmerglass/ui/tabs/audio_tab.py`
- [ ] **Reuse existing code** from `mesmerglass/ui/pages/audio.py`
- [ ] Primary audio: Load button + volume slider (0-100%)
- [ ] Secondary audio: Load button + volume slider (0-100%)
- [ ] **Integration**:
  ```python
  from mesmerglass.engine.audio import AudioEngine
  
  # Load audio files
  self.audio_engine.load_channel(0, audio_path_1, fade_in_duration=2.0)
  self.audio_engine.load_channel(1, audio_path_2, fade_in_duration=2.0)
  
  # Set volumes
  self.audio_engine.fade_in_and_play(0, volume=vol1/100.0, fade_duration=1.0)
  self.audio_engine.set_channel_volume(1, vol2/100.0)
  ```
- [ ] File dialog for .mp3/.wav/.ogg files
- [ ] Display current filename
- [ ] **NO changes needed** - just port existing UI

---

### Task 7.15: Device Tab (3 days)

#### 7.15.1 Port Existing Device Page
- [ ] **New file:** `mesmerglass/ui/tabs/device_tab.py`
- [ ] **Reuse existing code** from `mesmerglass/ui/pages/device.py`
- [ ] Enable Device Sync toggle
- [ ] Scan for Devices button
- [ ] Select Device button (opens DeviceSelectionDialog)
- [ ] Device status label
- [ ] **Integration**:
  ```python
  from mesmerglass.engine.device_manager import DeviceManager
  
  # Scan for devices
  device_list = await self.device_manager.scan_devices(timeout=5.0)
  
  # Show selection dialog
  selected_indices = DeviceSelectionDialog.get_selected(device_list)
  for idx in selected_indices:
      await self.device_manager.select_device(idx)
  ```

#### 7.15.2 Buzz on Flash Controls
- [ ] Enable toggle
- [ ] Intensity slider (0-100%)
- [ ] Wire to existing flash event system

#### 7.15.3 Random Bursts Controls
- [ ] Enable toggle
- [ ] Min gap spinbox (seconds)
- [ ] Max gap spinbox (seconds)
- [ ] Peak intensity slider (0-100%)
- [ ] Max duration spinbox (milliseconds)
- [ ] **NO changes needed** - just port existing UI

---

### Task 7.16: MesmerLoom Tab (3 days)

#### 7.16.1 Port Existing MesmerLoom Panel
- [ ] **New file:** `mesmerglass/ui/tabs/mesmerloom_tab.py`
- [ ] **Reuse existing code** from `mesmerglass/ui/panel_mesmerloom.py`
- [ ] Spiral colors section:
  - Arm color picker button
  - Gap color picker button
- [ ] **Integration**:
  ```python
  from mesmerglass.mesmerloom.spiral_director import SpiralDirector
  
  # Set colors
  self.spiral_director.set_arm_color(r, g, b, a)
  self.spiral_director.set_gap_color(r, g, b, a)
  ```

#### 7.16.2 Media Bank Section
- [ ] Media Bank list widget (shows entries from media_bank.json)
- [ ] Add Directory button
- [ ] Remove Directory button
- [ ] **Integration**:
  ```python
  # Load media bank
  with open("media_bank.json", 'r') as f:
      media_bank = json.load(f)
  
  # Add entry
  media_bank.append({
      "name": "Custom Directory",
      "path": str(directory_path),
      "type": "images"  # or "videos"
  })
  
  # Save media bank
  with open("media_bank.json", 'w') as f:
      json.dump(media_bank, f, indent=2)
  ```

#### 7.16.3 Custom Playback Loading
- [ ] Recent playbacks list
- [ ] Load Custom Playback button
- [ ] **Integration**:
  ```python
  from mesmerglass.mesmerloom.visual_director import VisualDirector
  
  # Load playback
  self.visual_director.load_playback(playback_path)
  ```
- [ ] **NO changes needed** - just port existing UI

---

### Task 7.17: Text Tab (2 days)

#### 7.17.1 Port Existing Text Tab
- [ ] **New file:** `mesmerglass/ui/tabs/text_tab.py`
- [ ] **Reuse existing code** from `mesmerglass/ui/text_tab.py`
- [ ] Message library list widget
- [ ] Add Message button
- [ ] Edit Message button
- [ ] Remove Message button
- [ ] **Integration**:
  ```python
  from mesmerglass.engine.text_director import TextDirector
  
  # Set message library
  self.text_director.set_text_library(messages, default_split_mode=None, user_set=True)
  self.text_director.set_enabled(True)
  ```
- [ ] Info banner explaining that text settings (opacity, timing, mode, positioning, fonts) are controlled by JSON playback files
- [ ] Default message library (Obey, Submit, Good toy, etc.)
- [ ] **NO changes needed** - just port existing UI

---

### Task 7.18: Performance Tab (2 days)

#### 7.18.1 Port Existing Performance Page
- [ ] **New file:** `mesmerglass/ui/tabs/performance_tab.py`
- [ ] **Reuse existing code** from `mesmerglass/ui/pages/performance.py`
- [ ] Frame Stats section:
  - FPS display
  - Average frame time (ms)
  - Max frame time (ms)
  - Stall count
  - Last stall time (ms)
  - Status hint label
- [ ] **Integration**:
  ```python
  from mesmerglass.engine.perf import perf_metrics
  
  # Set thresholds
  perf_metrics.target_fps = 30.0
  perf_metrics.warn_frame_ms = 60.0
  perf_metrics.warn_stall_ms = 120.0
  
  # Get stats
  fps = perf_metrics.current_fps
  avg_ms = perf_metrics.average_frame_ms
  max_ms = perf_metrics.max_frame_ms
  stalls = perf_metrics.stall_count
  ```

#### 7.18.2 Thresholds and Memory Sections
- [ ] Thresholds section (fixed values display)
- [ ] Audio Memory section (Primary/Secondary track usage)
- [ ] Warnings section (lists any warnings)
- [ ] Auto-refresh every 250ms
- [ ] **NO changes needed** - just port existing UI

---

### Task 7.19: DevTools Tab (2 days)

#### 7.19.1 Port Existing DevTools Page
- [ ] **New file:** `mesmerglass/ui/tabs/devtools_tab.py`
- [ ] **Reuse existing code** from `mesmerglass/ui/pages/devtools.py`
- [ ] Virtual Toy controls:
  - Port spinbox (default 12350)
  - Device name input
  - Latency slider (ms)
  - Mapping dropdown (linear, squared, cubed)
  - Gain/Gamma/Offset sliders
  - Start/Stop buttons
  - Progress bar (current intensity)
- [ ] **Integration**:
  ```python
  from mesmerglass.devtools.virtual_toy import VirtualToy
  
  # Create and run virtual toy
  runner = VirtualToyRunner(
      name=device_name,
      port=port,
      latency_ms=latency,
      mapping=mapping,
      gain=gain,
      gamma=gamma,
      offset=offset
  )
  runner.start()
  
  # Poll level for progress bar
  current_level = runner.level
  ```
- [ ] Multiple virtual toys support (tabbed interface within DevTools tab)
- [ ] **NO changes needed** - just port existing UI

---

### Task 7.20: Final Integration and Migration (5 days)

#### 7.20.1 Wire ALL Existing Systems
- [ ] Home tab → SessionRunner (Phase 6)
- [ ] Home tab → MediaBank
- [ ] Cuelists tab → File discovery
- [ ] Cues tab → Data extraction
- [ ] Playbacks tab → File scanning
- [ ] Display tab → Monitor/VR selection
- [ ] Audio tab → AudioEngine
- [ ] Device tab → DeviceManager + Buttplug
- [ ] MesmerLoom tab → SpiralDirector + VisualDirector + MediaBank
- [ ] Text tab → TextDirector
- [ ] Performance tab → perf_metrics
- [ ] DevTools tab → VirtualToyRunner
- [ ] **NO API changes** - all systems already work

#### 7.20.2 Complete Data Discovery
- [ ] Scan for .cuelist.json files on startup
- [ ] Scan for .json playback files on startup
- [ ] Load media_bank.json on startup
- [ ] Load default text messages on startup
- [ ] Initialize all engines (Audio, Device, Visual, Text)

#### 7.20.3 Replace Launcher
- [ ] Update `mesmerglass/__main__.py` to launch MainWindow instead of Launcher
- [ ] Update `mesmerglass/app.py` if needed
- [ ] Deprecate `mesmerglass/ui/launcher.py` (mark as legacy)
- [ ] Test complete application launch

---

### Task 7.21: Comprehensive Testing (5 days)

#### 7.21.1 Test All Tabs
- [ ] Home tab: Load cuelist, start/pause/stop/skip
- [ ] Cuelists tab: Browse, search, double-click to edit
- [ ] Cues tab: Browse, search, double-click to edit
- [ ] Playbacks tab: Browse, search, double-click to edit
- [ ] Display tab: Select monitors, select VR, refresh
- [ ] Audio tab: Load files, adjust volumes, test playback
- [ ] Device tab: Scan devices, select device, test buzz/bursts
- [ ] MesmerLoom tab: Change colors, add media bank entries, load playbacks
- [ ] Text tab: Add/edit/remove messages
- [ ] Performance tab: Verify FPS/stats display
- [ ] DevTools tab: Start/stop virtual toys

#### 7.21.2 Test All Editors
- [ ] Cuelist Editor: Create new, edit existing, save
- [ ] Cue Editor: Build playback pool, add audio tracks, set selection mode, save
- [ ] Playback Editor: Edit spiral, media, text, zoom settings, live preview, save

#### 7.21.3 Test Complete Workflows
- [ ] **Workflow 1**: Create .json playback → Build cue → Build cuelist → Run session
- [ ] **Workflow 2**: Edit existing cuelist → Modify cue → Add playback → Run session
- [ ] **Workflow 3**: Load session → Run → Pause → Skip cue → Stop → Save session
- [ ] **Workflow 4**: Configure devices → Run session with device sync → Test buzz on flash
- [ ] **Workflow 5**: Change spiral colors → Load custom playback → Verify preview
- [ ] **Workflow 6**: Add text messages → Load playback with text → Verify display
- [ ] **Workflow 7**: Monitor performance → Check FPS/stalls → Verify audio memory
- [ ] **Workflow 8**: Start virtual toy → Connect device tab → Verify control

#### 7.21.4 Test Edge Cases
- [ ] Empty cuelists/cues/playbacks lists
- [ ] Invalid JSON files
- [ ] Missing playback files
- [ ] Missing audio files
- [ ] No devices found
- [ ] VR not available
- [ ] Duplicate names
- [ ] Long file paths
- [ ] Special characters in names

---

### Task 7.22: Final Polish and Documentation (3 days)

#### 7.22.1 UI Polish
- [ ] Consistent dark theme styling across ALL tabs
- [ ] Tooltips on ALL controls
- [ ] Keyboard shortcuts (Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Q, Ctrl+Shift+D)
- [ ] Error dialogs for ALL failure cases
- [ ] Loading indicators for async operations
- [ ] Status bar updates for ALL operations
- [ ] Window state persistence (size, position, last tab)

#### 7.22.2 Documentation Updates
- [ ] Update README.md with new UI screenshots
- [ ] Update docs/user-guide/ with complete workflows
- [ ] Update docs/technical/ with architecture changes
- [ ] Create migration guide from old Launcher to new UI
- [ ] Document ALL keyboard shortcuts
- [ ] Document ALL file formats

#### 7.22.3 Cleanup
- [ ] Remove old gui-wireframes.md (superseded by v2)
- [ ] Remove old phase-7-gui-redesign-plan.md (superseded by v2)
- [ ] Mark Launcher as legacy/deprecated
- [ ] Add deprecation warnings if Launcher still accessible

---

## 📅 Updated Implementation Timeline

- **Week 1**: Task 7.1 Main Window + 7.2 Home Tab
- **Week 2**: Task 7.3 Cuelists + 7.4 Cues + 7.5 Playbacks
- **Week 3**: Task 7.6 Display + 7.7 Cuelist Editor + 7.8 Cue Editor (start)
- **Week 4**: Task 7.8 Cue Editor (finish) + 7.9 Playback Editor + 7.10 File Menu
- **Week 5**: Task 7.11 Dialogs + 7.12 Integration + 7.14 Audio + 7.15 Device (start)
- **Week 6**: Task 7.15 Device (finish) + 7.16 MesmerLoom + 7.17 Text + 7.18 Performance
- **Week 7**: Task 7.19 DevTools + 7.20 Final Integration + 7.21 Testing (start)
- **Week 8**: Task 7.21 Testing (finish) + 7.22 Polish + Documentation

---

## ✅ Success Criteria

Phase 7 is complete when:

1. ✅ **ALL 11 tabs functional**: Home, Cuelists, Cues, Playbacks, Display, Audio, Device, MesmerLoom, Text, Performance, DevTools
2. ✅ All 3 editor windows functional (Cuelist, Cue, Playback)
3. ✅ Session management works (New/Open/Save)
4. ✅ Complete workflow: Create .json playback → Build cue → Build cuelist → Execute session
5. ✅ Phase 6 SessionRunner functionality preserved and wired to Home tab
6. ✅ **ALL existing Launcher features working**: Audio loading/volume, Device scanning/selection/sync, Spiral colors/media bank, Text messages, Performance metrics, DevTools virtual toys
7. ✅ No regressions in visual quality or performance
8. ✅ All playback files use .json extension (NOT .vmode)
9. ✅ NO details panels on tabs (editing happens in popup windows)
10. ✅ Display tab only selects outputs (no settings that don't exist)
11. ✅ MediaBank loaded from media_bank.json at project root
12. ✅ All existing systems integrated without API changes
13. ✅ **NOTHING from current Launcher is missing**
14. ✅ All workflows tested and verified working
15. ✅ Complete documentation updated

---

## 🚀 Next Steps

1. **Review wireframes** - See `gui-wireframes-v2.md` for corrected mockups (all details panels removed, .json extensions fixed)
2. **Review codebase analysis** - See `phase-7-codebase-analysis.md` for complete system documentation
3. **Approve design** - Confirm vertical tabs and popup editors approach
4. **Begin Task 7.1** - Start main window framework with vertical tab sidebar

---

**Status**: Planning complete. Wireframes corrected. Codebase analyzed. Integration strategy documented with code examples. Ready to begin implementation after user approval.
