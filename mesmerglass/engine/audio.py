# mesmerglass/engine/audio.py
import contextlib
import wave
import pygame
import logging
import os
import time
import threading
import numpy as np
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from pathlib import Path
from collections import OrderedDict
from threading import Lock
from typing import Optional, Iterable, Tuple
from typing import Any

def clamp(x, a, b): return max(a, min(b, x))

class Audio2:
    """
    - Audio 1: tries Sound; on failure falls back to streamed music (pygame.mixer.music)
    - Audio 2: Sound only (for layering a small loop over the streamed track)
    """
    def __init__(self):
        self.init_ok = False
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self.init_ok = True
            logging.getLogger(__name__).info("pygame mixer initialized")
        except Exception as e:
            logging.getLogger(__name__).error("audio init failed: %s", e)
            return
        # Initialize state after successful (or failed) init attempt so callers
        # can still inspect attributes even if init_ok is False.
        self.snd1 = None
        self.snd2 = None
        self.chan1 = None
        self.chan2 = None
        self.music1_path: str | None = None   # streaming fallback
        self.snd1_path: str | None = None
        self.snd2_path: str | None = None

    # -------- loading --------------------------------------------------------
    def load1(self, path: str):
        if not self.init_ok: return
        self.snd1 = None
        self.snd1_path = None
        self.music1_path = None
        try:
            self.snd1 = pygame.mixer.Sound(path)  # full load
            self.snd1_path = path
        except Exception as e:
            logging.getLogger(__name__).warning("load1 error: %s — falling back to streaming", e)
            # streaming fallback (uses global music channel)
            self.music1_path = path

    def load2(self, path: str):
        if not self.init_ok: return
        try:
            self.snd2 = pygame.mixer.Sound(path)
            self.snd2_path = path
        except Exception as e:
            logging.getLogger(__name__).error("load2 error: %s", e)
            self.snd2 = None
            self.snd2_path = None

    # -------- playback -------------------------------------------------------
    def play(self, vol1=0.5, vol2=0.5):
        if not self.init_ok: return

        # Audio 1
        if self.music1_path:
            try:
                pygame.mixer.music.load(self.music1_path)
                pygame.mixer.music.set_volume(clamp(vol1, 0, 1))
                pygame.mixer.music.play(loops=-1)
            except Exception as e:
                logging.getLogger(__name__).error("music play error: %s", e)
        elif self.snd1 and not self.chan1:
            self.chan1 = self.snd1.play(loops=-1)
            if self.chan1:
                self.chan1.set_volume(clamp(vol1, 0, 1))

        # Audio 2
        if self.snd2 and not self.chan2:
            self.chan2 = self.snd2.play(loops=-1)
            if self.chan2:
                self.chan2.set_volume(clamp(vol2, 0, 1))

    def stop(self):
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass
        if self.chan1:
            self.chan1.stop(); self.chan1 = None
        if self.chan2:
            self.chan2.stop(); self.chan2 = None

    def set_vols(self, v1, v2):
        v1 = clamp(v1, 0, 1); v2 = clamp(v2, 0, 1)
        if self.music1_path:
            # streamed track
            try:
                pygame.mixer.music.set_volume(v1)
            except Exception:
                pass
        elif self.chan1:
            self.chan1.set_volume(v1)
        if self.chan2:
            self.chan2.set_volume(v2)

    # -------- performance helpers -----------------------------------------
    def memory_usage_bytes(self) -> dict:
        """Approximate memory footprint of loaded audio assets.

        For fully loaded sounds we use file size as a proxy (decoded size may be
        larger, but this keeps implementation lightweight). For streaming track
        we return None bytes and flag streaming True.
        """
        def _size(p: str | None):
            if not p: return None
            try: return os.path.getsize(p)
            except Exception: return None
        return {
            "audio1_bytes": _size(self.snd1_path),
            "audio2_bytes": _size(self.snd2_path),
            "audio1_streaming": bool(self.music1_path is not None),
        }

