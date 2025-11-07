# MesmerLoom Spiral Overlay

## Trance 7-Type Spiral System

MesmerLoom now implements the complete Trance spiral system with 7 distinct mathematical spiral types and cone-intersection depth effects.

### Spiral Types (1-7)

Each spiral type uses a different mathematical function to create unique visual patterns:

| Type | Name | Function | Visual Effect |
|------|------|----------|---------------|
| 1 | Logarithmic | `f(r) = log(r)` | Tighter at center, rapidly expanding outward |
| 2 | Quadratic | `f(r) = r²` | Accelerating expansion from center |
| 3 | Linear | `f(r) = r` | **Default** - Uniform spacing (Archimedean spiral) |
| 4 | Square Root | `f(r) = sqrt(r)` | Decelerating expansion, tighter at edges |
| 5 | Inverse Spike | `f(r) = -|r - 1|` | Central spike at r=1, symmetric |
| 6 | Power | Complex dual-zone | Dramatic power-law transition at r=1 |
| 7 | Modulated | `f(r) = r + ripple(r)` | Adds periodic 0.2-unit ripples |

**GLSL Implementation** (from `spiral.frag`):
```glsl
float spiral1(float r) { return log(r); }
float spiral2(float r) { return r * r; }
float spiral3(float r) { return r; }
float spiral4(float r) { return sqrt(r); }
float spiral5(float r) { return -abs(r - 1.0); }
float spiral6(float r) {
    float r1 = r * 1.2;
    float r2 = (1.5 - 0.5 * r) * 1.2;
    return r < 1.0 ? pow(r1, 6.0) : -pow(r2, 6.0);
}
float spiral7(float r) {
    float m = mod(r, 0.2);
    m = m < 0.1 ? m : 0.2 - m;
    return r + m * 3.0;
}
```

### Spiral Width (Arm Count)

The spiral width parameter controls how many degrees each arm spans:

| Width | Arms | Description |
|-------|------|-------------|
| 60° | 6 arms | **Default** - Dense, rapid rotation |
| 72° | 5 arms | Pentagonal symmetry |
| 90° | 4 arms | Quadrant divisions |
| 120° | 3 arms | Triangular symmetry |
| 180° | 2 arms | Binary division |
| 360° | 1 arm | Single continuous spiral |

### Rotation Formula

The exact Trance rotation formula ensures consistent rotation speeds across different spiral widths:

```python
phase += amount / (32 * sqrt(spiral_width))
```

**Examples** (at 60fps):
- `amount=1.0, width=60°` → ~4.1 seconds per rotation
- `amount=2.0, width=60°` → ~2.1 seconds per rotation  
- `amount=4.0, width=60°` → ~1.0 second per rotation

**Typical rotation amounts**:
- Visual programs: 1.0 - 4.0
- Slow cycles: 2.0
- Fast cycles: 4.0
- Accelerating: 1.0 + (intensity × 2.75)

### Cone Intersection (3D Depth Effect)

The shader uses **ray-cone intersection** to create a tunnel depth effect where the spiral appears to recede into the distance:

**How it works**:
1. Cast ray from eye position through near plane
2. Calculate intersection with cone defined by far plane
3. Project intersection back to near plane
4. Creates natural perspective distortion

**Parameters**:
- `near_plane = 1.0` (fixed, controls field of view)
- `far_plane = 5.0` (controls zoom depth intensity)
- `eye_offset = 0.0` (for VR/stereoscopic, normally zero)

**Visual effect**:
- Center of screen = closest point on spiral
- Edges of screen = spiral receding into distance
- Creates compelling "tunnel" illusion

**GLSL Implementation** (simplified):
```glsl
vec2 cone_intersection(vec2 aspect_position) {
    vec3 cone_origin = vec3(0.0, 0.0, far_plane);
    vec3 cone_axis = vec3(0.0, 0.0, -1.0);
    float cone_angle = atan(sqrt(max_width² + 1.0) / (far_plane - near_plane));
    
    vec3 ray_origin = vec3(eye_offset, 0.0, 0.0);
    vec3 ray_vector = normalize(vec3(aspect_position, near_plane));
    
    // Solve quadratic for ray-cone intersection...
    float t = solve_quadratic(a, b, c);
    vec3 intersection = ray_origin + t * ray_vector;
    
    // Project back to near plane
    return near_plane * intersection.xy / intersection.z;
}
```

