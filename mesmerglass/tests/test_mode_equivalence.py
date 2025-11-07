import json
from pathlib import Path

from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.mesmerloom.custom_visual import CustomVisual
from mesmerglass.mesmerloom.spiral_speed import SpiralSpeedCalculator


class DummyCompositor:
    def __init__(self, director: SpiralDirector):
        self.spiral_director = director


def make_mode(tmp_path: Path, rotation_speed: float, reverse: bool, opacity: float = 0.5) -> Path:
    data = {
        "version": "1.0",
        "name": "EquivalenceTest",
        "spiral": {"type": "linear", "rotation_speed": rotation_speed, "opacity": opacity, "reverse": reverse},
        "media": {"mode": "none", "cycle_speed": 50, "opacity": 1.0, "use_theme_bank": True},
        "text": {"enabled": False, "mode": "centered_sync", "opacity": 1.0, "use_theme_bank": True, "library": []},
        "zoom": {"mode": "none", "rate": 0.0},
    }
    p = tmp_path / "mode_eq.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def simulate_phase(d: SpiralDirector, frames: int = 60, dt: float = 1/60.0) -> float:
    start = d.state.phase
    for _ in range(frames):
        d.rotate_spiral(0.0)
        d.update(dt)
    end = d.state.phase
    # Phase wraps to [0,1); measure shortest arc distance as magnitude per second
    delta = (end - start) % 1.0
    # Choose minor arc so measurement is independent of rotation direction
    if delta > 0.5:
        delta = 1.0 - delta
    per_second = delta / (frames * dt)
    return per_second


def test_spiral_phase_matches_rpm_forward(tmp_path):
    d = SpiralDirector(seed=7)
    mode_path = make_mode(tmp_path, rotation_speed=4.0, reverse=False, opacity=0.5)
    comp = DummyCompositor(d)
    # Load via CustomVisual to apply rotation_speed and opacity
    CustomVisual(mode_path, theme_bank=None, compositor=comp, text_director=None)
    measured = simulate_phase(d, frames=120)
    expected = SpiralSpeedCalculator.rpm_to_phase_per_second(4.0)
    assert abs(measured - expected) < 0.01


def test_spiral_phase_matches_rpm_reverse(tmp_path):
    d = SpiralDirector(seed=7)
    mode_path = make_mode(tmp_path, rotation_speed=4.0, reverse=True, opacity=0.5)
    comp = DummyCompositor(d)
    CustomVisual(mode_path, theme_bank=None, compositor=comp, text_director=None)
    measured = simulate_phase(d, frames=120)
    expected = SpiralSpeedCalculator.rpm_to_phase_per_second(4.0)
    # magnitude match within tolerance regardless of direction
    assert abs(measured - expected) < 0.01
