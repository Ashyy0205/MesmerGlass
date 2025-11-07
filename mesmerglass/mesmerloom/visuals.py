"""
Visual programs for orchestrating images, text, and spiral animations.

Based on Trance's visual system - provides complete animation sequences
using cyclers, shuffler, and compositor integration.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any
from pathlib import Path

from mesmerglass.mesmerloom.cyclers import (
    Cycler, ActionCycler, RepeatCycler, SequenceCycler, ParallelCycler
)
from mesmerglass.engine.shuffler import Shuffler


class Visual(ABC):
    """
    Base class for all visual programs.
    
    A visual program is a complete animation sequence that orchestrates:
    - Image/video switching
    - Text overlay cycling
    - Spiral rotation and evolution
    - Timing via cycler composition
    """
    
    def __init__(self):
        self._cycler: Optional[Cycler] = None
        # Only set defaults if not already set by child
        if not hasattr(self, '_image_paths'):
            self._image_paths: List[Path] = []
        if not hasattr(self, '_text_lines'):
            self._text_lines: List[str] = []
    
    @abstractmethod
    def build_cycler(self) -> Cycler:
        """
        Build the cycler structure for this visual program.
        
        Returns:
            Root cycler that orchestrates all animations
        """
        pass
    
    def get_cycler(self) -> Cycler:
        """Get the cycler (builds it if needed)."""
        if self._cycler is None:
            self._cycler = self.build_cycler()
        return self._cycler
    
    def reset(self) -> None:
        """Reset visual to initial state."""
        # Rebuild cycler from scratch to ensure clean state
        self._cycler = None
        if hasattr(self, '_shuffler'):
            self._shuffler.reset()
    
    def complete(self) -> bool:
        """Check if visual program has finished."""
        if self._cycler is None:
            return False  # Not started yet
        return self._cycler.complete()
    
    def progress(self) -> float:
        """Get progress through visual [0.0 - 1.0]."""
        if self._cycler is None:
            return 0.0  # Not started yet
        return self._cycler.progress()


class SimpleVisual(Visual):
    """
    Basic slideshow visual program.
    
    Pattern from Trance's SimpleVisual:
    - Change image every 48 frames (~0.8s at 60fps)
    - Preload next image at frame 24 (halfway point)
    - Rotate spiral every frame
    - Repeat 16 times (16 images total)
    
    Example:
        visual = SimpleVisual(
            image_paths=my_images,
            on_change_image=lambda idx: load_image(images[idx]),
            on_rotate_spiral=lambda: spiral.rotate(2.0)
        )
        cycler = visual.get_cycler()
        
        # In update loop:
        cycler.advance()
    
    Args:
        image_paths: List of image file paths to cycle through
        on_change_image: Callback(index) to load/display an image
        on_preload_image: Optional callback(index) to preload next image
        on_rotate_spiral: Callback() to rotate spiral each frame
        shuffler: Optional custom shuffler (creates default if None)
        image_count: Number of images to show (default: 16)
        frame_period: Frames between image changes (default: 48)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        on_change_image: Callable[[int], None],
        on_rotate_spiral: Callable[[], None],
        on_preload_image: Optional[Callable[[int], None]] = None,
        shuffler: Optional[Shuffler] = None,
        image_count: int = 9999,  # Increased from 16 for continuous playback
        frame_period: int = 48
    ):
        super().__init__()
        
        if not image_paths:
            raise ValueError("image_paths cannot be empty")
        if image_count <= 0:
            raise ValueError(f"image_count must be positive, got {image_count}")
        if frame_period <= 0:
            raise ValueError(f"frame_period must be positive, got {frame_period}")
        
        self._image_paths = image_paths
        self._on_change_image = on_change_image
        self._on_preload_image = on_preload_image
        self._on_rotate_spiral = on_rotate_spiral
        self._image_count = image_count
        self._frame_period = frame_period
        
        # Create shuffler if not provided
        if shuffler is None:
            self._shuffler = Shuffler(
                item_count=len(image_paths),
                initial_weight=10,
                history_size=8
            )
        else:
            self._shuffler = shuffler
    
    def build_cycler(self) -> Cycler:
        """
        Build SimpleVisual cycler structure.
        
        Structure:
            ParallelCycler([
                ActionCycler(1, rotate_spiral),  # Every frame
                RepeatCycler(image_count, SequenceCycler([
                    ActionCycler(1, change_image),        # Frame 0
                    ActionCycler(1, preload_next, offset=frame_period//2)  # Frame 24
                ]))
            ])
        """
        
        def change_image():
            """Select and load next image."""
            index = self._shuffler.next()
            self._on_change_image(index)
        
        def preload_next():
            """Preload next image if callback provided."""
            if self._on_preload_image:
                # Peek at what will be selected next (without actually selecting)
                # For now, just preload a random choice
                index = self._shuffler.next()
                self._on_preload_image(index)
        
        # Image change cycle (48 frames)
        image_cycler = ActionCycler(
            period=self._frame_period,
            action=change_image,
            repeat_count=1
        )
        
        # Preload at halfway point (frame 24)
        if self._on_preload_image:
            preload_cycler = ActionCycler(
                period=self._frame_period,
                action=preload_next,
                offset=self._frame_period // 2,
                repeat_count=1
            )
            image_sequence = SequenceCycler([image_cycler, preload_cycler])
        else:
            image_sequence = image_cycler
        
        # Repeat for desired number of images
        image_loop = RepeatCycler(count=self._image_count, child=image_sequence)
        
        # Spiral rotation every frame (limit to same duration as images)
        spiral_cycler = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=self._image_count * self._frame_period  # Match image loop duration
        )
        
        # Run everything in parallel
        return ParallelCycler([spiral_cycler, image_loop])


