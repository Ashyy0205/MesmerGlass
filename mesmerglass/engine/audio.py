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


def _preferred_mixer_rate() -> int:
    """Return preferred mixer sample rate (Hz).

    Some Windows audio stacks behave poorly at 44100Hz (time-stretching / pitch shift).
    Allow overriding via MESMERGLASS_AUDIO_RATE (e.g. 48000).
    """
    default_rate = "48000" if os.name == "nt" else "44100"
    try:
        v = int(float(os.environ.get("MESMERGLASS_AUDIO_RATE", default_rate)))
    except Exception:
        v = int(float(default_rate))
    return max(8000, min(192000, v))


def _preferred_mixer_buffer() -> int:
    """Return SDL mixer buffer size in samples.

    Larger buffers reduce underruns on systems with heavy frame spikes.
    """
    try:
        v = int(float(os.environ.get("MESMERGLASS_AUDIO_BUFFER", "8192")))
    except Exception:
        v = 8192
    return max(512, min(32768, v))

class Audio2:
    """
    - Audio 1: tries Sound; on failure falls back to streamed music (pygame.mixer.music)
    - Audio 2: Sound only (for layering a small loop over the streamed track)
    """
    def __init__(self):
        self.init_ok = False
        try:
            rate = _preferred_mixer_rate()
            buf = _preferred_mixer_buffer()
            pygame.mixer.pre_init(rate, -16, 2, buf)
            pygame.mixer.init()
            self.init_ok = True
            logging.getLogger(__name__).info("pygame mixer initialized (rate=%s buffer=%s)", rate, buf)
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
            # Ensure a stable mixer output format. On some Windows setups SDL may
            # open the device in surround mode (e.g. 8 channels). Our streaming and
            # generated audio are designed for mono/stereo; surround output can lead
            # to distorted/static playback if the downstream expects different layouts.
            os.environ.setdefault("SDL_AUDIO_CHANNELS", "2")

            preferred_rate = _preferred_mixer_rate()
            os.environ.setdefault("SDL_AUDIO_FREQUENCY", str(preferred_rate))

            init = pygame.mixer.get_init()
            if init:
                try:
                    _rate, _fmt, out_ch = init
                    _rate = int(_rate or 0)
                    out_ch = int(out_ch or 2)
                except Exception:
                    _rate = 0
                    out_ch = 2
                # Force a stable stereo output. Mono output can cause streamed
                # interleaved buffers to be interpreted at the wrong frame count,
                # which sounds like "slow motion".
                if out_ch != 2 or (_rate and _rate != preferred_rate):
                    try:
                        pygame.mixer.quit()
                    except Exception:
                        pass
                    init = None

            if not init:
                rate = preferred_rate
                buf = _preferred_mixer_buffer()
                pygame.mixer.pre_init(rate, -16, 2, buf)
                pygame.mixer.init()
            self.init_ok = True
            try:
                existing = int(pygame.mixer.get_num_channels() or 0)
                target = max(existing, int(num_channels))
                pygame.mixer.set_num_channels(target)
            except Exception:
                pass
            try:
                # Use WARNING so it shows up in default console logs.
                self.logger.warning("[audio] pygame mixer init=%s", pygame.mixer.get_init())
                self.logger.warning("[audio] requested mixer rate=%s (MESMERGLASS_AUDIO_RATE)", _preferred_mixer_rate())
                self.logger.warning("[audio] requested mixer buffer=%s (MESMERGLASS_AUDIO_BUFFER)", _preferred_mixer_buffer())
            except Exception:
                pass
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
        # True for channels loaded via load_channel_pcm (synthesized/generated audio).
        # We treat these differently for volume control because pygame fade-in can
        # effectively ramp channel volume back toward 1.0 depending on mixer backend.
        self._generated = [False] * num_channels
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

        # Per-channel streaming (multi-track) state.
        self._stream_stop_events: list[Optional[threading.Event]] = [None] * num_channels
        self._stream_threads: list[Optional[threading.Thread]] = [None] * num_channels
        self._stream_paths_ch: list[Optional[str]] = [None] * num_channels
        self._stream_loop_ch: list[bool] = [False] * num_channels

    def _normalize_path(self, file_path: str) -> str:
        """Return absolute string path for caching consistency."""
        try:
            return str(Path(file_path).resolve())
        except Exception:
            return str(file_path)

    def _get_mixer_params(self) -> tuple[int, int, int]:
        init = pygame.mixer.get_init()
        if not init:
            return 44100, -16, 2
        rate, fmt, channels = init
        return int(rate or 44100), int(fmt or -16), int(channels or 2)

    def _mixer_format_bytes_and_dtype(self, mixer_fmt: int) -> tuple[int, Any, str]:
        """Return (bytes_per_sample, numpy_dtype, av_format) for the active mixer.

        pygame/SDL may report audio formats as bit counts (-16) or as SDL AUDIO_*
        constants (e.g. 32800 for AUDIO_S32SYS). If we guess wrong, raw buffers
        get interpreted at the wrong sample width and sound "chipmunk" fast.
        """
        # Try SDL constants first when available.
        try:
            fmt = int(mixer_fmt)
        except Exception:
            fmt = -16

        constants: list[tuple[str, int, int, Any, str]] = []
        for name, bps, dtype, avfmt in (
            ("AUDIO_U8", 1, np.uint8, "u8"),
            ("AUDIO_S8", 1, np.int8, "s8"),
            ("AUDIO_U16SYS", 2, np.uint16, "u16"),
            ("AUDIO_S16SYS", 2, np.int16, "s16"),
            ("AUDIO_S32SYS", 4, np.int32, "s32"),
            ("AUDIO_F32SYS", 4, np.float32, "flt"),
        ):
            if hasattr(pygame, name):
                constants.append((name, int(getattr(pygame, name)), bps, dtype, avfmt))

        for _name, value, bps, dtype, avfmt in constants:
            if fmt == value:
                return int(bps), dtype, avfmt

        # Fallback: treat as signed bit depth (pygame often returns -16).
        bits = int(abs(fmt) or 16)
        if bits in (8, 16, 32):
            bps = max(1, bits // 8)
            if bps == 1:
                return 1, np.int8, "s8"
            if bps == 4:
                return 4, np.int32, "s32"
            return 2, np.int16, "s16"

        # Safe default
        return 2, np.int16, "s16"

    def _get_fixed_channel(self, channel: int) -> Optional['pygame.mixer.Channel']:
        if not self.init_ok or not 0 <= channel < self.num_channels:
            return None
        try:
            return pygame.mixer.Channel(int(channel))
        except Exception:
            return None

    def _stop_stream_thread(self, channel: int) -> None:
        if not 0 <= channel < self.num_channels:
            return
        ev = self._stream_stop_events[channel]
        th = self._stream_threads[channel]
        if ev is not None:
            ev.set()
        if th is not None and th.is_alive():
            try:
                th.join(timeout=0.25)
            except Exception:
                pass
        self._stream_stop_events[channel] = None
        self._stream_threads[channel] = None
        self._stream_paths_ch[channel] = None
        self._stream_loop_ch[channel] = False

    def is_streaming_channel(self, channel: int) -> bool:
        if not 0 <= channel < self.num_channels:
            return False
        th = self._stream_threads[channel]
        return bool(th is not None and th.is_alive())

    def stream_channel(
        self,
        channel: int,
        file_path: str,
        *,
        volume: float = 1.0,
        fade_ms: float = 0,
        loop: bool = False,
    ) -> bool:
        """Stream a file into a specific mixer channel (multi-stream capable).

        Uses PyAV to decode small PCM chunks and queues them into
        pygame.mixer.Channel(channel).
        """
        if not self.init_ok or not 0 <= channel < self.num_channels:
            return False
        if not self._validate_streamable_path(file_path):
            self.logger.error("Streaming track missing or inaccessible: %s", file_path)
            return False

        # Stop any existing playback/streaming on this channel.
        self.stop_channel(channel)
        self._stop_stream_thread(channel)

        stop_event = threading.Event()
        self._stream_stop_events[channel] = stop_event
        normalized = self._normalize_path(file_path)
        self._stream_paths_ch[channel] = normalized
        self._stream_loop_ch[channel] = bool(loop)

        volume = clamp(volume, 0.0, 1.0)
        self._volumes[channel] = volume
        self._looping[channel] = bool(loop)
        self._generated[channel] = False
        self._paths[channel] = file_path

        pygame_channel = self._get_fixed_channel(channel)
        if pygame_channel is None:
            return False
        try:
            pygame_channel.set_volume(volume)
        except Exception:
            pass
        self._channels[channel] = pygame_channel

        fade_ms = max(0, int(fade_ms))

        def _worker() -> None:
            try:
                import av  # type: ignore
            except Exception as exc:
                self.logger.error("PyAV not available for streaming decode: %s", exc)
                return

            from collections import deque

            rate, mixer_fmt, channels = self._get_mixer_params()
            # If the output device is configured for surround (e.g. 8 channels),
            # we still decode/resample to stereo and then up-mix to the output
            # channel count by padding extra channels with silence.
            layout = "stereo" if channels >= 2 else "mono"
            src_channels = 2 if channels >= 2 else 1

            bytes_per_sample, target_dtype, av_format = self._mixer_format_bytes_and_dtype(mixer_fmt)
            try:
                # WARNING so it appears in default logs; emitted once per stream start.
                self.logger.warning(
                    "[audio.stream] ch=%d mixer(rate=%d fmt=%s channels=%d) -> %s/%s",
                    channel,
                    rate,
                    str(mixer_fmt),
                    channels,
                    av_format,
                    getattr(target_dtype, "__name__", str(target_dtype)),
                )
            except Exception:
                pass

            def _to_pcm_array(frame: Any) -> Optional[np.ndarray]:
                """Convert an AudioFrame to packed interleaved PCM ndarray.

                pygame.mixer.Sound(buffer=...) assumes the buffer matches the mixer's
                sample rate and channel count. If we accidentally pass only one plane
                of planar audio while the mixer is stereo, playback becomes ~2x speed
                and higher pitch.
                """
                try:
                    arr = frame.to_ndarray()
                except Exception:
                    return None

                if arr is None:
                    return None

                # Ensure target dtype
                if getattr(arr, "dtype", None) is not None and arr.dtype != target_dtype:
                    try:
                        arr = np.asarray(arr)
                        if np.issubdtype(arr.dtype, np.floating):
                            arr = np.clip(arr, -1.0, 1.0)
                            if target_dtype == np.int8:
                                arr = (arr * 127.0).astype(np.int8)
                            elif target_dtype == np.int32:
                                arr = (arr * 2147483647.0).astype(np.int32)
                            else:
                                arr = (arr * 32767.0).astype(np.int16)
                        else:
                            arr = arr.astype(target_dtype)
                    except Exception:
                        return None

                # Normalize shape to (samples, channels)
                try:
                    frame_samples = int(getattr(frame, "samples", 0) or 0)
                except Exception:
                    frame_samples = 0
                frame_channels = 0
                try:
                    layout_obj = getattr(frame, "layout", None)
                    frame_channels = int(getattr(layout_obj, "channels", 0) or 0)
                except Exception:
                    frame_channels = 0
                if not frame_channels:
                    try:
                        frame_channels = int(getattr(frame, "channels", 0) or 0)
                    except Exception:
                        frame_channels = 0
                if not frame_channels:
                    frame_channels = int(src_channels or 1)

                def _reshape_flat(flat: np.ndarray) -> np.ndarray:
                    # Use explicit (samples, channels) when possible.
                    if frame_samples > 0 and frame_channels > 0 and int(flat.size) == int(frame_samples) * int(frame_channels):
                        return flat.reshape(int(frame_samples), int(frame_channels))
                    if frame_channels > 1 and int(flat.size) % int(frame_channels) == 0:
                        return flat.reshape(int(flat.size) // int(frame_channels), int(frame_channels))
                    return flat.reshape(-1, 1)

                if arr.ndim == 1:
                    arr = _reshape_flat(arr)
                elif arr.ndim == 2:
                    # Prefer exact matching using frame.samples / channel count.
                    try:
                        sh0, sh1 = int(arr.shape[0]), int(arr.shape[1])
                    except Exception:
                        sh0, sh1 = 0, 0

                    if frame_samples > 0 and frame_channels > 0:
                        # Typical planar: (channels, samples)
                        if sh0 == frame_channels and sh1 == frame_samples:
                            arr = arr.T
                        # Typical packed: (samples, channels)
                        elif sh0 == frame_samples and sh1 == frame_channels:
                            pass
                        # Some backends return packed audio as (1, samples*channels) or (samples*channels, 1)
                        elif (sh0 == 1 and sh1 == frame_samples * frame_channels) or (sh1 == 1 and sh0 == frame_samples * frame_channels):
                            try:
                                flat = np.reshape(arr, (-1,))
                                arr = flat.reshape(int(frame_samples), int(frame_channels))
                            except Exception:
                                arr = _reshape_flat(np.reshape(arr, (-1,)))
                        elif sh0 == 1 or sh1 == 1:
                            arr = _reshape_flat(np.reshape(arr, (-1,)))
                        else:
                            # Fallback heuristic: if first dim looks like channels.
                            if sh0 <= 8 and sh1 > 32 and sh0 < sh1:
                                arr = arr.T
                    else:
                        # No metadata: fallback heuristic.
                        try:
                            if int(arr.shape[0]) <= 8 and int(arr.shape[1]) > 32 and int(arr.shape[0]) < int(arr.shape[1]):
                                arr = arr.T
                        except Exception:
                            pass
                else:
                    try:
                        arr = _reshape_flat(np.reshape(arr, (-1,)))
                    except Exception:
                        return None

                # Final sanity: must be (samples, channels)
                if arr.ndim != 2:
                    try:
                        arr = np.reshape(arr, (-1, 1))
                    except Exception:
                        return None

                # Match resampler output (mono/stereo)
                if src_channels == 1:
                    if arr.shape[1] >= 2:
                        arr = (arr[:, 0].astype(np.int32) + arr[:, 1].astype(np.int32)) // 2
                        arr = arr.astype(target_dtype).reshape(-1, 1)
                    elif arr.shape[1] != 1:
                        arr = arr.reshape(-1, 1)
                else:
                    if arr.shape[1] == 1:
                        arr = np.repeat(arr, 2, axis=1)
                    elif arr.shape[1] > 2:
                        arr = arr[:, :2]

                # Match mixer channel count (mono / stereo / surround)
                if channels == 1:
                    if arr.shape[1] >= 2:
                        # simple downmix
                        arr = (arr[:, 0].astype(np.int32) + arr[:, 1].astype(np.int32)) // 2
                        arr = arr.astype(target_dtype).reshape(-1, 1)
                    elif arr.shape[1] != 1:
                        arr = arr.reshape(-1, 1)
                elif channels == 2:
                    if arr.shape[1] == 1:
                        arr = np.repeat(arr, 2, axis=1)
                    elif arr.shape[1] > 2:
                        arr = arr[:, :2]
                else:
                    # Upmix/downmix to N-channel output by padding/truncating.
                    if arr.shape[1] == channels:
                        pass
                    elif arr.shape[1] == 1:
                        # replicate mono to all output channels
                        arr = np.repeat(arr, int(channels), axis=1)
                    elif arr.shape[1] == 2:
                        # place stereo in the first two channels; silence the rest
                        out_arr = np.zeros((arr.shape[0], int(channels)), dtype=arr.dtype)
                        out_arr[:, 0:2] = arr[:, 0:2]
                        arr = out_arr
                    elif arr.shape[1] > channels:
                        arr = arr[:, :int(channels)]
                    else:
                        # pad remaining channels with silence
                        pad = int(channels) - int(arr.shape[1])
                        if pad > 0:
                            arr = np.pad(arr, ((0, 0), (0, pad)), mode="constant")

                return np.ascontiguousarray(arr, dtype=target_dtype)

            try:
                resampler = av.audio.resampler.AudioResampler(
                    format=av_format,
                    layout=layout,
                    rate=rate,
                )
            except Exception as exc:
                self.logger.error("Failed to configure audio resampler: %s", exc)
                return

            # Chunks: pygame only supports a single queued Sound per channel.
            # If the main thread holds the GIL for ~100-200ms (common during video
            # warmup and ThemeBank image work), this streamer thread can miss the
            # small window where it needs to queue the *next* chunk.
            # Longer chunks make that window much less frequent.
            chunk_frames = max(2048, int(rate * 2.0))
            logged_chunk_stats = False
            expected_chunk_s = float(chunk_frames) / float(rate or 44100)

            def _sound_generator() -> Iterable['pygame.mixer.Sound']:
                """Yield Sound chunks indefinitely (or once if loop=False)."""
                carry_parts: list[np.ndarray] = []
                carry_frames = 0
                logged_make_sound_error = False
                logged_stream_info = False
                logged_first_in = False
                want_first_out = False

                def _push_samples(arr: np.ndarray) -> Iterable[np.ndarray]:
                    nonlocal carry_frames
                    if arr.size == 0 or arr.ndim != 2:
                        return []
                    carry_parts.append(arr)
                    carry_frames += int(arr.shape[0])

                    chunks: list[np.ndarray] = []
                    while carry_frames >= chunk_frames:
                        needed = int(chunk_frames)
                        take_parts: list[np.ndarray] = []
                        while needed > 0 and carry_parts:
                            part = carry_parts[0]
                            part_frames = int(part.shape[0])
                            if part_frames <= needed:
                                take_parts.append(part)
                                carry_parts.pop(0)
                                needed -= part_frames
                            else:
                                take_parts.append(part[:needed])
                                carry_parts[0] = part[needed:]
                                needed = 0

                        if take_parts:
                            try:
                                chunk_arr = np.concatenate(take_parts, axis=0)
                            except Exception:
                                chunk_arr = take_parts[0]
                            chunks.append(chunk_arr)
                            carry_frames -= int(chunk_arr.shape[0])
                        else:
                            break
                    return chunks

                def _open_container() -> Any:
                    return av.open(normalized)

                while not stop_event.is_set():
                    try:
                        container = _open_container()
                    except Exception as exc:
                        self.logger.error("Failed to open audio for streaming: %s", exc)
                        return

                    try:
                        stream = None
                        for s in container.streams:
                            if getattr(s, "type", None) == "audio":
                                stream = s
                                break
                        if stream is None:
                            self.logger.error("No audio stream found in: %s", normalized)
                            return

                        if not logged_stream_info:
                            logged_stream_info = True
                            try:
                                in_sr = None
                                in_layout = None
                                try:
                                    cc = getattr(stream, "codec_context", None)
                                    in_sr = getattr(cc, "sample_rate", None)
                                except Exception:
                                    in_sr = None
                                try:
                                    in_layout = getattr(getattr(stream, "layout", None), "name", None)
                                except Exception:
                                    in_layout = None
                                self.logger.warning(
                                    "[audio.stream] ch=%d input(sr=%s layout=%s) target(sr=%d layout=%s)",
                                    channel,
                                    str(in_sr),
                                    str(in_layout),
                                    int(rate),
                                    str(layout),
                                )
                            except Exception:
                                pass

                        # Prefer container.decode(stream) to avoid format-specific
                        # demux/packet edge cases.
                        decoded_any = False
                        decode_fallback_used = False
                        try:
                            frame_iter = container.decode(audio=0)
                        except Exception as exc:
                            decode_fallback_used = True
                            try:
                                self.logger.warning(
                                    "[audio.stream] ch=%d decode(audio=0) unavailable (%s); falling back to decode(stream)",
                                    channel,
                                    str(exc),
                                )
                            except Exception:
                                pass
                            frame_iter = container.decode(stream)

                        for frame in frame_iter:
                            if stop_event.is_set():
                                break
                            decoded_any = True

                            if not logged_first_in:
                                logged_first_in = True
                                want_first_out = True
                                try:
                                    self.logger.warning(
                                        "[audio.stream] ch=%d first_frame in(sr=%s samples=%s)",
                                        channel,
                                        str(getattr(frame, "sample_rate", None)),
                                        str(getattr(frame, "samples", None)),
                                    )
                                except Exception:
                                    pass
                            try:
                                out_frames = resampler.resample(frame)
                            except Exception as exc:
                                # Resampler errors should not kill the whole stream.
                                self.logger.debug("Streaming resample error: %s", exc)
                                continue

                            if out_frames is None:
                                continue
                            # PyAV has changed return types across versions: it may
                            # return a list of frames or a single AudioFrame.
                            if not isinstance(out_frames, (list, tuple)):
                                out_frames = [out_frames]

                            for out in out_frames:
                                if stop_event.is_set():
                                    break
                                if want_first_out:
                                    # Log output details once (paired with first input frame).
                                    try:
                                        self.logger.warning(
                                            "[audio.stream] ch=%d first_frame out(sr=%s samples=%s)",
                                            channel,
                                            str(getattr(out, "sample_rate", None)),
                                            str(getattr(out, "samples", None)),
                                        )
                                    except Exception:
                                        pass
                                    want_first_out = False
                                arr = _to_pcm_array(out)
                                if arr is None or arr.size == 0:
                                    continue
                                for chunk_arr in _push_samples(arr):
                                    if stop_event.is_set():
                                        break
                                    try:
                                        yield pygame.sndarray.make_sound(chunk_arr)
                                    except Exception as exc:
                                        if not logged_make_sound_error:
                                            logged_make_sound_error = True
                                            try:
                                                self.logger.warning(
                                                    "[audio.stream] ch=%d make_sound failed: %s (shape=%s dtype=%s)",
                                                    channel,
                                                    str(exc),
                                                    getattr(chunk_arr, "shape", None),
                                                    getattr(getattr(chunk_arr, "dtype", None), "name", None),
                                                )
                                            except Exception:
                                                pass
                                        continue

                        if not decoded_any:
                            self.logger.warning(
                                "[audio.stream] ch=%d decoded no frames from %s",
                                channel,
                                os.path.basename(normalized),
                            )

                        if not loop:
                            break
                    except Exception as exc:
                        self.logger.warning(
                            "Streaming decode error for %s: %s",
                            os.path.basename(normalized),
                            exc,
                        )
                        if not loop:
                            break
                    finally:
                        try:
                            container.close()
                        except Exception:
                            pass

                    if not loop:
                        break

            # Decode ahead into a small buffer so visuals can hitch without underruns.
            # Longer backlog helps survive heavy visual hitches and CPU spikes.
            # (Gaps between chunks can feel like "slow motion" playback.)
            buffer_max = 16
            prefill_min = 4
            buffer: 'deque[pygame.mixer.Sound]' = deque()
            gen = _sound_generator()
            gen_done = False

            def _fill_buffer() -> None:
                nonlocal gen_done, logged_chunk_stats
                while not stop_event.is_set() and not gen_done and len(buffer) < buffer_max:
                    try:
                        snd = next(gen)
                    except StopIteration:
                        gen_done = True
                        break
                    except Exception:
                        continue
                    if snd is None:
                        continue
                    if not logged_chunk_stats:
                        logged_chunk_stats = True
                        try:
                            self.logger.warning(
                                "[audio.stream] ch=%d first_chunk len=%.3fs expected=%.3fs (rate=%d chunk_frames=%d)",
                                channel,
                                float(snd.get_length() or 0.0),
                                expected_chunk_s,
                                int(rate),
                                int(chunk_frames),
                            )
                        except Exception:
                            pass
                    buffer.append(snd)

            # Prefill before starting playback.
            prefill_started = time.perf_counter()
            warned_prefill = False
            while not stop_event.is_set() and not gen_done and len(buffer) < prefill_min:
                _fill_buffer()
                if not warned_prefill and len(buffer) == 0 and (time.perf_counter() - prefill_started) > 1.0:
                    warned_prefill = True
                    try:
                        self.logger.warning(
                            "[audio.stream] ch=%d prefill stalled (no chunks yet) file=%s",
                            channel,
                            os.path.basename(normalized),
                        )
                    except Exception:
                        pass
                if len(buffer) < prefill_min:
                    time.sleep(0.005)

            first_chunk = True
            # Keep strong refs to avoid any backend edge cases where queued/play
            # sounds could be GC'd early.
            current_playing: Optional['pygame.mixer.Sound'] = None
            current_queued: Optional['pygame.mixer.Sound'] = None
            current_playing_start_ts = 0.0
            current_playing_len = 0.0
            last_play_ts = time.perf_counter()
            last_underrun_log_ts = 0.0
            underrun_count = 0
            queue_fail_logged = False
            restart_count = 0
            stats_last_log_ts = time.perf_counter()
            while not stop_event.is_set():
                _fill_buffer()

                try:
                    busy = pygame_channel.get_busy()
                    queued = pygame_channel.get_queue() is not None
                except Exception:
                    busy = False
                    queued = False

                if not busy:
                    if buffer:
                        snd = buffer.popleft()
                        try:
                            pygame_channel.play(
                                snd,
                                loops=0,
                                fade_ms=(fade_ms if first_chunk else 0),
                            )
                            current_playing = snd
                            current_playing_start_ts = time.perf_counter()
                            try:
                                current_playing_len = float(snd.get_length() or 0.0)
                            except Exception:
                                current_playing_len = 0.0
                            last_play_ts = time.perf_counter()
                        except Exception:
                            pass

                        if not first_chunk:
                            restart_count += 1
                        # Re-apply channel volume after starting playback.
                        try:
                            pygame_channel.set_volume(float(self._volumes[channel]))
                        except Exception:
                            pass
                        # Immediately queue the next chunk if available so we always
                        # have a full chunk of safety margin.
                        try:
                            if buffer and pygame_channel.get_queue() is None:
                                nxt = buffer.popleft()
                                pygame_channel.queue(nxt)
                                current_queued = nxt
                        except Exception as exc:
                            if not queue_fail_logged:
                                queue_fail_logged = True
                                try:
                                    self.logger.warning(
                                        "[audio.stream] ch=%d queue() failed: %s",
                                        channel,
                                        str(exc),
                                    )
                                except Exception:
                                    pass
                        try:
                            if not pygame_channel.get_busy():
                                self.logger.warning(
                                    "[audio.stream] ch=%d play() did not start (busy=%s queued=%s)",
                                    channel,
                                    str(False),
                                    str(pygame_channel.get_queue() is not None),
                                )
                        except Exception:
                            pass
                        first_chunk = False
                    elif gen_done:
                        break
                    else:
                        # We have not decoded enough to start yet (or we fell behind).
                        underrun_count += 1
                        now = time.perf_counter()
                        if (now - last_underrun_log_ts) > 1.0:
                            last_underrun_log_ts = now
                            try:
                                self.logger.warning(
                                    "[audio.stream] ch=%d underrun: busy=False buffer=%d gen_done=%s (since_last_play=%.2fs)",
                                    channel,
                                    int(len(buffer)),
                                    str(gen_done),
                                    float(now - last_play_ts),
                                )
                            except Exception:
                                pass
                else:
                    if not queued and buffer:
                        try:
                            nxt = buffer.popleft()
                            pygame_channel.queue(nxt)
                            current_queued = nxt
                        except Exception as exc:
                            if not queue_fail_logged:
                                queue_fail_logged = True
                                try:
                                    self.logger.warning(
                                        "[audio.stream] ch=%d queue() failed: %s",
                                        channel,
                                        str(exc),
                                    )
                                except Exception:
                                    pass
                        try:
                            pygame_channel.set_volume(float(self._volumes[channel]))
                        except Exception:
                            pass

                # If queue drained, drop the strong ref so we don't pin memory.
                if busy and not queued:
                    current_queued = None

                # Diagnose true time-stretch: if chunk boundaries take much longer
                # than the chunk length, playback is running "slow" (independent of
                # decode/queue health).
                try:
                    playing_now = pygame_channel.get_sound()
                except Exception:
                    playing_now = None
                if playing_now is not None and current_playing is not None and playing_now is not current_playing:
                    now = time.perf_counter()
                    elapsed = now - float(current_playing_start_ts or now)
                    expected = float(current_playing_len or 0.0)
                    if expected > 0.25:
                        ratio = elapsed / expected if expected > 0 else 1.0
                        if ratio >= 1.25 or ratio <= 0.75:
                            try:
                                self.logger.warning(
                                    "[audio.stream] ch=%d timing drift: chunk_elapsed=%.3fs chunk_len=%.3fs (ratio=%.2f)",
                                    channel,
                                    float(elapsed),
                                    float(expected),
                                    float(ratio),
                                )
                            except Exception:
                                pass
                    current_playing = playing_now
                    current_playing_start_ts = now
                    try:
                        current_playing_len = float(playing_now.get_length() or 0.0)
                    except Exception:
                        current_playing_len = 0.0

                now = time.perf_counter()
                if (now - stats_last_log_ts) >= 5.0:
                    stats_last_log_ts = now
                    try:
                        self.logger.warning(
                            "[audio.stream] ch=%d stats: buffer=%d restarts=%d underruns=%d busy=%s queued=%s",
                            channel,
                            int(len(buffer)),
                            int(restart_count),
                            int(underrun_count),
                            str(bool(busy)),
                            str(bool(queued)),
                        )
                    except Exception:
                        pass

                time.sleep(0.001)

            try:
                pygame_channel.stop()
            except Exception:
                pass

        thread = threading.Thread(target=_worker, name=f"audio-stream-ch{channel}", daemon=True)
        self._stream_threads[channel] = thread
        thread.start()
        return True

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

    def set_streaming_volume(self, volume: float) -> bool:
        """Set pygame.mixer.music volume (for the streaming track).

        Returns True if the call succeeded.
        """
        if not self.init_ok:
            return False
        try:
            pygame.mixer.music.set_volume(clamp(volume, 0.0, 1.0))
            return True
        except Exception as exc:
            self.logger.debug("Failed to set streaming volume: %s", exc)
            return False

    def is_streaming_active(self) -> bool:
        if self._streaming_active:
            return True
        for ch in range(self.num_channels):
            if self.is_streaming_channel(ch):
                return True
        return False

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
        self._stop_stream_thread(channel)
        
        sound, length = self._get_or_load_sound(file_path)
        if not sound:
            self._sounds[channel] = None
            self._paths[channel] = None
            self._lengths[channel] = 0.0
            return False

        self._sounds[channel] = sound
        self._paths[channel] = file_path
        self._lengths[channel] = length
        self._generated[channel] = False
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
            self._generated[channel] = True

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

        # Stop any streaming thread (if active) and stop the fixed channel.
        self._stop_stream_thread(channel)
        pygame_channel = self._get_fixed_channel(channel)
        if pygame_channel is None:
            return False
        try:
            pygame_channel.stop()
        except Exception:
            pass
        
        # Start playback with fade-in
        try:
            loops = -1 if loop else 0
            volume = clamp(volume, 0.0, 1.0)
            fade_ms = max(0, int(fade_ms))

            # For synthesized/generated audio (e.g. Shepard tone bed), prefer applying
            # volume at the Sound-level as well. Some mixer backends treat fade-in as
            # ramping toward full channel volume, which can make channel-only volume
            # scaling appear ineffective.
            if self._generated[channel]:
                try:
                    sound.set_volume(volume)
                except Exception:
                    pass
                play_volume = 1.0
            else:
                play_volume = volume

            pygame_channel.play(sound, loops=loops, fade_ms=fade_ms)
            self._channels[channel] = pygame_channel
            if self._channels[channel]:
                self._channels[channel].set_volume(play_volume)
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

        # Stop streaming thread so no more chunks are queued.
        self._stop_stream_thread(channel)
        
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

        # Stop streaming thread first (if any).
        self._stop_stream_thread(channel)
        
        pygame_channel = self._get_fixed_channel(channel)
        if pygame_channel:
            try:
                pygame_channel.stop()
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

        pygame_channel = self._channels[channel] or self._get_fixed_channel(channel)

        if self._generated[channel]:
            sound = self._sounds[channel]
            if sound:
                try:
                    sound.set_volume(volume)
                except Exception:
                    pass
            # Keep the active mixer channel at unity; volume is carried by the Sound.
            if pygame_channel and pygame_channel.get_busy():
                try:
                    pygame_channel.set_volume(1.0)
                    return True
                except Exception as e:
                    self.logger.error(f"Failed to set volume on channel {channel}: {e}")
                    return False
            return False

        if pygame_channel and pygame_channel.get_busy():
            try:
                pygame_channel.set_volume(volume)
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
        
        pygame_channel = self._channels[channel] or self._get_fixed_channel(channel)
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
            pygame_channel = self._channels[channel] or self._get_fixed_channel(channel)
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
            pygame_channel = self._channels[channel] or self._get_fixed_channel(channel)
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
