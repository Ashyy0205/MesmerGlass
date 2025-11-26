from pathlib import Path

import pytest

from mesmerglass.cli import _run_cuelist_diag
from mesmerglass.logging_utils import LogMode, get_log_mode, set_log_mode
from mesmerglass.session.cue import AudioRole, AudioTrack, Cue, PlaybackEntry
from mesmerglass.session.cuelist import Cuelist
from mesmerglass.session.runner import SessionRunner


@pytest.fixture(autouse=True)
def _force_perf_mode():
    """Ensure PerfTracer is enabled during these tests."""
    previous = get_log_mode()
    set_log_mode(LogMode.PERF)
    try:
        yield
    finally:
        set_log_mode(previous)


class _StubTextDirector:
    def reset(self) -> None:  # pragma: no cover - trivial
        return None

    def set_secondary_compositors(self, *_args, **_kwargs) -> None:  # pragma: no cover - trivial
        return None


class _StubVisualDirector:
    def __init__(self) -> None:
        self._cycle_count = 0
        self.text_director = _StubTextDirector()

    def register_cycle_callback(self, *_args, **_kwargs) -> None:
        return None

    def unregister_cycle_callback(self, *_args, **_kwargs) -> None:
        return None

    def register_secondary_compositor(self, *_args, **_kwargs) -> None:
        return None

    def unregister_secondary_compositor(self, *_args, **_kwargs) -> None:
        return None

    def get_cycle_count(self) -> int:
        return self._cycle_count

    def load_playback(self, _path) -> bool:
        return True

    def start_playback(self) -> None:
        self._cycle_count += 1

    def pause(self) -> None:  # pragma: no cover - trivial
        return None

    def resume(self) -> None:  # pragma: no cover - trivial
        return None

    def update(self, *_args, **_kwargs) -> None:  # pragma: no cover - trivial
        return None


class _StubAudioEngine:
    def __init__(self, *, preload_latency_ms: float = 0.0) -> None:
        self.num_channels = 2
        self.init_ok = True
        self._preload_latency = preload_latency_ms / 1000.0
        self.preload_calls: list[str] = []

    # --- setup / lifetime -------------------------------------------------
    def set_stream_threshold_mb(self, *_args, **_kwargs) -> None:
        return None

    def set_slow_decode_threshold_ms(self, *_args, **_kwargs) -> None:
        return None

    def stop_all(self) -> None:
        return None

    # --- helpers used by SessionRunner -----------------------------------
    def normalize_track_path(self, path: str) -> str:
        return str(Path(path))

    def preload_sound(self, path: str) -> bool:
        self.preload_calls.append(path)
        if self._preload_latency:
            import time as _time

            _time.sleep(self._preload_latency)
        return True

    def is_streaming_active(self) -> bool:
        return False

    def stop_streaming_track(self, **_kwargs) -> None:
        return None

    def should_stream(self, _path: str) -> bool:
        return False

    def play_streaming_track(self, *_args, **_kwargs) -> bool:
        return True

    def load_channel(self, *_args, **_kwargs) -> bool:
        return True

    def fade_in_and_play(self, *_args, **_kwargs) -> bool:
        return True

    def get_channel_length(self, _channel: int) -> float:
        return 8.0

    def drop_cached_sound(self, *_args, **_kwargs) -> None:
        return None

    def set_stream_threshold(self, *_args, **_kwargs) -> None:  # pragma: no cover - legacy alias
        return None

    def estimate_track_duration(self, *_args, **_kwargs) -> float:
        return 4.0

    def set_slow_decode_threshold(self, *_args, **_kwargs) -> None:  # pragma: no cover - legacy alias
        return None


def _make_test_cuelist(tmp_path: Path) -> Cuelist:
    playback_file = tmp_path / "pb.json"
    playback_file.write_text("{\"name\": \"PB\"}")
    audio_file = tmp_path / "track.mp3"
    audio_file.write_text("stub")

    cue = Cue(
        name="Cue #1",
        duration_seconds=5.0,
        playback_pool=[PlaybackEntry(playback_path=playback_file, weight=1.0)],
        audio_tracks=[AudioTrack(file_path=audio_file, role=AudioRole.HYPNO, loop=True)],
    )
    return Cuelist(name="Perf Test", cues=[cue])


def test_session_runner_emits_audio_spans(tmp_path):
    cuelist = _make_test_cuelist(tmp_path)
    runner = SessionRunner(
        cuelist=cuelist,
        visual_director=_StubVisualDirector(),
        audio_engine=_StubAudioEngine(),
    )

    runner._prefetch_cue_audio(0, force=True, async_allowed=False)
    ok = runner._await_cue_audio_ready(0)
    assert ok
    started = runner._start_cue(0)
    assert started

    snapshot = runner.get_perf_snapshot(reset=True)
    assert snapshot is not None
    names = {span["name"] for span in snapshot["spans"]}
    assert "prefetch_cue" in names
    assert "cue_audio_start" in names
    assert snapshot["span_count"] == len(snapshot["spans"])

    empty_snapshot = runner.get_perf_snapshot(reset=True)
    assert empty_snapshot is not None
    assert empty_snapshot["span_count"] == 0


def test_cli_diag_reports_spans(monkeypatch, tmp_path):
    cuelist = _make_test_cuelist(tmp_path)

    class _DiagStubAudio(_StubAudioEngine):
        def __init__(self, num_channels: int = 2):
            super().__init__()
            self.num_channels = num_channels

    monkeypatch.setattr("mesmerglass.cli.AudioEngine", _DiagStubAudio)

    result = _run_cuelist_diag(cuelist, cue_limit=1, prefetch_only=True)
    assert "snapshot" in result
    snapshot = result["snapshot"]
    assert snapshot
    names = {span["name"] for span in snapshot["spans"]}
    assert "prefetch_cue" in names
    assert result.get("executed", 0) == 1