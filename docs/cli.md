# MesmerGlass CLI

Argparse-based command line for running the app and utilities. Use via:

```
python run.py                          # Launch the Phase 7 MainApplication GUI
python -m mesmerglass --help           # Full CLI reference
python -m mesmerglass run --log-level DEBUG
```

`python run.py` now delegates directly to `mesmerglass.app.run()` so you can double-click or script the GUI without extra flags. The package CLI remains available for automation.

## Global options

- `--log-level {DEBUG,INFO,WARNING,ERROR}` (default: INFO)
- `--log-file <path>` (default: per-user log dir)
- `--log-format {plain,json}` (default: plain)
- `--log-mode {quiet,normal,perf}` (default: normal)

Logging flags can appear either before the subcommand (`python -m mesmerglass --log-level DEBUG run`) or after it (`python -m mesmerglass run --log-level DEBUG`).

### Logging verbosity defaults

`INFO` output now favors concise summaries: text overlays, ThemeBank carousel rebuilds, and async media loads emit burst totals every few seconds instead of one line per event. Use `--log-level DEBUG` whenever you need the legacy per-texture/per-image traces, or flip on `--log-mode perf` for a ready-made preset that forces DEBUG and reenables `[spiral.trace]` spam.

Logging modes:

- `quiet` — keeps file logging at the requested level but raises console output to WARNING/ERROR so automated runs stay clean.
- `normal` — default mix of summary INFO and occasional warnings.
- `perf` — forces DEBUG level (unless you already requested DEBUG or lower) and reenables compositor `[spiral.trace]` lines plus ThemeBank per-image traces.

See `docs/technical/logging-modes.md` for concrete examples and how these map to env vars like `MESMERGLASS_SPIRAL_TRACE`.

## Subcommands

   - Flags:
     - `--vr` — Enable head-locked VR streaming (OpenXR if available; falls back to mock).
     - `--vr-mock` — Force mock VR mode (no OpenXR session attempted).

### instructions
Execute a sequence of CLI commands described in a plaintext file—ideal for CI scripts, repro recipes, or demos that you want to run deterministically:

```powershell
# instructions.txt
selftest
state --print --file sessions/default.json
ui --tab "Text & FX" --set-text "Ready" --timeout 0.1 --status

python -m mesmerglass instructions instructions.txt
```

Each non-empty, non-comment line is treated as a MesmerGlass CLI invocation. Commands run sequentially; the runner stops on the first failure unless you pass `--continue-on-error`. Use `--dry-run` to preview, `--workdir` to pin a different directory (defaults to the current working directory; pass `--workdir @file` to run relative to the instructions file), and `--no-echo` to silence the `[instructions] (N/M)` banner.

Shortcut: `python run.py instructions.txt` automatically invokes the runner, so you can re-use existing notes/scripts without learning the full CLI yet. Add extra options later via `python run.py instructions instructions.txt --continue-on-error`.

### selftest

Environment sanity check that exercises the Python-side dependencies *and* verifies the LoomWindowCompositor background diagnostics hook. It does **not** open a Qt window or GL context, so it is safe to run in CI.

- Confirms `PyQt6` + audio/video engines import cleanly
- Imports `mesmerglass.mesmerloom.window_compositor` and asserts `get_background_debug_state()` exists
- Prints `"Selftest OK: imports + background diagnostics available"` on success

Exit codes:
- `0` — environment ready (all imports + diagnostics available)
- `1` — import failure or compositor debug hook missing

Examples:

```powershell
python -m mesmerglass selftest
python -m mesmerglass --log-level DEBUG selftest
```

### theme

Load and inspect theme collections for image/video/text content.

