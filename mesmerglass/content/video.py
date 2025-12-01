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
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)
VIDEO_IO_LOCK = threading.Lock()


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
        self.path = Path(path)
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
        
        # Cleanup
        self._old_decoder: Optional[VideoDecoder] = None
        self._old_frames: deque[VideoFrame] = deque()
        
        logger.info(f"[VideoStreamer] Initialized with buffer_size={buffer_size}")
    
    def load_video(self, path: str | Path, preload: bool = False, *, prefill_frames: Optional[int] = None) -> bool:
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
            decoder = VideoDecoder(path)
            
            if not decoder.success:
                logger.error(f"[VideoStreamer] Failed to decode: {path}")
                return False
            
            target_buffer = self._next if preload else self._current

            max_prefill = self.buffer_size if prefill_frames is None else max(1, min(prefill_frames, self.buffer_size))
            env_prefill_limit = VIDEO_PREFILL_FRAME_LIMIT
            env_limit_active = env_prefill_limit > 0 and env_prefill_limit < max_prefill
            prefill_cap = min(max_prefill, env_prefill_limit) if env_limit_active else max_prefill
            prefill_cap = max(1, prefill_cap)
            prefill_budget_ms = VIDEO_PREFILL_BUDGET_MS
            prefill_start = time.perf_counter()
            clipped_by_budget = False

            with self._lock:
                # Store old decoder for cleanup
                if target_buffer.decoder is not None:
                    self._old_decoder = target_buffer.decoder
                
                target_buffer.decoder = decoder
                target_buffer.frames.clear()
                target_buffer.begin = 0
                target_buffer.size = 0
                target_buffer.end = False
                
                # Pre-fill limited number of frames on caller thread to avoid UI stalls
                while not target_buffer.end and target_buffer.size < prefill_cap:
                    frame = decoder.next_frame()
                    if frame is not None:
                        target_buffer.frames.append(frame)
                        target_buffer.size += 1
                    else:
                        target_buffer.end = True
                        break

                    if prefill_budget_ms > 0:
                        elapsed_ms = (time.perf_counter() - prefill_start) * 1000.0
                        if elapsed_ms >= prefill_budget_ms:
                            clipped_by_budget = True
                            break
                
                logger.info(f"[VideoStreamer] Loaded {path.name if isinstance(path, Path) else Path(path).name} - "
                           f"buffered {target_buffer.size} frames (prefill cap={prefill_cap}), end={target_buffer.end}")

                elapsed_ms = (time.perf_counter() - prefill_start) * 1000.0
                frame_limit_hit = env_limit_active and not target_buffer.end and target_buffer.size >= prefill_cap
                if clipped_by_budget or frame_limit_hit:
                    reason = "budget" if clipped_by_budget else "frame_limit"
                    logger.warning(
                        "[visual.perf] video.prefill clipped (%s): %.2fms, frames=%d, limit=%s, budget=%s",
                        reason,
                        elapsed_ms,
                        target_buffer.size,
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
                    # Cleanup old decoder/frames
                    with self._lock:
                        if self._old_decoder is not None:
                            self._old_decoder.close()
                            self._old_decoder = None
                        
                        if self._old_frames:
                            self._old_frames.popleft()  # Gradual cleanup

                    if not self._loader_running:
                        break
                    
                    # Fill current buffer if not full
                    with self._lock:
                        if (self._current.decoder is not None and 
                            not self._current.end and 
                            self._current.size < self.buffer_size):
                            
                            frame = self._current.decoder.next_frame()
                            if frame is not None:
                                self._current.frames.append(frame)
                                self._current.size += 1
                            else:
                                self._current.end = True

                    if not self._loader_running:
                        break
                    
                    # Fill next buffer if not full
                    with self._lock:
                        if (self._next.decoder is not None and 
                            not self._next.end and 
                            self._next.size < self.buffer_size):
                            
                            frame = self._next.decoder.next_frame()
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
