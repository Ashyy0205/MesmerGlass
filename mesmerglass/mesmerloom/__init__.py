"""MesmerLoom visuals engine (Phase 2 scaffolding).

Exports: Compositor, SpiralDirector.
"""
from .spiral import SpiralDirector  # noqa: F401
from .compositor import Compositor  # noqa: F401

__all__ = ["SpiralDirector", "Compositor"]
