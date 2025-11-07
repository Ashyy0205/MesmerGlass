"""Text animation and effects system.

This module provides text animation effects including:
- Fade in/out
- Flash (rapid on/off)
- Slow flash (alternating speeds)
- Pulse (scale oscillation)
- Wobble (position oscillation)
- Drift (continuous movement)
- Zoom (scaling with background)
- Text sequences with timing

Based on Trance's FlashTextVisual, SlowFlashVisual, and text cycling system.
"""

import math
from typing import Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass


class TextEffect(Enum):
    """Text animation effects."""
    NONE = 0            # No animation
    FADE_IN = 1         # Fade from transparent to opaque
    FADE_OUT = 2        # Fade from opaque to transparent
    FLASH = 3           # Rapid on/off flashing
    SLOW_FLASH = 4      # Alternating slow/fast pulses
    PULSE = 5           # Smooth scale oscillation
    WOBBLE = 6          # Position wobble
    DRIFT = 7           # Continuous XY drift
    ZOOM = 8            # Scale with background zoom
    TYPEWRITER = 9      # Character-by-character reveal


@dataclass
class EffectConfig:
    """Configuration for text effects."""
    # Fade settings
    fade_duration: float = 1.0          # Fade in/out duration (seconds)
    
    # Flash settings
    flash_rate: float = 0.1             # Flash on/off interval (seconds)
    slow_flash_slow: float = 0.5        # Slow flash duration
    slow_flash_fast: float = 0.1        # Fast flash duration
    
    # Pulse settings
    pulse_scale_min: float = 0.95       # Minimum scale
    pulse_scale_max: float = 1.05       # Maximum scale
    pulse_duration: float = 1.0         # Full pulse cycle duration
    
    # Wobble settings
    wobble_amount: float = 2.0          # Wobble distance (pixels)
    wobble_speed: float = 2.0           # Wobble frequency (Hz)
    
    # Drift settings
    drift_speed_x: float = 10.0         # Horizontal drift (pixels/second)
    drift_speed_y: float = 5.0          # Vertical drift (pixels/second)
    
    # Typewriter settings
    typewriter_cps: float = 15.0        # Characters per second (increased from 10)
    
    # Zoom settings
    zoom_scale_min: float = 0.8         # Minimum scale
    zoom_scale_max: float = 1.2         # Maximum scale
    zoom_duration: float = 2.0          # Full zoom cycle duration
    
    # Fill screen carousel settings
    carousel_speed: float = 20.0        # Scroll speed (pixels/second)


@dataclass
class TextSequenceItem:
    """A single item in a text sequence."""
    text: str                           # Text to display
    duration: float                     # How long to show (seconds, 0 = forever)
    effect: TextEffect = TextEffect.NONE  # Effect to apply
    split_index: int = -1               # For split modes: which word/line to show (-1 = all)