@dataclass
class StreamingHandle:
    """Tracks async streaming start jobs so callers can poll completion."""

    file_path: str
    volume: float
    fade_ms: float
    loop: bool
    submitted_at: float = field(default_factory=time.perf_counter)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: Optional[Future] = None

    def done(self) -> bool:
        return bool(self.future and self.future.done())


# ============================================================================
# AudioEngine - Multi-channel audio system with fade support for cuelist system
# ============================================================================

class AudioEngine:
    """
    Multi-channel audio engine for cuelist session playback.
    
    Features:
    - Multiple independent audio channels (default: 2)
    - Per-channel fade in/out with configurable durations
    - Per-channel volume control and loop support
    - Handles pygame.mixer Sound objects with channel management
    
    Usage:
        engine = AudioEngine(num_channels=2)
        engine.load_channel(0, "path/to/audio.mp3")
        engine.fade_in_and_play(0, fade_ms=1000, volume=0.8, loop=True)
        engine.fade_out_and_stop(0, fade_ms=500)
    """
    
    def __init__(self, num_channels: int = 2):
        """
        Initialize AudioEngine with specified number of channels.
        
        Args:
            num_channels: Number of independent audio channels (default: 2)
        """
        self.logger = logging.getLogger(__name__)
        self.num_channels = num_channels
        self.init_ok = False
        
        # Initialize pygame mixer if not already initialized
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init()
            self.init_ok = True
            self.logger.info(f"AudioEngine initialized with {num_channels} channels")
        except Exception as e:
            self.logger.error(f"AudioEngine init failed: {e}")
            
        # Per-channel state
        self._sounds = [None] * num_channels       # pygame.mixer.Sound objects
        self._channels = [None] * num_channels     # pygame.mixer.Channel objects (active playback)
        self._paths = [None] * num_channels        # Loaded file paths
        self._volumes = [1.0] * num_channels       # Target volumes
        self._looping = [False] * num_channels     # Loop state
        self._fading_in = [False] * num_channels   # Fade-in active
        self._fading_out = [False] * num_channels  # Fade-out active
        self._lengths = [0.0] * num_channels       # Cached duration (seconds) for loaded audio
        # Shared cache so repeated cues reuse decoded buffers and avoid load stalls
        self._sound_cache: OrderedDict[str, pygame.mixer.Sound] = OrderedDict()
        self._length_cache: dict[str, float] = {}
        self._cache_lock = Lock()
        self._load_lock = Lock()
        self._cache_limit = 16  # Keep recent sounds in memory (tweakable)

        # Streaming (pygame.mixer.music) configuration/state
        self._streaming_enabled = True
        self._stream_threshold_bytes = 64 * 1024 * 1024  # Default: 64 MB
        self._streaming_path: Optional[str] = None
        self._streaming_loop = False
        self._streaming_active = False
        # Tracks assets that must stream even if below threshold (e.g. pygame OOM)
        self._forced_stream_paths: set[str] = set()
        self._duration_cache: dict[str, float] = {}
        self._slow_decode_threshold_ms = 0.0
        self._decode_time_ms: dict[str, float] = {}
        self._stream_executor: Optional[ThreadPoolExecutor] = None
        self._paused = False

    def _normalize_path(self, file_path: str) -> str:
        """Return absolute string path for caching consistency."""
        try:
            return str(Path(file_path).resolve())
        except Exception:
            return str(file_path)

    def _add_to_cache(self, normalized: str, sound: 'pygame.mixer.Sound', length: float) -> None:
        """LRU insert for decoded sound buffers (thread-safe)."""
        with self._cache_lock:
            self._sound_cache[normalized] = sound
            self._length_cache[normalized] = length
            self._sound_cache.move_to_end(normalized)
            while len(self._sound_cache) > self._cache_limit:
                old_path, _ = self._sound_cache.popitem(last=False)
                self._length_cache.pop(old_path, None)

    def _get_cached_sound(self, normalized: str) -> Tuple[Optional['pygame.mixer.Sound'], float]:
        with self._cache_lock:
            sound = self._sound_cache.get(normalized)
            if sound:
                self._sound_cache.move_to_end(normalized)
                return sound, self._length_cache.get(normalized, 0.0)
        return None, 0.0

    def _get_or_load_sound(self, file_path: str) -> tuple[Optional['pygame.mixer.Sound'], float]:
        """Return cached pygame Sound or load/insert into cache."""
        if not self.init_ok:
            return None, 0.0

        normalized = self._normalize_path(file_path)
        if normalized in self._forced_stream_paths:
            return None, 0.0
        sound, cached_length = self._get_cached_sound(normalized)
        if sound:
            return sound, cached_length

        try:
            decode_start = time.perf_counter()
            with self._load_lock:
                sound = pygame.mixer.Sound(normalized)
            elapsed_ms = (time.perf_counter() - decode_start) * 1000.0
            length = float(sound.get_length() or 0.0)
            self._decode_time_ms[normalized] = elapsed_ms
            slow_decode = (
                self._slow_decode_threshold_ms > 0.0
                and elapsed_ms >= self._slow_decode_threshold_ms
            )
            if slow_decode:
                self.force_stream_for_path(normalized)
                self.logger.warning(
                    "Audio decode for %s took %.0fms; switching to streaming",
                    os.path.basename(file_path),
                    elapsed_ms,
                )
            else:
                self._add_to_cache(normalized, sound, length)
            self._duration_cache[normalized] = length
            return sound, length
        except Exception as e:
            if self._should_force_stream(e):
                self._forced_stream_paths.add(normalized)
                self.logger.warning(
                    "Failed to load audio '%s': %s — marking for streaming fallback",
                    file_path,
                    e,
                )
            else:
                self.logger.error(f"Failed to load audio '{file_path}': {e}")
            return None, 0.0

    # === Streaming configuration/helpers ===

    def set_stream_threshold_mb(self, value: Optional[float]) -> None:
        """Configure the file-size threshold (in MB) that triggers streaming."""
        if value is None:
            return
        if value <= 0:
            self._streaming_enabled = False
            self.logger.info("AudioEngine streaming disabled (threshold <= 0)")
            return
        self._streaming_enabled = True
        self._stream_threshold_bytes = int(value * 1024 * 1024)
        self.logger.info(
            "AudioEngine streaming threshold set to %.1f MB",
            self._stream_threshold_bytes / (1024 * 1024)
        )

    def set_slow_decode_threshold_ms(self, value: Optional[float]) -> None:
        """Force streaming for assets whose decode takes longer than value milliseconds."""
        try:
            threshold = float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            threshold = 0.0
        if threshold <= 0.0:
            if self._slow_decode_threshold_ms > 0.0:
                self.logger.info("AudioEngine slow decode streaming disabled")
            self._slow_decode_threshold_ms = 0.0
            return
        self._slow_decode_threshold_ms = threshold
        self.logger.info(
            "AudioEngine slow decode threshold set to %.0fms",
            self._slow_decode_threshold_ms,
        )

    def get_last_decode_time_ms(self, file_path: str) -> Optional[float]:
        """Return the most recent decode duration for a path, if known."""
        normalized = self._normalize_path(file_path)
        return self._decode_time_ms.get(normalized)

    def _get_file_size(self, file_path: str) -> Optional[int]:
        try:
            return os.path.getsize(file_path)
        except OSError:
            return None

    def should_stream(self, file_path: str) -> bool:
        """Return True if the file should be streamed instead of fully cached."""
        normalized = self._normalize_path(file_path)
        if normalized in self._forced_stream_paths:
            return True
        if not self._streaming_enabled:
            return False

        # Compressed music-like formats can take a long time to fully decode via
        # pygame.mixer.Sound (observed multi-second stalls). Prefer streaming
        # for these to keep the render/update loop smooth.
        try:
            ext = Path(normalized).suffix.lower()
        except Exception:
            ext = ""
        stream_compressed = os.environ.get("MESMERGLASS_AUDIO_STREAM_COMPRESSED", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if stream_compressed and ext in {".mp3", ".m4a", ".aac"}:
            return True

        size = self._get_file_size(file_path)
        if size is None:
            return False
        return size >= self._stream_threshold_bytes

    def force_stream_for_path(self, file_path: str) -> None:
        """Testing hook: manually mark a file to always stream."""
        self._forced_stream_paths.add(self._normalize_path(file_path))

    def was_stream_forced(self, file_path: str) -> bool:
        """Return True if the path previously triggered a forced streaming fallback."""
        return self._normalize_path(file_path) in self._forced_stream_paths

    def _should_force_stream(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return isinstance(exc, MemoryError) or "out of memory" in message or "not enough memory" in message

    def _validate_streamable_path(self, file_path: str) -> bool:
        try:
            return os.path.isfile(file_path)
        except OSError:
            return False

    def _start_streaming_track_sync(
        self,
        file_path: str,
        *,
        volume: float = 1.0,
        fade_ms: float = 500,
        loop: bool = False,
    ) -> bool:
        """Internal helper that performs the blocking pygame streaming load."""
        if not self.init_ok:
            return False
        if not self._validate_streamable_path(file_path):
            self.logger.error("Streaming track missing or inaccessible: %s", file_path)
            return False

        try:
            normalized = self._normalize_path(file_path)
            pygame.mixer.music.load(normalized)
            pygame.mixer.music.set_volume(clamp(volume, 0.0, 1.0))
            fade_ms = max(0, int(fade_ms))
            loops = -1 if loop else 0
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
            self._streaming_path = normalized
            self._streaming_loop = loop
            self._streaming_active = True
            self.logger.debug("Streaming playback started: %s (loop=%s)", os.path.basename(file_path), loop)
            return True
        except Exception as exc:
            self.logger.error("Failed to stream audio '%s': %s", file_path, exc)
            self._streaming_path = None
            self._streaming_active = False
            return False

    def _ensure_stream_executor(self) -> None:
        if self._stream_executor is None:
            self._stream_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="audio-stream",
            )

    def ensure_stream_worker_ready(self) -> None:
        """Warm up the streaming executor so first-cue playback doesn't spawn threads."""
        if not self.init_ok:
            return
        if self._stream_executor is not None:
            return
        self._ensure_stream_executor()
        if not self._stream_executor:
            return
        future = self._stream_executor.submit(lambda: None)
        try:
            future.result(timeout=1.0)
        except Exception:
            pass

    def _streaming_task(self, handle: StreamingHandle) -> dict[str, Any]:
        if handle.cancel_event.is_set():
            return {"success": False, "elapsed_ms": 0.0, "cancelled": True}
        start = time.perf_counter()
        success = self._start_streaming_track_sync(
            handle.file_path,
            volume=handle.volume,
            fade_ms=handle.fade_ms,
            loop=handle.loop,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {"success": success, "elapsed_ms": elapsed_ms, "cancelled": False}

    def play_streaming_track(
        self,
        file_path: str,
        *,
        volume: float = 1.0,
        fade_ms: float = 500,
        loop: bool = False,
    ) -> bool:
        """Play large files via pygame.mixer.music streaming pipeline."""
        return self._start_streaming_track_sync(
            file_path,
            volume=volume,
            fade_ms=fade_ms,
            loop=loop,
        )

    def play_streaming_track_async(
        self,
        file_path: str,
        *,
        volume: float = 1.0,
        fade_ms: float = 500,
        loop: bool = False,
    ) -> Optional[StreamingHandle]:
        """Schedule streaming start on a worker so UI thread stays responsive."""
        if not self.init_ok:
            return None
        normalized = self._normalize_path(file_path)
        if not self._validate_streamable_path(normalized):
            self.logger.error("Streaming track missing or inaccessible: %s", normalized)
            return None
        self._ensure_stream_executor()
        handle = StreamingHandle(
            file_path=normalized,
            volume=volume,
            fade_ms=fade_ms,
            loop=loop,
        )

        def _task() -> dict[str, Any]:
            if handle.cancel_event.is_set():
                return {"success": False, "elapsed_ms": 0.0, "cancelled": True}
            return self._streaming_task(handle)

        handle.future = self._stream_executor.submit(_task)
        return handle

    def poll_stream_handle(
        self, handle: StreamingHandle
    ) -> Optional[tuple[bool, float, Optional[Exception]]]:
        """Return completion info for a handle once finished."""
        if not handle.future or not handle.future.done():
            return None
        try:
            result = handle.future.result()
            success = bool(result.get("success"))
            elapsed_ms = float(result.get("elapsed_ms", 0.0))
            cancelled = result.get("cancelled", False)
            if cancelled and not success:
                return False, elapsed_ms, None
            return success, elapsed_ms, None
        except Exception as exc:  # pragma: no cover - defensive
            return False, 0.0, exc

    def cancel_stream_handle(self, handle: StreamingHandle) -> None:
        handle.cancel_event.set()
        future = handle.future
        if future and not future.done():
            future.cancel()

    def shutdown_stream_worker(self) -> None:
        if self._stream_executor:
            self._stream_executor.shutdown(wait=False, cancel_futures=True)
            self._stream_executor = None

    def __del__(self):  # pragma: no cover - defensive cleanup
        try:
            self.shutdown_stream_worker()
        except Exception:
            pass

    def stop_streaming_track(self, fade_ms: float = 500) -> bool:
        """Fade out and stop the currently streaming track, if any."""
        if not self._streaming_active:
            return False
        try:
            fade_ms = max(0, int(fade_ms))
            pygame.mixer.music.fadeout(fade_ms)
        except Exception as exc:
            self.logger.warning("Failed to fade out streaming track: %s", exc)
        finally:
            self._streaming_active = False
            self._streaming_path = None
        return True

    def is_streaming_active(self) -> bool:
        return bool(self._streaming_active)

    def preload_sound(self, file_path: str) -> bool:
        """Decode audio ahead of time so later channel loads avoid I/O stalls."""
        if self.should_stream(file_path):
            return self._validate_streamable_path(file_path)
        sound, _ = self._get_or_load_sound(file_path)
        return sound is not None

    def drop_cached_sound(self, file_path: str) -> None:
        """Remove a cached sound buffer so memory can be reclaimed."""
        normalized = self._normalize_path(file_path)
        with self._cache_lock:
            if normalized in self._sound_cache:
                self._sound_cache.pop(normalized, None)
                self._length_cache.pop(normalized, None)
        self._duration_cache.pop(normalized, None)

    def normalize_track_path(self, file_path: str) -> str:
        """Expose normalized path for external managers (e.g., SessionRunner)."""
        return self._normalize_path(file_path)

    def estimate_track_duration(self, file_path: str) -> Optional[float]:
        """Best-effort duration lookup without decoding the entire asset."""
        normalized = self._normalize_path(file_path)
        if normalized in self._duration_cache:
            return self._duration_cache[normalized]
        cached_length = self._length_cache.get(normalized)
        if cached_length:
            self._duration_cache[normalized] = cached_length
            return cached_length

        # Try mutagen for most formats
        try:
            from mutagen import File as MutagenFile  # type: ignore

            audio = MutagenFile(normalized)
            if audio and getattr(audio, "info", None) and getattr(audio.info, "length", None):
                length = float(audio.info.length)
                self._duration_cache[normalized] = length
                return length
        except ImportError:
            self.logger.debug("mutagen not installed; skipping metadata duration lookup")
        except Exception as exc:
            self.logger.debug("mutagen failed to parse %s: %s", normalized, exc)

        # Fallback for WAV via stdlib wave module
        if normalized.lower().endswith(".wav"):
            try:
                with contextlib.closing(wave.open(normalized, "rb")) as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    if rate > 0:
                        length = frames / float(rate)
                        self._duration_cache[normalized] = length
                        return length
            except Exception as exc:
                self.logger.debug("wave module failed to inspect %s: %s", normalized, exc)

        return None

    def prefetch_tracks(self, file_paths: Iterable[str]) -> dict[str, bool]:
        """Preload a batch of tracks, returning per-path success flags."""
        results: dict[str, bool] = {}
        for path in file_paths:
            normalized = self._normalize_path(path)
            if normalized in results:
                continue  # Skip duplicates
            if self.should_stream(path):
                results[normalized] = self._validate_streamable_path(path)
            else:
                results[normalized] = self.preload_sound(path)
        return results
    
    def load_channel(self, channel: int, file_path: str) -> bool:
        """
        Load audio file into specified channel.
        
        Args:
            channel: Channel index (0 to num_channels-1)
            file_path: Path to audio file (mp3, wav, ogg, etc.)
            
        Returns:
            True if loaded successfully, False otherwise
        """
        if not self.init_ok:
            self.logger.warning("AudioEngine not initialized, cannot load audio")
            return False
            
        if not 0 <= channel < self.num_channels:
            self.logger.error(f"Invalid channel {channel}, valid range: 0-{self.num_channels-1}")
            return False
        
        # Stop any existing playback on this channel
        self.stop_channel(channel)
        
        sound, length = self._get_or_load_sound(file_path)
        if not sound:
            self._sounds[channel] = None
            self._paths[channel] = None
            self._lengths[channel] = 0.0
            return False

        self._sounds[channel] = sound
        self._paths[channel] = file_path
        self._lengths[channel] = length
        self.logger.debug(f"Loaded audio into channel {channel}: {file_path} (cached={length > 0.0})")
        return True

    def load_channel_pcm(self, channel: int, pcm_int16_stereo: 'np.ndarray', *, tag: str = "generated") -> bool:
        """Load an in-memory PCM buffer into a channel.

        This supports synthesized/generated layers without going through a file.

        Args:
            channel: Channel index (0..num_channels-1)
            pcm_int16_stereo: numpy array shaped (n_samples, 2) dtype int16
            tag: Debug label stored in _paths
        """
        if not self.init_ok:
            self.logger.warning("AudioEngine not initialized, cannot load generated audio")
            return False

        if not 0 <= channel < self.num_channels:
            self.logger.error(f"Invalid channel {channel}, valid range: 0-{self.num_channels-1}")
            return False

        try:
            if not isinstance(pcm_int16_stereo, np.ndarray):
                self.logger.error("pcm_int16_stereo must be a numpy array")
                return False
            if pcm_int16_stereo.dtype != np.int16:
                self.logger.error("pcm_int16_stereo must be int16")
                return False

            mixer_init = pygame.mixer.get_init()
            mixer_rate = int(mixer_init[0]) if mixer_init else 44100
            mixer_channels = int(mixer_init[2]) if mixer_init else 2

            pcm_for_mixer = pcm_int16_stereo
            # Accept either mono (n,) or stereo (n,2); coerce to match mixer.
            if pcm_for_mixer.ndim == 1:
                if mixer_channels == 1:
                    pass
                elif mixer_channels == 2:
                    pcm_for_mixer = np.stack([pcm_for_mixer, pcm_for_mixer], axis=1)
                else:
                    pcm_for_mixer = np.repeat(pcm_for_mixer[:, None], mixer_channels, axis=1)
            elif pcm_for_mixer.ndim == 2:
                if pcm_for_mixer.shape[1] == mixer_channels:
                    pass
                elif pcm_for_mixer.shape[1] == 2 and mixer_channels == 1:
                    # Downmix stereo -> mono. Keep int16 range.
                    pcm_for_mixer = (pcm_for_mixer.astype(np.int32).mean(axis=1)).astype(np.int16)
                elif pcm_for_mixer.shape[1] == 1 and mixer_channels == 2:
                    pcm_for_mixer = np.repeat(pcm_for_mixer, 2, axis=1)
                elif pcm_for_mixer.shape[1] == 2 and mixer_channels > 2:
                    pcm_for_mixer = np.repeat(pcm_for_mixer[:, :1], mixer_channels, axis=1)
                else:
                    self.logger.error(
                        "pcm buffer channels (%s) do not match mixer channels (%s)",
                        pcm_for_mixer.shape[1],
                        mixer_channels,
                    )
                    return False
            else:
                self.logger.error("pcm buffer must be 1D (mono) or 2D (multi-channel)")
                return False

            # Stop any existing playback on this channel
            self.stop_channel(channel)

            sound = pygame.sndarray.make_sound(pcm_for_mixer)
            self._sounds[channel] = sound
            self._paths[channel] = str(tag)

            # Estimate length from mixer sample rate.
            try:
                length = float(pcm_for_mixer.shape[0]) / float(mixer_rate or 44100)
            except Exception:
                length = 0.0
            self._lengths[channel] = length
            return True
        except Exception as exc:
            self.logger.error(f"Failed to load generated PCM into channel {channel}: {exc}")
            self._sounds[channel] = None
            self._paths[channel] = None
            self._lengths[channel] = 0.0
            return False
    
    def fade_in_and_play(
        self,
        channel: int,
        fade_ms: float = 500,
        volume: float = 1.0,
        loop: bool = False
    ) -> bool:
        """
        Start playback on channel with fade-in effect.
        
        Args:
            channel: Channel index
            fade_ms: Fade-in duration in milliseconds
            volume: Target volume (0.0 to 1.0)
            loop: Whether to loop the audio
            
        Returns:
            True if playback started, False otherwise
        """
        if not self.init_ok or not 0 <= channel < self.num_channels:
            return False
            
        sound = self._sounds[channel]
        if not sound:
            self.logger.warning(f"No audio loaded on channel {channel}, cannot play")
            return False
        
        # Stop existing playback if any
        if self._channels[channel]:
            self._channels[channel].stop()
        
        # Start playback with fade-in
        try:
            loops = -1 if loop else 0
            volume = clamp(volume, 0.0, 1.0)
            fade_ms = max(0, int(fade_ms))
            
            self._channels[channel] = sound.play(loops=loops, fade_ms=fade_ms)
            if self._channels[channel]:
                self._channels[channel].set_volume(volume)
                self._volumes[channel] = volume
                self._looping[channel] = loop
                self._fading_in[channel] = True
                self._fading_out[channel] = False
                self.logger.debug(f"Started playback on channel {channel} (fade: {fade_ms}ms, vol: {volume}, loop: {loop})")
                return True
            else:
                self.logger.warning(f"Failed to get pygame channel for channel {channel}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to play audio on channel {channel}: {e}")
            return False
    
    def fade_out_and_stop(self, channel: int, fade_ms: float = 500) -> bool:
        """
        Fade out and stop playback on channel.
        
        Args:
            channel: Channel index
            fade_ms: Fade-out duration in milliseconds
            
        Returns:
            True if fade-out initiated, False otherwise
        """
        if not self.init_ok or not 0 <= channel < self.num_channels:
            return False
        
        pygame_channel = self._channels[channel]
        if not pygame_channel or not pygame_channel.get_busy():
            # Nothing playing, clean up state
            self._channels[channel] = None
            self._fading_in[channel] = False
            self._fading_out[channel] = False
            return False
        
        try:
            fade_ms = max(0, int(fade_ms))
            pygame_channel.fadeout(fade_ms)
            self._fading_out[channel] = True
            self._fading_in[channel] = False
            self.logger.debug(f"Fading out channel {channel} ({fade_ms}ms)")
            return True
        except Exception as e:
            self.logger.error(f"Failed to fade out channel {channel}: {e}")
            return False
    
    def play_channel(self, channel: int, volume: float = 1.0, loop: bool = False) -> bool:
        """
        Start playback on channel without fade (instant).
        
        Args:
            channel: Channel index
            volume: Playback volume (0.0 to 1.0)
            loop: Whether to loop the audio
            
        Returns:
            True if playback started, False otherwise
        """
        return self.fade_in_and_play(channel, fade_ms=0, volume=volume, loop=loop)
    
    def stop_channel(self, channel: int) -> bool:
        """
        Stop playback on channel immediately (no fade).
        
        Args:
            channel: Channel index
            
        Returns:
            True if stopped, False otherwise
        """
        if not 0 <= channel < self.num_channels:
            return False
        
        if self._channels[channel]:
            try:
                self._channels[channel].stop()
            except Exception as e:
                self.logger.error(f"Error stopping channel {channel}: {e}")
        
        # Clean up state
        self._channels[channel] = None
        self._fading_in[channel] = False
        self._fading_out[channel] = False
        return True

    def get_channel_length(self, channel: int) -> Optional[float]:
        """Return cached length (seconds) for loaded audio on the channel."""
        if not 0 <= channel < self.num_channels:
            return None
        length = self._lengths[channel]
        return float(length) if length else None
    
    def set_volume(self, channel: int, volume: float) -> bool:
        """
        Set volume on channel immediately.
        
        Args:
            channel: Channel index
            volume: Volume level (0.0 to 1.0)
            
        Returns:
            True if volume set, False otherwise
        """
        if not self.init_ok or not 0 <= channel < self.num_channels:
            return False
        
        volume = clamp(volume, 0.0, 1.0)
        self._volumes[channel] = volume
        
        if self._channels[channel] and self._channels[channel].get_busy():
            try:
                self._channels[channel].set_volume(volume)
                return True
            except Exception as e:
                self.logger.error(f"Failed to set volume on channel {channel}: {e}")
                return False
        
        return False
    
    def is_playing(self, channel: int) -> bool:
        """
        Check if audio is currently playing on channel.
        
        Args:
            channel: Channel index
            
        Returns:
            True if playing, False otherwise
        """
        if not 0 <= channel < self.num_channels:
            return False
        
        pygame_channel = self._channels[channel]
        return pygame_channel is not None and pygame_channel.get_busy()
    
    def is_fading_in(self, channel: int) -> bool:
        """Check if channel is currently fading in."""
        if not 0 <= channel < self.num_channels:
            return False
        return self._fading_in[channel]
    
    def is_fading_out(self, channel: int) -> bool:
        """Check if channel is currently fading out."""
        if not 0 <= channel < self.num_channels:
            return False
        return self._fading_out[channel]
    
    def stop_all(self):
        """Stop all channels immediately (no fade)."""
        for i in range(self.num_channels):
            self.stop_channel(i)
        self.stop_streaming_track(fade_ms=0)
        self._paused = False

    def pause_all(self) -> bool:
        """Pause active channels and streaming audio so playback can resume seamlessly."""
        if not self.init_ok or self._paused:
            return False

        any_paused = False
        for channel in range(self.num_channels):
            pygame_channel = self._channels[channel]
            if pygame_channel and pygame_channel.get_busy():
                try:
                    pygame_channel.pause()
                    any_paused = True
                except Exception as exc:
                    self.logger.error(f"Failed to pause channel {channel}: {exc}")

        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
                any_paused = True
        except Exception as exc:
            self.logger.error(f"Failed to pause streaming track: {exc}")

        if any_paused:
            self._paused = True
        return any_paused

    def resume_all(self) -> bool:
        """Resume audio previously paused via pause_all."""
        if not self.init_ok or not self._paused:
            return False

        any_resumed = False
        for channel in range(self.num_channels):
            pygame_channel = self._channels[channel]
            if pygame_channel:
                try:
                    pygame_channel.unpause()
                    any_resumed = True
                except Exception as exc:
                    self.logger.error(f"Failed to resume channel {channel}: {exc}")

        try:
            pygame.mixer.music.unpause()
            any_resumed = True
        except Exception:
            pass

        self._paused = False
        return any_resumed
    
    def update(self):
        """
        Update audio engine state (call every frame).
        
        Handles:
        - Clearing fade flags when fades complete
        - Cleaning up finished playback channels
        """
        if not self.init_ok:
            return
        
        for i in range(self.num_channels):
            if self._channels[i]:
                if not self._channels[i].get_busy():
                    # Playback finished or fade-out completed
                    self._channels[i] = None
                    self._fading_in[i] = False
                    self._fading_out[i] = False
                else:
                    # Clear fade-in flag after fade completes (rough estimate: >100ms after start)
                    if self._fading_in[i]:
                        # Pygame doesn't provide fade completion callback, so we approximate
                        # by clearing the flag after the channel has been playing a bit
                        self._fading_in[i] = False
