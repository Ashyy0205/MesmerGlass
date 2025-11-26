# Session Consolidation Plan - Phase 7.10

**Date**: November 10, 2025  
**Status**: Planning Phase  
**Objective**: Consolidate all cuelists, cues, and playbacks into a single `.session.json` file

---

## Current Architecture (Distributed Files)

### File Structure
```
mesmerglass/
├── playbacks/
│   ├── default.json
│   ├── intense_spiral.json
│   ├── gentle_waves.json
│   └── custom_*.json
├── cuelists/
│   ├── example_short_session.cuelist.json
│   ├── meditation.cuelist.json
│   └── *.cuelist.json
└── sessions/
    └── (currently empty - sessions not implemented yet)
```

### Current JSON Formats

#### Playback JSON (`mesmerglass/playbacks/*.json`)
```json
{
  "version": "1.0",
  "name": "Default Spiral",
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": 40.0,
    "opacity": 0.48,
    "reverse": true
  },
  "media": {
    "mode": "images",
    "cycle_speed": 50,
    "fade_duration": 0.5,
    "use_theme_bank": false,
    "paths": [],
    "bank_selections": [0]
  },
  "text": {
    "enabled": true,
    "mode": "centered_sync",
    "opacity": 0.69,
    "use_theme_bank": true,
    "library": [],
    "sync_with_media": false
  },
  "zoom": {
    "mode": "exponential",
    "rate": 20.0
  }
}
```

#### Cue JSON (embedded in cuelist)
```json
{
  "name": "Opening",
  "duration": 60,
  "playback_pool": ["default", "intense_spiral"],
  "audio": {
    "tracks": [],
    "volume": 1.0
  }
}
```

#### Cuelist JSON (`cuelists/*.cuelist.json`)
```json
{
  "version": "1.0",
  "name": "Example Session",
  "loop_mode": "once",
  "cues": [
    {
      "name": "Opening",
      "duration": 60,
      "playback_pool": ["default"],
      "audio": {"tracks": [], "volume": 1.0}
    }
  ]
}
```

---

## New Architecture (Single Session File)

### File Structure
```
mesmerglass/
└── sessions/
    ├── default.session.json
    ├── meditation.session.json
    ├── intense_training.session.json
    └── *.session.json
```

### New Session JSON Format

```json
{
  "version": "1.0",
  "metadata": {
    "name": "My Training Session",
    "description": "Custom training session with multiple cues",
    "created": "2025-11-10T14:15:00Z",
    "modified": "2025-11-10T14:30:00Z",
    "author": "User",
    "tags": ["training", "spiral", "meditation"]
  },
  
  "playbacks": {
    "default": {
      "name": "Default Spiral",
      "spiral": {
        "type": "logarithmic",
        "rotation_speed": 40.0,
        "opacity": 0.48,
        "reverse": true
      },
      "media": {
        "mode": "images",
        "cycle_speed": 50,
        "fade_duration": 0.5,
        "use_theme_bank": false,
        "paths": [],
        "bank_selections": [0]
      },
      "text": {
        "enabled": true,
        "mode": "centered_sync",
        "opacity": 0.69,
        "use_theme_bank": true,
        "library": [],
        "sync_with_media": false
      },
      "zoom": {
        "mode": "exponential",
        "rate": 20.0
      }
    },
    "intense_spiral": {
      "name": "Intense Training",
      "spiral": { /* ... */ },
      "media": { /* ... */ },
      "text": { /* ... */ },
      "zoom": { /* ... */ }
    }
  },
  
  "cuelists": {
    "main": {
      "name": "Main Session",
      "loop_mode": "once",
      "cues": [
        {
          "name": "Opening",
          "duration": 60,
          "playback_pool": ["default"],
          "audio": {
            "tracks": [],
            "volume": 1.0
          }
        },
        {
          "name": "Deepener",
          "duration": 300,
          "playback_pool": ["default", "intense_spiral"],
          "audio": {
            "tracks": ["deepener.mp3"],
            "volume": 0.8
          }
        }
      ]
    },
    "alternate": {
      "name": "Quick Session",
      "loop_mode": "loop",
      "cues": [ /* ... */ ]
    }
  },
  
  "runtime": {
    "active_cuelist": "main",
    "active_cue_index": 0,
    "last_playback": "default",
    "session_time_elapsed": 0
  }
}
```

