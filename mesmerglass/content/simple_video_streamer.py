"""Simple video streamer with forward-only looping (no ping-pong).

This is a simplified wrapper around VideoStreamer that disables
ping-pong playback mode. Videos loop forward continuously.

Used by visual programs that don't need ping-pong behavior.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from .video import VideoStreamer, VideoFrame

logger = logging.getLogger(__name__)


class SimpleVideoStreamer:
    """Simple video streamer with forward-only looping.
    
    Wraps VideoStreamer but disables ping-pong behavior.
    Videos play forward and loop at the end.
    
    Usage:
        streamer = SimpleVideoStreamer()
        streamer.load_video("path/to/video.mp4")
        
        # In render loop (60 FPS):
        streamer.update()
        frame = streamer.get_current_frame()
        if frame:
            upload_to_gpu(frame.data)
    """
    
    def __init__(self, buffer_size: int = 120, prefill_frames: Optional[int] = None):
        """Initialize simple streamer.
        
        Args:
            buffer_size: Number of frames to buffer (default 120)
        """
        self._streamer = VideoStreamer(buffer_size=buffer_size)
        self._prefill_frames = prefill_frames
        self._current_video_path: Optional[Path] = None
        self._frame_counter = 0.0
        
        logger.info(
            "[SimpleVideoStreamer] Initialized (forward-only mode, buffer=%d, prefill=%s)",
            buffer_size,
            "auto" if prefill_frames is None else prefill_frames,
        )
    
    def load_video(self, path: str | Path) -> bool:
        """Load video for playback.
        
        Args:
            path: Path to video file (MP4, WebM, GIF)
        
        Returns:
            True if successful
        """
        path = Path(path)
        result = self._streamer.load_video(path, preload=False, prefill_frames=self._prefill_frames)
        
        if result:
            self._current_video_path = path
            self._frame_counter = 0.0
            logger.info(f"[SimpleVideoStreamer] Loaded: {path.name}")
        
        return result
    
    def get_current_frame(self) -> Optional[VideoFrame]:
        """Get current video frame.
        
        Returns:
            VideoFrame with RGB data, or None if no video loaded
        """
        return self._streamer.get_current_frame()
    
    def update(self, global_fps: float = 60.0) -> None:
        """Advance playback by one frame.
        
        Uses fractional frame advancement for smooth playback:
        counter += (120.0 / global_fps) / 8.0
        
        When counter >= 1.0, advance to next frame and loop at end.
        
        Args:
            global_fps: Current application FPS (default 60.0)
        """
        # Fractional frame advancement (Trance formula)
        # At 60 FPS: (120 / 60) / 8 = 0.25 per update
        # This means advance 1 video frame every 4 updates (15 FPS video playback)
        frame_increment = (120.0 / global_fps) / 8.0
        self._frame_counter += frame_increment
        
        # Advance frame when counter >= 1.0
        if self._frame_counter >= 1.0:
            self._frame_counter -= 1.0
            
            # Get current state
            info = self._streamer.get_info()
            current_idx = info.get('index', 0)
            buffer_size = info.get('current_size', 0)
            
            if buffer_size > 0:
                # Move to next frame
                next_idx = (current_idx + 1) % buffer_size
                
                # Manually update index (since we're not using ping-pong)
                with self._streamer._lock:
                    self._streamer._index = next_idx
                    
                    # If we wrapped around, video looped
                    if next_idx == 0:
                        logger.debug(f"[SimpleVideoStreamer] Looped: {self._current_video_path.name if self._current_video_path else 'unknown'}")
    
    def reset(self) -> None:
        """Reset playback to beginning."""
        with self._streamer._lock:
            self._streamer._index = 0
            self._streamer._backwards = False
            self._streamer._reached_end = False
            self._frame_counter = 0.0
        
        logger.debug("[SimpleVideoStreamer] Reset to start")
    
    def stop(self) -> None:
        """Stop playback and cleanup resources."""
        self._streamer.stop()
        self._current_video_path = None
        self._frame_counter = 0.0
        
        logger.info("[SimpleVideoStreamer] Stopped")
    
    def get_current_video_path(self) -> Optional[Path]:
        """Get path of currently loaded video.
        
        Returns:
            Path object or None
        """
        return self._current_video_path
    
    def is_loaded(self) -> bool:
        """Check if video is loaded.
        
        Returns:
            True if video loaded and ready
        """
        info = self._streamer.get_info()
        return info.get('current_size', 0) > 0
    
    def get_frame_count(self) -> int:
        """Get number of buffered frames.
        
        Returns:
            Frame count
        """
        info = self._streamer.get_info()
        return info.get('current_size', 0)
    
    # ===== GPU Upload Helper =====
    
    @staticmethod
    def upload_frame_to_gpu(frame: VideoFrame, gl_context) -> Optional[int]:
        """Upload video frame to OpenGL texture.
        
        Args:
            frame: VideoFrame to upload
            gl_context: ModernGL context
        
        Returns:
            Texture ID, or None if failed
        """
        try:
            # Create texture
            texture = gl_context.texture(
                size=(frame.width, frame.height),
                components=3,  # RGB
                data=frame.data.tobytes()
            )
            
            # Set filtering
            texture.filter = (gl_context.LINEAR, gl_context.LINEAR)
            
            return texture
        
        except Exception as e:
            logger.error(f"[SimpleVideoStreamer] GPU upload failed: {e}")
            return None
