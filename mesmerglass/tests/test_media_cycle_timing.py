"""
Test media cycle timing during fast playback.

Monitors actual frame delays between cycle boundaries and image loads,
comparing against the expected timing from cycle_speed settings.
"""
import json
import math
import time
from pathlib import Path
from typing import List, Dict, Optional
from unittest.mock import Mock, MagicMock

import pytest

from mesmerglass.content.themebank import ThemeBank
from mesmerglass.mesmerloom.custom_visual import CustomVisual


class TimingMonitor:
    """Tracks timing between cycle boundaries and image loads."""
    
    def __init__(self):
        self.cycle_requests: List[float] = []
        self.load_completions: List[float] = []
        self.frame_delays: List[int] = []  # Frames between request and load
        self.current_frame = 0
        self.pending_request_frame: Optional[int] = None
    
    def on_cycle_boundary(self):
        """Called when a cycle boundary is crossed."""
        self.cycle_requests.append(time.perf_counter())
        self.pending_request_frame = self.current_frame
    
    def on_image_loaded(self):
        """Called when an image finishes loading."""
        self.load_completions.append(time.perf_counter())
        if self.pending_request_frame is not None:
            delay = self.current_frame - self.pending_request_frame
            self.frame_delays.append(delay)
            self.pending_request_frame = None
    
    def advance_frame(self):
        """Called once per frame."""
        self.current_frame += 1
    
    def get_statistics(self) -> Dict:
        """Return timing statistics."""
        if not self.frame_delays:
            return {
                'min_frame_delay': 0,
                'max_frame_delay': 0,
                'avg_frame_delay': 0.0,
                'total_cycles': 0,
                'delays': []
            }
        
        return {
            'min_frame_delay': min(self.frame_delays),
            'max_frame_delay': max(self.frame_delays),
            'avg_frame_delay': sum(self.frame_delays) / len(self.frame_delays),
            'total_cycles': len(self.frame_delays),
            'delays': self.frame_delays.copy()
        }


def expected_frames_per_cycle(speed: int) -> int:
    """Calculate expected frames per cycle based on cycle_speed."""
    speed = max(1, min(100, int(speed)))
    interval_ms = 10000 * math.pow(0.005, (speed - 1) / 99.0)
    return max(1, round((interval_ms / 1000.0) * 60.0))


def create_test_theme(tmp_path: Path, num_images: int = 50) -> Path:
    """Create a test theme with multiple images."""
    theme_dir = tmp_path / "test_theme"
    theme_dir.mkdir(exist_ok=True)
    
    # Create dummy image files
    image_paths = []
    for i in range(num_images):
        img_path = theme_dir / f"image_{i:03d}.jpg"
        img_path.write_bytes(b"fake_image_data")
        image_paths.append(img_path.name)
    
    # Create theme JSON
    theme_data = {
        "name": "Test Theme",
        "image_path": image_paths
    }
    theme_json = theme_dir / "theme.json"
    theme_json.write_text(json.dumps(theme_data), encoding="utf-8")
    
    return theme_dir


def create_test_mode(tmp_path: Path, cycle_speed: int) -> Path:
    """Create a test custom mode with specified cycle speed."""
    data = {
        "version": "1.0",
        "name": f"TimingTest_{cycle_speed}",
        "spiral": {
            "type": "linear",
            "rotation_speed": 4.0,
            "opacity": 0.8,
            "reverse": False
        },
        "media": {
            "mode": "images",
            "cycle_speed": cycle_speed,
            "opacity": 1.0,
            "use_theme_bank": True
        },
        "text": {
            "enabled": False,
            "mode": "centered_sync",
            "opacity": 1.0,
            "use_theme_bank": True,
            "library": []
        },
        "zoom": {
            "mode": "none",
            "rate": 0.0
        }
    }
    mode_path = tmp_path / f"timing_test_{cycle_speed}.json"
    mode_path.write_text(json.dumps(data), encoding="utf-8")
    return mode_path


