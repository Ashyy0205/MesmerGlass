"""OpenVR utility functions and helpers.

Provides utility functions for working with OpenVR, including:
- Texture setup and management
- Coordinate system conversions
- Error handling and diagnostics
- FBO texture extraction
"""
from __future__ import annotations
import logging
from typing import Optional, Tuple

try:
    import openvr
    _OPENVR_AVAILABLE = True
except ImportError:
    openvr = None  # type: ignore
    _OPENVR_AVAILABLE = False

try:
    from OpenGL import GL
    _GL_AVAILABLE = True
except ImportError:
    GL = None  # type: ignore
    _GL_AVAILABLE = False


def is_openvr_available() -> bool:
    """Check if OpenVR is available and can be initialized.
    
    Returns:
        True if pyopenvr is installed and SteamVR runtime can be initialized.
    """
    if not _OPENVR_AVAILABLE:
        return False
    
    try:
        # Try a quick init/shutdown to verify runtime is available
        vr_system = openvr.init(openvr.VRApplication_Utility)
        if vr_system is None:
            return False
        openvr.shutdown()
        return True
    except Exception:
        return False


def get_fbo_color_texture(fbo_id: int) -> Optional[int]:
    """Extract the color texture ID from an FBO.
    
    Args:
        fbo_id: OpenGL framebuffer object ID
    
    Returns:
        Texture ID attached to GL_COLOR_ATTACHMENT0, or None if error
    """
    if not _GL_AVAILABLE or GL is None:
        return None
    
    try:
        # Save current binding
        prev_fbo = GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING)
        
        # Bind the FBO to query
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo_id)
        
        # Get the texture attached to color attachment 0
        texture_id = GL.glGetFramebufferAttachmentParameteriv(
            GL.GL_FRAMEBUFFER,
            GL.GL_COLOR_ATTACHMENT0,
            GL.GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME
        )
        
        # Restore previous binding
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, prev_fbo)
        
        return int(texture_id) if texture_id > 0 else None
        
    except Exception as e:
        logging.getLogger(__name__).error(
            "Failed to get FBO color texture: %s", e
        )
        return None


def create_eye_texture(texture_id: int, color_space: int = None) -> Optional[openvr.Texture_t]:  # type: ignore
    """Create an OpenVR texture struct for the given OpenGL texture.
    
    Args:
        texture_id: OpenGL texture ID
        color_space: OpenVR color space (default: ColorSpace_Gamma)
    
    Returns:
        Initialized Texture_t struct, or None if OpenVR unavailable
    """
    if not _OPENVR_AVAILABLE or openvr is None:
        return None
    
    try:
        texture = openvr.Texture_t()
        texture.handle = int(texture_id)
        texture.eType = openvr.TextureType_OpenGL
        
        if color_space is None:
            texture.eColorSpace = openvr.ColorSpace_Gamma
        else:
            texture.eColorSpace = color_space
        
        return texture
        
    except Exception as e:
        logging.getLogger(__name__).error(
            "Failed to create eye texture: %s", e
        )
        return None


def get_recommended_eye_size() -> Tuple[int, int]:
    """Get recommended render target size per eye from VR system.
    
    Returns:
        (width, height) tuple, or (1920, 1080) if unavailable
    """
    if not _OPENVR_AVAILABLE or openvr is None:
        return (1920, 1080)
    
    try:
        vr_system = openvr.VRSystem()
        if vr_system is None:
            return (1920, 1080)
        
        w, h = vr_system.getRecommendedRenderTargetSize()
        return (int(w), int(h))
        
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to get recommended eye size: %s (using 1920x1080)", e
        )
        return (1920, 1080)


def get_openvr_error_string(error_code: int) -> str:
    """Convert OpenVR error code to human-readable string.
    
    Args:
        error_code: OpenVR error code (VRCompositorError_*)
    
    Returns:
        Error description string
    """
    if not _OPENVR_AVAILABLE or openvr is None:
        return f"Unknown error ({error_code})"
    
    # Map common error codes
    error_map = {
        openvr.VRCompositorError_None: "No error",
        openvr.VRCompositorError_RequestFailed: "Request failed",
        openvr.VRCompositorError_IncompatibleVersion: "Incompatible version",
        openvr.VRCompositorError_DoNotHaveFocus: "Application does not have focus",
        openvr.VRCompositorError_InvalidTexture: "Invalid texture",
        openvr.VRCompositorError_IsNotSceneApplication: "Not a scene application",
        openvr.VRCompositorError_TextureIsOnWrongDevice: "Texture is on wrong device",
        openvr.VRCompositorError_TextureUsesUnsupportedFormat: "Unsupported texture format",
        openvr.VRCompositorError_SharedTexturesNotSupported: "Shared textures not supported",
        openvr.VRCompositorError_IndexOutOfRange: "Index out of range",
        openvr.VRCompositorError_AlreadySubmitted: "Already submitted",
    }
    
    return error_map.get(error_code, f"Unknown error ({error_code})")


def log_vr_system_info():
    """Log information about the connected VR system for diagnostics."""
    logger = logging.getLogger(__name__)
    
    if not _OPENVR_AVAILABLE or openvr is None:
        logger.info("[VR] OpenVR not available")
        return
    
    try:
        vr_system = openvr.VRSystem()
        if vr_system is None:
            logger.info("[VR] No VR system connected")
            return
        
        # Get HMD model
        try:
            model = vr_system.getStringTrackedDeviceProperty(
                openvr.k_unTrackedDeviceIndex_Hmd,
                openvr.Prop_ModelNumber_String
            )
            logger.info("[VR] HMD Model: %s", model)
        except Exception:
            pass
        
        # Get recommended size
        w, h = vr_system.getRecommendedRenderTargetSize()
        logger.info("[VR] Recommended eye resolution: %dx%d", w, h)
        
        # Get display frequency
        try:
            freq = vr_system.getFloatTrackedDeviceProperty(
                openvr.k_unTrackedDeviceIndex_Hmd,
                openvr.Prop_DisplayFrequency_Float
            )
            logger.info("[VR] Display frequency: %.1f Hz", freq)
        except Exception:
            pass
        
    except Exception as e:
        logger.error("[VR] Failed to get VR system info: %s", e)
