"""Tests for Trance 7-type spiral system implementation."""

import pytest
from mesmerglass.mesmerloom.spiral import SpiralDirector


class TestSpiralTypes:
    """Test suite for spiral type switching and parameters."""
    
    def test_spiral_type_range(self):
        """Verify spiral type can be set to 1-7."""
        director = SpiralDirector()
        
        for spiral_type in range(1, 8):
            director.set_spiral_type(spiral_type)
            assert director.spiral_type == spiral_type
            
            # Verify it exports correctly
            uniforms = director.export_uniforms()
            assert uniforms['spiral_type'] == float(spiral_type)
    
    def test_spiral_type_clamping(self):
        """Verify spiral type is clamped to valid range."""
        director = SpiralDirector()
        
        # Test out of range values
        director.set_spiral_type(0)
        assert director.spiral_type == 1  # Should clamp to minimum
        
        director.set_spiral_type(10)
        assert director.spiral_type == 7  # Should clamp to maximum
        
        director.set_spiral_type(-5)
        assert director.spiral_type == 1  # Should clamp to minimum
    
    def test_spiral_width_options(self):
        """Verify all valid spiral width options work."""
        director = SpiralDirector()
        valid_widths = [360, 180, 120, 90, 72, 60]
        
        for width in valid_widths:
            director.set_spiral_width(width)
            assert director.spiral_width == width
            
            # Verify it exports correctly
            uniforms = director.export_uniforms()
            assert uniforms['width'] == float(width)
    
    def test_spiral_width_closest_match(self):
        """Verify invalid widths snap to closest valid value."""
        director = SpiralDirector()
        
        # Test values that should snap to closest
        director.set_spiral_width(100)  # Should snap to 90 or 120
        assert director.spiral_width in [90, 120]
        
        director.set_spiral_width(70)  # Should snap to 60 or 72
        assert director.spiral_width in [60, 72]
    
    def test_rotation_formula(self):
        """Verify RPM-based rotation uses dt instead of legacy amount parameter."""
        director = SpiralDirector()
        director.set_rotation_speed(30.0)  # 30 RPM = 0.5 rps
        dt = 1.0 / 60.0  # 60 FPS frame

        initial_phase = director._phase_accumulator
        director.rotate_spiral(0.0, dt=dt)

        expected_increment = (director.rotation_speed / 60.0) * dt
        actual_increment = director._phase_accumulator - initial_phase
        assert pytest.approx(expected_increment, rel=1e-6) == actual_increment
    
    def test_rotation_wrapping(self):
        """Verify phase wraps at 1.0."""
        director = SpiralDirector()
        director.state.phase = 0.99
        director.spiral_width = 60
        
        # Large rotation should wrap
        director.rotate_spiral(100.0)
        
        # Phase should be in [0, 1) range
        assert 0.0 <= director.state.phase < 1.0
    
    def test_change_spiral_randomness(self):
        """Verify change_spiral() produces different types/widths."""
        director = SpiralDirector(seed=42)  # Use seed for reproducibility
        
        initial_type = director.spiral_type
        initial_width = director.spiral_width
        
        # Call change_spiral multiple times (75% skip chance, so need multiple calls)
        changed = False
        for _ in range(20):
            director.change_spiral()
            if director.spiral_type != initial_type or director.spiral_width != initial_width:
                changed = True
                break
        
        # At least one change should have occurred in 20 attempts
        assert changed, "change_spiral() should eventually change type or width"
    
    def test_trance_uniforms_present(self):
        """Verify all Trance-specific uniforms are exported."""
        director = SpiralDirector()
        uniforms = director.export_uniforms()
        
        # Check Trance uniforms exist
        assert 'near_plane' in uniforms
        assert 'far_plane' in uniforms
        assert 'eye_offset' in uniforms
        assert 'aspect_ratio' in uniforms
        assert 'width' in uniforms
        assert 'spiral_type' in uniforms
        assert 'time' in uniforms  # Should be same as phase
        assert 'acolour' in uniforms
        assert 'bcolour' in uniforms
        # Verify default values
        assert uniforms['near_plane'] == 1.0
        assert uniforms['far_plane'] == 5.0
        assert uniforms['eye_offset'] == 0.0
        assert isinstance(uniforms['aspect_ratio'], float)
        
        # Verify colors are RGBA tuples
        assert len(uniforms['acolour']) == 4
        assert len(uniforms['bcolour']) == 4

    def test_flip_wave_uniforms(self):
        """Flip wave exports radius and width within expected ranges."""
        director = SpiralDirector()
        director.state.flip_state = 1
        director.state.flip_radius = 0.5
        director.state.flip_width = 0.03

        uniforms = director.export_uniforms()
        assert uniforms['uFlipWaveRadius'] == pytest.approx(0.5)
        assert uniforms['uFlipWaveWidth'] == pytest.approx(0.03)


class TestRotationFormula:
    """Detailed tests for the RPM-based rotation integrator."""

    @pytest.mark.parametrize("rpm,dt", [
        (4.0, 1 / 30.0),
        (15.0, 1 / 60.0),
        (-20.0, 1 / 90.0),
    ])
    def test_rotation_increments(self, rpm, dt):
        """Phase increment should follow rpm/60 * dt regardless of legacy amount parameter."""
        director = SpiralDirector()
        director.set_rotation_speed(rpm)
        initial = director._phase_accumulator

        director.rotate_spiral(0.0, dt=dt)

        expected = (rpm / 60.0) * dt
        actual = director._phase_accumulator - initial
        if actual > 0.5:
            actual -= 1.0
        if actual < -0.5:
            actual += 1.0
        assert pytest.approx(expected, rel=1e-6) == actual


class TestSpiralDefaults:
    """Test default values match Trance expectations."""
    
    def test_default_spiral_type(self):
        """Verify default spiral type is 3 (linear)."""
        director = SpiralDirector()
        assert director.spiral_type == 3
    
    def test_default_spiral_width(self):
        """Verify default spiral width is 60 degrees."""
        director = SpiralDirector()
        assert director.spiral_width == 60
    
    def test_default_near_far_planes(self):
        """Verify default plane distances match Trance."""
        director = SpiralDirector()
        assert director.near_plane == 1.0
        assert director.far_plane == 5.0
    
    def test_default_eye_offset(self):
        """Verify default eye offset is 0.0 (non-VR)."""
        director = SpiralDirector()
        assert director.eye_offset == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
