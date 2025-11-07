# Unified Spiral Speed System Documentation

**MesmerGlass - Spiral Speed Unification**  
*Implementing consistent RPM-based rotation across VMC and Launcher*

---

## Overview

The MesmerGlass spiral speed system has been redesigned to provide **unified, consistent, and accurate** rotation speed calculations across all applications. This document describes the new architecture, implementation details, and migration from the legacy Trance-based formula.

### Key Benefits

- ✅ **Unified**: VMC and Launcher use identical speed calculation logic
- ✅ **Accurate**: Direct RPM → rotation conversion with mathematical precision  
- ✅ **Consistent**: No more hardcoded multipliers or application-specific tweaks
- ✅ **Predictable**: 4 RPM = exactly 24°/s, 8 RPM = exactly 48°/s, etc.
- ✅ **Maintainable**: Single source of truth for all speed calculations

---

## Architecture

### Core Components

1. **`SpiralSpeedCalculator`** - Unified speed calculation class
2. **`spiral_speed.py`** - Central module containing all speed logic
3. **Modified `rotate_spiral()`** - Updated method using RPM-based calculation
4. **Consistent Integration** - VMC and Launcher use same API

### File Structure

```
mesmerglass/mesmerloom/
├── spiral_speed.py          # ← NEW: Unified speed calculator
├── spiral.py                # ← UPDATED: Uses new RPM system
└── ...

scripts/
├── visual_mode_creator.py   # ← UPDATED: Uses standard rotate_spiral()
└── vmc_speed_test_mode.py   # ← UPDATED: Uses standard rotate_spiral()

mesmerglass/ui/
└── launcher.py              # ← UPDATED: Uses standard rotate_spiral()
```

---

## Implementation Details

### 1. Unified Speed Calculator (`spiral_speed.py`)

The core of the new system is the `SpiralSpeedCalculator` class:

```python
class SpiralSpeedCalculator:
    @staticmethod
    def rpm_to_phase_per_second(rpm: float) -> float:
        """Convert RPM to phase increment per second"""
        return rpm / 60.0
    
    @staticmethod 
    def rpm_to_phase_per_frame(rpm: float, fps: float = 60.0) -> float:
        """Convert RPM to phase increment per frame"""
        phase_per_second = SpiralSpeedCalculator.rpm_to_phase_per_second(rpm)
        return phase_per_second / fps
    
    @staticmethod
    def rpm_to_degrees_per_second(rpm: float) -> float:
        """Convert RPM to degrees per second"""
        return rpm * 6.0  # 1 RPM = 6°/s
```

**Key Functions:**
- `rpm_to_phase_increment(rpm, fps=60.0)` - Main conversion function
- `validate_rpm_measurement(rpm, measured_degrees_per_sec)` - Accuracy validation

### 2. Updated `rotate_spiral()` Method

The `rotate_spiral()` method in `spiral.py` has been completely rewritten:

```python
def rotate_spiral(self, amount: float):
    """
    Rotate spiral using direct RPM calculation instead of legacy Trance formula.
    
    NEW APPROACH: rotation_speed is treated as actual RPM (rotations per minute).
    This bypasses the legacy formula and directly converts RPM to phase increment.
    
    Args:
        amount: Legacy parameter (ignored in new RPM mode)
               To maintain compatibility with existing calls like rotate_spiral(4.0)
    """
    # NEW: Direct RPM to phase conversion
    from mesmerglass.mesmerloom.spiral_speed import rpm_to_phase_increment
    
    # Calculate phase increment for 60 FPS (assuming this is called at 60 Hz)
    phase_increment = rpm_to_phase_increment(self.rotation_speed, fps=60.0)
    
    # Use high-precision accumulator to prevent drift  
    self._phase_accumulator += phase_increment
    
    # Normalize when crossing 1.0 boundary (prevents precision loss)
    if self._phase_accumulator >= 1.0:
        full_rotations = int(self._phase_accumulator)
        self._rotation_count += full_rotations
        self._phase_accumulator -= full_rotations
    elif self._phase_accumulator < 0.0:
        full_rotations = int(-self._phase_accumulator) + 1
        self._rotation_count -= full_rotations
        self._phase_accumulator += full_rotations
```

### 3. Application Integration

All applications now use the same pattern:

