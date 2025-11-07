# VR Troubleshooting Guide

This document covers all debugging steps taken during VR implementation and solutions to common OpenXR/SteamVR issues.

---

## Problem 1: NULL Space Handle (0x0)

### Symptoms
```
[XR] locate_views failed: Invalid handle
[XR] Space handle: 0x0 (NULL)
RuntimeError: xrLocateViews failed with result XR_ERROR_HANDLE_INVALID
```

### Root Cause
pyopenxr's `create_reference_space()` was being called with individual parameters instead of a CreateInfo struct. The API silently returned NULL handles without throwing exceptions.

### Solution
Implement proper CreateInfo struct pattern with explicit NULL validation:

```python
def _is_valid_handle(self, handle) -> bool:
    """Check if OpenXR handle is valid (not NULL/0x0)"""
    if handle is None:
        return False
    if hasattr(handle, 'value'):
        return handle.value != 0
    return int(handle) != 0

def _create_first_valid_space(self):
    """Try space types in order until we get valid handle"""
    for space_type in [xr.ReferenceSpaceType.LOCAL, 
                       xr.ReferenceSpaceType.STAGE, 
                       xr.ReferenceSpaceType.VIEW]:
        try:
            create_info = xr.ReferenceSpaceCreateInfo(
                reference_space_type=space_type,
                pose_in_reference_space=xr.Posef()
            )
            space = xr.create_reference_space(self.session, create_info)
            
            if self._is_valid_handle(space):
                self.logger.info(f"[XR] ✅ Created {space_type.name} space with VALID handle")
                return space, space_type
        except Exception as e:
            self.logger.warning(f"[XR] Failed to create {space_type.name} space: {e}")
            continue
    
    return None, None
```

### Verification
```
[XR] ✅ Created LOCAL space with VALID handle
[XR] ✅ Using LOCAL space for rendering
[VR] ✅ locate_views SUCCESS! Got 2 views with POSITION_VALID
```

**Status**: ✅ FIXED

---

## Problem 2: Compositor Not Showing Rendered Content

### Symptoms
- Frames render at 72Hz with 0 drops
- `locate_views` succeeds with POSITION_VALID
- Session reaches FOCUSED state
- But headset shows SteamVR loading grid, not app content

### Investigation Steps

#### Step 1: Check Swapchain Format
**Hypothesis**: SRGB formats may not composite correctly

**Original Format Preference**:
```python
preferred = [0x8C43, 0x8058, 0x881A]  # SRGB first
```

**Fix**: Prioritize LINEAR formats
```python
preferred = [
    0x8058,  # GL_RGBA8 (LINEAR)
    0x881A,  # GL_RGBA16F (LINEAR)
    0x8C43,  # GL_SRGB8_ALPHA8 (fallback)
]
```

**Runtime Selected**: 0x881A (RGBA16F LINEAR) ✅

---

#### Step 2: Check Layer Visibility Flags
**Hypothesis**: Missing compositor flags causing layer culling

**Fix**: Add proper OpenXR layer flags
```python
flags = (xr.CompositionLayerFlags.BLEND_TEXTURE_SOURCE_ALPHA_BIT |  # 0x1
         xr.CompositionLayerFlags.CORRECT_CHROMATIC_ABERRATION_BIT)   # 0x2

projection_layer.layer_flags = flags
quad_layer.layer_flags = flags
```

**Verification**: Flags applied to all submitted layers ✅

---

#### Step 3: Check Clear Color Alpha
**Hypothesis**: Alpha=0 causing transparent/invisible rendering

**Code Check**:
```python
glClearColor(0.0, 1.0, 0.0, 1.0)  # Green, FULLY OPAQUE
```

**Status**: Alpha already 1.0 (fully opaque) ✅

---

#### Step 4: Check Environment Blend Mode
**Hypothesis**: Wrong blend mode causing compositor issues

**Code Check**:
```python
frame_end_info = xr.FrameEndInfo(
    display_time=frame_state.predictedDisplayTime,
    environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE,
    layers=layers
)
```

**Status**: Using OPAQUE mode correctly ✅

---

#### Step 5: Check Empty Layers Bug
**Hypothesis**: Calling `end_frame()` with empty layers blocks state progression

**Original Code**:
```python
xr.begin_frame(self.session)
# ... tracking fails ...
layers = []  # Empty!
xr.end_frame(self.session, frame_end_info)
```

