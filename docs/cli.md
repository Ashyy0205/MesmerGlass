# MesmerGlass CLI

Argparse-based command line for running the app and utilities. Use via:

```
python -m mesmerglass --help
python -m mesmerglass run --log-level DEBUG
```

Legacy: `python run.py` still works but is deprecated (see migration note).

## Global options

- `--log-level {DEBUG,INFO,WARNING,ERROR}` (default: INFO)
- `--log-file <path>` (default: per-user log dir)
- `--log-format {plain,json}` (default: plain)

## Subcommands

-- `run` — Start the GUI.
-- `pulse --level 0..1 --duration <ms>` — Send a single pulse (alias: `test`).
-- `server [--port N]` — Start a local Buttplug-compatible server.
-- `ui` — Drive basic UI navigation (list/select tabs) and simple actions for testing.
-- `toy` — Run a deterministic virtual toy simulator for dev/CI (no hardware required).
-- `selftest` — Quick import/environment check; exit code 0 on success.
-- `test-run [type]` — Run pytest selection (replaces `run_tests.py`).
### test-run

Wrapper around pytest for common selections.

Examples:
```
python -m mesmerglass test-run              # all tests
python -m mesmerglass test-run fast -v      # fast subset
python -m mesmerglass test-run bluetooth    # bluetooth-marked tests
python -m mesmerglass test-run -c           # with coverage
```

Equivalent legacy commands using `run_tests.py` are deprecated.

### ui

Drive simple UI actions for tests without heavy side-effects.

Flags:
- `--list-tabs` — Print top-level tab names (one per line) and exit.
- `--tab <name-or-index>` — Select a tab by case-insensitive name or zero-based index.
- `--layout {tabbed|sidebar}` — Choose the UI layout (default: `tabbed`).
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
python -m mesmerglass ui --layout sidebar --show --timeout 0.1
python -m mesmerglass ui --tab "Text & FX" --set-text "HELLO" --set-fx-mode Shimmer --set-fx-intensity 60 --status
python -m mesmerglass ui --displays primary --launch --timeout 0.2
```

### toy (dev-only)

Run a simple virtual toy that connects to the local Buttplug server and reacts to ScalarCmd/StopDeviceCmd.

Flags:
- `--name` (default: "Virtual Test Toy")
- `--port` (default: 12345)
- `--latency-ms` (default: 0)
- `--map {linear|ease}` (default: linear)
- `--gain` (default: 1.0)
- `--gamma` (default: 1.0; used for ease curve)
- `--offset` (default: 0.0)
- `--run-for` seconds to auto-exit (default: 5.0)

Examples:

```
python -m mesmerglass server --port 0  # start server on ephemeral port; note the port from logs
python -m mesmerglass toy --port 12345 --latency-ms 50 --map ease --gamma 2.0 --run-for 1.0
```

## Exit codes

- 0 on success
- 1 on selftest/import failure or UI action error (e.g., unknown tab)
- 2 on argument errors
