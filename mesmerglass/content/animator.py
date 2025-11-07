"""Background animation system for zoom and drift effects.

This module provides the BackgroundAnimator class which handles various animation
patterns for background media (images/videos):

- None: Static background (no animation)
- CenterZoom: Smooth zoom in/out with hold periods at start/end
- Drift: Continuous XY panning with configurable speed
- Random: Randomized zoom and drift changes at intervals

Based on Trance's zoom_intensity formula:
    final_zoom = zoom_origin + (zoom - zoom_origin) * intensity
"""

import time
import random
from enum import Enum
from typing import Tuple
from dataclasses import dataclass


class AnimationPattern(Enum):
    """Available background animation patterns."""
    NONE = 0
    CENTER_ZOOM = 1
    DRIFT = 2
    RANDOM = 3


@dataclass
class CenterZoomConfig:
    """Configuration for center zoom animation."""
    start_zoom: float = 1.0      # Initial zoom level (1.0 = no zoom)
    end_zoom: float = 1.5        # Final zoom level
    duration: float = 8.0        # Duration of zoom transition (seconds)
    hold_start: float = 2.0      # Hold time at start_zoom (seconds)
    hold_end: float = 2.0        # Hold time at end_zoom (seconds)
    loop: bool = True            # Loop animation


@dataclass
class DriftConfig:
    """Configuration for drift animation."""
    x_speed: float = 0.5         # Horizontal drift speed
    y_speed: float = 0.3         # Vertical drift speed
    drift_scale: float = 0.3     # Maximum drift distance (0.0-1.0)


@dataclass
class RandomConfig:
    """Configuration for random animation."""
    change_interval: float = 12.0  # Time between random changes (seconds)
    max_zoom: float = 1.8          # Maximum zoom level
    max_drift: float = 0.5         # Maximum drift distance


