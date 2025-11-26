# Theme & Image Cache Parameters

This note captures every knob that influences how many images MesmerGlass keeps in RAM, how aggressively it preloads, and how to tune those values without hunting through the codebase.

## Memory Math Cheat Sheet

- Images are stored in RGBA `uint8` buffers before GPU upload: `bytes = width * height * 4`.
- Quick conversions:
  - 1920×1080 (2.1 MP) → ~8.3 MB per cached frame.
  - 2560×1440 (3.7 MP) → ~14.2 MB.
  - 3840×2160 (8.3 MP) → ~33.2 MB.
- Approximate RAM footprint = `cache_entries_per_theme * avg_image_bytes * active_themes`.

Combine this with `docs/technical/media-pool-recommendations.md` when choosing pool sizes.

## Primary Cache Budget

| Parameter | Default | Current GUI value | Location | What it does | How to edit |
|-----------|---------|-------------------|----------|--------------|-------------|
| `ThemeBank(image_cache_size)` | 64 | **256** (`MainApplication` constructor) | `mesmerglass/content/themebank.py` & `mesmerglass/ui/main_application.py` | Total decoded-image budget shared across enabled themes. `_cache_per_theme()` splits it evenly unless only one theme is active. | Edit the literal in `MainApplication` (look for `ThemeBank(..., image_cache_size=256)`). CLI diagnostics can override via `--diag-cache-size` inside `python -m mesmerglass theme --diag ...`.
| `_cache_per_theme()` | Derived | Derived | `mesmerglass/content/themebank.py` | Splits `image_cache_size` equally across enabled themes but never exceeds each theme's asset count. | Adjust logic if you ever want weighted splits (e.g., based on pool size). |
| `_preload_aggressively` | `False` | `False` unless `MESMERGLASS_THEME_PRELOAD_ALL=1` | `mesmerglass/content/themebank.py` | When `True`, `_preload_theme_images()` attempts to fill each per-theme cache immediately; when `False`, only the first `min(15, cache_size)` items are queued and the rest rely on lookahead. | Toggle via env/CLI (see **Env & CLI Overrides**). |
| `LAST_IMAGE_COUNT` | 100 | 100 | `mesmerglass/content/themebank.py` | Size of the "recently used" deque that prevents repeats. Larger numbers avoid repeats but require more bookkeeping (negligible RAM). | Change constant if you need a longer no-repeat horizon. |
| `_cache_refill_interval` | 5 frames | 5 frames | `mesmerglass/content/themebank.py` | How often `async_update()` calls `_refill_hot_cache()` (currently a no-op but kept for compatibility). | Adjust only if you revive the legacy hot cache. |
| `_gc_interval` | 50 evictions | 50 | `mesmerglass/content/themebank.py` | Triggers `gc.collect()` every 50 evictions to recover Python heap after large image churn. | Bump up if collections become too frequent. |

## Lookahead & Background Preload

`ThemeBankThrottleConfig` (same file) centralizes the async loader knobs. Defaults come from the dataclass fields and can be overridden via environment or (for CLI `run`) the matching flags.

| Field | Default | Purpose | Notes |
|-------|---------|---------|-------|
| `lookahead_count` | 32 | How many *future* indices `shuffler.peek_next()` returns per trigger. Caps the theoretical preload horizon. |
| `lookahead_batch_size` | 12 | Maximum images decoded per background batch (even if lookahead queue is larger). Keeps burst memory usage bounded. |
| `lookahead_sleep_ms` | 4.0 ms | Sleep inserted between background image decodes. Raises this to reduce I/O pressure; lower it for faster warmups. |
| `max_preload_ms` | 200 ms | Hard stop for a single background batch; if exceeded, the preload thread yields. Prevents runaway CPU/RAM spikes. |
| `loader_queue_size` | 8 | Passed straight into each `ImageCache` → `AsyncImageLoader(max_queue_size=loader_queue_size)`. This is the pending decode queue per theme. |
| `sync_warning_ms` | 45 ms | If a synchronous fallback decode (cache miss) exceeds this, ThemeBank logs a warning. Not memory, but useful when tuning queue sizes. |
| `background_warning_ms` | 150 ms | Similar warning threshold for background batches. |
| `preload_aggressively` | `False` | Mirrors `_preload_aggressively` (see above). |

Runtime copies inside `ThemeBank`:

- `_lookahead_interval = 1` (run lookahead every `get_image` call).
- `_lookahead_sleep_sec = lookahead_sleep_ms / 1000`.
- `_preload_initial_lookahead()` preloads `min(lookahead_count, lookahead_batch_size)` items at startup when aggressive preloading is enabled.

## ImageCache Internals (`mesmerglass/content/media.py`)