Flags:
- `--load <path>` — Path to theme JSON file (Trance format or direct).
- `--list` — List all themes in the collection with details.
- `--show-config` — Print theme configuration as JSON.
- `--test-shuffler <N>` — Test weighted shuffler with N selections (anti-repetition algorithm).
- `--test-cache` — Test image cache creation.
- `--diag` — Run ThemeBank perf diagnostics using the real loader/cache stack (requires `--load`).
- `--diag-json` — Emit the raw `PerfTracer` snapshot for archival/automation.
- `--diag-limit` / `--diag-threshold` — Control how many spans to print and which duration (ms) counts as “slow”.
- `--diag-lookups` — Number of `get_image` calls to simulate (triggers lookahead + sync fallbacks).
- `--diag-cache-size` — Override ThemeBank cache size during diagnostics.
- `--diag-prefetch-only` — Skip synchronous loads; only measure background prefetch threads.
- `--diag-fail` — Exit with code `3` when any span meets/exceeds the threshold (CI gate).

Examples:

```
# Show summary
python -m mesmerglass theme --load themes/default.json

# List all themes
python -m mesmerglass theme --load themes/default.json --list

# Show full configuration
python -m mesmerglass theme --load themes/default.json --show-config

# Test shuffler (anti-repetition)
python -m mesmerglass theme --load themes/default.json --test-shuffler 100

# Test image cache
python -m mesmerglass theme --test-cache

# Run diagnostics and fail the build if a span >=150 ms is recorded
python -m mesmerglass theme --load themes/default.json --diag --diag-threshold 150 --diag-fail
```

Diagnostics reuse the `PerfTracer` table format from `cuelist --diag`. When `--diag-fail` is present the command exits with status `3` as soon as any span meets/exceeds the requested threshold; otherwise it returns 0 even if slow spans were detected.

### themebank

Interrogate the new ThemeBank readiness helpers without opening the GUI. Every subcommand honors the global logging flags described earlier.

```
python -m mesmerglass themebank --help
```

Subcommands:

- `stats` — Print a single-line summary plus a JSON blob detailing image/video counts, whether the cache has delivered at least one decoded asset, pending async loads, and the last successful image/video paths. Exit code `0` indicates “ready”; `3` means no usable media was discovered or decoded yet. Pass `--json` for machine-readable output only.
- `selftest` — Runs the same ThemeBank readiness gate that `SessionRunner` and `SessionRunnerTab` rely on. Useful for CI smoke tests (`0` ready, `3` not ready, `1` unexpected error).
- `pull-image` / `pull-video` — Force ThemeBank to fetch one asset immediately and print the resolved path. Handy when you want to confirm the decoded asset on disk and double-check permissions. Use `--timeout` (seconds, default 5.0) to fail quickly when no media is available.

Common flows:

```
# Inspect readiness details and pending queue depth
python -m mesmerglass themebank stats --json

# CI-style gate that mirrors SessionRunner
python -m mesmerglass themebank selftest --timeout 10

# Manually spot-check media access
python -m mesmerglass themebank pull-image
python -m mesmerglass themebank pull-video --timeout 2
```

The CLI uses the same loader that powers the GUI, so if `themebank selftest` reports `ThemeBank empty` you can expect sessions to stay stuck on the spiral/text overlay until media paths are corrected or rescanned.

### run (VR options)

Enable a head-locked VR stream that mirrors the spiral compositor each frame.

Notes:
- OpenXR is optional. If not present or binding fails, the bridge runs in mock mode (logs only).
- The XR session is now bound to the compositor's actual GL context. If no GL context is current at startup, session creation is deferred until the compositor is initialized.
- On Windows/Qt, we make the compositor context current briefly to bind the XR session safely.

VR stability helpers:
- `--vr-safe-mode` uses an offscreen FBO tap in the compositor for safer mirroring.
- `--vr-minimal` disables media, OpenCV, server, BLE loop, and diagnostics watchdog for maximum stability.
- You can set `MESMERGLASS_VR_DEBUG_SOLID=1` to fill the XR swapchain with solid green (per-eye) to confirm visibility independent of the blit.

Examples:

```
python -m mesmerglass run --vr
python -m mesmerglass run --vr --vr-mock  # force mock even if OpenXR is available
python -m mesmerglass run --vr --vr-safe-mode --vr-minimal  # safest path
```

