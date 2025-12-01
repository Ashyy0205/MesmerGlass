# Session Schema Reference (v1.0)

This document is the single source of truth for building `.session.json` files by hand. It consolidates the rules enforced by `SessionManager`, the cue/cuelist dataclasses, and the current UI expectations so you can author a session from scratch that loads and runs in MesmerGlass without opening the editors.

---

## Quick Skeleton

```json
{
  "version": "1.0",
  "metadata": { ... },
  "playbacks": {
    "playback_key": { ... }
  },
  "cuelists": {
    "cuelist_key": {
      "name": "...",
      "cues": [ ... ]
    }
  },
  "runtime": {
    "active_cuelist": null,
    "active_cue_index": 0,
    "last_playback": null,
    "session_time_elapsed": 0
  },
  "media_bank": [
    { "name": "Images", "path": "C:\\Media\\Images", "type": "images" }
  ]
}
```

All keys are required unless explicitly noted. Extra keys are preserved but ignored by the editors; keep experimental data under namespaced keys if you need forward compatibility.

---

## metadata

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | ✔ | Display name in UI and window title. |
| `description` | string | ✔ | Allow empty string, but field must exist. |
| `created` | ISO-8601 string | ✔ | Set once when the file is first authored. |
| `modified` | ISO-8601 string | ✔ | Updated on every save. SessionManager overwrites this when saving. |
| `author` | string | ✖ | Optional attribution. |
| `tags` | array[string] | ✖ | Free-form search tags. |

Top-level `version` currently must be the string `"1.0"`. You can add other metadata fields (difficulty, theme, etc.) but expect to update tooling if they need UI exposure.

---

## playbacks

`playbacks` is a dictionary keyed by an identifier you choose (snake_case recommended). Each value carries the configuration the visual runtime consumes.

### Shared playback fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `version` | string | ✔ | Set to `"1.0"` for now. |
| `name` | string | ✔ | Friendly name shown in editors. |
| `description` | string | ✖ | Recommended for future authors. |

### spiral

```json
"spiral": {
  "type": "logarithmic",
  "rotation_speed": 40.0,
  "opacity": 0.5,
  "reverse": false,
  "arm_color": [1, 1, 1],
  "gap_color": [0, 0, 0]
}
```

- `type`: one of `logarithmic`, `quadratic`, `linear`, `sqrt`, `inverse`, `power`, `sawtooth`.
- `rotation_speed`: float multiplier (UI slider 40–400 translates to 4.0–40.0x).
- `opacity`: 0.0–1.0.
- `reverse`: flips rotation direction.
- `arm_color`/`gap_color`: optional RGB triples in 0.0–1.0.

### media

```json
"media": {
  "mode": "both",
  "cycle_speed": 50,
  "fade_duration": 0.5,
  "use_theme_bank": true,
  "paths": [],
  "shuffle": false,
  "bank_selections": [0, 1]
}
```

- `mode`: `both`, `images`, or `videos`.
- `cycle_speed`: integer 1–100 (lower is slower).
- `fade_duration`: seconds between stills/videos (0 for hard cut).
- `use_theme_bank`: when true, pull assets from the selected media banks.
- `paths`: optional explicit file list or folders; leave empty to rely on banks.
- `shuffle`: randomized order within the playlist.
- `bank_selections`: list of indexes into `media_bank` (respect order; `0` is the first entry).

### text

```json
"text": {
  "enabled": true,
  "mode": "centered_sync",
  "opacity": 0.8,
  "use_theme_bank": true,
  "library": [],
  "sync_with_media": true,
  "manual_cycle_speed": 50,
  "color": [1, 1, 1],
  "font_path": null,
  "use_font_bank": true
}
```

- `mode`: `centered_sync`, `subtext`, or `none`.
- `use_theme_bank`: pulls text lines from ThemeBank when true.
- `library`: manual override strings (ignored if ThemeBank or Text tab has a user override).
- `sync_with_media`: ties text changes to media cycles; set to false to enable manual speed.
- `manual_cycle_speed`: 1–100 when `sync_with_media` is false.
- `color`: optional RGB triple (defaults to white).
- `font_path`: direct font override.
- `use_font_bank`: when true, ThemeBank can supply fonts; ignored if user locked the Text tab font.

### zoom

```json
"zoom": {
  "mode": "exponential",
  "rate": 0.2
}
```

- `mode`: `exponential`, `pulse`, `linear`, or `none` (UI shows “Disabled”).
- `rate`: float intensity; actual range used in UI is 0.0–5.0.

### accelerate (optional)

```json
"accelerate": {
  "enabled": true,
  "duration": 30,
  "start_rotation_x": 4.0,
  "start_media_speed": 50.0,
  "start_zoom_rate": 0.2
}
```

Enable this block to ramp spiral/media/zoom speeds during the first `duration` seconds. Leave the block out entirely (or set `enabled` false) for static behavior.

---

## cuelists and cues

`cuelists` mirrors `playbacks`: dictionary keyed by ID. Each cuelist object supports the following:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | ✔ | Display name. |
| `description` | string | ✖ | Optional. |
| `version` | string | ✖ | Keep at `"1.0"` for consistency. |
| `author` | string | ✖ | Optional. |
| `loop_mode` | string | ✔ | `once`, `loop`, or `ping_pong`. |
| `transition_mode` | string | ✔ | `snap` or `fade` (applies between cues unless cue overrides). |
| `transition_duration_ms` | number | ✔ | Default duration when `transition_mode` is `fade`. |
| `metadata` | object | ✖ | Free-form tags/labels. |
| `cues` | array | ✔ | Ordered list of cue objects. |

