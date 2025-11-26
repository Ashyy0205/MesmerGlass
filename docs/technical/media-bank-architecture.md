# Media Bank Architecture

## Overview

MesmerGlass uses a **two-tier media system**:

1. **Media Bank (Launcher - Global)** - Defines ALL available media directories
2. **Mode Selection (VMC - Per-Mode)** - Each mode selects which Media Bank paths to use

This allows:
- One-time configuration of all media locations
- Per-mode selection of which media to use
- Easy sharing of modes (paths reference bank indices, not absolute paths)

---

## Architecture

### Tier 1: Media Bank (Launcher)

**Location:** Launcher GUI → MesmerLoom tab → Media Bank section

**Storage:** Global launcher setting (persistent across sessions)

**Structure:**
```python
media_bank = [
    {"name": "Default Images", "path": "C:/MesmerGlass/MEDIA/Images", "type": "images"},
    {"name": "Default Videos", "path": "C:/MesmerGlass/MEDIA/Videos", "type": "videos"},
    {"name": "Custom Collection 1", "path": "U:/Diaper Boi Haven/Images", "type": "images"},
    {"name": "Custom Collection 2", "path": "D:/Videos/Hypno", "type": "videos"}
]
```

**UI Features:**
- Add new directory (Browse button)
- Remove directory
- Rename directory (for easy identification)
- Type selection (images/videos/both)
- List view with checkboxes for quick enable/disable

---

### Tier 2: Mode Selection (VMC)

**Location:** Visual Mode Creator → Media tab → Bank Selection

**Storage:** Per-mode JSON file

**Structure:**
```json
{
  "media": {
    "mode": "images",
    "cycle_speed": 50,
    "opacity": 1.0,
    "fade_duration": 0.5,
    "bank_selections": [0, 2]  // Indices into media_bank array
  }
}
```

**UI Features:**
- Checkboxes for each Media Bank entry
- Only shows bank entries matching media mode (images/videos/both)
- Preview: shows total count of selected media
- Default: uses indices 0,1 (default MEDIA folders)

---

## Data Flow

### Mode Creation (VMC):
1. User opens VMC
2. VMC reads launcher's `media_bank` array
3. User selects which bank entries to use (checkboxes)
4. VMC saves selected indices in `media.bank_selections` field
5. VMC previews media using selected banks

### Mode Loading (Launcher):
1. User loads mode JSON
2. Launcher reads `media.bank_selections` array
3. Launcher resolves indices to actual paths via `media_bank[index]`
4. ThemeBank is rebuilt with ONLY selected paths
5. VisualDirector plays media from filtered ThemeBank

---

## Benefits

### 1. **Portability**
Modes reference bank indices, not absolute paths:
- Share mode JSONs easily
- Recipients configure their own Media Bank
- Mode uses recipient's paths at same indices

### 2. **Flexibility**
Change media locations without editing modes:
- Update Media Bank paths in launcher
- All modes using those indices automatically updated

### 3. **Organization**
Name collections for easy identification:
- "SFW Content", "NSFW Content"
- "Quick Loops", "Long Sessions"
- "Text-Safe", "Image-Only"

### 4. **Performance**
Only load media from selected banks:
- No scanning unused directories
- Faster mode switching
- Lower memory usage

---

## Implementation Details

### Launcher Changes

**New Attributes:**
```python
self._media_bank: List[Dict[str, Any]] = [
    {"name": "Default Images", "path": str(media_dir / "Images"), "type": "images"},
    {"name": "Default Videos", "path": str(media_dir / "Videos"), "type": "videos"}
]
```

**New UI (MesmerLoom tab):**
- QListWidget showing bank entries
- Add/Remove/Edit buttons
- Save/Load bank configuration

**New Method:**
```python
def _rebuild_media_library_from_selections(self, bank_indices: List[int]) -> None:
    """Rebuild ThemeBank using only selected Media Bank indices."""
    selected_paths = [self._media_bank[i] for i in bank_indices]
    # Build ThemeBank from selected_paths only
```

---

### VMC Changes

**New UI (Media tab):**
- "Select from Media Bank" section
- Checkboxes for each bank entry
- Auto-filter by media mode (images/videos)
- Total count display

**Mode JSON Schema Update:**
```json
{
  "version": "1.1",
  "media": {
    "mode": "images",
    "bank_selections": [0, 2],  // NEW: indices into media_bank
    // ... existing fields
  }
}
```

**Backward Compatibility:**
- If `bank_selections` missing, default to `[0, 1]` (original MEDIA folders)
- Old modes work without modification

---

### CustomVisual Changes

**Load Method:**
```python
def load_mode(self, mode_path: Path):
    data = json.loads(mode_path.read_text())
    
    # Read bank selections (default to [0,1] for old modes)
    bank_selections = data.get("media", {}).get("bank_selections", [0, 1])
    
    # Tell launcher to rebuild ThemeBank with selected banks
    self._rebuild_media_library_from_selections(bank_selections)
```

### ThemeBank Runtime Fallbacks

- `ThemeBank.get_video()` now automatically searches every active theme slot (primary, alternate, queued) for animations.
- If the currently selected theme has no videos, the request transparently falls back to another theme that does, so "video" playbacks never regress to still images when mixed banks are enabled.
- Fallback selections are logged (`[ThemeBank] Video fallback ...`) to aid debugging and can be correlated with the launcher’s bank configuration when curating media.

