# Audio Prefetch Lag (Phase 7.7)

## Summary
Cue transitions that included HYPNO/BACKGROUND audio were pausing for 1.5‑2.0 seconds even though the frame budget stayed under 16 ms. The stall happened because `_start_cue()` still executed synchronous `pygame.mixer.Sound` decodes whenever the async worker had not finished when the transition fired, and we had no guardrails to detect extremely slow decodes caused by giant WAV assets.

## Root Cause
- `_prefetch_cue_audio()` correctly submitted decode jobs to `AudioPrefetchWorker`, but `_start_cue()` disregarded outstanding jobs and immediately called `load_channel()`, forcing a blocking decode on the render thread.
- The runner also lacked any ability to briefly wait for the worker to finish, so even when a job was milliseconds from completion we still performed the expensive sync path.

## Fix
1. Added `AudioPrefetchWorker.pending_for_cue()` plus `wait_for_cues()` so the runner can query/await specific jobs without draining completions.
2. Introduced `_await_cue_audio_ready()` in `SessionRunner`, which processes worker completions while giving the queue up to `settings.audio.prefetch_block_limit_ms` (default 150 ms) to finish decoding before falling back to streaming.
3. When the wait expires, the runner now streams affected tracks (and releases their buffer reservations) instead of triggering another full decode on the UI thread.
4. AudioEngine now measures every decode and permanently forces any asset whose decode exceeds `settings.audio.slow_decode_stream_ms` (default 350 ms) into streaming mode. The runner logs when prefetch jobs cross this threshold so operators can spot problem files immediately.
5. Added regression tests:
   - `test_audio_integration.py::test_audio_prefetch_worker_wait_for_cue_completion` ensures worker waits converge.
   - `test_session_runner.py::TestSessionRunnerAudioPrefetch` verifies the new guard waits and times out deterministically.
6. Transitions now keep audio prefetch asynchronous—`_request_transition()` still forces a refresh but allows the worker to handle it, so cue changes no longer block the render thread. A new regression test locks this behavior in.
7. Streaming start moved off the render thread via `AudioEngine.play_streaming_track_async()`. SessionRunner now queues large WAV loads onto the streaming worker, tracks handles per role, and polls them every frame, so the 1.7 s stall no longer freezes visuals even when streaming is unavoidable.
8. Added a streaming-worker warmup (`AudioEngine.ensure_stream_worker_ready`) and blocking-operation instrumentation around playback bootstrap/stream fallbacks so the opening cue never spends hundreds of milliseconds spawning threads, and frame spike summaries now pinpoint the exact cause instead of reporting “unknown”.

## Verification
- Manual: run the "Multi Test" cuelist with audio layers; cue transitions now stay under ~150 ms and the `[session] Prefetch latency ... slow-decode threshold` warning appears exactly once per offending WAV before it switches to streaming.
- Automated: `./.venv/bin/python -m pytest mesmerglass/tests/test_audio_integration.py mesmerglass/tests/test_session_runner.py -k prefetch`.
