from mesmerglass.content.models import build_session_pack
import time


def test_valid_pack_parses():
    raw = {"version": 1, "name": "Sample", "text": {"items": [{"msg": "Relax", "secs": 10}]}, "pulse": {"stages": [{"mode": "wave", "intensity": 0.4, "secs": 20}], "fallback": "idle"}}
    pack = build_session_pack(raw)
    assert pack.first_text == "Relax"
    assert abs(pack.avg_intensity - 0.4) < 1e-6


def test_invalid_version():
    try:
        build_session_pack({"version": 2, "name": "X"})
        assert False
    except ValueError as e:
        assert "Unsupported" in str(e)


def test_intensity_range_check():
    try:
        build_session_pack({"version": 1, "name": "Bad", "pulse": {"stages": [{"mode": "wave", "intensity": 2, "secs": 5}]}})
        assert False
    except ValueError as e:
        assert "intensity" in str(e)


def test_performance_under_threshold():
    raw = {"version": 1, "name": "Perf", "text": {"items": [{"msg": "A", "secs": 1} for _ in range(50)]}, "pulse": {"stages": [{"mode": "m", "intensity": 0.5, "secs": 1} for _ in range(50)]}}
    start = time.perf_counter()
    pack = build_session_pack(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert elapsed_ms < 500