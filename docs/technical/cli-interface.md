# CLI Interface

The CLI is built on argparse and mirrors every tool used during development. You can:

- Launch the Phase 7 GUI directly: `python run.py`
- Use the package entry point: `python -m mesmerglass <subcommand>`

Both paths share the same logging configuration and defaults. By default we now collapse repetitive renderer/media chatter into short INFO summaries every few seconds; switch to `--log-level DEBUG` whenever you need the original per-texture or per-file traces.

## Key Subcommands

### run
Launch the MainApplication window (equivalent to `python run.py`). Supports VR flags such as `--vr`, `--vr-mock`, `--vr-safe-mode`, and `--vr-minimal` for compositor mirroring.

### selftest
Smoke-test imports, confirm Python/Qt versions, and exit with status 0/1. Useful for CI “is the environment ready?” checks:

```powershell
python -m mesmerglass selftest
```

### pulse (device spot test)
Send a single vibration command via the embedded Buttplug server:

```powershell
python -m mesmerglass pulse --level 0.8 --duration 2000 --port 12345
```

### server
Run a standalone Buttplug-compatible server for external clients:

```powershell
python -m mesmerglass server --port 12345
```

### toy
Spin up a deterministic virtual toy that connects to the local server—handy for demonstrations and automated testing:

```powershell
python -m mesmerglass toy --name "QA Toy" --port 12345 --latency-ms 40 --run-for 5
```

### test-run
Wrapper around pytest with presets (fast, bluetooth, coverage, etc.):

```powershell
python -m mesmerglass test-run fast -v
python -m mesmerglass test-run -- -k "not slow"
```

### state / session
Capture or replay MainApplication session snapshots:

```powershell
python -m mesmerglass state --save --file my_state.json
python -m mesmerglass session --load sessions/default.session.json
```

### cuelist
Headless tooling for the Phase 5 cuelist runner. Flags `--validate`, `--print`, and `--execute` share a single parser and can emit JSON with `--json`.

- `--validate` performs structural checks plus filesystem validation for every playback/audio reference.
- `--print` returns either a readable summary or the canonical JSON payload.
- `--execute` simulates cue timing without Qt, respecting optional `--duration` overrides.

Exit codes: 0 success, 1 error (missing file/validation failure), matching the automation expectations used in `mesmerglass/tests/test_cli_cuelist.py`.

**Dual audio awareness:** validation now also enforces audio role coverage. If a cue configures audio but omits the `hypno` role, validation fails. Missing or non-looping background tracks generate warnings (reported in both console and JSON output) so CI logs highlight cues that will run without ambient layers. Human-readable `--print` summaries list per-cue role coverage (`hypno/background`) for quick scans.

### theme
Inspect theme collections, stress-test the weighted shuffler, or exercise ThemeBank in headless mode.

- `--load <file>` plus `--list`, `--show-config`, or `--test-shuffler N` provide the legacy inspection utilities.
- `--diag` switches the command into perf diagnostics mode: it constructs a real `ThemeBank`, enables `PerfTracer`, runs a configurable number of `get_image` calls (or background prefetch-only loops), and prints the longest spans.
- Pair `--diag-json` with `--diag-fail` to archive raw snapshots and gate CI builds whenever any span meets/exceeds `--diag-threshold` (exit code 3 on violation).

Diagnostics share the same reporting helpers as `cuelist --diag`, so table formatting, thresholds, and JSON schemas match exactly. Use them to spot cache starvation (e.g., `theme_sync_load` spans), slow OpenCV/PIL decodes, or runaway background workers without launching the full GUI.

### vr-selftest / spiral-test / media-measure
Diagnostics for rendering, VR, and timing. Refer to `docs/cli.md` for the full option matrix.

## Entry Point Summary

| Goal | Command |
|------|---------|
| Launch GUI (Phase 7 MainApplication) | `python run.py` or `python -m mesmerglass run` |
| Quick smoke test | `python -m mesmerglass selftest` |
| Pulse device | `python -m mesmerglass pulse --level 0.5 --duration 1500` |
| Start server for external clients | `python -m mesmerglass server --port 12345` |
| Execute tests | `python -m mesmerglass test-run` |

Exit codes follow conventional CLI practice: 0 success, non-zero on error (argument errors use status 2).
