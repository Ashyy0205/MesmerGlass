"""Unit tests for background animation system."""

import pytest
from mesmerglass.content.animator import (
    BackgroundAnimator,
    AnimationPattern,
    CenterZoomConfig,
    DriftConfig,
    RandomConfig
)


class TestBackgroundAnimator:
    """Test BackgroundAnimator class."""
    
    def test_init(self):
        """Test animator initialization."""
        animator = BackgroundAnimator()
        assert animator.get_pattern() == AnimationPattern.NONE
        assert animator.center_zoom_config is not None
        assert animator.drift_config is not None
        assert animator.random_config is not None
    
    def test_pattern_none(self):
        """Test NONE pattern returns static values."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.NONE)
        
        # Should return zoom=1.0, offset=(0, 0) regardless of time
        for _ in range(100):
            zoom, offset = animator.update(1/60)
            assert zoom == 1.0
            assert offset == (0.0, 0.0)
    
    def test_pattern_switching(self):
        """Test switching between patterns."""
        animator = BackgroundAnimator()
        
        # Switch to center zoom
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        assert animator.get_pattern() == AnimationPattern.CENTER_ZOOM
        
        # Switch to drift
        animator.set_pattern(AnimationPattern.DRIFT)
        assert animator.get_pattern() == AnimationPattern.DRIFT
        
        # Switch back to none
        animator.set_pattern(AnimationPattern.NONE)
        assert animator.get_pattern() == AnimationPattern.NONE


class TestCenterZoom:
    """Test center zoom animation pattern."""
    
    def test_hold_start(self):
        """Test hold period at start zoom."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        
        # Configure: 1.0x start, 2.0x end, 2s hold start
        animator.center_zoom_config.start_zoom = 1.0
        animator.center_zoom_config.end_zoom = 2.0
        animator.center_zoom_config.hold_start = 2.0
        animator.center_zoom_config.duration = 4.0
        
        # During hold start, should stay at start_zoom
        for _ in range(60):  # 1 second @ 60fps
            zoom, offset = animator.update(1/60)
            assert zoom == 1.0
            assert offset == (0.0, 0.0)
    
    def test_zoom_transition(self):
        """Test zoom interpolation from start to end."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        
        # Configure: 1.0x → 2.0x over 4 seconds, no holds
        animator.center_zoom_config.start_zoom = 1.0
        animator.center_zoom_config.end_zoom = 2.0
        animator.center_zoom_config.duration = 4.0
        animator.center_zoom_config.hold_start = 0.0
        animator.center_zoom_config.hold_end = 0.0
        
        # Skip to zoom phase (no hold)
        zoom_values = []
        for _ in range(240):  # 4 seconds @ 60fps
            zoom, offset = animator.update(1/60)
            zoom_values.append(zoom)
        
        # Should start at 1.0
        assert zoom_values[0] == 1.0
        
        # Should end at 2.0
        assert zoom_values[-1] == pytest.approx(2.0, abs=0.01)
        
        # Should be monotonically increasing (smooth interpolation)
        for i in range(len(zoom_values) - 1):
            assert zoom_values[i] <= zoom_values[i + 1]
    
    def test_hold_end(self):
        """Test hold period at end zoom."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        
        # Configure: 1.0x → 2.0x, 1s duration, 2s hold end
        animator.center_zoom_config.start_zoom = 1.0
        animator.center_zoom_config.end_zoom = 2.0
        animator.center_zoom_config.duration = 1.0
        animator.center_zoom_config.hold_start = 0.0
        animator.center_zoom_config.hold_end = 2.0
        animator.center_zoom_config.loop = False
        
        # Run through transition + hold
        for _ in range(60):  # 1s transition
            animator.update(1/60)
        
        # During hold end, should stay at end_zoom
        for _ in range(120):  # 2s hold
            zoom, offset = animator.update(1/60)
            assert zoom == pytest.approx(2.0, abs=0.01)
    
    def test_loop(self):
        """Test looping back to start."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        
        # Configure: 1.0x ↔ 2.0x, 1s transition, 0.5s holds, loop=True
        animator.center_zoom_config.start_zoom = 1.0
        animator.center_zoom_config.end_zoom = 2.0
        animator.center_zoom_config.duration = 1.0
        animator.center_zoom_config.hold_start = 0.5
        animator.center_zoom_config.hold_end = 0.5
        animator.center_zoom_config.loop = True
        
        # Run through one full cycle
        # Phase 0: hold start (0.5s = 30 frames)
        for _ in range(30):
            zoom, _ = animator.update(1/60)
            assert zoom == 1.0
        
        # Phase 1: zoom in (1.0s = 60 frames)
        for _ in range(60):
            animator.update(1/60)
        
        # Phase 2: hold end (0.5s = 30 frames)
        for _ in range(30):
            zoom, _ = animator.update(1/60)
            assert zoom == pytest.approx(2.0, abs=0.01)
        
        # Phase 3: zoom out (1.0s = 60 frames)
        for _ in range(60):
            animator.update(1/60)
        
        # Should be back at start
        zoom, _ = animator.update(1/60)
        assert zoom == pytest.approx(1.0, abs=0.1)


class TestDrift:
    """Test drift animation pattern."""
    
    def test_continuous_drift(self):
        """Test that drift continuously changes offset."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.DRIFT)
        
        # Configure drift
        animator.drift_config.x_speed = 0.5
        animator.drift_config.y_speed = 0.3
        animator.drift_config.drift_scale = 1.0
        
        # Get initial offset
        _, offset0 = animator.update(1/60)
        
        # Update several times
        offsets = []
        for _ in range(60):  # 1 second
            _, offset = animator.update(1/60)
            offsets.append(offset)
        
        # Offsets should be changing
        assert offsets[0] != offsets[-1]
        
        # Zoom should stay at 1.0
        zoom, _ = animator.update(1/60)
        assert zoom == 1.0
    
    def test_drift_wrapping(self):
        """Test that drift wraps at drift_scale boundary."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.DRIFT)
        
        # Configure fast drift with small scale
        animator.drift_config.x_speed = 1.0
        animator.drift_config.y_speed = 0.0
        animator.drift_config.drift_scale = 0.5
        
        # Run until wrap occurs
        for _ in range(120):  # 2 seconds
            zoom, offset = animator.update(1/60)
        
        # Offset should be within [-drift_scale, drift_scale]
        assert abs(offset[0]) <= animator.drift_config.drift_scale
        assert abs(offset[1]) <= animator.drift_config.drift_scale


class TestRandom:
    """Test random animation pattern."""
    
    def test_random_changes(self):
        """Test that random pattern changes targets periodically."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.RANDOM)
        
        # Configure short change interval
        animator.random_config.change_interval = 1.0
        animator.random_config.max_zoom = 2.0
        animator.random_config.max_drift = 0.5
        
        # Get initial state
        zoom0, offset0 = animator.update(1/60)
        
        # Run for change interval
        for _ in range(60):  # 1 second
            animator.update(1/60)
        
        # After change interval, state should be different
        # (might be close due to interpolation, but targets changed)
        zoom1, offset1 = animator.update(1/60)
        
        # Values should be within configured bounds
        assert 1.0 <= zoom1 <= animator.random_config.max_zoom
        assert abs(offset1[0]) <= animator.random_config.max_drift
        assert abs(offset1[1]) <= animator.random_config.max_drift
    
    def test_random_interpolation(self):
        """Test smooth interpolation to random targets."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.RANDOM)
        
        # Configure
        animator.random_config.change_interval = 2.0
        animator.random_config.max_zoom = 1.5
        
        # Collect zoom values
        zooms = []
        for _ in range(60):  # 1 second
            zoom, _ = animator.update(1/60)
            zooms.append(zoom)
        
        # Should be smoothly changing (no sudden jumps)
        for i in range(len(zooms) - 1):
            diff = abs(zooms[i+1] - zooms[i])
            assert diff < 0.1  # No large jumps


class TestAnimationConfig:
    """Test animation configuration classes."""
    
    def test_center_zoom_config(self):
        """Test CenterZoomConfig defaults and modification."""
        config = CenterZoomConfig()
        assert config.start_zoom == 1.0
        assert config.end_zoom == 1.5
        assert config.duration == 8.0
        assert config.loop is True
        
        # Modify
        config.end_zoom = 3.0
        assert config.end_zoom == 3.0
    
    def test_drift_config(self):
        """Test DriftConfig defaults and modification."""
        config = DriftConfig()
        assert config.x_speed == 0.5
        assert config.y_speed == 0.3
        assert config.drift_scale == 0.3
        
        # Modify
        config.x_speed = 1.0
        assert config.x_speed == 1.0
    
    def test_random_config(self):
        """Test RandomConfig defaults and modification."""
        config = RandomConfig()
        assert config.change_interval == 12.0
        assert config.max_zoom == 1.8
        assert config.max_drift == 0.5
        
        # Modify
        config.change_interval = 5.0
        assert config.change_interval == 5.0


class TestAnimatorInfo:
    """Test animator state inspection."""
    
    def test_get_info(self):
        """Test get_info returns current state."""
        animator = BackgroundAnimator()
        animator.set_pattern(AnimationPattern.CENTER_ZOOM)
        
        # Update a few times
        for _ in range(30):
            animator.update(1/60)
        
        # Get info
        info = animator.get_info()
        
        assert 'pattern' in info
        assert info['pattern'] == 'CENTER_ZOOM'
        assert 'zoom' in info
        assert 'offset' in info
        assert 'phase' in info
        assert 'elapsed' in info
        
        # Values should be reasonable
        assert isinstance(info['zoom'], float)
        assert isinstance(info['offset'], list)
        assert len(info['offset']) == 2
