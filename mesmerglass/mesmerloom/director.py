"""
Visual program director with FPS-independent timing control.

Manages execution of visual programs with frame accumulator pattern,
decoupling logical frame updates from screen refresh rate.
"""

import time
from typing import Optional
from .cyclers import Cycler


class VisualDirector:
    """
    Manages visual program execution with FPS control.
    
    Uses frame accumulator pattern to maintain consistent logical frame
    timing regardless of actual screen refresh rate. This ensures that
    animations run at the same speed whether the display is 30Hz, 60Hz,
    or 144Hz.
    
    Example:
        # Create director at 60 logical fps
        director = VisualDirector(global_fps=60)
        
        # Set a visual program with cycler
        director.set_visual(my_visual_cycler)
        
        # In render loop (called at screen refresh rate):
        def render():
            director.update()  # Advances logical frames as needed
            # ... render current state ...
    
    Args:
        global_fps: Logical frames per second for animations (default: 60)
    """
    
    def __init__(self, global_fps: int = 60):
        if global_fps <= 0:
            raise ValueError(f"global_fps must be positive, got {global_fps}")
        
        self.global_fps = global_fps
        self._frame_duration = 1.0 / global_fps  # Seconds per logical frame
        
        # Current visual program
        self._current_visual: Optional[Cycler] = None
        
        # Frame accumulator for FPS independence
        self._frame_accumulator = 0.0
        self._last_update_time = time.perf_counter()
        
        # Statistics
        self._total_frames = 0
        self._start_time = time.perf_counter()
    
    def set_visual(self, visual: Cycler) -> None:
        """
        Set the current visual program.
        
        Args:
            visual: Cycler representing the visual program to execute
        """
        self._current_visual = visual
        self._frame_accumulator = 0.0
        self._last_update_time = time.perf_counter()
    
    def update(self) -> None:
        """
        Update visual state based on elapsed time.
        
        Called once per render frame. Accumulates time and advances
        logical frames as needed to maintain consistent animation speed.
        
        Example:
            # At 60Hz screen refresh with 60 logical fps: advances 1 frame
            # At 30Hz screen refresh with 60 logical fps: advances 2 frames
            # At 144Hz screen refresh with 60 logical fps: advances ~0.4 frames
        """
        if self._current_visual is None:
            return
        
        # Calculate elapsed time since last update
        now = time.perf_counter()
        dt = now - self._last_update_time
        self._last_update_time = now
        
        # Accumulate fractional frames based on elapsed time
        # Example: dt=0.0333s at 60fps → accumulator += 2.0 frames
        self._frame_accumulator += dt / self._frame_duration
        
        # Advance logical frames (integer steps only)
        frames_to_advance = int(self._frame_accumulator)
        if frames_to_advance > 0:
            # Clamp to prevent runaway updates after long pauses
            # (e.g., if app was suspended for 10 seconds)
            max_frames_per_update = self.global_fps  # Max 1 second of catch-up
            frames_to_advance = min(frames_to_advance, max_frames_per_update)
            
            for _ in range(frames_to_advance):
                self._current_visual.advance()
                self._total_frames += 1
            
            # Keep fractional remainder for next update
            self._frame_accumulator -= frames_to_advance
    
    def is_complete(self) -> bool:
        """
        Check if current visual program has completed.
        
        Returns:
            True if visual is complete or no visual is set
        """
        if self._current_visual is None:
            return True
        return self._current_visual.complete()
    
    def get_progress(self) -> float:
        """
        Get progress through current visual program.
        
        Returns:
            Progress ratio [0.0 - 1.0], or 1.0 if no visual
        """
        if self._current_visual is None:
            return 1.0
        return self._current_visual.progress()
    
    def get_frame_count(self) -> int:
        """
        Get total logical frames advanced since creation.
        
        Returns:
            Total frame count
        """
        return self._total_frames
    
    def get_runtime_seconds(self) -> float:
        """
        Get runtime in seconds since creation.
        
        Returns:
            Elapsed seconds
        """
        return time.perf_counter() - self._start_time
    
    def get_average_fps(self) -> float:
        """
        Get average logical FPS since creation.
        
        Returns:
            Average frames per second
        """
        runtime = self.get_runtime_seconds()
        if runtime <= 0:
            return 0.0
        return self._total_frames / runtime
    
    def reset(self) -> None:
        """
        Reset director state.
        
        Clears current visual and resets statistics.
        """
        self._current_visual = None
        self._frame_accumulator = 0.0
        self._last_update_time = time.perf_counter()
        self._total_frames = 0
        self._start_time = time.perf_counter()
    
    def set_fps(self, fps: int) -> None:
        """
        Change logical FPS.
        
        Args:
            fps: New frames per second
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        
        self.global_fps = fps
        self._frame_duration = 1.0 / fps
    
    def __repr__(self) -> str:
        return (
            f"VisualDirector(global_fps={self.global_fps}, "
            f"frames={self._total_frames}, "
            f"runtime={self.get_runtime_seconds():.2f}s)"
        )