**Problem Discovered**: First frame has `shouldRender=False`, but we called `begin_frame()` anyway, then submitted empty layers.

**Fix**: Check `shouldRender` BEFORE calling `begin_frame()`
```python
frame_state = xr.wait_frame(self.session)

if not frame_state.shouldRender:
    # Don't call begin_frame if we won't render!
    return False

xr.begin_frame(self.session)

# Always ensure at least one layer
layers = [projection_layer] if tracking_ok else [quad_fallback]

xr.end_frame(self.session, frame_end_info)
```

**Result**: State progression now works (SYNCHRONIZED → VISIBLE → FOCUSED) ✅

---

### Final Root Cause: SteamVR App Registration

After all rendering fixes, the real problem was identified from SteamVR logs:

```
[Error] - [Input] LoadActionManifest failed. Could not find action manifest for app 'system.generated.openxr.mesmerglass.python.exe'
[Info] - Changing app type for 25676: python: Refusing because app start error VRInitError_Init_Retry
```

**Analysis**:
1. Compositor accepts all frames correctly (0 drops, proper format, valid layers)
2. BUT SteamVR refuses to exit loading screen
3. Reason: `python.exe` is not a registered VR application
4. SteamVR auto-generates key `system.generated.openxr.mesmerglass.python.exe`
5. This key has no matching `.vrmanifest` file
6. Compositor won't promote to scene app until registration validated

**Status**: ❌ BLOCKED on registration (not a rendering issue)

---

## Problem 3: Action Manifest Not Loading

### Symptoms
```
[Error] - [Input] LoadActionManifest failed. Could not find action manifest for app '...'
```

### Solution 1: Set Environment Variable
```python
def _setup_action_manifest_path(self):
    """Set STEAMVR_ACTION_MANIFEST_PATH before OpenXR init"""
    manifest_path = Path(__file__).parent.parent.parent / "actions.json"
    if manifest_path.exists():
        os.environ["STEAMVR_ACTION_MANIFEST_PATH"] = str(manifest_path.resolve())
        self.logger.info(f"[VR] ✅ Set STEAMVR_ACTION_MANIFEST_PATH={manifest_path}")
```

Call this in `__init__()` BEFORE `xr.create_instance()`.

### Solution 2: Link in VRManifest
```json
{
  "applications": [{
    "action_manifest_path": "C:\\Users\\Ash\\Desktop\\MesmerGlass\\actions.json"
  }]
}
```

**Status**: ⚠️ Environment variable set, but still requires app registration

---

## Problem 4: Python.exe Not Recognized as VR App

### Symptoms
- SteamVR generates dynamic key: `system.generated.openxr.mesmerglass.python.exe`
- No registered manifest matches this key
- Error: "Refusing because app start error VRInitError_Init_Retry"

### Attempted Solutions

#### Solution A: Register python.exe Directly
**Manifest**:
```json
{
  "app_key": "system.generated.openxr.mesmerglass.python.exe",
  "binary_path": "C:\\Program Files\\Python311\\python.exe",
  "arguments": "-m mesmerglass vr-selftest"
}
```

**Result**: ❌ SteamVR still doesn't recognize it

---

#### Solution B: Use Venv Python
**Manifest**:
```json
{
  "app_key": "mesmerglass",
  "binary_path_windows": "C:\\Users\\Ash\\Desktop\\MesmerGlass\\.venv\\Scripts\\python.exe",
  "arguments": "-m mesmerglass vr-selftest",
  "working_directory": "C:\\Users\\Ash\\Desktop\\MesmerGlass"
}
```

**Status**: ⏳ Pending registration confirmation

---

#### Solution C: Build Dedicated Launcher .exe
**Built**: `mesmerglass_launcher.exe` via PyInstaller

**Code**:
```python
def main():
    venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    cmd = [str(venv_python), "-m", "mesmerglass", "vr-selftest"]
    result = subprocess.run(cmd)
    return result.returncode
```

**Problem**: Launcher spawned infinite subprocess loops  
**Status**: ❌ Abandoned

---

#### Solution D: Batch File Launcher
**File**: `mesmerglass_launcher.bat`
```batch
@echo off
.\.venv\Scripts\python.exe -m mesmerglass vr-selftest
```

