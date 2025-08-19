# MesmerGlass CLI

Argparse-based command line for running the app and utilities. Use via:

```
python -m mesmerglass --help
python -m mesmerglass run --log-level DEBUG
```

## Global options

- `--log-level {DEBUG,INFO,WARNING,ERROR}` (default: INFO)
- `--log-file <path>` (default: per-user log dir)
- `--log-format {plain,json}` (default: plain)

## Subcommands

- `run` — Start the GUI.
- `pulse --level 0..1 --duration <ms>` — Send a single pulse to the selected device.
- `server [--port N]` — Start a local Buttplug-compatible server.
- `ui` — Drive basic UI navigation (list/select tabs) and simple actions for testing.
- `selftest` — Quick import/environment check; exit code 0 on success.

### ui

Drive simple UI actions for tests without heavy side-effects.

Flags:
- `--list-tabs` — Print top-level tab names (one per line) and exit.
- `--tab <name-or-index>` — Select a tab by case-insensitive name or zero-based index.
- `--set-text <str>` — Set overlay text.
- `--set-text-scale <0..100>` — Set text scale percent.
- `--set-fx-mode <name>` — Set FX mode.
- `--set-fx-intensity <0..100>` — Set FX intensity.
- `--vol1 <0..100>` / `--vol2 <0..100>` — Set audio volumes.
- `--displays {all|primary|none}` — Quick-select displays.
- `--launch` / `--stop` — Start/stop overlays.
- `--status` — Print a JSON blob with current state.
- `--timeout <seconds>` — Keep the Qt event loop alive for a short time (default: 0.3s).
- `--show` — Show the main window (default is hidden; CI-safe).

Examples:

```
python -m mesmerglass ui --list-tabs
python -m mesmerglass ui --tab Audio --timeout 0.1
python -m mesmerglass ui --tab "Text & FX" --set-text "HELLO" --set-fx-mode Shimmer --set-fx-intensity 60 --status
python -m mesmerglass ui --displays primary --launch --timeout 0.2
```

## Exit codes

- 0 on success
- 1 on selftest/import failure or UI action error (e.g., unknown tab)
- 2 on argument errors