---

## Migration Strategy

### Phase 1: Session File Format Implementation

**File**: `mesmerglass/session_manager.py`

```python
class SessionManager:
    """Manages session save/load operations."""
    
    def __init__(self):
        self.session_dir = Path("mesmerglass/sessions")
        self.session_dir.mkdir(exist_ok=True)
        self.current_session = None
        self.current_file = None
        self.dirty = False
    
    def new_session(self, name: str) -> dict:
        """Create new empty session."""
        return {
            "version": "1.0",
            "metadata": {
                "name": name,
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
            },
            "display": self._default_display_config(),
            "playbacks": {},
            "cuelists": {},
            "runtime": {
                "active_cuelist": None,
                "active_cue_index": 0,
                "last_playback": None,
                "session_time_elapsed": 0
            }
        }
    
    def save_session(self, filepath: Path, session_data: dict):
        """Save session to file."""
        session_data["metadata"]["modified"] = datetime.now().isoformat()
        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2)
        self.dirty = False
    
    def load_session(self, filepath: Path) -> dict:
        """Load session from file."""
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def mark_dirty(self):
        """Mark session as having unsaved changes."""
        self.dirty = True
```

### Phase 2: Tab Refactoring (Data Source Changes)

#### 2.1 Playbacks Tab
**Before**: Scans `mesmerglass/playbacks/*.json`  
**After**: Reads `session_data["playbacks"]` dictionary

**Changes**:
- Remove `_load_playbacks()` file scanning
- Add `set_session_data(session_data)` method
- Populate table from `session_data["playbacks"].items()`
- Add/Edit/Delete operations update session dict, not files
- Signal `playback_changed` → marks session dirty

#### 2.2 Cuelists Tab
**Before**: Scans `cuelists/*.cuelist.json`  
**After**: Reads `session_data["cuelists"]` dictionary

**Changes**:
- Remove file scanning
- Add `set_session_data(session_data)` method
- Populate from `session_data["cuelists"].items()`
- New/Edit/Delete updates session dict
- Signal `cuelist_changed` → marks session dirty

#### 2.3 Cues Tab
**Before**: Extracts cues from all cuelist files  
**After**: Flattens all cues from `session_data["cuelists"]`

**Changes**:
- Remove file reading loop
- Iterate `session_data["cuelists"].values()` → extract cues
- Add "Source Cuelist" column (cuelist key)
- Edit operations find parent cuelist and update

#### 2.4 Display Tab
**Before**: Settings only affect runtime  
**After**: Reads/writes `session_data["display"]`

**Changes**:
- Pre-populate from `session_data["display"]`
- On change → update session dict
- Signal `display_changed` → marks session dirty

#### 2.5 Home Tab
**Before**: Quick actions trigger session runner  
**After**: Must have active session loaded

**Changes**:
- Add "Load Session" / "New Session" required state
- Show current session name
- "Start Session" button launches SessionRunner with current session
- Runtime state updates `session_data["runtime"]`

### Phase 3: Editor Refactoring

#### 3.1 PlaybackEditor
**Changes**:
- Constructor takes `session_data` and `playback_key`
- On save → updates `session_data["playbacks"][playback_key]`
- Emits `saved(playback_key, playback_data)` signal
- Parent tab catches signal and marks session dirty

#### 3.2 CuelistEditor
**Changes**:
- Constructor takes `session_data` and `cuelist_key`
- On save → updates `session_data["cuelists"][cuelist_key]`
- Emits `saved(cuelist_key, cuelist_data)` signal

#### 3.3 CueEditor
**Changes**:
- Constructor takes `session_data`, `cuelist_key`, `cue_index`
- On save → updates `session_data["cuelists"][cuelist_key]["cues"][cue_index]`
- Emits `saved(cuelist_key, cue_index, cue_data)` signal

### Phase 4: MainApplication Integration

**File**: `mesmerglass/ui/main_application.py`

