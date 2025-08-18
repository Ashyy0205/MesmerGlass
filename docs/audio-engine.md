# Audio Engine Documentation

## Overview
The audio engine manages audio playback, mixing, and synchronization using pygame's mixer module.

## Components

### 1. Audio Player
```python
from mesmerglass.engine.audio import Audio2

# Example usage
player = Audio2()
player.load_track(1, "music.mp3")
player.set_volume(1, 0.75)  # 75% volume
player.play(1)
```

#### Supported Formats
- MP3 (recommended)
- WAV
- OGG

### 2. Dual Track System

#### Track Management
- Independent volume control
- Synchronized playback
- Loop control
- Individual track states

```python
class Audio2:
    def __init__(self):
        """Initialize dual-track audio system"""
        pygame.mixer.init()
        self.tracks = {1: None, 2: None}
        self.volumes = {1: 1.0, 2: 1.0}
```

### 3. Mixing Features

#### Volume Control
```python
def set_volume(self, track: int, level: float):
    """Set volume for specified track (0.0 - 1.0)"""
    if track in self.tracks and self.tracks[track]:
        self.volumes[track] = clamp(level, 0.0, 1.0)
        self.tracks[track].set_volume(self.volumes[track])
```

#### Playback Control
```python
def play(self, track: int, loop: bool = True):
    """Start playback of specified track"""
    if track in self.tracks and self.tracks[track]:
        self.tracks[track].play(-1 if loop else 0)

def stop(self, track: int):
    """Stop playback of specified track"""
    if track in self.tracks and self.tracks[track]:
        self.tracks[track].stop()
```

## Technical Details

### Memory Management

#### Loading Strategy
```python
def load_track(self, track: int, filepath: str):
    """Load audio file into specified track"""
    if track in self.tracks:
        # Clean up existing
        if self.tracks[track]:
            self.tracks[track].stop()
            self.tracks[track] = None
            
        # Load new track
        try:
            self.tracks[track] = pygame.mixer.Sound(filepath)
            self.set_volume(track, self.volumes[track])
        except Exception as e:
            logger.error(f"Failed to load audio: {e}")
```

### Error Handling

#### Common Issues
1. File format compatibility
2. Memory constraints
3. Device availability
4. Playback synchronization

#### Recovery Strategies
```python
def ensure_mixer_ready(self):
    """Ensure pygame mixer is initialized"""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except pygame.error:
            logger.error("Failed to initialize audio")
            return False
    return True
```

## Performance Optimization

### Memory Usage
- Efficient audio loading
- Resource cleanup
- Buffer management

### System Integration
- Device selection
- Format conversion
- Stream management

## Testing

### Unit Tests
```python
def test_audio_loading():
    player = Audio2()
    assert player.load_track(1, "test.mp3")
    assert player.tracks[1] is not None

def test_volume_control():
    player = Audio2()
    player.load_track(1, "test.mp3")
    player.set_volume(1, 0.5)
    assert abs(player.volumes[1] - 0.5) < 0.001
```

### Integration Tests
- Track synchronization
- Memory management
- Device handling
- Format support

## API Reference

### Audio2 Class
```python
class Audio2:
    def __init__(self):
        """Initialize audio system"""
        
    def load_track(self, track: int, filepath: str) -> bool:
        """Load audio file into specified track"""
        
    def play(self, track: int, loop: bool = True):
        """Start playback of specified track"""
        
    def stop(self, track: int):
        """Stop playback of specified track"""
        
    def set_volume(self, track: int, level: float):
        """Set volume for specified track"""
        
    def cleanup(self):
        """Release all resources"""
```

## Best Practices

### File Formats
- Use MP3 for best compatibility
- Convert WAV to MP3 for memory efficiency
- Test OGG support on target platform

### Memory Management
- Unload unused tracks
- Monitor memory usage
- Clean up resources properly

### Error Handling
- Validate audio files
- Handle device errors gracefully
- Provide user feedback
