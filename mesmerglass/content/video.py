"""Video decoding and streaming for background media.

Implements Trance's AsyncStreamer architecture with:
- Double-buffered streaming (Buffer A/B)
- Ping-pong playback mode (forward then backward)
- Fractional frame advancement for smooth temporal sampling
- Async preloading on separate thread
- Support for GIF (memory), WebM/MP4 (streamed)

Reference: RECREATION_FILES/async_streamer.cpp lines 1-189
           RECREATION_FILES/SPIRAL_AND_MEDIA_DOCUMENTATION.md lines 403-536
"""

from __future__ import annotations

import os
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Callable
from dataclasses import dataclass
from collections import deque, OrderedDict

import numpy as np

logger = logging.getLogger(__name__)
VIDEO_IO_LOCK = threading.Lock()


def _normalize_path(path: str | Path) -> Path:
    path_obj = path if isinstance(path, Path) else Path(path)
    try:
        return path_obj.resolve()
    except Exception:
        try:
            return path_obj.absolute()
        except Exception:
            return path_obj


def _read_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


VIDEO_PREFILL_FRAME_LIMIT = max(0, _read_env_int("MESMERGLASS_VIDEO_PREFILL_FRAMES", 48))
VIDEO_PREFILL_BUDGET_MS = max(0.0, _read_env_float("MESMERGLASS_VIDEO_PREFILL_MAX_MS", 12.0))

# Decoder reuse cache (helps when cycling among a small set of clips).
# Keeps cv2.VideoCapture handles open to avoid repeated open/close stalls.
VIDEO_DECODER_CACHE_MAX = max(0, _read_env_int("MESMERGLASS_VIDEO_DECODER_CACHE", 4))
_DECODER_CACHE_LOCK = threading.Lock()
_DECODER_CACHE: "OrderedDict[Path, VideoDecoder]" = OrderedDict()  # type: ignore[name-defined]

# Warmup pacing / backpressure to avoid starving the UI thread during rapid cycling.
VIDEO_WARMUP_QUEUE_MAX = max(
    0,
    _read_env_int(
        "MESMERGLASS_VIDEO_WARMUP_QUEUE_MAX",
        max(8, VIDEO_DECODER_CACHE_MAX * 4),
    ),
)
VIDEO_WARMUP_YIELD_S = max(0.0, _read_env_float("MESMERGLASS_VIDEO_WARMUP_YIELD_MS", 1.0) / 1000.0)

# Background warmup: pre-open decoders off the UI thread and place them into the cache.
_DECODER_WARM_QUEUE: deque[Path] = deque()
_DECODER_WARM_SET: set[Path] = set()
_DECODER_WARM_LOCK = threading.Lock()
_DECODER_WARM_EVENT = threading.Event()
_DECODER_WARM_THREAD: Optional[threading.Thread] = None


def queue_decoder_warmup(path: str | Path, *, priority: bool = False) -> None:
    """Schedule a decoder open in the background.

    This is a best-effort optimization to reduce stalls when cycling videos
    quickly (e.g., every ~0.7s). It is safe to call frequently; requests are
    deduplicated.
    """
    if VIDEO_DECODER_CACHE_MAX <= 0:
        return

    try:
        path_obj = _normalize_path(path)
    except Exception:
        return

    global _DECODER_WARM_THREAD
    with _DECODER_WARM_LOCK:
        if priority:
            # Focus warmup bandwidth on the currently requested clip.
            # This prevents large media banks from flooding the warmup queue and
            # starving the actual pending switch.
            _DECODER_WARM_QUEUE.clear()
            _DECODER_WARM_SET.clear()
        if VIDEO_WARMUP_QUEUE_MAX > 0 and len(_DECODER_WARM_QUEUE) >= VIDEO_WARMUP_QUEUE_MAX:
            return
        if path_obj in _DECODER_WARM_SET:
            if priority:
                try:
                    _DECODER_WARM_QUEUE.remove(path_obj)
                    _DECODER_WARM_QUEUE.appendleft(path_obj)
                except Exception:
                    pass
                _DECODER_WARM_EVENT.set()
            return
        # If already cached, don't bother.
        with _DECODER_CACHE_LOCK:
            if path_obj in _DECODER_CACHE:
                return

        _DECODER_WARM_SET.add(path_obj)
        if priority:
            _DECODER_WARM_QUEUE.appendleft(path_obj)
        else:
            _DECODER_WARM_QUEUE.append(path_obj)
        _DECODER_WARM_EVENT.set()

        if _DECODER_WARM_THREAD is None or not _DECODER_WARM_THREAD.is_alive():
            _DECODER_WARM_THREAD = threading.Thread(
                target=_decoder_warmup_worker,
                name="VideoDecoderWarmup",
                daemon=True,
            )
            _DECODER_WARM_THREAD.start()


