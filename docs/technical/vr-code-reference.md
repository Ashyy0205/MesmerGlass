# VR Implementation Code Reference

Quick reference for key code patterns and implementations in the VR system.

---

## Initialization Pattern

### Full Initialization Sequence

```python
from mesmerglass.vr.vr_bridge import VRBridge

# 1. Create bridge instance (sets action manifest env var)
bridge = VRBridge()

# 2. Initialize OpenXR
if not bridge.initialize():
    print("VR initialization failed")
    return

# 3. Run frame loop
try:
    while True:
        if not bridge.render_frame():
            break
        time.sleep(0.001)  # Minimal sleep, frame timing handled by wait_frame
except KeyboardInterrupt:
    print("Shutting down...")
finally:
    bridge.shutdown()
```

---

## Reference Space Creation

### Robust Space Creation with Fallback

```python
def _create_first_valid_space(self):
    """
    Try space types in priority order: LOCAL → STAGE → VIEW
    Returns first valid (non-NULL) space handle
    """
    for space_type in [xr.ReferenceSpaceType.LOCAL, 
                       xr.ReferenceSpaceType.STAGE, 
                       xr.ReferenceSpaceType.VIEW]:
        try:
            # IMPORTANT: Use ReferenceSpaceCreateInfo struct
            create_info = xr.ReferenceSpaceCreateInfo(
                reference_space_type=space_type,
                pose_in_reference_space=xr.Posef()  # Identity pose
            )
            space = xr.create_reference_space(self.session, create_info)
            
            # CRITICAL: Validate handle is not NULL (0x0)
            if self._is_valid_handle(space):
                self.space = space
                self.space_type = space_type
                self.logger.info(f"[XR] ✅ Created {space_type.name} space with VALID handle")
                return space, space_type
            else:
                self.logger.warning(f"[XR] ⚠️ {space_type.name} space returned NULL handle")
        except Exception as e:
            self.logger.warning(f"[XR] Failed to create {space_type.name} space: {e}")
            continue
    
    # All space types failed
    return None, None

def _is_valid_handle(self, handle) -> bool:
    """Check if OpenXR handle is valid (not NULL/0x0)"""
    if handle is None:
        return False
    if hasattr(handle, 'value'):
        return handle.value != 0
    return int(handle) != 0
```

**Key Points**:
- Use `ReferenceSpaceCreateInfo` struct, not individual parameters
- Validate handles explicitly - NULL returns don't throw exceptions
- Fallback order: LOCAL (room-scale) → STAGE (standing) → VIEW (head-locked)

---

## Swapchain Format Selection

### Prefer LINEAR Formats for SteamVR

```python
def _choose_gl_format(self, available_formats):
    """
    Choose OpenGL format from available swapchain formats.
    Prioritizes LINEAR formats for SteamVR compatibility.
    """
    # Format preference: LINEAR first, SRGB fallback
    preferred = [
        0x8058,  # GL_RGBA8 (LINEAR)
        0x881A,  # GL_RGBA16F (LINEAR)
        0x881B,  # GL_RGB16F (LINEAR)
        0x8C41,  # GL_SRGB8 (LINEAR-like)
        0x8C43,  # GL_SRGB8_ALPHA8 (SRGB - fallback)
    ]
    
    for fmt in preferred:
        if fmt in available_formats:
            self.logger.info(f"[VR] Selected format: 0x{fmt:04X}")
            return fmt
    
    # Last resort: use first available
    self.logger.warning(f"[VR] Using fallback format: 0x{available_formats[0]:04X}")
    return available_formats[0]
```

**Why LINEAR?**:
- SteamVR compositor expects LINEAR color space
- SRGB formats may cause visibility issues
- Runtime typically selects RGBA16F (0x881A) - confirmed working

---

## Frame Loop Pattern

### Complete Frame Rendering with State Checks