class BackgroundAnimator:
    """Manages background animation patterns with smooth interpolation.
    
    This class handles various animation patterns for background media,
    providing zoom and offset values that can be applied to the compositor.
    
    Usage:
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        animator.center_zoom_config.duration = 10.0
        
        # In update loop (60 FPS):
        zoom, offset = animator.update(dt=1/60)
        compositor.set_background_zoom(zoom)
        compositor.set_background_offset(offset[0], offset[1])
    """
    
    def __init__(self):
        """Initialize background animator with default settings."""
        # Current pattern
        self._pattern = AnimationPattern.NONE
        
        # Pattern configurations
        self.center_zoom_config = CenterZoomConfig()
        self.drift_config = DriftConfig()
        self.random_config = RandomConfig()
        
        # Animation state
        self._elapsed = 0.0          # Time elapsed in current animation phase
        self._current_zoom = 1.0     # Current zoom level
        self._current_offset = [0.0, 0.0]  # Current XY offset
        self._target_zoom = 1.0      # Target zoom for interpolation
        self._target_offset = [0.0, 0.0]   # Target offset for interpolation
        self._phase = 0              # Current animation phase (for multi-stage patterns)
        self._direction = 1          # Animation direction (1=forward, -1=reverse)
        
        # Random state
        self._last_random_change = 0.0
    
    def set_pattern(self, pattern: AnimationPattern) -> None:
        """Change animation pattern.
        
        Args:
            pattern: New animation pattern to use
        """
        if pattern == self._pattern:
            return
        
        self._pattern = pattern
        self._reset_state()
    
    def get_pattern(self) -> AnimationPattern:
        """Get current animation pattern."""
        return self._pattern
    
    def _reset_state(self) -> None:
        """Reset animation state when pattern changes."""
        self._elapsed = 0.0
        self._current_zoom = 1.0
        self._current_offset = [0.0, 0.0]
        self._target_zoom = 1.0
        self._target_offset = [0.0, 0.0]
        self._phase = 0
        self._direction = 1
        self._last_random_change = 0.0
    
    def update(self, dt: float) -> Tuple[float, Tuple[float, float]]:
        """Update animation and return current zoom and offset.
        
        Args:
            dt: Delta time since last update (seconds)
        
        Returns:
            Tuple of (zoom, (offset_x, offset_y))
        """
        self._elapsed += dt
        
        if self._pattern == AnimationPattern.NONE:
            return self._update_none()
        elif self._pattern == AnimationPattern.CENTER_ZOOM:
            return self._update_center_zoom(dt)
        elif self._pattern == AnimationPattern.DRIFT:
            return self._update_drift(dt)
        elif self._pattern == AnimationPattern.RANDOM:
            return self._update_random(dt)
        
        return 1.0, (0.0, 0.0)
    
    def _update_none(self) -> Tuple[float, Tuple[float, float]]:
        """No animation - return static values."""
        return 1.0, (0.0, 0.0)
    
    def _update_center_zoom(self, dt: float) -> Tuple[float, Tuple[float, float]]:
        """Update center zoom animation.
        
        Animation phases:
        0: Hold at start_zoom
        1: Zoom from start to end
        2: Hold at end_zoom
        3: Zoom from end to start (if looping)
        """
        cfg = self.center_zoom_config
        
        # Phase 0: Hold at start
        if self._phase == 0:
            self._current_zoom = cfg.start_zoom
            if self._elapsed >= cfg.hold_start:
                self._elapsed = 0.0
                self._phase = 1
                self._direction = 1
        
        # Phase 1: Zoom in (start -> end)
        elif self._phase == 1:
            progress = min(1.0, self._elapsed / cfg.duration)
            # Smooth interpolation (ease in/out)
            progress = self._ease_in_out(progress)
            self._current_zoom = cfg.start_zoom + (cfg.end_zoom - cfg.start_zoom) * progress
            
            if self._elapsed >= cfg.duration:
                self._current_zoom = cfg.end_zoom
                self._elapsed = 0.0
                self._phase = 2
        
        # Phase 2: Hold at end
        elif self._phase == 2:
            self._current_zoom = cfg.end_zoom
            if self._elapsed >= cfg.hold_end:
                self._elapsed = 0.0
                if cfg.loop:
                    self._phase = 3  # Zoom back out
                else:
                    self._phase = 2  # Stay at end
        
        # Phase 3: Zoom out (end -> start)
        elif self._phase == 3:
            progress = min(1.0, self._elapsed / cfg.duration)
            progress = self._ease_in_out(progress)
            self._current_zoom = cfg.end_zoom + (cfg.start_zoom - cfg.end_zoom) * progress
            
            if self._elapsed >= cfg.duration:
                self._current_zoom = cfg.start_zoom
                self._elapsed = 0.0
                self._phase = 0  # Back to start
        
        return self._current_zoom, (0.0, 0.0)
    
    def _update_drift(self, dt: float) -> Tuple[float, Tuple[float, float]]:
        """Update drift animation with continuous XY panning."""
        cfg = self.drift_config
        
        # Update drift offset continuously
        self._current_offset[0] += cfg.x_speed * dt
        self._current_offset[1] += cfg.y_speed * dt
        
        # Wrap around using drift_scale as maximum
        if abs(self._current_offset[0]) > cfg.drift_scale:
            self._current_offset[0] = -cfg.drift_scale if self._current_offset[0] > 0 else cfg.drift_scale
        if abs(self._current_offset[1]) > cfg.drift_scale:
            self._current_offset[1] = -cfg.drift_scale if self._current_offset[1] > 0 else cfg.drift_scale
        
        return 1.0, (self._current_offset[0], self._current_offset[1])
    
    def _update_random(self, dt: float) -> Tuple[float, Tuple[float, float]]:
        """Update random animation with periodic changes."""
        cfg = self.random_config
        
        # Check if it's time for a random change
        if self._elapsed - self._last_random_change >= cfg.change_interval:
            # Generate new random targets
            self._target_zoom = 1.0 + random.random() * (cfg.max_zoom - 1.0)
            self._target_offset[0] = (random.random() - 0.5) * 2.0 * cfg.max_drift
            self._target_offset[1] = (random.random() - 0.5) * 2.0 * cfg.max_drift
            self._last_random_change = self._elapsed
        
        # Smoothly interpolate to target
        interpolation_speed = 2.0  # How fast to reach target
        t = min(1.0, (self._elapsed - self._last_random_change) / interpolation_speed)
        t = self._ease_in_out(t)
        
        # Interpolate zoom
        self._current_zoom = self._current_zoom + (self._target_zoom - self._current_zoom) * t * dt * 5.0
        
        # Interpolate offset
        self._current_offset[0] += (self._target_offset[0] - self._current_offset[0]) * t * dt * 5.0
        self._current_offset[1] += (self._target_offset[1] - self._current_offset[1]) * t * dt * 5.0
        
        return self._current_zoom, (self._current_offset[0], self._current_offset[1])
    
    def _ease_in_out(self, t: float) -> float:
        """Smooth ease-in-out interpolation (cubic).
        
        Args:
            t: Progress value (0.0-1.0)
        
        Returns:
            Smoothed progress value (0.0-1.0)
        """
        if t < 0.5:
            return 4.0 * t * t * t
        else:
            p = 2.0 * t - 2.0
            return 1.0 + p * p * p / 2.0
    
    def get_info(self) -> dict:
        """Get current animation state information.
        
        Returns:
            Dictionary with current state:
            - pattern: Current animation pattern name
            - zoom: Current zoom level
            - offset: Current [x, y] offset
            - phase: Current animation phase
            - elapsed: Time elapsed in current phase
        """
        return {
            'pattern': self._pattern.name,
            'zoom': self._current_zoom,
            'offset': self._current_offset.copy(),
            'phase': self._phase,
            'elapsed': self._elapsed,
        }