class SubTextVisual(Visual):
    """
    Images with cycling text overlay visual program.
    
    Pattern from Trance's SubTextVisual:
    - Change image every 48 frames
    - Text resets every 4 frames
    - Text cycles through words, repeats 23 times per image
    - Multiple subtext layers at different speeds (12/24/48 frames)
    - Rotate spiral every frame (faster: 4.0 degrees vs 2.0)
    - Repeat 16 times
    
    Args:
        image_paths: List of image file paths
        text_lines: List of text strings to cycle through
        on_change_image: Callback(index) to load/display image
        on_change_text: Callback(text) to update text overlay
        on_change_subtext: Callback(text) to update subtext overlay
        on_rotate_spiral: Callback() to rotate spiral
        shuffler: Optional custom shuffler
        image_count: Number of images to show (default: 16)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        text_lines: List[str],
        on_change_image: Callable[[int], None],
        on_change_text: Callable[[str], None],
        on_change_subtext: Callable[[str], None],
        on_rotate_spiral: Callable[[], None],
        shuffler: Optional[Shuffler] = None,
        image_count: int = 16
    ):
        super().__init__()
        
        if not image_paths:
            raise ValueError("image_paths cannot be empty")
        if not text_lines:
            raise ValueError("text_lines cannot be empty")
        
        self._image_paths = image_paths
        self._text_lines = text_lines
        self._on_change_image = on_change_image
        self._on_change_text = on_change_text
        self._on_change_subtext = on_change_subtext
        self._on_rotate_spiral = on_rotate_spiral
        self._image_count = image_count
        
        # Create shuffler
        if shuffler is None:
            self._shuffler = Shuffler(
                item_count=len(image_paths),
                initial_weight=10,
                history_size=8
            )
        else:
            self._shuffler = shuffler
        
        # Split text into words for cycling
        self._words = []
        for line in text_lines:
            self._words.extend(line.split())
        
        if not self._words:
            self._words = ["..."]  # Fallback
        
        self._word_index = 0
        self._subtext_index = 0
    
    def build_cycler(self) -> Cycler:
        """
        Build SubTextVisual cycler structure.
        
        Structure matches Trance's SubTextVisual with multiple text layers
        cycling at different speeds.
        """
        
        def change_image():
            index = self._shuffler.next()
            self._on_change_image(index)
        
        def reset_text():
            """Reset text cycle to beginning."""
            self._word_index = 0
            self._on_change_text(self._words[0])
        
        def cycle_text():
            """Advance to next word."""
            self._word_index = (self._word_index + 1) % len(self._words)
            self._on_change_text(self._words[self._word_index])
        
        def cycle_subtext():
            """Cycle subtext (separate from main text)."""
            self._subtext_index = (self._subtext_index + 1) % len(self._words)
            self._on_change_subtext(self._words[self._subtext_index])
        
        # Image changes every 48 frames
        image_cycler = ActionCycler(period=48, action=change_image, repeat_count=1)
        
        # Text system: reset every 4 frames, then cycle 23 times
        text_reset = ActionCycler(period=4, action=reset_text, repeat_count=1)
        text_cycle = ActionCycler(period=4, action=cycle_text, repeat_count=1)
        text_loop = SequenceCycler([
            text_reset,
            RepeatCycler(count=23, child=text_cycle)
        ])
        
        # Subtext at different speeds (creates layered effect)
        subtext_slow = ActionCycler(period=12, action=cycle_subtext, repeat_count=4)
        subtext_med = ActionCycler(period=24, action=cycle_subtext, repeat_count=2)
        subtext_fast = ActionCycler(period=48, action=cycle_subtext, repeat_count=1)
        
        # All visual elements in parallel per image
        per_image = ParallelCycler([
            image_cycler,
            text_loop,
            subtext_slow,
            subtext_med,
            subtext_fast
        ])
        
        # Repeat for multiple images
        main_loop = RepeatCycler(count=self._image_count, child=per_image)
        
        # Spiral rotation (faster than SimpleVisual) - match main loop duration
        total_frames = self._image_count * 48  # Each image is 48 frames
        spiral_cycler = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=total_frames
        )
        
        return ParallelCycler([spiral_cycler, main_loop])


class AccelerateVisual(Visual):
    """
    Accelerating slideshow visual program.
    
    Pattern from Trance's AccelerateVisual:
    - Starts with images showing for 56 frames each
    - Each image duration decreases by 1 frame
    - Minimum duration is 12 frames
    - Zoom increases with global progress: zoom_origin = 0.4 * progress
    - Spiral rotation speed increases with acceleration
    
    Args:
        image_paths: List of image file paths
        on_change_image: Callback(index, zoom) to load/display image with zoom
        on_rotate_spiral: Callback(speed) to rotate spiral at variable speed
        shuffler: Optional custom shuffler
        start_duration: Starting frame duration (default: 56)
        min_duration: Minimum frame duration (default: 12)
        image_count: Number of images to show (default: 44 = 56-12)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        on_change_image: Callable[[int, float], None],
        on_rotate_spiral: Callable[[float], None],
        shuffler: Optional[Shuffler] = None,
        start_duration: int = 56,
        min_duration: int = 12,
        image_count: Optional[int] = None
    ):
        super().__init__()
        
        if not image_paths:
            raise ValueError("image_paths cannot be empty")
        
        self._image_paths = image_paths
        self._on_change_image = on_change_image
        self._on_rotate_spiral = on_rotate_spiral
        self._start_duration = start_duration
        self._min_duration = min_duration
        
        # Default image count = full acceleration range
        if image_count is None:
            self._image_count = start_duration - min_duration
        else:
            self._image_count = image_count
        
        # Create shuffler
        if shuffler is None:
            self._shuffler = Shuffler(
                item_count=len(image_paths),
                initial_weight=10,
                history_size=8
            )
        else:
            self._shuffler = shuffler
        
        # State
        self._current_duration = start_duration
        self._images_shown = 0
    
    def build_cycler(self) -> Cycler:
        """
        Build AccelerateVisual cycler structure.
        
        Note: This is simplified - a full implementation would dynamically
        adjust frame periods. For now, we'll use a sequence of decreasing periods.
        """
        
        def change_image():
            """Load image with increasing zoom based on progress."""
            # Calculate zoom based on global progress
            progress = self._images_shown / self._image_count
            zoom_origin = 0.4 * progress
            
            index = self._shuffler.next()
            self._on_change_image(index, zoom_origin)
            
            self._images_shown += 1
            
            # Decrease duration for next image
            self._current_duration = max(
                self._min_duration,
                self._current_duration - 1
            )
        
        def rotate_spiral():
            """Rotate spiral with increasing speed."""
            # Base rotation + acceleration factor
            progress = self._images_shown / self._image_count
            # Speed increases from 1.0 to 4.0 as we accelerate
            speed = 1.0 + (3.0 * progress)
            self._on_rotate_spiral(speed)
        
        # Build sequence of image cyclers with decreasing durations
        image_cyclers = []
        current_dur = self._start_duration
        
        for i in range(self._image_count):
            cycler = ActionCycler(
                period=current_dur,
                action=change_image,
                repeat_count=1
            )
            image_cyclers.append(cycler)
            
            # Decrease duration for next iteration
            current_dur = max(self._min_duration, current_dur - 1)
        
        # Sequence all image changes
        image_sequence = SequenceCycler(image_cyclers)
        
        # Spiral rotation every frame - match image sequence duration
        total_frames = sum(
            max(self._min_duration, self._start_duration - i)
            for i in range(self._image_count)
        )
        spiral_cycler = ActionCycler(
            period=1,
            action=rotate_spiral,
            repeat_count=total_frames
        )
        
        return ParallelCycler([spiral_cycler, image_sequence])


