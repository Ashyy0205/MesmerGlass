"""OpenXR VR bridge (scaffold with mock fallback).

This module provides a minimal head-locked VR output path using OpenXR.
It is designed to blit the app's existing 1920x1080 OpenGL render into
per-eye swapchains provided by the OpenXR runtime (e.g., ALVR on Windows).

Key points:
- Optional dependency: Python OpenXR bindings (imported as `openxr`)
- Graphics API: OpenGL via XR_KHR_opengl_enable
- Mode: VIEW space for head-locked imagery
- Fallback: If OpenXR is unavailable or binding fails, the bridge switches
  to a no-op mock mode that logs frames but does not affect rendering.

API surface (stable):
- VrBridge(enabled: bool = False)
- start()
- submit_frame_from_fbo(source_fbo: int, src_w: int, src_h: int) -> None
- shutdown()

Integration contract:
- The app renders to an FBO or default framebuffer of size 1920x1080.
- On each frame, after render completes and the context is current, call
  `bridge.submit_frame_from_fbo(fbo_id, 1920, 1080)`.
- If the bridge is in mock mode, this is a quick no-op.

NOTE ON CONTEXT BINDING (Windows / PyQt6):
Creating an OpenXR session with OpenGL on Windows requires native HGLRC/HDC,
which are normally obtained from a WGL context (GLFW exposes these easily).
QOpenGLWindow/QOpenGLContext do not expose these handles directly via public
APIs. For this initial scaffold, we:
- Attempt to create a session using the current context if bindings can be
  resolved by the OpenXR Python package (platform structs),
- Otherwise run in mock mode until a native handle retrieval strategy is added
  (e.g., a small SIP helper, or switching to a shared GLFW context for VR).
"""
from __future__ import annotations
import logging
from typing import Optional, List, Tuple

_XR_AVAILABLE = False
_XR_FALLBACK = False
_XR_MODULE_NAME = None
try:  # Preferred import name used by some bindings
    import openxr as xr  # type: ignore
    # Verify it has the class-based API we rely on
    if hasattr(xr, 'ApplicationInfo') and (
        hasattr(xr, 'GraphicsBindingOpenGLWin32KHR') or hasattr(xr, 'GraphicsBindingOpenGLWin32KHR'.lower())
    ):
        _XR_AVAILABLE = True
        _XR_FALLBACK = False
        _XR_MODULE_NAME = 'openxr'
    else:
        xr = None  # type: ignore
        raise ImportError("openxr module lacks required classes")
except Exception:
    # Try common pyopenxr layouts
    try:
        # Some distributions expose classes under pyopenxr.openxr
        from pyopenxr import openxr as xr  # type: ignore
        _XR_AVAILABLE = True
        _XR_FALLBACK = True
        _XR_MODULE_NAME = 'pyopenxr.openxr'
    except Exception:
        try:
            import pyopenxr.openxr as xr  # type: ignore
            _XR_AVAILABLE = True
            _XR_FALLBACK = True
            _XR_MODULE_NAME = 'pyopenxr.openxr'
        except Exception:
            try:
                import pyopenxr as xr  # type: ignore
                # Verify it actually has the class-based API
                if hasattr(xr, 'ApplicationInfo') and (
                    hasattr(xr, 'GraphicsBindingOpenGLWin32KHR') or hasattr(xr, 'GraphicsBindingOpenGLWin32KHR'.lower())
                ):
                    _XR_AVAILABLE = True
                    _XR_FALLBACK = True
                    _XR_MODULE_NAME = 'pyopenxr'
                else:
                    xr = None  # type: ignore
            except Exception:
                xr = None  # type: ignore
                # Final fallback: some wheels expose the package name 'xr'
                try:
                    import xr as xr  # type: ignore  # noqa: F401
                    if hasattr(xr, 'ApplicationInfo') and (
                        hasattr(xr, 'GraphicsBindingOpenGLWin32KHR') or hasattr(xr, 'GraphicsBindingOpenGLWin32KHR'.lower())
                    ):
                        _XR_AVAILABLE = True
                        _XR_FALLBACK = True
                        _XR_MODULE_NAME = 'xr'
                    else:
                        xr = None  # type: ignore
                except Exception:
                    xr = None  # type: ignore

try:  # Optional GL helpers
    from OpenGL import GL
except Exception:  # pragma: no cover
    GL = None  # type: ignore


# ============================================================================
# ROBUST SPACE CREATION HELPERS
# ============================================================================

# Identity pose constant for space creation
if _XR_AVAILABLE and xr is not None:
    try:
        IDENTITY_POSE = xr.Posef(
            orientation=xr.Quaternionf(0.0, 0.0, 0.0, 1.0),
            position=xr.Vector3f(0.0, 0.0, 0.0),
        )
    except Exception:
        IDENTITY_POSE = None
else:
    IDENTITY_POSE = None

# SteamVR compositor layer flags for opaque/gamma-correct content
# These flags are CRITICAL for making layers visible in SteamVR
# Without these, the compositor treats layers as transparent or behind the environment
XR_COMPOSITION_LAYER_BLEND_TEXTURE_SOURCE_ALPHA_BIT = 0x00000001
XR_COMPOSITION_LAYER_CORRECT_CHROMATIC_ABERRATION_BIT = 0x00000002  # Also known as CORRECT_CONTENT_GAMMA_BIT_MNDX
XR_COMPOSITION_LAYER_UNPREMULTIPLIED_ALPHA_BIT = 0x00000004

# Fallback order for reference space types (LOCAL → STAGE → VIEW)
# VIEW is head-locked and can be used for quad layer fallback
if _XR_AVAILABLE and xr is not None:
    try:
        SPACE_FALLBACK_ORDER = [
            xr.ReferenceSpaceType.LOCAL,
            xr.ReferenceSpaceType.STAGE,
            xr.ReferenceSpaceType.VIEW,
        ]
    except Exception:
        SPACE_FALLBACK_ORDER = []
else:
    SPACE_FALLBACK_ORDER = []


def _is_valid_handle(h) -> bool:
    """Check if an OpenXR handle is valid (non-NULL).
    
    pyopenxr objects usually expose .handle or are truthy when non-zero.
    This helper tries multiple detection strategies to avoid false positives.
    """
    if h is None:
        return False
    try:
        # Strategy 1: Try .handle attribute (some pyopenxr builds)
        raw = getattr(h, "handle", None)
        if raw is not None:
            return int(raw) != 0
        
        # Strategy 2: Try .value attribute (ctypes-like objects)
        raw = getattr(h, "value", None)
        if raw is not None:
            return int(raw) != 0
        
        # Strategy 3: Try casting via ctypes
        try:
            import ctypes
            ptr_val = ctypes.cast(h, ctypes.c_void_p).value
            return ptr_val is not None and ptr_val != 0
        except Exception:
            pass
        
        # Strategy 4: Fall back to bool(h) as validity check
        return bool(h)
    except Exception:
        return False


def _create_first_valid_space(session, xr_module, logger):
    """Try to create reference spaces in fallback order until one succeeds.
    
    Returns: (space_type, space_handle) or (None, None) if all fail.
    
    This handles the common case where LOCAL or STAGE space creation
    returns a NULL handle without raising an exception.
    """
    if not SPACE_FALLBACK_ORDER:
        logger.error("[XR] No space fallback order defined (OpenXR not available)")
        return None, None
    
    last_err = None
    for ref_type in SPACE_FALLBACK_ORDER:
        try:
            # Use the identity pose constant
            pose = IDENTITY_POSE
            if pose is None:
                # Construct inline if constant creation failed
                pose = xr_module.Posef(
                    orientation=xr_module.Quaternionf(0.0, 0.0, 0.0, 1.0),
                    position=xr_module.Vector3f(0.0, 0.0, 0.0),
                )
            
            # Build ReferenceSpaceCreateInfo struct
            # pyopenxr signature: (session, create_info) where create_info contains type + pose
            create_info = xr_module.ReferenceSpaceCreateInfo(
                reference_space_type=ref_type,
                pose_in_reference_space=pose
            )
            
            # Call create_reference_space with proper signature
            space = xr_module.create_reference_space(session, create_info)
            
            # CRITICAL: Verify the handle is actually valid (non-NULL)
            if _is_valid_handle(space):
                logger.info("[XR] ✅ Created %s space with VALID handle", ref_type.name if hasattr(ref_type, 'name') else ref_type)
                return ref_type, space
            else:
                logger.warning("[XR] ⚠️ %s space returned NULL handle (silently failed)", ref_type.name if hasattr(ref_type, 'name') else ref_type)
        except Exception as e:
            last_err = e
            logger.warning("[XR] ❌ create_reference_space(%s) raised: %s", 
                          ref_type.name if hasattr(ref_type, 'name') else ref_type, e)
    
    # All space types failed
    logger.error("[XR] 🚨 FATAL: Could not create ANY reference space with a valid handle!")
    if last_err:
        logger.error("[XR] Last error was: %s", last_err)
    return None, None


