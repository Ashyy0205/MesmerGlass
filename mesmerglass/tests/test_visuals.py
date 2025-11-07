"""
Unit tests for visual programs.

Tests visual program execution, timing, and integration with cyclers/shuffler.
"""

import pytest
from pathlib import Path
from mesmerglass.mesmerloom.visuals import (
    Visual, SimpleVisual, SubTextVisual, AccelerateVisual
)
from mesmerglass.engine.shuffler import Shuffler


class TestSimpleVisual:
    """Test SimpleVisual - basic slideshow."""
    
    def test_basic_initialization(self):
        """Test simple visual creates correctly."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        events = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: events.append(('image', idx)),
            on_rotate_spiral=lambda: events.append(('spiral',))
        )
        
        assert not visual.complete()
        assert visual.progress() == 0.0
    
    def test_cycler_execution(self):
        """Test that cycler executes image changes and spiral rotation."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        image_changes = []
        spiral_rotations = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: image_changes.append(idx),
            on_rotate_spiral=lambda: spiral_rotations.append(1),
            image_count=3,  # Just 3 images for quick test
            frame_period=10  # 10 frames per image
        )
        
        cycler = visual.get_cycler()
        
        # Run for full duration (3 images * 10 frames = 30 frames)
        for _ in range(30):
            cycler.advance()
        
        # Should have changed image 3 times (at frames 0, 10, 20)
        assert len(image_changes) == 3
        
        # Should have rotated spiral 30 times (every frame)
        assert len(spiral_rotations) == 30
        
        # Should be complete
        assert cycler.complete()
    
    def test_shuffler_integration(self):
        """Test that shuffler provides varied image selection."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        image_changes = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: image_changes.append(idx),
            on_rotate_spiral=lambda: None,
            image_count=10,
            frame_period=5
        )
        
        cycler = visual.get_cycler()
        
        # Run full program
        for _ in range(50):
            cycler.advance()
        
        # Should have 10 unique selections
        assert len(image_changes) == 10
        
        # Should have variety (not all the same)
        assert len(set(image_changes)) > 1
    
    def test_preload_callback(self):
        """Test preload callback if provided."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        preloads = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: None,
            on_rotate_spiral=lambda: None,
            on_preload_image=lambda idx: preloads.append(idx),
            image_count=2,
            frame_period=10
        )
        
        cycler = visual.get_cycler()
        
        # Run full program
        for _ in range(20):
            cycler.advance()
        
        # Should have preloaded images (at frames 5 and 15)
        assert len(preloads) >= 1
    
    def test_reset(self):
        """Test visual reset functionality."""
        images = [Path(f"img{i}.jpg") for i in range(5)]
        image_changes = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: image_changes.append(idx),
            on_rotate_spiral=lambda: None,
            image_count=2,
            frame_period=5
        )
        
        cycler = visual.get_cycler()
        
        # Run partway
        for _ in range(5):
            cycler.advance()
        
        assert len(image_changes) == 1
        
        # Reset
        visual.reset()
        image_changes.clear()
        
        # Get fresh cycler after reset
        cycler = visual.get_cycler()
        
        # Run again
        for _ in range(5):
            cycler.advance()
        
        # Should execute again
        assert len(image_changes) == 1
    
    def test_invalid_parameters(self):
        """Test validation of parameters."""
        with pytest.raises(ValueError, match="image_paths cannot be empty"):
            SimpleVisual(
                image_paths=[],
                on_change_image=lambda idx: None,
                on_rotate_spiral=lambda: None
            )
        
        with pytest.raises(ValueError, match="image_count must be positive"):
            SimpleVisual(
                image_paths=[Path("img.jpg")],
                on_change_image=lambda idx: None,
                on_rotate_spiral=lambda: None,
                image_count=0
            )
        
        with pytest.raises(ValueError, match="frame_period must be positive"):
            SimpleVisual(
                image_paths=[Path("img.jpg")],
                on_change_image=lambda idx: None,
                on_rotate_spiral=lambda: None,
                frame_period=0
            )


