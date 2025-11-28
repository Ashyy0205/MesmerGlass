from __future__ import annotations

from pathlib import Path

import pytest

from mesmerglass.content.theme import ThemeConfig
from mesmerglass.content.themebank import ThemeBank
from mesmerglass.engine.text_director import TextDirector


class _DummyStyle:
    def __init__(self) -> None:
        self.font_path: str | None = None
        self.font_size: int = 48
        self.color = (255, 255, 255, 255)


class _DummyRenderer:
    def __init__(self) -> None:
        self._style = _DummyStyle()

    def get_style(self) -> _DummyStyle:
        return self._style

    def set_style(self, style: _DummyStyle) -> None:
        self._style = style


def test_themebank_font_queue_cycles(tmp_path: Path) -> None:
    theme = ThemeConfig(name="Empty", enabled=True, image_path=[], animation_path=[], font_path=[], text_line=[])
    bank = ThemeBank([theme], root_path=tmp_path, image_cache_size=1)
    try:
        fonts = []
        for idx in range(3):
            font_path = tmp_path / f"Font{idx}.ttf"
            font_path.write_text("dummy")
            fonts.append(str(font_path))

        bank.set_font_library(fonts)
        first_round = {bank.pick_font_for_playback() for _ in range(len(fonts))}
        assert first_round == set(fonts)

        second_round = [bank.pick_font_for_playback() for _ in range(len(fonts))]
        assert all(second_round)
    finally:
        bank.shutdown()


def test_text_director_user_override_blocks_auto(tmp_path: Path) -> None:
    renderer = _DummyRenderer()
    director = TextDirector(text_renderer=renderer, compositor=None)

    user_font = str((tmp_path / "UserFont.ttf").resolve())
    auto_font = str((tmp_path / "AutoFont.ttf").resolve())

    director.set_font_path(user_font, user_set=True)
    assert renderer.get_style().font_path == user_font
    assert director.has_user_font_override() is True

    director.set_font_path(auto_font, user_set=False)
    assert renderer.get_style().font_path == user_font

    director.set_font_path(None, user_set=True)
    assert director.has_user_font_override() is False
    assert renderer.get_style().font_path is None

    director.set_font_path(auto_font, user_set=False)
    assert renderer.get_style().font_path == auto_font
