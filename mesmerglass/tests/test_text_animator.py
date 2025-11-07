"""Unit tests for TextAnimator (Phase 3.2)."""

import pytest
import math
from unittest.mock import MagicMock

from ..content.text_animator import (
    TextAnimator,
    TextEffect,
    EffectConfig,
)


@pytest.fixture
def text_animator():
    """Create a TextAnimator instance for testing."""
    return TextAnimator()


@pytest.fixture
def custom_config():
    """Create a custom EffectConfig for testing."""
    return EffectConfig(
        fade_duration=2.0,
        flash_rate=0.2,
        pulse_duration=1.5,
        zoom_duration=3.0,
        typewriter_cps=20.0
    )


class TestTextAnimatorInit:
    """Test TextAnimator initialization."""
    
    def test_init_default_values(self, text_animator):
        """Test default initialization values."""
        assert text_animator._current_effect == TextEffect.NONE
        assert text_animator._time == 0.0
        assert text_animator._alpha == 1.0
        assert text_animator._scale == 1.0
        assert text_animator._offset_x == 0.0
        assert text_animator._offset_y == 0.0
    
    def test_init_with_custom_config(self, custom_config):
        """Test initialization with custom configuration."""
        animator = TextAnimator(config=custom_config)
        assert animator._config.fade_duration == 2.0
        assert animator._config.flash_rate == 0.2
        assert animator._config.pulse_duration == 1.5


class TestEffectConfiguration:
    """Test effect configuration."""
    
    def test_default_effect_config(self):
        """Test default EffectConfig values."""
        config = EffectConfig()
        assert config.fade_duration == 1.0
        assert config.flash_rate == 0.1
        assert config.slow_flash_slow == 0.5
        assert config.slow_flash_fast == 0.1
        assert config.pulse_scale_min == 0.95
        assert config.pulse_scale_max == 1.05
        assert config.pulse_duration == 1.0
        assert config.wobble_amount == 0.02
        assert config.wobble_frequency == 2.0
        assert config.drift_speed == 0.01
        assert config.zoom_scale_min == 0.8
        assert config.zoom_scale_max == 1.2
        assert config.zoom_duration == 2.0
        assert config.typewriter_cps == 15.0
        assert config.carousel_speed == 20.0


class TestEffectSetting:
    """Test setting effects."""
    
    def test_set_effect_none(self, text_animator):
        """Test setting NONE effect."""
        text_animator.set_effect(TextEffect.NONE)
        assert text_animator._current_effect == TextEffect.NONE
        assert text_animator._time == 0.0
    
    def test_set_effect_fade_in(self, text_animator):
        """Test setting FADE_IN effect."""
        text_animator.set_effect(TextEffect.FADE_IN)
        assert text_animator._current_effect == TextEffect.FADE_IN
        assert text_animator._time == 0.0
        assert text_animator._alpha == 0.0  # Starts transparent
    
    def test_set_effect_fade_out(self, text_animator):
        """Test setting FADE_OUT effect."""
        text_animator.set_effect(TextEffect.FADE_OUT)
        assert text_animator._current_effect == TextEffect.FADE_OUT
        assert text_animator._time == 0.0
        assert text_animator._alpha == 1.0  # Starts opaque
    
    def test_set_effect_resets_time(self, text_animator):
        """Test that setting a new effect resets time."""
        text_animator._time = 5.0
        text_animator.set_effect(TextEffect.FLASH)
        assert text_animator._time == 0.0


class TestNoneEffect:
    """Test NONE effect (no animation)."""
    
    def test_none_effect_no_changes(self, text_animator):
        """Test NONE effect keeps default values."""
        text_animator.set_effect(TextEffect.NONE)
        text_animator.update(1.0)
        
        assert text_animator._alpha == 1.0
        assert text_animator._scale == 1.0
        assert text_animator._offset_x == 0.0
        assert text_animator._offset_y == 0.0


class TestFadeInEffect:
    """Test FADE_IN effect."""
    
    def test_fade_in_starts_transparent(self, text_animator):
        """Test FADE_IN starts at alpha=0."""
        text_animator.set_effect(TextEffect.FADE_IN)
        assert text_animator._alpha == 0.0
    
    def test_fade_in_progression(self, text_animator):
        """Test FADE_IN progresses over time."""
        text_animator.set_effect(TextEffect.FADE_IN)
        
        # At 25% duration
        text_animator.update(0.25)
        assert 0.0 < text_animator._alpha < 1.0
        
        # At 50% duration
        text_animator.update(0.25)
        assert 0.0 < text_animator._alpha < 1.0
        
        # At 100% duration
        text_animator.update(0.5)
        assert text_animator._alpha == 1.0
    
    def test_fade_in_completes(self, text_animator):
        """Test FADE_IN reaches full opacity."""
        text_animator.set_effect(TextEffect.FADE_IN)
        text_animator.update(10.0)  # Well past duration
        assert text_animator._alpha == 1.0


