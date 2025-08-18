# Video Engine Documentation

## Overview
The video engine handles video playback, effects processing, and overlay management using OpenCV and PyQt6.

## Components

### 1. Video Playback
```python
from mesmerglass.engine.video import VideoPlayer

# Example usage
player = VideoPlayer(filepath="media/video.mp4")
player.set_opacity(0.75)
player.play()
```

#### Supported Formats
- MP4 (H.264/H.265)
- MOV (QuickTime)
- AVI (with appropriate codecs)

#### Performance Settings
- Hardware acceleration when available
- Buffer management for smooth playback
- Frame-skip for performance

### 2. Effects Pipeline

#### Opacity Control
- Real-time opacity adjustment
- Independent control for primary/secondary layers
- Blend mode management

#### Effect Modes
```python
# Available effect modes
EFFECTS = {
    "none": NoEffect(),
    "breath": BreathEffect(intensity=0.5),
    "shimmer": ShimmerEffect(speed=1.0),
    "tunnel": TunnelEffect(depth=2.0)
}
```

### 3. Multi-Monitor Support

#### Display Management
- Per-monitor overlay windows
- Synchronized playback
- Independent opacity control

#### Window Properties
```python
class OverlayWindow:
    def __init__(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
```

## API Reference

### VideoPlayer Class
```python
class VideoPlayer:
    def __init__(self, filepath: str):
        """Initialize video player with source file"""
        
    def play(self):
        """Start video playback"""
        
    def pause(self):
        """Pause video playback"""
        
    def set_opacity(self, value: float):
        """Set video opacity (0.0 - 1.0)"""
        
    def set_effect(self, effect_name: str, **params):
        """Apply named effect with parameters"""
```

### Effect Base Class
```python
class Effect:
    def __init__(self, **params):
        """Initialize effect with parameters"""
        
    def process_frame(self, frame):
        """Process a single video frame"""
        
    def update_params(self, **params):
        """Update effect parameters"""
```

## Performance Optimization

### GPU Acceleration
- Uses OpenGL when available
- CUDA support for compatible systems
- Fallback to CPU processing

### Memory Management
- Frame buffer limits
- Texture recycling
- Resource cleanup

### Threading Model
```python
# Background processing thread
self.process_thread = QThread()
self.worker = VideoProcessor()
self.worker.moveToThread(self.process_thread)
```

## Error Handling

### Common Issues
1. Format compatibility
2. Codec availability
3. Memory constraints
4. GPU compatibility

### Recovery Strategies
```python
try:
    self.load_video(path)
except VideoError as e:
    if e.code == ErrorCode.CODEC_MISSING:
        self.fallback_to_cpu()
    elif e.code == ErrorCode.MEMORY_ERROR:
        self.reduce_buffer_size()
```

## Performance Monitoring

### Metrics
- Frame rate
- Memory usage
- GPU utilization
- Drop frame count

### Diagnostics
```python
def get_performance_metrics(self):
    return {
        "fps": self.current_fps,
        "memory_mb": self.memory_usage,
        "gpu_util": self.gpu_percentage,
        "dropped": self.dropped_frames
    }
```

## Testing

### Unit Tests
```python
def test_video_loading():
    player = VideoPlayer("test.mp4")
    assert player.is_loaded()
    assert player.get_duration() > 0

def test_opacity_control():
    player = VideoPlayer("test.mp4")
    player.set_opacity(0.5)
    assert abs(player.get_opacity() - 0.5) < 0.001
```

### Performance Tests
- Frame rate stability
- Memory leak detection
- Multi-monitor sync
- Effect pipeline latency
