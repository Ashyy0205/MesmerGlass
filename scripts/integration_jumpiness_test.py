"""Integration test for visual jumpiness with all effects combined.

Tests the exact scenario from the "Jumpy" cuelist with "overstim" playback:
- Spiral overlay (sawtooth, speed 80, opacity 0.56, reversed)
- Media cycling (speed 100, no fade, exponential zoom 0.48)
- Text rendering (centered_sync, opacity 0.59)
- All running simultaneously at 60 FPS

This simulates the real app scenario where jumpiness is observed.
"""

import sys
import time
import math
from pathlib import Path
from typing import Optional
import psutil

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import QTimer, Qt, QRectF
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QFont

from mesmerglass.content.themebank import ThemeBank


def create_simple_spiral(width: int, height: int, phase: float, opacity: float = 0.56) -> QPixmap:
    """Create a simple rotating spiral for testing (simplified version)."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Draw simple spiral arms
    center_x = width / 2
    center_y = height / 2
    max_radius = min(width, height) / 2
    
    # Sawtooth spiral with 8 arms
    num_arms = 8
    pen = QPen(QColor(255, 255, 255, int(255 * opacity)))
    pen.setWidth(3)
    painter.setPen(pen)
    
    for arm in range(num_arms):
        arm_angle_offset = (arm / num_arms) * 2 * 3.14159
        
        # Draw spiral arm
        prev_x = None
        prev_y = None
        for r in range(0, int(max_radius), 5):
            # Sawtooth pattern
            angle = (r / max_radius) * 6 * 3.14159 + phase + arm_angle_offset
            x = center_x + r * math.cos(angle)
            y = center_y + r * math.sin(angle)
            
            if prev_x is not None:
                painter.drawLine(int(prev_x), int(prev_y), int(x), int(y))
            
            prev_x, prev_y = x, y
    
    painter.end()
    return pixmap


class IntegrationTestWindow(QLabel):
    """Test window that combines all visual effects."""
    
    def __init__(self, media_path: Path, duration_seconds: float):
        super().__init__()
        
        # Window setup - fullscreen overlay simulation
        self.setWindowTitle("Integration Jumpiness Test")
        self.setGeometry(100, 100, 1920, 1080)
        self.setStyleSheet("background-color: black;")
        
        # Test parameters
        self.duration_seconds = duration_seconds
        self.media_path = media_path
        
        # ThemeBank setup (media cycling)
        print(f"\nLoading images from: {media_path}")
        
        # Create a simple theme config
        from mesmerglass.content.theme import ThemeConfig
        theme_config = ThemeConfig(
            name="test_theme",
            enabled=True,
            image_path=[],  # Will be populated
            animation_path=[],
            font_path=[],
            text_line=[]
        )
        
        # Find all images
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        image_files = []
        for ext in image_extensions:
            image_files.extend(media_path.rglob(f'*{ext}'))
            image_files.extend(media_path.rglob(f'*{ext.upper()}'))
        
        # Make paths relative to media_path and convert to strings
        theme_config.image_path = [str(img.relative_to(media_path)) for img in image_files]
        
        print(f"Found {len(theme_config.image_path)} images")
        
        self.theme_bank = ThemeBank([theme_config], media_path)
        self.theme_bank.set_active_themes(primary_index=1)  # 1-indexed!
        
        # Spiral setup (simplified for testing)
        self.spiral_phase = 0.0
        self.spiral_rotation_speed = 80.0  # degrees per second
        self.spiral_opacity = 0.56
        
        # Media cycling parameters (from "overstim" playback)
        self.cycle_speed = 100  # Speed 100 = ~3-4 frames per image at 60fps
        self.fade_duration = 0.0  # No fade
        self.zoom_mode = "exponential"
        self.zoom_rate = 0.48
        
        # Text parameters
        self.text_enabled = True
        self.text_opacity = 0.59
        self.text_mode = "centered_sync"
        self.current_text = "OBEY AND SURRENDER"
        
        # Timing state
        self.frame_count = 0
        self.cycle_count = 0
        self.start_time = time.perf_counter()
        self.last_cycle_time = self.start_time
        self.frames_since_last_cycle = 0
        
        # Current media state
        self.current_pixmap: Optional[QPixmap] = None
        self.current_zoom_scale = 1.0
        self.zoom_progress = 0.0  # 0.0 to 1.0 over cycle duration
        
        # Performance tracking
        self.frame_times = []
        self.last_frame_time = self.start_time
        self.late_frames = 0
        
        # Memory tracking
        self.process = psutil.Process()
        self.initial_memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory_mb = self.initial_memory_mb
        
        # 60 FPS timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(16)  # ~60 FPS (16.67ms)
        
        print(f"\n{'='*70}")
        print(f"INTEGRATION JUMPINESS TEST")
        print(f"{'='*70}")
        print(f"Spiral: sawtooth, speed 80, opacity 0.56, reversed")
        print(f"Media: speed 100, no fade, exponential zoom 0.48")
        print(f"Text: centered_sync, opacity 0.59")
        print(f"Duration: {duration_seconds}s")
        print(f"Target FPS: 60")
        print(f"{'='*70}\n")
    
    def _update(self) -> None:
        """Update called every frame (~60 FPS)."""
        current_time = time.perf_counter()
        elapsed = current_time - self.start_time
        
        # Track frame timing
        frame_delta = (current_time - self.last_frame_time) * 1000  # ms
        self.frame_times.append(frame_delta)
        if frame_delta > 16.67:  # Late frame
            self.late_frames += 1
        self.last_frame_time = current_time
        
        # Memory tracking
        current_memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory_mb = max(self.peak_memory_mb, current_memory_mb)
        
        # Check if test complete
        if elapsed >= self.duration_seconds:
            self._finish_test()
            return
        
        # Update spiral phase
        dt = 1.0 / 60.0  # Assume 60 FPS
        self.spiral_phase += (self.spiral_rotation_speed / 360.0) * 2 * 3.14159 * dt
        
        # Calculate frames per cycle from speed (100 = ~3 frames)
        frames_per_cycle = max(1, int(300 / max(1, self.cycle_speed)))
        
        # Check if we need to cycle image
        self.frames_since_last_cycle += 1
        if self.frames_since_last_cycle >= frames_per_cycle:
            self._cycle_image()
            self.frames_since_last_cycle = 0
            self.last_cycle_time = current_time
            self.zoom_progress = 0.0
        
        # Update zoom progress (exponential)
        cycle_duration = frames_per_cycle / 60.0  # seconds
        cycle_elapsed = current_time - self.last_cycle_time
        self.zoom_progress = min(1.0, cycle_elapsed / cycle_duration)
        
        # Calculate zoom scale (exponential mode)
        if self.zoom_mode == "exponential":
            # Exponential zoom: scale = 1.0 + rate * (exp(progress) - 1) / (e - 1)
            import math
            normalized = (math.exp(self.zoom_progress) - 1.0) / (math.e - 1.0)
            self.current_zoom_scale = 1.0 + self.zoom_rate * normalized
        
        self.frame_count += 1
        
        # Trigger repaint
        self.update()
    
    def _cycle_image(self) -> None:
        """Cycle to next image."""
        self.cycle_count += 1
        
        # Get next image from ThemeBank (primary theme)
        image_data = self.theme_bank.get_image(alternate=False)
        if image_data:
            # Convert numpy array to QPixmap
            from PyQt6.QtGui import QImage
            height, width, channels = image_data.data.shape
            bytes_per_line = channels * width
            q_image = QImage(
                image_data.data.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGBA8888
            )
            self.current_pixmap = QPixmap.fromImage(q_image)
            
            # Update text if synced
            if self.text_mode == "centered_sync":
                texts = [
                    "OBEY AND SURRENDER",
                    "DEEPER AND DEEPER",
                    "MINDLESS BLISS",
                    "SUBMIT COMPLETELY",
                    "EMPTY YOUR MIND",
                    "PLEASURE AND OBEDIENCE"
                ]
                self.current_text = texts[self.cycle_count % len(texts)]
    
    def paintEvent(self, event):
        """Render combined visual effects."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Fill background
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        # Render media with zoom
        if self.current_pixmap:
            # Calculate scaled size
            window_width = self.width()
            window_height = self.height()
            
            # Scale pixmap to fit window
            scaled_pixmap = self.current_pixmap.scaled(
                window_width,
                window_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Apply zoom by scaling further
            zoomed_width = int(scaled_pixmap.width() * self.current_zoom_scale)
            zoomed_height = int(scaled_pixmap.height() * self.current_zoom_scale)
            
            if zoomed_width > 0 and zoomed_height > 0:
                zoomed_pixmap = scaled_pixmap.scaled(
                    zoomed_width,
                    zoomed_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # Center the zoomed pixmap
                x = (window_width - zoomed_width) // 2
                y = (window_height - zoomed_height) // 2
                
                painter.drawPixmap(x, y, zoomed_pixmap)
        
        # Render spiral overlay
        spiral_pixmap = create_simple_spiral(self.width(), self.height(), self.spiral_phase, self.spiral_opacity)
        if spiral_pixmap:
            painter.drawPixmap(0, 0, spiral_pixmap)
        
        # Render text
        if self.text_enabled and self.current_text:
            painter.setOpacity(self.text_opacity)
            painter.setPen(QColor(255, 255, 255))
            
            # Large centered text
            font = QFont("Arial", 48, QFont.Weight.Bold)
            painter.setFont(font)
            
            text_rect = self.rect()
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.current_text)
            
            painter.setOpacity(1.0)
    
    def _finish_test(self) -> None:
        """Complete test and show results."""
        self.timer.stop()
        
        elapsed = time.perf_counter() - self.start_time
        avg_fps = self.frame_count / elapsed
        
        # Calculate timing stats
        avg_frame_time = sum(self.frame_times) / len(self.frame_times) if self.frame_times else 0
        max_frame_time = max(self.frame_times) if self.frame_times else 0
        min_frame_time = min(self.frame_times) if self.frame_times else 0
        
        # On-time percentage
        on_time_frames = self.frame_count - self.late_frames
        on_time_percent = (on_time_frames / self.frame_count * 100) if self.frame_count > 0 else 0
        
        # Memory stats
        final_memory_mb = self.process.memory_info().rss / 1024 / 1024
        memory_increase_mb = final_memory_mb - self.initial_memory_mb
        
        print(f"\n{'='*70}")
        print(f"TEST COMPLETE")
        print(f"{'='*70}")
        print(f"Duration: {elapsed:.2f}s")
        print(f"Total Frames: {self.frame_count}")
        print(f"Total Cycles: {self.cycle_count}")
        print(f"Actual FPS: {avg_fps:.2f} (target: 60)")
        print(f"")
        print(f"MEMORY USAGE:")
        print(f"  Initial: {self.initial_memory_mb:.1f} MB")
        print(f"  Final: {final_memory_mb:.1f} MB")
        print(f"  Peak: {self.peak_memory_mb:.1f} MB")
        print(f"  Increase: +{memory_increase_mb:.1f} MB")
        print(f"")
        print(f"FRAME TIMING (ms):")
        print(f"  Average: {avg_frame_time:.2f}ms")
        print(f"  Min: {min_frame_time:.2f}ms")
        print(f"  Max: {max_frame_time:.2f}ms")
        print(f"  Budget: 16.67ms (60fps)")
        print(f"  On-time: {on_time_frames}/{self.frame_count} ({on_time_percent:.1f}%)")
        print(f"  Late: {self.late_frames}")
        print(f"")
        
        # Frame distribution
        bins = [0, 10, 15, 20, 30, 50, float('inf')]
        labels = ["0-10ms", "10-15ms", "15-20ms (BUDGET)", "20-30ms", "30-50ms", "50ms+"]
        counts = [0] * len(labels)
        
        for ft in self.frame_times[-1000:]:  # Last 1000 frames
            for i, (low, high) in enumerate(zip(bins[:-1], bins[1:])):
                if low <= ft < high:
                    counts[i] += 1
                    break
        
        print(f"FRAME DELAY DISTRIBUTION (last 1000 frames):")
        total_sampled = sum(counts)
        for label, count in zip(labels, counts):
            percent = (count / total_sampled * 100) if total_sampled > 0 else 0
            print(f"  {label}: {count} ({percent:.1f}%)")
        
        print(f"{'='*70}\n")
        print("✓ Integration jumpiness test complete")
        
        QApplication.quit()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Integration test for visual jumpiness")
    parser.add_argument(
        "--media-path",
        type=Path,
        default=Path.home() / "Desktop" / "Images",
        help="Path to media directory"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Test duration in seconds (default: 30)"
    )
    
    args = parser.parse_args()
    
    if not args.media_path.exists():
        print(f"Error: Media path does not exist: {args.media_path}")
        return 1
    
    app = QApplication(sys.argv)
    window = IntegrationTestWindow(args.media_path, args.duration)
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
