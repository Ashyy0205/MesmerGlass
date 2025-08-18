# Features Documentation

## Interface Components

### Media Controls

#### Primary Video
- File selection supports MP4, MOV, AVI formats
- Opacity range: 0-100%
- Always-on-top overlay
- Click-through capability
- Multi-monitor support

#### Secondary Video
- Optional overlay layer
- Independent opacity control
- Blends with primary video
- Same format support as primary

### Text Effects

#### Text Properties
- Custom message input
- Font selection (TTF/OTF support)
- Color picker with alpha channel
- Auto-sizing to screen height
- Centered positioning

#### Effect Modes
1. **Breath + Sway**
   - Smooth opacity pulsing
   - Gentle horizontal movement
   - Configurable intensity

2. **Shimmer**
   - Rapid opacity fluctuation
   - Sparkle-like effect
   - Adjustable speed

3. **Tunnel**
   - Zoom-based animation
   - Depth perception effect
   - Scale control

4. **Subtle**
   - Minimal movement
   - Slight opacity changes
   - Low-intensity option

#### Flash Controls
- Interval timing (ms)
- Flash width duration
- Opacity boost during flash
- Screen blend mode

### Audio System

#### Dual Track Support
- Primary audio track
- Secondary audio track
- Independent volume controls
- Loop functionality
- Format support:
  - MP3 (recommended)
  - WAV
  - OGG

### Device Integration

#### Buttplug/Intiface Protocol
- WebSocket connection
- Auto-reconnection
- Safe disconnection
- Device discovery

#### Control Modes

##### Buzz on Flash
- Synced with text flashes
- Intensity control
- Duration = Flash Width
- Immediate response

##### Random Bursts
- Min/Max delay settings
- Peak intensity control
- Duration limits
- Pattern types:
  - Hit (quick pulse)
  - Wave (gradual)
  - Edge (build-up)

### Display Management

#### Multi-Monitor
- Individual display selection
- Full-screen overlay
- Independent instances
- Synchronized timing

#### Window Properties
- Always-on-top
- Click-through
- Zero-impact mode
- Clean exit handling

## Advanced Features

### Performance Optimization
- GPU acceleration
- Memory management
- Resource cleanup
- Efficient rendering

### Safety Features
- Graceful shutdown
- Device zeroing on exit
- Connection resilience
- Error recovery

## Configuration

### Persistence
- Settings saved between sessions
- Display preferences remembered
- Last used directories
- Effect parameters

### Customization
- Custom font support
- User media folders
- Device configurations
- Effect parameters

## Technical Details

### Video Processing
- OpenCV backend
- Hardware acceleration
- Format conversion
- Frame synchronization

### Audio Engine
- pygame mixer
- Dual channel mixing
- Volume normalization
- Efficient looping

### Device Protocol
- Buttplug v3 spec
- WebSocket transport
- Command queueing
- State management

### UI Framework
- PyQt6 based
- Native controls
- Responsive layout
- Theme support
