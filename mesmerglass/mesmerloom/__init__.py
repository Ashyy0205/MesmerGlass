"""MesmerLoom visuals engine (Phase 2 scaffolding).

Exports: Compositor, SpiralDirector.
"""
from .spiral import SpiralDirector  # noqa: F401
from .compositor import LoomCompositor

# Back-compat alias for older tests/imports:
Compositor = LoomCompositor

__all__ = ["LoomCompositor", "Compositor"]

__all__ = ["SpiralDirector", "Compositor"]