#### ThemeBank throttles (CLI-only)

The GUI no longer exposes the old "ThemeBank Limits" panel—background media throttles stay at their hardcoded defaults unless you override them with CLI flags or environment variables. Use the `run` subcommand's ThemeBank group when you need to experiment:

- `--theme-lookahead <N>` — Cap the lookahead queue (default 32)
- `--theme-batch <N>` — Limit decoded images per preload batch (default 12)
- `--theme-sleep-ms <MS>` — Sleep between background loads (default 4.0)
- `--theme-max-ms <MS>` — Max milliseconds a preload batch can run before yielding (default 200)
- `--media-queue <N>` — Async decode queue depth (default 8)
- `--theme-preload-all` or `--theme-no-preload` — Force/disable aggressive preloading

These switches mirror the environment variables `MESMERGLASS_THEME_*` and give you the only supported path to tweak ThemeBank performance.

### vr-selftest

Run a minimal offscreen OpenGL render loop and submit frames to OpenXR swapchains via the VrBridge without creating any Qt windows.

Flags:
- `--seconds <S>` — Duration to run (default: 2.0)
- `--fps <N>` — Target frames per second (default: 60)
- `--pattern {solid|grid}` — Test pattern (default: solid)
- `--size WxH` — Render size (default: 1920x1080)
- `--mock` — Force VR mock mode (skip OpenXR)

Exit codes:
- 0 on success
- 1 on unexpected error

Examples:

```powershell
# Quick sanity test without OpenXR
python -m mesmerglass vr-selftest --seconds 1 --fps 30 --pattern grid --mock

# Stream to ALVR (start SteamVR + ALVR first), 60 FPS for 5 seconds
python -m mesmerglass vr-selftest --seconds 5 --fps 60 --pattern solid
```

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

### state

Manage a lightweight snapshot of current UI-related configuration (distinct from message packs):

Actions (mutually exclusive):
- `--save --file path.json` capture a fresh MainApplication session state to JSON
- `--apply --file path.json` load a state file and apply to a headless MainApplication instance (prints minimal status JSON)
- `--print --file path.json` pretty-print canonical JSON to stdout

Schema top-level keys: `version`, `kind="session_state"`, `saved_at`, `app_version`, `video`, `audio`, `textfx`, `device_sync`.

`textfx` now may include:
- `font_path` — user-imported font file (ttf/otf) reloaded on state apply (if still present)
- `font_family`, `font_point_size` — resolved Qt font metrics

`audio` block additions (Phase 7.5+):
- `max_buffer_seconds_hypno`, `max_buffer_seconds_background`, `max_buffer_seconds_generic` — per-role decoded-buffer budgets (defaults: 10 s for hypno/background, 5 s generic). Any track that would exceed its role limit auto-streams instead of decoding, ensuring total buffered audio never surpasses ~20 s even when multiple cues are queued.
- `stream_threshold_mb` — unchanged, but now combined with the buffer caps so oversized files stream immediately while shorter loops still benefit from the two-channel cache.

Environment: for `state` and `session` commands the embedded Mesmer server is auto-suppressed via `MESMERGLASS_NO_SERVER=1` to keep operations fast and deterministic in CI.

Examples:
```
python -m mesmerglass state --save --file my_state.json
python -m mesmerglass state --print --file my_state.json
python -m mesmerglass state --apply --file my_state.json
```

### ui (headless shim)

Drive a minimal UI surrogate that exposes the legacy `Launcher` knobs needed by
automation. This shim keeps CLI tests deterministic without spinning up the full
Phase 7 MainApplication.