| Component | Default | Details | Memory Considerations |
|-----------|---------|---------|-----------------------|
| `ImageCache(cache_size)` | Provided by ThemeBank | LRU cache storing `CachedImage(image_data, gpu_texture_id, last_used)`. RAM usage is dominated by `image_data`. | Expect roughly `cache_size * avg_image_bytes`. |
| `AsyncImageLoader(max_queue_size)` | `loader_queue_size` (default 8) | Queue of pending decode requests per theme. Each queued image allocates RAM only after decode completes. | Large queues can spike disk usage but images only consume RAM post-decode. |
| `preload_images(max_count)` | `min(15, cache_size)` when not aggressive | Called during `_preload_theme_images()`. When `preload_aggressively=True`, `max_count=cache_size` so every slot is filled immediately. |
| Eviction path | LRU + optional GPU cleanup | When cache is full, `get_image`/background preloads evict least recently used entries and delete GPU textures (if any). | Keeps RAM capped at `cache_size`, but note that each theme owns its own `ImageCache` instance. |

## Video Buffers & Streamers

Video memory lives outside ThemeBank but still contributes to overall RAM usage, especially when looping GIFs or buffering MP4/WebM clips.

| Component | Default | Location | Behavior | Memory Impact / Tuning |
|-----------|---------|----------|----------|------------------------|
| `VideoStreamer(buffer_size)` | 120 frames **per buffer** | `mesmerglass/content/video.py` | Maintains two `AnimationBuffer`s (A/B) so one can stream ahead while the other plays. 120 frames ≈ 2 s @ 60 fps. | RAM per buffer ≈ `buffer_size * width * height * 3 bytes`. Doubled because of ping-pong buffers. Lower `buffer_size` or downscale media if RAM is tight. |
| `SimpleVideoStreamer(buffer_size)` | 120 frames | `mesmerglass/content/simple_video_streamer.py` | Forward-only wrapper around `VideoStreamer`; still allocates the same double buffer internally. | Change the constructor default if you want a lighter forward-only loop. |
| GIF caching | Entire file resident | `VideoDecoder._load_gif` | Every frame is decoded up front and stored in `gif_frames` (list of RGB numpy arrays). | RAM ≈ `frame_count * width * height * 3`. Prefer MP4/WebM for large clips if you can’t afford the full cost. |
| MP4/WebM streaming | Streamed from disk | `VideoDecoder._open_video` | `cv2.VideoCapture` streams from disk; only buffered frames live in memory. | RAM driven purely by `buffer_size`. |
| Loader thread | 1 thread | `VideoStreamer._start_loader_thread` | Background thread keeps the “next” buffer warm. | CPU-only, but be aware simultaneous high-res videos means two buffers of RGB data in RAM. |

**Video math example**: A 2560×1440 MP4 at default settings consumes `2560*1440*3 ≈ 11.1 MB` per frame. With 120 frames × 2 buffers ≈ `2.7 GB`, so you must lower resolution/buffer_size or rely on GIF (which is even larger) only for tiny loops.

There is no CLI override today; edit the constructors where you instantiate `VideoStreamer`/`SimpleVideoStreamer` (search for `buffer_size=`) to adjust the buffering budget globally.

## Audio Buffers & Streaming

Audio uses a mix of decoded-sample caches and streaming fallbacks to cap RAM while keeping cue transitions gapless.

### Runtime budgets (`mesmerglass/session/runner.py`)

| Setting | Default | Source | Effect | How to change |
|---------|---------|--------|--------|---------------|
| `audio.prefetch_lead_seconds` | 8 s | Session settings → `_resolve_audio_prefetch_lead` | When remaining cue time ≤ lead window, the next cue’s audio prefetch starts. | Edit session JSON (`settings.audio.prefetch_lead_seconds`) or expose a GUI control. |
| `audio.prefetch_block_limit_ms` | 150 ms (clamped 20–500) | `_resolve_audio_prefetch_block_limit` | Maximum time `_await_cue_audio_ready()` will wait for async decode before falling back to streaming. | Session setting `prefetch_block_limit_ms`. |
| `audio.stream_threshold_mb` | 64 MB (0 disables) | `_resolve_audio_stream_threshold` → `AudioEngine.set_stream_threshold_mb` | Files at/above threshold skip decoding and stream via `pygame.mixer.music`. | Session setting `stream_threshold_mb` or call `AudioEngine.set_stream_threshold_mb`. |
| `audio.slow_decode_stream_ms` | 350 ms (cap 2000) | `_resolve_slow_decode_stream_threshold` | Any decode taking longer than this forces future playback to stream. | Session setting `slow_decode_stream_ms` or `AudioEngine.set_slow_decode_threshold_ms`. |
| `max_buffer_seconds_{role}` | HYPNO 10 s, BACKGROUND 10 s, GENERIC 5 s | `_resolve_audio_buffer_limits` | Per-role decoded duration budget. Beyond it, cues defer or stream. | Session fields `max_buffer_seconds_hypno/background/generic` or nested `max_buffer_seconds` dict. |

