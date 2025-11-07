import math

from mesmerglass.cli import predict_spiral_frames


def test_predict_spiral_frames_matches_closed_form_roundup():
    # 60 RPM, 90 degrees: closed form is 0.25s, at 60 FPS -> 15 frames exactly
    rpm = 60.0
    delta_deg = 90.0
    frames, seconds = predict_spiral_frames(rpm, delta_deg, fps=60.0)
    assert frames == 15
    assert math.isclose(seconds, 15/60.0, rel_tol=0, abs_tol=1e-12)

    # 130 RPM, 90 degrees: expected seconds = delta/(rpm*6)
    rpm = 130.0
    expected = delta_deg / (rpm * 6.0)
    frames, seconds = predict_spiral_frames(rpm, delta_deg, fps=60.0)
    # Round-up property: seconds should be ceil(expected*60)/60
    expected_frames = math.ceil(expected * 60.0 - 1e-12)
    assert frames == expected_frames
    assert math.isclose(seconds, expected_frames/60.0, rel_tol=0, abs_tol=1e-12)