Key behaviors:
- `--set-font-path`, `--set-text`, `--vol1/--vol2`, `--tab`, and `--status` operate entirely in-process; font paths are recorded even if the file is not a real font.
- `--load-state` accepts both canonical session-state JSON and ad-hoc dicts; values hydrate the shim before other setters run.
- `--launch`/`--stop` simply toggle an internal `running` flag that shows up in the status JSON (no overlays are spawned).
- `--list-tabs` and `--tab` work against a static set of logical tabs (Display, Home, Cuelists, Playbacks, Device, Performance, DevTools).
- When the shim is active, commands that depend on the historic OpenGL launcher (e.g. `media-measure --mode launcher`) will emit a clear “skipped: Launcher UI not available” note instead of crashing.

If you need the full GUI instead of the shim, launch via `python run.py` or
`python -m mesmerglass run`. The CLI will automatically switch back to the true
launcher once `mesmerglass.ui.launcher.Launcher` is implemented by the Phase 7
UI layer.

### cuelist

Work with Phase 5+ cuelist files without launching the GUI. Supports validation, summaries, and headless execution.

Flags:
- `--load <path>` (required) — Path to `.cuelist.json` file.
- `--validate` — Structural validation plus on-disk dependency checks for playback/audio files.
- `--print` — Show a human-readable summary (default text) or emit raw JSON when paired with `--json`.
- `--execute` — Run a fast headless simulation (default action when no other mode is selected).
- `--duration <seconds>` — Override total runtime for execution mode (useful for smoke tests).
- `--json` — Machine-readable output for `--validate` and `--print`.
- `--diag` — Run the new PerfTracer-powered diagnostics harness (headless).
- `--diag-cues <N>` — Number of cues to simulate while gathering spans (default: 2).
- `--diag-json` — Emit the raw PerfTracer snapshot as JSON instead of the table view.
- `--diag-threshold <ms>` — Only show spans at/above this duration in the summary table (default: 250 ms).
- `--diag-limit <N>` — Cap the number of spans printed in the summary table (default: 10).
- `--diag-prefetch-only` — Skip playback startup and only measure audio prefetch latency.
- `--diag-fail` — Exit with code `3` when any span meets/exceeds the threshold (useful for CI alerts).

Examples:
```
# Validate and output JSON status
python -m mesmerglass cuelist --load sessions/demo.cuelist.json --validate --json

# Print summary to stdout
python -m mesmerglass cuelist --load sessions/demo.cuelist.json --print

# Execute headlessly for 20 seconds
python -m mesmerglass cuelist --load sessions/demo.cuelist.json --execute --duration 20

# Collect diagnostics for the first three cues and print the longest spans
python -m mesmerglass cuelist --load sessions/demo.cuelist.json --diag --diag-cues 3 --diag-threshold 150 --diag-limit 5

# Emit raw JSON spans and fail CI when any span exceeds 500 ms
python -m mesmerglass cuelist --load sessions/demo.cuelist.json --diag --diag-json --diag-threshold 500 --diag-fail
```

#### Diagnostics (`--diag`)

`--diag` spins up a lightweight `SessionRunner` with a headless visual stub and the real `AudioEngine`, forces `--log-mode perf` (so `PerfTracer` is enabled), and runs through the first _N_ cues (default: 2). The command prints a ranked table of spans grouped by category (`audio`, `cue`, `visual`, etc.) so you can see exactly where a transition stalled. Use `--diag-json` when you want to archive the snapshot, and pair `--diag-fail` with a custom `--diag-threshold` to break CI whenever a cue step exceeds your budget.

Diagnostics never launch the GUI and they automatically stop the async prefetch worker when finished, making them safe to run repeatedly in CI or on a headless workstation.

#### Audio role validation & warnings

- `--validate` now reports **warnings** when a cue configures only a hypno track (no looping background) or when the background track disables looping. JSON output gains a `warnings` array alongside `errors`.
- Missing hypno-role assignments are treated as validation errors when any audio is present, ensuring dual-track cues remain deterministic.
- `--print` summaries list per-cue audio role coverage (`hypno/background`) so you can spot silent layers quickly in CI logs.

## Exit codes

- 0 on success
- 1 on selftest/import failure or UI action error (e.g., unknown tab)
- 2 on argument errors

### spiral-test

Run a short GPU spiral render for benchmarking / CI availability checks.