```python
def render_frame(self):
    """
    Render one VR frame with proper state management.
    Returns False if session should end.
    """
    # 1. Poll events first (state changes, etc.)
    self._poll_events()
    
    # 2. Check if session is in running state
    if not self.session_running:
        return False
    
    # 3. Wait for frame timing
    frame_state = xr.wait_frame(self.session)
    
    # 4. CRITICAL: Check shouldRender BEFORE begin_frame
    if not frame_state.shouldRender:
        # Don't call begin_frame if not rendering!
        # This happens during state transitions
        return True
    
    # 5. Begin frame (compositor is ready)
    xr.begin_frame(self.session)
    
    # 6. Locate views (get eye poses)
    views, view_state = self._locate_views(frame_state.predictedDisplayTime)
    
    # 7. Render to swapchains
    layers = []
    
    if views and (view_state.view_state_flags & xr.ViewStateFlags.POSITION_VALID):
        # Tracking valid - use projection layers
        layer = self._render_projection_layer(views, frame_state.predictedDisplayTime)
        if layer:
            layers.append(layer)
    
    # 8. Fallback: quad layer if no projection
    if not layers:
        layer = self._render_quad_fallback()
        if layer:
            layers.append(layer)
    
    # 9. CRITICAL: Never submit empty layers!
    if not layers:
        self.logger.error("[VR] ❌ No layers to submit!")
        return False
    
    # 10. End frame (submit to compositor)
    frame_end_info = xr.FrameEndInfo(
        display_time=frame_state.predictedDisplayTime,
        environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE,
        layers=layers
    )
    
    result = xr.end_frame(self.session, frame_end_info)
    
    return True
```

**Critical Points**:
- Always check `shouldRender` before `begin_frame()`
- Never call `end_frame()` with empty layers array
- Always have fallback layer (quad) if projection fails

---

## View Location Pattern

### Getting Eye Poses with Error Handling

```python
def _locate_views(self, display_time):
    """
    Locate eye views at predicted display time.
    Returns (views, view_state) or (None, None) on failure.
    """
    # Check space handle is valid
    if not self._is_valid_handle(self.space):
        self.logger.warning("[XR] No valid space handle - cannot call locate_views")
        return None, None
    
    try:
        # IMPORTANT: Use ViewLocateInfo struct
        view_locate_info = xr.ViewLocateInfo(
            view_configuration_type=self.view_config_type,
            display_time=display_time,
            space=self.space
        )
        
        view_state, views = xr.locate_views(
            self.session,
            view_locate_info
        )
        
        # Check if position tracking is valid
        if view_state.view_state_flags & xr.ViewStateFlags.POSITION_VALID:
            self.logger.debug(f"[VR] ✅ locate_views SUCCESS! Got {len(views)} views with POSITION_VALID")
            return views, view_state
        else:
            self.logger.warning(f"[VR] ⚠️ locate_views returned but POSITION_INVALID (flags={view_state.view_state_flags})")
            return None, view_state
    
    except Exception as e:
        self.logger.error(f"[XR] locate_views failed: {e}")
        return None, None
```

**Key Points**:
- Use `ViewLocateInfo` struct
- Check `POSITION_VALID` flag before using poses
- Handle gracefully - failure should fall back to quad layer

---

## Layer Submission Patterns

### Projection Layer (Stereo Tracking)

