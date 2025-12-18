import numpy as np
from pathlib import Path

from mesmerglass.mesmerloom.visual_director import VisualDirector


class _FakeImage:
    def __init__(self, width: int = 64, height: int = 64):
        self.width = width
        self.height = height
        self.path = Path("fake/test.png")
        self.data = np.zeros((height, width, 4), dtype=np.uint8)


class _FakeThemeBank:
    def __init__(self, sequence):
        self._sequence = list(sequence)

    def get_image(self, alternate: bool = True):  # noqa: ARG002 (signature parity)
        if not self._sequence:
            return None
        return self._sequence.pop(0)


class _FakeCompositor:
    def __init__(self):
        self.upload_calls = []
        self.set_calls = []
        self._zoom_animation_enabled = True

    def upload_image_to_gpu(self, image_data, generate_mipmaps: bool = False):  # noqa: ARG002
        texture_id = len(self.upload_calls) + 1
        self.upload_calls.append((image_data.width, image_data.height))
        return texture_id

    def set_background_texture(self, texture_id, zoom: float, image_width: int, image_height: int):
        self.set_calls.append((texture_id, zoom, image_width, image_height))

    def start_zoom_animation(self, *args, **kwargs):  # noqa: D401
        """Record that zoom animation was requested."""
        self.zoom_call = (args, kwargs)


def test_on_change_image_defers_until_ready():
    fake_image = _FakeImage()
    theme_bank = _FakeThemeBank([None, fake_image, fake_image])
    compositor = _FakeCompositor()
    director = VisualDirector(theme_bank=theme_bank, compositor=compositor)

    # First call returns None to simulate ThemeBank still loading
    director._on_change_image(0)
    assert compositor.upload_calls == []
    stats = director.get_media_pipeline_stats()
    assert stats["pending_retries"] == 1
    assert stats["last_image_still_loading"] is True

    # Second call should upload exactly once and apply background
    director._on_change_image(1)
    assert len(compositor.upload_calls) == 1
    assert len(compositor.set_calls) == 1
    stats = director.get_media_pipeline_stats()
    assert stats["pending_retries"] == 0
    assert stats["last_image_path"].endswith("test.png")

    # Third call sees same image path and must skip redundant uploads
    director._on_change_image(2)
    assert len(compositor.upload_calls) == 1
    assert len(compositor.set_calls) == 1