class TestFadeOutEffect:
    """Test FADE_OUT effect."""
    
    def test_fade_out_starts_opaque(self, text_animator):
        """Test FADE_OUT starts at alpha=1."""
        text_animator.set_effect(TextEffect.FADE_OUT)
        assert text_animator._alpha == 1.0
    
    def test_fade_out_progression(self, text_animator):
        """Test FADE_OUT progresses over time."""
        text_animator.set_effect(TextEffect.FADE_OUT)
        
        # At 50% duration
        text_animator.update(0.5)
        assert 0.0 < text_animator._alpha < 1.0
        
        # At 100% duration
        text_animator.update(0.5)
        assert text_animator._alpha == 0.0
    
    def test_fade_out_completes(self, text_animator):
        """Test FADE_OUT reaches full transparency."""
        text_animator.set_effect(TextEffect.FADE_OUT)
        text_animator.update(10.0)  # Well past duration
        assert text_animator._alpha == 0.0


class TestFlashEffect:
    """Test FLASH effect."""
    
    def test_flash_toggles(self, text_animator):
        """Test FLASH toggles between on/off."""
        text_animator.set_effect(TextEffect.FLASH)
        
        # First update - should be visible
        text_animator.update(0.05)
        first_alpha = text_animator._alpha
        
        # After flash_rate time - should toggle
        text_animator.update(0.1)
        second_alpha = text_animator._alpha
        
        assert first_alpha != second_alpha
    
    def test_flash_values_binary(self, text_animator):
        """Test FLASH uses binary alpha values."""
        text_animator.set_effect(TextEffect.FLASH)
        
        for _ in range(10):
            text_animator.update(0.05)
            assert text_animator._alpha in [0.0, 1.0]


class TestSlowFlashEffect:
    """Test SLOW_FLASH effect."""
    
    def test_slow_flash_alternates(self, text_animator):
        """Test SLOW_FLASH alternates between slow and fast."""
        text_animator.set_effect(TextEffect.SLOW_FLASH)
        
        # Should alternate between visible and invisible
        alphas = []
        for _ in range(20):
            text_animator.update(0.1)
            alphas.append(text_animator._alpha)
        
        # Should have both 0.0 and 1.0 values
        assert 0.0 in alphas
        assert 1.0 in alphas


class TestPulseEffect:
    """Test PULSE effect."""
    
    def test_pulse_oscillates_scale(self, text_animator):
        """Test PULSE oscillates scale value."""
        text_animator.set_effect(TextEffect.PULSE)
        
        scales = []
        for _ in range(10):
            text_animator.update(0.1)
            scales.append(text_animator._scale)
        
        # Scale should vary
        assert len(set(scales)) > 1
        # Scale should stay within bounds
        for scale in scales:
            assert text_animator._config.pulse_scale_min <= scale <= text_animator._config.pulse_scale_max
    
    def test_pulse_full_cycle(self, text_animator):
        """Test PULSE completes full cycle."""
        text_animator.set_effect(TextEffect.PULSE)
        
        # Record scale at start
        start_scale = text_animator._scale
        
        # Complete full cycle
        text_animator.update(text_animator._config.pulse_duration)
        
        # Should return to approximately same scale
        assert abs(text_animator._scale - start_scale) < 0.01


class TestWobbleEffect:
    """Test WOBBLE effect."""
    
    def test_wobble_moves_position(self, text_animator):
        """Test WOBBLE changes position offset."""
        text_animator.set_effect(TextEffect.WOBBLE)
        
        text_animator.update(0.5)
        
        # At least one offset should be non-zero
        assert text_animator._offset_x != 0.0 or text_animator._offset_y != 0.0
    
    def test_wobble_stays_in_bounds(self, text_animator):
        """Test WOBBLE keeps offsets within bounds."""
        text_animator.set_effect(TextEffect.WOBBLE)
        
        for _ in range(20):
            text_animator.update(0.1)
            assert abs(text_animator._offset_x) <= text_animator._config.wobble_amount
            assert abs(text_animator._offset_y) <= text_animator._config.wobble_amount


