"""VR utilities with OpenVR/OpenXR backend support.

Submodules:
- vr_bridge_openvr: OpenVR + OpenGL compositor bridge (preferred for SteamVR)
- vr_bridge: OpenXR + OpenGL swapchain bridge (legacy, fallback)
- offscreen: Minimal offscreen OpenGL context + FBO utilities for tests/CLI
- openvr_utils: Helper functions for OpenVR integration

Backend selection:
- Environment variable: MESMERGLASS_VR_BACKEND=openvr|openxr
- Default: Try OpenVR first, fallback to OpenXR
- Both fall back to mock mode if unavailable
"""
import os
import logging

# Determine which VR backend to use
VR_BACKEND = os.environ.get('MESMERGLASS_VR_BACKEND', 'auto').lower()
_logger = logging.getLogger(__name__)

# Try to import preferred backend
VrBridge = None
_backend_name = None

if VR_BACKEND in ('openvr', 'auto'):
    try:
        from .vr_bridge_openvr import VrBridgeOpenVR as VrBridge
        _backend_name = 'openvr'
        _logger.debug("[VR] Using OpenVR backend")
    except Exception as e:
        if VR_BACKEND == 'openvr':
            _logger.warning("[VR] OpenVR backend requested but unavailable: %s", e)
        # Fall through to try OpenXR

if VrBridge is None and VR_BACKEND in ('openxr', 'auto'):
    try:
        from .vr_bridge import VrBridge  # Legacy OpenXR implementation
        _backend_name = 'openxr'
        _logger.debug("[VR] Using OpenXR backend (legacy)")
    except Exception as e:
        if VR_BACKEND == 'openxr':
            _logger.warning("[VR] OpenXR backend requested but unavailable: %s", e)

# If still None, create a mock bridge that does nothing
if VrBridge is None:
    _logger.warning("[VR] No VR backend available, creating mock bridge")
    _backend_name = 'mock'
    
    class MockVrBridge:
        """Mock VR bridge that does nothing (no VR backend available)."""
        def __init__(self, enabled: bool = False):
            self.enabled = False
            self._mock = True
        
        def start(self) -> bool:
            return False
        
        def submit_frame_from_fbo(self, source_fbo: int, src_w: int, src_h: int) -> None:
            pass
        
        def shutdown(self) -> None:
            pass
    
    VrBridge = MockVrBridge  # type: ignore

__all__ = [
    "VrBridge",
    "VR_BACKEND",
]

# Export the actual backend name that was loaded
VR_BACKEND = _backend_name or 'none'
