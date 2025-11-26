# Audio Engine Documentation

## Overview
The Phase 7 audio stack centers on `AudioEngine`, a multi-channel mixer with per-cue caching, fade envelopes, and CLI/test hooks. The legacy `Audio2` helper remains for backwards compatibility but no longer drives session playback.

## AudioEngine (Phase 7+)

### Key Features
- Multi-channel playback with per-channel fade-in/out and volume automation.
- **LRU decoding cache** so multiple cues can reuse the same `pygame.mixer.Sound` buffer without blocking disk I/O.
- **Adaptive streaming fallback**: files beyond a configurable size (default 64 MB) are routed through `pygame.mixer.music` so extended hypnosis tracks no longer allocate enormous RAM chunks.
- `prefetch_tracks()` batch helper invoked by `SessionRunner` whenever the first cue is prepared or a transition target is selected. This eliminates the audible gap that previously occurred when back-to-back cues both owned audio tracks.
- `preload_sound()` utility for tests/devtools where individual files should be decoded ahead of time.

### Prefetch Flow (SessionRunner)
1. When `SessionRunner.start()` is called, **only cue `0`** is prefetched. This keeps decoded buffers focused on the active cue until we know a transition is approaching.
2. While a cue is running, `_ensure_audio_prefetch_window()` monitors the remaining duration. Once we are within `audio.prefetch_lead_seconds` (default 8 s) of ending, the next cue is prefetched so the transition stays seamless without preloading too early.
3. Manual skips and transition requests still call `_prefetch_cue_audio()` as a safety net, ensuring that even abrupt jumps have the target cue warmed if budgets permit.

Prefetch results are logged at DEBUG level (`"Prefetched X/Y audio tracks for cue"`) to aid diagnosis if a file fails to decode. A dedicated `_prefetched_cues` set prevents redundant disk hits yet is cleared whenever cues start/stop so loops can re-warm as they wrap.

### Streaming Oversized Assets


### 20 s Decoded-Buffer Budget

- Session audio now obeys a **hard 20 s decoded budget** (10 s HYPNO + 10 s BACKGROUND, 5 s for generic/legacy roles). These defaults can be overridden per session via `settings.audio.max_buffer_seconds_{hypno|background|generic}`.
- When `SessionRunner` evaluates a track it queries `AudioEngine.estimate_track_duration()` (mutagen metadata, with WAV fallback) and attempts to reserve buffer seconds for the cue. If the track would exceed its role’s budget it is automatically streamed before any decoding happens, eliminating the old “Out of memory” warnings.
- Reservations decay in real time as a cue plays. Every second of HYPNO playback frees one second of budget, allowing the runner to prefetch the next cue gradually instead of decoding four tracks at once.
- If budgets are temporarily exhausted, the cue’s prefetch is deferred and retried every frame. As soon as enough playback time has elapsed (freeing buffer seconds) the deferred cue is decoded, ensuring only the minimum media needed for seamless transitions sits in RAM.
- Operators can monitor the behaviour via DEBUG logs: look for `[session] Streaming hypno audio ... (buffer limit)` when massive files are routed through the streaming path.

### Home Tab Prefetch Buffer
- Selecting a cuelist in the Home tab's Session Runner invokes `prefetch_audio_for_cuelist()` (see `mesmerglass/session/audio_prefetch.py`). The helper now limits itself to the **first cue only** (`max_cues=1`) so selecting long playlists no longer attempts to decode every HYPNO/BACKGROUND file at once. The runtime prefetcher still prepares upcoming cues in the background as playback progresses.
- The Session Runner UI status line reports `"🎧 Prefetched X/Y audio tracks"` so operators know the cache is ready before pressing **Start**.
- Both the GUI warm-up and the runtime lead window rely on the same helper utilities, ensuring CLI sessions and automated tests share identical caching semantics.

### Asynchronous Prefetch Queue (Phase 7.6)
- The runtime SessionRunner now owns an `AudioPrefetchWorker`, which serializes `pygame.mixer.Sound` decoding onto a background `ThreadPoolExecutor`. `_prefetch_cue_audio()` reserves buffer budgets synchronously but immediately hands the heavy decode to the worker so the render loop never blocks when cues transition.
- Completed jobs are harvested each frame via `_process_completed_prefetch_jobs()`. Once every required track for a cue finishes, the cue is marked pre-warmed and `_prefetch_backlog` entries are cleared. Failures automatically release buffer reservations and trigger a retry once the budget frees up.
- Instrumentation: any decode (async or sync fallback) that exceeds **40 ms** logs a `[perf]` warning with the cue index/file name so you can correlate pauses with large assets. Streaming starts get the same treatment, surfacing slow network paths.
- Slow decode telemetry builds on this by capturing the full job runtime and comparing it against `slow_decode_stream_ms`. When exceeded, the runner logs the threshold breach and AudioEngine marks the asset for streaming so the UI thread never blocks on it again.
- Safety: Bootstrap prefetch for cue `0` still runs synchronously so the opening cue never races the worker. Manual skips/lead-window prefetch all happen asynchronously, so transitions stay smooth even when the HYPNO track is large.
- Worker lifecycle is fully covered by `test_audio_integration.py::test_audio_prefetch_worker_reports_results` and `test_session_runner.py::TestAsyncAudioPrefetch`, ensuring both the queue and the fallback path behave deterministically in CI.
- Cue start guard: when a transition fires, `_await_cue_audio_ready()` gives the worker up to `settings.audio.prefetch_block_limit_ms` (default **150 ms**) to finish decoding before the runner falls back to streaming. This lightweight wait loops alongside `_process_completed_prefetch_jobs()` so completions are applied immediately without freezing the Qt event loop.
- If the wait expires or a cue’s buffer budget forces streaming, the SESSION log spells out the reason (e.g., `prefetch pending` vs. `buffer limit`) and the reservation is surrendered to avoid hoarding RAM for a track that is now streaming anyway.

