import os
import pytest

from mesmerglass.vr.vr_bridge import VrBridge


def test_choose_best_format_prefers_srgb8a8():
    b = VrBridge(enabled=False)
    # Available includes RGBA8 and SRGB8_A8; should pick SRGB8_A8 (0x8C43)
    fmt = b._choose_gl_format([0x8058, 0x8C43, 0x881A])
    assert int(fmt) == 0x8C43


def test_choose_best_format_fallback_first_available():
    b = VrBridge(enabled=False)
    # No preferred formats; should pick first
    fmt = b._choose_gl_format([0x1908, 0x1907])  # GL_RGBA=0x1908, GL_RGB=0x1907
    assert int(fmt) == 0x1908


def test_choose_best_format_when_none_available_returns_default():
    b = VrBridge(enabled=False)
    fmt = b._choose_gl_format(None)
    # Expect our fallback constant 0x8C43 (GL_SRGB8_ALPHA8)
    assert int(fmt) == 0x8C43
