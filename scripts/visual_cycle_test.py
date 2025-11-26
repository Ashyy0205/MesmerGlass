"""
Standalone visual media cycling timing test.

Tests the FULL pipeline with actual display to identify rendering bottlenecks.
Run with: python scripts/visual_cycle_test.py --media-path MEDIA/Images
"""
import sys
import time
import psutil
from pathlib import Path
from collections import deque
from typing import Deque, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QImage

from mesmerglass.content.themebank import ThemeBank
from mesmerglass.content.theme import ThemeConfig


class CycleTimingTestWindow(QWidget):
    """Test window that cycles through ThemeBank images and measures timing."""
    
    def __init__(
        self,
        theme_bank: ThemeBank,
        target_fps: int = 60,
        cycle_speed: int = 95,
        test_duration_seconds: float = 20.0
    ):
        super().__init__()
        
        self.theme_bank = theme_bank
        self.target_fps = target_fps
        self.cycle_speed = cycle_speed
        self.test_duration = test_duration_seconds
        
        # Calculate frame interval and cycle interval
        self.frame_interval_ms = int(1000 / target_fps)  # ~16.67ms for 60fps
        
        # Cycle speed maps to frames per cycle (from spiral speed system)
        frames_per_cycle = self._speed_to_frames(cycle_speed)
        self.cycle_interval_frames = frames_per_cycle
        
        # Timing tracking
        self.frame_count = 0
        self.cycle_count = 0
        self.frame_delays: Deque[float] = deque(maxlen=1000)
        self.cycle_delays: Deque[float] = deque(maxlen=1000)
        self.load_times: Deque[float] = deque(maxlen=1000)
        
        # Memory tracking
        self.process = psutil.Process()
        self.initial_memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory_mb = self.initial_memory_mb
        
        # Track unique images shown
        self.unique_images_shown: set[str] = set()
        self.image_show_count: dict[str, int] = {}
        self.image_sizes: list[tuple[int, int]] = []  # Track (width, height) of loaded images
        
        self.last_frame_time = time.perf_counter()
        self.last_cycle_time = time.perf_counter()
        self.start_time = time.perf_counter()
        
        self.current_image: Optional[QPixmap] = None
        
        # UI Setup
        self.setWindowTitle(f"Media Cycle Timing Test - Speed {cycle_speed} @ {target_fps}fps")
        self.setGeometry(100, 100, 1024, 768)
        
        layout = QVBoxLayout()
        
        # Image display label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setScaledContents(True)
        layout.addWidget(self.image_label)
        
        # Stats display label
        self.stats_label = QLabel()
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats_label)
        
        self.setLayout(layout)
        
        # Frame timer
        self.frame_timer = QTimer()
        self.frame_timer.timeout.connect(self._on_frame)
        self.frame_timer.start(self.frame_interval_ms)
        
        # Stats update timer (every 100ms)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats_display)
        self.stats_timer.start(100)
        
        print(f"\n{'='*70}")
        print(f"VISUAL CYCLE TIMING TEST")
        print(f"{'='*70}")
        print(f"Target FPS: {target_fps}")
        print(f"Cycle Speed: {cycle_speed}")
        print(f"Frames per Cycle: {frames_per_cycle}")
        print(f"Test Duration: {test_duration_seconds}s")
        print(f"{'='*70}\n")
    
    def _speed_to_frames(self, speed: int) -> int:
        """Convert cycle speed to frames per cycle."""
        if speed >= 100:
            return 3
        elif speed >= 95:
            return 4
        elif speed >= 90:
            return 5
        elif speed >= 80:
            return 7
        elif speed >= 70:
            return 10
        else:
            return 15
    
    def _on_frame(self):
        """Called every frame - handles cycling and rendering."""
        now = time.perf_counter()
        
        # Track frame delay
        frame_delay = (now - self.last_frame_time) * 1000
        self.frame_delays.append(frame_delay)
        self.last_frame_time = now
        
        # Check if we should cycle to next image
        if self.frame_count % self.cycle_interval_frames == 0:
            self._cycle_image()
        
        # Display current image
        if self.current_image:
            self.image_label.setPixmap(self.current_image)
        
        self.frame_count += 1
        
        # Check if test is complete
        elapsed = now - self.start_time
        if elapsed >= self.test_duration:
            self._finish_test()
    
    def _cycle_image(self):
        """Load and prepare next image from ThemeBank."""
        cycle_start = time.perf_counter()
        
        # Track memory usage
        current_memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory_mb = max(self.peak_memory_mb, current_memory_mb)
        
        # Get next image from ThemeBank
        load_start = time.perf_counter()
        image_data = self.theme_bank.get_image(alternate=False)
        load_time = (time.perf_counter() - load_start) * 1000
        self.load_times.append(load_time)
        
        if image_data:
            # Convert numpy array to QImage then QPixmap (simulates texture upload)
            height, width, channels = image_data.data.shape
            bytes_per_line = channels * width
            qimage = QImage(
                image_data.data.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGBA8888
            )
            self.current_image = QPixmap.fromImage(qimage)
            
            # Track unique images
            img_name = image_data.path.name
            self.unique_images_shown.add(img_name)
            self.image_show_count[img_name] = self.image_show_count.get(img_name, 0) + 1
            
            # Track image size
            self.image_sizes.append((width, height))
            
            # Update window title with current image name for debugging
            self.setWindowTitle(
                f"Media Cycle Test - Speed {self.cycle_speed} @ {self.target_fps}fps - "
                f"[{self.cycle_count}] {img_name}"
            )
        
        cycle_time = (time.perf_counter() - cycle_start) * 1000
        self.cycle_delays.append(cycle_time)
        
        self.cycle_count += 1
        self.last_cycle_time = time.perf_counter()
    
    def _update_stats_display(self):
        """Update statistics display."""
        if not self.frame_delays or not self.cycle_delays:
            return
        
        elapsed = time.perf_counter() - self.start_time
        actual_fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        # Frame timing stats
        avg_frame = sum(self.frame_delays) / len(self.frame_delays)
        min_frame = min(self.frame_delays)
        max_frame = max(self.frame_delays)
        
        # Cycle timing stats
        avg_cycle = sum(self.cycle_delays) / len(self.cycle_delays)
        min_cycle = min(self.cycle_delays)
        max_cycle = max(self.cycle_delays)
        
        # Load timing stats
        avg_load = sum(self.load_times) / len(self.load_times) if self.load_times else 0
        min_load = min(self.load_times) if self.load_times else 0
        max_load = max(self.load_times) if self.load_times else 0
        
        # Calculate distribution
        frame_budget = 1000 / self.target_fps
        on_time = sum(1 for d in self.frame_delays if d <= frame_budget * 1.1)
        late = len(self.frame_delays) - on_time
        on_time_pct = (on_time / len(self.frame_delays)) * 100 if self.frame_delays else 0
        
        # Image diversity stats
        unique_count = len(self.unique_images_shown)
        repeat_rate = (self.cycle_count - unique_count) / self.cycle_count * 100 if self.cycle_count > 0 else 0
        
        # Memory stats
        current_memory_mb = self.process.memory_info().rss / 1024 / 1024
        memory_increase_mb = current_memory_mb - self.initial_memory_mb
        
        stats_text = f"""
<b>Test Progress:</b> {elapsed:.1f}s / {self.test_duration:.1f}s<br>
<b>Frames:</b> {self.frame_count} | <b>Cycles:</b> {self.cycle_count} | <b>Actual FPS:</b> {actual_fps:.1f}<br>
<b>Unique Images:</b> {unique_count} / {self.cycle_count} ({100 - repeat_rate:.1f}% unique)<br>
<b>Memory:</b> {current_memory_mb:.1f} MB (+{memory_increase_mb:.1f} MB, Peak: {self.peak_memory_mb:.1f} MB)<br>
<br>
<b>Frame Timing (ms):</b><br>
Avg: {avg_frame:.2f} | Min: {min_frame:.2f} | Max: {max_frame:.2f} | Budget: {frame_budget:.2f}<br>
On-time: {on_time} ({on_time_pct:.1f}%) | Late: {late}<br>
<br>
<b>Cycle Timing (ms):</b><br>
Avg: {avg_cycle:.2f} | Min: {min_cycle:.2f} | Max: {max_cycle:.2f}<br>
<br>
<b>Load Timing (ms):</b><br>
Avg: {avg_load:.2f} | Min: {min_load:.2f} | Max: {max_load:.2f}<br>
"""
        self.stats_label.setText(stats_text)
    
    def _finish_test(self):
        """Complete test and print results."""
        self.frame_timer.stop()
        self.stats_timer.stop()
        
        elapsed = time.perf_counter() - self.start_time
        actual_fps = self.frame_count / elapsed
        
        print(f"\n{'='*70}")
        print(f"TEST COMPLETE")
        print(f"{'='*70}")
        print(f"Duration: {elapsed:.2f}s")
        print(f"Total Frames: {self.frame_count}")
        print(f"Total Cycles: {self.cycle_count}")
        print(f"Actual FPS: {actual_fps:.2f} (target: {self.target_fps})")
        print()
        
        # Memory analysis
        final_memory_mb = self.process.memory_info().rss / 1024 / 1024
        memory_increase_mb = final_memory_mb - self.initial_memory_mb
        
        print(f"MEMORY USAGE:")
        print(f"  Initial: {self.initial_memory_mb:.1f} MB")
        print(f"  Final: {final_memory_mb:.1f} MB")
        print(f"  Peak: {self.peak_memory_mb:.1f} MB")
        print(f"  Increase: +{memory_increase_mb:.1f} MB")
        print()
        
        # Image diversity analysis
        unique_count = len(self.unique_images_shown)
        repeat_rate = (self.cycle_count - unique_count) / self.cycle_count * 100 if self.cycle_count > 0 else 0
        
        print(f"IMAGE DIVERSITY:")
        print(f"  Unique images shown: {unique_count}")
        print(f"  Total cycles: {self.cycle_count}")
        print(f"  Unique rate: {100 - repeat_rate:.1f}%")
        print(f"  Repeat rate: {repeat_rate:.1f}%")
        
        # Show most repeated images
        if self.image_show_count:
            most_repeated = sorted(self.image_show_count.items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"  Most repeated images:")
            for img_name, count in most_repeated:
                print(f"    {img_name}: {count} times")
        print()
        
        # Image size analysis
        if self.image_sizes:
            avg_width = sum(w for w, h in self.image_sizes) / len(self.image_sizes)
            avg_height = sum(h for w, h in self.image_sizes) / len(self.image_sizes)
            max_width = max(w for w, h in self.image_sizes)
            max_height = max(h for w, h in self.image_sizes)
            min_width = min(w for w, h in self.image_sizes)
            min_height = min(h for w, h in self.image_sizes)
            
            # Calculate megapixels
            avg_mpx = (avg_width * avg_height) / 1_000_000
            max_mpx = (max_width * max_height) / 1_000_000
            
            print(f"IMAGE SIZE ANALYSIS:")
            print(f"  Average: {avg_width:.0f}x{avg_height:.0f} ({avg_mpx:.1f} MP)")
            print(f"  Max: {max_width}x{max_height} ({max_mpx:.1f} MP)")
            print(f"  Min: {min_width}x{min_height}")
        print()
        
        # Frame timing analysis
        avg_frame = sum(self.frame_delays) / len(self.frame_delays)
        min_frame = min(self.frame_delays)
        max_frame = max(self.frame_delays)
        frame_budget = 1000 / self.target_fps
        
        print(f"FRAME TIMING (ms):")
        print(f"  Average: {avg_frame:.2f}ms")
        print(f"  Min: {min_frame:.2f}ms")
        print(f"  Max: {max_frame:.2f}ms")
        print(f"  Budget: {frame_budget:.2f}ms ({self.target_fps}fps)")
        
        on_time = sum(1 for d in self.frame_delays if d <= frame_budget * 1.1)
        late = len(self.frame_delays) - on_time
        on_time_pct = (on_time / len(self.frame_delays)) * 100
        
        print(f"  On-time: {on_time}/{len(self.frame_delays)} ({on_time_pct:.1f}%)")
        print(f"  Late: {late}")
        print()
        
        # Cycle timing analysis
        avg_cycle = sum(self.cycle_delays) / len(self.cycle_delays)
        min_cycle = min(self.cycle_delays)
        max_cycle = max(self.cycle_delays)
        
        print(f"CYCLE TIMING (ms):")
        print(f"  Average: {avg_cycle:.2f}ms")
        print(f"  Min: {min_cycle:.2f}ms")
        print(f"  Max: {max_cycle:.2f}ms")
        print()
        
        # Load timing analysis
        avg_load = sum(self.load_times) / len(self.load_times)
        min_load = min(self.load_times)
        max_load = max(self.load_times)
        
        print(f"LOAD TIMING (ms):")
        print(f"  Average: {avg_load:.2f}ms")
        print(f"  Min: {min_load:.2f}ms")
        print(f"  Max: {max_load:.2f}ms")
        print()
        
        # Distribution analysis
        print(f"FRAME DELAY DISTRIBUTION:")
        buckets = {
            "0-10ms": 0,
            "10-15ms": 0,
            "15-20ms (BUDGET)": 0,
            "20-30ms": 0,
            "30-50ms": 0,
            "50ms+": 0
        }
        
        for delay in self.frame_delays:
            if delay < 10:
                buckets["0-10ms"] += 1
            elif delay < 15:
                buckets["10-15ms"] += 1
            elif delay < 20:
                buckets["15-20ms (BUDGET)"] += 1
            elif delay < 30:
                buckets["20-30ms"] += 1
            elif delay < 50:
                buckets["30-50ms"] += 1
            else:
                buckets["50ms+"] += 1
        
        for bucket, count in buckets.items():
            pct = (count / len(self.frame_delays)) * 100
            print(f"  {bucket}: {count} ({pct:.1f}%)")
        
        print(f"{'='*70}\n")
        
        # Close window after 3 seconds
        QTimer.singleShot(3000, self.close)


