# OpenVR Integration - Getting Started

## Quick Start

The VR system now supports OpenVR as the primary backend with OpenXR as fallback.

### Installation

```bash
# Install OpenVR bindings
pip install openvr
```

### Usage

The VR system automatically selects the best available backend:

```python
from mesmerglass.vr import VrBridge, VR_BACKEND

# Check which backend is loaded
print(f"Using VR backend: {VR_BACKEND}")  # 'openvr', 'openxr', or 'mock'

# Use VrBridge as normal
bridge = VrBridge(enabled=True)
if bridge.start():
    # VR initialized successfully
    bridge.submit_frame_from_fbo(fbo_id, width, height)
else:
    # Running in mock mode
    pass

# Clean shutdown
bridge.shutdown()
```

### Environment Variables

Control backend selection:

```bash
# Force OpenVR (fail to mock if unavailable)
export MESMERGLASS_VR_BACKEND=openvr

# Force OpenXR legacy (fail to mock if unavailable)
export MESMERGLASS_VR_BACKEND=openxr

# Auto-detect (default: try openvr → openxr → mock)
export MESMERGLASS_VR_BACKEND=auto
```

## Current Status

### ✅ Completed
- [x] Created OpenVR bridge skeleton (`vr_bridge_openvr.py`)
- [x] Created OpenVR utilities module (`openvr_utils.py`)
- [x] Updated `vr/__init__.py` with conditional backend loading
- [x] Created comprehensive migration plan document
- [x] Created initial tests for OpenVR bridge
- [x] Maintained API compatibility with existing `VrBridge`

### 🚧 In Progress
- [ ] Import working OpenVR implementation from other project
- [ ] Test basic initialization with SteamVR
- [ ] Implement proper FBO → texture extraction
- [ ] Implement per-eye rendering (currently duplicates same image)

### 📋 Planned
- [ ] Update existing VR tests for OpenVR
- [ ] Add comprehensive OpenVR integration tests
- [ ] Performance benchmarking vs OpenXR
- [ ] Documentation updates
- [ ] Move OpenXR code to legacy/

## File Structure

```
mesmerglass/vr/
├── __init__.py                    # Backend selection logic ✅
├── vr_bridge_openvr.py           # New OpenVR implementation ✅
├── openvr_utils.py               # OpenVR helper functions ✅
├── vr_bridge.py                  # Legacy OpenXR implementation
├── offscreen.py                  # Offscreen rendering utilities
└── registration/
    └── actions.json              # SteamVR action manifest

docs/migration/
└── openxr-to-openvr-migration-plan.md   # Detailed migration plan ✅

mesmerglass/tests/
├── test_openvr_bridge.py         # OpenVR-specific tests ✅
├── test_vr_formats.py            # Format selection tests (needs update)
├── test_vr_handles.py            # Handle validation tests (needs update)
└── test_vr_toggle.py             # Enable/disable tests
```

## Next Steps

### 1. Import Working Code
Copy your working OpenVR implementation from the other project:
- Look for initialization code
- Frame submission logic
- Texture handling
- Error management

### 2. Test with SteamVR
```bash
# Start SteamVR
# Run test
python -m pytest mesmerglass/tests/test_openvr_bridge.py -v
```

### 3. Integration Testing
```bash
# Test with launcher
export MESMERGLASS_VR_BACKEND=openvr
python run.py

# Test with CLI
python -m mesmerglass vr-render --help
```

## Key Implementation Points

### Texture Submission
The main work is in `submit_frame_from_fbo()`:

```python
def submit_frame_from_fbo(self, source_fbo: int, src_w: int, src_h: int):
    # 1. Extract texture from FBO
    texture_id = get_fbo_color_texture(source_fbo)
    
    # 2. Set up OpenVR texture structs
    self._left_texture.handle = texture_id
    self._right_texture.handle = texture_id  # TODO: separate eyes
    
    # 3. Submit to compositor
    self._compositor.submit(openvr.Eye_Left, self._left_texture)
    self._compositor.submit(openvr.Eye_Right, self._right_texture)
    
    # 4. Signal frame complete
    self._compositor.postPresentHandoff()
```

### Per-Eye Rendering (Future)
For proper stereoscopic rendering:
1. Query eye-to-head transforms from VR system
2. Render scene twice with different view matrices
3. Submit different textures for each eye

### Error Handling
OpenVR errors are more straightforward than OpenXR:
- `VRCompositorError_None` = success
- Other values = specific error codes
- Use `get_openvr_error_string()` for diagnostics

## Troubleshooting

### "OpenVR not available"
- Install: `pip install openvr`
- Ensure SteamVR is installed
- Check that SteamVR is running (doesn't need to be in VR mode)

### "Failed to initialize OpenVR system"
- Start SteamVR first
- Check that your headset is connected
- Try `vr_test.exe` from SteamVR tools to verify setup

### "Invalid texture" error
- Ensure FBO is properly bound and has color attachment
- Check texture format (prefer GL_RGBA8 or GL_RGBA16F)
- Verify OpenGL context is current during submission

### "Application does not have focus"
- OpenVR may reject frames if app isn't focused
- This is normal during development
- Frame submission will resume when focus returns

## Testing Checklist

- [ ] Import succeeds when openvr not installed (mock mode)
- [ ] Import succeeds when openvr installed
- [ ] Initialization succeeds with SteamVR running
- [ ] Initialization fails gracefully without SteamVR
- [ ] Frame submission works (visible in headset)
- [ ] Shutdown is clean (no crashes)
- [ ] Multiple init/shutdown cycles work
- [ ] Mock mode works correctly
- [ ] Backend selection via env var works
- [ ] Performance is acceptable (60fps+ target)

## Reference

- **Migration Plan:** `docs/migration/openxr-to-openvr-migration-plan.md`
- **OpenVR Docs:** https://github.com/ValveSoftware/openvr/wiki
- **pyopenvr:** https://github.com/cmbruns/pyopenvr
- **SteamVR:** https://partner.steamgames.com/doc/features/steamvr

---

**Status:** 🚧 Initial setup complete, ready for working code import  
**Updated:** November 3, 2025
