"""OpenVR VR bridge (SteamVR native).

This module provides VR output using OpenVR (pyopenvr) for direct SteamVR integration.
It maintains API compatibility with the existing VrBridge class while using OpenVR
instead of OpenXR for better SteamVR compatibility and simpler implementation.

Key points:
- Dependency: pyopenvr (pip install openvr)
- Graphics API: OpenGL via native OpenVR compositor
- Mode: Head-locked rendering (can extend to overlay mode)
- Fallback: If OpenVR is unavailable, switches to mock mode

API surface (compatible with OpenXR VrBridge):
- VrBridgeOpenVR(enabled: bool = False)
- start() -> bool
- submit_frame_from_fbo(source_fbo: int, src_w: int, src_h: int) -> None
- shutdown() -> None

Integration contract (same as OpenXR):
- The app renders to an FBO or default framebuffer (typically 1920x1080)
- On each frame, after render completes and context is current, call
  `bridge.submit_frame_from_fbo(fbo_id, 1920, 1080)`
- If the bridge is in mock mode, this is a quick no-op
"""
from __future__ import annotations
import logging
from typing import Optional

# Try to import OpenVR bindings
_OPENVR_AVAILABLE = False
_OPENVR_MODULE = None

try:
    import openvr
    _OPENVR_AVAILABLE = True
    _OPENVR_MODULE = openvr
except ImportError:
    openvr = None  # type: ignore

# Try to import OpenGL for texture operations
try:
    from OpenGL import GL
except ImportError:
    GL = None  # type: ignore


