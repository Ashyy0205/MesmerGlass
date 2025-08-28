"""Deprecated legacy spiral module.

This legacy path now re-exports the MesmerLoom spiral implementation and
emits a DeprecationWarning on import. Update imports to
``from mesmerglass.mesmerloom.spiral import ...``.
"""
from __future__ import annotations
import warnings as _warnings

_warnings.filterwarnings("default", category=DeprecationWarning)
_warnings.warn(
    "mesmerglass.engine.spiral is deprecated; use mesmerglass.mesmerloom.spiral",
    DeprecationWarning,
    stacklevel=2,
)

from mesmerglass.mesmerloom.spiral import *  # type: ignore  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Legacy compatibility layer
# The historical API exposed SpiralConfig dataclass and a SpiralDirector that
# accepted (cfg: SpiralConfig, seed: int|None). Tests still rely on a subset
# of that interface, so we provide a thin wrapper translating to the new
# MesmerLoom SpiralDirector (imported above). This should be removed once
# legacy tests are retired.
# ---------------------------------------------------------------------------
from dataclasses import dataclass as _dataclass
from typing import Optional as _Optional, Dict as _Dict, Any as _Any

@_dataclass
class SpiralConfig:  # minimal fields used in tests
    intensity: float = 0.0
    speed_base_cps: float = 0.09

class SpiralDirector:  # type: ignore[override]
    MAX_PHASE_SPEED = 0.18  # map to new SPEED_CAP
    BAR_WIDTH_MIN = 0.36
    BAR_WIDTH_MAX = 0.62
    CONTRAST_MIN = 0.85
    CONTRAST_MAX = 1.25

    def __init__(self, cfg: SpiralConfig | None = None, seed: _Optional[int] = None):
        from mesmerglass.mesmerloom import spiral as _loom
        self._loom = _loom.SpiralDirector(seed=seed)
        self.cfg = cfg or SpiralConfig()
        # apply initial intensity
        self._loom.set_intensity(self.cfg.intensity)
        self._loom.update(1/60)
        self.cfg.speed_base_cps = self._loom.state.base_speed

    # legacy API
    def set_intensity(self, v: float, abrupt: bool = False):  # abrupt ignored (new director handles slew internally)
        self._loom.set_intensity(v)
        # force an update tick to realize new base speed for test assertion
        self._loom.update(1/60)
        self.cfg.speed_base_cps = self._loom.state.base_speed

    def update(self, dt: float):
        self._loom.update(dt)

    # provide uniform dict resembling legacy keys
    def uniforms(self) -> _Dict[str, _Any]:
        s = self._loom.state
        return {
            'uArms': 4,  # fixed in legacy tests
            'uBarWidth': s.bar_width,
            'uOpacity': s.opacity,  # legacy name
            'uSpeedCPS': s.effective_speed,
            'uContrast': s.contrast,
        }

    # constants already class attributes; legacy tests access via instance
