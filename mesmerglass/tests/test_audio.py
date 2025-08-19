"""Unit tests for the audio engine (pygame-based)."""

import pytest
from unittest.mock import MagicMock, patch

from ..engine.audio import Audio2, clamp


def test_clamp_basic():
    assert clamp(0.5, 0, 1) == 0.5
    assert clamp(-1, 0, 1) == 0
    assert clamp(2, 0, 1) == 1


@patch("pygame.mixer")
def test_audio_init_success(mock_mixer):
    mock_mixer.pre_init = MagicMock()
    mock_mixer.init = MagicMock()
    a = Audio2()
    assert a.init_ok is True


@patch("pygame.mixer")
def test_audio_init_failure(mock_mixer):
    def boom(*args, **kwargs):
        raise RuntimeError("init failed")
    mock_mixer.pre_init = MagicMock()
    mock_mixer.init = MagicMock(side_effect=boom)
    a = Audio2()
    assert a.init_ok is False


@patch("pygame.mixer")
def test_load1_fallback_to_streaming(mock_mixer):
    # Sound raises -> fallback to music path
    class FakeSound:
        def __init__(self, *a, **k):
            raise RuntimeError("no decode")

    mock_mixer.pre_init = MagicMock()
    mock_mixer.init = MagicMock()
    mock_mixer.Sound = FakeSound
    a = Audio2()
    a.load1("song.wav")
    assert a.music1_path == "song.wav"
    assert a.snd1 is None


@patch("pygame.mixer")
def test_load2_error_handled(mock_mixer):
    class FakeSound:
        def __init__(self, *a, **k):
            raise RuntimeError("no decode")

    mock_mixer.pre_init = MagicMock()
    mock_mixer.init = MagicMock()
    mock_mixer.Sound = FakeSound
    a = Audio2()
    a.load2("fx.wav")
    assert a.snd2 is None


@patch("pygame.mixer")
def test_play_and_stop(mock_mixer):
    # Arrange basic mixer mocks
    mock_mixer.pre_init = MagicMock()
    mock_mixer.init = MagicMock()

    class FakeChan:
        def __init__(self):
            self._vol = 0
        def set_volume(self, v):
            self._vol = v
        def stop(self):
            pass

    class FakeSound:
        def __init__(self, *a, **k):
            pass
        def play(self, loops=0):
            return FakeChan()

    mock_mixer.Sound = FakeSound
    mock_mixer.music = MagicMock()
    mock_mixer.music.get_busy.return_value = False

    a = Audio2()
    a.load1("song.wav")  # loads as full sound (since FakeSound doesn't fail)
    a.load2("fx.wav")
    a.play(vol1=0.7, vol2=0.2)
    assert a.chan1 is not None
    assert a.chan2 is not None

    # Stop should not raise
    a.stop()


@patch("pygame.mixer")
def test_set_vols(mock_mixer):
    mock_mixer.pre_init = MagicMock()
    mock_mixer.init = MagicMock()

    class FakeChan:
        def __init__(self):
            self.vol = None
        def set_volume(self, v):
            self.vol = v

    class FakeSound:
        def __init__(self, *a, **k):
            pass
        def play(self, loops=0):
            return FakeChan()

    mock_mixer.Sound = FakeSound
    mock_mixer.music = MagicMock()

    a = Audio2()
    a.load1("song.wav")
    a.load2("fx.wav")
    a.play(0.2, 0.8)
    a.set_vols(2.0, -1.0)  # clamp to 1.0 and 0.0
    assert a.chan1 is not None and a.chan2 is not None