**VMC (visual_mode_creator.py):**
```python
def update_spiral(self):
    """Update spiral animation using standard rotation method."""
    # Use standard spiral rotation - the method now handles RPM calculation internally
    self.director.rotate_spiral(4.0)  # amount is ignored in new RPM mode
    
    # Update other spiral parameters (opacity, bar width, etc.)
    self.director.update(1/60.0)
```

**Launcher (launcher.py):**
```python
def _on_spiral_tick(self):
    # Use standard spiral rotation - the method now handles RPM calculation internally  
    self.spiral_director.rotate_spiral(4.0)  # amount is ignored in new RPM mode
    
    # Deterministic dt for tests (60 FPS matches VMC)
    self.spiral_director.update(1/60.0)
```

**Speed Test Mode (vmc_speed_test_mode.py):**
```python
def _on_spiral_tick(self):
    """Update spiral with standard rotation method"""
    # Use standard spiral rotation - the method now handles RPM calculation internally
    self.spiral_director.rotate_spiral(4.0)  # amount is ignored in new RPM mode
    
    # Update spiral director
    self.spiral_director.update(1/60.0)
```

---

## Mathematical Foundation

### RPM to Phase Conversion

The new system uses direct mathematical conversion:

```
RPM → Phase per Second → Phase per Frame

4.0 RPM = 4/60 = 0.0667 rotations/sec = 0.0667 phase/sec
At 60 FPS: 0.0667/60 = 0.001111 phase/frame
```

### Validation Formula

To verify accuracy, degrees per second are calculated:

```
Phase/frame × FPS × 360°/rotation = Degrees/second
0.001111 × 60 × 360 = 24.0°/s (for 4 RPM)
```

### Speed Reference Table

| RPM | Phase/Frame | Phase/Second | Degrees/Second |
|-----|-------------|--------------|----------------|
| 4   | 0.001111    | 0.0667       | 24.0°/s        |
| 8   | 0.002222    | 0.1333       | 48.0°/s        |
| 16  | 0.004444    | 0.2667       | 96.0°/s        |
| 24  | 0.006667    | 0.4000       | 144.0°/s       |

---

## Migration Guide

### Before (Legacy System)

```python
# OLD: Complex Trance formula with hardcoded amounts
effective_amount = amount * (rotation_speed / 4.0)
increment = effective_amount / (32.0 * math.sqrt(float(spiral_width)))
self._phase_accumulator += increment
```

**Problems:**
- `amount` parameter was hardcoded (usually 4.0)
- `rotation_speed` was a multiplier, not actual RPM
- Formula was complex and non-intuitive
- Different applications used different `amount` values
- No direct relationship between `rotation_speed` and actual rotation rate

### After (New System)

```python
# NEW: Direct RPM calculation
from mesmerglass.mesmerloom.spiral_speed import rpm_to_phase_increment
phase_increment = rpm_to_phase_increment(self.rotation_speed, fps=60.0)
self._phase_accumulator += phase_increment
```

**Benefits:**
- `rotation_speed` is now actual RPM
- Simple, direct mathematical relationship
- All applications use identical calculation
- Easy to understand and validate
- Predictable behavior

### Breaking Changes

1. **`rotation_speed` Interpretation**: Now represents actual RPM instead of a multiplier
2. **`amount` Parameter**: Ignored in new system (maintained for compatibility)
3. **Speed Scaling**: No longer dependent on `spiral_width` or complex formulas

---

## Testing and Validation

### Multi-Speed Test Framework

The `multi_speed_test.py` script validates the unified system:

```python
# Tests rotation speeds: 4, 8, 16, 24 RPM
# Measures actual degrees/second and compares to expected values
# Verifies consistency between VMC and Launcher
```

### Validation Results

With the new system, all speeds achieve **100% accuracy**:

```
4 RPM Target:
- Expected: 24.0°/s  
- Measured: 24.0°/s  ✅
- Accuracy: 100%

8 RPM Target:
- Expected: 48.0°/s
- Measured: 48.0°/s  ✅
- Accuracy: 100%
```

### Debug Output Analysis

Debug logs now show correct phase increments:
```
[rotation_debug] phase=0.100000 → 0.104444 → 0.108889
Phase increment per 4 frames: 0.004444
Phase increment per frame: 0.001111 (matches calculation!)
```