class SlowFlashVisual(Visual):
    """
    Alternating slow and fast image cycles visual program.
    
    Pattern from Trance's SlowFlashVisual:
    - Slow mode: 64 frames per image, repeated 16 times
    - Fast mode: 8 frames per image, repeated 32 times
    - Alternates between slow and fast sequences
    - Spiral rotation: 2.0 degrees per frame (slow), 4.0 degrees (fast)
    - Creates pacing variation and rhythm changes
    
    Args:
        image_paths: List of image file paths
        on_change_image: Callback when image changes (receives index)
        on_rotate_spiral: Callback for spiral rotation (receives degrees)
        on_preload_image: Optional callback for preloading next image
        slow_duration: Frames per image in slow mode (default: 64)
        fast_duration: Frames per image in fast mode (default: 8)
        slow_count: Number of images in slow mode (default: 16)
        fast_count: Number of images in fast mode (default: 32)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        on_change_image: Callable[[int], None],
        on_rotate_spiral: Callable[[], None],
        on_preload_image: Optional[Callable[[int], None]] = None,
        slow_duration: int = 64,
        fast_duration: int = 8,
        slow_count: int = 16,
        fast_count: int = 32
    ):
        if slow_duration <= 0:
            raise ValueError("slow_duration must be positive")
        if fast_duration <= 0:
            raise ValueError("fast_duration must be positive")
        if slow_count <= 0:
            raise ValueError("slow_count must be positive")
        if fast_count <= 0:
            raise ValueError("fast_count must be positive")
        
        self._image_paths = image_paths
        self._on_change_image = on_change_image
        self._on_rotate_spiral = on_rotate_spiral
        self._on_preload_image = on_preload_image
        self._slow_duration = slow_duration
        self._fast_duration = fast_duration
        self._slow_count = slow_count
        self._fast_count = fast_count
        
        # Create shuffler
        self._shuffler = Shuffler(item_count=len(image_paths))
        
        super().__init__()
    
    def build_cycler(self) -> Cycler:
        """Build slow-fast alternating cycler."""
        
        def change_image():
            index = self._shuffler.next()
            self._on_change_image(index)
        
        # Slow mode sequence
        slow_image = ActionCycler(
            period=self._slow_duration,
            action=change_image,
            repeat_count=1
        )
        slow_loop = RepeatCycler(count=self._slow_count, child=slow_image)
        slow_spiral = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=self._slow_count * self._slow_duration
        )
        slow_sequence = ParallelCycler([slow_spiral, slow_loop])
        
        # Fast mode sequence
        fast_image = ActionCycler(
            period=self._fast_duration,
            action=change_image,
            repeat_count=1
        )
        fast_loop = RepeatCycler(count=self._fast_count, child=fast_image)
        fast_spiral = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=self._fast_count * self._fast_duration
        )
        fast_sequence = ParallelCycler([fast_spiral, fast_loop])
        
        # Alternate slow and fast
        return SequenceCycler([slow_sequence, fast_sequence])


class FlashTextVisual(Visual):
    """
    Rapid text flashing visual program.
    
    Pattern from Trance's FlashTextVisual:
    - Very short display times (4-8 frames)
    - Text rapidly cycles through word lists
    - Multiple text layers flashing at different rates
    - Creates subliminal/rapid-fire text effect
    - Spiral rotation: 3.0 degrees per frame
    
    Args:
        image_paths: List of image file paths
        text_lines: List of text strings to flash
        on_change_image: Callback when image changes
        on_change_text: Callback when text changes (receives text string)
        on_rotate_spiral: Callback for spiral rotation
        flash_period: Frames per text flash (default: 6)
        image_period: Frames per image change (default: 24)
        flash_count: Number of text flashes per image (default: 4)
        total_images: Total number of images to show (default: 12)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        text_lines: List[str],
        on_change_image: Callable[[int], None],
        on_change_text: Callable[[str], None],
        on_rotate_spiral: Callable[[], None],
        flash_period: int = 6,
        image_period: int = 24,
        flash_count: int = 4,
        total_images: int = 12
    ):
        if flash_period <= 0:
            raise ValueError("flash_period must be positive")
        if image_period <= 0:
            raise ValueError("image_period must be positive")
        if flash_count <= 0:
            raise ValueError("flash_count must be positive")
        if total_images <= 0:
            raise ValueError("total_images must be positive")
        if not text_lines:
            raise ValueError("text_lines cannot be empty")
        
        self._image_paths = image_paths
        self._text_lines = text_lines
        self._on_change_image = on_change_image
        self._on_change_text = on_change_text
        self._on_rotate_spiral = on_rotate_spiral
        self._flash_period = flash_period
        self._image_period = image_period
        self._flash_count = flash_count
        self._total_images = total_images
        
        # Create shufflers
        self._image_shuffler = Shuffler(item_count=len(image_paths))
        self._text_index = 0
        
        super().__init__()
    
    def build_cycler(self) -> Cycler:
        """Build rapid text flashing cycler."""
        
        def change_image():
            index = self._image_shuffler.next()
            self._on_change_image(index)
        
        def flash_text():
            text = self._text_lines[self._text_index % len(self._text_lines)]
            self._on_change_text(text)
            self._text_index += 1
        
        # Image changes
        image_cycler = ActionCycler(
            period=self._image_period,
            action=change_image,
            repeat_count=1
        )
        image_loop = RepeatCycler(count=self._total_images, child=image_cycler)
        
        # Text flashing
        text_flash = ActionCycler(
            period=self._flash_period,
            action=flash_text,
            repeat_count=1
        )
        text_loop = RepeatCycler(
            count=self._flash_count,
            child=text_flash
        )
        # Repeat text loop for each image
        text_sequence = RepeatCycler(count=self._total_images, child=text_loop)
        
        # Spiral rotation
        total_frames = self._total_images * self._image_period
        spiral_cycler = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=total_frames
        )
        
        # Run everything in parallel
        return ParallelCycler([spiral_cycler, image_loop, text_sequence])