class TextAnimator:
    """Manages text animation effects and sequences.
    
    This class handles:
    - Visual effects (fade, flash, pulse, etc.)
    - Text sequences with timing
    - Spiral rotation speed coordination (Trance compatibility)
    - Alpha/scale/position transformations
    
    Usage:
        animator = TextAnimator()
        
        # Add sequence
        animator.add_sequence_item("Hello", duration=2.0, effect=TextEffect.FADE_IN)
        animator.add_sequence_item("World", duration=2.0, effect=TextEffect.PULSE)
        
        # Update each frame
        animator.update(delta_time)
        
        # Get current state
        alpha, scale, offset = animator.get_transform()
    """
    
    def __init__(self):
        """Initialize text animator."""
        self._config = EffectConfig()
        self._current_effect = TextEffect.NONE
        self._elapsed = 0.0                # Time in current effect
        self._total_elapsed = 0.0          # Total time
        
        # Sequence management
        self._sequence: List[TextSequenceItem] = []
        self._current_sequence_index = 0
        self._sequence_elapsed = 0.0       # Time in current sequence item
        self._sequence_loop = True
        
        # Transform state
        self._alpha = 1.0
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        
        # Typewriter state
        self._typewriter_chars_shown = 0
        self._typewriter_total_chars = 0
        
        # Flash state (for slow flash alternation)
        self._flash_phase = 0  # 0 = slow, 1 = fast
    
    def set_config(self, config: EffectConfig):
        """Update effect configuration."""
        self._config = config
    
    def get_config(self) -> EffectConfig:
        """Get current effect configuration."""
        return self._config
    
    def set_effect(self, effect: TextEffect):
        """Change current effect.
        
        Args:
            effect: New effect to apply
        """
        if effect != self._current_effect:
            self._current_effect = effect
            self._elapsed = 0.0
            self._reset_effect_state()
    
    def _reset_effect_state(self):
        """Reset effect-specific state."""
        self._alpha = 1.0
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._typewriter_chars_shown = 0
        self._flash_phase = 0
    
    def add_sequence_item(self, text: str, duration: float, 
                         effect: TextEffect = TextEffect.NONE,
                         split_index: int = -1):
        """Add item to text sequence.
        
        Args:
            text: Text to display
            duration: How long to show (0 = forever)
            effect: Effect to apply
            split_index: For split modes, which part to show
        """
        self._sequence.append(TextSequenceItem(text, duration, effect, split_index))
    
    def clear_sequence(self):
        """Clear text sequence."""
        self._sequence.clear()
        self._current_sequence_index = 0
        self._sequence_elapsed = 0.0
    
    def set_sequence_loop(self, loop: bool):
        """Enable/disable sequence looping."""
        self._sequence_loop = loop
    
    def get_current_sequence_item(self) -> Optional[TextSequenceItem]:
        """Get current sequence item.
        
        Returns:
            Current sequence item, or None if sequence empty/finished
        """
        if not self._sequence:
            return None
        
        if self._current_sequence_index >= len(self._sequence):
            if self._sequence_loop:
                self._current_sequence_index = 0
            else:
                return None
        
        return self._sequence[self._current_sequence_index]
    
    def update(self, dt: float):
        """Update animation state.
        
        Args:
            dt: Delta time (seconds)
        """
        self._elapsed += dt
        self._total_elapsed += dt
        
        # Update sequence
        if self._sequence:
            self._sequence_elapsed += dt
            
            current_item = self.get_current_sequence_item()
            if current_item:
                # Auto-advance sequence
                if current_item.duration > 0 and self._sequence_elapsed >= current_item.duration:
                    self._current_sequence_index += 1
                    self._sequence_elapsed = 0.0
                    self._reset_effect_state()
                    
                    # Update effect
                    next_item = self.get_current_sequence_item()
                    if next_item:
                        self._current_effect = next_item.effect
                else:
                    # Use current item's effect
                    self._current_effect = current_item.effect
        
        # Apply effect
        self._update_effect(dt)
    
    def _update_effect(self, dt: float):
        """Update current effect state."""
        if self._current_effect == TextEffect.NONE:
            self._alpha = 1.0
            self._scale = 1.0
            self._offset_x = 0.0
            self._offset_y = 0.0
        
        elif self._current_effect == TextEffect.FADE_IN:
            # Fade from 0 to 1
            progress = min(1.0, self._elapsed / self._config.fade_duration)
            self._alpha = progress
        
        elif self._current_effect == TextEffect.FADE_OUT:
            # Fade from 1 to 0
            progress = min(1.0, self._elapsed / self._config.fade_duration)
            self._alpha = 1.0 - progress
        
        elif self._current_effect == TextEffect.FLASH:
            # Rapid on/off flashing (Trance FlashTextVisual)
            cycle_time = self._elapsed % (self._config.flash_rate * 2)
            self._alpha = 1.0 if cycle_time < self._config.flash_rate else 0.0
        
        elif self._current_effect == TextEffect.SLOW_FLASH:
            # Alternating slow/fast pulses (Trance SlowFlashVisual)
            if self._flash_phase == 0:
                # Slow phase
                cycle_time = self._elapsed % (self._config.slow_flash_slow * 2)
                self._alpha = 1.0 if cycle_time < self._config.slow_flash_slow else 0.0
                
                # Check for phase switch
                if self._elapsed >= self._config.slow_flash_slow * 2:
                    self._flash_phase = 1
                    self._elapsed = 0.0
            else:
                # Fast phase
                cycle_time = self._elapsed % (self._config.slow_flash_fast * 2)
                self._alpha = 1.0 if cycle_time < self._config.slow_flash_fast else 0.0
                
                # Check for phase switch
                if self._elapsed >= self._config.slow_flash_fast * 2:
                    self._flash_phase = 0
                    self._elapsed = 0.0
        
        elif self._current_effect == TextEffect.PULSE:
            # Smooth scale oscillation (sine wave)
            progress = (self._elapsed / self._config.pulse_duration) * 2.0 * math.pi
            scale_range = self._config.pulse_scale_max - self._config.pulse_scale_min
            self._scale = self._config.pulse_scale_min + (math.sin(progress) * 0.5 + 0.5) * scale_range
        
        elif self._current_effect == TextEffect.WOBBLE:
            # Position wobble (sine wave in X and Y)
            progress = self._elapsed * self._config.wobble_speed * 2.0 * math.pi
            self._offset_x = math.sin(progress) * self._config.wobble_amount
            self._offset_y = math.cos(progress * 1.3) * self._config.wobble_amount  # Different frequency
        
        elif self._current_effect == TextEffect.DRIFT:
            # Continuous drift
            self._offset_x += self._config.drift_speed_x * dt
            self._offset_y += self._config.drift_speed_y * dt
        
        elif self._current_effect == TextEffect.ZOOM:
            # Scale oscillation (like pulse but bigger range)
            progress = (self._elapsed / self._config.zoom_duration) * 2.0 * math.pi
            scale_range = self._config.zoom_scale_max - self._config.zoom_scale_min
            self._scale = self._config.zoom_scale_min + (math.sin(progress) * 0.5 + 0.5) * scale_range
        
        elif self._current_effect == TextEffect.TYPEWRITER:
            # Character-by-character reveal
            if self._typewriter_total_chars > 0:
                chars_to_show = int(self._elapsed * self._config.typewriter_cps)
                self._typewriter_chars_shown = min(chars_to_show, self._typewriter_total_chars)
    
    def set_typewriter_length(self, char_count: int):
        """Set total characters for typewriter effect.
        
        Args:
            char_count: Total number of characters in text
        """
        self._typewriter_total_chars = char_count
        self._typewriter_chars_shown = 0
    
    def get_typewriter_chars_shown(self) -> int:
        """Get number of characters to show in typewriter mode."""
        return self._typewriter_chars_shown
    
    def get_transform(self) -> Tuple[float, float, Tuple[float, float]]:
        """Get current transform state.
        
        Returns:
            (alpha, scale, (offset_x, offset_y))
        """
        return (self._alpha, self._scale, (self._offset_x, self._offset_y))
    
    def get_alpha(self) -> float:
        """Get current alpha value (0.0 - 1.0)."""
        return self._alpha
    
    def get_scale(self) -> float:
        """Get current scale multiplier."""
        return self._scale
    
    def get_offset(self) -> Tuple[float, float]:
        """Get current position offset (x, y)."""
        return (self._offset_x, self._offset_y)
    
    def reset(self):
        """Reset animator to initial state."""
        self._elapsed = 0.0
        self._total_elapsed = 0.0
        self._current_sequence_index = 0
        self._sequence_elapsed = 0.0
        self._reset_effect_state()
    
    def get_spiral_speed(self) -> float:
        """Get recommended spiral rotation speed for current effect.
        
        This provides compatibility with Trance's visual programs
        which coordinate spiral speed with text effects.
        
        Returns:
            Spiral rotation speed multiplier
        """
        # From SPIRAL_AND_MEDIA_DOCUMENTATION.md:
        # FlashTextVisual: spiral speed 2.5
        # SlowFlashVisual: alternates between 2.0 (slow) and 4.0 (fast)
        
        if self._current_effect == TextEffect.FLASH:
            return 2.5
        elif self._current_effect == TextEffect.SLOW_FLASH:
            return 2.0 if self._flash_phase == 0 else 4.0
        elif self._current_effect == TextEffect.PULSE:
            return 1.5  # Slightly faster for pulse
        elif self._current_effect == TextEffect.ZOOM:
            return 1.3  # Slightly faster for zoom
        else:
            return 1.0  # Normal speed
    
    def get_info(self) -> dict:
        """Get debug information.
        
        Returns:
            Dictionary with current state
        """
        current_item = self.get_current_sequence_item()
        
        return {
            'effect': self._current_effect.name,
            'elapsed': self._elapsed,
            'total_elapsed': self._total_elapsed,
            'alpha': self._alpha,
            'scale': self._scale,
            'offset': (self._offset_x, self._offset_y),
            'sequence_index': self._current_sequence_index,
            'sequence_count': len(self._sequence),
            'sequence_elapsed': self._sequence_elapsed,
            'current_text': current_item.text if current_item else None,
            'spiral_speed': self.get_spiral_speed(),
        }