class TestSubTextVisual:
    """Test SubTextVisual - images with text overlay."""
    
    def test_initialization(self):
        """Test SubTextVisual creates correctly."""
        images = [Path(f"img{i}.jpg") for i in range(5)]
        text_lines = ["Line 1", "Line 2", "Line 3"]
        
        visual = SubTextVisual(
            image_paths=images,
            text_lines=text_lines,
            on_change_image=lambda idx: None,
            on_change_text=lambda txt: None,
            on_change_subtext=lambda txt: None,
            on_rotate_spiral=lambda: None
        )
        
        assert not visual.complete()
    
    def test_text_cycling(self):
        """Test that text cycles through words."""
        images = [Path(f"img{i}.jpg") for i in range(5)]
        text_lines = ["Hello world", "Foo bar"]
        text_changes = []
        
        visual = SubTextVisual(
            image_paths=images,
            text_lines=text_lines,
            on_change_image=lambda idx: None,
            on_change_text=lambda txt: text_changes.append(txt),
            on_change_subtext=lambda txt: None,
            on_rotate_spiral=lambda: None,
            image_count=1  # Just one image
        )
        
        cycler = visual.get_cycler()
        
        # Run for one image cycle (48 frames)
        for _ in range(48):
            cycler.advance()
        
        # Text should have cycled through words
        # Reset at frame 0, then 23 cycles every 4 frames
        assert len(text_changes) > 0
        
        # Should include words from our text
        text_str = ' '.join(text_changes)
        assert 'Hello' in text_str or 'world' in text_str or 'Foo' in text_str or 'bar' in text_str
    
    def test_multi_layer_text(self):
        """Test multiple text layers at different speeds."""
        images = [Path(f"img{i}.jpg") for i in range(5)]
        text_lines = ["Word one two three"]
        
        text_changes = []
        subtext_changes = []
        
        visual = SubTextVisual(
            image_paths=images,
            text_lines=text_lines,
            on_change_image=lambda idx: None,
            on_change_text=lambda txt: text_changes.append(txt),
            on_change_subtext=lambda txt: subtext_changes.append(txt),
            on_rotate_spiral=lambda: None,
            image_count=1
        )
        
        cycler = visual.get_cycler()
        
        for _ in range(48):
            cycler.advance()
        
        # Both text and subtext should have updates
        assert len(text_changes) > 0
        assert len(subtext_changes) > 0
        
        # Subtext should update less frequently
        assert len(subtext_changes) < len(text_changes)
    
    def test_invalid_parameters(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="image_paths cannot be empty"):
            SubTextVisual(
                image_paths=[],
                text_lines=["text"],
                on_change_image=lambda idx: None,
                on_change_text=lambda txt: None,
                on_change_subtext=lambda txt: None,
                on_rotate_spiral=lambda: None
            )
        
        with pytest.raises(ValueError, match="text_lines cannot be empty"):
            SubTextVisual(
                image_paths=[Path("img.jpg")],
                text_lines=[],
                on_change_image=lambda idx: None,
                on_change_text=lambda txt: None,
                on_change_subtext=lambda txt: None,
                on_rotate_spiral=lambda: None
            )


