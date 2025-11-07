# OpenXR → OpenVR Migration Plan

## Overview

**Goal:** Replace the OpenXR-based VR system with OpenVR (pyopenvr) for better compatibility with SteamVR.

**Current State:** OpenXR implementation with complex fallback logic and compatibility issues  
**Target State:** Clean OpenVR implementation using pyopenvr bindings

---

## Current VR Architecture

### File Structure
```
mesmerglass/vr/
├── __init__.py              # Module exports
├── vr_bridge.py            # Main VrBridge class (2995 lines)
├── offscreen.py            # Offscreen rendering utilities
└── registration/           # SteamVR action manifest
    └── actions.json
```

### Current Implementation (vr_bridge.py)

**Key Components:**
1. **OpenXR Import Logic** (Lines 40-96)
   - Multiple fallback import attempts
   - `openxr`, `pyopenxr.openxr`, `pyopenxr`, `xr` packages
   - Feature detection for required classes

2. **Space Creation Helpers** (Lines 104-225)
   - Identity pose constants
   - Fallback order: LOCAL → STAGE → VIEW
   - Robust handle validation
   - SteamVR compositor layer flags

3. **VrBridge Class** (Lines 226+)
   - Initialization with mock fallback
   - Session management
   - Swapchain creation
   - Frame submission

**Usage Points:**
- `mesmerglass/ui/launcher.py` (lines 53, 1135-1147)
- `mesmerglass/cli.py` (lines 2180-2204)

**Test Files:**
- `mesmerglass/tests/test_vr_formats.py`
- `mesmerglass/tests/test_vr_handles.py`
- `mesmerglass/tests/test_vr_toggle.py`

---

## OpenVR Target Architecture

### pyopenvr Package
- **Package:** `openvr` (pip install openvr)
- **Bindings:** Direct SteamVR API bindings
- **Advantages:**
  - Simpler API than OpenXR
  - Better SteamVR integration
  - Proven stability
  - Direct compositor access

### Key OpenVR Concepts

#### 1. Initialization
```python
import openvr

# Initialize VR system
vr_system = openvr.init(openvr.VRApplication_Scene)

# Get compositor for frame submission
compositor = openvr.VRCompositor()
```

#### 2. Tracking Space
```python
# OpenVR uses HmdMatrix34_t for poses
# Coordinate system: -Z forward, +Y up, +X right
```

#### 3. Eye Rendering
```python
# Get render target size per eye
left_w, left_h = vr_system.getRecommendedRenderTargetSize()

# Create textures for each eye
texture = openvr.Texture_t()
texture.handle = gl_texture_id
texture.eType = openvr.TextureType_OpenGL
texture.eColorSpace = openvr.ColorSpace_Gamma

# Submit frames
compositor.submit(openvr.Eye_Left, texture)
compositor.submit(openvr.Eye_Right, texture)
```

---

## Migration Strategy

### Phase 1: Preparation (Create Parallel Implementation)

**Goal:** Create new OpenVR bridge alongside existing OpenXR code

#### Files to Create:
1. **`mesmerglass/vr/vr_bridge_openvr.py`** - New OpenVR implementation
   - Class: `VrBridgeOpenVR`
   - Same public API as current `VrBridge`
   - Methods: `start()`, `submit_frame_from_fbo()`, `shutdown()`

2. **`mesmerglass/vr/openvr_utils.py`** - OpenVR helper functions
   - Eye texture setup
   - Coordinate system conversions
   - Error handling

#### API Compatibility Layer:
```python
class VrBridgeOpenVR:
    """OpenVR-based VR bridge (SteamVR native)."""
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._mock = False
        self._vr_system = None
        self._compositor = None
        self._textures = {}  # eye → Texture_t
        self._logger = logging.getLogger(__name__)
    
    def start(self) -> bool:
        """Initialize OpenVR session and compositor."""
        pass
    
    def submit_frame_from_fbo(self, source_fbo: int, src_w: int, src_h: int) -> None:
        """Submit rendered frame to VR compositor."""
        pass
    
    def shutdown(self) -> None:
        """Clean shutdown of OpenVR session."""
        pass
```

---

### Phase 2: Implementation Details

#### Key Differences to Handle:

**1. Initialization**
```python
# OpenXR (Current)
instance = xr.create_instance(...)
system_id = xr.get_system(...)
session = xr.create_session(...)

# OpenVR (Target)
vr_system = openvr.init(openvr.VRApplication_Scene)
compositor = openvr.VRCompositor()
```