### Cache Behaviour
- Default cache size: 16 decoded sounds (configurable in `AudioEngine._cache_limit`). Older entries are evicted LRU-style when the limit is exceeded.
- Paths are normalized (`Path.resolve()`) before caching, preventing duplicate cache rows for relative vs. absolute paths.
- Length metadata (from `Sound.get_length()`) is stored alongside the buffer so UI components can display approximate durations without re-opening the file.

### Manual QA Checklist
1. Build a cuelist with two cues, each containing HYPNO + BACKGROUND layers.
2. Run the session and observe the transition boundary between cue 1 → cue 2. Audio should remain continuous—no silent gap while the second cue starts.
3. Repeat while repeatedly skipping forward/back via the session toolbar. Prefetch logging should show up for every target cue, and no extra clicking should be audible.

## Legacy Components (Audio2 helper)

> **Note:** The `Audio2` class below is kept for tooling and legacy scripts. The production session runner exclusively uses `AudioEngine`.

### 1. Audio Player
```python
from mesmerglass.engine.audio import Audio2

# Example usage
player = Audio2()
player.load_track(1, "music.mp3")
player.set_volume(1, 0.75)  # 75% volume
player.play(1)
```

#### Supported Formats
- MP3 (recommended)
- WAV
- OGG

### 2. Dual Track System

#### Track Management
- Independent volume control
- Synchronized playback
- Loop control
- Individual track states

```python
class Audio2:
    def __init__(self):
        """Initialize dual-track audio system"""
        pygame.mixer.init()
        self.tracks = {1: None, 2: None}
        self.volumes = {1: 1.0, 2: 1.0}
```

### 3. Mixing Features

#### Volume Control
```python
def set_volume(self, track: int, level: float):
    """Set volume for specified track (0.0 - 1.0)"""
    if track in self.tracks and self.tracks[track]:
        self.volumes[track] = clamp(level, 0.0, 1.0)
        self.tracks[track].set_volume(self.volumes[track])
```

#### Playback Control
```python
def play(self, track: int, loop: bool = True):
    """Start playback of specified track"""
    if track in self.tracks and self.tracks[track]:
        self.tracks[track].play(-1 if loop else 0)

def stop(self, track: int):
    """Stop playback of specified track"""
    if track in self.tracks and self.tracks[track]:
        self.tracks[track].stop()
```

## Technical Details (Legacy Audio2)

### Memory Management

#### Loading Strategy
```python
def load_track(self, track: int, filepath: str):
    """Load audio file into specified track"""
    if track in self.tracks:
        # Clean up existing
        if self.tracks[track]:
            self.tracks[track].stop()
            self.tracks[track] = None
            
        # Load new track
        try:
            self.tracks[track] = pygame.mixer.Sound(filepath)
            self.set_volume(track, self.volumes[track])
        except Exception as e:
            logger.error(f"Failed to load audio: {e}")
```

### Error Handling

#### Common Issues
1. File format compatibility
2. Memory constraints
3. Device availability
4. Playback synchronization

#### Recovery Strategies
```python
def ensure_mixer_ready(self):
    """Ensure pygame mixer is initialized"""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except pygame.error:
            logger.error("Failed to initialize audio")
            return False
    return True
```

## Performance Optimization

### Memory Usage
- Efficient audio loading
- Resource cleanup
- Buffer management

### System Integration
- Device selection
- Format conversion
- Stream management

## Testing

### Unit Tests
```python
def test_audio_loading():
    player = Audio2()
    assert player.load_track(1, "test.mp3")
    assert player.tracks[1] is not None

def test_volume_control():
    player = Audio2()
    player.load_track(1, "test.mp3")
    player.set_volume(1, 0.5)
    assert abs(player.volumes[1] - 0.5) < 0.001
```

### Integration Tests
- Track synchronization
- Memory management
- Device handling
- Format support

## API Reference

### Audio2 Class
```python
class Audio2:
    def __init__(self):
        """Initialize audio system"""
        
    def load_track(self, track: int, filepath: str) -> bool:
        """Load audio file into specified track"""
        
    def play(self, track: int, loop: bool = True):
        """Start playback of specified track"""
        
    def stop(self, track: int):
        """Stop playback of specified track"""
        
    def set_volume(self, track: int, level: float):
        """Set volume for specified track"""
        
    def cleanup(self):
        """Release all resources"""
```

## Best Practices

### File Formats
- Use MP3 for best compatibility
- Convert WAV to MP3 for memory efficiency
- Test OGG support on target platform

### Memory Management
- Unload unused tracks
- Monitor memory usage
- Clean up resources properly

### Error Handling
- Validate audio files
- Handle device errors gracefully
- Provide user feedback