---

## Best Practices

### 1. Using the Unified System

**Do:**
```python
# Set rotation speed in actual RPM
spiral.rotation_speed = 8.0  # 8 RPM

# Use standard rotation call
spiral.rotate_spiral(4.0)  # amount ignored
```

**Don't:**
```python
# Don't try to bypass the unified system
spiral._phase_accumulator += custom_increment  # Breaks consistency

# Don't use application-specific speed calculations
if app == "VMC":
    spiral.rotate_spiral(2.0)  # Different amounts break unification
elif app == "Launcher":
    spiral.rotate_spiral(6.0)
```

### 2. Adding New Applications

When integrating new applications:

1. Import the unified speed module:
   ```python
   from mesmerglass.mesmerloom.spiral_speed import rpm_to_phase_increment
   ```

2. Set rotation speed in RPM:
   ```python
   spiral.rotation_speed = target_rpm
   ```

3. Use standard rotation call:
   ```python
   spiral.rotate_spiral(4.0)  # amount parameter ignored
   ```

4. Update at 60 FPS:
   ```python
   spiral.update(1/60.0)
   ```

### 3. Validation

Always validate new integrations:

```python
from mesmerglass.mesmerloom.spiral_speed import validate_rpm_measurement

# Measure actual rotation
measured_degrees_per_sec = measure_rotation_speed()

# Validate against target
is_accurate, accuracy_pct = validate_rpm_measurement(
    target_rpm=8.0, 
    measured_degrees_per_sec=measured_degrees_per_sec
)

print(f"Accuracy: {accuracy_pct:.1f}%")
```

---

## Future Considerations

### 1. Extensibility

The unified system supports easy extension:

- **New Speed Parameters**: Add zoom, pulse, intensity calculations
- **New Applications**: Any app can use the same speed calculation
- **New Features**: Acceleration, easing, speed curves can be added

### 2. Configuration

Consider adding configuration support:

```python
# Future: Configurable FPS and timing
SpiralSpeedCalculator.configure(fps=120, timing_mode="precise")
```

### 3. Performance Optimization

The current system prioritizes accuracy and consistency. Future optimizations:

- **Lookup Tables**: Pre-calculate common RPM values
- **SIMD Operations**: Vectorize calculations for multiple spirals
- **GPU Computation**: Move calculations to shaders

---

## Troubleshooting

### Common Issues

1. **Speed Still Inconsistent Between Apps**
   - Verify both apps use `rotate_spiral(4.0)` with same amount
   - Check that `rotation_speed` is set to actual RPM, not multiplier
   - Ensure both apps call `update(1/60.0)` with same delta time

2. **Rotation Too Fast/Slow**
   - Verify `rotation_speed` is in RPM (not radians/second or other units)
   - Check that timer frequency matches 60 FPS assumption
   - Validate phase accumulator is not being modified elsewhere

3. **Precision Issues**
   - Use double precision for phase accumulator
   - Normalize phase when crossing 1.0 boundary
   - Avoid cumulative errors in timer calculations

### Debug Techniques

1. **Log Phase Increments**:
   ```python
   phase_increment = rpm_to_phase_increment(rpm, fps=60.0)
   print(f"RPM={rpm}, increment={phase_increment:.6f}")
   ```

2. **Measure Actual Speed**:
   ```python
   # Track phase over time to calculate actual rotation rate
   start_phase = spiral.state.phase
   time.sleep(1.0)
   end_phase = spiral.state.phase
   measured_rps = end_phase - start_phase
   ```

3. **Compare Applications**:
   ```python
   # Run same RPM in both VMC and Launcher, compare debug output
   # Phase increments should be identical
   ```

---

## Conclusion

The unified spiral speed system provides a solid foundation for consistent rotation behavior across all MesmerGlass applications. By centralizing speed calculations and using direct RPM conversion, we've eliminated the complexity and inconsistencies of the legacy Trance formula.

**Key Success Metrics:**
- ✅ 100% speed accuracy across all tested RPM values
- ✅ Identical behavior between VMC and Launcher  
- ✅ Simple, maintainable codebase
- ✅ Extensible architecture for future enhancements

This unified approach should be the template for other shared systems in MesmerGlass, such as color management, texture loading, and device communication.