class VrBridge:
    """Head-locked VR bridge (OpenXR if available, else mock)."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = bool(enabled)
        self._mock = not _XR_AVAILABLE
        self._instance = None
        self._system_id = None
        self._session = None
        self._space = None
        self._views = []
        self._swapchains = []  # (swapchain, w, h)
        self._swapchain_images = []  # per-swapchain list of GL images (GLuint)
        self._frame_state = None
        self._frame_started = False
        self._logger = logging.getLogger(__name__)
        
        # CRITICAL: Set action manifest path for SteamVR
        # SteamVR requires this to exit loading screen and show rendered content
        self._setup_action_manifest_path()
        # Track whether xrBeginSession actually succeeded. If False, we must not
        # drive the XR frame loop (wait/begin_frame/end_frame) to avoid runtime crashes.
        self._session_began = False
        # Log suppression flag to avoid per-frame spam when frames are disabled
        self._suppress_log_once = False
        # Cache of resolved OpenXR procs (module wrapper or function pointer)
        self._proc_cache: dict[str, object] = {}
        # Deferred init: if we couldn't bind GL at start(), allow initializing later
        self._deferred_init = False
        # WGL handles (diagnostics; used to detect context/share changes)
        self._wgl_hdc: int | None = None
        self._wgl_hglrc: int | None = None
        # Session state tracking (critical for visibility)
        self._session_state = None  # Current OpenXR session state
        self._session_running = False  # True when in READY/SYNCHRONIZED/VISIBLE/FOCUSED states
        # Space type and fallback tracking (for robust space creation)
        self._space_type = None  # Which ReferenceSpaceType succeeded (LOCAL/STAGE/VIEW)
        self._view_space = None  # Separate VIEW space for quad layer fallback
        self._last_locate_ok = False  # Track if locate_views succeeded this frame

    def start(self) -> bool:
        """Initialize OpenXR session and swapchains if possible.

        Returns True if active (OpenXR initialized), False if running in mock.
        """
        if not self.enabled:
            self._logger.info("[VR] VrBridge disabled; mock mode")
            self._mock = True
            return False
        if self._mock:
            self._logger.warning("[VR] OpenXR not available; running in mock mode")
            return False
        try:
            if globals().get('_XR_AVAILABLE', False):
                try:
                    self._logger.info("[VR] OpenXR bindings module: %s (fallback=%s)", globals().get('_XR_MODULE_NAME', '?'), globals().get('_XR_FALLBACK', False))
                except Exception:
                    pass
            # 1) Create instance
            app_info = xr.ApplicationInfo(
                application_name="MesmerGlass",
                application_version=1,
                engine_name="MesmerGlass",
                engine_version=1
            )
            # Some bindings may not expose the constant; use string as fallback
            try:
                khr_gl = xr.KHR_OPENGL_ENABLE_EXTENSION_NAME
            except Exception:
                khr_gl = "XR_KHR_opengl_enable"
            exts = [khr_gl]

            # Compatibility: different bindings accept different create_instance signatures
            self._instance = self._create_instance_compat(xr, app_info, exts)
            # 2) Get system id for HMD
            # Compatibility: some bindings use camelCase field names
            try:
                sys_get_info = xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY)
            except TypeError:
                sys_get_info = xr.SystemGetInfo(formFactor=xr.FormFactor.HEAD_MOUNTED_DISPLAY)  # type: ignore
            self._system_id = self._xr_get_system(self._instance, sys_get_info)

            # 2.5) Get OpenGL graphics requirements (critical for proper context binding)
            try:
                graphics_reqs = self._xr_get_opengl_graphics_requirements(self._instance, self._system_id)
                self._logger.debug("[VR] OpenGL graphics requirements: min_version=%s max_version=%s", 
                                   getattr(graphics_reqs, 'min_api_version_supported', 'unknown'),
                                   getattr(graphics_reqs, 'max_api_version_supported', 'unknown'))
            except Exception as e:
                self._logger.warning("[VR] Failed to get OpenGL graphics requirements: %s", e)

            # 3) Attempt to create session with current OpenGL binding. If no GL context
            # is current yet (typical before the Qt compositor exists), defer session
            # creation to ensure_initialized_with_current_context().
            graphics_binding = self._build_opengl_binding()
            if graphics_binding is None:
                self._logger.info("[VR] Deferred OpenXR session until a GL context is current (Qt compositor)")
                self._deferred_init = True
                # Keep instance/system alive; we'll complete init later.
                self._session = None
            else:
                # Compatibility: next vs nextChain and field names
                try:
                    sess_info = xr.SessionCreateInfo(system_id=self._system_id, next=graphics_binding)
                except TypeError:
                    try:
                        sess_info = xr.SessionCreateInfo(systemId=self._system_id, next=graphics_binding)  # type: ignore
                    except TypeError:
                        sess_info = xr.SessionCreateInfo(system_id=self._system_id, nextChain=graphics_binding)  # type: ignore
                # Use DIRECT module-level xr.create_session like working examples
                self._session = xr.create_session(instance=self._instance, create_info=sess_info)
                # Ensure session wrapper links back to instance for high-level helpers
                try:
                    if hasattr(self._session, 'instance') and getattr(self._session, 'instance', None) is None:
                        setattr(self._session, 'instance', self._instance)
                except Exception:
                    pass

            # 4) Defer space creation until AFTER begin_session (will create in SYNCHRONIZED state)
            # Creating space too early causes "invalid handle" errors in locate_views
            self._space = None
            self._logger.info("[VR] Space will be created after begin_session (in SYNCHRONIZED state)")

            # 5) Configure views/swapchains
            view_cfg = xr.ViewConfigurationType.PRIMARY_STEREO
            if self._session is not None:
                views = self._xr_enumerate_view_configuration_views(self._instance, self._system_id, view_cfg)
                self._views = views
                self._create_swapchains_with_best_format(views)
                # 6) DON'T begin session yet - must wait for READY state via event polling
                # The session will be begun when we receive SessionState::READY event
                self._logger.info("[VR] Session created; waiting for READY state before beginning")
                self._session_began = False  # Will be set to True when READY event received
                self._logger.info("[VR] OpenXR initialized: %d eyes (waiting for READY state)", len(self._swapchains))
            return True
        except Exception as e:  # pragma: no cover (environment dependent)
            self._logger.error("[VR] Failed to initialize OpenXR: %s", e)
            self._mock = True
            return False

    def ensure_initialized_with_current_context(self) -> bool:
        """If OpenXR is not fully initialized, (re)create session/swapchains using the
        currently-current GL context (Qt compositor). Returns True when a session is
        active (even if frame loop stays disabled), False if still mock/deferred.

        Safe to call frequently; will no-op if already initialized with the same WGL handles.
        """
        if not self.enabled or self._mock:
            return False
        if self._session and self._swapchains:
            return True
        # Build graphics binding from CURRENT context
        binding = self._build_opengl_binding()
        if binding is None:
            # Still no current GL context
            return False
        try:
            # Create session
            try:
                sess_info = xr.SessionCreateInfo(system_id=self._system_id, next=binding)
            except TypeError:
                try:
                    sess_info = xr.SessionCreateInfo(systemId=self._system_id, next=binding)  # type: ignore
                except TypeError:
                    sess_info = xr.SessionCreateInfo(system_id=self._system_id, nextChain=binding)  # type: ignore
            # Use DIRECT module-level xr.create_session like working examples
            self._session = xr.create_session(instance=self._instance, create_info=sess_info)
            try:
                if hasattr(self._session, 'instance') and getattr(self._session, 'instance', None) is None:
                    setattr(self._session, 'instance', self._instance)
            except Exception:
                pass
            try:
                self._logger.debug("[VR] Created session repr=%s", repr(self._session))
            except Exception:
                pass
            
            # CRITICAL: Register action manifest with SteamVR to exit loading screen
            # SteamVR requires an action manifest (even empty) to transition from loading to scene
            self._register_action_manifest()

            # Space (LOCAL - matches working script)
            self._space = self._xr_create_reference_space(
                self._session,
                xr.ReferenceSpaceType.LOCAL,
                xr.Posef(orientation=xr.Quaternionf(0, 0, 0, 1))
            )
            # Views / swapchains
            view_cfg = xr.ViewConfigurationType.PRIMARY_STEREO
            views = self._xr_enumerate_view_configuration_views(self._instance, self._system_id, view_cfg)
            self._views = views
            self._create_swapchains_with_best_format(views)
            # Begin session
            try:
                self._xr_begin_session(self._session, view_cfg)
                self._session_began = True
                self._logger.info("[VR] OpenXR session bound to current GL context; eyes=%d", len(self._swapchains))
            except Exception as e:
                self._session_began = False
                self._logger.warning("[VR] Session begun disabled (binding limitation): %s", e)
            # Clear deferred flag and mock
            self._deferred_init = False
            return True
        except Exception as e:
            self._logger.error("[VR] ensure_initialized_with_current_context failed: %s", e)
            return False

    def submit_frame_from_fbo(self, source_fbo: int, src_w: int, src_h: int) -> None:
        """Blit the given FBO into each eye's swapchain image and present.

        In mock mode, this is a no-op; otherwise, it runs the XR frame loop.
        The current OpenGL context must be current when calling this method.
        """
        if not self.enabled or self._mock:
            return
        if GL is None:  # pragma: no cover
            return
        
        # CRITICAL: Poll OpenXR events to handle session state changes
        # Must poll BEFORE checking session_began, because polling is what triggers
        # the READY state which causes session to begin
        self._poll_xr_events()
        
        # If the session did not successfully begin, do not enter the XR frame loop.
        if not self._session_began:
            # Don't log spam - event polling will trigger begin when READY
            return
        
        # NOTE: We must call wait_frame/begin_frame/end_frame even when not visible
        # because these calls can trigger further state transitions (SYNCHRONIZED -> VISIBLE -> FOCUSED)
        # Only skip rendering the actual content when not in running state
        
        try:
            # Always call wait_frame to progress state machine
            fs = self._xr_session_wait_frame(self._session)
            
            # Check if runtime wants us to render (shouldRender flag)
            should_render_flag = getattr(fs, 'shouldRender', getattr(fs, 'should_render', True))
            
            # Begin frame ONLY if we're going to submit layers
            # This avoids the begin/end imbalance when we don't have content
            if not should_render_flag:
                if not getattr(self, "_logged_wait_for_render", False):
                    self._logger.info("[VR] ⏭️ Runtime says don't render yet (shouldRender=False)")
                    self._logged_wait_for_render = True
                return
            
            # Now begin frame - from here we MUST call end_frame
            self._xr_session_begin_frame(self._session)
            
            # Check if session is in running state
            if not self._session_running:
                # Session not fully started yet - but we already called begin_frame!
                # We MUST call end_frame, but we can't submit empty layers to SteamVR
                # Solution: This shouldn't happen if shouldRender logic is correct
                if not getattr(self, "_logged_not_running", False):
                    self._logger.warning("[VR] ⚠️ begin_frame called but session not running - this may cause issues")
                    self._logged_not_running = True
                # Fall through and try to build layers anyway

            # Check if we should render and if we have images
            # If swapchain images enumerated as 0, fall back to simplified rendering like working script
            has_images = any(len(imgs) > 0 for imgs in self._swapchain_images)
            
            if not has_images:
                # Simplified path: just run frame loop without actual rendering
                # This matches the working script's approach for initial testing
                try:
                    import os as _os_dbg
                    if _os_dbg.environ.get("MESMERGLASS_VR_DEBUG_SOLID", "0") in ("1", "true", "True"):
                        if not getattr(self, "_logged_no_images", False):
                            self._logger.info("[VR] No swapchain images available; running simplified frame loop (like working script)")
                            self._logged_no_images = True
                except Exception:
                    pass
                # End frame with empty layers (working script style)
                display_time = getattr(fs, 'predictedDisplayTime', getattr(fs, 'predicted_display_time', None))
                self._xr_session_end_frame(self._session, [], display_time)
                return

            # Full rendering path with image blitting
            proj_layer = None
            
            # Locate views using module-level xr.locate_views (not session method)
            # This is what working examples use!
            view_poses = []
            
            # CRITICAL: Only try locate_views if space is valid (non-NULL handle)
            # Set _last_locate_ok flag to control layer submission
            self._last_locate_ok = False
            
            if self._space is None or not _is_valid_handle(self._space):
                if not getattr(self, "_logged_no_space", False):
                    self._logger.warning("[XR] No valid space handle - cannot call locate_views")
                    self._logged_no_space = True
            else:
                try:
                    view_cfg = xr.ViewConfigurationType.PRIMARY_STEREO
                    display_time = getattr(fs, 'predictedDisplayTime', getattr(fs, 'predicted_display_time', 0))
                    
                    # Build ViewLocateInfo with proper field names
                    # CRITICAL: Use display_time from THIS frame's wait_frame
                    view_locate_info = xr.ViewLocateInfo(
                        view_configuration_type=view_cfg,
                        display_time=display_time,
                        space=self._space
                    )
                    
                    # Call module-level xr.locate_views
                    # pyopenxr returns (view_state, views) - it's a wrapper, not raw C API
                    view_state, views = xr.locate_views(self._session, view_locate_info)
                    
                    # locate_views succeeded! Now check if position is valid
                    if hasattr(view_state, 'view_state_flags'):
                        flags = view_state.view_state_flags
                        if flags & xr.ViewStateFlags.POSITION_VALID_BIT:
                            view_poses = list(views)
                            self._last_locate_ok = True  # Mark success for layer submission
                            if not getattr(self, "_logged_locate_success", False):
                                self._logger.info("[VR] ✅ locate_views SUCCESS! Got %d views with POSITION_VALID", len(view_poses))
                                # Validate and log FOV values (SteamVR requires non-zero FOV)
                                for i, v in enumerate(views):
                                    if hasattr(v, 'fov'):
                                        fov = v.fov
                                        self._logger.info(
                                            "[VR] Eye %d FOV: left=%.3f right=%.3f up=%.3f down=%.3f",
                                            i, fov.angle_left, fov.angle_right, fov.angle_up, fov.angle_down
                                        )
                                        # Sanity check: FOV should be non-zero
                                        if abs(fov.angle_left) < 0.01 or abs(fov.angle_right) < 0.01:
                                            self._logger.warning("[VR] ⚠️ Eye %d has near-zero horizontal FOV!", i)
                                        if abs(fov.angle_up) < 0.01 or abs(fov.angle_down) < 0.01:
                                            self._logger.warning("[VR] ⚠️ Eye %d has near-zero vertical FOV!", i)
                                self._logged_locate_success = True
                        else:
                            if not getattr(self, "_logged_position_invalid", False):
                                self._logger.warning("[VR] View position not valid yet (flags=0x%X)", flags)
                                self._logged_position_invalid = True
                    else:
                        # No flags check available, just use the views
                        view_poses = list(views)
                        self._last_locate_ok = True  # Mark success for layer submission
                        if not getattr(self, "_logged_locate_success", False):
                            self._logger.info("[VR] ✅ locate_views SUCCESS! Got %d views (no flag check)", len(view_poses))
                            self._logged_locate_success = True
                            
                except Exception as e:
                    self._last_locate_ok = False
                    if not getattr(self, "_logged_locate_error", False):
                        self._logger.error("[VR] ❌ locate_views failed: %s", e)
                        self._logger.info("[XR] Will fall back to head-locked quad layer")
                        self._logged_locate_error = True

            # Acquire/Blit/Release for each eye
            proj_views = []
            for eye, (sc, w, h) in enumerate(self._swapchains):
                img_idx = self._xr_swapchain_acquire_image(sc)
                self._xr_swapchain_wait_image(sc)
                try:
                    if not getattr(self, "_logged_first_img", False):
                        self._logger.info("[VR] Eye %d acquired image index %s (%dx%d)", eye, img_idx, w, h)
                        self._logged_first_img = True
                except Exception:
                    pass
                # Get pre-enumerated GL image handle
                tex = None
                try:
                    imgs = self._swapchain_images[eye]
                    # Images in Python binding may expose `.image` or be ints
                    tex = imgs[img_idx]
                    if hasattr(tex, 'image'):
                        tex = int(tex.image)
                    else:
                        tex = int(tex)
                    
                    # CRITICAL: Verify we have a valid texture ID
                    if tex == 0 or tex is None:
                        if not getattr(self, "_logged_invalid_tex", False):
                            self._logger.error("[VR] Swapchain image is 0 or None - graphics binding not set up correctly!")
                            self._logged_invalid_tex = True
                    elif not getattr(self, "_logged_valid_tex", False):
                        self._logger.info("[VR] Valid swapchain texture ID: %d", tex)
                        self._logged_valid_tex = True
                        
                except Exception:
                    tex = None
                    try:
                        if imgs and not getattr(self, "_logged_img_type_once", False):
                            t = imgs[0]
                            self._logger.warning("[VR] Unexpected swapchain image type: %s attrs=%s", type(t), [a for a in dir(t) if not a.startswith('_')][:10])
                            self._logged_img_type_once = True
                    except Exception:
                        pass
                # Create a temporary FBO for DRAW
                draw_fbo = GL.glGenFramebuffers(1)
                GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, source_fbo)
                GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, draw_fbo)
                try:
                    if tex is not None:
                        GL.glFramebufferTexture2D(GL.GL_DRAW_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, tex, 0)
                        
                        # Check framebuffer completeness
                        status = GL.glCheckFramebufferStatus(GL.GL_DRAW_FRAMEBUFFER)
                        if status != GL.GL_FRAMEBUFFER_COMPLETE:
                            if not getattr(self, "_logged_fbo_incomplete", False):
                                self._logger.error("[VR] Framebuffer incomplete: 0x%X", status)
                                self._logged_fbo_incomplete = True
                        
                        # Optional debug fill to validate XR visibility: MESMERGLASS_VR_DEBUG_SOLID=1
                        try:
                            import os as _os_dbg
                            if _os_dbg.environ.get("MESMERGLASS_VR_DEBUG_SOLID", "0") in ("1", "true", "True"):
                                if not getattr(self, "_logged_solid", False):
                                    self._logger.info("[VR] Debug solid mode active (MESMERGLASS_VR_DEBUG_SOLID=1)")
                                    self._logged_solid = True
                                GL.glDisable(GL.GL_BLEND)
                                GL.glViewport(0, 0, int(w), int(h))
                                # Flash between bright green and bright magenta for easy visibility
                                import time as _tdbg
                                phase = int(_tdbg.perf_counter() * 2.0) % 2  # 0.5Hz flash
                                if phase == 0:
                                    GL.glClearColor(0.0, 1.0, 0.0, 1.0)  # bright green
                                else:
                                    GL.glClearColor(1.0, 0.0, 1.0, 1.0)  # bright magenta
                                GL.glClear(GL.GL_COLOR_BUFFER_BIT)
                                # CRITICAL: Ensure rendering completes before OpenXR compositor reads
                                GL.glFlush()
                                GL.glFinish()
                            else:
                                # Blit full frame from source FBO to swapchain
                                GL.glBlitFramebuffer(0, 0, int(src_w), int(src_h), 0, 0, int(w), int(h), GL.GL_COLOR_BUFFER_BIT, GL.GL_LINEAR)
                                # CRITICAL: Ensure blit completes before OpenXR compositor reads
                                GL.glFlush()
                                GL.glFinish()
                        except Exception:
                            # Fallback to blit if debug path fails
                            try:
                                GL.glBlitFramebuffer(0, 0, int(src_w), int(src_h), 0, 0, int(w), int(h), GL.GL_COLOR_BUFFER_BIT, GL.GL_LINEAR)
                                GL.glFlush()
                                GL.glFinish()
                            except Exception:
                                pass
                finally:
                    GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
                    GL.glDeleteFramebuffers(1, [draw_fbo])
                self._xr_swapchain_release_image(sc)

                # Build projection view using located views
                try:
                    if view_poses and eye < len(view_poses):
                        v = view_poses[eye]
                        sub = xr.SwapchainSubImage(swapchain=sc,
                                                   image_rect=xr.Rect2Di(offset=xr.Offset2Di(0, 0), extent=xr.Extent2Di(w, h)),
                                                   image_array_index=0)
                        pv = xr.CompositionLayerProjectionView(
                            pose=v.pose,
                            fov=v.fov,
                            sub_image=sub
                        )
                        proj_views.append(pv)
                        if not getattr(self, "_logged_proj_view", False):
                            self._logger.info("[VR] Built projection view for eye %d", eye)
                            self._logged_proj_view = True
                except Exception as e:
                    if not getattr(self, "_logged_proj_view_error", False):
                        self._logger.error("[VR] Failed to build projection view for eye %d: %s", eye, e)
                        self._logged_proj_view_error = True

            # End frame with appropriate layer type based on locate_views success
            # PROJECTION layers: stereo with head tracking (preferred)
            # QUAD layer: head-locked fallback in VIEW space (when locate_views fails)
            # 
            # CRITICAL WORKAROUND: SteamVR may require at least ONE projection layer during startup
            # to transition out of "loading" state. After startup, we can use quad layers.
            # 
            # Strategy: Submit projection layers for first N frames (startup), then switch to quad
            # Check env vars:
            # - MESMERGLASS_VR_FORCE_QUAD=1: Always use quad (for testing)
            # - MESMERGLASS_VR_STARTUP_FRAMES=N: Number of projection frames before switching (default 60)
            import os as _os_check
            force_quad = _os_check.environ.get("MESMERGLASS_VR_FORCE_QUAD", "0") in ("1", "true", "True")
            startup_frames = int(_os_check.environ.get("MESMERGLASS_VR_STARTUP_FRAMES", "60"))
            
            # Track frame count for startup transition
            if not hasattr(self, "_vr_frame_count"):
                self._vr_frame_count = 0
            self._vr_frame_count += 1
            
            # Decide whether to use projection or quad
            use_projection = (
                self._last_locate_ok and 
                view_poses and 
                len(proj_views) > 0 and 
                not force_quad and
                (self._vr_frame_count <= startup_frames or startup_frames == 0)  # 0 means always projection
            )
            
            try:
                layers = []
                
                if use_projection:
                    # ===== PROJECTION PATH (stereo with head tracking) =====
                    # CRITICAL: Set layer flags for SteamVR compositor visibility
                    # Without these flags, SteamVR treats the layer as transparent or behind the environment
                    layer_flags = (
                        XR_COMPOSITION_LAYER_BLEND_TEXTURE_SOURCE_ALPHA_BIT |
                        XR_COMPOSITION_LAYER_CORRECT_CHROMATIC_ABERRATION_BIT
                    )
                    
                    # Try to create projection layer with flags
                    try:
                        # Try flags parameter (some pyopenxr versions)
                        proj_layer = xr.CompositionLayerProjection(
                            space=self._space, 
                            views=proj_views,
                            flags=layer_flags
                        )
                    except TypeError:
                        # Fallback: try layerFlags parameter (alternate naming)
                        try:
                            proj_layer = xr.CompositionLayerProjection(
                                space=self._space, 
                                views=proj_views,
                                layerFlags=layer_flags
                            )
                        except TypeError:
                            # Last resort: create without flags and try to set directly
                            proj_layer = xr.CompositionLayerProjection(space=self._space, views=proj_views)
                            try:
                                proj_layer.flags = layer_flags
                            except AttributeError:
                                try:
                                    proj_layer.layerFlags = layer_flags
                                except AttributeError:
                                    self._logger.warning("[VR] ⚠️ Could not set layer flags - layer may be transparent in SteamVR")
                    
                    layers = [proj_layer]
                    if not getattr(self, "_logged_projection_submit", False):
                        self._logger.info("[XR] 🎯 Submitting PROJECTION layer with flags=0x%X", layer_flags)
                        self._logged_projection_submit = True
                        
                else:
                    # ===== QUAD FALLBACK PATH (head-locked, no tracking needed) =====
                    # Ensure we have a VIEW space for the quad layer
                    if self._view_space is None or not _is_valid_handle(self._view_space):
                        # Need to create VIEW space if we don't have it
                        if self._space_type != xr.ReferenceSpaceType.VIEW:
                            try:
                                pose = IDENTITY_POSE if IDENTITY_POSE else xr.Posef(
                                    orientation=xr.Quaternionf(0.0, 0.0, 0.0, 1.0),
                                    position=xr.Vector3f(0.0, 0.0, 0.0),
                                )
                                # Use proper ReferenceSpaceCreateInfo struct
                                view_create_info = xr.ReferenceSpaceCreateInfo(
                                    reference_space_type=xr.ReferenceSpaceType.VIEW,
                                    pose_in_reference_space=pose
                                )
                                self._view_space = xr.create_reference_space(
                                    self._session,
                                    view_create_info
                                )
                                if _is_valid_handle(self._view_space):
                                    self._logger.info("[XR] ✅ Created VIEW space for quad fallback")
                                else:
                                    self._logger.error("[XR] ❌ VIEW space creation returned NULL handle")
                                    self._view_space = None
                            except Exception as view_err:
                                self._logger.error("[XR] ❌ VIEW space creation failed: %s", view_err)
                                self._view_space = None
                        else:
                            # Already using VIEW space as primary
                            self._view_space = self._space
                    
                    # Submit quad layer if we have VIEW space
                    if self._view_space and _is_valid_handle(self._view_space):
                        # Use first swapchain for mono rendering
                        if self._swapchains:
                            sc, w, h = self._swapchains[0]
                            sub = xr.SwapchainSubImage(
                                swapchain=sc,
                                image_rect=xr.Rect2Di(
                                    offset=xr.Offset2Di(0, 0),
                                    extent=xr.Extent2Di(w, h)
                                ),
                                image_array_index=0
                            )
                            
                            # Pose in VIEW space (identity = centered in view)
                            pose = IDENTITY_POSE if IDENTITY_POSE else xr.Posef(
                                orientation=xr.Quaternionf(0.0, 0.0, 0.0, 1.0),
                                position=xr.Vector3f(0.0, 0.0, 0.0),
                            )
                            
                            # Size in meters (~16:9 floating screen, 1.2m wide)
                            size = xr.Extent2Df(1.2, 0.68)
                            
                            # CRITICAL: Set layer flags for SteamVR visibility (same as projection)
                            layer_flags = (
                                XR_COMPOSITION_LAYER_BLEND_TEXTURE_SOURCE_ALPHA_BIT |
                                XR_COMPOSITION_LAYER_CORRECT_CHROMATIC_ABERRATION_BIT
                            )
                            
                            # Try to create quad layer with flags
                            try:
                                quad = xr.CompositionLayerQuad(
                                    space=self._view_space,
                                    pose=pose,
                                    size=size,
                                    sub_image=sub,
                                    flags=layer_flags
                                )
                            except TypeError:
                                try:
                                    quad = xr.CompositionLayerQuad(
                                        space=self._view_space,
                                        pose=pose,
                                        size=size,
                                        sub_image=sub,
                                        layerFlags=layer_flags
                                    )
                                except TypeError:
                                    quad = xr.CompositionLayerQuad(
                                        space=self._view_space,
                                        pose=pose,
                                        size=size,
                                        sub_image=sub
                                    )
                                    try:
                                        quad.flags = layer_flags
                                    except AttributeError:
                                        pass
                            
                            layers = [quad]
                            
                            if not getattr(self, "_logged_quad_submit", False):
                                self._logger.info("[XR] 📺 Submitting QUAD layer with flags=0x%X", layer_flags)
                                self._logger.info("[XR] Quad layer: 1.2m x 0.68m centered in VIEW space")
                                self._logged_quad_submit = True
                    else:
                        # No VIEW space available, submit empty layers
                        if not getattr(self, "_logged_empty_submit", False):
                            self._logger.warning("[XR] ⚠️ VIEW space invalid - submitting empty layers")
                            self._logger.warning("[XR] Consider switching to OpenVR bindings")
                            self._logged_empty_submit = True
                
            except Exception as e:
                layers = []
                if not getattr(self, "_logged_layer_error", False):
                    self._logger.error("[XR] ❌ Layer submission failed: %s", e)
                    import traceback
                    self._logger.error("[XR] Traceback:\n%s", traceback.format_exc())
                    self._logged_layer_error = True

            display_time = getattr(fs, 'predictedDisplayTime', getattr(fs, 'predicted_display_time', None))
            
            # Log layer diagnostics before submission (once per session)
            if not getattr(self, "_logged_layer_types", False) and len(layers) > 0:
                layer_info = []
                for ly in layers:
                    layer_type = getattr(ly, 'type', 'UNKNOWN')
                    layer_info.append(str(layer_type))
                self._logger.info("[VR] Frame layers: count=%d types=%s", len(layers), layer_info)
                self._logged_layer_types = True
            
            # CRITICAL: Never call xrEndFrame with empty layers list
            # SteamVR compositor rejects frames with zero layers and stays in loading screen
            if len(layers) > 0:
                result = self._xr_session_end_frame(self._session, layers, display_time)
                # Log successful frame submission once
                if not getattr(self, "_logged_frame_success", False):
                    self._logger.info("[VR] ✅ First successful end_frame with %d layer(s) - loading screen should exit!", len(layers))
                    self._logged_frame_success = True
            else:
                # This should NEVER happen now with our restructured logic
                if not getattr(self, "_logged_skip_empty_frame", False):
                    self._logger.error("[VR] ❌ CRITICAL: Tried to call end_frame with no layers! This will break SteamVR!")
                    self._logged_skip_empty_frame = True
        except Exception as e:  # pragma: no cover
            self._logger.debug("[VR] submit_frame_from_fbo failed: %s", e)

    # ---- swapchain helpers (format selection + creation) ----
    def _create_swapchains_with_best_format(self, views) -> None:
        """Create per-eye swapchains using a runtime-supported GL format."""
        self._swapchains = []
        self._swapchain_images = []
        # Enumerate available formats if possible
        avail = []
        try:
            # Prefer module-level helper directly for clearer diagnostics
            try:
                avail = list(getattr(xr, 'enumerate_swapchain_formats')(self._session))
            except Exception:
                avail = list(self._xr_enumerate_swapchain_formats(self._session))  # type: ignore[arg-type]
        except Exception as e:
            avail = []
            try:
                self._logger.warning("[VR] enumerate_swapchain_formats failed: %s", e)
            except Exception:
                pass
        fmt = self._choose_gl_format(avail)
        try:
            self._logger.info("[VR] Using swapchain format=0x%X (avail=%s)", int(fmt),
                              ','.join([f"0x{int(x):X}" for x in (avail[:6] if avail else [])]) + ("…" if avail and len(avail) > 6 else ""))
        except Exception:
            pass
        for v in views:
            try:
                sc_info = xr.SwapchainCreateInfo(
                    usage_flags=(xr.SwapchainUsageFlags.COLOR_ATTACHMENT_BIT | xr.SwapchainUsageFlags.SAMPLED_BIT),
                    format=fmt,
                    sample_count=v.recommended_swapchain_sample_count,
                    width=v.recommended_image_rect_width,
                    height=v.recommended_image_rect_height,
                    face_count=1,
                    array_size=1,
                    mip_count=1,
                )
            except TypeError:
                # camelCase fields
                sc_info = xr.SwapchainCreateInfo(
                    usageFlags=(xr.SwapchainUsageFlags.COLOR_ATTACHMENT_BIT | xr.SwapchainUsageFlags.SAMPLED_BIT),  # type: ignore
                    format=fmt,
                    sampleCount=v.recommended_swapchain_sample_count,  # type: ignore
                    width=v.recommended_image_rect_width,
                    height=v.recommended_image_rect_height,
                    faceCount=1,  # type: ignore
                    arraySize=1,  # type: ignore
                    mipCount=1,  # type: ignore
                )
            sc = self._xr_create_swapchain(self._session, sc_info)
            # Ensure swapchain knows its instance for high-level helpers
            try:
                if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                    setattr(sc, 'instance', self._instance)
                    try:
                        if not getattr(self, "_logged_sc_instance_link", False):
                            self._logger.debug("[VR] Linked swapchain.instance to current instance for binding helpers")
                            self._logged_sc_instance_link = True
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                inst = getattr(sc, 'instance', None)
                self._logger.info("[VR] Swapchain created: type=%s instance_is_none=%s instance_type=%s",
                                  type(sc), inst is None, type(inst))
            except Exception:
                pass
            try:
                self._logger.debug("[VR] Created swapchain repr=%s", repr(sc))
            except Exception:
                pass
            self._swapchains.append((sc, sc_info.width, sc_info.height))
            # Pre-enumerate GL images for this swapchain (OpenGL)
            try:
                imgs = self._xr_enumerate_swapchain_images(sc)
                if imgs:
                    self._logger.info("[VR] Swapchain created: type=%s instance_is_none=%s instance_type=%s", 
                                      type(sc), 
                                      getattr(sc, 'instance', None) is None,
                                      type(getattr(sc, 'instance', None)))
            except Exception:
                imgs = []
            self._swapchain_images.append(list(imgs))
            try:
                self._logger.info("[VR] Swapchain images enumerated: %d", len(imgs))
                if not imgs:
                    self._logger.warning("[VR] No swapchain images returned by binding; texture attach will be skipped")
            except Exception:
                pass

    def _xr_enumerate_swapchain_formats(self, session):
        """Enumerate supported swapchain GL formats for a session."""
        # Instance/session methods
        for mname in ("enumerate_swapchain_formats", "enumerateSwapchainFormats"):
            f = getattr(session, mname, None)
            if f:
                try:
                    res = f()
                    try:
                        if res and len(res) > 0:
                            return res
                    except Exception:
                        if res:
                            return res
                except Exception:
                    pass
        # Module-level variants
        for fname in ("enumerate_swapchain_formats", "xrEnumerateSwapchainFormats", "enumerateSwapchainFormats"):
            g = getattr(xr, fname, None)
            if g:
                try:
                    res = g(session)
                    try:
                        if res and len(res) > 0:
                            return res
                    except Exception:
                        if res:
                            return res
                except Exception:
                    pass
        # Function-pointer fallback
        try:
            proc = self._xr_proc('xrEnumerateSwapchainFormats', ['PFN_xrEnumerateSwapchainFormats'])
        except Exception:
            return []
        try:
            import ctypes as _ct
            sess_handle = self._enhance_handle_extraction(session)
            if sess_handle is None:
                sess_handle = self._as_xr_handle(session)  # fallback to original
            count = _ct.c_uint32(0)
            # Query count
            try:
                ret = proc(sess_handle if sess_handle else session, 0, _ct.byref(count), _ct.c_void_p())
            except Exception:
                return []
            n = int(getattr(count, 'value', 0))
            if n <= 0:
                try:
                    if not getattr(self, "_logged_zero_formats_once", False):
                        # Inspect session wrapper for clues
                        s_attrs = []
                        try:
                            s_attrs = [a for a in dir(session) if not a.startswith('_')][:20]
                        except Exception:
                            s_attrs = []
                        self._logger.info("[VR] Enhanced session handle extraction: sess_handle=%r (type=%s)", sess_handle, type(sess_handle))
                        self._logger.warning("[VR] Format count 0 via FP (ret=%r, sess_handle=%r, sess_type=%s, sess_attrs=%s)",
                                              ret if 'ret' in locals() else None, sess_handle, type(session), s_attrs)
                        self._logged_zero_formats_once = True
                except Exception:
                    pass
                return []
            # Allocate int64 array and fill
            ArrayT = _ct.c_int64 * n
            arr = ArrayT()
            try:
                ret = proc(sess_handle if sess_handle else session, n, _ct.byref(count), arr)
            except Exception:
                return []
            nn = int(getattr(count, 'value', n))
            return [int(arr[i]) for i in range(nn)]
        except Exception:
            return []

    def _choose_gl_format(self, available: list[int] | None = None) -> int:
        """Pick a runtime-supported GL color format.
        
        SteamVR compositor requires LINEAR formats (GL_RGBA8) not SRGB.
        Prefer RGBA8 (0x8058) first for SteamVR compatibility.
        If 'available' is empty/None, returns a sensible default constant.
        """
        # Preferred in order: RGBA8 (LINEAR for SteamVR), RGBA16F, SRGB8_A8
        preferred = [0x8058, 0x881A, 0x8C43]
        
        print(f"[VR] Available swapchain formats: {[hex(x) for x in (available or [])]}")
        
        if available:
            for p in preferred:
                try:
                    if int(p) in [int(x) for x in available]:
                        selected = int(p)
                        format_name = {0x8058: "GL_RGBA8", 0x881A: "GL_RGBA16F", 0x8C43: "GL_SRGB8_ALPHA8"}.get(selected, "UNKNOWN")
                        print(f"[VR] Selected swapchain format: {hex(selected)} ({format_name})")
                        return selected
                except Exception:
                    continue
            try:
                fallback = int(available[0])
                print(f"[VR] Using fallback format (first available): {hex(fallback)}")
                return fallback
            except Exception:
                pass
        # Fall back to GL_RGBA8 (LINEAR, SteamVR-compatible)
        print("[VR] Using hardcoded fallback: 0x8058 (GL_RGBA8)")
        try:
            return xr.GL_RGBA8
        except Exception:
            return 0x8058

    def _poll_xr_events(self) -> None:
        """Poll OpenXR events and handle session state changes.
        
        This is CRITICAL - without polling events, the session never transitions
        to VISIBLE/FOCUSED states and the runtime won't display our content.
        """
        if not self._instance:
            return
        
        try:
            # Poll all available events
            while True:
                try:
                    # pyopenxr poll_event takes just the instance
                    event = None
                    try:
                        poll_func = getattr(xr, 'poll_event', None)
                        if poll_func:
                            try:
                                result = poll_func(self._instance)
                                # result might be (status, event) tuple or just event
                                if isinstance(result, tuple):
                                    status, event = result[0], result[1] if len(result) > 1 else None
                                    if not getattr(self, "_logged_poll_once", False):
                                        self._logger.info("[VR] poll_event returned tuple: status=%s event=%s", status, type(event).__name__ if event else None)
                                        self._logged_poll_once = True
                                    if event is None:
                                        break  # No more events
                                else:
                                    event = result
                                    if not getattr(self, "_logged_poll_once", False):
                                        self._logger.info("[VR] poll_event returned: %s", type(event).__name__ if event else None)
                                        self._logged_poll_once = True
                                    if event is None:
                                        break
                                    # If event is EventDataBuffer, we need to cast/extract the actual event
                                    EventDataBuffer = getattr(xr, 'EventDataBuffer', None)
                                    if EventDataBuffer and isinstance(event, EventDataBuffer):
                                        # The buffer needs to be cast to the specific event type
                                        # Try to get the event type from the buffer's type field
                                        try:
                                            event_type_value = getattr(event, 'type', None)
                                            if event_type_value is not None:
                                                # Check if it's a session state changed event
                                                StructureType = getattr(xr, 'StructureType', None)
                                                if StructureType:
                                                    session_state_type = getattr(StructureType, 'TYPE_EVENT_DATA_SESSION_STATE_CHANGED', None) or \
                                                                        getattr(StructureType, 'EVENT_DATA_SESSION_STATE_CHANGED', None)
                                                    if session_state_type and int(event_type_value) == int(session_state_type):
                                                        # Cast buffer to EventDataSessionStateChanged
                                                        EventDataSessionStateChanged = getattr(xr, 'EventDataSessionStateChanged', None)
                                                        if EventDataSessionStateChanged:
                                                            try:
                                                                # Try to cast using ctypes
                                                                import ctypes
                                                                event = ctypes.cast(ctypes.pointer(event), ctypes.POINTER(EventDataSessionStateChanged)).contents
                                                                if not getattr(self, "_logged_cast_once", False):
                                                                    self._logger.info("[VR] Cast EventDataBuffer to EventDataSessionStateChanged")
                                                                    self._logged_cast_once = True
                                                            except Exception as cast_err:
                                                                if not getattr(self, "_logged_cast_error_once", False):
                                                                    self._logger.warning("[VR] Failed to cast event buffer: %s", cast_err)
                                                                    self._logged_cast_error_once = True
                                        except Exception:
                                            pass
                            except Exception as e:
                                # EventUnavailable means no more events
                                if not getattr(self, "_logged_poll_exception_once", False):
                                    self._logger.info("[VR] poll_event exception: %s", e)
                                    self._logged_poll_exception_once = True
                                exc_str = str(e)
                                exc_type = type(e).__name__
                                if 'Unavailable' in exc_type or 'EVENT_UNAVAILABLE' in exc_str or 'EventUnavailable' in exc_str:
                                    break  # Normal - no more events
                                # Other exceptions break the loop
                                break
                    except Exception as poll_err:
                        if not getattr(self, "_logged_poll_outer_exception_once", False):
                            self._logger.info("[VR] poll outer exception: %s", poll_err)
                            self._logged_poll_outer_exception_once = True
                        break  # No events available
                    
                    if event is None:
                        break  # No more events
                    
                    # Handle session state change events
                    # Check if event is EventDataSessionStateChanged type
                    is_state_change = False
                    try:
                        EventDataSessionStateChanged = getattr(xr, 'EventDataSessionStateChanged', None)
                        if EventDataSessionStateChanged and isinstance(event, EventDataSessionStateChanged):
                            is_state_change = True
                    except Exception:
                        pass
                    
                    # Fallback: check event type field
                    if not is_state_change:
                        try:
                            event_type = getattr(event, 'type', None) or getattr(event, 'event_type', None)
                            if event_type is not None:
                                # Check if type indicates session state changed
                                state_changed_type = None
                                try:
                                    # Try different naming conventions
                                    for name in ('TYPE_SESSION_STATE_CHANGED', 'SESSION_STATE_CHANGED', 'SessionStateChanged'):
                                        try:
                                            state_changed_type = getattr(xr.StructureType, name, None)
                                            if state_changed_type is not None:
                                                break
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                
                                if state_changed_type is not None:
                                    try:
                                        is_state_change = (int(event_type) == int(state_changed_type))
                                    except Exception:
                                        is_state_change = (event_type == state_changed_type)
                        except Exception:
                            pass
                    
                    if is_state_change:
                        # Extract new session state
                        new_state = None
                        try:
                            new_state = getattr(event, 'state', None) or getattr(event, 'session_state', None)
                        except Exception:
                            pass
                        
                        if new_state is not None:
                            self._handle_session_state_change(new_state)
                
                except Exception:
                    break  # Exit on any poll error
        
        except Exception as e:
            if not getattr(self, "_logged_poll_error", False):
                self._logger.warning("[VR] Event polling error: %s", e)
                self._logged_poll_error = True
    
    def _handle_session_state_change(self, new_state) -> None:
        """Handle OpenXR session state transitions."""
        try:
            old_state = self._session_state
            self._session_state = new_state
            
            # Get state name for logging
            state_name = "UNKNOWN"
            try:
                # Try to get enum name
                if hasattr(new_state, 'name'):
                    state_name = new_state.name
                else:
                    # Try SessionState enum lookup
                    SessionState = getattr(xr, 'SessionState', None)
                    if SessionState:
                        for name in dir(SessionState):
                            if not name.startswith('_'):
                                val = getattr(SessionState, name, None)
                                try:
                                    if int(val) == int(new_state):
                                        state_name = name
                                        break
                                except Exception:
                                    pass
            except Exception:
                state_name = str(new_state)
            
            self._logger.info("[VR] Session state changed: %s", state_name)
            
            # Handle READY state - need to begin session if not already begun
            try:
                SessionState = getattr(xr, 'SessionState', None)
                if SessionState:
                    ready_state = getattr(SessionState, 'READY', None) or getattr(SessionState, 'ready', None)
                    if ready_state and int(new_state) == int(ready_state):
                        # Session is READY - start it if we haven't already
                        if not self._session_began:
                            try:
                                view_cfg = xr.ViewConfigurationType.PRIMARY_STEREO
                                self._xr_begin_session(self._session, view_cfg)
                                self._session_began = True
                                # CRITICAL: Set running flag immediately so frame loop starts
                                # This is required for SteamVR to exit loading screen
                                self._session_running = True
                                self._logger.info("[VR] Began session in response to READY state - frame loop enabled")
                            except Exception as begin_err:
                                self._logger.error("[VR] Failed to begin session on READY: %s", begin_err)
            except Exception as e:
                self._logger.warning("[VR] Error handling READY state: %s", e)
            
            # Update running flag based on state
            # Session should render when in SYNCHRONIZED, VISIBLE, or FOCUSED states
            try:
                SessionState = getattr(xr, 'SessionState', None)
                if SessionState:
                    running_states = []
                    for state_name_check in ('SYNCHRONIZED', 'VISIBLE', 'FOCUSED', 
                                            'synchronized', 'visible', 'focused'):
                        state_val = getattr(SessionState, state_name_check, None)
                        if state_val is not None:
                            running_states.append(state_val)
                    
                    # Check if current state is in running states
                    self._session_running = False
                    for running_state in running_states:
                        try:
                            if int(new_state) == int(running_state):
                                self._session_running = True
                                break
                        except Exception:
                            pass
                    
                    if self._session_running:
                        self._logger.info("[VR] Session now RUNNING - will render frames")
                        
                        # CRITICAL: Create reference space when first entering SYNCHRONIZED state
                        # Using robust fallback order: LOCAL → STAGE → VIEW
                        if self._space is None:
                            try:
                                synchronized_state = getattr(SessionState, 'SYNCHRONIZED', None) or getattr(SessionState, 'synchronized', None)
                                if synchronized_state and int(new_state) == int(synchronized_state):
                                    self._logger.info("[XR] Attempting to create reference space in SYNCHRONIZED state...")
                                    self._space_type, self._space = _create_first_valid_space(
                                        self._session, xr, self._logger
                                    )
                                    
                                    if self._space is None:
                                        self._logger.error("[XR] 🚨 ALL space types returned NULL handles!")
                                        self._logger.error("[XR] This likely indicates a pyopenxr or SteamVR compatibility issue")
                                        self._logger.error("[XR] Consider using OpenVR bindings as fallback")
                                    else:
                                        space_name = self._space_type.name if hasattr(self._space_type, 'name') else str(self._space_type)
                                        self._logger.info("[XR] ✅ Using %s space for rendering", space_name)
                            except Exception as space_err:
                                self._logger.error("[XR] ❌ Space creation failed with exception: %s", space_err)
                                import traceback
                                self._logger.error("[XR] Traceback:\n%s", traceback.format_exc())
                                self._space = None
                                self._space_type = None
                    else:
                        self._logger.info("[VR] Session NOT running - frames will be skipped")
            except Exception as e:
                self._logger.warning("[VR] Could not determine if session is running: %s", e)
                # Assume running to avoid blocking rendering
                self._session_running = True
        
        except Exception as e:
            self._logger.error("[VR] Error handling session state change: %s", e)

    def shutdown(self) -> None:
        if not self.enabled or self._mock:
            return
        try:
            # Destroy swapchains, session, instance
            for sc, _, _ in list(self._swapchains):
                try:
                    sc.destroy()
                except Exception:
                    pass
            self._swapchains.clear()
            try:
                if self._space:
                    self._space.destroy()
            except Exception:
                pass
            if self._session:
                try:
                    self._xr_end_session(self._session)
                except Exception:
                    pass
                try:
                    self._session.destroy()
                except Exception:
                    pass
            if self._instance:
                try:
                    self._instance.destroy_instance()
                except Exception:
                    pass
        except Exception:
            pass

    # ----------------- helpers -----------------
    def _xr_proc(self, name: str, pfn_names: Optional[List[str]] = None):
        """Resolve an OpenXR function as a Python callable.

        Attempts in order:
        - Module-level python wrapper xr.<name>
        - xr.xrGetInstanceProcAddr / xr.get_instance_proc_addr returning callable
        - xr.xrGetInstanceProcAddr returning address + PFN_xr* type cast (if available)
        Returns a callable or raises AttributeError.
        """
        if name in self._proc_cache:
            return self._proc_cache[name]
        # 1) Direct module-level function
        f = getattr(xr, name, None)
        if callable(f):
            self._proc_cache[name] = f
            return f
        # 2) Instance proc address helpers
        gip = getattr(xr, 'xrGetInstanceProcAddr', None) or getattr(xr, 'get_instance_proc_addr', None) or getattr(xr, 'getInstanceProcAddr', None)
        if gip is not None:
            try:
                # Try common call styles
                for nm in (name, name.encode() if isinstance(name, str) else name):
                    try:
                        fn = gip(self._instance, nm)  # some bindings return a callable
                        if callable(fn):
                            self._proc_cache[name] = fn
                            return fn
                    except Exception:
                        pass
                # Try to retrieve raw address (int/ctypes c_void_p)
                try:
                    addr = gip(self._instance, name)
                except Exception:
                    try:
                        addr = gip(self._instance, name.encode())
                    except Exception:
                        addr = None
                if addr:
                    # Cast using PFN type if present on binding
                    if pfn_names is None:
                        pfn_names = [f'PFN_{name}']
                    for pfn in pfn_names:
                        PT = getattr(xr, pfn, None)
                        if PT is not None:
                            try:
                                # PT may be a ctypes CFUNCTYPE; attempt to cast
                                import ctypes as _ct
                                cfunc = _ct.cast(int(addr), PT)
                                if callable(cfunc):
                                    self._proc_cache[name] = cfunc
                                    return cfunc
                            except Exception:
                                continue
                    # As a last resort, define a prototype for known functions
                    try:
                        import ctypes as _ct
                        # Guessed prototypes for specific functions we use
                        if name == 'xrEnumerateSwapchainImages':
                            Proto = _ct.CFUNCTYPE(_ct.c_int32, _ct.c_void_p, _ct.c_uint32, _ct.POINTER(_ct.c_uint32), _ct.c_void_p)
                            cfunc = Proto(int(addr))
                            self._proc_cache[name] = cfunc
                            return cfunc
                        if name == 'xrEnumerateSwapchainFormats':
                            Proto = _ct.CFUNCTYPE(_ct.c_int32, _ct.c_void_p, _ct.c_uint32, _ct.POINTER(_ct.c_uint32), _ct.POINTER(_ct.c_int64))
                            cfunc = Proto(int(addr))
                            self._proc_cache[name] = cfunc
                            return cfunc
                    except Exception:
                        pass
            except Exception:
                pass
        raise AttributeError(f"Unable to resolve OpenXR proc {name}")

    # --- low-level helpers for interop with function-pointer paths ---
    def _as_xr_handle(self, obj):
        """Coerce a Python binding wrapper (Session/Swapchain) into a raw handle.

        Tries common attributes seen across bindings: handle, value, ptr, _ptr,
    _handle, _as_parameter_, c_void_p, contents, and int(obj) fallback. Returns int or None.
        """
        try:
            if obj is None:
                return None
            # Helper to unwrap nested/callable attributes until we can int() it
            def _extract(v, depth=0):
                if v is None or depth > 4:
                    return None
                # Direct ints
                if isinstance(v, int):
                    return v
                # ctypes pointer-like
                try:
                    import ctypes as _ct
                    if isinstance(v, _ct.c_void_p):
                        return int(v.value) if v.value else None
                    # If this is a ctypes pointer, try to read its value
                    # v.contents may hold a simple value type representing the handle
                    try:
                        if hasattr(v, 'contents'):
                            c = v.contents
                            # allow direct int() on contents for odd wrappers
                            try:
                                return int(c)
                            except Exception:
                                pass
                            # common simple types expose .value
                            if hasattr(c, 'value'):
                                return int(c.value)
                            # fallback: try casting to uint64 and deref
                            try:
                                ptr = _ct.cast(v, _ct.POINTER(_ct.c_uint64))
                                return int(ptr.contents.value)
                            except Exception:
                                pass
                            # try reading likely-named fields on contents
                            for nm in ('handle', 'value', 'ptr', '_ptr', 'h', 'raw'):
                                try:
                                    if hasattr(c, nm):
                                        vv = getattr(c, nm)
                                        if isinstance(vv, _ct.c_void_p):
                                            return int(vv.value) if vv.value else None
                                        try:
                                            return int(vv)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                    except Exception:
                        pass
                except Exception:
                    pass
                # callable: try call
                try:
                    if callable(v):
                        return _extract(v(), depth + 1)
                except Exception:
                    pass
                # common nested fields
                for nm in ("value", "handle", "ptr", "_ptr", "_handle", "as_parameter", "_as_parameter_", "h", "raw", "contents", "instance"):
                    try:
                        if hasattr(v, nm):
                            return _extract(getattr(v, nm), depth + 1)
                    except Exception:
                        continue
                # last resort cast
                try:
                    return int(v)
                except Exception:
                    return None

            # First try direct int(obj)
            try:
                return int(obj)
            except Exception:
                pass
            # Try well-known attribute names on the object itself
            for name in ("handle", "value", "ptr", "_ptr", "handle_value", "h", "raw", "contents", "instance", "_handle", "_as_parameter_"):
                try:
                    if hasattr(obj, name):
                        out = _extract(getattr(obj, name))
                        if isinstance(out, int):
                            return out
                except Exception:
                    continue
            # Broad scan for likely int-like attributes to catch odd bindings (one-time best effort)
            try:
                for name in dir(obj):
                    if any(tok in name.lower() for tok in ("handle", "value", "ptr", "swap", "session", "content", "instance")):
                        try:
                            out = _extract(getattr(obj, name))
                            if isinstance(out, int):
                                return out
                        except Exception:
                            continue
            except Exception:
                pass
            # Special-case: ctypes pointer-ish wrappers often expose .contents
            try:
                import ctypes as _ct
                if hasattr(obj, 'contents'):
                    c = obj.contents
                    # try a straightforward int() on contents
                    try:
                        return int(c)
                    except Exception:
                        pass
                    if hasattr(c, 'value'):
                        return int(c.value)
                    try:
                        ptr = _ct.cast(obj, _ct.POINTER(_ct.c_uint64))
                        return int(ptr.contents.value)
                    except Exception:
                        pass
                    # As another fallback, try to read typical fields on contents
                    for nm in ('handle', 'value', 'ptr', '_ptr', 'h', 'raw'):
                        try:
                            if hasattr(c, nm):
                                vv = getattr(c, nm)
                                if isinstance(vv, _ct.c_void_p):
                                    return int(vv.value) if vv.value else None
                                try:
                                    return int(vv)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                # As a final attempt, cast object itself to void* and use its integer value
                try:
                    # Try direct void* attribute if present
                    vp = _ct.c_void_p.from_buffer(obj) if hasattr(obj, '__buffer__') else _ct.cast(obj, _ct.c_void_p)
                    if vp and getattr(vp, 'value', None):
                        return int(vp.value)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            return None
        return None
    def _create_instance_compat(self, xr, app_info, exts):
        """Create an OpenXR instance across binding variants.

        Tries multiple signatures and struct styles seen in different Python bindings.
        """
        last_err = None
        # Variant A: keyword args (snake_case)
        try:
            inst = xr.create_instance(application_info=app_info, enabled_extension_names=list(exts))
            self._logger.debug("[VR] create_instance: kw snake_case")
            return inst
        except Exception as e:
            last_err = e
        # Variant B: positional
        try:
            inst = xr.create_instance(app_info, list(exts))
            self._logger.debug("[VR] create_instance: positional")
            return inst
        except Exception as e:
            last_err = e

        # Variant C: InstanceCreateInfo struct (snake_case)
        if hasattr(xr, 'InstanceCreateInfo'):
            try:
                ici = xr.InstanceCreateInfo(
                    application_info=app_info,
                    enabled_extension_names=list(exts),
                    enabled_api_layer_names=[],
                )
                try:
                    inst = xr.create_instance(ici)
                    self._logger.debug("[VR] create_instance: InstanceCreateInfo positional")
                    return inst
                except TypeError:
                    inst = xr.create_instance(instance_create_info=ici)  # type: ignore
                    self._logger.debug("[VR] create_instance: InstanceCreateInfo kw")
                    return inst
            except Exception as e:
                last_err = e
            # Variant D: InstanceCreateInfo camelCase
            try:
                ici = xr.InstanceCreateInfo(
                    applicationInfo=app_info,
                    enabledExtensionNames=list(exts),
                    enabledApiLayerNames=[],
                )
                try:
                    inst = xr.create_instance(ici)
                    self._logger.debug("[VR] create_instance: InstanceCreateInfo camel positional")
                    return inst
                except TypeError:
                    inst = xr.create_instance(instanceCreateInfo=ici)  # type: ignore
                    self._logger.debug("[VR] create_instance: InstanceCreateInfo camel kw")
                    return inst
            except Exception as e:
                last_err = e

        # If we reached here, propagate the most recent error
        if last_err is not None:
            raise last_err
        raise RuntimeError("create_instance compatibility failed with unknown error")
    def _build_opengl_binding(self):
        """Build a platform-specific OpenGL graphics binding struct.

        Returns the binding or None if not possible.
        """
        try:
            import sys
            if sys.platform != 'win32':
                return None
            # Obtain native WGL handles from current context
            # Ensure a GL context is current before calling this.
            import ctypes
            wgl = ctypes.windll.opengl32
            # Ensure correct pointer-sized return types; default c_int can corrupt handles
            try:
                wgl.wglGetCurrentContext.restype = ctypes.c_void_p
                wgl.wglGetCurrentDC.restype = ctypes.c_void_p
            except Exception:
                pass
            hglrc = wgl.wglGetCurrentContext()
            hdc = wgl.wglGetCurrentDC()
            if not hglrc or not hdc:
                # Attempt to make any Qt context current is up to caller
                self._logger.warning("[VR] WGL handles not available (no current context)")
                return None
            try:
                import ctypes as _ct
                # Normalize to unsigned pointer-sized integers to avoid negative repr
                self._wgl_hdc = int(_ct.c_void_p(hdc).value or 0)
                self._wgl_hglrc = int(_ct.c_void_p(hglrc).value or 0)
                self._logger.info("[VR] WGL current hdc=0x%X hglrc=0x%X", self._wgl_hdc, self._wgl_hglrc)
            except Exception:
                pass
            # Build OpenXR Win32 GL binding with multiple fallbacks
            def _stype_val():
                # Try to obtain a structure type constant if required by the binding
                for path in (
                    ("StructureType", "GRAPHICS_BINDING_OPENGL_WIN32_KHR"),
                    ("StructureType", "GRAPHICSBINDINGOPENGLWIN32KHR"),
                    (None, "TYPE_GRAPHICS_BINDING_OPENGL_WIN32_KHR"),
                    (None, "XR_TYPE_GRAPHICS_BINDING_OPENGL_WIN32_KHR"),
                ):
                    enum, name = path
                    try:
                        if enum:
                            et = getattr(xr, enum, None)
                            if et is not None:
                                return getattr(et, name)
                        else:
                            return getattr(xr, name)
                    except Exception:
                        continue
                return None

            # Use unsigned pointer values consistently
            try:
                import ctypes as _ct
                dch = int(_ct.c_void_p(hdc).value or 0)
                rc = int(_ct.c_void_p(hglrc).value or 0)
            except Exception:
                dch = int(hdc)
                rc = int(hglrc)
            attempts = []
            # kwargs (camelCase)
            attempts.append(("kw_hDC_hGLRC", lambda: xr.GraphicsBindingOpenGLWin32KHR(hDC=dch, hGLRC=rc)))
            # kwargs (snake_case)
            attempts.append(("kw_hdc_hglrc", lambda: xr.GraphicsBindingOpenGLWin32KHR(hdc=dch, hglrc=rc)))  # type: ignore
            # kwargs (snake_with_underscore like working sample scripts)
            # Many wheels expose parameters as h_dc/h_glrc; include these explicitly.
            attempts.append(("kw_h_dc_h_glrc", lambda: xr.GraphicsBindingOpenGLWin32KHR(h_dc=dch, h_glrc=rc)))  # type: ignore
            # kwargs with sType/next
            st = _stype_val()
            if st is not None:
                attempts.append((
                    "kw_with_type_camel",
                    lambda: xr.GraphicsBindingOpenGLWin32KHR(type=st, next=None, hDC=dch, hGLRC=rc)
                ))
                attempts.append((
                    "kw_with_type_snake",
                    lambda: xr.GraphicsBindingOpenGLWin32KHR(type=st, next=None, hdc=dch, hglrc=rc)  # type: ignore
                ))
                attempts.append((
                    "kw_with_type_snake_underscore",
                    lambda: xr.GraphicsBindingOpenGLWin32KHR(type=st, next=None, h_dc=dch, h_glrc=rc)  # type: ignore
                ))
            # positional (common order: hDC, hGLRC)
            attempts.append(("pos_hDC_hGLRC", lambda: xr.GraphicsBindingOpenGLWin32KHR(dch, rc)))
            # positional reversed (defensive)
            attempts.append(("pos_hGLRC_hDC", lambda: xr.GraphicsBindingOpenGLWin32KHR(rc, dch)))
            # empty then attribute assign
            def _empty_then_set():
                obj = xr.GraphicsBindingOpenGLWin32KHR()
                ok = False
                for n, v in (("hDC", dch), ("hGLRC", rc)):
                    try:
                        setattr(obj, n, v)
                        ok = True
                    except Exception:
                        pass
                for n, v in (("hdc", dch), ("hglrc", rc)):
                    try:
                        setattr(obj, n, v)
                        ok = True
                    except Exception:
                        pass
                for n, v in (("h_dc", dch), ("h_glrc", rc)):
                    try:
                        setattr(obj, n, v)
                        ok = True
                    except Exception:
                        pass
                if not ok:
                    raise TypeError("no writable fields on GraphicsBindingOpenGLWin32KHR")
                return obj
            attempts.append(("empty_then_set", _empty_then_set))

            last_err = None
            for label, ctor in attempts:
                try:
                    binding = ctor()
                    self._logger.debug("[VR] GraphicsBindingOpenGLWin32KHR via %s", label)
                    return binding
                except Exception as e:
                    last_err = e
                    continue
            self._logger.error("[VR] Failed to construct GraphicsBindingOpenGLWin32KHR: %s", last_err)
            return None
        except Exception as e:
            self._logger.error("[VR] _build_opengl_binding error: %s", e)
            return None

    

    def _xr_get_opengl_graphics_requirements(self, instance, system_id):
        """Get OpenGL graphics requirements (required before session creation)."""
        # Instance method
        for mname in ("get_opengl_graphics_requirements_khr", "getOpenGLGraphicsRequirementsKHR", "get_opengl_graphics_requirements"):
            f = getattr(instance, mname, None)
            if f:
                try:
                    return f(system_id)
                except Exception:
                    pass
        # Module-level function
        for fname in ("get_opengl_graphics_requirements_khr", "xr_get_opengl_graphics_requirements_khr", "xrGetOpenGLGraphicsRequirementsKHR"):
            g = getattr(xr, fname, None)
            if g:
                try:
                    return g(instance, system_id)
                except Exception:
                    pass
        # Not fatal if missing, but warn
        raise AttributeError("OpenXR binding lacks get_opengl_graphics_requirements_khr")

    def _enhance_handle_extraction(self, obj):
        """Enhanced handle extraction based on working script patterns."""
        try:
            if obj is None:
                return None
            # Direct int conversion
            try:
                return int(obj)
            except:
                pass
            # For xr.typedefs Handle types, try common patterns from working scripts
            if hasattr(obj, 'contents'):
                try:
                    # Try contents.handle first (common in ctypes wrappers)
                    if hasattr(obj.contents, 'handle'):
                        return int(obj.contents.handle)
                    # Try contents._handle
                    if hasattr(obj.contents, '_handle'):
                        return int(obj.contents._handle)
                    # Try direct int(contents)
                    return int(obj.contents)
                except:
                    pass
            # Try obj._handle pattern
            if hasattr(obj, '_handle'):
                try:
                    return int(obj._handle)
                except:
                    pass
            # Try obj.handle pattern
            if hasattr(obj, 'handle'):
                try:
                    return int(obj.handle)
                except:
                    pass
            # Working script style: get memory address of object
            try:
                import ctypes as _ct
                return _ct.addressof(obj)
            except:
                pass
            # Last resort: existing extraction logic
            return self._as_xr_handle(obj)
        except:
            return None

    def _xr_get_system(self, instance, sys_get_info):
        """Call get_system via instance method or module-level function."""
        try:
            return instance.get_system(sys_get_info)
        except Exception:
            pass
        # Module-level fallback names
        for fname in ("get_system", "xr_get_system", "xrGetSystem", "getSystem"):
            f = getattr(xr, fname, None)
            if f:
                try:
                    return f(instance, sys_get_info)
                except Exception:
                    continue
        raise AttributeError("OpenXR binding lacks get_system")

    def _xr_create_session(self, instance, sess_info):
        """Create session via instance method or module-level function."""
        # 1) Instance method
        try:
            return instance.create_session(sess_info)
        except Exception:
            pass
        # 2) Module function variants with multiple calling conventions
        fn_names = ("create_session", "xr_create_session", "xrCreateSession", "createSession")
        for fname in fn_names:
            f = getattr(xr, fname, None)
            if not f:
                continue
            # a) (instance, sess_info)
            try:
                return f(instance, sess_info)
            except Exception:
                pass
            # b) (sess_info, instance)
            try:
                return f(sess_info, instance)
            except Exception:
                pass
            # c) keyword forms
            for kwargs in (
                dict(instance=instance, session_create_info=sess_info),
                dict(instance=instance, create_info=sess_info),
                dict(instance=instance, info=sess_info),
                dict(inst=instance, info=sess_info),
            ):
                try:
                    return f(**kwargs)
                except Exception:
                    pass
        # 3) Direct Session class constructor
        Sess = getattr(xr, 'Session', None)
        if Sess is not None:
            # Try positional and keyword patterns
            try:
                return Sess(instance, sess_info)
            except Exception:
                pass
            for kwargs in (
                dict(instance=instance, session_create_info=sess_info),
                dict(instance=instance, create_info=sess_info),
                dict(instance=instance, info=sess_info),
            ):
                try:
                    return Sess(**kwargs)
                except Exception:
                    pass
        raise AttributeError("OpenXR binding lacks create_session")

    def _xr_enumerate_view_configuration_views(self, instance, system_id, view_cfg):
        """Enumerate views via instance method or module-level function."""
        try:
            return instance.enumerate_view_configuration_views(system_id, view_cfg)
        except Exception:
            pass
        for fname in ("enumerate_view_configuration_views", "xr_enumerate_view_configuration_views", "xrEnumerateViewConfigurationViews", "enumerateViewConfigurationViews"):
            f = getattr(xr, fname, None)
            if f:
                try:
                    return f(instance, system_id, view_cfg)
                except Exception:
                    continue
        raise AttributeError("OpenXR binding lacks enumerate_view_configuration_views")

    def _setup_action_manifest_path(self):
        """Set environment variable for SteamVR to find the action manifest.
        
        SteamVR looks for STEAMVR_ACTION_MANIFEST_PATH to determine if an app
        is interactive and ready to show content.
        """
        try:
            import os
            import pathlib
            
            # Find actions.json in vr/registration directory
            manifest_path = pathlib.Path(__file__).parent / "registration" / "actions.json"
            
            if manifest_path.exists():
                # Set environment variable for SteamVR
                manifest_str = str(manifest_path.absolute())
                os.environ['STEAMVR_ACTION_MANIFEST_PATH'] = manifest_str
                self._logger.info("[VR] ✅ Set STEAMVR_ACTION_MANIFEST_PATH=%s", manifest_str)
            else:
                self._logger.warning("[VR] ⚠️ actions.json not found at %s", manifest_path)
        except Exception as e:
            self._logger.debug("[VR] Failed to set action manifest path: %s", e)

    def _register_action_manifest(self):
        """Register action manifest with SteamVR to signal app is ready for scene rendering.
        
        SteamVR requires an action manifest (even if empty) to transition from loading screen
        to actual scene rendering. Without this, the compositor stays in loading grid forever.
        """
        try:
            import os
            import pathlib
            
            # Find actions.json in vr/registration directory
            manifest_path = pathlib.Path(__file__).parent / "registration" / "actions.json"
            
            if not manifest_path.exists():
                self._logger.warning("[VR] ⚠️ actions.json not found at %s - SteamVR may stay in loading screen", manifest_path)
                return
            
            # Create a minimal action set to satisfy SteamVR
            try:
                # Try to create action set (pyopenxr style)
                ActionSetCreateInfo = getattr(xr, 'ActionSetCreateInfo', None)
                if ActionSetCreateInfo is not None:
                    action_set_info = ActionSetCreateInfo(
                        action_set_name="default",
                        localized_action_set_name="Default",
                        priority=0
                    )
                    # Try various method names
                    for method_name in ('create_action_set', 'createActionSet'):
                        create_fn = getattr(self._instance, method_name, None)
                        if create_fn:
                            try:
                                action_set = create_fn(action_set_info)
                                self._logger.info("[VR] ✅ Created action set for SteamVR manifest")
                                
                                # Attach action sets to session (even if empty)
                                SessionActionSetsAttachInfo = getattr(xr, 'SessionActionSetsAttachInfo', None)
                                if SessionActionSetsAttachInfo is not None:
                                    attach_info = SessionActionSetsAttachInfo(
                                        action_sets=[action_set]
                                    )
                                    for attach_method in ('attach_session_action_sets', 'attachSessionActionSets'):
                                        attach_fn = getattr(self._session, attach_method, None) or getattr(xr, attach_method, None)
                                        if attach_fn:
                                            try:
                                                if hasattr(attach_fn, '__self__'):
                                                    # Instance method
                                                    attach_fn(attach_info)
                                                else:
                                                    # Module-level function
                                                    attach_fn(self._session, attach_info)
                                                self._logger.info("[VR] ✅ Attached action sets to session - SteamVR should exit loading screen")
                                                return
                                            except Exception as e:
                                                self._logger.debug("[VR] attach_session_action_sets failed: %s", e)
                                                continue
                                break
                            except Exception as e:
                                self._logger.debug("[VR] create_action_set failed: %s", e)
                                continue
                
                # If action set creation failed, just log that we have the manifest file
                # SteamVR may still pick it up via environment variable
                self._logger.info("[VR] Action manifest exists at %s", manifest_path)
                self._logger.info("[VR] Set STEAMVR_ACTION_MANIFEST_PATH env var if loading screen persists")
                
            except Exception as e:
                self._logger.debug("[VR] Action set creation attempt failed: %s", e)
                
        except Exception as e:
            self._logger.warning("[VR] Failed to register action manifest: %s", e)

    def _xr_create_reference_space(self, session, ref_space_type, pose):
        """Create a reference space using various binding styles."""
        # Build alternative representations for pose
        pose_variants = []
        try:
            # Ensure position is set if supported by binding
            V3 = getattr(xr, 'Vector3f', None)
            if V3 is not None and hasattr(pose, 'position') and getattr(pose, 'position') is None:
                pose2 = xr.Posef(position=V3(0.0, 0.0, 0.0), orientation=pose.orientation)
                pose_variants.append(pose2)
        except Exception:
            pass
        # Dict-based pose variant (for bindings that accept mapping)
        try:
            q = getattr(pose, 'orientation', None)
            if q is not None and hasattr(q, 'x'):
                pos_dict = dict(x=0.0, y=0.0, z=0.0)
                ori_dict = dict(x=float(q.x), y=float(q.y), z=float(q.z), w=float(q.w))
                pose_variants.append(dict(position=pos_dict, orientation=ori_dict))
        except Exception:
            pass
        if not pose_variants:
            pose_variants = [pose]

        # Build a robust pose with position + orientation if available
        try:
            zero = getattr(xr, 'Vector3f', None)
            if zero is not None and hasattr(pose, 'position') and getattr(pose, 'position') is None:
                pose = xr.Posef(position=zero(0.0, 0.0, 0.0), orientation=pose.orientation)
        except Exception:
            pass

        # Instance methods: try several name variants
        for mname in ("create_reference_space", "createReferenceSpace", "create_space", "createSpace"):
            f = getattr(session, mname, None)
            if not f:
                continue
            # snake/camel kwargs
            for pv in pose_variants:
                try:
                    return f(reference_space_type=ref_space_type, pose_in_reference_space=pv)
                except Exception:
                    pass
                try:
                    return f(referenceSpaceType=ref_space_type, poseInReferenceSpace=pv)  # type: ignore
                except Exception:
                    pass
                # positional
                try:
                    return f(ref_space_type, pv)
                except Exception:
                    pass

        # Construct create info struct
        create_infos = []
        if hasattr(xr, 'ReferenceSpaceCreateInfo'):
            try:
                for pv in pose_variants:
                    create_infos.append(xr.ReferenceSpaceCreateInfo(
                        reference_space_type=ref_space_type,
                        pose_in_reference_space=pv,
                    ))
            except Exception:
                pass
            try:
                for pv in pose_variants:
                    create_infos.append(xr.ReferenceSpaceCreateInfo(
                        referenceSpaceType=ref_space_type,  # type: ignore
                        poseInReferenceSpace=pv,  # type: ignore
                    ))
            except Exception:
                pass
        # Try constructing a Space/ReferenceSpace class directly
        for clsname in ("Space", "ReferenceSpace"):
            Cls = getattr(xr, clsname, None)
            if Cls is not None:
                # Try positional
                for pv in pose_variants:
                    try:
                        return Cls(session, ref_space_type, pv)
                    except Exception:
                        pass
                    # Keyword variants
                    for kwargs in (
                        dict(session=session, reference_space_type=ref_space_type, pose_in_reference_space=pv),
                        dict(session=session, referenceSpaceType=ref_space_type, poseInReferenceSpace=pv),
                        dict(sess=session, type=ref_space_type, pose=pv),
                    ):
                        try:
                            return Cls(**kwargs)
                        except Exception:
                            pass

        # Module-level functions with various arg orders and names
        fn_names = (
            "create_reference_space", "xr_create_reference_space", "xrCreateReferenceSpace", "createReferenceSpace",
            "create_space", "xrCreateSpace", "createSpace",
        )
        for info in create_infos or [None]:
            for fname in fn_names:
                f = getattr(xr, fname, None)
                if not f:
                    continue
                # a) (session, info)
                if info is not None:
                    try:
                        return f(session, info)
                    except Exception:
                        pass
                # b) keywords
                try:
                    kwargs = {}
                    if info is not None:
                        # Try common kw names
                        for key in ("create_info", "space_create_info", "reference_space_create_info", "info",
                                    "createInfo", "spaceCreateInfo", "referenceSpaceCreateInfo"):
                            kwargs = {"session": session, key: info}
                            try:
                                return f(**kwargs)
                            except Exception:
                                continue
                    else:
                        # Try direct kwargs without create info struct
                        for sesskey in ("session", "sess"):
                            for a, b in (
                                ("reference_space_type", "pose_in_reference_space"),
                                ("referenceSpaceType", "poseInReferenceSpace"),
                                ("type", "pose"),
                            ):
                                for pv in pose_variants:
                                    kwargs = {sesskey: session, a: ref_space_type, b: pv}
                                    try:
                                        return f(**kwargs)
                                    except Exception:
                                        continue
                except Exception:
                    pass
                # c) positional (session, ref_space_type, pose)
                for pv in pose_variants:
                    try:
                        return f(session, ref_space_type, pv)
                    except Exception:
                        pass
        # Emit some diagnostic to help identify symbols in this binding
        try:
            mod_syms = [n for n in dir(xr) if ("space" in n.lower() or "Space" in n)]
            sess_syms = [n for n in dir(session) if ("space" in n.lower() or "Space" in n)]
            self._logger.debug("[VR] Binding symbols (module contains): %s", ', '.join(sorted(mod_syms)[:40]))
            self._logger.debug("[VR] Binding symbols (session contains): %s", ', '.join(sorted(sess_syms)[:40]))
        except Exception:
            pass
        raise AttributeError("OpenXR binding lacks create_reference_space")

    def _xr_create_swapchain(self, session, sc_info):
        """Create a swapchain via module function or instance method with various signatures.

        Prefer module-level creation first to ensure pyopenxr wires `swapchain.instance` properly.
        """
        # Module-level functions (preferred)
        fn_names = ("create_swapchain", "xr_create_swapchain", "xrCreateSwapchain", "createSwapchain",
                    "create_swap_chain", "xrCreateSwapChain", "createSwapChain")
        for fname in fn_names:
            f = getattr(xr, fname, None)
            if not f:
                continue
            # a) (session, sc_info)
            try:
                sc = f(session, sc_info)
                # Best-effort: ensure instance linkage for later helper calls
                try:
                    if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                        setattr(sc, 'instance', self._instance)
                except Exception:
                    pass
                return sc
            except Exception:
                pass
            # b) (sc_info, session)
            try:
                sc = f(sc_info, session)
                try:
                    if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                        setattr(sc, 'instance', self._instance)
                except Exception:
                    pass
                return sc
            except Exception:
                pass
            # c) keyword forms
            for kwargs in (
                dict(session=session, create_info=sc_info),
                dict(session=session, swapchain_create_info=sc_info),
                dict(session=session, swap_chain_create_info=sc_info),
                dict(sess=session, info=sc_info),
                dict(sess=session, createInfo=sc_info),
                dict(session=session, swapchainCreateInfo=sc_info),
            ):
                try:
                    sc = f(**kwargs)
                    try:
                        if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                            setattr(sc, 'instance', self._instance)
                    except Exception:
                        pass
                    return sc
                except Exception:
                    pass
        # Instance method (fallback)
        for mname in ("create_swapchain", "createSwapchain", "create_swap_chain", "createSwapChain"):
            f = getattr(session, mname, None)
            if not f:
                continue
            try:
                sc = f(sc_info)
                try:
                    if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                        setattr(sc, 'instance', self._instance)
                except Exception:
                    pass
                return sc
            except Exception:
                pass
        # Class constructor fallback
        for clsname in ("Swapchain", "SwapChain"):
            C = getattr(xr, clsname, None)
            if C is None:
                continue
            # Positional
            try:
                sc = C(session, sc_info)
                try:
                    if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                        setattr(sc, 'instance', self._instance)
                except Exception:
                    pass
                return sc
            except Exception:
                pass
            # Keyword variants
            for kwargs in (
                dict(session=session, create_info=sc_info),
                dict(session=session, swapchain_create_info=sc_info),
                dict(sess=session, info=sc_info),
                dict(session=session, createInfo=sc_info),
            ):
                try:
                    sc = C(**kwargs)
                    try:
                        if hasattr(sc, 'instance') and getattr(sc, 'instance', None) is None:
                            setattr(sc, 'instance', self._instance)
                    except Exception:
                        pass
                    return sc
                except Exception:
                    pass
        # Emit diagnostic symbols once
        try:
            mod_syms = [n for n in dir(xr) if ("swap" in n.lower())]
            sess_syms = [n for n in dir(session) if ("swap" in n.lower())]
            self._logger.debug("[VR] Binding symbols (module swap*): %s", ', '.join(sorted(mod_syms)[:40]))
            self._logger.debug("[VR] Binding symbols (session swap*): %s", ', '.join(sorted(sess_syms)[:40]))
        except Exception:
            pass
        raise AttributeError("OpenXR binding lacks create_swapchain")

    def _xr_enumerate_swapchain_images(self, swapchain):
        """Enumerate swapchain images via method or module functions.

        Only returns early if a method yields a non-empty result; otherwise
        falls back to the function-pointer path that fills typed arrays.
        """
        for mname in ("enumerate_images", "enumerateImages", "get_images", "getImages"):
            f = getattr(swapchain, mname, None)
            if not f:
                continue
            try:
                res = f()
                try:
                    if res and len(res) > 0:
                        return res
                except Exception:
                    if res:
                        return res
            except Exception:
                pass
        # Prefer high-level binding helper that accepts element type
        # xr.enumerate_swapchain_images(swapchain, xr.SwapchainImageOpenGLKHR)
        for fname in ("enumerate_swapchain_images", "enumerateSwapchainImages"):
            f = getattr(xr, fname, None)
            if not f:
                continue
            try:
                ImgCls = getattr(xr, 'SwapchainImageOpenGLKHR', None)
                if ImgCls is not None:
                    # Try keywords then positional
                    try:
                        imgs = f(swapchain=swapchain, element_type=ImgCls)
                    except Exception:
                        imgs = f(swapchain, ImgCls)
                    # Convert to image ids if present
                    out = []
                    try:
                        for it in imgs:
                            try:
                                out.append(int(getattr(it, 'image')))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if out:
                        return out
                # Fallback: try OpenGLES variant (some bindings/platforms)
                ImgGLES = getattr(xr, 'SwapchainImageOpenGLESKHR', None)
                if ImgGLES is not None:
                    try:
                        imgs = f(swapchain=swapchain, element_type=ImgGLES)
                    except Exception:
                        imgs = f(swapchain, ImgGLES)
                    out = []
                    try:
                        for it in imgs:
                            try:
                                out.append(int(getattr(it, 'image')))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if out:
                        return out
                # As a last resort, if we got a non-empty sequence, return it raw
                try:
                    if imgs:
                        return imgs
                except Exception:
                    pass
            except Exception as e:
                try:
                    self._logger.warning("[VR] enumerate_swapchain_images via binding failed: %s", e)
                except Exception:
                    pass
                # continue to fallback
        # Fallback: use raw proc with typed array for OpenGL images (XR_KHR_opengl_enable)
        try:
            proc = self._xr_proc('xrEnumerateSwapchainImages', ['PFN_xrEnumerateSwapchainImages'])
        except Exception:
            return []
        try:
            import ctypes as _ct
            sc_handle = self._enhance_handle_extraction(swapchain)
            if sc_handle is None:
                sc_handle = self._as_xr_handle(swapchain)  # fallback to original
            count = _ct.c_uint32(0)
            # 1) Query count
            try:
                ret = proc(sc_handle if sc_handle else swapchain, 0, _ct.byref(count), _ct.c_void_p())
            except Exception:
                return []
            n = int(getattr(count, 'value', 0))
            if n <= 0:
                try:
                    if not getattr(self, "_logged_zero_imgs_once", False):
                        # Basic introspection of wrapper object to help mapping
                        attrs = []
                        c_typ = None
                        c_attrs = []
                        c_val = None
                        inst_typ = None
                        inst_attrs = []
                        try:
                            attrs = [a for a in dir(swapchain) if not a.startswith('_')][:20]
                        except Exception:
                            attrs = []
                        # Inspect .contents if present
                        try:
                            c = getattr(swapchain, 'contents')
                            try:
                                c_typ = type(c)
                            except Exception:
                                c_typ = None
                            try:
                                c_attrs = [a for a in dir(c) if not a.startswith('_')][:20]
                            except Exception:
                                c_attrs = []
                            try:
                                c_val = getattr(c, 'value') if hasattr(c, 'value') else None
                            except Exception:
                                c_val = None
                        except Exception:
                            c_typ = None
                            c_attrs = []
                            c_val = None
                        # Inspect .instance if present
                        try:
                            inst = getattr(swapchain, 'instance')
                            try:
                                inst_typ = type(inst)
                            except Exception:
                                inst_typ = None
                            try:
                                inst_attrs = [a for a in dir(inst) if not a.startswith('_')][:20]
                            except Exception:
                                inst_attrs = []
                        except Exception:
                            inst_typ = None
                            inst_attrs = []
                        self._logger.info("[VR] Enhanced handle extraction: sc_handle=%r (type=%s)", sc_handle, type(sc_handle))
                        self._logger.warning("[VR] Swapchain image count 0 (ret=%r handle=%r, hasOpenGLStruct=%r, hasBaseHdr=%r, obj_type=%s, obj_attrs=%s, contents_type=%s, contents_attrs=%s, contents_value=%r, instance_type=%s, instance_attrs=%s)",
                                              ret if 'ret' in locals() else None,
                                              sc_handle,
                                              hasattr(xr, 'SwapchainImageOpenGLKHR'),
                                              hasattr(xr, 'SwapchainImageBaseHeader'),
                                              type(swapchain), attrs, c_typ, c_attrs, c_val, inst_typ, inst_attrs)
                        self._logged_zero_imgs_once = True
                except Exception:
                    pass
                return []
            # 2) Allocate array of SwapchainImageOpenGLKHR and set type
            ImgCls = getattr(xr, 'SwapchainImageOpenGLKHR', None)
            BaseHdr = getattr(xr, 'SwapchainImageBaseHeader', None)
            if ImgCls is None:
                return []
            try:
                st = self._get_structure_type((
                    (None, 'XR_TYPE_SWAPCHAIN_IMAGE_OPENGL_KHR'),
                    (None, 'TYPE_SWAPCHAIN_IMAGE_OPENGL_KHR'),
                    ('StructureType', 'SWAPCHAIN_IMAGE_OPENGL_KHR'),
                ))
            except Exception:
                st = None
            CArr = (ImgCls * n)()
            for i in range(n):
                try:
                    for name in ('type', 'sType', 'stype'):
                        try:
                            setattr(CArr[i], name, st)
                            break
                        except Exception:
                            continue
                    for name in ('next', 'pNext'):
                        try:
                            setattr(CArr[i], name, None)
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
            # 3) Call enumerate with pointer to base header array
            try:
                if BaseHdr is not None:
                    ptr = _ct.cast(CArr, _ct.POINTER(BaseHdr))
                else:
                    ptr = _ct.cast(CArr, _ct.c_void_p)
            except Exception:
                return []
            try:
                ret = proc(sc_handle if sc_handle else swapchain, n, _ct.byref(count), ptr)
            except Exception:
                return []
            nn = int(getattr(count, 'value', n))
            out = []
            for i in range(nn):
                try:
                    out.append(int(getattr(CArr[i], 'image')))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def _xr_swapchain_acquire_image(self, swapchain):
        """Acquire next image index from swapchain."""
        for mname in ("acquire_image", "acquireImage"):
            f = getattr(swapchain, mname, None)
            if not f:
                continue
            try:
                return f()
            except Exception:
                pass
        # Prepare AcquireInfo if needed
        ai = None
        for cname in ("SwapchainImageAcquireInfo", "SwapChainImageAcquireInfo"):
            C = getattr(xr, cname, None)
            if C is not None:
                try:
                    ai = C()
                    break
                except Exception:
                    ai = None
        for fname in ("acquire_swapchain_image", "xrAcquireSwapchainImage", "acquireSwapchainImage"):
            f = getattr(xr, fname, None)
            if f:
                try:
                    if ai is not None:
                        return f(swapchain, ai)
                    return f(swapchain)
                except Exception:
                    pass
        raise AttributeError("OpenXR binding lacks acquire_image")

    def _xr_swapchain_wait_image(self, swapchain, timeout_ns: int | None = None):
        """Wait for acquired image to become available."""
        for mname in ("wait_image", "waitImage"):
            f = getattr(swapchain, mname, None)
            if f:
                try:
                    return f()
                except Exception:
                    pass
        # Some bindings require a wait info struct
        wi = None
        for cname in ("SwapchainImageWaitInfo", "SwapChainImageWaitInfo"):
            C = getattr(xr, cname, None)
            if C is not None:
                try:
                    t = timeout_ns if timeout_ns is not None else int(10_000_000)  # 10ms default
                    wi = C(timeout=t)
                    break
                except Exception:
                    wi = None
        for fname in ("wait_swapchain_image", "xrWaitSwapchainImage", "waitSwapchainImage"):
            f = getattr(xr, fname, None)
            if f:
                try:
                    if wi is not None:
                        return f(swapchain, wi)
                    return f(swapchain)
                except Exception:
                    pass
        return None

    def _xr_swapchain_release_image(self, swapchain):
        """Release acquired image back to swapchain."""
        for mname in ("release_image", "releaseImage"):
            f = getattr(swapchain, mname, None)
            if f:
                try:
                    return f()
                except Exception:
                    pass
        # ReleaseInfo if needed
        ri = None
        for cname in ("SwapchainImageReleaseInfo", "SwapChainImageReleaseInfo"):
            C = getattr(xr, cname, None)
            if C is not None:
                try:
                    ri = C()
                    break
                except Exception:
                    ri = None
        for fname in ("release_swapchain_image", "xrReleaseSwapchainImage", "releaseSwapchainImage"):
            f = getattr(xr, fname, None)
            if f:
                try:
                    if ri is not None:
                        return f(swapchain, ri)
                    return f(swapchain)
                except Exception:
                    pass
        return None

    def _xr_session_wait_frame(self, session):
        """Wait for next frame; handle module/instance variants and info structs."""
        # Prefer module-level function first (pyopenxr commonly exposes these)
        FWI = getattr(xr, 'FrameWaitInfo', None)
        info = None
        if FWI is not None:
            try:
                info = FWI()
            except Exception:
                info = None
        for fname in ("wait_frame", "xrWaitFrame", "waitFrame"):
            g = getattr(xr, fname, None)
            if not g:
                continue
            try:
                if info is not None:
                    return g(session, info)
                return g(session)
            except Exception:
                pass
        # Fallback to instance methods
        f = getattr(session, 'wait_frame', None) or getattr(session, 'waitFrame', None)
        if f:
            try:
                return f()
            except Exception:
                pass
        # Some bindings require FrameWaitInfo (instance path)
        FWI = getattr(xr, 'FrameWaitInfo', None)
        info = None
        if FWI is not None:
            try:
                info = FWI()
            except Exception:
                info = None
        raise AttributeError("OpenXR binding lacks wait_frame")

    def _xr_session_begin_frame(self, session):
        """Begin frame; handle instance/module variants."""
        # Prefer module-level first
        FBI = getattr(xr, 'FrameBeginInfo', None)
        info = None
        if FBI is not None:
            try:
                info = FBI()
            except Exception:
                info = None
        for fname in ("begin_frame", "xrBeginFrame", "beginFrame"):
            g = getattr(xr, fname, None)
            if not g:
                continue
            try:
                if info is not None:
                    return g(session, info)
                return g(session)
            except Exception:
                pass
        # Instance methods as fallback
        f = getattr(session, 'begin_frame', None) or getattr(session, 'beginFrame', None)
        if f:
            try:
                return f()
            except Exception:
                pass
        # Proc address fallback
        try:
            g = self._xr_proc('xrBeginFrame', ['PFN_xrBeginFrame'])
            if info is None:
                FBI = getattr(xr, 'FrameBeginInfo', None)
                try:
                    info = FBI() if FBI is not None else None
                except Exception:
                    info = None
            if info is not None:
                return g(session, info)
            return g(session)
        except Exception:
            pass
        raise AttributeError("OpenXR binding lacks begin_frame")

    def _xr_session_end_frame(self, session, layers, display_time=None):
        """End frame; try instance method then module-level APIs with end info."""
        # Prefer module-level first
        FEI = getattr(xr, 'FrameEndInfo', None)
        info = None
        blend_mode_value = None
        
        if FEI is not None:
            try:
                # Try to provide display_time and blend_mode
                blend = getattr(xr, 'EnvironmentBlendMode', None)
                if blend is not None and hasattr(blend, 'OPAQUE'):
                    bm = blend.OPAQUE
                    blend_mode_value = bm
                else:
                    bm = 1  # typical opaque value fallback
                    blend_mode_value = bm
                if display_time is not None:
                    info = FEI(display_time=display_time, environment_blend_mode=bm, layers=layers)
                else:
                    info = FEI(layers=layers)
            except Exception:
                try:
                    if display_time is not None:
                        info = FEI(displayTime=display_time, environmentBlendMode=bm, layers=layers)  # type: ignore
                    else:
                        info = FEI()
                except Exception:
                    info = None
        
        # Log end_frame parameters once for debugging
        if not getattr(self, "_logged_end_frame_params", False):
            self._logger.info("[VR] end_frame params: layers=%d blend_mode=%s display_time=%s", 
                            len(layers), blend_mode_value, display_time is not None)
            self._logged_end_frame_params = True
        
        result = None
        for fname in ("end_frame", "xrEndFrame", "endFrame"):
            g = getattr(xr, fname, None)
            if not g:
                continue
            try:
                if info is not None:
                    result = g(session, info)
                else:
                    # Fall back to calling with layers only
                    result = g(session)
                
                # Log the result on first successful call
                if not getattr(self, "_logged_end_frame_result", False):
                    self._logger.info("[VR] end_frame result: %s (XR_SUCCESS expected)", result)
                    self._logged_end_frame_result = True
                return result
            except Exception as e:
                # Log once but don't fail - continue to instance method fallback
                if not getattr(self, "_logged_end_frame_error", False):
                    self._logger.debug("[VR] end_frame module-level failed, trying instance method: %s", e)
                    self._logged_end_frame_error = True
                # Don't return here - continue to instance method fallback
        # Instance method as fallback
        f = getattr(session, 'end_frame', None) or getattr(session, 'endFrame', None)
        if f:
            try:
                # Try with frame_end_info argument (pyopenxr style)
                if info is not None:
                    result = f(info)
                else:
                    result = f(layers=layers)
                
                # Log the result on first successful call
                if not getattr(self, "_logged_end_frame_result2", False):
                    self._logger.info("[VR] end_frame (instance) result: %s (XR_SUCCESS expected)", result)
                    self._logged_end_frame_result2 = True
                return result
            except Exception as e:
                if not getattr(self, "_logged_end_frame_error2", False):
                    self._logger.debug("[VR] end_frame instance method failed: %s", e)
                    self._logged_end_frame_error2 = True
                try:
                    return f()
                except Exception:
                    pass
        # Proc address fallback
        try:
            g = self._xr_proc('xrEndFrame', ['PFN_xrEndFrame'])
            if info is None:
                FEI = getattr(xr, 'FrameEndInfo', None)
                if FEI is not None:
                    try:
                        blend = getattr(xr, 'EnvironmentBlendMode', None)
                        bm = getattr(blend, 'OPAQUE', 1) if blend is not None else 1
                        info = FEI(display_time=display_time, environment_blend_mode=bm, layers=layers)
                    except Exception:
                        try:
                            info = FEI()
                        except Exception:
                            info = None
            if info is not None:
                return g(session, info)
            return g(session)
        except Exception:
            pass
        return None

    def _xr_session_locate_views(self, session, view_cfg, display_time, space):
        """Locate views; support instance/module calls and locate info structs."""
        # Instance method
        for mname in ("locate_views", "locateViews"):
            f = getattr(session, mname, None)
            if not f:
                continue
            try:
                return f(view_configuration_type=view_cfg, display_time=display_time, space=space)
            except Exception:
                try:
                    return f(viewConfigurationType=view_cfg, displayTime=display_time, space=space)  # type: ignore
                except Exception:
                    pass
        # Build locate info
        VLI = getattr(xr, 'ViewLocateInfo', None)
        info = None
        if VLI is not None:
            try:
                info = VLI(view_configuration_type=view_cfg, display_time=display_time, space=space)
            except Exception:
                try:
                    info = VLI(viewConfigurationType=view_cfg, displayTime=display_time, space=space)  # type: ignore
                except Exception:
                    info = None
        for fname in ("locate_views", "xrLocateViews", "locateViews"):
            g = getattr(xr, fname, None)
            if not g:
                continue
            try:
                if info is not None:
                    return g(session, info)
                return g(session, view_cfg, display_time, space)
            except Exception:
                pass
        # Proc address fallback
        try:
            g = self._xr_proc('xrLocateViews', ['PFN_xrLocateViews'])
            if info is None:
                VLI = getattr(xr, 'ViewLocateInfo', None)
                try:
                    info = VLI(view_configuration_type=view_cfg, display_time=display_time, space=space) if VLI else None
                except Exception:
                    info = None
            if info is not None:
                return g(session, info)
            return g(session, view_cfg, display_time, space)
        except Exception:
            pass
        raise AttributeError("OpenXR binding lacks locate_views")

    def _xr_begin_session(self, session, view_cfg):
        """Begin an XR session with the specified view configuration."""
        # Instance method
        for mname in ("begin_session", "beginSession", "begin", "start_session", "startSession"):
            f = getattr(session, mname, None)
            if f:
                try:
                    # Common snake_case field name used by some bindings
                    return f(view_configuration_type=view_cfg)
                except Exception:
                    try:
                        # CamelCase variant used by others
                        return f(viewConfigurationType=view_cfg)  # type: ignore
                    except Exception:
                        try:
                            # Official OpenXR name: primary_view_configuration_type
                            return f(primary_view_configuration_type=view_cfg)
                        except Exception:
                            try:
                                # CamelCase official: primaryViewConfigurationType
                                return f(primaryViewConfigurationType=view_cfg)  # type: ignore
                            except Exception:
                                try:
                                    # Some bindings accept no-arg begin()
                                    return f()
                                except Exception:
                                    pass
        # Build begin info
        SBI = getattr(xr, 'SessionBeginInfo', None)
        info = None
        if SBI is not None:
            try:
                # Try several field name variants
                info = SBI(view_configuration_type=view_cfg)
            except Exception:
                try:
                    info = SBI(viewConfigurationType=view_cfg)  # type: ignore
                except Exception:
                    try:
                        info = SBI(primary_view_configuration_type=view_cfg)
                    except Exception:
                        try:
                            info = SBI(primaryViewConfigurationType=view_cfg)  # type: ignore
                        except Exception:
                            info = None
        # If info is still None, try constructing empty then setting attributes (including type/next)
        if info is None and SBI is not None:
            try:
                info = SBI()
                # type/next if required
                st = self._get_structure_type((
                    ("StructureType", "SESSION_BEGIN_INFO"),
                    (None, "XR_TYPE_SESSION_BEGIN_INFO"),
                    (None, "TYPE_SESSION_BEGIN_INFO"),
                ))
                for name in ("type", "sType", "stype"):
                    try:
                        setattr(info, name, st)
                        break
                    except Exception:
                        continue
                for name in ("next", "pNext"):
                    try:
                        setattr(info, name, None)
                        break
                    except Exception:
                        continue
                # set view config via various names
                for name in ("view_configuration_type", "viewConfigurationType", "primary_view_configuration_type", "primaryViewConfigurationType"):
                    try:
                        setattr(info, name, view_cfg)
                        break
                    except Exception:
                        continue
            except Exception:
                info = None
        # Module-level functions
        for fname in ("begin_session", "xr_begin_session", "xrBeginSession", "beginSession", "begin"):
            g = getattr(xr, fname, None)
            if not g:
                continue
            try:
                if info is not None:
                    return g(session, info)
                # Some bindings accept kwargs directly
                try:
                    return g(session, view_cfg)
                except Exception:
                    try:
                        return g(session, primary_view_configuration_type=view_cfg)
                    except Exception:
                        # Last resort: no-arg
                        return g(session)
            except Exception:
                pass
        # Proc address fallback
        try:
            g = self._xr_proc('xrBeginSession', ['PFN_xrBeginSession'])
            if info is None:
                SBI = getattr(xr, 'SessionBeginInfo', None)
                try:
                    info = SBI(view_configuration_type=view_cfg) if SBI else None
                except Exception:
                    info = None
            if info is not None:
                return g(session, info)
            # Some function pointers may accept (session, view_cfg) if they internally wrap
            return g(session, view_cfg)
        except Exception:
            pass
        raise AttributeError("OpenXR binding lacks begin_session")

    def _get_structure_type(self, candidates: tuple[tuple[str | None, str], ...]):
        """Try to resolve a structure type constant across binding naming patterns.

        candidates: sequence of (enum_class_name_or_None, member_name)
        """
        for enum, name in candidates:
            try:
                if enum:
                    et = getattr(xr, enum, None)
                    if et is not None:
                        return getattr(et, name)
                else:
                    return getattr(xr, name)
            except Exception:
                continue
        return None

    def _xr_end_session(self, session):
        """End an XR session if API supports it."""
        # Instance method
        for mname in ("end_session", "endSession"):
            f = getattr(session, mname, None)
            if f:
                try:
                    return f()
                except Exception:
                    pass
        # Module-level function
        for fname in ("end_session", "xrEndSession", "endSession"):
            g = getattr(xr, fname, None)
            if g:
                try:
                    return g(session)
                except Exception:
                    pass
        return None