```python
def _render_projection_layer(self, views, display_time):
    """
    Render stereo projection layer with tracked eye poses.
    """
    projection_views = []
    
    for eye_index, view in enumerate(views):
        # Acquire swapchain image
        swapchain = self.swapchains[eye_index]
        acquire_info = xr.SwapchainImageAcquireInfo()
        image_index = xr.acquire_swapchain_image(swapchain, acquire_info)
        
        # Wait for image to be ready
        wait_info = xr.SwapchainImageWaitInfo(timeout=xr.INFINITE_DURATION)
        xr.wait_swapchain_image(swapchain, wait_info)
        
        # Get OpenGL texture ID
        gl_images = self.swapchain_images[eye_index]
        texture_id = gl_images[image_index].image
        
        # Bind and render to texture
        glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, 
                               GL_TEXTURE_2D, texture_id, 0)
        
        glViewport(0, 0, view.recommended_image_rect_width, 
                   view.recommended_image_rect_height)
        
        # Clear with OPAQUE alpha
        glClearColor(0.0, 1.0, 0.0, 1.0)  # Green for left, magenta for right
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # TODO: Render actual content here using view.pose and view.fov
        
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        
        # Release swapchain image
        release_info = xr.SwapchainImageReleaseInfo()
        xr.release_swapchain_image(swapchain, release_info)
        
        # Build projection view
        projection_views.append(xr.CompositionLayerProjectionView(
            pose=view.pose,
            fov=view.fov,
            sub_image=xr.SwapchainSubImage(
                swapchain=swapchain,
                image_rect=xr.Rect2Di(
                    offset=xr.Offset2Di(0, 0),
                    extent=xr.Extent2Di(
                        view.recommended_image_rect_width,
                        view.recommended_image_rect_height
                    )
                )
            )
        ))
    
    # Create projection layer
    layer = xr.CompositionLayerProjection(
        space=self.space,
        views=projection_views,
        layer_flags=(xr.CompositionLayerFlags.BLEND_TEXTURE_SOURCE_ALPHA_BIT |
                     xr.CompositionLayerFlags.CORRECT_CHROMATIC_ABERRATION_BIT)
    )
    
    return layer
```

---

### Quad Layer (Head-Locked Fallback)

```python
def _render_quad_fallback(self):
    """
    Render head-locked quad layer as fallback when tracking unavailable.
    Uses VIEW space so quad is always centered in view.
    """
    # Create VIEW space for head-locked rendering
    if not hasattr(self, '_view_space') or not self._is_valid_handle(self._view_space):
        try:
            create_info = xr.ReferenceSpaceCreateInfo(
                reference_space_type=xr.ReferenceSpaceType.VIEW,
                pose_in_reference_space=xr.Posef()
            )
            self._view_space = xr.create_reference_space(self.session, create_info)
            self.logger.info("[XR] ✅ Created VIEW space for quad fallback")
        except Exception as e:
            self.logger.error(f"[XR] Failed to create VIEW space: {e}")
            return None
    
    # Use first swapchain (left eye)
    swapchain = self.swapchains[0]
    
    # Acquire, render, release (similar to projection)
    acquire_info = xr.SwapchainImageAcquireInfo()
    image_index = xr.acquire_swapchain_image(swapchain, acquire_info)
    
    wait_info = xr.SwapchainImageWaitInfo(timeout=xr.INFINITE_DURATION)
    xr.wait_swapchain_image(swapchain, wait_info)
    
    # Render quad content...
    # (bind FBO, render, unbind - same as projection)
    
    release_info = xr.SwapchainImageReleaseInfo()
    xr.release_swapchain_image(swapchain, release_info)
    
    # Create quad layer
    # Position: 1.2m in front, centered
    pose = xr.Posef(
        orientation=xr.Quaternionf(0, 0, 0, 1),  # No rotation
        position=xr.Vector3f(0, 0, -1.2)  # 1.2m in front
    )
    
    # Size: 1.2m wide, 0.68m tall (16:9 aspect)
    layer = xr.CompositionLayerQuad(
        space=self._view_space,  # VIEW space = head-locked
        pose=pose,
        size=xr.Extent2Df(1.2, 0.68),
        sub_image=xr.SwapchainSubImage(
            swapchain=swapchain,
            image_rect=xr.Rect2Di(
                offset=xr.Offset2Di(0, 0),
                extent=xr.Extent2Di(
                    self.view_width,
                    self.view_height
                )
            )
        ),
        layer_flags=(xr.CompositionLayerFlags.BLEND_TEXTURE_SOURCE_ALPHA_BIT |
                     xr.CompositionLayerFlags.CORRECT_CHROMATIC_ABERRATION_BIT)
    )
    
    self.logger.info("[XR] 📺 Submitting QUAD layer with flags=0x3")
    return layer
```

