# Tab Cleanup - November 10, 2025

## Summary
Removed obsolete tabs from MainApplication (Phase 7) that were redundant with better alternatives.

## Tabs Removed

### 1. Cues Tab (`mesmerglass/ui/tabs/cues_tab.py`)
**Reason**: Redundant - all cue functionality is accessible via:
- **CuelistsTab**: Browse/edit cuelists → edit individual cues
- **HomeTab → SessionRunner**: Load and execute cuelists

**What it did**: Showed flat list of all cues from all cuelists in session
**Why redundant**: 
- No unique functionality
- Cuelists tab provides better hierarchical view
- SessionRunner provides execution controls
- CueEditor provides full editing capability

### 2. Audio Tab (placeholder)
**Reason**: Not implemented, no clear use case in Phase 7 session model
**Alternative**: Audio settings are controlled by:
- Playback definitions (in playbacks)
- Cue audio settings (in cue editor)
- Mode-specific audio (in mode files)

### 3. MesmerLoom Tab (placeholder)
**Reason**: Not implemented, no clear use case in Phase 7 session model
**Alternative**: Visual settings are controlled by:
- Playback definitions (visual programs, speeds, colors)
- Display tab (monitor/VR selection)
- Mode-specific visuals (in mode files)

### 4. Text Tab (placeholder)
**Reason**: Not implemented, no clear use case in Phase 7 session model
**Alternative**: Text settings are controlled by:
- Mode-specific text/messages (in mode files)
- Playback definitions (if text effects added)

## Remaining Tabs (Phase 7)

| Tab | Purpose | Status |
|-----|---------|--------|
| 🏠 Home | Session info, SessionRunner, quick actions | ✅ Complete |
| 📝 Cuelists | Browse/edit cuelist files in session | ✅ Complete |
| 🎨 Playbacks | Browse/edit playback definitions | ✅ Complete |
| 🖥️ Display | Monitor/VR selection | ✅ Complete |
| 🔗 Device | Device control (future) | 📋 Placeholder |
| 📊 Performance | Performance monitoring (future) | 📋 Placeholder |
| 🛠️ DevTools | Developer tools (future) | 📋 Placeholder |

## Files Removed
- `mesmerglass/ui/tabs/cues_tab.py` (330 lines)
- Import removed from `mesmerglass/ui/main_application.py`
- Tab creation/signal connections removed from `main_application.py`
- Session data propagation call removed

## Files Not Touched
- `mesmerglass/ui/text_tab.py` - Used by legacy launcher.py (not MainApplication)
- `mesmerglass/ui/launcher.py` - Old UI system (deprecated but still functional)

## Testing Notes
After this cleanup:
1. ✅ Main application should have 7 tabs total (4 functional, 3 placeholders)
2. ✅ No references to CuesTab should remain in main_application.py
3. ✅ Session data should propagate to: Home, Cuelists, Playbacks, Display
4. ✅ All cue editing should work via Cuelists → Edit Cuelist → Edit Cue
5. ✅ CueEditor should still show session playbacks (not file browser)
6. ✅ SessionRunnerTab should still show session cuelists (not file browser)

### 2025-11-24 follow-up
- ✅ `SessionRunnerTab` rebuilt to remove duplicated legacy Phase 6 widget logic. UI now derives controls/log/metrics fully from the Phase 7 automation surface and exposes the same hooks perf-harness depends on. Legacy `_start_session_internal` / `btn_skip_next` paths were deleted.
- ✅ Added pytest-qt coverage (`mesmerglass/tests/test_session_runner_tab.py`) to guard against regressions in cuelist loading and programmatic start flows.

## Architecture Notes
This cleanup follows the "session-first" design principle:
- **Session is source of truth**: All data lives in .session.json
- **Tabs are views/editors**: Each tab edits a specific part of session
- **No redundant views**: Each piece of data has ONE primary editing location
- **Hierarchical access**: Cuelists → Cues → Playback Pool (natural flow)

The flat "Cues" tab violated this by providing a parallel access path that confused the data model and added no unique value.