def _decoder_warmup_worker() -> None:
    while True:
        _DECODER_WARM_EVENT.wait()

        while True:
            with _DECODER_WARM_LOCK:
                if not _DECODER_WARM_QUEUE:
                    _DECODER_WARM_EVENT.clear()
                    break
                path_obj = _DECODER_WARM_QUEUE.popleft()
                _DECODER_WARM_SET.discard(path_obj)

            with _DECODER_CACHE_LOCK:
                if path_obj in _DECODER_CACHE:
                    continue

            try:
                decoder = VideoDecoder(path_obj)
            except Exception:
                continue

            try:
                if getattr(decoder, "success", False):
                    _return_cached_decoder(decoder)
                else:
                    decoder.close()
            except Exception:
                try:
                    decoder.close()
                except Exception:
                    pass

            # Be polite to the main thread: let Qt and the render loop run.
            try:
                if VIDEO_WARMUP_YIELD_S > 0:
                    time.sleep(VIDEO_WARMUP_YIELD_S)
                else:
                    time.sleep(0)
            except Exception:
                pass


def _checkout_cached_decoder(path: Path) -> Optional["VideoDecoder"]:  # type: ignore[name-defined]
    if VIDEO_DECODER_CACHE_MAX <= 0:
        return None
    try:
        path = _normalize_path(path)
    except Exception:
        pass
    with _DECODER_CACHE_LOCK:
        decoder = _DECODER_CACHE.pop(path, None)
    if decoder is None:
        return None
    try:
        decoder.reset()
    except Exception:
        try:
            decoder.close()
        except Exception:
            pass
        return None
    return decoder


def _return_cached_decoder(decoder: "VideoDecoder") -> None:  # type: ignore[name-defined]
    if VIDEO_DECODER_CACHE_MAX <= 0:
        try:
            decoder.close()
        except Exception:
            pass
        return

    # Only cache streamable video decoders; GIFs are already fully in-memory.
    if not getattr(decoder, "success", False) or getattr(decoder, "format", "") != "video":
        try:
            decoder.close()
        except Exception:
            pass
        return

    path = getattr(decoder, "path", None)
    if not isinstance(path, Path):
        try:
            decoder.close()
        except Exception:
            pass
        return

    try:
        path = _normalize_path(path)
    except Exception:
        pass

    with _DECODER_CACHE_LOCK:
        _DECODER_CACHE[path] = decoder
        _DECODER_CACHE.move_to_end(path)
        while len(_DECODER_CACHE) > VIDEO_DECODER_CACHE_MAX:
            _, evicted = _DECODER_CACHE.popitem(last=False)
            try:
                evicted.close()
            except Exception:
                pass


@dataclass
class VideoFrame:
    """Single video frame with RGB data."""
    data: np.ndarray  # Shape: (height, width, 3), dtype=uint8
    width: int
    height: int
    timestamp: float  # Frame timestamp in seconds