**Key Points**:
- Use VIEW space for head-locked content
- Single swapchain (not stereo) for quad
- Set appropriate size and distance
- Same layer flags as projection

---

## Action Manifest Setup

### Set Environment Variable Before OpenXR Init

```python
def _setup_action_manifest_path(self):
    """
    Set STEAMVR_ACTION_MANIFEST_PATH environment variable.
    MUST be called before xr.create_instance()!
    """
    manifest_path = Path(__file__).parent.parent.parent / "actions.json"
    
    if manifest_path.exists():
        os.environ["STEAMVR_ACTION_MANIFEST_PATH"] = str(manifest_path.resolve())
        self.logger.info(f"[VR] ✅ Set STEAMVR_ACTION_MANIFEST_PATH={manifest_path}")
    else:
        self.logger.warning(f"[VR] ⚠️ actions.json not found at {manifest_path}")

def __init__(self):
    # IMPORTANT: Set action manifest FIRST
    self._setup_action_manifest_path()
    
    # Then create OpenXR instance
    self.instance = None
    self.session = None
    # ... rest of init
```

### Minimal Action Manifest File

**File**: `actions.json`
```json
{
  "default_bindings": [],
  "actions": [
    {
      "name": "/actions/default/in/head_pose",
      "type": "pose"
    }
  ],
  "action_sets": [
    {
      "name": "/actions/default",
      "usage": "leftright"
    }
  ],
  "localization": {
    "en_US": {
      "/actions/default": "Default",
      "/actions/default/in/head_pose": "Head Pose"
    }
  }
}
```

**Purpose**: Minimal manifest to satisfy SteamVR input system

---

## Session State Management

### Event Polling and State Tracking

```python
def _poll_events(self):
    """
    Poll OpenXR events and handle state changes.
    Call this at start of every frame.
    """
    while True:
        try:
            event = xr.poll_event(self.instance)
            
            if isinstance(event, xr.EventDataSessionStateChanged):
                self._handle_session_state_changed(event)
            elif isinstance(event, xr.EventDataInstanceLossPending):
                self.logger.warning("[VR] Instance loss pending!")
                return False
            # ... handle other event types
            
        except xr.EventUnavailable:
            # No more events
            break
        except Exception as e:
            self.logger.error(f"[VR] Event polling error: {e}")
            break
    
    return True

def _handle_session_state_changed(self, event):
    """Handle OpenXR session state transitions"""
    old_state = self.session_state
    new_state = event.state
    
    self.session_state = new_state
    self.logger.info(f"[VR] Session state changed: {new_state.name}")
    
    if new_state == xr.SessionState.READY:
        # Begin session when ready
        session_begin_info = xr.SessionBeginInfo(
            primary_view_configuration_type=self.view_config_type
        )
        xr.begin_session(self.session, session_begin_info)
        self.session_running = True
        self.logger.info("[VR] Began session in response to READY state")
        
    elif new_state == xr.SessionState.STOPPING:
        # End session when stopping
        xr.end_session(self.session)
        self.session_running = False
        self.logger.info("[VR] Ended session in response to STOPPING state")
        
    elif new_state in [xr.SessionState.SYNCHRONIZED, 
                       xr.SessionState.VISIBLE, 
                       xr.SessionState.FOCUSED]:
        # These are all "running" states
        self.session_running = True
        
    elif new_state in [xr.SessionState.IDLE, 
                       xr.SessionState.EXITING, 
                       xr.SessionState.LOSS_PENDING]:
        # These are "not running" states
        self.session_running = False
```

**State Progression**:
1. IDLE - Initial state
2. READY - Runtime ready, call `begin_session()`
3. SYNCHRONIZED - Session active, timing valid, NO frames yet
4. VISIBLE - Frames visible in compositor
5. FOCUSED - Frames visible AND app has input focus