**Manifest**:
```json
{
  "binary_path_windows": "C:\\Users\\Ash\\Desktop\\MesmerGlass\\mesmerglass_launcher.bat"
}
```

**Status**: ⏳ Works locally, pending registration

---

### Registration Method Issues

#### Method 1: vrpathreg.exe Command Line
```powershell
& "C:\Program Files (x86)\Steam\steamapps\common\SteamVR\bin\win64\vrpathreg.exe" addmanifest "mesmerglass.vrmanifest"
```

**Problem**: User's SteamVR version doesn't have `addmanifest` command  
**Output**:
```
Commands:
  show - Display the current paths
  setruntime <path> - Sets the runtime path
  adddriver <path> - Adds an external driver
  # No addmanifest command listed!
```

**Status**: ❌ Command not available

---

#### Method 2: SteamVR Settings UI
**Steps**:
1. SteamVR → Settings
2. Click "Developer" in sidebar
3. Scroll to "Add Application Manifest"
4. Browse to `mesmerglass.vrmanifest`
5. Restart SteamVR

**Status**: ⏳ Instructions provided but not confirmed working

---

## Problem 5: Launcher .exe Spawning Loop

### Symptoms
After building `mesmerglass_launcher.exe`, running it caused:
- Dozens of Python processes spawned
- KeyboardInterrupt errors in rapid succession
- System resources exhausted

### Root Cause Analysis
**Launcher Code**:
```python
result = subprocess.run(cmd, cwd=str(project_root))
```

**Problem**: SteamVR was repeatedly launching the .exe, which repeatedly spawned Python subprocesses. Each subprocess launched MesmerGlass, which registered with OpenXR, causing SteamVR to... launch the .exe again.

### Why This Happened
1. User ran `mesmerglass_launcher.exe` manually
2. SteamVR detected new OpenXR app
3. SteamVR tried to register it automatically
4. SteamVR re-launched the .exe to "validate" it
5. New instance spawned new Python process
6. Goto step 2 (infinite loop)

### Solution
**Don't use launcher .exe approach**. Use direct Python registration instead:

```json
{
  "binary_path_windows": "C:\\...\\python.exe",
  "arguments": "-m mesmerglass vr-selftest"
}
```

This avoids subprocess indirection and lets SteamVR track the actual rendering process.

**Status**: ✅ Switched to direct Python approach

---

## Debugging Tools and Commands

### Check SteamVR Runtime Status
```powershell
& "C:\Program Files (x86)\Steam\steamapps\common\SteamVR\bin\win64\vrpathreg.exe" show
```

**Output**:
```
Runtime path = C:\Program Files (x86)\Steam\steamapps\common\SteamVR
Config path = C:\Program Files (x86)\Steam\config
Log path = C:\Program Files (x86)\Steam\logs
External Drivers:
        alvr_server : C:\Users\Ash\Downloads\ALVR\driver\
```

---

### Check OpenXR Active Runtime
```powershell
Get-ItemProperty -Path "HKLM:\SOFTWARE\Khronos\OpenXR\1" -Name "ActiveRuntime"
```

**Expected**:
```
ActiveRuntime : C:\Program Files (x86)\Steam\steamapps\common\SteamVR\steamxr_win64.json
```

---

### Tail SteamVR Logs (Real-Time)
```powershell
Get-Content "C:\Program Files (x86)\Steam\logs\vrserver.txt" -Wait -Tail 20
```

**Watch for**:
- `LoadActionManifest failed` - Action manifest not found
- `VRInitError_Init_Retry` - App registration failed
- `Transition to VRApplication_Scene` - Success!

---

### Check Python OpenXR Binding
```powershell
.\.venv\Scripts\python.exe -c "import xr; print(xr.__file__); print(dir(xr))"
```

**Verify**:
- Module loads without errors
- `create_instance`, `create_session`, `ReferenceSpaceCreateInfo` available

---