class VrBridgeOpenVR:
    """Head-locked VR bridge using OpenVR (SteamVR native).
    
    This class provides the same API as the OpenXR-based VrBridge but uses
    OpenVR for direct SteamVR integration. It handles initialization, frame
    submission, and cleanup with graceful fallback to mock mode if OpenVR
    is unavailable.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize the VR bridge.
        
        Args:
            enabled: If False, bridge runs in mock mode (no-op). If True,
                    attempts to initialize OpenVR.
        """
        self.enabled = bool(enabled)
        self._mock = not _OPENVR_AVAILABLE
        self._vr_system: Optional[openvr.IVRSystem] = None  # type: ignore
        self._compositor: Optional[openvr.IVRCompositor] = None  # type: ignore
        self._logger = logging.getLogger(__name__)
        
        # Track initialization state
        self._initialized = False
        self._frame_count = 0
        
        # Texture handles for each eye
        self._left_texture: Optional[openvr.Texture_t] = None  # type: ignore
        self._right_texture: Optional[openvr.Texture_t] = None  # type: ignore
        
        # Recommended render target size per eye
        self._eye_width = 1920
        self._eye_height = 1080
        
        # Cache for error suppression (avoid log spam)
        self._suppress_log_once = False

    def start(self) -> bool:
        """Initialize OpenVR session and compositor.
        
        Returns:
            True if active (OpenVR initialized), False if running in mock mode.
        """
        if not self.enabled:
            self._logger.info("[VR] VrBridgeOpenVR disabled; mock mode")
            self._mock = True
            return False
        
        if self._mock:
            self._logger.warning("[VR] OpenVR not available; running in mock mode")
            return False
        
        if self._initialized:
            self._logger.warning("[VR] Already initialized")
            return True
        
        try:
            self._logger.info("[VR] Initializing OpenVR...")
            
            # Initialize OpenVR system
            self._vr_system = openvr.init(openvr.VRApplication_Scene)
            
            if self._vr_system is None:
                self._logger.error("[VR] Failed to initialize OpenVR system")
                self._mock = True
                return False
            
            # Get compositor interface
            self._compositor = openvr.VRCompositor()
            
            if self._compositor is None:
                self._logger.error("[VR] Failed to get OpenVR compositor")
                self._mock = True
                openvr.shutdown()
                return False
            
            # Get recommended render target size
            w, h = self._vr_system.getRecommendedRenderTargetSize()
            self._eye_width = w
            self._eye_height = h
            
            self._logger.info(
                "[VR] OpenVR initialized successfully (eye resolution: %dx%d)",
                self._eye_width, self._eye_height
            )
            
            # Create texture structs for each eye
            self._left_texture = openvr.Texture_t()
            self._right_texture = openvr.Texture_t()
            
            # Set texture type to OpenGL
            self._left_texture.eType = openvr.TextureType_OpenGL
            self._right_texture.eType = openvr.TextureType_OpenGL
            
            # Use Gamma color space (matches our rendering)
            self._left_texture.eColorSpace = openvr.ColorSpace_Gamma
            self._right_texture.eColorSpace = openvr.ColorSpace_Gamma
            
            self._initialized = True
            return True
            
        except Exception as e:
            self._logger.error("[VR] OpenVR initialization failed: %s", e)
            self._mock = True
            try:
                if _OPENVR_MODULE:
                    _OPENVR_MODULE.shutdown()
            except Exception:
                pass
            return False

    def submit_frame_from_fbo(self, source_fbo: int, src_w: int, src_h: int) -> None:
        """Submit rendered frame from FBO to VR compositor.
        
        Args:
            source_fbo: OpenGL FBO id containing the rendered frame
            src_w: Source framebuffer width
            src_h: Source framebuffer height
        """
        if self._mock or not self._initialized:
            # Mock mode: just count frames silently
            self._frame_count += 1
            if self._frame_count == 1 and not self._suppress_log_once:
                self._logger.debug("[VR] Mock mode: frame submission is no-op")
                self._suppress_log_once = True
            return
        
        if not self._compositor or not self._left_texture or not self._right_texture:
            self._logger.error("[VR] Compositor or textures not initialized")
            return
        
        try:
            # Get the color attachment texture from the FBO
            # Assumes FBO has a texture attached to GL_COLOR_ATTACHMENT0
            if GL:
                # TODO: Get texture ID from FBO
                # For now, assume source_fbo is directly usable as texture ID
                # (caller should pass texture ID, not FBO ID in production)
                texture_id = source_fbo
                
                # Set texture handle for both eyes (for now, same image)
                # TODO: Render separate images for each eye
                self._left_texture.handle = texture_id
                self._right_texture.handle = texture_id
                
                # Submit to compositor
                error_left = self._compositor.submit(openvr.Eye_Left, self._left_texture)
                error_right = self._compositor.submit(openvr.Eye_Right, self._right_texture)
                
                # Check for errors
                if error_left != openvr.VRCompositorError_None:
                    self._logger.warning(
                        "[VR] Left eye submission error: %s", 
                        error_left
                    )
                
                if error_right != openvr.VRCompositorError_None:
                    self._logger.warning(
                        "[VR] Right eye submission error: %s",
                        error_right
                    )
                
                # Post present handoff (tells compositor frame is complete)
                self._compositor.postPresentHandoff()
                
                self._frame_count += 1
                
                if self._frame_count % 300 == 1:  # Log every ~5 seconds at 60fps
                    self._logger.debug("[VR] Submitted frame %d", self._frame_count)
            
        except Exception as e:
            self._logger.error("[VR] Frame submission failed: %s", e)

    def shutdown(self) -> None:
        """Clean shutdown of OpenVR session."""
        if self._mock or not self._initialized:
            return
        
        try:
            self._logger.info("[VR] Shutting down OpenVR (submitted %d frames)", self._frame_count)
            
            # Clear references
            self._compositor = None
            self._vr_system = None
            self._left_texture = None
            self._right_texture = None
            
            # Shutdown OpenVR
            if _OPENVR_MODULE:
                _OPENVR_MODULE.shutdown()
            
            self._initialized = False
            
        except Exception as e:
            self._logger.error("[VR] Shutdown error: %s", e)

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        try:
            self.shutdown()
        except Exception:
            pass


# Convenience alias for drop-in replacement
VrBridge = VrBridgeOpenVR
