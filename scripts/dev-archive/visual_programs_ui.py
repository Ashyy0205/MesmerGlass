#!/usr/bin/env python3
"""
Phase 6 Visual Programs Demo with Full UI

Interactive demo with controls for:
- Visual program selection (1-7)
- Spiral settings (intensity, arms, type, direction, rate)
- Background effects (kaleidoscope, zoom)
- Playback controls (pause/resume)
- Real-time parameter adjustment

Usage:
    python scripts/visual_programs_ui.py
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QComboBox, QGroupBox, QCheckBox,
    QSpinBox
)

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.mesmerloom.compositor import LoomCompositor
from mesmerglass.content.video import VideoStreamer
from mesmerglass.content.media import load_image_sync
from mesmerglass.content.texture import upload_image_to_gpu
from mesmerglass.content.text_renderer import TextRenderer


class VisualProgramsWindow(LoomCompositor):
    """Compositor window with visual programs."""
    
    def __init__(self, video_paths: list[Path], image_paths: list[Path], director: SpiralDirector):
        super().__init__(director)
        self.video_paths = video_paths
        self.image_paths = image_paths
        self.kaleidoscope_active = False
        
        # Media loaders
        self.streamer = VideoStreamer(buffer_size=90)
        self.text_renderer = TextRenderer()
        
        # Text lines
        self.text_lines = [
            "You are getting sleepy",
            "Deeper and deeper",
            "So relaxed",
            "Let go",
            "Sink down"
        ]
        
        # Text effect state (separate from visual programs)
        self.text_effect_enabled = False
        self.text_effect_speed = 1.0  # Multiplier for text cycling speed
        self.text_index = 0
        self.text_frame_counter = 0
        self.text_update_period = 60  # Frames between text changes
        
        # Visual programs state (only control media timing, not text)
        self.current_visual_index = 0
        self.current_visual = None
        self.paused = False
        self.frame_count = 0
        self.visual_names = [
            "Normal Speed (48 frames)",
            "Slow Speed (72 frames)",
            "Accelerating Zoom",
            "Very Slow (120 frames)",
            "Fast Speed (24 frames)",
            "Multi-Image",
            "Video Playback"
        ]
        
        # CRITICAL: Activate compositor
        self.set_active(True)
        
        # Initial spiral config
        self.director.set_intensity(0.4)
        self.director.set_arm_count(5)
        self.director.set_spiral_type(3)
        
        # Window setup
        self.resize(1400, 900)
        self.setWindowTitle("MesmerGlass - Visual Programs Demo (Phase 6)")
        self.show()
        
        # Import and create visuals (after Qt OpenGL initialized)
        self._create_visuals()
        
        # Delayed start
        QTimer.singleShot(100, lambda: self._delayed_start())
    
    def _delayed_start(self):
        """Start first visual after GL is fully ready."""
        print("[DEBUG] Starting first visual...")
        
        # Start with first visual
        self.switch_visual(0)
        
        # Update timer (60 FPS)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_frame)
        self.update_timer.start(16)
    
    def _create_visuals(self):
        """Create all visual program instances (AFTER show() to avoid pygame conflict)."""
        from mesmerglass.mesmerloom.visuals import (
            SimpleVisual, SubTextVisual, AccelerateVisual,
            SlowFlashVisual, FlashTextVisual, ParallelImagesVisual, AnimationVisual
        )
        
        # Visual programs now only control media timing, not text
        # Text is controlled separately via UI
        self.visuals = [
            # 1. SimpleVisual - Basic image slideshow
            SimpleVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral,
                on_preload_image=None
            ),
            
            # 2. SubTextVisual - Slower image changes (text handled separately)
            SimpleVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral,
                on_preload_image=None,
                frame_period=72  # Slower than default
            ),
            
            # 3. AccelerateVisual - Images with zoom effect
            AccelerateVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image_zoom,
                on_rotate_spiral=lambda d: None
            ),
            
            # 4. SlowFlashVisual - Very slow image cycling
            SlowFlashVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral
            ),
            
            # 5. FlashTextVisual - Rapid image cycling (text handled separately)
            SimpleVisual(
                image_paths=self.image_paths,
                on_change_image=self._on_change_image,
                on_rotate_spiral=self._on_rotate_spiral,
                on_preload_image=None,
                frame_period=24  # Fast cycling
            ),
            
            # 6. ParallelImagesVisual - Multi-slot images
            ParallelImagesVisual(
                image_paths=self.image_paths,
                on_change_image=lambda slot, idx: self._on_change_image(idx),
                on_rotate_spiral=self._on_rotate_spiral,
                slot_count=1
            ),
            
            # 7. AnimationVisual - Video playback
            AnimationVisual(
                video_paths=self.video_paths,
                on_change_video=self._on_change_video,
                on_rotate_spiral=self._on_rotate_spiral,
                video_duration=180,
                video_count=len(self.video_paths)
            )
        ]
    
    # ===== Visual Program Callbacks =====
    
    def _on_change_image(self, index: int):
        """Load and display image using GPU texture upload."""
        if 0 <= index < len(self.image_paths):
            path = self.image_paths[index]
            try:
                img_data = load_image_sync(str(path))
                if not img_data:
                    return
                
                texture_id = upload_image_to_gpu(img_data, generate_mipmaps=False)
                self.set_background_texture(
                    texture_id,
                    zoom=1.0,
                    image_width=img_data.width,
                    image_height=img_data.height
                )
                
            except Exception as e:
                print(f"[ERROR] Failed to load image: {e}")
    
    def _on_change_image_zoom(self, index: int, zoom: float):
        """Load image with zoom (AccelerateVisual)."""
        if 0 <= index < len(self.image_paths):
            path = self.image_paths[index]
            try:
                img_data = load_image_sync(str(path))
                if not img_data:
                    return
                
                actual_zoom = 1.0 + zoom * 0.5
                texture_id = upload_image_to_gpu(img_data, generate_mipmaps=False)
                self.set_background_texture(
                    texture_id,
                    zoom=actual_zoom,
                    image_width=img_data.width,
                    image_height=img_data.height
                )
                
            except Exception as e:
                print(f"[ERROR] Failed to load image: {e}")
    
    def _on_change_video(self, index: int):
        """Load and start video (AnimationVisual)."""
        if 0 <= index < len(self.video_paths):
            path = self.video_paths[index]
            self.streamer.load_video(path)
    
    def _on_change_text(self, text: str):
        """Render and display text."""
        if text:
            self.clear_text_textures()
            rendered = self.text_renderer.render(text)
            if rendered and rendered.texture_data is not None:
                self.add_text_texture(rendered.texture_data, x=0.5, y=0.5, alpha=1.0, scale=1.5)
    
    def _update_text_effect(self):
        """Update independent text effect (separate from visual programs)."""
        if not self.text_effect_enabled:
            self.clear_text_textures()
            return
        
        self.text_frame_counter += 1
        
        # Update text based on speed setting
        actual_period = int(self.text_update_period / self.text_effect_speed)
        if self.text_frame_counter >= actual_period:
            self.text_frame_counter = 0
            self.text_index = (self.text_index + 1) % len(self.text_lines)
            self._on_change_text(self.text_lines[self.text_index])
    
    def _on_rotate_spiral(self):
        """Spiral rotation callback."""
        pass
    
    # ===== Update Loop =====
    
    def _update_frame(self):
        """Update visual program and render."""
        if self.paused or not self.current_visual:
            return
        
        try:
            # Update visual program (media timing only)
            cycler = self.current_visual.get_cycler()
            if cycler:
                cycler.advance()
                self.frame_count += 1
                
                # Update video if AnimationVisual
                if self.current_visual.__class__.__name__ == 'AnimationVisual':
                    self._update_video()
                
                # Update independent text effect
                self._update_text_effect()
                
                self.update()
                
                # Check completion
                if self.current_visual.complete():
                    print(f"✓ {self.visual_names[self.current_visual_index]} complete ({self.frame_count} frames)")
                    self.paused = True
                    
        except Exception as e:
            print(f"[ERROR in _update_frame] {e}")
            import traceback
            traceback.print_exc()
            self.paused = True
    
    def _update_video(self):
        """Update video playback (for AnimationVisual)."""
        self.streamer.advance_frame(global_fps=60.0)
        frame = self.streamer.get_current_frame()
        if frame:
            self.set_background_video_frame(frame.data, frame.width, frame.height, zoom=1.0)
    
    # ===== Visual Switching =====
    
    def switch_visual(self, index: int):
        """Switch to different visual program."""
        if 0 <= index < len(self.visuals):
            print(f"\n{'='*60}")
            print(f"Switching to: {self.visual_names[index]}")
            print(f"{'='*60}\n")
            
            self.current_visual_index = index
            self.current_visual = self.visuals[index]
            self.current_visual.reset()
            self.frame_count = 0
            self.paused = False
            
            # Trigger first frame
            cycler = self.current_visual.get_cycler()
            if cycler:
                cycler.advance()
                self.update()
    
    def closeEvent(self, event):
        """Cleanup on window close."""
        print("\n[Cleaning up...]")
        self.update_timer.stop()
        self.streamer.stop()
        event.accept()


class ControlPanel(QWidget):
    """Control panel for visual programs and spiral settings."""
    
    def __init__(self, compositor: VisualProgramsWindow):
        super().__init__()
        self.compositor = compositor
        self.director = compositor.director
        
        self.setWindowTitle("Visual Programs - Control Panel")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Visual Program Selection
        layout.addWidget(self._create_visual_group())
        
        # Playback Controls
        layout.addWidget(self._create_playback_group())
        
        # Spiral Settings
        layout.addWidget(self._create_spiral_group())
        
        # Text Effect Settings (independent control)
        layout.addWidget(self._create_text_group())
        
        # Background Effects
        layout.addWidget(self._create_effects_group())
        
        # Status
        layout.addWidget(self._create_status_group())
        
        layout.addStretch()
        self.setLayout(layout)
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status)
        self.update_timer.start(100)
    
    def _create_visual_group(self):
        """Create visual program selection group."""
        group = QGroupBox("Media Timing Program")
        layout = QVBoxLayout()
        
        self.visual_combo = QComboBox()
        self.visual_combo.addItems(self.compositor.visual_names)
        self.visual_combo.currentIndexChanged.connect(self._on_visual_changed)
        layout.addWidget(self.visual_combo)
        
        group.setLayout(layout)
        return group
    
    def _create_playback_group(self):
        """Create playback controls group."""
        group = QGroupBox("Playback")
        layout = QHBoxLayout()
        
        self.play_btn = QPushButton("⏸ Pause")
        self.play_btn.clicked.connect(self._toggle_pause)
        layout.addWidget(self.play_btn)
        
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.clicked.connect(self._reset_visual)
        layout.addWidget(self.reset_btn)
        
        group.setLayout(layout)
        return group
    
    def _create_spiral_group(self):
        """Create spiral settings group."""
        group = QGroupBox("Spiral Settings")
        layout = QVBoxLayout()
        
        # Intensity
        intensity_layout = QHBoxLayout()
        intensity_layout.addWidget(QLabel("Intensity:"))
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(0, 100)
        self.intensity_slider.setValue(40)
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        intensity_layout.addWidget(self.intensity_slider)
        self.intensity_label = QLabel("40%")
        intensity_layout.addWidget(self.intensity_label)
        layout.addLayout(intensity_layout)
        
        # Arm Count
        arms_layout = QHBoxLayout()
        arms_layout.addWidget(QLabel("Arms:"))
        self.arms_spin = QSpinBox()
        self.arms_spin.setRange(1, 12)
        self.arms_spin.setValue(5)
        self.arms_spin.valueChanged.connect(self._on_arms_changed)
        arms_layout.addWidget(self.arms_spin)
        arms_layout.addStretch()
        layout.addLayout(arms_layout)
        
        # Spiral Type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "0: Logarithmic",
            "1: Hyperbolic",
            "2: Archimedes",
            "3: Linear",
            "4: Quadratic",
            "5: Inverse",
            "6: Exponential"
        ])
        self.type_combo.setCurrentIndex(3)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)
        
        # Rotation (manual control removed - handled by visual programs)
        # Rotation Rate
        rate_layout = QHBoxLayout()
        rate_layout.addWidget(QLabel("Manual Rotation:"))
        self.rotate_left_btn = QPushButton("← CCW")
        self.rotate_left_btn.clicked.connect(lambda: self._rotate_spiral(-2.0))
        rate_layout.addWidget(self.rotate_left_btn)
        self.rotate_right_btn = QPushButton("CW →")
        self.rotate_right_btn.clicked.connect(lambda: self._rotate_spiral(2.0))
        rate_layout.addWidget(self.rotate_right_btn)
        layout.addLayout(rate_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_text_group(self):
        """Create text effect settings group."""
        group = QGroupBox("Text Effect (Independent)")
        layout = QVBoxLayout()
        
        # Enable/Disable
        self.text_enabled_check = QCheckBox("Enable Text Overlay")
        self.text_enabled_check.stateChanged.connect(self._on_text_enabled_changed)
        layout.addWidget(self.text_enabled_check)
        
        # Speed
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Text Speed:"))
        self.text_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_speed_slider.setRange(10, 300)  # 0.1x to 3.0x
        self.text_speed_slider.setValue(100)  # 1.0x
        self.text_speed_slider.valueChanged.connect(self._on_text_speed_changed)
        speed_layout.addWidget(self.text_speed_slider)
        self.text_speed_label = QLabel("1.0x")
        speed_layout.addWidget(self.text_speed_label)
        layout.addLayout(speed_layout)
        
        # Current text display
        self.current_text_label = QLabel("Current: (none)")
        self.current_text_label.setWordWrap(True)
        self.current_text_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.current_text_label)
        
        group.setLayout(layout)
        return group
    
    def _create_effects_group(self):
        """Create background effects group."""
        group = QGroupBox("Background Effects")
        layout = QVBoxLayout()
        
        self.kaleidoscope_check = QCheckBox("Kaleidoscope")
        self.kaleidoscope_check.stateChanged.connect(self._on_kaleidoscope_changed)
        layout.addWidget(self.kaleidoscope_check)
        
        group.setLayout(layout)
        return group
    
    def _create_status_group(self):
        """Create status display group."""
        group = QGroupBox("Status")
        layout = QVBoxLayout()
        
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        self.frame_label = QLabel("Frame: 0")
        layout.addWidget(self.frame_label)
        
        self.progress_label = QLabel("Progress: 0%")
        layout.addWidget(self.progress_label)
        
        group.setLayout(layout)
        return group
    
    # ===== Event Handlers =====
    
    def _on_visual_changed(self, index):
        """Visual program selection changed."""
        self.compositor.switch_visual(index)
    
    def _toggle_pause(self):
        """Toggle pause/resume."""
        self.compositor.paused = not self.compositor.paused
        self.play_btn.setText("▶ Play" if self.compositor.paused else "⏸ Pause")
    
    def _reset_visual(self):
        """Reset current visual."""
        self.compositor.switch_visual(self.compositor.current_visual_index)
    
    def _on_intensity_changed(self, value):
        """Spiral intensity changed."""
        intensity = value / 100.0
        self.director.set_intensity(intensity)
        self.intensity_label.setText(f"{value}%")
    
    def _on_arms_changed(self, value):
        """Spiral arm count changed."""
        self.director.set_arm_count(value)
    
    def _on_type_changed(self, index):
        """Spiral type changed."""
        self.director.set_spiral_type(index)
    
    def _rotate_spiral(self, amount: float):
        """Manually rotate spiral."""
        self.director.rotate_spiral(amount)
    
    def _on_text_enabled_changed(self, state):
        """Text effect enabled/disabled."""
        enabled = (state == Qt.CheckState.Checked)
        self.compositor.text_effect_enabled = enabled
        if enabled:
            # Show first text immediately
            self.compositor.text_index = 0
            self.compositor.text_frame_counter = 0
            self.compositor._on_change_text(self.compositor.text_lines[0])
        else:
            self.compositor.clear_text_textures()
    
    def _on_text_speed_changed(self, value):
        """Text speed changed."""
        speed = value / 100.0  # 0.1 to 3.0
        self.compositor.text_effect_speed = speed
        self.text_speed_label.setText(f"{speed:.1f}x")
    
    def _on_kaleidoscope_changed(self, state):
        """Kaleidoscope effect toggled."""
        enabled = (state == Qt.CheckState.Checked)
        self.compositor.set_background_kaleidoscope(enabled)
    
    def _update_status(self):
        """Update status display."""
        if not self.compositor.current_visual:
            return
        
        # Status
        if self.compositor.paused:
            status = "⏸ Paused"
        elif self.compositor.current_visual.complete():
            status = "✓ Complete"
        else:
            status = "▶ Playing"
        self.status_label.setText(status)
        
        # Frame count
        self.frame_label.setText(f"Frame: {self.compositor.frame_count}")
        
        # Progress
        progress = self.compositor.current_visual.progress() * 100
        self.progress_label.setText(f"Progress: {progress:.1f}%")
        
        # Update current text display
        if self.compositor.text_effect_enabled:
            current_text = self.compositor.text_lines[self.compositor.text_index]
            self.current_text_label.setText(f"Current: {current_text}")
        else:
            self.current_text_label.setText("Current: (disabled)")


def main():
    """Run visual programs demo with UI."""
    app = QApplication(sys.argv)
    
    # Load media paths
    media_dir = Path(__file__).parent.parent / "MEDIA"
    video_dir = media_dir / "Videos"
    image_dir = media_dir / "Images"
    
    video_paths = sorted(video_dir.glob("*.mp4"))[:10]
    image_paths = sorted(image_dir.glob("*.jpg"))[:20]
    
    if not video_paths:
        print("[ERROR] No videos found in MEDIA/Videos")
        return 1
    
    if not image_paths:
        print("[ERROR] No images found in MEDIA/Images")
        return 1
    
    print(f"\n[OK] Loaded {len(video_paths)} videos, {len(image_paths)} images")
    
    # Create director
    director = SpiralDirector()
    
    # Create compositor window
    compositor = VisualProgramsWindow(video_paths, image_paths, director)
    
    # Create control panel
    control_panel = ControlPanel(compositor)
    control_panel.show()
    
    # Position windows side by side
    compositor.move(100, 100)
    control_panel.move(compositor.x() + compositor.width() + 10, 100)
    
    print("\n[OK] Visual Programs Demo Ready")
    print("     Use control panel to adjust settings\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