class VideoDecoder:
    """Decodes video files frame-by-frame.
    
    Supports:
    - GIF: Entire file loaded into memory
    - MP4/WebM: Streamed from disk via OpenCV
    
    Frame extraction mimics Trance's Streamer::next_frame() behavior.
    """
    
    def __init__(self, path: str | Path):
        """Initialize decoder for video file.
        
        Args:
            path: Path to video file (GIF, MP4, WebM)
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format unsupported
        """
        self.path = _normalize_path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")
        
        self.format = self._detect_format()
        self.width = 0
        self.height = 0
        self.fps = 30.0
        self.frame_count = 0
        self.current_frame_idx = 0
        self.success = False
        
        # OpenCV video capture (for MP4/WebM)
        self.cap: Optional[object] = None
        
        # GIF frames (entire file in memory)
        self.gif_frames: list[VideoFrame] = []
        
        self._initialize()
    
    def _detect_format(self) -> str:
        """Detect video format from file extension."""
        ext = self.path.suffix.lower()
        if ext == '.gif':
            return 'gif'
        elif ext in ['.mp4', '.webm', '.avi', '.mov']:
            return 'video'
        else:
            raise ValueError(f"Unsupported video format: {ext}")
    
    def _initialize(self) -> None:
        """Initialize decoder based on format."""
        if self.format == 'gif':
            self._load_gif()
        else:
            self._open_video()
    
    def _load_gif(self) -> None:
        """Load entire GIF into memory.
        
        Trance behavior: GIF loaded entirely, transparency/disposal modes supported.
        We use OpenCV which handles GIF as video.
        """
        try:
            import cv2
            with VIDEO_IO_LOCK:
                cap = cv2.VideoCapture(str(self.path))
                if not cap.isOpened():
                    logger.error(f"Failed to open GIF: {self.path}")
                    return
            
            self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Load all frames into memory
            frame_idx = 0
            while True:
                with VIDEO_IO_LOCK:
                    ret, frame = cap.read()
                if not ret:
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = frame_idx / self.fps

                self.gif_frames.append(VideoFrame(
                    data=rgb,
                    width=self.width,
                    height=self.height,
                    timestamp=timestamp
                ))
                frame_idx += 1
            
            with VIDEO_IO_LOCK:
                cap.release()
            
            if self.gif_frames:
                self.success = True
                logger.info(f"[GIF] Loaded {len(self.gif_frames)} frames from {self.path.name}")
            else:
                logger.warning(f"[GIF] No frames loaded from {self.path}")
        
        except Exception as e:
            logger.error(f"[GIF] Failed to load {self.path}: {e}")
            self.success = False
    
    def _open_video(self) -> None:
        """Open video file for streaming.
        
        Trance behavior: WebM/MP4 streamed from disk, YUV→RGB per frame.
        """
        try:
            import cv2
            with VIDEO_IO_LOCK:
                self.cap = cv2.VideoCapture(str(self.path))
                if not self.cap.isOpened():
                    logger.error(f"[Video] Failed to open: {self.path}")
                    return
            
            with VIDEO_IO_LOCK:
                self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 30.0)
                self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            self.success = True
            logger.info(f"[Video] Opened {self.path.name} - {self.width}x{self.height} @ {self.fps}fps, {self.frame_count} frames")
        
        except Exception as e:
            logger.error(f"[Video] Failed to open {self.path}: {e}")
            self.success = False
    
    def next_frame(self) -> Optional[VideoFrame]:
        """Get next frame from video.
        
        Mimics Trance's Streamer::next_frame():
        - GIF: Returns next frame from memory buffer (wraps at end)
        - Video: Reads next frame from disk, returns None at end
        
        Returns:
            VideoFrame if available, None if end reached (for streamed video)
        """
        if not self.success:
            return None
        
        if self.format == 'gif':
            # GIF: Return frames from memory (circular)
            if not self.gif_frames:
                return None
            
            frame = self.gif_frames[self.current_frame_idx]
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.gif_frames)
            return frame
        
        else:
            # Video: Stream from disk
            if self.cap is None:
                return None
            
            try:
                import cv2
                with VIDEO_IO_LOCK:
                    ret, frame = self.cap.read()
                
                if not ret:
                    # End of video reached
                    return None
                
                # Convert BGR to RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = self.current_frame_idx / self.fps
                
                self.current_frame_idx += 1
                
                return VideoFrame(
                    data=rgb,
                    width=self.width,
                    height=self.height,
                    timestamp=timestamp
                )
            
            except Exception as e:
                logger.error(f"[Video] Frame read error: {e}")
                return None
    
    def seek(self, frame_idx: int) -> bool:
        """Seek to specific frame index.
        
        Args:
            frame_idx: Target frame index (0-based)
        
        Returns:
            True if seek successful
        """
        if not self.success:
            return False
        
        if self.format == 'gif':
            # GIF: Just update index (frames in memory)
            if 0 <= frame_idx < len(self.gif_frames):
                self.current_frame_idx = frame_idx
                return True
            return False
        
        else:
            # Video: Use OpenCV seek
            if self.cap is None:
                return False
            
            try:
                import cv2
                with VIDEO_IO_LOCK:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                self.current_frame_idx = frame_idx
                return True
            except Exception as e:
                logger.error(f"[Video] Seek failed: {e}")
                return False
    
    def reset(self) -> None:
        """Reset to beginning of video."""
        self.seek(0)
    
    def close(self) -> None:
        """Close video file and release resources."""
        if self.cap is not None:
            try:
                with VIDEO_IO_LOCK:
                    self.cap.release()
            except Exception:
                pass
            self.cap = None
        
        # Clear GIF frames to free memory
        self.gif_frames.clear()
        self.success = False
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()
    
    def __enter__(self):
        """Context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()


class VideoStreamer:
    """Double-buffered video streamer with ping-pong playback.
    
    Implements Trance's AsyncStreamer architecture:
    - Buffer A: Currently playing video
    - Buffer B: Preloading next video in background
    - Ping-pong mode: Play forward, then backward, repeat
    - Fractional frame advancement: Smooth temporal sampling
    - Async loading: Separate thread for buffer filling
    
    Reference: RECREATION_FILES/async_streamer.cpp
    """
    
    def __init__(self, buffer_size: int = 120):
        """Initialize double-buffered streamer.
        
        Args:
            buffer_size: Number of frames to buffer per video (default 120 = 2 sec @ 60fps)
        """
        self.buffer_size = buffer_size
        
        # Animation buffers (Trance's Animation struct)
        self._buffer_a = AnimationBuffer(buffer_size)
        self._buffer_b = AnimationBuffer(buffer_size)
        
        # Current/Next pointers (swap on video change)
        self._current = self._buffer_a
        self._next = self._buffer_b
        
        # Playback state
        self._index = 0  # Current frame index in buffer
        self._backwards = False  # Ping-pong direction
        self._reached_end = False  # Hit end of current video
        self._update_counter = 0.0  # Fractional frame accumulator
        
        # Threading
        self._lock = threading.Lock()
        self._loader_thread: Optional[threading.Thread] = None
        self._loader_running = False
        self._loader_done = threading.Event()

        # Avoid holding the main streamer lock while decoding frames.
        # When set to "current" or "next", the async loader will not fill that
        # buffer (so the decoder isn't driven concurrently from multiple threads).
        self._prefill_active: Optional[str] = None
        
        # Cleanup
        self._old_decoder: Optional[VideoDecoder] = None
        self._old_frames: deque[VideoFrame] = deque()
        
        logger.info(f"[VideoStreamer] Initialized with buffer_size={buffer_size}")
    
    def load_video(
        self,
        path: str | Path,
        preload: bool = False,
        *,
        prefill_frames: Optional[int] = None,
        allow_async_open: bool = True,
    ) -> bool:
        """Load video into streamer.
        
        Args:
            path: Path to video file
            preload: If True, load into next buffer (background). If False, load into current.
            prefill_frames: Maximum number of frames to decode synchronously before returning.
                Defaults to ``buffer_size`` (legacy behavior).
        
        Returns:
            True if load successful
        """
        try:
            path_obj = _normalize_path(path)
            decoder = _checkout_cached_decoder(path_obj)
            if decoder is None:
                # Opening cv2.VideoCapture can stall for 100ms+ on some systems.
                # For runtime cycling we prefer to warm up off the UI thread.
                if allow_async_open:
                    try:
                        queue_decoder_warmup(path_obj, priority=True)
                    except Exception:
                        pass
                    return False
                decoder = VideoDecoder(path_obj)
            
            if not decoder.success:
                logger.error(f"[VideoStreamer] Failed to decode: {path}")
                return False
            
            target_buffer = self._next if preload else self._current
            target_name = "next" if preload else "current"

            max_prefill = (
                self.buffer_size
                if prefill_frames is None
                else max(0, min(int(prefill_frames), self.buffer_size))
            )
            env_prefill_limit = VIDEO_PREFILL_FRAME_LIMIT
            env_limit_active = env_prefill_limit > 0 and env_prefill_limit < max_prefill
            prefill_cap = min(max_prefill, env_prefill_limit) if env_limit_active else max_prefill
            prefill_cap = max(0, prefill_cap)
            prefill_budget_ms = VIDEO_PREFILL_BUDGET_MS
            prefill_start = time.perf_counter()
            clipped_by_budget = False

            # Swap decoder/buffer state under lock, but decode frames outside the lock.
            with self._lock:
                self._prefill_active = target_name if prefill_cap > 0 else None

                # Store old decoder for cleanup
                if target_buffer.decoder is not None:
                    self._old_decoder = target_buffer.decoder

                target_buffer.decoder = decoder
                target_buffer.frames.clear()
                target_buffer.begin = 0
                target_buffer.size = 0
                target_buffer.end = False

            # Pre-fill limited number of frames on caller thread.
            # IMPORTANT: Do not hold self._lock while decoding; decoder.next_frame()
            # can stall (IO/codec) and would block get_current_frame() on the UI thread.
            if prefill_cap > 0:
                while True:
                    if prefill_budget_ms > 0:
                        elapsed_ms = (time.perf_counter() - prefill_start) * 1000.0
                        if elapsed_ms >= prefill_budget_ms:
                            clipped_by_budget = True
                            break

                    frame = decoder.next_frame()

                    with self._lock:
                        # If another load replaced the decoder, stop prefill.
                        if target_buffer.decoder is not decoder:
                            break

                        if target_buffer.end or target_buffer.size >= prefill_cap:
                            break

                        if frame is None:
                            target_buffer.end = True
                            break

                        target_buffer.frames.append(frame)
                        target_buffer.size += 1

            with self._lock:
                if self._prefill_active == target_name:
                    self._prefill_active = None
                buffered_frames = int(target_buffer.size)
                buffered_end = bool(target_buffer.end)

            logger.info(
                f"[VideoStreamer] Loaded {path_obj.name} - buffered {buffered_frames} frames "
                f"(prefill cap={prefill_cap}), end={buffered_end}"
            )

            elapsed_ms = (time.perf_counter() - prefill_start) * 1000.0
            frame_limit_hit = env_limit_active and (not buffered_end) and buffered_frames >= prefill_cap
            if clipped_by_budget or frame_limit_hit:
                reason = "budget" if clipped_by_budget else "frame_limit"
                logger.warning(
                    "[visual.perf] video.prefill clipped (%s): %.2fms, frames=%d, limit=%s, budget=%s",
                    reason,
                    elapsed_ms,
                    buffered_frames,
                    str(env_prefill_limit) if env_prefill_limit > 0 else "n/a",
                    f"{prefill_budget_ms:.1f}ms" if prefill_budget_ms > 0 else "disabled",
                )
            
            # Start async loader thread if not running
            if not self._loader_running:
                self._start_loader_thread()
            
            return True
        
        except Exception as e:
            logger.error(f"[VideoStreamer] Load failed: {e}")
            return False
    
    def get_current_frame(self) -> Optional[VideoFrame]:
        """Get current video frame for rendering.
        
        Returns:
            VideoFrame at current playback position, or None if no video loaded
        """
        with self._lock:
            if self._current.size == 0:
                return None
            
            # Return frame at current index (within circular buffer)
            return self._current.frames[self._index % len(self._current.frames)]
    
    def advance_frame(self, global_fps: float = 60.0, maybe_switch: bool = False, 
                     force_switch: bool = False) -> None:
        """Advance playback by one update tick.
        
        Implements Trance's advance_frame() logic:
        - Fractional frame advancement (120/global_fps/8 per tick)
        - Ping-pong direction reversal at endpoints
        - Automatic video switching when conditions met
        
        Args:
            global_fps: Application frame rate (default 60)
            maybe_switch: Allow video switching if conditions met
            force_switch: Force switch to next video immediately
        """
        with self._lock:
            # Check if we can switch to next video (Trance logic)
            can_switch = (
                self._current.decoder is not None and
                self._next.decoder is not None and
                self._old_decoder is None and
                (not self._current.decoder.success or
                 self._current.size == 0 or
                 (maybe_switch and (self._reached_end or force_switch) and
                  (self._next.end or self._next.size >= self.buffer_size)))
            )
            
            if can_switch:
                # Swap current ↔ next
                self._current, self._next = self._next, self._current
                
                # Reset next buffer for new video
                self._next.begin = 0
                self._next.size = 0
                self._next.end = False
                
                # Reset playback state
                self._reached_end = False
                self._backwards = False
                self._index = 0
                
                # Move old decoder to cleanup queue
                self._old_decoder = self._next.decoder
                for frame in self._next.frames:
                    self._old_frames.append(frame)
                self._next.frames.clear()
                self._next.decoder = None
                
                logger.info("[VideoStreamer] Switched to next video")
            
            # Fractional frame advancement (Trance formula: 120/fps/8)
            # This creates smooth temporal sampling
            # Example at 60fps: 120/60/8 = 0.25 frames per update
            #   → Video frame advances every 4 screen frames
            self._update_counter += (120.0 / global_fps) / 8.0
            
            # Advance frames when counter >= 1.0
            while self._update_counter >= 1.0:
                self._update_counter -= 1.0
                
                if self._current.size == 0:
                    break
                
                # Ping-pong logic: Play forward, then backward, repeat
                buffer_end = (self._current.begin + self._current.size - 1) % self.buffer_size
                
                if self._backwards:
                    # Playing backward
                    if self._index != self._current.begin:
                        self._index = self._prev_index(self._index)
                    else:
                        # Hit beginning → reverse to forward
                        self._backwards = False
                        if self._index != buffer_end:
                            self._index = (self._index + 1) % self.buffer_size
                else:
                    # Playing forward
                    if self._index != buffer_end:
                        self._index = (self._index + 1) % self.buffer_size
                    else:
                        # Hit end → reverse to backward
                        self._backwards = True
                        if self._index != self._current.begin:
                            self._index = self._prev_index(self._index)
            
            # Check if reached end (for switching logic)
            if self._current.end:
                buffer_end = (self._current.begin + self._current.size - 1) % self.buffer_size
                if self._index == buffer_end:
                    self._reached_end = True
    
    def _prev_index(self, idx: int) -> int:
        """Get previous index in circular buffer."""
        return (idx + self.buffer_size - 1) % self.buffer_size
    
    def _start_loader_thread(self) -> None:
        """Start async loader thread for buffer filling."""
        if self._loader_running:
            return
        
        self._loader_running = True
        self._loader_done.clear()
        self._loader_thread = threading.Thread(target=self._async_loader, daemon=True)
        self._loader_thread.start()
        logger.info("[VideoStreamer] Started async loader thread")
    
    def _async_loader(self) -> None:
        """Async thread: Fill buffers and cleanup old frames.
        
        Mimics Trance's async_update() behavior.
        """
        try:
            while self._loader_running:
                try:
                    # Cleanup old decoder/frames (do heavy work outside lock)
                    old_decoder: Optional[VideoDecoder] = None
                    with self._lock:
                        if self._old_decoder is not None:
                            old_decoder = self._old_decoder
                            self._old_decoder = None

                        if self._old_frames:
                            self._old_frames.popleft()  # Gradual cleanup

                    if old_decoder is not None:
                        _return_cached_decoder(old_decoder)

                    if not self._loader_running:
                        break
                    
                    # Fill current buffer if not full (decode outside lock)
                    current_decoder: Optional[VideoDecoder] = None
                    with self._lock:
                        if (
                            self._prefill_active != "current"
                            and self._current.decoder is not None
                            and not self._current.end
                            and self._current.size < self.buffer_size
                        ):
                            current_decoder = self._current.decoder

                    if current_decoder is not None:
                        frame = current_decoder.next_frame()
                        with self._lock:
                            if (
                                self._prefill_active != "current"
                                and self._current.decoder is current_decoder
                                and not self._current.end
                                and self._current.size < self.buffer_size
                            ):
                                if frame is not None:
                                    self._current.frames.append(frame)
                                    self._current.size += 1
                                else:
                                    self._current.end = True

                    if not self._loader_running:
                        break
                    
                    # Fill next buffer if not full (decode outside lock)
                    next_decoder: Optional[VideoDecoder] = None
                    with self._lock:
                        if (
                            self._prefill_active != "next"
                            and self._next.decoder is not None
                            and not self._next.end
                            and self._next.size < self.buffer_size
                        ):
                            next_decoder = self._next.decoder

                    if next_decoder is not None:
                        frame = next_decoder.next_frame()
                        with self._lock:
                            if (
                                self._prefill_active != "next"
                                and self._next.decoder is next_decoder
                                and not self._next.end
                                and self._next.size < self.buffer_size
                            ):
                                if frame is not None:
                                    self._next.frames.append(frame)
                                    self._next.size += 1
                                else:
                                    self._next.end = True
                    
                    # Sleep to avoid spinning (Trance uses 1ms)
                    time.sleep(0.001)
                
                except Exception as e:
                    logger.error(f"[VideoStreamer] Async loader error: {e}")
                    time.sleep(0.1)
        finally:
            self._loader_done.set()
    
    def stop(self) -> None:
        """Stop async loader and cleanup resources."""
        self._loader_running = False
        if self._loader_thread is not None:
            if not self._loader_done.wait(timeout=3.0):
                logger.warning("[VideoStreamer] Loader thread did not exit within 3s; skipping aggressive cleanup")
            self._loader_thread.join(timeout=0.5)
        thread_alive = self._loader_thread is not None and self._loader_thread.is_alive()
        
        with self._lock:
            if not thread_alive:
                if self._current.decoder is not None:
                    self._current.decoder.close()
                if self._next.decoder is not None:
                    self._next.decoder.close()
                if self._old_decoder is not None:
                    self._old_decoder.close()
            else:
                logger.warning("[VideoStreamer] Skipping decoder close while loader thread is still alive")
            
            self._current.frames.clear()
            self._next.frames.clear()
            self._old_frames.clear()

        if self._loader_thread is not None and not thread_alive:
            self._loader_thread = None
        
        logger.info("[VideoStreamer] Stopped")
    
    def get_info(self) -> dict:
        """Get current playback info for debugging/UI.
        
        Returns:
            Dict with current state (frame counts, direction, etc.)
        """
        with self._lock:
            return {
                'current_size': self._current.size,
                'current_end': self._current.end,
                'next_size': self._next.size,
                'next_end': self._next.end,
                'index': self._index,
                'backwards': self._backwards,
                'reached_end': self._reached_end,
                'update_counter': self._update_counter,
                'current_video': self._current.decoder.path.name if self._current.decoder else None,
                'next_video': self._next.decoder.path.name if self._next.decoder else None,
            }


@dataclass
class AnimationBuffer:
    """Buffer for one video's frames (Trance's Animation struct).
    
    Attributes:
        decoder: VideoDecoder instance
        frames: Circular buffer of frames
        begin: Start index in buffer
        size: Number of frames currently in buffer
        end: True if reached end of video
    """
    buffer_size: int
    decoder: Optional[VideoDecoder] = None
    frames: list = None  # Will be list[VideoFrame]
    begin: int = 0
    size: int = 0
    end: bool = False
    
    def __post_init__(self):
        if self.frames is None:
            self.frames = []
