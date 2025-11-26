"""Timing-focused tests for TextDirector."""

from __future__ import annotations

import math
from unittest import mock

from mesmerglass.engine.text_director import TextDirector


class RecordingTextDirector(TextDirector):
    """Minimal subclass that counts renders for deterministic assertions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.render_count = 0

    def _render_current_text(self) -> None:  # type: ignore[override]
        self.render_count += 1


class _OpacityCompositor:
    def __init__(self) -> None:
        self.opacity = None

    def set_text_opacity(self, value: float) -> None:
        self.opacity = value

    def clear_text_textures(self) -> None:  # pragma: no cover - noop
        pass


def test_manual_cycle_uses_elapsed_seconds():
    """Manual text timing should honor slider seconds even at low FPS."""

    timeline = {"t": 0.0}

    def fake_time() -> float:
        return timeline["t"]

    director = RecordingTextDirector(
        text_renderer=object(),
        compositor=object(),
        time_provider=fake_time,
    )
    director.set_text_library(["Alpha", "Beta"])
    director.set_enabled(True)
    director.configure_sync(sync_with_media=False, frames_per_text=60)  # ≈1s

    with mock.patch("mesmerglass.engine.text_director.random.random", return_value=0.0):
        director.update()  # Initial render
        assert director.render_count == 1

        timeline["t"] += 0.5  # half a second
        director.update()
        assert director.render_count == 1  # not enough elapsed time

        timeline["t"] += 0.49
        director.update()
        assert director.render_count == 1  # still under 1s threshold

        timeline["t"] += 0.02  # cross the 1s mark
        director.update()
        assert director.render_count == 2  # second render triggered
        assert director._elapsed_time_s == 0.0


def test_set_opacity_applies_to_all_compositors():
    primary = _OpacityCompositor()
    director = TextDirector(text_renderer=None, compositor=primary)

    secondary = _OpacityCompositor()
    director.set_secondary_compositors([secondary])

    director.set_opacity(0.42)

    assert math.isclose(primary.opacity, 0.42, rel_tol=1e-6)
    assert math.isclose(secondary.opacity, 0.42, rel_tol=1e-6)