**Changes**:
```python
class MainApplication(QMainWindow):
    def __init__(self):
        # ...existing init...
        self.session_manager = SessionManager()
        self.session_data = None
        self._setup_session_actions()
    
    def _setup_session_actions(self):
        """Add File menu actions."""
        file_menu = self.menuBar().addMenu("&File")
        
        file_menu.addAction("&New Session", self._new_session)
        file_menu.addAction("&Open Session...", self._open_session)
        file_menu.addAction("&Save Session", self._save_session)
        file_menu.addAction("Save Session &As...", self._save_session_as)
        file_menu.addSeparator()
        file_menu.addAction("&Import Legacy Files...", self._import_legacy)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)
    
    def _new_session(self):
        """Create new session."""
        if self.session_manager.dirty:
            # Prompt to save (Task 7.12)
            pass
        
        name, ok = QInputDialog.getText(self, "New Session", "Session Name:")
        if ok and name:
            self.session_data = self.session_manager.new_session(name)
            self.session_manager.current_file = None
            self._propagate_session_to_tabs()
            self.statusBar().showMessage(f"New session: {name}")
    
    def _open_session(self):
        """Open existing session."""
        if self.session_manager.dirty:
            # Prompt to save (Task 7.12)
            pass
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "Open Session",
            str(self.session_manager.session_dir),
            "Session Files (*.session.json)"
        )
        
        if filepath:
            self.session_data = self.session_manager.load_session(Path(filepath))
            self.session_manager.current_file = Path(filepath)
            self._propagate_session_to_tabs()
            name = self.session_data["metadata"]["name"]
            self.statusBar().showMessage(f"Loaded: {name}")
    
    def _save_session(self):
        """Save current session."""
        if not self.session_data:
            return
        
        if not self.session_manager.current_file:
            self._save_session_as()
        else:
            self.session_manager.save_session(
                self.session_manager.current_file,
                self.session_data
            )
            self.statusBar().showMessage("Session saved")
    
    def _save_session_as(self):
        """Save session with new filename."""
        if not self.session_data:
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session As",
            str(self.session_manager.session_dir),
            "Session Files (*.session.json)"
        )
        
        if filepath:
            self.session_manager.current_file = Path(filepath)
            self.session_manager.save_session(Path(filepath), self.session_data)
            self.statusBar().showMessage(f"Saved: {filepath}")
    
    def _propagate_session_to_tabs(self):
        """Send session data to all tabs."""
        # Each tab gets reference to session_data dict
        # Tabs modify dict in-place, then mark dirty
        
        self.home_tab.set_session_data(self.session_data)
        self.playbacks_tab.set_session_data(self.session_data)
        self.cuelists_tab.set_session_data(self.session_data)
        self.cues_tab.set_session_data(self.session_data)
        self.display_tab.set_session_data(self.session_data)
        
        # Connect dirty signals
        self.playbacks_tab.data_changed.connect(self.session_manager.mark_dirty)
        self.cuelists_tab.data_changed.connect(self.session_manager.mark_dirty)
        # ... etc for all tabs
```

---

## Migration Path for Existing Data

### Legacy Import Tool

**File**: `scripts/import_legacy_to_session.py`

```python
"""Import legacy playback/cuelist files into session format."""

def import_legacy_files():
    """Scan old directories and create session."""
    session = {
        "version": "1.0",
        "metadata": {
            "name": "Imported Legacy Session",
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
        },
        "display": default_display_config(),
        "playbacks": {},
        "cuelists": {},
        "runtime": {}
    }
    
    # Import playbacks
    playback_dir = Path("mesmerglass/playbacks")
    for pb_file in playback_dir.glob("*.json"):
        with open(pb_file) as f:
            data = json.load(f)
        key = pb_file.stem  # filename without extension
        session["playbacks"][key] = data
    
    # Import cuelists
    cuelist_dir = Path("cuelists")
    for cl_file in cuelist_dir.glob("*.cuelist.json"):
        with open(cl_file) as f:
            data = json.load(f)
        key = cl_file.stem.replace(".cuelist", "")
        session["cuelists"][key] = data
    
    # Save as new session
    output = Path("mesmerglass/sessions/imported.session.json")
    with open(output, 'w') as f:
        json.dump(session, f, indent=2)
    
    print(f"Imported {len(session['playbacks'])} playbacks")
    print(f"Imported {len(session['cuelists'])} cuelists")
    print(f"Saved to: {output}")
```