Arguments:
- `--video <path>` optional background video (loops if shorter than duration). You can pass a relative filename under `MEDIA/Videos` or an absolute path.
- `--intensity 0..1` starting intensity (default: 0.75)
- `--blend {multiply,screen,softlight}` blend mode (default: multiply)
- `--duration <seconds>` run time (default: 5.0)
- `--render-scale {1.0,0.85,0.75}` offscreen scale (default: 1.0)
- `--supersampling {1,4,9,16}` anti-aliasing level: 1=none, 4=2x2, 9=3x3, 16=4x4 (default: 4)
- `--precision {low,medium,high}` floating-point precision level (default: high)
- `--debug-gl-state` print OpenGL state information for debugging visual artifacts
- `--screen <N>` select display index (0=primary, 1=secondary, ...)

Exit Codes:
- 0 success (prints average FPS summary)
- 77 OpenGL unavailable (environment without GL context)
- 1 unexpected error

Examples:
```
python -m mesmerglass spiral-test --screen 1 --duration 2
python -m mesmerglass spiral-test --intensity 0.8 --blend screen --render-scale 0.85
python -m mesmerglass spiral-test --video sample.mp4 --duration 4 --blend softlight
python -m mesmerglass spiral-test --video MEDIA/Videos/example.mp4 --duration 3
python -m mesmerglass spiral-test --supersampling 16 --intensity 0.3 --duration 3
python -m mesmerglass spiral-test --precision high --supersampling 4 --intensity 0.2
python -m mesmerglass spiral-test --debug-gl-state --intensity 0.2 --duration 3
```

### spiral-type

Test specific Trance spiral types with custom width and rotation parameters. Uses the 7-type spiral system from Trance with cone-intersection depth effects.

Arguments:
- `--type {1-7}` spiral type (default: 3)
  - 1: Logarithmic — Tighter at center, rapidly expanding outward
  - 2: Quadratic — Accelerating expansion from center
  - 3: Linear — Default uniform spacing (Archimedean spiral)
  - 4: Square Root — Decelerating expansion, tighter at edges
  - 5: Inverse Spike — Central spike at r=1, symmetric
  - 6: Power — Dramatic power-law transition at r=1
  - 7: Modulated — Adds periodic 0.2-unit ripples
- `--width {360,180,120,90,72,60}` spiral width in degrees (default: 60)
  - 60° = 6 arms (dense, rapid rotation)
  - 72° = 5 arms (pentagonal symmetry)
  - 90° = 4 arms (quadrant divisions)
  - 120° = 3 arms (triangular symmetry)
  - 180° = 2 arms (binary division)
  - 360° = 1 arm (single continuous spiral)
- `--rotation FLOAT` rotation speed amount (default: 2.0)
- `--duration FLOAT` test duration in seconds (default: 5.0)
- `--intensity FLOAT` intensity 0-1 (default: 0.75)
- `--screen INT` target screen index (0=primary, 1=secondary, ...)

Rotation Formula: `phase += amount / (32 * sqrt(spiral_width))`

Examples:
```bash
# Test logarithmic spiral with 6 arms
python -m mesmerglass spiral-type --type 1 --width 60 --duration 5

# Test modulated spiral with 2 arms, slow rotation
python -m mesmerglass spiral-type --type 7 --width 180 --rotation 1.0 --duration 10

# Fast-rotating quadratic spiral on secondary screen
python -m mesmerglass spiral-type --type 2 --rotation 4.0 --screen 1 --duration 3

# Single-arm power spiral with low intensity
python -m mesmerglass spiral-type --type 6 --width 360 --intensity 0.3 --duration 8
```

### mode-verify

Headless diagnostics to confirm that a mode JSON produces expected timing:

Checks:
- Spiral RPM → phase-per-second matches `rpm/60` within tolerance.
- Media `cycle_speed` maps to frames-per-cycle using the same exponential formula as Visual Mode Creator.