**2. Frame Submission**
```python
# OpenXR (Current)
xr.wait_frame()
xr.begin_frame()
# ... render to swapchain images
xr.end_frame(layers)

# OpenVR (Target)
# ... render to FBO
texture = openvr.Texture_t()
texture.handle = fbo_texture_id
texture.eType = openvr.TextureType_OpenGL
compositor.submit(openvr.Eye_Left, texture)
compositor.submit(openvr.Eye_Right, texture)
compositor.postPresentHandoff()
```

**3. Coordinate Systems**
```python
# OpenXR uses right-handed: +Y up, -Z forward
# OpenVR uses right-handed: +Y up, -Z forward
# (Same! No conversion needed)
```

**4. Texture Formats**
```python
# OpenXR preferred: GL_SRGB8_ALPHA8
# OpenVR preferred: GL_RGBA8 or GL_RGBA16F
# Need to update format selection in tests
```

---

### Phase 3: Integration Points

#### Files to Modify:

**1. `mesmerglass/vr/__init__.py`**
```python
# Add conditional import
try:
    from .vr_bridge_openvr import VrBridgeOpenVR as VrBridge
    VR_BACKEND = 'openvr'
except ImportError:
    from .vr_bridge import VrBridge  # Fallback to OpenXR
    VR_BACKEND = 'openxr'

__all__ = ["VrBridge", "VR_BACKEND"]
```

**2. `mesmerglass/ui/launcher.py`** (lines 1135-1147)
```python
def _init_vr(self):
    """Initialize VrBridge according to env flags."""
    try:
        from ..vr import VrBridge, VR_BACKEND
        self.vr_bridge = VrBridge(enabled=True)
        # ... existing code
        logging.getLogger(__name__).info(
            "[vr] VrBridge initialized (backend=%s, mock=%s)", 
            VR_BACKEND, 
            getattr(self.vr_bridge, "_mock", True)
        )
```

**3. `mesmerglass/cli.py`** (lines 2192-2204)
```python
# VR rendering command
from .vr import VrBridge, VR_BACKEND
logging.getLogger(__name__).info("[vr] Using backend: %s", VR_BACKEND)
bridge = VrBridge(enabled=True)
```

---

### Phase 4: Testing Strategy

#### Unit Tests to Update:

**1. `test_vr_formats.py`**
- Update expected format from `0x8C43` (GL_SRGB8_ALPHA8) to `0x8058` (GL_RGBA8)
- Test OpenVR texture format selection
- Verify both EYE_LEFT and EYE_RIGHT submission

**2. `test_vr_handles.py`**
- Update handle validation for OpenVR types
- Test `vr_system` handle validity
- Test `compositor` handle validity

**3. `test_vr_toggle.py`**
- Verify enable/disable behavior with OpenVR
- Test mock mode fallback

#### New Tests to Create:

**1. `test_openvr_initialization.py`**
```python
def test_openvr_init_success():
    """Test OpenVR initialization succeeds when available."""
    pass

def test_openvr_init_fallback_to_mock():
    """Test graceful fallback to mock mode if OpenVR unavailable."""
    pass

def test_openvr_compositor_available():
    """Test compositor is accessible after init."""
    pass
```

**2. `test_openvr_frame_submission.py`**
```python
def test_submit_frame_both_eyes():
    """Test frame submission to left and right eyes."""
    pass

def test_submit_frame_invalid_fbo():
    """Test error handling for invalid FBO."""
    pass
```

---

### Phase 5: Cleanup & Deprecation

**Files to Deprecate:**
1. `mesmerglass/vr/vr_bridge.py` (old OpenXR implementation)
   - Move to `mesmerglass/vr/legacy/vr_bridge_openxr.py`
   - Add deprecation warning if imported

**Documentation to Update:**
1. `docs/technical/vr-setup.md` - New OpenVR setup instructions
2. `docs/migration/openxr-removal.md` - Migration notes
3. `README.md` - Update VR requirements

**Dependencies to Update:**
```toml
# requirements.txt or pyproject.toml
# REMOVE:
# openxr (or pyopenxr)

# ADD:
openvr>=1.23.0  # SteamVR bindings
```

---

## Implementation Checklist

### ✅ Pre-Migration
- [ ] Review existing OpenVR implementation from other project
- [ ] Document current VrBridge API surface
- [ ] Identify all usage points in codebase
- [ ] Create test plan for both implementations

### 📝 Phase 1: Create Parallel Implementation
- [ ] Create `vr_bridge_openvr.py` with matching API
- [ ] Create `openvr_utils.py` helper module
- [ ] Implement basic initialization in mock mode
- [ ] Add unit tests for new implementation