**Usage**:
```powershell
.\.venv\Scripts\python.exe scripts/import_legacy_to_session.py
```

---

## Implementation Order

### Task 7.10 Breakdown:

1. **7.10.1**: Create `session_manager.py` with SessionManager class
2. **7.10.2**: Define session JSON schema and validation
3. **7.10.3**: Create default session templates
4. **7.10.4**: Add File menu actions to MainApplication
5. **7.10.5**: Refactor PlaybacksTab to use session data
6. **7.10.6**: Refactor CuelistsTab to use session data
7. **7.10.7**: Refactor CuesTab to use session data
8. **7.10.8**: Refactor DisplayTab to use session data
9. **7.10.9**: Update HomeTab for session integration
10. **7.10.10**: Update PlaybackEditor for session mode
11. **7.10.11**: Update CuelistEditor for session mode
12. **7.10.12**: Update CueEditor for session mode
13. **7.10.13**: Implement dirty state tracking
14. **7.10.14**: Create legacy import script
15. **7.10.15**: Test session save/load workflow
16. **7.10.16**: Create example sessions

---

## Benefits

1. **Single File**: All session data in one place
2. **Simplified Workflow**: No managing multiple JSON files
3. **Atomic Saves**: All changes saved together
4. **Version Control Friendly**: One file to track
5. **Portability**: Easy to share complete sessions
6. **Backup**: Simple to backup/restore
7. **No File Sync Issues**: Single file = no orphaned data

---

## Backward Compatibility

### During Development:
- Keep legacy file support in read-only mode
- Show import dialog on first launch if legacy files detected
- Offer "Import All" button in File menu

### Post-Migration:
- Archive old directories: `playbacks_legacy/`, `cuelists_legacy/`
- Keep import script available for old files
- Document migration process

---

## Testing Checklist

- [ ] Create new session from scratch
- [ ] Save session to file
- [ ] Load session from file
- [ ] Add playback to session
- [ ] Edit playback in session
- [ ] Delete playback from session
- [ ] Add cuelist to session
- [ ] Edit cuelist in session
- [ ] Delete cuelist from session
- [ ] Edit cue within cuelist
- [ ] Update display settings
- [ ] Verify dirty state tracking
- [ ] Test unsaved changes prompt
- [ ] Import legacy playback files
- [ ] Import legacy cuelist files
- [ ] Verify session validation
- [ ] Test corrupted session recovery
- [ ] Test large session performance (100+ playbacks)

---

## Risk Assessment

### Low Risk:
- New file format (no existing data to break)
- Editors already work with dict data structures
- Import tool provides migration path

### Medium Risk:
- Tab refactoring (many changes needed)
- Signal/slot rewiring for dirty state
- Ensuring all tabs stay synchronized with session dict

### High Risk:
- None - this is greenfield implementation

---

## Timeline Estimate

- **7.10.1-7.10.4**: Session manager + UI actions (2-3 hours)
- **7.10.5-7.10.9**: Tab refactoring (4-5 hours)
- **7.10.10-7.10.12**: Editor updates (2-3 hours)
- **7.10.13-7.10.16**: Testing + import tool (2-3 hours)

**Total**: ~10-14 hours of development

---

## Notes

- Session format is extensible (can add engine state, window positions, etc.)
- Consider adding session "templates" for common use cases
- Could add session "presets" (minimal vs full session structure)
- Future: Session encryption for privacy
- Future: Cloud sync integration
- Future: Session versioning/history (git-like)

---

## Next Steps

After approval of this plan:
1. Start with 7.10.1 (SessionManager implementation)
2. Add File menu integration (7.10.4)
3. Refactor one tab at a time (7.10.5-7.10.9)
4. Update editors (7.10.10-7.10.12)
5. Add dirty tracking and testing (7.10.13-7.10.16)
