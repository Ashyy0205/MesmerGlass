# Cuelist Loading Progress

MesmerGlass now surfaces a modal progress dialog whenever a cuelist with audio tracks is loaded. The dialog keeps the UI responsive while the AudioEngine warms its cache and makes it clear that the application is still working.

## When It Appears

- Loading a cuelist from the Home tab or Session Runner tab that references one or more audio tracks.
- Only when at least one audio file is found; purely visual cuelists still load instantly without a dialog.

## Behavior

1. The dialog lists the number of audio files that must be decoded.
2. Each track update refreshes the message (`Prefetched 2/5: leadin.mp3`) and advances the progress bar.
3. Failures are counted and displayed at the end so operators know to inspect logs.
4. The dialog blocks destructive actions (close button removed) to prevent partially prepared sessions.
5. Qt events are pumped between tracks so the window repaints and remains draggable even during large batches.

## Technical Details

- `SessionRunnerTab` gathers audio paths and invokes `prefetch_audio_for_cuelist` with a progress callback.
- `prefetch_audio_for_cuelist` now supports incremental callbacks and falls back to sequential `AudioEngine.preload_sound` calls when a callback is provided.
- `CuelistLoadingDialog` lives in `mesmerglass/ui/dialogs/` and exposes `update_progress` and `mark_complete` helpers for deterministic testing.

## Manual QA

1. Launch the GUI and open **Session Runner**.
2. Load a cuelist that contains several audio tracks.
3. Verify that a dialog titled “Preparing Audio Tracks” appears and advances without freezing the window.
4. Disconnect audio files or corrupt one path to confirm the warning message is shown at completion.

## Related Files

- `mesmerglass/ui/session_runner_tab.py`
- `mesmerglass/ui/dialogs/cuelist_loading_dialog.py`
- `mesmerglass/session/audio_prefetch.py`
- `mesmerglass/tests/test_cuelist_loading_dialog.py`
