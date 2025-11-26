# Playback Pool Duration Enforcement

## Summary
Cues that were authored before the new selection-mode UI kept their pools in the default `on_cue_start` mode even when every playback entry defined `min_duration_s` / `max_duration_s`. After the Phase 7 session runner tightened the `ON_MEDIA_CYCLE` guard, those cues would now select a single playback at cue start and never honor the configured durations, so a 15 s cue with two 5 s entries no longer swapped three times as expected.

## Root Cause
- `_check_playback_switch()` exited unless `cue.selection_mode == ON_MEDIA_CYCLE`, so any cue left at the old default never even evaluated playback timers.
- Legacy editors saved duration constraints without changing the selection mode, so existing content silently regressed once the guard shipped.
- No regression test covered “legacy durations + on_cue_start” to detect the behavioral break.

## Fix
1. Added `_determine_selection_mode()` in `SessionRunner` to compute an **effective** mode per cue. When multiple pool entries include any duration or cycle constraints, the runner automatically promotes the cue to cycle-based switching to preserve backward compatibility.
2. Persist the resolved mode in `_active_selection_mode` plus `_selection_mode_override_active` for diagnostics, and emit a warning so authors know their cue should be updated explicitly.
3. Updated `_check_playback_switch()` to consult the effective mode so the override actually enables timers.
4. Added `TestPlaybackPoolSwitching.test_duration_constraints_enable_cycle_switching` to lock the behavior in place.

## Verification
- **Automated**: `./.venv/bin/python -m pytest mesmerglass/tests/test_session_runner.py -k playback_pool_switching`.
- **Manual**: Create or load a cue with two pool entries, set each to 5 s min/max, keep the selection mode at "On cue start", then run the cuelist—playbacks now rotate roughly every 5 s (still synchronized to media cycle boundaries).