---

## CLI Integration

### VR Selftest Command

**File**: `mesmerglass/cli.py`

```python
@main.command()
def vr_selftest():
    """Run VR rendering self-test with colored quads"""
    from mesmerglass.vr.vr_bridge import VRBridge
    import time
    
    print("VR system initializing... Please put on your headset.")
    
    bridge = VRBridge()
    
    if not bridge.initialize():
        print("❌ VR initialization failed!")
        return 1
    
    print("✅ VR initialized successfully!")
    print("Starting VR rendering...")
    print("Press Ctrl+C to stop.")
    
    try:
        frame_count = 0
        while True:
            if not bridge.render_frame():
                print("Session ended by runtime")
                break
            
            frame_count += 1
            if frame_count % 72 == 0:  # Every second at 72Hz
                print(f"  {frame_count} frames rendered...")
            
            time.sleep(0.001)  # Minimal sleep
            
    except KeyboardInterrupt:
        print("\n\nShutting down VR...")
    finally:
        bridge.shutdown()
        print("✅ VR shutdown complete")
    
    return 0
```

**Run**:
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-selftest
```

---

## Logging Configuration

### Useful Log Levels

```python
import logging

# In __init__:
self.logger = logging.getLogger(__name__)

# Key log points:
self.logger.info("[VR] ✅ Success message")
self.logger.warning("[VR] ⚠️ Warning message")
self.logger.error("[VR] ❌ Error message")
self.logger.debug("[VR] Debug details")

# For critical diagnostics:
self.logger.info(f"[VR] Space handle: {self.space} (valid={self._is_valid_handle(self.space)})")
self.logger.info(f"[VR] Session state: {self.session_state.name}")
self.logger.info(f"[VR] Swapchain format: 0x{format:04X}")
```

---

## Complete Minimal Example

```python
#!/usr/bin/env python3
"""Minimal VR example"""

import xr
import time
from OpenGL.GL import *

def main():
    # 1. Create instance
    app_info = xr.ApplicationInfo(
        application_name="MinimalVR",
        application_version=1,
        engine_name="",
        engine_version=0,
        api_version=xr.XR_CURRENT_API_VERSION
    )
    
    create_info = xr.InstanceCreateInfo(
        application_info=app_info,
        enabled_extension_names=["XR_KHR_opengl_enable"]
    )
    
    instance = xr.create_instance(create_info)
    
    # 2. Get system
    get_info = xr.SystemGetInfo(
        form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY
    )
    system_id = xr.get_system(instance, get_info)
    
    # 3. Create session (requires OpenGL context)
    # ... (OpenGL setup code)
    
    session_create_info = xr.SessionCreateInfo(
        system_id=system_id,
        # ... graphics binding ...
    )
    session = xr.create_session(instance, session_create_info)
    
    # 4. Create space
    space_create_info = xr.ReferenceSpaceCreateInfo(
        reference_space_type=xr.ReferenceSpaceType.LOCAL,
        pose_in_reference_space=xr.Posef()
    )
    space = xr.create_reference_space(session, space_create_info)
    
    # 5. Create swapchains
    # ... (swapchain code)
    
    # 6. Frame loop
    while True:
        frame_state = xr.wait_frame(session)
        
        if not frame_state.shouldRender:
            continue
        
        xr.begin_frame(session)
        
        # Render...
        
        frame_end_info = xr.FrameEndInfo(
            display_time=frame_state.predictedDisplayTime,
            environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE,
            layers=[layer]
        )
        xr.end_frame(session, frame_end_info)
    
    # 7. Cleanup
    xr.destroy_space(space)
    xr.destroy_session(session)
    xr.destroy_instance(instance)

if __name__ == "__main__":
    main()
```

---

**Document Version**: 1.0  
**Last Updated**: November 2, 2025