@pytest.mark.parametrize("cycle_speed", [70, 80, 90, 95, 100])
def test_media_cycle_timing_accuracy(tmp_path, cycle_speed):
    """
    Test that media loads occur within acceptable frame delays during fast cycling.
    
    This test simulates 20 seconds of fast media cycling and measures:
    - Frame delays between cycle boundary and image load
    - Min/max/average delays
    - Percentage of images loading within 1 frame (ideal for smooth playback)
    """
    # Setup
    theme_dir = create_test_theme(tmp_path, num_images=50)
    mode_path = create_test_mode(tmp_path, cycle_speed)
    
    # Mock ThemeBank that returns images instantly (simulating synchronous loading)
    mock_theme_bank = MagicMock(spec=ThemeBank)
    mock_image_data = Mock()
    mock_image_data.width = 1920
    mock_image_data.height = 1080
    
    # Track when get_image is called
    monitor = TimingMonitor()
    
    def mock_get_image(*args, **kwargs):
        monitor.on_image_loaded()
        return mock_image_data
    
    mock_theme_bank.get_image = Mock(side_effect=mock_get_image)
    
    # Mock compositor and text director
    mock_compositor = MagicMock()
    mock_text_director = MagicMock()
    
    # Create CustomVisual
    visual = CustomVisual(
        mode_path,
        theme_bank=mock_theme_bank,
        compositor=mock_compositor,
        text_director=mock_text_director
    )
    
    # Calculate test parameters
    expected_frames = expected_frames_per_cycle(cycle_speed)
    fps = 60
    test_duration = 20  # seconds
    total_frames = fps * test_duration
    
    # Simulate playback
    frame_count = 0
    cycle_count = 0
    
    for frame in range(total_frames):
        monitor.current_frame = frame
        
        # Check if cycle boundary crossed
        if frame % expected_frames == 0 and frame > 0:
            monitor.on_cycle_boundary()
            # Trigger media load
            visual._load_current_media()
            cycle_count += 1
        
        monitor.advance_frame()
        frame_count += 1
    
    # Get statistics
    stats = monitor.get_statistics()
    
    # Print detailed report
    print(f"\n{'='*60}")
    print(f"Media Cycle Timing Test - Speed {cycle_speed}")
    print(f"{'='*60}")
    print(f"Expected frames per cycle: {expected_frames}")
    print(f"Expected cycles in 20s: {20 * fps // expected_frames}")
    print(f"Actual cycles completed: {stats['total_cycles']}")
    print(f"\nFrame Delay Statistics:")
    print(f"  Minimum: {stats['min_frame_delay']} frames")
    print(f"  Maximum: {stats['max_frame_delay']} frames")
    print(f"  Average: {stats['avg_frame_delay']:.2f} frames")
    
    # Calculate distribution
    if stats['delays']:
        instant_loads = sum(1 for d in stats['delays'] if d == 0)
        one_frame = sum(1 for d in stats['delays'] if d == 1)
        two_frame = sum(1 for d in stats['delays'] if d == 2)
        three_plus = sum(1 for d in stats['delays'] if d >= 3)
        
        total = len(stats['delays'])
        print(f"\nDelay Distribution:")
        print(f"  0 frames (instant): {instant_loads}/{total} ({instant_loads/total*100:.1f}%)")
        print(f"  1 frame: {one_frame}/{total} ({one_frame/total*100:.1f}%)")
        print(f"  2 frames: {two_frame}/{total} ({two_frame/total*100:.1f}%)")
        print(f"  3+ frames: {three_plus}/{total} ({three_plus/total*100:.1f}%)")
    
    print(f"{'='*60}\n")
    
    # Assertions for synchronous loading (post-fix expectations)
    # With synchronous loading, ALL images should load in 0 frames
    assert stats['max_frame_delay'] == 0, \
        f"Expected all images to load instantly (0 frames), but max delay was {stats['max_frame_delay']}"
    
    assert stats['min_frame_delay'] == 0, \
        f"Expected all images to load instantly (0 frames), but min delay was {stats['min_frame_delay']}"
    
    assert stats['avg_frame_delay'] == 0.0, \
        f"Expected average delay of 0 frames, but got {stats['avg_frame_delay']:.2f}"
    
    # At fast speeds, we should complete many cycles
    min_expected_cycles = (20 * fps // expected_frames) - 5  # Allow some tolerance
    assert stats['total_cycles'] >= min_expected_cycles, \
        f"Expected at least {min_expected_cycles} cycles, but only got {stats['total_cycles']}"


def test_media_cycle_timing_regression_check(tmp_path):
    """
    Regression test to ensure synchronous loading never introduces delays.
    
    This is a stricter version that fails if ANY image takes more than 0 frames.
    """
    cycle_speed = 95  # Very fast cycling
    theme_dir = create_test_theme(tmp_path, num_images=100)
    mode_path = create_test_mode(tmp_path, cycle_speed)
    
    monitor = TimingMonitor()
    
    # Mock with instant loading
    mock_theme_bank = MagicMock(spec=ThemeBank)
    mock_image_data = Mock()
    mock_image_data.width = 1920
    mock_image_data.height = 1080
    
    def instant_load(*args, **kwargs):
        monitor.on_image_loaded()
        return mock_image_data
    
    mock_theme_bank.get_image = Mock(side_effect=instant_load)
    
    mock_compositor = MagicMock()
    mock_text_director = MagicMock()
    
    visual = CustomVisual(
        mode_path,
        theme_bank=mock_theme_bank,
        compositor=mock_compositor,
        text_director=mock_text_director
    )
    
    expected_frames = expected_frames_per_cycle(cycle_speed)
    
    # Test 1000 frames (about 16 seconds at 60fps)
    for frame in range(1000):
        monitor.current_frame = frame
        
        if frame % expected_frames == 0 and frame > 0:
            monitor.on_cycle_boundary()
            visual._load_current_media()
        
        monitor.advance_frame()
    
    stats = monitor.get_statistics()
    
    # STRICT: No delays allowed
    assert stats['max_frame_delay'] == 0, \
        f"Regression detected! Found {stats['max_frame_delay']} frame delay (expected 0)"
    
    assert all(d == 0 for d in stats['delays']), \
        f"Regression detected! Some images had non-zero delays: {[d for d in stats['delays'] if d > 0]}"
    
    print(f"\n✓ Regression test passed: All {stats['total_cycles']} cycles loaded instantly (0 frames)")


if __name__ == "__main__":
    # Run with: pytest test_media_cycle_timing.py -v -s
    pytest.main([__file__, "-v", "-s"])
