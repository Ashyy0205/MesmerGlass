import json

from mesmerglass.cli import sweep_spiral_measure


def test_sweep_spiral_measure_director_predictive_frames():
    # 90 deg sweep; at 60 rpm -> 15 frames; at 120 rpm -> 8 frames
    speeds = [60.0, 120.0]
    results = sweep_spiral_measure(speeds, use_x=False, delta_deg=90.0, mode="director", reverse=False, ceil_frame=True)
    assert len(results) == 2
    assert results[0]["predicted_frames"] == 15
    assert results[1]["predicted_frames"] == 8
    # measured ticks must be >= predicted frames (stop when meets/exceeds target)
    assert results[0]["ticks"] >= results[0]["predicted_frames"]
    assert results[1]["ticks"] >= results[1]["predicted_frames"]
