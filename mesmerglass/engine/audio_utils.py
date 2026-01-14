"""Audio utility helpers for duration probing and normalization."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Optional

try:
    import pygame
except Exception:  # pragma: no cover - pygame may be unavailable in headless docs builds
    pygame = None  # type: ignore

_log = logging.getLogger(__name__)
_probe_lock = Lock()


def _ensure_mixer() -> bool:
    """Initialize pygame mixer lazily.

    Returns True when mixer is ready, False otherwise. Any initialization error is logged once.
    """
    if pygame is None:
        _log.debug("pygame not available; audio probing disabled")
        return False
    try:
        if not pygame.mixer.get_init():
            # Keep mixer config consistent with the main AudioEngine so that
            # later synthesized buffers (e.g. Shepard tone bed) match channel
            # depth expectations.
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
        return True
    except Exception as exc:  # pragma: no cover - depends on host audio stack
        _log.warning("pygame mixer init failed for duration probe: %s", exc)
        return False


@lru_cache(maxsize=128)
def probe_audio_duration(path: str | Path) -> Optional[float]:
    """Return audio duration in seconds using pygame's Sound metadata.

    Args:
        path: Path to audio file. Relative paths are resolved relative to current working directory.

    Returns:
        Duration in seconds, or None if detection fails.
    """
    target = Path(path)
    if not target.exists():
        _log.debug("Audio probe skipped (missing file): %s", target)
        return None

    with _probe_lock:
        if not _ensure_mixer():
            return None
        try:
            sound = pygame.mixer.Sound(str(target))  # type: ignore[arg-type]
            try:
                length = float(sound.get_length())
            finally:
                del sound
            if length > 0:
                return length
        except Exception as exc:
            _log.warning("Failed to probe audio duration for %s: %s", target, exc)
    return None


def normalize_volume(value: float) -> float:
    """Clamp and normalize arbitrary numeric volume inputs to 0..1."""
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0
