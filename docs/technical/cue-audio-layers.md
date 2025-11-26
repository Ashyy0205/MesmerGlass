# Cue Audio Layers

Dual-track audio is now first-class inside the Cue Editor, the session runner, and the CLI. Each cue can host up to two purpose-driven layers:

- **Hypno Track** – the primary spoken-word / induction audio. Its measured duration is used to suggest the cue length.
- **Background Track** – a looping ambient layer that fills any silence between media transitions and matches the hypno track automatically.

## Editor Behavior

1. **Per-role sections**: The Cue Editor shows two dedicated panels (Hypno + Background). Each panel includes file browse/clear buttons, read-only path display, a normalized volume spinner (0–100%), and an info label that shows filename, cached duration, and whether the layer loops.
2. **Manual file sourcing**: Both panels open the OS file picker directly—there is no theme/library indirection. Tracks are saved exactly as selected paths so sessions remain portable between GUI and CLI.
3. **Legacy hydration**: Existing `audio_tracks` arrays (without explicit roles) still load. The first entry is treated as `hypno`, the second as `background` to keep older cuelists functional.
4. **Selection mode safety**: Loading cue data blocks widget signals, so re-opening an existing cue no longer flags it as dirty until the user edits something.

## Duration Suggestions

- When a hypno track is selected, the editor probes the file (or uses cached `duration`) and displays a "Suggested duration" hint.
- The cue duration spinner automatically snaps to the rounded hypno length unless the user manually overrides it. Manual overrides are clearly labeled.
- Clearing or changing the hypno track resets the suggestion and removes any override flags so new measurements propagate.

## Background Loop Enforcement

- The default background configuration is looped with gentle fade in/out envelopes.
- Users can technically disable looping, but the CLI surfaces a warning and SessionRunner still forces the stream to loop internally so the ambient layer never runs dry mid-cue.
- If a cue configures audio but omits the background role entirely, validation emits a warning so content authors notice the missing layer before going live.

## JSON Schema

Two parallel representations are emitted for backward compatibility:

```json
"audio": {
  "hypno": {
    "file": "audio/hypno.wav",
    "volume": 0.85,
    "loop": false,
    "fade_in_ms": 1200,
    "fade_out_ms": 900,
    "duration": 182.4
  },
  "background": {
    "file": "audio/bg.wav",
    "volume": 0.35,
    "loop": true,
    "fade_in_ms": 600,
    "fade_out_ms": 800
  }
},
"audio_tracks": [
  {"role": "hypno", "file": "audio/hypno.wav", ...},
  {"role": "background", "file": "audio/bg.wav", ...}
]
```

`SessionRunner` always consumes the role-aware form. The legacy array is serialized for tooling that still expects Phase 6 schemas.

## CLI Integration

- `python -m mesmerglass cuelist --validate` reports file-missing **errors** and audio-role **warnings** in JSON (`errors[]` and `warnings[]`). Missing hypno roles fail validation when any audio is configured.
- `--print` now includes a per-cue line showing role coverage so headless logs reveal whether hypno/background are present.
- Tests live in `mesmerglass/tests/test_cli_cuelist.py` and `mesmerglass/tests/test_cue_editor_integration.py` to guard the behavior end-to-end.

## Manual QA Checklist

- Add a hypno track → verify cue duration auto-updates and hint text matches the measured length.
- Clear the hypno track → duration suggestion resets to `--` and manual overrides are cleared.
- Add a background track with loop disabled → save, re-open, confirm it still hydrates and CLI warns about the non-looping state.
- Run `python -m mesmerglass cuelist --validate --json` on a cuelist that includes both tracks to confirm `warnings` is empty; remove the background block to verify the warning text appears.