### cue object

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | ✔ | Unique within the cuelist. |
| `duration_seconds` | number | ✔ | Positive float. |
| `playback_pool` | array | ✔ | At least one playback entry. |
| `selection_mode` | string | ✔ | `on_cue_start`, `on_media_cycle`, or `on_timed_interval`. |
| `selection_interval_seconds` | number | conditional | Mandatory for `on_timed_interval`. |
| `transition_in` / `transition_out` | object | ✔ | `{ "type": "none|fade|interpolate", "duration_ms": >=0 }`. |
| `audio_tracks` | array | ✖ | Max two entries. |
| `text_messages` | array[string] | ✖ | Overrides playback text for this cue. |
| `vibrate_on_text_cycle` | bool | ✖ | Enables pairing with haptics. |
| `vibration_intensity` | number | ✖ | 0.0–1.0, default 0.5. |

> Legacy `audio` blocks mirroring the first entry are still written for compatibility; `audio_tracks` is the authoritative format.

#### playback_pool entry

```json
{
  "playback": "image_log_sinking_test",
  "weight": 1.0,
  "min_duration_s": 10.0,
  "max_duration_s": 15.0,
  "min_cycles": null,
  "max_cycles": null,
  "text_messages": ["Follow", "Sink"]
}
```

- `playback`: key from the top-level `playbacks` dict.
- `weight`: selection probability when using weighted or shuffle algorithms (>0).
- `min_duration_s` / `max_duration_s`: preferred timing constraints.
- `min_cycles` / `max_cycles`: deprecated but still respected for legacy sessions.
- `text_messages`: optional override for just this entry (rotates with the playback).

#### audio_tracks entry

```json
{
  "file": "C:/Media/Audio/track.wav",
  "volume": 0.8,
  "loop": false,
  "fade_in_ms": 1000,
  "fade_out_ms": 1000,
  "role": "hypno"
}
```

- `role`: `hypno`, `background`, or `generic`. Only one non-generic role per cue is allowed.

---

## runtime

Tracks live progress so a session can resume immediately after saving mid-run. Fields are optional for hand-authored files but the structure must be present.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `active_cuelist` | string \| null | ✔ | Set to `null` for a fresh session. |
| `active_cue_index` | integer | ✔ | Usually `0`. |
| `last_playback` | string \| null | ✔ | The most recent playback key (or null). |
| `session_time_elapsed` | number | ✔ | Seconds. |

Older sessions may include `last_cuelist` or `custom_media_dirs`; these remain backward compatible.

---

## media_bank

Array describing the user media directories the banks reference.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | ✔ | Label shown in UI checklists. |
| `path` | string | ✔ | Absolute path to the folder. Escape backslashes in JSON. |
| `type` | string | ✔ | `images`, `videos`, or `fonts`. |

Keep ordering stable; `bank_selections` in playbacks reference the zero-based index.

---

## Minimal Valid Example

```json
{
  "version": "1.0",
  "metadata": {
    "name": "Manual Sample",
    "description": "Hand-authored session",
    "created": "2025-11-28T12:00:00",
    "modified": "2025-11-28T12:00:00",
    "author": "CLI",
    "tags": ["manual"]
  },
  "playbacks": {
    "gentle_intro": {
      "version": "1.0",
      "name": "Gentle Intro",
      "description": "Soft spiral",
      "spiral": {
        "type": "logarithmic",
        "rotation_speed": 40.0,
        "opacity": 0.5,
        "reverse": false
      },
      "media": {
        "mode": "images",
        "cycle_speed": 40,
        "fade_duration": 0.0,
        "use_theme_bank": true,
        "paths": [],
        "shuffle": false,
        "bank_selections": [0]
      },
      "text": {
        "enabled": true,
        "mode": "centered_sync",
        "opacity": 0.9,
        "use_theme_bank": true,
        "library": [],
        "sync_with_media": true,
        "manual_cycle_speed": 50
      },
      "zoom": {
        "mode": "exponential",
        "rate": 0.2
      }
    }
  },
  "cuelists": {
    "main": {
      "name": "Main Flow",
      "description": "Single cue",
      "version": "1.0",
      "author": "CLI",
      "loop_mode": "once",
      "transition_mode": "snap",
      "transition_duration_ms": 2000,
      "metadata": {},
      "cues": [
        {
          "name": "Intro",
          "duration_seconds": 60,
          "playback_pool": [
            { "playback": "gentle_intro", "weight": 1.0 }
          ],
          "selection_mode": "on_cue_start",
          "transition_in": { "type": "fade", "duration_ms": 1500 },
          "transition_out": { "type": "fade", "duration_ms": 1500 },
          "audio_tracks": []
        }
      ]
    }
  },
  "runtime": {
    "active_cuelist": null,
    "active_cue_index": 0,
    "last_playback": null,
    "session_time_elapsed": 0
  },
  "media_bank": [
    {
      "name": "Images",
      "path": "C:/Users/Ash/Desktop/MesmerGlass/Test Media/Images",
      "type": "images"
    }
  ]
}
```

Drop this into `mesmerglass/sessions/manual_sample.session.json`, open it via File → Open Session, and it will run immediately.

---

## Manual Editing Checklist

- Use UTF-8 + LF formatting; editors expect ASCII-compatible characters for paths.
- Keep trailing commas out of JSON—Python’s loader is strict.
- Ensure every cue references a playback that exists.
- Ensure every playback referencing `bank_selections` has those indexes available in `media_bank`.
- Set absolute paths for media banks/fonts so the ThemeBank scanner can locate files without guessing.
- When cloning sessions, refresh `metadata.created` if you want audit trails; `modified` will auto-update on save.
- If you experiment with new fields, prefix them (e.g., `"ext": { "my_feature": ... }`) so legacy tooling skips them gracefully.

Following this reference, you can craft `.session.json` files by hand, drop them into `mesmerglass/sessions/`, and open/run them without relying on the UI editors.