### 🔨 Phase 2: OpenVR Implementation
- [ ] Implement `start()` - OpenVR init
- [ ] Implement `submit_frame_from_fbo()` - Frame submission
- [ ] Implement `shutdown()` - Cleanup
- [ ] Handle errors and edge cases
- [ ] Test with actual VR headset

### 🔌 Phase 3: Integration
- [ ] Update `vr/__init__.py` with conditional import
- [ ] Add environment variable for backend selection
- [ ] Update launcher.py integration
- [ ] Update cli.py integration
- [ ] Test full application flow

### ✅ Phase 4: Testing & Validation
- [ ] Update existing VR tests
- [ ] Create new OpenVR-specific tests
- [ ] Test with SteamVR runtime
- [ ] Test fallback to mock mode
- [ ] Performance benchmarking

### 🧹 Phase 5: Cleanup
- [ ] Move old OpenXR code to legacy/
- [ ] Add deprecation warnings
- [ ] Update all documentation
- [ ] Update requirements.txt
- [ ] Remove OpenXR-specific code paths

### 📚 Phase 6: Documentation
- [ ] Write migration guide
- [ ] Update setup instructions
- [ ] Document new API
- [ ] Add troubleshooting guide

---

## Risk Mitigation

### Potential Issues:

**1. OpenVR Availability**
- **Risk:** pyopenvr package not installed
- **Mitigation:** Graceful fallback to mock mode
- **Detection:** Check `openvr` import at module load

**2. SteamVR Not Running**
- **Risk:** Runtime not available when app starts
- **Mitigation:** Mock mode with clear error message
- **Detection:** Catch `openvr.init()` exceptions

**3. GL Context Issues**
- **Risk:** Context not current during texture submission
- **Mitigation:** Verify context before submission
- **Detection:** Check GL errors after operations

**4. Breaking Changes**
- **Risk:** API changes break existing integrations
- **Mitigation:** Maintain exact same public API
- **Detection:** Run full test suite

---

## Success Criteria

### Must Have:
- ✅ VrBridge API remains unchanged (drop-in replacement)
- ✅ All existing tests pass
- ✅ Mock mode works without OpenVR installed
- ✅ Real VR mode works with SteamVR runtime
- ✅ Frame submission works for both eyes
- ✅ Clean shutdown without crashes

### Nice to Have:
- ⭐ Better performance than OpenXR
- ⭐ Simpler codebase (less fallback logic)
- ⭐ Easier setup for users
- ⭐ Better SteamVR integration
- ⭐ Support for VR overlays

---

## Timeline Estimate

**Phase 1 (Preparation):** 2-4 hours
- File structure setup
- API definition
- Test scaffolding

**Phase 2 (Implementation):** 6-10 hours
- Core OpenVR integration
- Frame submission logic
- Error handling

**Phase 3 (Integration):** 2-4 hours
- Conditional imports
- Usage point updates
- Integration testing

**Phase 4 (Testing):** 4-6 hours
- Test updates
- VR headset testing
- Bug fixes

**Phase 5 (Cleanup):** 2-3 hours
- Code cleanup
- Documentation
- Deprecation

**Total:** 16-27 hours

---

## Next Steps

1. **Review this plan** - Get approval on approach
2. **Test OpenVR import** - Verify `openvr` package works in current environment
3. **Copy working code** - Bring over OpenVR implementation from other project
4. **Create skeleton** - Set up `vr_bridge_openvr.py` with API stubs
5. **Implement start()** - Get basic initialization working
6. **Test mock mode** - Verify fallback works
7. **Implement submission** - Get frame rendering working
8. **Full integration** - Wire into launcher and test end-to-end

---

## Questions for Review

1. **Backwards Compatibility:** Should we keep OpenXR as a fallback option or do clean removal?
2. **Environment Variable:** Add `MESMERGLASS_VR_BACKEND=openxr|openvr` for testing?
3. **Mock Mode:** Keep existing mock mode or create OpenVR-specific mock?
4. **Coordinate Systems:** Any special handling needed for coordinate transforms?
5. **Texture Formats:** Prefer RGBA8 or RGBA16F for OpenVR submission?

---

## Reference Links

- **pyopenvr GitHub:** https://github.com/cmbruns/pyopenvr
- **OpenVR API Docs:** https://github.com/ValveSoftware/openvr/wiki/API-Documentation
- **SteamVR Developer:** https://partner.steamgames.com/doc/features/steamvr/developing

---

**Status:** 📋 Planning  
**Next Action:** Review plan → Begin Phase 1  
**Created:** November 3, 2025
