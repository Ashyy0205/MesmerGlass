# MesmerLoom Spiral Overlay
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