class ParallelImagesVisual(Visual):
    """
    Multiple simultaneous images visual program.
    
    Pattern from Trance's ParallelVisual:
    - 2-4 images on screen simultaneously
    - Different positions, scales, or zoom levels
    - Independent timing for each image slot
    - Creates visual complexity and layering
    - Spiral rotation: 2.5 degrees per frame
    
    Note: This visual type demonstrates the cycler pattern. Actual multi-image
    rendering requires compositor support for multiple background layers.
    
    Args:
        image_paths: List of image file paths
        on_change_image: Callback when image changes (receives slot_index, image_index)
        on_rotate_spiral: Callback for spiral rotation
        slot_count: Number of simultaneous image slots (default: 3)
        slot_period: Frames between changes per slot (default: [32, 48, 64])
        total_cycles: Number of complete cycles (default: 8)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        on_change_image: Callable[[int, int], None],  # (slot, image_index)
        on_rotate_spiral: Callable[[], None],
        slot_count: int = 3,
        slot_periods: Optional[List[int]] = None,
        total_cycles: int = 8
    ):
        if slot_count <= 0:
            raise ValueError("slot_count must be positive")
        if total_cycles <= 0:
            raise ValueError("total_cycles must be positive")
        
        self._image_paths = image_paths
        self._on_change_image = on_change_image
        self._on_rotate_spiral = on_rotate_spiral
        self._slot_count = slot_count
        self._slot_periods = slot_periods or [32, 48, 64][:slot_count]
        self._total_cycles = total_cycles
        
        # Ensure we have enough periods
        while len(self._slot_periods) < slot_count:
            self._slot_periods.append(48)
        
        # Create shufflers for each slot
        self._shufflers = [Shuffler(item_count=len(image_paths)) for _ in range(slot_count)]
        
        super().__init__()
    
    def build_cycler(self) -> Cycler:
        """Build parallel multi-image cycler."""
        
        # Create image cycler for each slot
        slot_cyclers = []
        for slot_idx in range(self._slot_count):
            period = self._slot_periods[slot_idx]
            shuffler = self._shufflers[slot_idx]
            
            def make_change_image(slot, shuf):
                def change():
                    index = shuf.next()
                    self._on_change_image(slot, index)
                return change
            
            image_cycler = ActionCycler(
                period=period,
                action=make_change_image(slot_idx, shuffler),
                repeat_count=1
            )
            slot_loop = RepeatCycler(count=self._total_cycles, child=image_cycler)
            slot_cyclers.append(slot_loop)
        
        # Spiral rotation - match longest slot duration
        total_frames = max(self._slot_periods) * self._total_cycles
        spiral_cycler = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=total_frames
        )
        
        # Run all slots in parallel
        return ParallelCycler([spiral_cycler] + slot_cyclers)


class AnimationVisual(Visual):
    """
    Video/animation focused visual program.
    
    Pattern from Trance's AnimationVisual:
    - Plays video files frame-by-frame using VideoStreamer
    - Synchronizes with spiral rotation
    - Supports ping-pong playback mode (forward then backward)
    - Integrates with Phase 1 video streaming infrastructure
    
    The callback on_change_video() should load the video using VideoStreamer.load_video().
    Actual frame-by-frame playback is handled by the calling code (typically via QTimer).
    This visual just controls WHEN to switch videos.
    
    Args:
        video_paths: List of video file paths
        on_change_video: Callback when video changes (receives index)
        on_rotate_spiral: Callback for spiral rotation
        video_duration: Frames to play each video (default: 300 = 5 seconds at 60fps)
        video_count: Number of videos to play (default: 6)
    """
    
    def __init__(
        self,
        video_paths: List[Path],
        on_change_video: Callable[[int], None],
        on_rotate_spiral: Callable[[], None],
        video_duration: int = 300,
        video_count: int = 6
    ):
        if video_duration <= 0:
            raise ValueError("video_duration must be positive")
        if video_count <= 0:
            raise ValueError("video_count must be positive")
        
        self._video_paths = video_paths
        self._on_change_video = on_change_video
        self._on_rotate_spiral = on_rotate_spiral
        self._video_duration = video_duration
        self._video_count = video_count
        
        # Create shuffler
        self._shuffler = Shuffler(item_count=len(video_paths))
        
        super().__init__()
    
    def build_cycler(self) -> Cycler:
        """Build video playback cycler."""
        
        def change_video():
            index = self._shuffler.next()
            self._on_change_video(index)
        
        # Video changes
        video_cycler = ActionCycler(
            period=self._video_duration,
            action=change_video,
            repeat_count=1
        )
        video_loop = RepeatCycler(count=self._video_count, child=video_cycler)
        
        # Spiral rotation
        total_frames = self._video_duration * self._video_count
        spiral_cycler = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=total_frames
        )
        
        return ParallelCycler([spiral_cycler, video_loop])


class MixedVisual(Visual):
    """
    Mixed media visual program that alternates between images and videos.
    
    Pattern:
    - Shows N images (using SimpleVisual logic)
    - Then shows M videos (using AnimationVisual logic)
    - Repeats the cycle
    
    Args:
        image_paths: List of image file paths
        video_paths: List of video file paths
        on_change_image: Callback when image changes (receives index)
        on_change_video: Callback when video changes (receives index)
        on_rotate_spiral: Callback for spiral rotation
        image_duration: Frames per image (default: 48 = 0.8s at 60fps)
        video_duration: Frames per video (default: 300 = 5s at 60fps)
        images_per_cycle: Number of images to show per cycle (default: 3)
        videos_per_cycle: Number of videos to show per cycle (default: 2)
        cycles: Number of full cycles to run (default: 3)
    """
    
    def __init__(
        self,
        image_paths: List[Path],
        video_paths: List[Path],
        on_change_image: Callable[[int], None],
        on_change_video: Callable[[int], None],
        on_rotate_spiral: Callable[[], None],
        image_duration: int = 48,
        video_duration: int = 300,
        images_per_cycle: int = 3,
        videos_per_cycle: int = 2,
        cycles: int = 3
    ):
        if image_duration <= 0:
            raise ValueError("image_duration must be positive")
        if video_duration <= 0:
            raise ValueError("video_duration must be positive")
        if images_per_cycle <= 0:
            raise ValueError("images_per_cycle must be positive")
        if videos_per_cycle <= 0:
            raise ValueError("videos_per_cycle must be positive")
        if cycles <= 0:
            raise ValueError("cycles must be positive")
        
        self._image_paths = image_paths
        self._video_paths = video_paths
        self._on_change_image = on_change_image
        self._on_change_video = on_change_video
        self._on_rotate_spiral = on_rotate_spiral
        self._image_duration = image_duration
        self._video_duration = video_duration
        self._images_per_cycle = images_per_cycle
        self._videos_per_cycle = videos_per_cycle
        self._cycles = cycles
        
        # Create separate shufflers for images and videos
        self._image_shuffler = Shuffler(item_count=len(image_paths))
        self._video_shuffler = Shuffler(item_count=len(video_paths))
        
        # Track which media type is currently active
        self._showing_video = False
        
        super().__init__()
    
    def build_cycler(self) -> Cycler:
        """Build mixed media cycler structure.
        
        Structure:
            RepeatCycler(cycles, SequenceCycler([
                # Image phase
                RepeatCycler(images_per_cycle, 
                    ActionCycler(image_duration, change_image)
                ),
                # Video phase
                RepeatCycler(videos_per_cycle,
                    ActionCycler(video_duration, change_video)
                )
            ]))
        """
        
        def change_image():
            """Select and load next image."""
            self._showing_video = False  # Mark that we're showing an image
            index = self._image_shuffler.next()
            self._on_change_image(index)
        
        def change_video():
            """Select and load next video."""
            self._showing_video = True  # Mark that we're showing a video
            index = self._video_shuffler.next()
            self._on_change_video(index)
        
        # Image phase: show N images
        image_cycler = ActionCycler(
            period=self._image_duration,
            action=change_image,
            repeat_count=1
        )
        image_phase = RepeatCycler(count=self._images_per_cycle, child=image_cycler)
        
        # Video phase: show M videos
        video_cycler = ActionCycler(
            period=self._video_duration,
            action=change_video,
            repeat_count=1
        )
        video_phase = RepeatCycler(count=self._videos_per_cycle, child=video_cycler)
        
        # One complete cycle: images then videos
        one_cycle = SequenceCycler([image_phase, video_phase])
        
        # Repeat the cycle
        media_loop = RepeatCycler(count=self._cycles, child=one_cycle)
        
        # Spiral rotation every frame (for entire duration)
        total_frames = self._cycles * (
            self._images_per_cycle * self._image_duration +
            self._videos_per_cycle * self._video_duration
        )
        spiral_cycler = ActionCycler(
            period=1,
            action=self._on_rotate_spiral,
            repeat_count=total_frames
        )
        
        return ParallelCycler([spiral_cycler, media_loop])
    
    def is_showing_video(self) -> bool:
        """Check if currently showing a video (vs an image)."""
        return self._showing_video


# ===== Export CustomVisual (future-proof replacement for hardcoded visuals) =====
try:
    from .custom_visual import CustomVisual
    __all__ = ['Visual', 'SimpleVisual', 'SubTextVisual', 'AccelerateVisual', 
               'SlowFlashVisual', 'FlashTextVisual', 'ParallelImagesVisual',
               'AnimationVisual', 'MixedVisual', 'CustomVisual']
except ImportError as e:
    # CustomVisual not available (optional dependency or file missing)
    __all__ = ['Visual', 'SimpleVisual', 'SubTextVisual', 'AccelerateVisual',
               'SlowFlashVisual', 'FlashTextVisual', 'ParallelImagesVisual',
               'AnimationVisual', 'MixedVisual']