### UI Controls

**MesmerLoom Tab** in launcher:
- **Opacity**: Overall spiral visibility/intensity (0-100%)
- **Blend Mode**: Multiply, Screen, or SoftLight blending
- **Spiral Type**: Dropdown with 7 spiral types
- **Spiral Width**: Dropdown with 6 width options (60-360°)
- **Rotation Speed**: Slider to control rotation speed (0.0-2.0x) - [See details](rotation-speed-control.md)
- **Arm Color**: Color picker for spiral arms
- **Gap Color**: Color picker for gaps between arms

**Programmatic Control**:
```python
from mesmerglass.mesmerloom.spiral import SpiralDirector

director = SpiralDirector()
director.set_spiral_type(3)         # Linear (default)
director.set_spiral_width(60)       # 60 degrees per arm
director.set_rotation_speed(0.5)    # 0.5x speed (default)
director.rotate_spiral(2.0)         # Rotate using Trance formula
director.change_spiral()            # Randomly change type/width
```

### CLI Testing

Test specific spiral types:
```bash
python -m mesmerglass spiral-type --type 1 --width 60 --duration 5
python -m mesmerglass spiral-type --type 7 --width 180 --duration 10
```

**Command options**:
- `--type {1-7}`: Select spiral type (1=log, 2=quad, 3=linear, ...)
- `--width {360,180,120,90,72,60}`: Spiral width in degrees
- `--rotation FLOAT`: Rotation speed amount (default: 2.0)
- `--duration FLOAT`: Test duration in seconds
- `--intensity FLOAT`: Intensity 0-1
- `--screen INT`: Target screen index

---

## Troubleshooting: Secondary Screen Black

If the spiral overlay is black or not rendering on a secondary display:

1. Enable trace logging: `MESMERGLASS_SPIRAL_TRACE=1`
2. Check logs for `[spiral.trace]` entries for both screens. Look for geometry, context, framebuffer, and visibility.
3. Confirm that the secondary screen is listed in `[launcher] Available screens:` and `[spiral.trace] Assigned to screen index ...`.
4. Check for errors in `LoomCompositor.__init__`, `showEvent`, and `initializeGL` for the secondary window.
5. If geometry is incorrect, verify that `setScreen` and `setGeometry` are called with the correct QScreen and QRect.
6. If context/fb is missing, try running with `MESMERGLASS_SPIRAL_DEBUG_SURFACE=1` to disable translucency/click-through.
7. If still black, try swapping screen indices or running with only the secondary display enabled.
8. Report logs and system details for further diagnosis.

**Note:** Some Windows/Qt/driver combinations may fail to create a valid OpenGL context on non-primary screens. The logs will help pinpoint if the compositor is initializing, if the framebuffer/context is valid, and if the window is visible/fullscreen.
## Logging & Diagnostics

To enable verbose spiral trace logging (for debugging multi-display or context issues), set the environment variable:

	MESMERGLASS_SPIRAL_TRACE=1

When enabled, detailed logs from the OpenGL compositor (LoomCompositor) will be emitted for each window and frame. By default, these logs are suppressed to avoid log spam.


## Overview
MesmerLoom is the MesmerGlass visuals engine providing a GPU spiral overlay composited over video. It consists of a SpiralDirector (parameter evolution + intensity scaling + flip choreography) and an OpenGL compositor (fullscreen triangle shader pipeline). The legacy `mesmerglass.engine.spiral` path now re-exports the MesmerLoom implementation and emits a `DeprecationWarning`.

### Enhanced Anti-Aliasing
The spiral fragment shader features advanced anti-aliasing to eliminate visual artifacts, particularly the grainy/pixelated appearance at low opacity or intensity:

- **Multi-sample anti-aliasing (MSAA)**: Configurable supersampling with 1, 4, 9, or 16 samples per pixel
- **Adaptive edge detection**: Uses `fwidth()` derivatives for automatic edge smoothing
- **Distance-based filtering**: Edge width scales with radial distance for consistent quality
- **High-frequency artifact reduction**: Additional smoothing in high-gradient areas

### Enhanced Precision
The shader implements multiple precision levels to eliminate floating-point artifacts and moiré patterns:

- **High-precision constants**: Uses extended-precision π (3.1415926535897932...) for accurate calculations
- **Angle normalization**: Prevents floating-point drift in polar coordinate calculations
- **Precision-based clamping**: Adaptive value clamping based on precision level
- **Configurable precision levels**: Low/medium/high precision for compatibility vs. quality trade-offs

The `uSuperSamples` uniform controls anti-aliasing:
- `1`: No anti-aliasing (fastest)
- `4`: 2x2 supersampling (default, balanced quality/performance)
- `9`: 3x3 supersampling (high quality)
- `16`: 4x4 supersampling (maximum quality)

The `uPrecisionLevel` uniform controls precision:
- `0`: Low precision (fastest, may have artifacts on older hardware)
- `1`: Medium precision (balanced, default)
- `2`: High precision (maximum quality, may be slower)

### OpenGL State Management

To prevent visual artifacts (dotted patterns, feathered effects, graininess), the compositor configures specific OpenGL states:

**Disabled States:**
- `GL_DITHER` - Prevents ordered dithering patterns that appear as white dot grids
- `GL_SAMPLE_ALPHA_TO_COVERAGE` - Prevents alpha-to-coverage artifacts with MSAA  
- `GL_POLYGON_SMOOTH` - Disables legacy polygon smoothing that can cause artifacts
- `GL_DEPTH_TEST` - Disabled for overlay rendering (no depth buffer needed)

**Enabled States:**
- `GL_BLEND` - Proper alpha blending for overlay transparency
- `GL_MULTISAMPLE` - MSAA anti-aliasing support (1x, 4x, 9x, 16x samples)

**Blending Configuration:**
- Source: `GL_SRC_ALPHA`
- Destination: `GL_ONE_MINUS_SRC_ALPHA`
- Standard alpha blending for proper overlay compositing

### Debug Mode
Use the `--debug-gl-state` CLI flag to inspect OpenGL state configuration:

```bash
python -m mesmerglass spiral-test --debug-gl-state --duration 3 --intensity 0.2
```

This displays the current state of all relevant OpenGL flags and blend function settings.
- `0`: Low precision (maximum compatibility)
- `1`: Medium precision (balanced)
- `2`: High precision (default, maximum quality)

Performance impact is minimal (typically <2% even at maximum settings) due to efficient GPU implementation.

## Uniforms
| Name | Description | Typical / Range | Notes |
|------|-------------|-----------------|-------|
| uPhase | Running phase accumulator | grows monotonically | Wraps at large value; used for time functions |
| uBaseSpeed | Base spiral rotation speed (cycles/s) | 0.09–0.14 | Intensity mapped |
| uEffectiveSpeed | Base + wobble + flip boost | <=0.18 cap | Safety capped |
| uBarWidth | Normalized bar (arm) width | 0.36–0.62 (clamped) | Breathing & intensity scaled |
| uTwist | Twist / coil tightness | 0.06–0.14 (default span) | Intensity scaled |
| uSpiralOpacity | Overlay opacity | 0.55–0.95 (upper half used) | Intensity scaled |
| uContrast | Contrast multiplier | 0.85–1.25 (clamped) | Intensity adds up to +0.18 |
| uVignette | Vignette amount | 0.22–0.38 | Intensity scaled |
| uChromaticShift | Pixel radius color shift | 0.0–0.3 | Intensity scaled |
| uFlipWaveRadius | Wavefront position | -0.2 → 1.2 | Animates during flip |
| uFlipState | 0 idle / 1 flipping | {0,1} | Controls boost + radius prog |
| uIntensity | Current intensity scalar | 0.0–1.0 | UI slider (slew-limited) |
| uSafetyClamped | Flag if any clamp applied this frame | {0,1} | Diagnostic |
| uSuperSamples | Anti-aliasing samples | {1,4,9,16} | Configurable MSAA level |
| uPrecisionLevel | Floating-point precision | {0,1,2} | 0=low, 1=medium, 2=high |

