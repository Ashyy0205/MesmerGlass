import json
import math
from pathlib import Path

from mesmerglass.mesmerloom.custom_visual import CustomVisual


def make_mode(tmp_path: Path, cycle_speed: int) -> Path:
    data = {
        "version": "1.0",
        "name": f"TestSpeed{cycle_speed}",
        "spiral": {"type": "linear", "rotation_speed": 4.0, "opacity": 0.8, "reverse": False},
        "media": {"mode": "images", "cycle_speed": cycle_speed, "opacity": 1.0, "use_theme_bank": True},
        "text": {"enabled": False, "mode": "centered_sync", "opacity": 1.0, "use_theme_bank": True, "library": []},
        "zoom": {"mode": "none", "rate": 0.0},
    }
    p = tmp_path / f"mode_{cycle_speed}.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def expected_frames_per_cycle(speed: int) -> int:
    speed = max(1, min(100, int(speed)))
    interval_ms = 10000 * math.pow(0.005, (speed - 1) / 99.0)
    return max(1, round((interval_ms / 1000.0) * 60.0))


def test_media_cycle_formula_matches_visual_creator(tmp_path):
    for speed in [1, 20, 50, 100]:
        path = make_mode(tmp_path, speed)
        cv = CustomVisual(path, theme_bank=None, compositor=None, text_director=None)
        assert cv._frames_per_cycle == expected_frames_per_cycle(speed)