### Runtime Integration (Phase 7)

- **SimpleVideoStreamer wiring** – MainApplication now instantiates `SimpleVideoStreamer` during engine bring-up and feeds it into `VisualDirector`. ThemeBank video callbacks (`on_change_video`) therefore load real file paths immediately instead of falling back to still imagery when the GUI forgets to initialize a streamer. The window’s `closeEvent` shuts the streamer down so OpenCV/decoder threads do not linger between test runs.
- **VisualDirector diagnostics** – When visuals request a video but the compositor or streamer is missing, the director logs a one-time warning (`[visual] Video requested but ...`) so QA can spot wiring problems in field logs without reproducing under a debugger.
- **SessionRunner duration guard** – Cue transitions still prefer media-cycle boundaries, but we now timestamp every pending transition request. If two seconds pass without a cycle boundary (for example because a ThemeBank video never loaded), SessionRunner logs a warning and forces the transition so cues honor their configured `duration_seconds`. This matches the legacy “15 s cue” expectation and prevents sessions from overrunning indefinitely when the media pipeline stalls.

### Case-insensitive scanning

- The launcher now relies on `mesmerglass.content.media_scan.scan_media_directory()` when loading `media_bank.json`. The helper walks each directory once and compares suffixes using a lowercase set, so files such as `PHOTO.JPG` or `Loop.MP4` are picked up automatically.
- Returned paths are absolute strings to keep ThemeBank rebuilds deterministic even when users mix drive letters or mount points.
- Custom scan lists can still be provided (for example adding `*.tiff`) by passing overrides to `scan_media_directory()`, and tests cover the mixed-case behavior to guard against regressions.

---

### ThemeBank readiness & diagnostics

- `ThemeBank.get_status()` exposes aggregate counts, pending async load depth, and the last decoded image/video paths so SessionRunner and diagnostics can explain exactly why visuals are missing.
- `ThemeBank.ensure_ready()` is invoked by `SessionRunner`, `SessionRunnerTab`, and the `themebank selftest` CLI to block or warn until at least one decoded image or video is available. Logs surface the `ThemeBankStatus` snapshot to aid support tickets.
- CLI tooling (`python -m mesmerglass themebank ...`) calls the same readiness helpers, providing `stats`, `selftest`, and `pull-*` commands for CI and field troubleshooting. Exit code `3` uniformly means “media missing/not ready”.
- `mesmerglass/tests/test_themebank_diagnostics.py` covers status generation, CLI plumbing, and readiness gates so regressions surface before shipping.
- VisualDirector logs the first video/image paths that reach the compositor, letting you correlate ThemeBank readiness with actual uploads when diagnosing “spiral only” reports.

When media paths are misconfigured or inaccessible, ThemeBank remains in a “not ready” state that surfaces through the CLI, SessionRunner UI warnings, and VisualDirector logs. This layered approach prevents silent failures where sessions display only the fallback spiral/text overlays.

---

## Example Workflow

### Setup Phase (One-Time):
1. Open Launcher → MesmerLoom tab
2. Click "Add to Media Bank"
3. Browse to `U:/Diaper Boi Haven/Images`
4. Name it "Personal Collection"
5. Set type to "images"
6. Click "Add to Media Bank" again
7. Browse to `D:/Videos/Hypno`
8. Name it "Hypno Videos"
9. Set type to "videos"

### Mode Creation:
1. Open VMC
2. Set media mode to "images"
3. See checkboxes:
   - ☑ Default Images
   - ☐ Default Videos (grayed - wrong type)
   - ☑ Personal Collection
   - ☐ Hypno Videos (grayed - wrong type)
4. Check "Personal Collection"
5. Preview shows 3348 images
6. Save mode as "personal_mode.json"

### Mode Usage:
1. Load "personal_mode.json"
2. ThemeBank rebuilt with only:
   - MEDIA/Images
   - U:/Diaper Boi Haven/Images
3. Spiral displays images from both directories
4. Videos from Hypno folder NOT loaded (not selected)

---

## Migration Strategy

### Phase 1: Add Media Bank to Launcher
- Add `_media_bank` attribute
- Initialize with default MEDIA folders
- Add UI for managing bank entries

### Phase 2: Update VMC
- Add bank selection UI
- Save `bank_selections` in JSON
- Default to `[0, 1]` if not specified

### Phase 3: Update Mode Loading
- Read `bank_selections` from JSON
- Rebuild ThemeBank from selected banks only
- Maintain backward compatibility

### Phase 4: Documentation
- Update user guide with Media Bank workflow
- Update mode file format documentation
- Add migration notes for existing users

---

## Future Enhancements

- [ ] Import/Export Media Bank configurations
- [ ] Cloud sync for Media Bank (share across machines)
- [ ] Auto-detect media in common locations
- [ ] Media Bank templates (SFW/NSFW presets)
- [ ] Per-bank caching for faster switching
- [ ] Media Bank search/filter
- [ ] Thumbnails for bank preview

---

**Status:** Architecture defined, ready for implementation

**Next Steps:**
1. Implement launcher Media Bank UI
2. Update VMC with bank selection
3. Update CustomVisual mode loading
4. Test end-to-end workflow