def run_visual_test(media_path: Optional[Path] = None, speed: int = 95, duration: float = 20.0):
    """Run visual cycle timing test."""
    
    if media_path and media_path.exists():
        # Use real media from specified path
        print(f"\nLoading images from: {media_path}")
        
        # Find all image files
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
            image_files.extend(media_path.glob(ext))
            image_files.extend(media_path.glob(ext.upper()))
        
        if not image_files:
            print(f"WARNING: No images found in {media_path}, generating test images instead")
            media_path = None
        else:
            print(f"Found {len(image_files)} images")
            # Use relative paths from parent directory
            test_dir = media_path.parent
            # Use ALL images - no limit
            image_paths = [img.relative_to(test_dir) for img in sorted(image_files)]
            print(f"Using all {len(image_paths)} images for test")
    
    if not media_path:
        # Generate test images
        from PyQt6.QtGui import QPainter, QColor
        
        test_dir = Path("test_images")
        test_dir.mkdir(exist_ok=True)
        
        print(f"\nGenerating test images in: {test_dir}")
        
        image_paths = []
        for i in range(20):
            img_path = test_dir / f"test_image_{i:02d}.jpg"
            if not img_path.exists():
                img = QImage(800, 600, QImage.Format.Format_RGB888)
                painter = QPainter(img)
                color = QColor.fromHsv((i * 18) % 360, 200, 200)
                painter.fillRect(0, 0, 800, 600, color)
                painter.end()
                img.save(str(img_path), "JPEG", 90)
            
            image_paths.append(Path(img_path.name))
    
    # Create theme
    theme = ThemeConfig(
        name="Visual Test Theme",
        image_path=image_paths,
        enabled=True
    )
    
    # Create ThemeBank
    theme_bank = ThemeBank(themes=[theme], root_path=test_dir)
    theme_bank.set_active_themes(primary_index=1)
    
    print(f"\nThemeBank created with {len(image_paths)} images")
    print("Using lookahead preloading (next 15 images will be preloaded during cycling)\n")
    
    # Create Qt application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    window = CycleTimingTestWindow(
        theme_bank=theme_bank,
        target_fps=60,
        cycle_speed=speed,
        test_duration_seconds=duration
    )
    window.show()
    
    # Run test
    app.exec()
    
    print("\n✓ Visual cycle timing test complete")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Visual media cycling timing test")
    parser.add_argument(
        "--media-path",
        type=Path,
        help="Path to directory containing images to test (e.g., MEDIA/Images)"
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=95,
        choices=[70, 80, 90, 95, 100],
        help="Cycle speed to test (default: 95)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=20.0,
        help="Test duration in seconds (default: 20.0)"
    )
    
    args = parser.parse_args()
    
    run_visual_test(media_path=args.media_path, speed=args.speed, duration=args.duration)
