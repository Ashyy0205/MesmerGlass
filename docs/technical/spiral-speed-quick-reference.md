# Spiral Speed Unification - Developer Quick Reference

## Quick Integration Guide

### 1. Set Target RPM
```python
spiral.rotation_speed = 8.0  # 8 rotations per minute
```

### 2. Update Spiral (Standard Pattern)
```python
def update_spiral(self):
    # All applications use this exact pattern
    self.spiral.rotate_spiral(4.0)  # amount ignored in unified mode
    self.spiral.update(1/60.0)      # 60 FPS timing
```

### 3. Validate Results
```python
from mesmerglass.mesmerloom.spiral_speed import validate_rpm_measurement

# Measure actual rotation speed from debug output
measured_degrees_per_sec = measure_rotation_from_debug()

# Validate accuracy
is_accurate, accuracy_pct = validate_rpm_measurement(
    rpm=8.0, 
    measured_degrees_per_sec=measured_degrees_per_sec
)
```

## Speed Reference Table

| RPM | Degrees/Second | Expected Debug Phase Increment |
|-----|----------------|---------------------------------|
| 4   | 24.0°/s        | 0.001111 per frame             |
| 8   | 48.0°/s        | 0.002222 per frame             |
| 16  | 96.0°/s        | 0.004444 per frame             |
| 24  | 144.0°/s       | 0.006667 per frame             |

## Key Files Modified

- `mesmerglass/mesmerloom/spiral_speed.py` - **NEW** unified calculator
- `mesmerglass/mesmerloom/spiral.py` - Updated `rotate_spiral()` method
- `scripts/visual_mode_creator.py` - Uses standard pattern
- `mesmerglass/ui/launcher.py` - Uses standard pattern
- `scripts/vmc_speed_test_mode.py` - Uses standard pattern

## API Reference

### Core Functions

```python
# Main conversion function
rpm_to_phase_increment(rpm: float, fps: float = 60.0) -> float

# Validation function  
validate_rpm_measurement(rpm: float, measured_degrees_per_sec: float) -> tuple[bool, float]

# Calculator class methods
SpiralSpeedCalculator.rpm_to_phase_per_frame(rpm, fps=60.0)
SpiralSpeedCalculator.rpm_to_degrees_per_second(rpm)
```

### Migration Pattern

**Before (Legacy):**
```python
# Different amounts per application, complex formula
if app == "VMC":
    spiral.rotate_spiral(2.0) 
elif app == "Launcher":
    spiral.rotate_spiral(4.0)
# Result: Inconsistent speeds
```

**After (Unified):**
```python
# Same call everywhere, RPM-based calculation
spiral.rotation_speed = target_rpm
spiral.rotate_spiral(4.0)  # amount ignored
# Result: Consistent, accurate speeds
```

## Testing Commands

```bash
# Run multi-speed validation test
.\.venv\Scripts\python.exe scripts\multi_speed_test.py

# Test single speed (VMC)
.\.venv\Scripts\python.exe scripts\vmc_speed_test_mode.py

# Manual RPM calculation test
.\.venv\Scripts\python.exe -c "
from mesmerglass.mesmerloom.spiral_speed import rpm_to_phase_increment
print(f'8 RPM = {rpm_to_phase_increment(8.0):.6f} phase/frame')
print(f'Expected: {8/60/60:.6f} phase/frame')
"
```

## Debug Output Analysis

Look for these patterns in console output:

```
[rotation_debug] phase=0.100000  # Starting phase
[rotation_debug] phase=0.104444  # +0.004444 (4 frames later)
[rotation_debug] rotation_speed=4.0

# Calculate: 0.004444 / 4 frames = 0.001111 per frame
# Verify: 4 RPM → 0.001111 expected ✓
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Speed inconsistent between apps | Different `amount` parameters | Use 4.0 for all apps |
| Too fast/slow | `rotation_speed` not in RPM | Set to actual RPM value |
| Debug shows wrong increment | Timer frequency mismatch | Ensure 60 FPS timing |

## Future Extensions

This unified pattern can be extended to:
- Zoom speed unification
- Color transition synchronization  
- Audio-visual timing coordination
- Device command timing standardization

Use the same principles:
1. Central calculation module
2. Unified API across all applications
3. Mathematical validation
4. Comprehensive testing framework