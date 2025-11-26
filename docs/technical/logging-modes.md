# Logging Modes

MesmerGlass now ships with log presets so you can dial noise up or down without memorizing multiple flags. All presets are available via the global `--log-mode` switch (`quiet`, `normal`, `perf`) or the `MESMERGLASS_LOG_MODE` environment variable.

## Mode summary

| Mode   | Console output                               | File output | Extras |
|--------|----------------------------------------------|-------------|--------|
| quiet  | Suppresses everything below `WARNING`, even if the file log level is lower. Use this for CI or scripted runs where you only care about failures. | Respects `--log-level` | Keeps aggregated INFO summaries in the log file for ThemeBank/image activity.
| normal | Existing behavior (INFO summaries + warnings). | Respects `--log-level` | Default. `[spiral.trace]` lines stay muted unless explicitly enabled.
| perf   | Forces `DEBUG` if you requested a higher level, and reenables `[spiral.trace]` compositor chatter along with per-image ThemeBank traces. | Matches console | Designed for short profiling sessions—expect lots of output (enables `PerfTracer`).

## Aggregated burst logging

Several subsystems now report burst summaries instead of spamming a line per frame:

- **ThemeBank**: every ~2 seconds it emits a single `[ThemeBank] served N images` line that includes synchronous load counts and cache pressure.
- **VisualDirector**: image uploads are coalesced into `[visual] Applied N images` summaries that also mention pending retries.
- **Spiral compositor**: `[spiral.trace]` lines are filtered unless you opt into perf mode or export `MESMERGLASS_SPIRAL_TRACE=1`.

The `BurstSampler` utility drives these summaries so you still see totals during quiet modes while keeping console noise minimal. When perf mode is active, the new `PerfTracer` timeline collector also records span metadata for cue transitions, audio prefetch, and compositor swaps so you can retrieve a structured snapshot later.

## Re-enabling compositor traces

The compositor still logs plenty of diagnostic detail, but `[spiral.trace]` and `[spiral.debug]` messages are now filtered out unless one of the following is true:

1. You pass `--log-mode perf` (or set `MESMERGLASS_LOG_MODE=perf`).
2. You export `MESMERGLASS_SPIRAL_TRACE=1` before launching the CLI.
3. You manually set `--log-level DEBUG` *and* enable the env var above.

If you only need a handful of trace lines, prefer `--log-mode perf` so the filter automatically opens.

## Tips

- Pair `--log-mode quiet` with `--log-level DEBUG` when you want full file detail but clean CI stdout.
- Use `--log-mode perf --log-file mesmerglass-perf.log` during cue-switch profiling runs to capture per-image timings without overwhelming your terminal.
- `run.py` honors `MESMERGLASS_LOG_MODE`, so GUI launches outside the CLI can still opt into these presets.
- `PerfTracer` is only active in perf mode (or when explicitly forced). The `cuelist --diag` command automatically enables perf mode, spins up a headless runner, and prints the longest spans so you can spot 1.7 s cue stalls without attaching a debugger. See `docs/technical/perf-tracing.md` for details.

## Frame spike attribution

Session runs now emit a "Worst Frame Spike" line alongside the frame delay histogram. When a frame blows past the 100 ms budget, the runner looks for the most recent blocking operation (for example, a synchronous audio prefetch fallback) and reports it next to the spike duration. This makes it obvious when a 1.7 s pause originated from a track decode versus something like a cue transition. The console warning fires immediately, and the end-of-session summary captures the longest spike so you can line it up with frame delay logs after the run.
