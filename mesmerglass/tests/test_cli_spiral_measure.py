import math

from mesmerglass.cli import measure_spiral_time_director


def test_measure_spiral_time_director_quarter_turn_at_60rpm():
    # 60 RPM -> 1 revolution per second => 90° (0.25 rev) should take 0.25s
    rpm = 60.0
    delta_deg = 90.0
    seconds, frames, achieved = measure_spiral_time_director(rpm, delta_deg, reverse=False, fps=60.0)

    expected = delta_deg / (rpm * 6.0)
    # Deterministic: director uses fixed dt=1/60, so expect exactly 0.25s within 1 frame tolerance
    assert frames >= 1
    assert math.isclose(seconds, expected, rel_tol=0, abs_tol=1/60.0)
    # Achieved phase should meet or exceed the target (within tiny epsilon)
    target_phase = delta_deg / 360.0
    assert achieved + 1e-9 >= target_phase