### AudioEngine caches (`mesmerglass/engine/audio.py`)

| Component | Default | Details | Tuning |
|-----------|---------|---------|--------|
| `_cache_limit` | 16 decoded sounds | OrderedDict of `pygame.mixer.Sound` objects shared across channels. Evicts LRU when limit exceeded. | Increase for more reuse at cost of RAM; edit the literal inside `AudioEngine.__init__`. |
| Streaming threshold | 64 MB | `_stream_threshold_bytes` triggers streaming instead of caching. | Adjust via `set_stream_threshold_mb()` or session `stream_threshold_mb`. |
| Slow-decode detector | 0 ms disabled / 350 ms default via session | `_slow_decode_threshold_ms`; if decode exceeds, path is added to `_forced_stream_paths`. | Use `set_slow_decode_threshold_ms()` or `settings.audio.slow_decode_stream_ms`. |
| Forced-stream set | Empty by default | `_forced_stream_paths` keeps assets that previously OOM’d. | `force_stream_for_path()` helper + CLI tests can seed it. |
| Duration cache | Cached per path | `_duration_cache` avoids re-opening files to estimate lengths during budget math. | Automatically maintained; no tuning needed. |

### Prefetch worker (`mesmerglass/session/audio_prefetch_worker.py`)

- `AudioPrefetchWorker` owns a `ThreadPoolExecutor(max_workers=1)` so only one heavy decode runs at a time; additional jobs queue in `_pending`.
- `PrefetchJob` tracks cue index + role; `pending_for_cue()`/`wait_for_cues()` let the runner block briefly (`prefetch_block_limit_ms`) before falling back to streaming.
- Completed results are drained each frame via `_process_completed_prefetch_jobs()` so decoded buffers attach to cues as soon as RAM budgets allow.

When tuning audio memory:
1. Lower the per-role buffer seconds if you need a smaller decoded footprint (e.g., HYPNO 6 s). The runner automatically streams longer tracks.
2. Drop `stream_threshold_mb` to stream more files regardless of duration.
3. Increase `_cache_limit` cautiously if you reuse many short clips and have spare RAM.
4. Watch logs for `[perf] SLOW sync load` or `[session] Streaming hypno audio ... (buffer limit)` to confirm the budgets you set are actually being enforced.

## Env & CLI Overrides

`python -m mesmerglass run` exposes switches that map directly to env vars consumed by `ThemeBankThrottleConfig.from_env()`:

| CLI Flag | Env Var | Affects |
|----------|---------|---------|
| `--theme-lookahead <N>` | `MESMERGLASS_THEME_LOOKAHEAD` | `lookahead_count` |
| `--theme-batch <N>` | `MESMERGLASS_THEME_BATCH` | `lookahead_batch_size` |
| `--theme-sleep-ms <MS>` | `MESMERGLASS_THEME_SLEEP_MS` | `lookahead_sleep_ms` |
| `--theme-max-ms <MS>` | `MESMERGLASS_THEME_MAX_MS` | `max_preload_ms` |
| `--media-queue <N>` | `MESMERGLASS_MEDIA_QUEUE` | `loader_queue_size` |
| `--theme-preload-all` | `MESMERGLASS_THEME_PRELOAD_ALL=1` | Enables `_preload_aggressively` |
| `--theme-no-preload` | `MESMERGLASS_THEME_PRELOAD_ALL=0` | Forces conservative preload |

For non-CLI launches (e.g., double-clicking `run.py`), set the environment variables before starting Python to achieve the same effect.

## Where to Change Defaults Later

1. **Global GUI cache size**: edit `mesmerglass/ui/main_application.py` (search for `ThemeBank(`). This is the only place the Phase 7 UI passes `image_cache_size=256`.
2. **CLI/automation runs**: `mesmerglass/cli.py` already wires the flags above—no code change needed, but keep `docs/cli.md` updated if you add new ones.
3. **Throttle defaults**: adjust the dataclass literals at the top of `mesmerglass/content/themebank.py` if you want new baseline behavior for everyone.
4. **Per-test overrides**: tests such as `mesmerglass/tests/test_playback_pool_visual.py` hardcode smaller caches (e.g., `image_cache_size=10`). Update them if new defaults would break assumptions.

## Validation Workflow

- Use `python -m mesmerglass theme --load <themes.json> --diag --diag-cache-size <N>` to inspect how different budgets behave. Set `--diag-json` for machine-readable perf spans.
- For the live GUI, run `python -m mesmerglass run --theme-lookahead 16 --theme-batch 8 ...` and monitor logs at `INFO` (ThemeBank prints cache fill stats every 2 seconds).
- Pair these tweaks with `docs/technical/media-pool-recommendations.md` to ensure your media libraries stay within RAM budgets.

With this map, future edits just require updating the values in the files listed above and re-running the CLI diagnostics to confirm smooth cycling.
