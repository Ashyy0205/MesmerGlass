import math, time
import pytest

from mesmerglass.mesmerloom.spiral import SpiralDirector


def advance(director: SpiralDirector, seconds: float, step: float=1/60):
    t = 0.0
    while t < seconds:
        director.update(step)
        t += step


def test_intensity_scaling_endpoints():
    d = SpiralDirector(seed=1)
    d.set_intensity(0.0); advance(d, 0.2)
    low_speed = d.state.base_speed
    d.set_intensity(1.0)
    # Advance long enough for slew to reach target (DW_BASE_SPEED per frame, plus tightened first 1.5s)
    advance(d, 3.0)
    high_speed = d.state.base_speed
    assert 0.089 <= low_speed <= 0.091
    assert 0.138 <= high_speed <= 0.141
    assert high_speed > low_speed


def test_safety_clamps():
    d = SpiralDirector(seed=2)
    d.state.bar_width = 0.1  # force out of range
    d.state.opacity = 0.2
    d.state.contrast = 2.0
    d.state.chromatic_shift = 1.0
    d.update(1/60)
    assert d.state.bar_width >= d.BAR_WIDTH_MIN
    assert d.state.opacity >= d.OPACITY_MIN
    assert d.state.contrast <= d.CONTRAST_MAX
    assert d.state.chromatic_shift <= d.CHROMA_MAX
    assert d.state.safety_clamped


def test_slew_limits():
    d = SpiralDirector(seed=3)
    d.set_intensity(1.0)  # triggers cooldown (tight slew)
    # Capture initial then advance a single frame
    before = d.state.base_speed
    d.update(1/60)
    after1 = d.state.base_speed
    # Should not exceed DW_BASE_SPEED * 0.5 on first frame (tight mode)
    assert after1 - before <= d.DW_BASE_SPEED * 0.51
    # Advance past cooldown
    advance(d, 2.0)
    before2 = d.state.base_speed
    d.set_intensity(0.0)
    d.update(1/60)
    # Tight again
    assert abs(d.state.base_speed - before2) <= d.DW_BASE_SPEED * 0.51


def test_flip_fsm_progression():
    d = SpiralDirector(seed=4)
    # Force immediate flip
    d.force_flip()
    assert d.state.flip_state == 1
    # Advance through wave duration at intensity 0 (≈40s) but accelerate for test by manually updating with large dt
    total = 0.0
    while d.state.flip_state == 1 and total < 45.0:
        d.update(1.0)
        total += 1.0
    assert d.state.flip_state == 0
    # Ensure next flip is scheduled (next_flip_in decreased over time in idle; implicit by private var not exposed)