### Test VR Selftest
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-selftest
```

**Expected Output**:
```
[VR] OpenXR initialized: 2 eyes
[VR] Session state changed: FOCUSED
[VR] ✅ locate_views SUCCESS!
[VR] 🎯 Submitting PROJECTION layer
```

---

## Common Pitfalls

### ❌ Calling begin_frame() when shouldRender=False
**Problem**: Blocks state progression, causes empty layer submission  
**Fix**: Check `shouldRender` before calling `begin_frame()`

### ❌ Using SRGB Swapchain Formats
**Problem**: May cause compositor visibility issues  
**Fix**: Prioritize LINEAR formats (RGBA8, RGBA16F)

### ❌ Forgetting Layer Visibility Flags
**Problem**: Layers may be culled by compositor  
**Fix**: Set `BLEND_TEXTURE_SOURCE_ALPHA_BIT` and `CORRECT_CHROMATIC_ABERRATION_BIT`

### ❌ Submitting Empty Layers Array
**Problem**: end_frame() fails or blocks state progression  
**Fix**: Always submit at least one layer (projection or quad fallback)

### ❌ Not Validating Space Handles
**Problem**: NULL handles (0x0) cause `XR_ERROR_HANDLE_INVALID`  
**Fix**: Implement `_is_valid_handle()` check after creation

### ❌ Assuming python.exe is Recognized by SteamVR
**Problem**: SteamVR requires explicit app registration  
**Fix**: Register via `.vrmanifest` file in SteamVR Settings

---

## Performance Optimization Tips

### Use Projection Layers Over Quad Layers
**Why**: Projection layers use native compositor reprojection  
**When**: Whenever tracking is valid (POSITION_VALID flag set)

### Minimize CPU-GPU Sync
**How**: Don't call `glFinish()` or `glReadPixels()` in frame loop  
**Benefit**: Keeps pipeline full, reduces latency

### Reuse Framebuffer Objects
**How**: Create FBOs once, bind swapchain textures each frame  
**Benefit**: Avoid allocation/deallocation overhead

### Match Native Resolution
**How**: Use swapchain recommended dimensions (1764x1960 for Quest 3)  
**Benefit**: Avoid scaling overhead in compositor

---

## Known Limitations

### 1. Registration Requirement
**Issue**: SteamVR requires `.vrmanifest` registration  
**Impact**: Loading screen blocks visibility even with perfect rendering  
**Workaround**: None - registration is mandatory

### 2. Python.exe Not Auto-Recognized
**Issue**: SteamVR generates dynamic keys for unknown executables  
**Impact**: Can't register `python.exe` directly  
**Workaround**: Use dedicated launcher or register venv python

### 3. No Native Linux Support
**Issue**: pyopenxr has incomplete Linux bindings  
**Impact**: Can't run on SteamVR Linux  
**Workaround**: Windows only for now

### 4. Limited Action Input
**Issue**: Only head pose action implemented  
**Impact**: No controller input yet  
**Future**: Add controller actions to `actions.json`

---

## Success Criteria Checklist

When VR is working correctly, you should see:

- ✅ OpenXR instance creation succeeds
- ✅ Session reaches FOCUSED state within 2-3 seconds
- ✅ locate_views returns POSITION_VALID flags
- ✅ Swapchain format is LINEAR (0x8058 or 0x881A)
- ✅ Zero dropped frames in SteamVR stats
- ✅ Projection layers submitted when tracking available
- ✅ Quad fallback layer when tracking unavailable
- ✅ Layer flags include BLEND + CHROMATIC_ABERRATION
- ✅ No empty layer submissions to end_frame()
- ✅ Action manifest environment variable set
- ✅ SteamVR logs show "Transition to VRApplication_Scene"
- ✅ Loading screen exits within 1-2 seconds
- ✅ Rendered content visible in headset

**Current Status**: First 10 items ✅, last 2 items ❌ (blocked on registration)

---

## References

### OpenXR Specification
- Space Creation: https://registry.khronos.org/OpenXR/specs/1.0/html/xrspec.html#spaces
- Layer Submission: https://registry.khronos.org/OpenXR/specs/1.0/html/xrspec.html#composition-layers
- Frame Loop: https://registry.khronos.org/OpenXR/specs/1.0/html/xrspec.html#frame-loop

### SteamVR Documentation
- App Manifests: https://github.com/ValveSoftware/openvr/wiki/Application-Manifests
- Action Manifests: https://github.com/ValveSoftware/openvr/wiki/Action-manifest

### pyopenxr Documentation
- GitHub: https://github.com/cmbruns/pyopenxr
- Examples: https://github.com/cmbruns/pyopenxr/tree/main/examples

---

**Document Version**: 1.0  
**Last Updated**: November 2, 2025
