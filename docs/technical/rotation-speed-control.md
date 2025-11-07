# Spiral Rotation Speed Control

## Overview
Added a controllable rotation speed parameter for the MesmerLoom spiral, allowing users to adjust how fast the spiral rotates from completely stopped (0.0x) to very fast (2.0x speed).

## Implementation Details

### 1. Backend (SpiralDirector)
**File**: `mesmerglass/mesmerloom/spiral.py`

- Added `rotation_speed` parameter (default: 0.5)
- Added `set_rotation_speed(speed: float)` method with safety clamping (0.5-4.0 range)
- Range: 0.5 = normal speed, 4.0 = maximum speed (8x faster than normal)

### 2. Shader Integration
**Files**: 
- `mesmerglass/mesmerloom/raw_window.py`
- `mesmerglass/mesmerloom/raw_qwindow.py`

**Changes**:
- Replaced hardcoded `rotation_speed = 0.5` with uniform `u_rotation_speed`
- Added uniform to both vertex/fragment shaders
- Shader calculation: `spiral_angle = angle + u_time * u_rotation_speed`
- Uniform is set from `director.rotation_speed` each frame

### 3. UI Control (MesmerLoom Tab)
**File**: `mesmerglass/ui/panel_mesmerloom.py`

**Added Components**:
- **Slider**: `sld_rotation_speed` (horizontal slider, range 50-400)
  - Maps to 0.5-4.0x speed (value/100.0)
  - Default value: 50 (0.5x speed)
  - Located in "General" section below Spiral Width

- **Signal**: `rotationSpeedChanged = pyqtSignal(float)`
  - Emits speed value (0.0-2.0) when slider changes

- **Slot**: `_on_rotation_speed(value: int)`
  - Converts slider value to float speed
  - Calls `director.set_rotation_speed(speed)`
  - Emits `rotationSpeedChanged` signal

### 4. UI Layout
The rotation speed slider is positioned in the MesmerLoom tab:

```
General Group:
  - Opacity (renamed from Intensity)
  - Blend Mode
  - Spiral Type
  - Spiral Width
  - Rotation Speed  ← NEW
```

## Speed Reference
| Slider Value | Speed Multiplier | Description |
|--------------|------------------|-------------|
| 50           | 0.5x             | Default/Normal (minimum) |
| 75           | 0.75x            | Slow-medium |
| 100          | 1.0x             | Medium |
| 150          | 1.5x             | Medium-fast |
| 200          | 2.0x             | Fast |
| 300          | 3.0x             | Very fast |
| 400          | 4.0x             | Maximum speed |

## Testing

### Quick Test (No Visual)
```powershell
.\.venv\Scripts\python.exe test_rotation_speed.py
```
Tests:
- Control exists and is accessible
- Value range works correctly (0-200)
- Director.rotation_speed updates properly
- Tests speeds: 0.1x, 0.5x, 1.5x, 0.0x

### Visual Test (Launches Spiral)
```powershell
.\.venv\Scripts\python.exe test_rotation_speed_visual.py
```
Tests:
- Launches actual spiral window
- Demonstrates speed progression: 0.1x → 0.3x → 0.5x → 1.0x → 2.0x
- Shows real-time speed changes
- Allows manual slider testing

## Use Cases

### 1. Standard Rotation
Default 0.5x provides the classic mesmerizing rotation - this is the minimum speed.

### 2. Medium Effect
Speeds of 1.0-1.5x create moderate rotation patterns.

### 3. Intense/Fast Effect
Speeds of 2.0-4.0x create intense, rapid rotation patterns.

### 4. Device Synchronization (Future)
The `rotationSpeedChanged` signal can be connected to device control systems to synchronize rotation speed with haptic patterns or other outputs.

## Safety & Limits

- **Minimum**: 0.5x (normal rotation - slider at 50)
- **Maximum**: 4.0x (very fast - slider at 400)
- **Default**: 0.5x (established baseline)
- **Clamping**: Automatic safety clamp prevents values outside 0.5-4.0 range

## Integration Points

The rotation speed control integrates with:
1. **Shader Rendering**: Real-time uniform updates
2. **SpiralDirector**: Centralized spiral parameter management  
3. **UI System**: Standard PyQt6 signal/slot pattern
4. **Future Device Control**: Signal available for external systems

## Notes

- Rotation speed is independent of intensity/opacity
- Changes take effect immediately (no interpolation)
- Speed is preserved when switching spiral types/widths
- Works with all spiral types (1-7) and all spiral widths (60-360°)
