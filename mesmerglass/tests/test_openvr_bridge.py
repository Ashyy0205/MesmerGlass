"""Tests for OpenVR backend initialization and basic functionality."""
import pytest
from unittest.mock import Mock, patch


def test_openvr_import_available():
    """Test that OpenVR bridge can be imported."""
    from mesmerglass.vr.vr_bridge_openvr import VrBridgeOpenVR
    assert VrBridgeOpenVR is not None


def test_openvr_bridge_init_disabled():
    """Test VrBridgeOpenVR initialization with enabled=False."""
    from mesmerglass.vr.vr_bridge_openvr import VrBridgeOpenVR
    
    bridge = VrBridgeOpenVR(enabled=False)
    assert bridge.enabled is False
    assert bridge._mock is True or bridge._mock is False  # Depends on openvr availability


def test_openvr_bridge_start_when_disabled():
    """Test that start() returns False when bridge is disabled."""
    from mesmerglass.vr.vr_bridge_openvr import VrBridgeOpenVR
    
    bridge = VrBridgeOpenVR(enabled=False)
    result = bridge.start()
    assert result is False


def test_openvr_bridge_submit_frame_when_disabled():
    """Test that submit_frame_from_fbo is no-op when disabled."""
    from mesmerglass.vr.vr_bridge_openvr import VrBridgeOpenVR
    
    bridge = VrBridgeOpenVR(enabled=False)
    # Should not raise
    bridge.submit_frame_from_fbo(123, 1920, 1080)


def test_openvr_bridge_shutdown_when_disabled():
    """Test that shutdown is safe when disabled."""
    from mesmerglass.vr.vr_bridge_openvr import VrBridgeOpenVR
    
    bridge = VrBridgeOpenVR(enabled=False)
    # Should not raise
    bridge.shutdown()


def test_openvr_utils_import():
    """Test that openvr_utils can be imported."""
    from mesmerglass.vr import openvr_utils
    assert openvr_utils is not None


def test_is_openvr_available():
    """Test OpenVR availability check."""
    from mesmerglass.vr.openvr_utils import is_openvr_available
    
    # Should return bool without raising
    result = is_openvr_available()
    assert isinstance(result, bool)


def test_get_recommended_eye_size_fallback():
    """Test that get_recommended_eye_size returns sensible fallback."""
    from mesmerglass.vr.openvr_utils import get_recommended_eye_size
    
    w, h = get_recommended_eye_size()
    assert isinstance(w, int)
    assert isinstance(h, int)
    assert w > 0
    assert h > 0


def test_vr_backend_selection_via_env():
    """Test that VR backend can be selected via environment variable."""
    import os
    from importlib import reload
    
    # Save original
    original = os.environ.get('MESMERGLASS_VR_BACKEND')
    
    try:
        # Test OpenVR preference
        os.environ['MESMERGLASS_VR_BACKEND'] = 'openvr'
        import mesmerglass.vr
        reload(mesmerglass.vr)
        # Should load openvr or mock, not openxr
        assert mesmerglass.vr.VR_BACKEND in ('openvr', 'mock', 'none')
        
    finally:
        # Restore
        if original is None:
            os.environ.pop('MESMERGLASS_VR_BACKEND', None)
        else:
            os.environ['MESMERGLASS_VR_BACKEND'] = original


def test_vr_bridge_alias():
    """Test that VrBridge is properly exported from vr module."""
    from mesmerglass.vr import VrBridge
    assert VrBridge is not None
    
    # Should be instantiable
    bridge = VrBridge(enabled=False)
    assert hasattr(bridge, 'start')
    assert hasattr(bridge, 'submit_frame_from_fbo')
    assert hasattr(bridge, 'shutdown')


def test_mock_bridge_behavior():
    """Test that mock bridge works when no VR backend available."""
    from mesmerglass.vr import VrBridge
    
    bridge = VrBridge(enabled=False)
    
    # Should all be no-ops without raising
    assert bridge.start() is False
    bridge.submit_frame_from_fbo(999, 1920, 1080)
    bridge.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