Arguments:
- `--mode <path>` JSON mode file to validate
- `--frames N` frames to simulate (default: 120)
- `--fps FLOAT` frames per second (default: 60.0)
- `--tolerance FLOAT` allowed relative error (default: 0.05 = 5%)
- `--json` print JSON summary

Exit codes:
- 0 success (within tolerance)
- 2 validation failure (file or tolerance)
- 1 unexpected error

Examples:
```
python -m mesmerglass mode-verify --mode mesmerglass/modes/slow.json
python -m mesmerglass mode-verify --mode my_mode.json --frames 300 --tolerance 0.02 --json
```

### spiral-measure

Measure how long a spiral arm takes to sweep a given angle, using either the pure director tick (deterministic 60 FPS) or an event-loop driven Qt timer. Useful to compare timing across code paths and validate rotation math.

Arguments:
- `--rpm FLOAT` spiral speed in RPM (signed; negative = reverse)
- `--x FLOAT` UI speed value mapped to RPM using the Visual Mode Creator gain (RPM = x * 10)
- `--rpm-list` comma-separated RPM values (e.g., `60,90,120`)
- `--x-list` comma-separated x values (e.g., `10,13,20`)
- `--rpm-range` RPM range `start:stop:step` (e.g., `30:180:30`)
- `--x-range` x range `start:stop:step` (e.g., `5:20:2.5`)
- `--delta-deg FLOAT` degrees to sweep (default: 90)
- `--mode {director,qt16,qt33}` measurement mode (default: director)
  - `director` uses fixed 60 FPS updates, deterministic
  - `qt16` uses a 16ms QTimer
  - `qt33` uses a 33ms QTimer
- `--reverse` reverse direction (negates RPM)
- `--ceil-frame` report predicted minimal whole-frame time (no loop), including predicted_frames and predicted_seconds (and predicted_seconds_timer for Qt)
- `--compare` compare VMC (director) vs the legacy Qt timer profiles (qt16/qt33) across x values and print a table by default
- `--launcher-mode {qt16,qt33}` legacy timer profile used for comparison (default: qt16)
- `--x-min --x-max --x-step` defaults to 4, 40, 2 for comparison sweeps (or use `--x-list/--x-range`)
- `--clock {frame,wall}` choose time basis; frame = ticks/60 (deterministic), wall = perf_counter (Qt). Default: frame for `--compare`, wall otherwise.
- `--json` print JSON result

Output includes: measured seconds, expected seconds from closed-form formula `delta_deg / (abs(rpm) * 6.0)`, percent error, number of ticks/frames, and achieved phase delta. With `--ceil-frame`, also includes `predicted_frames`, `predicted_seconds` (at 60 FPS), and for Qt modes `predicted_seconds_timer` based on the timer interval.

Examples:
```
# Deterministic quarter turn at 60 RPM should be ~0.25s
python -m mesmerglass spiral-measure --rpm 60 --delta-deg 90 --mode director --json

# Compare Qt 16ms timer against director at x=13 (~130 RPM)
python -m mesmerglass spiral-measure --x 13 --delta-deg 90 --mode qt16
python -m mesmerglass spiral-measure --x 13 --delta-deg 90 --mode director

# Predictive minimal whole-frame time (no loop)
python -m mesmerglass spiral-measure --rpm 60 --delta-deg 90 --mode director --ceil-frame --json

# Sweep multiple speeds (JSON array output):
# RPM list
python -m mesmerglass spiral-measure --rpm-list 60,90,120 --delta-deg 90 --mode director --ceil-frame --json
# x range
python -m mesmerglass spiral-measure --x-range 5:20:2.5 --delta-deg 90 --mode qt16 --ceil-frame --json

# Compare VMC vs legacy Qt timer (table output; x=4..40 step 2 by default)
python -m mesmerglass spiral-measure --compare --launcher-mode qt16 --delta-deg 90
python -m mesmerglass spiral-measure --compare --x-list 4,8,12,20,30,40 --launcher-mode qt33 --delta-deg 90 --ceil-frame
```