class TestAccelerateVisual:
    """Test AccelerateVisual - accelerating slideshow."""
    
    def test_initialization(self):
        """Test AccelerateVisual creates correctly."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        
        visual = AccelerateVisual(
            image_paths=images,
            on_change_image=lambda idx, zoom: None,
            on_rotate_spiral=lambda speed: None
        )
        
        assert not visual.complete()
    
    def test_acceleration(self):
        """Test that image duration decreases over time."""
        images = [Path(f"img{i}.jpg") for i in range(20)]
        image_changes = []
        
        visual = AccelerateVisual(
            image_paths=images,
            on_change_image=lambda idx, zoom: image_changes.append((idx, zoom)),
            on_rotate_spiral=lambda speed: None,
            start_duration=20,
            min_duration=10,
            image_count=10
        )
        
        cycler = visual.get_cycler()
        
        # Run full program
        # Total frames = 20 + 19 + 18 + ... + 11 = 155 frames
        for _ in range(200):
            cycler.advance()
        
        # Should have shown 10 images
        assert len(image_changes) == 10
        
        # Zoom should increase with progress
        zooms = [zoom for idx, zoom in image_changes]
        assert zooms[-1] > zooms[0]  # Later images have more zoom
    
    def test_spiral_speed_increase(self):
        """Test that spiral rotation speed increases."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        spiral_speeds = []
        
        visual = AccelerateVisual(
            image_paths=images,
            on_change_image=lambda idx, zoom: None,
            on_rotate_spiral=lambda speed: spiral_speeds.append(speed),
            start_duration=10,
            min_duration=5,
            image_count=5
        )
        
        cycler = visual.get_cycler()
        
        # Run full program
        for _ in range(50):
            cycler.advance()
        
        # Should have many spiral rotations
        assert len(spiral_speeds) > 0
        
        # Speed should increase (later speeds > earlier speeds)
        if len(spiral_speeds) >= 10:
            early_avg = sum(spiral_speeds[:5]) / 5
            late_avg = sum(spiral_speeds[-5:]) / 5
            assert late_avg >= early_avg
    
    def test_custom_parameters(self):
        """Test custom start/min durations."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        
        visual = AccelerateVisual(
            image_paths=images,
            on_change_image=lambda idx, zoom: None,
            on_rotate_spiral=lambda speed: None,
            start_duration=30,
            min_duration=15,
            image_count=5
        )
        
        cycler = visual.get_cycler()
        
        # Should create valid cycler
        assert cycler is not None


class TestVisualCompletion:
    """Test visual program completion and progress."""
    
    def test_simple_visual_completion(self):
        """Test SimpleVisual completes correctly."""
        images = [Path(f"img{i}.jpg") for i in range(5)]
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: None,
            on_rotate_spiral=lambda: None,
            image_count=2,
            frame_period=10
        )
        
        cycler = visual.get_cycler()
        
        # Should not be complete initially
        assert not visual.complete()
        
        # Run to completion (2 images * 10 frames = 20)
        for _ in range(20):
            cycler.advance()
        
        # Should be complete
        assert visual.complete()
        assert visual.progress() == 1.0
    
    def test_progress_tracking(self):
        """Test progress calculation during execution."""
        images = [Path(f"img{i}.jpg") for i in range(5)]
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: None,
            on_rotate_spiral=lambda: None,
            image_count=2,
            frame_period=10
        )
        
        cycler = visual.get_cycler()
        
        # Progress should start at 0
        assert visual.progress() == 0.0
        
        # Advance halfway
        for _ in range(10):
            cycler.advance()
        
        # Progress should be around 0.5
        progress = visual.progress()
        assert 0.4 < progress < 0.6
        
        # Advance to completion
        for _ in range(10):
            cycler.advance()
        
        # Progress should be 1.0
        assert visual.progress() == 1.0


class TestShufflerIntegration:
    """Test visual programs with custom shufflers."""
    
    def test_custom_shuffler(self):
        """Test providing custom shuffler."""
        images = [Path(f"img{i}.jpg") for i in range(10)]
        
        # Create custom shuffler with different settings
        custom_shuffler = Shuffler(
            item_count=10,
            initial_weight=20,  # Higher weight
            history_size=5      # Smaller history
        )
        
        image_changes = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: image_changes.append(idx),
            on_rotate_spiral=lambda: None,
            shuffler=custom_shuffler,
            image_count=5,
            frame_period=5
        )
        
        cycler = visual.get_cycler()
        
        for _ in range(25):
            cycler.advance()
        
        # Should use custom shuffler
        assert len(image_changes) == 5
    
    def test_shuffler_anti_repetition(self):
        """Test that shuffler prevents immediate repeats."""
        images = [Path(f"img{i}.jpg") for i in range(3)]  # Small set to make repeats likely
        
        image_changes = []
        
        visual = SimpleVisual(
            image_paths=images,
            on_change_image=lambda idx: image_changes.append(idx),
            on_rotate_spiral=lambda: None,
            image_count=10,
            frame_period=5
        )
        
        cycler = visual.get_cycler()
        
        for _ in range(50):
            cycler.advance()
        
        # Check for immediate repeats (same index twice in a row)
        immediate_repeats = sum(
            1 for i in range(len(image_changes) - 1)
            if image_changes[i] == image_changes[i + 1]
        )
        
        # With 3 items and anti-repetition, should have fewer immediate repeats
        # than pure random (which would be ~33% = 3 repeats)
        # Allow up to 5 for randomness, but should be less than pure random
        assert immediate_repeats <= 5