## Intensity Scaling Map
| Parameter | Intensity 0 | Intensity 1 | Notes |
|-----------|-------------|-------------|-------|
| Base Speed (uBaseSpeed) | 0.09 cps | 0.14 cps | Linear lerp |
| Wobble Amplitude | 0.006 cps | 0.020 cps | Adds sinusoidal mod |
| Twist (target) | 0.06 | 0.14 | Lerp |
| Breathing Cycle | 140 s | 70 s | Inverse scaling |
| Bar Width Breathing Amplitude (internal) | 0.04 | 0.10 | Applied around midpoint |
| Opacity Target | Mid of [0.55,0.95] | Upper end | Uses 0.5+0.5*I mapping |
| Contrast Boost | +0.00 | +0.18 | Added then clamped 0.85–1.25 |
| Vignette | 0.22 | 0.38 | Lerp |
| Chromatic Shift | 0.00 | 0.30 | Lerp |
| Flip Period (avg) | 240 s | 120 s | Jitter ±45 s |
| Flip Wave Duration | 40 s | 22 s | Lerp inverse |

## Inside-Out Flip Wave
- Trigger cadence: every ~3 min (240→120 s intensity mapped) ±45 s jitter.
- Wavefront radius animates: `uFlipWaveRadius -0.2 → 1.2` over wave duration (~22–40 s depending on intensity).
- Wave width soft edge: ~`uFlipWaveWidth` conceptual (~0.08) encoded via shader smoothstep logic.
- During flip: temporary speed boost (~+0.03 cps) inside active region (simplified: uniform additive boost).
- After completion: radius resets to -0.2 and state returns to idle.

## Safety Clamps
| Quantity | Clamp |
|----------|-------|
| Base/Eff Speed | <= 0.18 cps (effective) |
| Bar Width | [0.36, 0.62] |
| Opacity | [0.55, 0.95] |
| Contrast | [0.85, 1.25] |
| Chromatic Shift | <= 0.30 |

### Per-Frame Slew Caps (@ ~60 fps)
| Parameter | Δ Max |
|-----------|-------|
| Bar Width | 0.0016 |
| Opacity | 0.003 |
| Contrast | 0.004 |
| Base Speed | 0.0015 |
| Chromatic Shift | 0.01 (approx) |

Intensity changes engage a short cooldown window applying tighter (½) slew limits.

## Blend Modes (Conceptual Formulas)
Let Cb = underlying video color, Cs = spiral color, a = opacity. The shader currently applies a composite consistent with these modes:
- Multiply: `out = mix(Cb, Cb * Cs, a)`
- Screen: `out = mix(Cb, 1 - (1-Cb)*(1-Cs), a)`
- SoftLight (approx): `out = mix(Cb, softlight(Cb, Cs), a)` where `softlight` is a polynomial approximation.

## Render Scale
Optional offscreen scale factors to trade clarity vs performance:
- 1.00 (full resolution)
- 0.85
- 0.75
The spiral pass renders at scaled size then upscales to window size.

## Troubleshooting Visual Artifacts

### Dotted/Grid Patterns
If you see white dot grids or ordered dithering patterns:
1. Verify OpenGL state with `--debug-gl-state` flag
2. Check that `GL_DITHER: 0` (should be disabled)
3. Ensure proper GPU drivers are installed

### Feathered/Grainy Effects
For blurry or grainy spiral edges at low intensity:
1. Increase `--supersampling` from 4 to 9 or 16
2. Set `--precision high` for maximum floating-point accuracy
3. Check that `GL_SAMPLE_ALPHA_TO_COVERAGE: 0` (should be disabled)

### Performance Issues
If spiral rendering is slow or choppy:
1. Reduce `--supersampling` from 16 to 4 or 1
2. Lower `--precision` from high to medium or low
3. Use `--render-scale 0.85` or `0.75` to reduce resolution

### Debug Information
```bash
# Full state inspection
python -m mesmerglass spiral-test --debug-gl-state --duration 3 --intensity 0.2

# Test different precision levels
python -m mesmerglass spiral-test --precision low --duration 2
python -m mesmerglass spiral-test --precision high --supersampling 16 --duration 2
```

## Sanity Commands
```bash
# Launch full GUI
python -m mesmerglass run

# Headless spiral test (bounded loop) – exits 0 on success or 77 if GL unavailable
python -m mesmerglass spiral-test --duration 3 --intensity 0.6 --blend multiply --render-scale 0.85

# Run tests
python -m mesmerglass test-run fast
pytest -q
```

## Legacy Shim
`mesmerglass.engine.spiral` re-exports the MesmerLoom spiral and emits a `DeprecationWarning` on import. Update imports to `mesmerglass.mesmerloom.spiral` going forward.