### media-measure

Measure media cycling intervals used by Visual Mode Creator (VMC) and the legacy launcher loop, and compare against:
- The expected exponential mapping: `interval_ms = 10000 * 0.005^((speed-1)/99)`
- A Qt PreciseTimer baseline (no GL/text load)

Arguments:
- `--mode {timer,vmc,launcher,both,all}` which paths to measure. `launcher`/`all` retain the retired Phase 6 Qt timer for historical benchmarking; `both` = timer+vmc.
- `--speeds "10,20,50,80,100"` explicit list of cycle speeds (1..100)
- `--sweep start:end:step` inclusive range, e.g. `10:100:10`
- `--cycles N` number of cycles per speed to sample (default: 20)
- `--progress` / `--no-progress` show or disable concise progress lines on stderr (default: on). Progress is always suppressed when `--json` is used and is independent of `--quiet`.
- `--auto-seconds S` target runtime per speed (seconds). Overrides `--cycles` adaptively using the expected mapping.
- `--min-cycles N` lower bound on cycles with `--auto-seconds` (default: 1)
- `--max-cycles N` upper bound on cycles with `--auto-seconds` (default: 20)
- `--include-videos` include videos during VMC measurement (images-only by default)
- `--json` print a JSON object with rows (implies quiet)
- `--quiet` suppress noisy prints from GL/text subsystems during VMC measurement
 - `--timeout-multiplier M` scale factor for the per-speed timeout window (default: 2.5). Effective timeout per speed is `expected_ms * cycles * M + 2000ms`.
 - `--max-seconds S` absolute cap on per-speed runtime. If reached, returns partial samples collected so far (default: no cap).
- `--csv path.csv` write results to a CSV file (columns follow the printed table for the selected mode)

Notes:
- On Windows/argparse, put global flags before the subcommand, e.g. `python -m mesmerglass --log-level WARNING media-measure ...`

Examples:
```powershell
# Single speed (50), both modes, JSON output
python -m mesmerglass --log-level WARNING media-measure --mode both --speeds 50 --cycles 12 --json

# VMC only, sweep a few speeds with fewer cycles
python -m mesmerglass --log-level WARNING media-measure --mode vmc --sweep 10:100:30 --cycles 6 --quiet

# Timer baseline only (no GL), quick check
python -m mesmerglass --log-level WARNING media-measure --mode timer --speeds 50 --cycles 8

# Legacy Qt timer timings at speed 50
python -m mesmerglass --log-level WARNING media-measure --mode launcher --speeds 50 --cycles 8 --json

# All three
python -m mesmerglass --log-level WARNING media-measure --mode all --speeds 50 --cycles 6 --json

# Long runtimes at low speeds
At low speeds (e.g., speed 10 ≈ 6.18 seconds per cycle), multi-cycle measurements can take a while. Use fewer cycles and/or runtime caps:

```
python -m mesmerglass --log-level WARNING media-measure --mode vmc --speeds 10 --cycles 2 --max-seconds 8 --json
python -m mesmerglass --log-level WARNING media-measure --mode all --speeds 10,20,30,40,50,60,80,100 --cycles 3 --timeout-multiplier 1.2 --max-seconds 8 --json

# Auto-cycles: target ~5s per speed with bounds
python -m mesmerglass --log-level WARNING media-measure --mode all --speeds 10,20,30,40,50,60,80,100 --auto-seconds 5 --min-cycles 1 --max-cycles 8 --csv media_measure_table.csv

# With progress (default; goes to stderr so tables/CSV on stdout are clean)
python -m mesmerglass --log-level WARNING media-measure --mode all --speeds 10,20,30,40,50,60,80,100 --auto-seconds 5 --min-cycles 1 --max-cycles 6 --timeout-multiplier 1.2 --max-seconds 8 --quiet

# Disable progress explicitly
python -m mesmerglass --log-level WARNING media-measure --mode vmc --speeds 50 --cycles 6 --no-progress --quiet
```
```