class TestDriftEffect:
    """Test DRIFT effect."""
    
    def test_drift_moves_continuously(self, text_animator):
        """Test DRIFT moves position continuously."""
        text_animator.set_effect(TextEffect.DRIFT)
        
        positions = []
        for _ in range(10):
            text_animator.update(0.1)
            positions.append((text_animator._offset_x, text_animator._offset_y))
        
        # Positions should change
        assert len(set(positions)) > 1


class TestZoomEffect:
    """Test ZOOM effect."""
    
    def test_zoom_oscillates_scale(self, text_animator):
        """Test ZOOM oscillates scale value."""
        text_animator.set_effect(TextEffect.ZOOM)
        
        scales = []
        for _ in range(10):
            text_animator.update(0.2)
            scales.append(text_animator._scale)
        
        # Scale should vary
        assert len(set(scales)) > 1
        # Scale should stay within zoom bounds
        for scale in scales:
            assert text_animator._config.zoom_scale_min <= scale <= text_animator._config.zoom_scale_max
    
    def test_zoom_cycles(self, text_animator):
        """Test ZOOM completes cycles."""
        text_animator.set_effect(TextEffect.ZOOM)
        
        start_scale = text_animator._scale
        
        # Complete full cycle
        text_animator.update(text_animator._config.zoom_duration)
        
        # Should return to approximately same scale
        assert abs(text_animator._scale - start_scale) < 0.01


class TestTypewriterEffect:
    """Test TYPEWRITER effect."""
    
    def test_typewriter_reveals_characters(self, text_animator):
        """Test TYPEWRITER reveals characters over time."""
        text_animator.set_effect(TextEffect.TYPEWRITER)
        text_animator.set_typewriter_length(10)
        
        # At start
        assert text_animator.get_typewriter_chars_shown() == 0
        
        # After some time
        text_animator.update(0.2)
        chars_shown = text_animator.get_typewriter_chars_shown()
        assert 0 < chars_shown <= 10
    
    def test_typewriter_respects_length(self, text_animator):
        """Test TYPEWRITER doesn't exceed text length."""
        text_animator.set_effect(TextEffect.TYPEWRITER)
        text_animator.set_typewriter_length(5)
        
        # Update for long time
        text_animator.update(10.0)
        
        assert text_animator.get_typewriter_chars_shown() == 5
    
    def test_typewriter_speed(self, text_animator):
        """Test TYPEWRITER characters-per-second rate."""
        text_animator.set_effect(TextEffect.TYPEWRITER)
        text_animator.set_typewriter_length(100)
        
        # Update for 1 second
        text_animator.update(1.0)
        
        chars_shown = text_animator.get_typewriter_chars_shown()
        # Should show approximately typewriter_cps characters (15 by default)
        assert 10 <= chars_shown <= 20  # Allow some tolerance


class TestTransformRetrieval:
    """Test getting transform values."""
    
    def test_get_transform(self, text_animator):
        """Test get_transform returns correct values."""
        text_animator.set_effect(TextEffect.NONE)
        
        alpha, scale, offset = text_animator.get_transform()
        
        assert alpha == 1.0
        assert scale == 1.0
        assert offset == (0.0, 0.0)
    
    def test_get_scale(self, text_animator):
        """Test get_scale returns current scale."""
        text_animator._scale = 1.5
        assert text_animator.get_scale() == 1.5
    
    def test_get_typewriter_chars_shown(self, text_animator):
        """Test get_typewriter_chars_shown."""
        text_animator.set_effect(TextEffect.TYPEWRITER)
        text_animator.set_typewriter_length(10)
        
        chars = text_animator.get_typewriter_chars_shown()
        assert chars >= 0


class TestSpiralSpeedCoordination:
    """Test spiral speed coordination."""
    
    def test_get_recommended_spiral_speed_none(self, text_animator):
        """Test recommended spiral speed for NONE effect."""
        text_animator.set_effect(TextEffect.NONE)
        assert text_animator.get_recommended_spiral_speed() == 1.0
    
    def test_get_recommended_spiral_speed_flash(self, text_animator):
        """Test recommended spiral speed for FLASH effect."""
        text_animator.set_effect(TextEffect.FLASH)
        assert text_animator.get_recommended_spiral_speed() == 2.5
    
    def test_get_recommended_spiral_speed_slow_flash(self, text_animator):
        """Test recommended spiral speed for SLOW_FLASH effect."""
        text_animator.set_effect(TextEffect.SLOW_FLASH)
        speed = text_animator.get_recommended_spiral_speed()
        assert speed in [2.0, 4.0]  # Alternates between slow and fast
    
    def test_get_recommended_spiral_speed_pulse(self, text_animator):
        """Test recommended spiral speed for PULSE effect."""
        text_animator.set_effect(TextEffect.PULSE)
        assert text_animator.get_recommended_spiral_speed() == 1.5
    
    def test_get_recommended_spiral_speed_zoom(self, text_animator):
        """Test recommended spiral speed for ZOOM effect."""
        text_animator.set_effect(TextEffect.ZOOM)
        assert text_animator.get_recommended_spiral_speed() == 1.3


