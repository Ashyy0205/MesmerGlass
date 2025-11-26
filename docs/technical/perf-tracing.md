# Perf Tracing & Diagnostics

`PerfTracer` is a lightweight timeline collector that records the duration of high-impact cue operations (audio prefetch, playback loading, transition execution, etc.). The tracer stays dormant in normal logging mode, then springs to life whenever you opt into `--log-mode perf` or run the CLI diagnostics harness.

## When traces are collected

- **`--log-mode perf`** (or `MESMERGLASS_LOG_MODE=perf`) turns the tracer on for all running `SessionRunner` instances. Every cue transition contributes spans to the in-memory timeline, and you can dump the current state via developer tools or CLI hooks.
- **`python -m mesmerglass cuelist --diag …`** automatically forces perf mode, spins up a headless runner with the real `AudioEngine`, runs the first _N_ cues (default: 2), then prints the longest spans in a readable table or raw JSON. This is the fastest way to confirm whether 1.7 s pauses are coming from audio decode, streaming fallback, or playback setup.
- **`python -m mesmerglass theme --diag …`** constructs a headless `ThemeBank`, enables perf tracing even outside `--log-mode perf`, simulates synchronous `get_image` calls (or prefetch-only loops), and surfaces spans like `theme_sync_load`, `theme_background_preload`, and `media_cache_ingest` so you can pinpoint filesystem or cache bottlenecks without opening the GUI.

## Captured spans

| Span name            | Category | Description / metadata |
|----------------------|----------|------------------------|
| `prefetch_cue`       | `audio`  | Result (`ready`, `async`, `retry`) plus cue index, async flags. Covers buffer reservation, worker submissions, and synchronous fallbacks.
| `await_prefetch`     | `audio`  | Time spent waiting for the async worker before a cue may start. Metadata reports timeout thresholds and whether the wait succeeded.
| `select_playback`    | `cue`    | Pool selection latency (metadata: cue name/index, playback key).
| `load_playback`      | `visual` | Wall time for `VisualDirector.load_playback()` (metadata: playback file/key).
| `cue_audio_start`    | `audio`  | End-to-end audio startup: channel loads, streaming fallback, fade-in. Metadata includes `prefetch_ready`, active channels, and streaming role.
| `execute_transition` | `cue`    | Duration of the SNAP/FADE transition orchestrator, including session completion. Metadata flags the transition mode, target cue, and success.

New spans can be added anywhere by calling `self._perf_span("name", category="foo", extra="metadata")` inside `SessionRunner`.

## Using the CLI diagnostics mode

The `cuelist --diag` workflow is designed for headless debugging:

```powershell
python -m mesmerglass cuelist --load sessions/demo.cuelist.json --diag --diag-cues 3 --diag-threshold 150 --diag-limit 5
```

Produces a table similar to:

```
[diag] Simulated 3 cue(s); threshold=150.0 ms
Span            | Category   | Duration (ms) | Metadata
-------------------------------------------------------
audio_prefetch_track | audio      |     612.43 | {"idx": 1, "path": "long-loop.flac", "result": "ok"}
await_prefetch  | audio      |     510.12 | {"cue_index": 1, "result": "timeout"}
load_playback   | visual     |     184.03 | {"playback": "heavy-video.json", "result": "ok"}
```

`theme --diag` shares the same rendering helpers but focuses on ThemeBank: it spins up the real async loader, exercises cache refill/lookahead logic, and reports spans grouped under the `themebank` and `media` categories. Use `--diag-json` + `--diag-fail` to gate CI on slow disk/decoding paths just like you would for cue playback.

Key flags:

- `--diag-cues N` — number of cues to simulate (default: 2).
- `--diag-prefetch-only` — collect data without calling `_start_cue`, ideal when you only care about prefetch behavior.
- `--diag-json` — emit the raw tracer snapshot so you can archive/parse it yourself.
- `--diag-threshold ms` + `--diag-limit N` — control which spans appear in the table.
- `--diag-fail` — exit with code `3` when any span meets/exceeds the threshold (useful for CI gates).

Diagnostics maintain a clean environment:

- The GUI never launches; a stub visual director satisfies the runner’s dependencies.
- The async audio prefetch worker is shut down cleanly between runs.
- Perf mode is enabled automatically so you don’t have to set env vars.

## Best practices

1. **Start broad, then narrow.** Run `--diag` with a generous threshold (e.g., `250 ms`) to see the overall picture, then tighten it to expose only the slowest spans.
2. **Use `--diag-prefetch-only` when audio assets change frequently.** This isolates decode latency without the noise of playback/text setup.
3. **Capture JSON for regression tracking.** The snapshot contains every span and per-category totals; storing it alongside CI artifacts makes it easy to compare runs.
4. **Monitor categories for skew.** The `categories` block sums duration per category; if `audio` dominates a cue even though playback files are cached, you likely hit the streaming fallback path.
5. **Keep perf mode off during normal play.** PerfTracer is lightweight, but the extra bookkeeping still adds a few microseconds per span—reserve it for investigations.

For deeper context on logging presets and environment flags, see `docs/technical/logging-modes.md`. To integrate diagnostics into automation, combine `--diag`, `--diag-json`, and `--diag-fail` (supported by both cuelist and theme workflows) with your preferred CI runner.