class TestStateManagement:
    """Test state management."""
    
    def test_get_state(self, text_animator):
        """Test get_state returns complete state."""
        text_animator.set_effect(TextEffect.PULSE)
        text_animator.update(0.5)
        
        state = text_animator.get_state()
        
        assert 'effect' in state
        assert 'time' in state
        assert 'alpha' in state
        assert 'scale' in state
        assert 'offset_x' in state
        assert 'offset_y' in state
        assert state['effect'] == TextEffect.PULSE
    
    def test_reset(self, text_animator):
        """Test reset restores initial state."""
        text_animator.set_effect(TextEffect.FADE_IN)
        text_animator.update(0.5)
        
        text_animator.reset()
        
        assert text_animator._time == 0.0
        assert text_animator._alpha == 1.0
        assert text_animator._scale == 1.0
        assert text_animator._offset_x == 0.0
        assert text_animator._offset_y == 0.0


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_negative_delta_time(self, text_animator):
        """Test update with negative delta time."""
        text_animator.set_effect(TextEffect.FADE_IN)
        
        # Should handle gracefully (likely clamp to 0 or ignore)
        text_animator.update(-1.0)
        
        # Should not crash and maintain valid state
        assert text_animator._time >= 0.0
    
    def test_very_large_delta_time(self, text_animator):
        """Test update with very large delta time."""
        text_animator.set_effect(TextEffect.FADE_IN)
        
        text_animator.update(1000.0)
        
        # Should complete effect
        assert text_animator._alpha == 1.0
    
    def test_zero_delta_time(self, text_animator):
        """Test update with zero delta time."""
        text_animator.set_effect(TextEffect.PULSE)
        initial_scale = text_animator._scale
        
        text_animator.update(0.0)
        
        # State should remain unchanged
        assert text_animator._scale == initial_scale
    
    def test_typewriter_zero_length(self, text_animator):
        """Test TYPEWRITER with zero text length."""
        text_animator.set_effect(TextEffect.TYPEWRITER)
        text_animator.set_typewriter_length(0)
        
        text_animator.update(1.0)
        
        assert text_animator.get_typewriter_chars_shown() == 0
    
    def test_typewriter_negative_length(self, text_animator):
        """Test TYPEWRITER with negative text length."""
        text_animator.set_effect(TextEffect.TYPEWRITER)
        text_animator.set_typewriter_length(-5)
        
        text_animator.update(1.0)
        
        # Should handle gracefully (likely clamp to 0)
        assert text_animator.get_typewriter_chars_shown() >= 0


class TestMultipleUpdates:
    """Test multiple sequential updates."""
    
    def test_multiple_fade_in_updates(self, text_animator):
        """Test multiple updates during FADE_IN."""
        text_animator.set_effect(TextEffect.FADE_IN)
        
        alphas = []
        for _ in range(20):
            text_animator.update(0.05)
            alphas.append(text_animator._alpha)
        
        # Alphas should be monotonically increasing (or stable at 1.0)
        for i in range(1, len(alphas)):
            assert alphas[i] >= alphas[i-1]
    
    def test_multiple_pulse_updates(self, text_animator):
        """Test multiple updates during PULSE."""
        text_animator.set_effect(TextEffect.PULSE)
        
        scales = []
        for _ in range(30):
            text_animator.update(0.1)
            scales.append(text_animator._scale)
        
        # Should have oscillation
        assert max(scales) > min(scales)
    
    def test_effect_change_during_animation(self, text_animator):
        """Test changing effect mid-animation."""
        text_animator.set_effect(TextEffect.FADE_IN)
        text_animator.update(0.5)
        
        # Change effect
        text_animator.set_effect(TextEffect.PULSE)
        
        # Time should reset
        assert text_animator._time == 0.0
        # State should be valid
        assert text_animator._alpha >= 0.0
        assert text_animator._scale >= 0.0
