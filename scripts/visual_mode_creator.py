"""
Visual Mode Creator

Create and save custom visual modes with all settings:
- Spiral parameters (type, speed, opacity, colors)
- Media settings (images/videos/both, cycling times)
- Text settings (enabled, effects, opacity)
- Zoom settings (rate, mode)
- Background opacity

Modes are saved to text files and can be loaded into the main application.
"""

import sys
import logging
import math
import json
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QTextEdit, QLineEdit, QCheckBox,
    QComboBox, QGroupBox, QSpinBox, QColorDialog, QFileDialog, QListWidget,
    QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

def _find_project_root(start: Path) -> Path:
    """Ascend from 'start' to locate the MesmerGlass project root.

    Heuristics:
    - Directory contains 'mesmerglass/' package AND 'MEDIA/' folder.
    - Fallback: first directory that contains 'mesmerglass/'.
    - Final fallback: the starting directory.
    """
    start = start.resolve()
    candidate = start
    fallback_pkg_root = None
    while True:
        has_pkg = (candidate / 'mesmerglass').is_dir()
        has_media = (candidate / 'MEDIA').is_dir()
        if has_pkg and has_media:
            return candidate
        if has_pkg and fallback_pkg_root is None:
            fallback_pkg_root = candidate
        if candidate.parent == candidate:
            # Reached filesystem root
            return fallback_pkg_root or start
        candidate = candidate.parent


# Compute and insert project root for imports reliably (script may be run from repo root)
PROJECT_ROOT = _find_project_root(Path(__file__).parent)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mesmerglass.mesmerloom.compositor import LoomCompositor
from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.content.texture import upload_image_to_gpu
from mesmerglass.content import media
from mesmerglass.content.text_renderer import TextRenderer, SplitMode
from mesmerglass.engine.text_director import TextDirector
import cv2
import numpy as np


class VisualModeCreator(QMainWindow):
    """Visual Mode Creator - design and save custom visual modes."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visual Mode Creator")
        self.setGeometry(100, 100, 1800, 950)
        
        # Create spiral director
        self.director = SpiralDirector()
        # Note: Intensity not set - reserved for future use (default=0.0)
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # Left side: Spiral compositor (16:9 aspect ratio)
        self.compositor = LoomCompositor(
            director=self.director,
            parent=self,
            trace=False,
            sim_flag=False,
            force_flag=False
        )
        self.compositor.setMinimumSize(1280, 720)
        self.compositor.setMaximumHeight(720)
        self.compositor.set_active(True)
        
        main_layout.addWidget(self.compositor, stretch=2)
        
        # Initialize text rendering system (will be set up after GL context ready)
        self.text_renderer = None
        self.text_director = None
        
        # Video playback state
        self.video_cap = None
        self.video_fps = 30.0
        self.video_frame_timer = None
        self.current_video_file = None
        self.video_first_frame = False  # Track first frame of new video for fade
        
        # Initialize Media Bank (load from shared config file)
        self._media_bank = []
        self._load_media_bank_config()
        
        # Right side: Controls (scrollable)
        from PyQt6.QtWidgets import QScrollArea, QFrame
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setSpacing(10)
        scroll.setWidget(controls_widget)
        main_layout.addWidget(scroll, stretch=1)
        
        # === Mode Name ===
        name_group = QGroupBox("Mode Name")
        name_layout = QVBoxLayout(name_group)
        self.mode_name_input = QLineEdit("Custom Mode")
        self.mode_name_input.setPlaceholderText("Enter mode name...")
        name_layout.addWidget(self.mode_name_input)
        controls_layout.addWidget(name_group)
        
        # === Spiral Settings ===
        spiral_group = QGroupBox("Spiral Settings")
        spiral_layout = QVBoxLayout(spiral_group)
        
        # Spiral Type
        spiral_layout.addWidget(QLabel("Spiral Type:"))
        self.spiral_type_combo = QComboBox()
        self.spiral_type_combo.addItems([
            "1 - Logarithmic",
            "2 - Quadratic (r²)",
            "3 - Linear (r)",
            "4 - Square Root (√r)",
            "5 - Inverse (|r-1|)",
            "6 - Power (r⁶)",
            "7 - Sawtooth"
        ])
        self.spiral_type_combo.setCurrentIndex(2)  # Linear default
        self.spiral_type_combo.currentIndexChanged.connect(self.on_spiral_type_changed)
        spiral_layout.addWidget(self.spiral_type_combo)
        
    # Spiral Opacity
        spiral_layout.addWidget(QLabel("Spiral Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(80)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        self.opacity_label = QLabel("80%")
        spiral_layout.addWidget(self.opacity_slider)
        spiral_layout.addWidget(self.opacity_label)
        
    # Rotation Speed
        spiral_layout.addWidget(QLabel("Rotation Speed:"))
        self.rotation_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_speed_slider.setRange(40, 400)  # 4.0 to 40.0x
        self.rotation_speed_slider.setValue(40)
        self.rotation_speed_slider.valueChanged.connect(self.on_rotation_speed_changed)
        self.rotation_speed_label = QLabel("4.0x")
        spiral_layout.addWidget(self.rotation_speed_slider)
        spiral_layout.addWidget(self.rotation_speed_label)
        
        # Spiral Reverse Direction
        self.spiral_reverse_check = QCheckBox("Reverse Spiral Direction")
        self.spiral_reverse_check.setChecked(False)
        self.spiral_reverse_check.stateChanged.connect(self.on_spiral_reverse_changed)
        spiral_layout.addWidget(self.spiral_reverse_check)
        
        # Spiral Colors
        color_layout = QHBoxLayout()
        self.arm_color_btn = QPushButton("Arm Color")
        self.arm_color_btn.clicked.connect(lambda: self.pick_color("arm"))
        self.gap_color_btn = QPushButton("Gap Color")
        self.gap_color_btn.clicked.connect(lambda: self.pick_color("gap"))
        color_layout.addWidget(self.arm_color_btn)
        color_layout.addWidget(self.gap_color_btn)
        spiral_layout.addLayout(color_layout)
        
        # Store colors
        self.arm_color = (1.0, 1.0, 1.0)  # White default
        self.gap_color = (0.0, 0.0, 0.0)  # Black default
        
        controls_layout.addWidget(spiral_group)
        
        # === Media Settings ===
        media_group = QGroupBox("Media Settings")
        media_layout = QVBoxLayout(media_group)
        
        # Media Mode
        media_layout.addWidget(QLabel("Media Mode:"))
        self.media_mode_combo = QComboBox()
        self.media_mode_combo.addItems([
            "Images & Videos",
            "Images Only",
            "Videos Only"
        ])
        # Default to showing both images and videos so demos work out of the box
        self.media_mode_combo.setCurrentIndex(0)  # Images & Videos default
        self.media_mode_combo.currentIndexChanged.connect(self.on_media_mode_changed)
        media_layout.addWidget(self.media_mode_combo)
        
        # Media Cycling Speed (for both images and videos)
        media_layout.addWidget(QLabel("Media Cycling Speed:"))
        self.media_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.media_speed_slider.setRange(1, 100)  # 1 = slowest (10s), 100 = fastest (0.05s)
        self.media_speed_slider.setValue(50)  # Medium speed default
        self.media_speed_slider.valueChanged.connect(self.on_media_speed_changed)
        self.media_speed_label = QLabel("50 (Medium)")
        media_layout.addWidget(self.media_speed_slider)
        media_layout.addWidget(self.media_speed_label)
        
        # Background Opacity
        media_layout.addWidget(QLabel("Background Opacity:"))
        self.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(100)
        self.bg_opacity_slider.valueChanged.connect(self.on_bg_opacity_changed)
        self.bg_opacity_label = QLabel("100%")
        media_layout.addWidget(self.bg_opacity_slider)
        media_layout.addWidget(self.bg_opacity_label)
        
        # Fade Duration (transition time between images/videos)
        media_layout.addWidget(QLabel("Media Fade Duration:"))
        self.fade_duration_slider = QSlider(Qt.Orientation.Horizontal)
        self.fade_duration_slider.setRange(0, 50)  # 0 to 5.0 seconds (stored as tenths)
        self.fade_duration_slider.setValue(5)  # Default 0.5 seconds
        self.fade_duration_slider.valueChanged.connect(self.on_fade_duration_changed)
        self.fade_duration_label = QLabel("0.5s")
        media_layout.addWidget(self.fade_duration_slider)
        media_layout.addWidget(self.fade_duration_label)
        
        # Media Bank Selection
        media_layout.addWidget(QLabel("─" * 30))  # Separator
        media_layout.addWidget(QLabel("Media Bank Selection:"))
        media_layout.addWidget(QLabel("Select which directories this mode uses:"))
        
        # Media Bank list with checkboxes
        self.list_media_bank = QListWidget()
        self.list_media_bank.setMaximumHeight(150)
        self.list_media_bank.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_media_bank.itemChanged.connect(lambda: self._update_bank_info())
        media_layout.addWidget(self.list_media_bank)
        
        # Bank management buttons
        bank_buttons_layout = QHBoxLayout()
        self.btn_add_to_bank = QPushButton("➕ Add Directory")
        self.btn_add_to_bank.clicked.connect(self._on_add_to_media_bank)
        self.btn_remove_from_bank = QPushButton("➖ Remove")
        self.btn_remove_from_bank.clicked.connect(self._on_remove_from_media_bank)
        self.btn_manage_bank = QPushButton("⚙ Manage Bank")
        self.btn_manage_bank.clicked.connect(self._on_manage_bank)
        bank_buttons_layout.addWidget(self.btn_add_to_bank)
        bank_buttons_layout.addWidget(self.btn_remove_from_bank)
        bank_buttons_layout.addWidget(self.btn_manage_bank)
        media_layout.addLayout(bank_buttons_layout)
        
        # Info label showing selected count
        self.lbl_bank_info = QLabel("")
        self.lbl_bank_info.setStyleSheet("color: #666; font-size: 9pt;")
        media_layout.addWidget(self.lbl_bank_info)
        
        # Populate Media Bank list
        self._refresh_media_bank_list()
        
        controls_layout.addWidget(media_group)
        
        # === Text Settings ===
        text_group = QGroupBox("Text Settings")
        text_layout = QVBoxLayout(text_group)
        
        # Text Enabled
        self.text_enabled_check = QCheckBox("Enable Text Overlay")
        self.text_enabled_check.setChecked(True)  # Default to enabled for testing
        self.text_enabled_check.stateChanged.connect(self.on_text_enabled_changed)
        text_layout.addWidget(self.text_enabled_check)
        
        # Text Opacity
        text_layout.addWidget(QLabel("Text Opacity:"))
        self.text_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity_slider.setRange(0, 100)
        self.text_opacity_slider.setValue(80)
        self.text_opacity_slider.valueChanged.connect(self.on_text_opacity_changed)
        self.text_opacity_label = QLabel("80%")
        text_layout.addWidget(self.text_opacity_slider)
        text_layout.addWidget(self.text_opacity_label)
        
        # Text Display Mode (new system from text_director.py)
        text_layout.addWidget(QLabel("Text Display Mode:"))
        self.text_mode_combo = QComboBox()
        self.text_mode_combo.addItems([
            "Centered (Synced with Media)",
            "Scrolling Carousel (Wallpaper)"
        ])
        self.text_mode_combo.setCurrentIndex(0)  # Default to centered
        self.text_mode_combo.currentIndexChanged.connect(self.on_text_mode_changed)
        text_layout.addWidget(self.text_mode_combo)
        
        # Info label explaining modes
        info_label = QLabel(
            "• Centered: Text changes with each media item\n"
            "• Carousel: Scrolling text grid filling screen"
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        info_label.setWordWrap(True)
        text_layout.addWidget(info_label)
        
        controls_layout.addWidget(text_group)
        
        # === Zoom Settings ===
        zoom_group = QGroupBox("Zoom Settings")
        zoom_layout = QVBoxLayout(zoom_group)
        
        # Zoom Mode
        zoom_layout.addWidget(QLabel("Zoom Mode:"))
        self.zoom_mode_combo = QComboBox()
        self.zoom_mode_combo.addItems([
            "Exponential (Falling In)",
            "Pulse (Wave)",
            "Linear (Legacy)",
            "Disabled"
        ])
        self.zoom_mode_combo.setCurrentIndex(0)  # Exponential default
        zoom_layout.addWidget(self.zoom_mode_combo)
        
        # Zoom Rate
        zoom_layout.addWidget(QLabel("Zoom Rate:"))
        self.zoom_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_rate_slider.setRange(0, 500)  # 0.0 to 5.0
        self.zoom_rate_slider.setValue(20)  # 0.2 default
        self.zoom_rate_slider.valueChanged.connect(self.on_zoom_rate_changed)
        self.zoom_rate_label = QLabel("0.200")
        zoom_layout.addWidget(self.zoom_rate_slider)
        zoom_layout.addWidget(self.zoom_rate_label)
        
        controls_layout.addWidget(zoom_group)
        
        # === Action Buttons ===
        button_layout = QVBoxLayout()
        
        self.preview_info = QLabel("Preview: Adjust settings and see live preview")
        self.preview_info.setStyleSheet("color: #666; font-style: italic;")
        button_layout.addWidget(self.preview_info)
        
        # Export as JSON (primary method - for launcher import)
        self.export_json_button = QPushButton("� Export Mode (JSON)")
        self.export_json_button.clicked.connect(self.export_mode_json)
        self.export_json_button.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #1976D2;
            }
        """)
        button_layout.addWidget(self.export_json_button)
        
        # Save as text (legacy method - human-readable)
        self.save_button = QPushButton("💾 Save Mode (Text)")
        self.save_button.clicked.connect(self.save_visual_mode)
        self.save_button.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #45a049;
            }
        """)
        button_layout.addWidget(self.save_button)
        
        # Status display
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(120)
        self.status_display.setStyleSheet("background: #f9f9f9; font-family: monospace; font-size: 10px;")
        self.status_display.setPlainText("Ready to create visual mode...")
        button_layout.addWidget(self.status_display)
        
        controls_layout.addLayout(button_layout)
        controls_layout.addStretch()
        
        # Track manual zoom override
        self.manual_zoom_rate = None
        
        # Initialize image cycling
        self.image_files = []
        self.current_image_index = 0
        
        # Start animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spiral)
        self.timer.start(16)  # ~60 FPS
        
        # Force compositor rendering and text updates
        self.render_timer = QTimer()
        self.render_timer.timeout.connect(self.update_render)
        self.render_timer.start(16)
        
        # Load test images and initialize text system after compositor initialized
        QTimer.singleShot(500, self.initialize_text_system)
        QTimer.singleShot(500, self.load_test_images)
        
        # Initialize fade duration (0.5s default for smooth transitions)
        self.compositor.set_fade_duration(0.5)
        
        # Update initial state
        self.on_spiral_type_changed(2)  # Linear
        self.on_rotation_speed_changed(40)
        self.on_zoom_rate_changed(20)
    
    def initialize_text_system(self):
        """Initialize text rendering after OpenGL context is ready."""
        logging.info("[visual_mode] initialize_text_system() called - starting initialization...")
        
        try:
            # Initialize text renderer (matching launcher.py - no configuration)
            logging.info("[visual_mode] Creating TextRenderer...")
            self.text_renderer = TextRenderer()
            logging.info("[visual_mode] TextRenderer created successfully (default style, no shadow)")
            
            logging.info("[visual_mode] Creating TextDirector...")
            self.text_director = TextDirector(
                text_renderer=self.text_renderer,
                compositor=self.compositor
            )
            logging.info("[visual_mode] TextDirector created successfully")
            
            # Load sample text library for preview
            sample_texts = [
                "Focus on my words",
                "Let your mind relax",
                "Deeper and deeper",
                "Feel the spiral pull you in",
                "Your thoughts are fading"
            ]
            self.text_director.set_text_library(sample_texts, default_split_mode=SplitMode.CENTERED_SYNC)
            logging.info("[visual_mode] Text library loaded with 5 sample texts")
            
            # Enable text rendering by default (checkbox is checked)
            self.text_director.set_enabled(True)
            logging.info("[visual_mode] Text rendering enabled")
            
            logging.info("[visual_mode] ✓ Text system initialized successfully with style: font_size=72, white with shadow, ENABLED")
        except Exception as e:
            logging.error(f"[visual_mode] ✗ Failed to initialize text system: {e}")
            import traceback
            traceback.print_exc()
    
    def update_render(self):
        """Update text director and compositor rendering."""
        # Update text system (handles frame counting and rendering)
        if self.text_director:
            self.text_director.update()
            
            # Debug: Log text state periodically
            if hasattr(self, '_debug_frame_count'):
                self._debug_frame_count += 1
                if self._debug_frame_count % 120 == 0:  # Every 2 seconds at 60fps
                    logging.info(f"[visual_mode] Text debug: enabled={self.text_director.is_enabled()}, current_text='{self.text_director._current_text[:30] if self.text_director._current_text else 'NONE'}', frame={self.text_director._frame_counter}")
            else:
                self._debug_frame_count = 0
        
        # Update compositor
        self.compositor.update()
    
    def load_test_images(self):
        """Load test media (images and/or videos) from selected Media Bank entries."""
        # Get selected bank indices
        selected_indices = self._get_selected_bank_indices()
        
        if not selected_indices:
            logging.warning("[visual_mode] No Media Bank entries selected!")
            self.image_files = []
            self.video_files = []
            return
        
        logging.info(f"[visual_mode] Loading media from {len(selected_indices)} selected bank entries")
        
        # Collect directories by type
        image_dirs = []
        video_dirs = []
        
        for idx in selected_indices:
            if idx >= len(self._media_bank):
                continue
            
            entry = self._media_bank[idx]
            entry_path = Path(entry["path"])
            entry_type = entry["type"]
            
            if entry_type in ("images", "both"):
                image_dirs.append(entry_path)
            if entry_type in ("videos", "both"):
                video_dirs.append(entry_path)
        
        # Load images from all selected directories
        self.image_files = []
        for image_dir in image_dirs:
            if image_dir.exists():
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                    self.image_files.extend(list(image_dir.glob(ext)))
                logging.info(f"[visual_mode] Scanned images from: {image_dir}")
            else:
                logging.warning(f"[visual_mode] Images directory does not exist: {image_dir}")
        
        self.image_files.sort()
        
        # Load videos from all selected directories
        self.video_files = []
        for video_dir in video_dirs:
            if video_dir.exists():
                for ext in ['*.mp4', '*.webm', '*.mkv', '*.avi', '*.mov']:
                    self.video_files.extend(list(video_dir.glob(ext)))
                logging.info(f"[visual_mode] Scanned videos from: {video_dir}")
            else:
                logging.warning(f"[visual_mode] Videos directory does not exist: {video_dir}")
        
        self.video_files.sort()

        logging.info(f"[visual_mode] Media scan complete: {len(self.image_files)} images, {len(self.video_files)} videos")
        
        self.current_media_index = 0
        self.current_media_list = []
        
        # Build media list based on mode
        self.rebuild_media_list()
        
        if self.current_media_list:
            self.load_next_media()
            
            # Start media cycling timer
            self.image_cycle_timer = QTimer()
            self.image_cycle_timer.timeout.connect(self.cycle_media)
            # Calculate initial interval from image speed slider
            self.update_cycle_interval()
            
            logging.info(f"[visual_mode] Found {len(self.image_files)} images, {len(self.video_files)} videos")
    
    def rebuild_media_list(self):
        """Rebuild media list based on current mode."""
        media_mode = self.media_mode_combo.currentIndex()
        
        if media_mode == 0:  # Images & Videos
            self.current_media_list = self.image_files + self.video_files
        elif media_mode == 1:  # Images Only
            self.current_media_list = self.image_files
        else:  # Videos Only
            self.current_media_list = self.video_files
        
        # Reset index
        self.current_media_index = 0
        logging.info(f"[visual_mode] Media list rebuilt: {len(self.current_media_list)} items")
    
    def update_cycle_interval(self):
        """Update cycling timer interval based on speed setting."""
        if not hasattr(self, 'image_cycle_timer'):
            logging.warning("[visual_mode] Timer not initialized yet")
            return
        
        speed = self.media_speed_slider.value()
        
        # Exponential curve for better control at high speeds
        # Speed 1 = 10000ms (10s)
        # Speed 20 = ~2000ms (2s)  <- High-speed range starts here
        # Speed 100 = 50ms (0.05s)
        # Use exponential decay: interval = 10000 * (0.005^((speed-1)/99))
        import math
        normalized = (speed - 1) / 99.0  # 0.0 to 1.0
        interval_ms = int(10000 * math.pow(0.005, normalized))
        
        self.image_cycle_timer.setInterval(interval_ms)
        self.image_cycle_timer.start()
        logging.info(f"[visual_mode] Cycle interval updated: {interval_ms}ms (speed={speed})")
    
    def load_next_media(self):
        """Load the next media item (image or video) in cycle."""
        if not self.current_media_list:
            logging.warning("[visual_mode] No media list to load from")
            return
        
        try:
            media_file = self.current_media_list[self.current_media_index]
            logging.info(f"[visual_mode] Loading media {self.current_media_index + 1}/{len(self.current_media_list)}: {media_file.name}")
            
            # Check if it's an image or video
            if media_file.suffix.lower() in ['.jpg', '.png', '.jpeg', '.bmp', '.gif']:
                self.stop_video()  # Stop any playing video
                self.load_image(media_file)
            else:
                # Load and play video
                self.load_video(media_file)
        except Exception as e:
            logging.error(f"[visual_mode] Failed to load media: {e}")
            import traceback
            traceback.print_exc()
    
    def load_image(self, image_file):
        """Load a specific image file."""
        try:
            image_data = media.load_image_sync(image_file)
            
            self.compositor.makeCurrent()
            texture_id = upload_image_to_gpu(image_data)
            
            logging.info(f"[visual_mode] Setting texture {texture_id} ({image_data.width}x{image_data.height})")
            
            self.compositor.set_background_texture(
                texture_id,
                zoom=1.0,
                image_width=image_data.width,
                image_height=image_data.height
            )
            
            # Start zoom animation
            zoom_mode_map = {
                0: "exponential",
                1: "pulse",
                2: "linear",
                3: "linear"  # Disabled = linear with rate 0
            }
            mode = zoom_mode_map[self.zoom_mode_combo.currentIndex()]
            
            self.compositor.start_zoom_animation(
                start_zoom=1.0,
                duration_frames=9999,
                mode=mode
            )
            
            # Apply manual zoom override
            if self.manual_zoom_rate is not None:
                import time
                self.compositor._zoom_rate = self.manual_zoom_rate
                self.compositor._zoom_start_time = time.time()
                self.compositor._zoom_current = 1.0
            
            # Force compositor to refresh display
            self.compositor.update()
            
            # Trigger text change for CENTERED_SYNC mode
            if self.text_director:
                old_text = self.text_director._current_text
                self.text_director.on_media_change()
                new_text = self.text_director._current_text
                if old_text != new_text:
                    logging.info(f"[visual_mode] Text changed with media: '{old_text}' -> '{new_text}'")
            
            logging.info(f"[visual_mode] Loaded image: {image_file.name}")
        except Exception as e:
            logging.error(f"[visual_mode] Failed to load image: {e}")
    
    def load_video(self, video_file):
        """Load and start playing a video file."""
        try:
            # Stop any current video
            self.stop_video()
            
            # Open video with OpenCV
            self.video_cap = cv2.VideoCapture(str(video_file))
            
            if not self.video_cap.isOpened():
                logging.error(f"[visual_mode] Failed to open video: {video_file.name}")
                return
            
            # Get video properties
            self.video_fps = self.video_cap.get(cv2.CAP_PROP_FPS)
            if self.video_fps <= 0:
                self.video_fps = 30.0
            
            self.current_video_file = video_file
            self.video_first_frame = True  # Mark that next frame is first frame of new video
            
            # Create video frame update timer
            self.video_frame_timer = QTimer()
            self.video_frame_timer.timeout.connect(self.update_video_frame)
            frame_interval_ms = int(1000.0 / self.video_fps)
            self.video_frame_timer.start(frame_interval_ms)
            
            # Start zoom animation for video
            zoom_mode_map = {
                0: "exponential",
                1: "pulse",
                2: "linear",
                3: "linear"  # Disabled
            }
            mode = zoom_mode_map[self.zoom_mode_combo.currentIndex()]
            
            self.compositor.start_zoom_animation(
                start_zoom=1.0,
                duration_frames=9999,
                mode=mode
            )
            
            # Apply manual zoom override
            if self.manual_zoom_rate is not None:
                import time
                self.compositor._zoom_rate = self.manual_zoom_rate
                self.compositor._zoom_start_time = time.time()
                self.compositor._zoom_current = 1.0
            
            # Trigger text change for CENTERED_SYNC mode
            if self.text_director:
                old_text = self.text_director._current_text
                self.text_director.on_media_change()
                new_text = self.text_director._current_text
                if old_text != new_text:
                    logging.info(f"[visual_mode] Text changed with media: '{old_text}' -> '{new_text}'")
            
            logging.info(f"[visual_mode] Started video playback: {video_file.name} @ {self.video_fps:.2f} fps")
            
        except Exception as e:
            logging.error(f"[visual_mode] Failed to load video: {e}")
            import traceback
            traceback.print_exc()
    
    def update_video_frame(self):
        """Read and display next video frame."""
        if not self.video_cap or not self.video_cap.isOpened():
            return
        
        ret, frame = self.video_cap.read()
        
        if not ret:
            # Loop video
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.video_cap.read()
            if not ret:
                logging.warning("[visual_mode] Failed to loop video")
                return
        
        try:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width = frame_rgb.shape[:2]
            
            # Make OpenGL context current
            self.compositor.makeCurrent()
            
            # Get current zoom from compositor (it's managed by zoom animation)
            current_zoom = getattr(self.compositor, '_zoom_current', 1.0)
            
            # Upload frame to GPU (pass new_video flag for fade transition on first frame)
            self.compositor.set_background_video_frame(
                frame_rgb,
                width=width,
                height=height,
                zoom=current_zoom,
                new_video=self.video_first_frame
            )
            
            # Clear first frame flag after upload
            self.video_first_frame = False
            
            # Force update
            self.compositor.update()
            
        except Exception as e:
            logging.error(f"[visual_mode] Failed to update video frame: {e}")
    
    def stop_video(self):
        """Stop video playback and release resources."""
        if self.video_frame_timer:
            self.video_frame_timer.stop()
            self.video_frame_timer = None
        
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
        
        self.current_video_file = None
    
    def cycle_media(self):
        """Cycle to next media item."""
        if not self.current_media_list:
            logging.warning("[visual_mode] No media in list to cycle")
            return
        self.current_media_index = (self.current_media_index + 1) % len(self.current_media_list)
        logging.debug(f"[visual_mode] Cycling to media {self.current_media_index + 1}/{len(self.current_media_list)}")
        self.load_next_media()
    
    # --- Speed mapping helpers (UI "x" -> RPM) ---
    SPEED_GAIN = 10.0  # Calibrates modern RPM to match legacy "feel" (x4 old ≈ x40 new)

    def _compute_rpm(self, x_value: float, reversed_flag: bool) -> float:
        """Map UI "x" value (e.g., 4.0..40.0) to actual RPM with calibration.

        Using a gain of 10.0 makes new x40 feel like legacy x4 speeds.
        Negative RPM represents reverse direction.
        """
        rpm = float(x_value) * float(self.SPEED_GAIN)
        return -rpm if reversed_flag else rpm

    def update_spiral(self):
        """Update spiral animation using standard rotation method."""
        # Use standard spiral rotation - the method now handles RPM calculation internally
        self.director.rotate_spiral(4.0)  # amount is ignored in new RPM mode
        
        # Update other spiral parameters (opacity, bar width, etc.)
        self.director.update(1/60.0)
        
        # Debug log rotation values every 120 frames
        if not hasattr(self, '_debug_frame_count'):
            self._debug_frame_count = 0
        self._debug_frame_count += 1
        
        if self._debug_frame_count % 120 == 0:
            uniforms = self.director.export_uniforms()
            print(f"[VMC rotation_debug] time={uniforms.get('time', 0):.6f}")
            print(f"[VMC rotation_debug] rotation_speed={uniforms.get('rotation_speed', 0)}")
            print(f"[VMC rotation_debug] uEffectiveSpeed={uniforms.get('uEffectiveSpeed', 0)}")
            print(f"[VMC rotation_debug] uBaseSpeed={uniforms.get('uBaseSpeed', 0)}")
            print(f"[VMC rotation_debug] uIntensity={uniforms.get('uIntensity', 0)}")
        
        self.compositor.update_zoom_animation()
        self.compositor.update()
    
    def on_spiral_type_changed(self, index):
        """Handle spiral type change."""
        spiral_type = index + 1
        self.director.set_spiral_type(spiral_type)
        
        # Update spiral type names
        type_names = {
            1: "Logarithmic",
            2: "Quadratic",
            3: "Linear",
            4: "Square Root",
            5: "Inverse",
            6: "Power",
            7: "Sawtooth"
        }
        logging.info(f"[visual_mode] Spiral type: {type_names.get(spiral_type, spiral_type)}")
    
    def on_opacity_changed(self, value):
        """Handle opacity slider.

        IMPORTANT: Opacity should map to SpiralDirector.set_opacity, not intensity.
        Intensity is decoupled from brightness in the MesmerLoom director and is
        not used for visual alpha; shader uses uSpiralOpacity for blending.
        """
        opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")
        # Use explicit opacity setter to keep VMC 1:1 with Launcher/CustomVisual
        try:
            self.director.set_opacity(opacity)
        except Exception:
            # Fallback to legacy in case of older director versions
            self.director.set_intensity(opacity)
    
    def on_rotation_speed_changed(self, value):
        """Handle rotation speed slider.

        UI reports an "x" value (4.0..40.0). We convert this to RPM using
        SPEED_GAIN so the perceived speed matches legacy behavior, and then
        pass RPM to the SpiralDirector (shared with Launcher).
        """
        x_val = value / 10.0
        reversed_flag = self.spiral_reverse_check.isChecked()
        rpm = self._compute_rpm(x_val, reversed_flag)
        # Update label to keep familiar "x" notation and show RPM in tooltip
        self.rotation_speed_label.setText(f"{abs(x_val):.1f}x")
        try:
            self.rotation_speed_label.setToolTip(f"≈ {abs(rpm):.1f} RPM{' (reverse)' if reversed_flag else ''}")
        except Exception:
            pass
        self.director.set_rotation_speed(rpm)
        logging.info(
            f"[visual_mode] Rotation speed set: x={x_val:.1f} → rpm={rpm:.1f} (reversed={reversed_flag})"
        )
    
    def on_spiral_reverse_changed(self, state):
        """Handle spiral reverse checkbox."""
        logging.info(f"[visual_mode] Spiral reverse changed: {state == 2}")
        # Re-apply rotation speed with new direction
        self.on_rotation_speed_changed(self.rotation_speed_slider.value())
    
    def on_zoom_rate_changed(self, value):
        """Handle zoom rate slider."""
        import time
        rate = value / 100.0
        self.zoom_rate_label.setText(f"{rate:.3f}")
        
        # Store manual rate
        self.manual_zoom_rate = rate
        
        # Apply immediately
        self.compositor._zoom_rate = rate
        self.compositor._zoom_start_time = time.time()
        self.compositor._zoom_current = 1.0
    
    def on_media_mode_changed(self, index):
        """Handle media mode change."""
        mode_names = ["Images & Videos", "Images Only", "Videos Only"]
        logging.info(f"[visual_mode] Media mode changed to: {mode_names[index]}")
        
        # Refresh Media Bank list (filters by media mode)
        self._refresh_media_bank_list()
        
        # Rebuild media list and restart cycling
        self.rebuild_media_list()
        if self.current_media_list:
            self.load_next_media()
    
    def on_media_speed_changed(self, value):
        """Handle media speed slider (controls both image and video cycling)."""
        # Calculate actual interval for display using same exponential formula
        import math
        normalized = (value - 1) / 99.0
        interval_ms = int(10000 * math.pow(0.005, normalized))
        interval_s = interval_ms / 1000.0
        
        # Dynamic speed description based on actual interval
        if interval_s > 5:
            speed_desc = "Very Slow"
        elif interval_s > 2:
            speed_desc = "Slow"
        elif interval_s > 0.5:
            speed_desc = "Medium"
        elif interval_s > 0.2:
            speed_desc = "Fast"
        else:
            speed_desc = "Very Fast"
        
        self.media_speed_label.setText(f"{value} ({speed_desc}) - {interval_s:.2f}s")
        
        # Update cycling interval in real-time
        self.update_cycle_interval()
    
    def on_bg_opacity_changed(self, value):
        """Handle background opacity slider."""
        opacity = value / 100.0
        self.bg_opacity_label.setText(f"{value}%")
        # Apply to compositor if needed
        # self.compositor.set_background_opacity(opacity)
    
    def on_fade_duration_changed(self, value):
        """Handle fade duration slider (transition time between media)."""
        duration_s = value / 10.0  # Convert tenths to seconds (0.0 - 5.0)
        self.fade_duration_label.setText(f"{duration_s:.1f}s")
        
        # Apply to compositor in real-time for 1:1 preview match with launcher
        self.compositor.set_fade_duration(duration_s)
    
    def on_text_opacity_changed(self, value):
        """Handle text opacity slider."""
        opacity = value / 100.0
        self.text_opacity_label.setText(f"{value}%")
        # Apply to compositor text rendering
        if self.compositor:
            self.compositor.set_text_opacity(opacity)
    
    def on_text_enabled_changed(self, state):
        """Handle text enabled checkbox."""
        enabled = state == 2  # Qt.Checked == 2
        if self.text_director:
            self.text_director.set_enabled(enabled)
            
            # If enabling and no text selected, pick one now
            if enabled and not self.text_director._current_text:
                text, split_mode = self.text_director.get_random_text()
                if text:
                    self.text_director._current_text = text
                    self.text_director._current_split_mode = split_mode
                    self.text_director._render_current_text()
                    logging.info(f"[visual_mode] Text rendering enabled with text: '{text[:30]}...'")
            else:
                # When disabling, force compositor update to show cleared state
                if not enabled and self.compositor:
                    self.compositor.update()
                logging.info(f"[visual_mode] Text rendering: {'enabled' if enabled else 'disabled'}")
    
    def on_text_mode_changed(self, index):
        """Handle text mode combo box."""
        # Map index to SplitMode: 0=CENTERED_SYNC, 1=SUBTEXT
        mode = SplitMode.CENTERED_SYNC if index == 0 else SplitMode.SUBTEXT
        if self.text_director:
            self.text_director.set_all_split_mode(mode)
            
            # Force update of current split mode and re-render
            self.text_director._current_split_mode = mode
            
            # If text already selected, re-render with new mode
            if self.text_director._current_text:
                self.text_director._render_current_text()
            else:
                # No text selected yet, pick one now
                text, split_mode = self.text_director.get_random_text()
                if text:
                    self.text_director._current_text = text
                    self.text_director._current_split_mode = mode
                    self.text_director._render_current_text()
            
            logging.info(f"[visual_mode] Text mode changed to: {mode.name} and re-rendered")
    
    def pick_color(self, which: str):
        """Open color picker for arm or gap color."""
        if which == "arm":
            current = QColor.fromRgbF(*self.arm_color)
        else:
            current = QColor.fromRgbF(*self.gap_color)
        
        color = QColorDialog.getColor(current, self, f"Pick {which.capitalize()} Color")
        
        if color.isValid():
            rgb = (color.redF(), color.greenF(), color.blueF())
            
            if which == "arm":
                self.arm_color = rgb
                self.director.set_arm_color(*rgb)
                self.arm_color_btn.setStyleSheet(f"background-color: {color.name()};")
            else:
                self.gap_color = rgb
                self.director.set_gap_color(*rgb)
                self.gap_color_btn.setStyleSheet(f"background-color: {color.name()};")
    
    def export_mode_json(self):
        """Export current settings to JSON mode file (for launcher import)."""
        mode_name = self.mode_name_input.text().strip()
        if not mode_name:
            self.status_display.setPlainText("❌ ERROR: Please enter a mode name!")
            return
        
        # Open file dialog to choose save location
        default_dir = Path(__file__).parent.parent / "mesmerglass" / "modes"
        default_dir.mkdir(parents=True, exist_ok=True)
        
        default_filename = f"{mode_name.replace(' ', '_').lower()}.json"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Visual Mode",
            str(default_dir / default_filename),
            "JSON Mode Files (*.json);;All Files (*)"
        )
        
        if not filepath:
            return  # User cancelled
        
        filepath = Path(filepath)
        
        # Build JSON config (excludes spiral colors - those are global in launcher)
        spiral_type_names = ["", "logarithmic", "quadratic", "linear", "sqrt", "inverse", "power", "sawtooth"]
        spiral_type_index = self.spiral_type_combo.currentIndex() + 1
        
        media_modes = ["both", "images", "videos"]
        media_mode_index = self.media_mode_combo.currentIndex()
        
        text_modes = ["centered_sync", "subtext"]
        text_mode_index = self.text_mode_combo.currentIndex()
        
        zoom_modes_map = {
            "Exponential (Falling In)": "exponential",
            "Pulse (Wave)": "pulse",
            "Linear (Legacy)": "linear",
            "Disabled": "none"
        }
        zoom_mode = zoom_modes_map.get(self.zoom_mode_combo.currentText(), "none")
        
        # Compute calibrated RPM for export (keeps Launcher & CLI semantics as RPM)
        x_val = self.rotation_speed_slider.value() / 10.0
        reversed_flag = self.spiral_reverse_check.isChecked()
        export_rpm = self._compute_rpm(x_val, False)  # store magnitude as RPM; reverse is separate flag

        config = {
            "version": "1.0",
            "name": mode_name,
            "description": f"Custom mode created on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            
            "spiral": {
                "type": spiral_type_names[spiral_type_index] if spiral_type_index < len(spiral_type_names) else "logarithmic",
                # Store RPM (not UI x-value) so Launcher applies exactly the same speed
                "rotation_speed": export_rpm,
                "opacity": self.opacity_slider.value() / 100.0,
                "reverse": self.spiral_reverse_check.isChecked()
                # NOTE: arm_color and gap_color NOT exported - controlled globally in launcher
            },
            
            "media": {
                "mode": media_modes[media_mode_index] if media_mode_index < len(media_modes) else "both",
                "cycle_speed": self.media_speed_slider.value(),  # 1-100
                "fade_duration": self.fade_duration_slider.value() / 10.0,  # Convert tenths to seconds (0.0-5.0)
                "use_theme_bank": True,  # Always use ThemeBank for now
                "paths": [],  # Empty - using ThemeBank
                "shuffle": False,  # Can be added to UI later
                "bank_selections": self._get_selected_bank_indices()  # NEW: Store selected bank indices
            },
            
            "text": {
                "enabled": self.text_enabled_check.isChecked(),
                "mode": text_modes[text_mode_index] if text_mode_index < len(text_modes) else "centered_sync",
                "opacity": self.text_opacity_slider.value() / 100.0,
                "use_theme_bank": True,  # Always use ThemeBank for now
                "library": [],  # Empty - using ThemeBank
                "sync_with_media": True  # CENTERED_SYNC always syncs with media
            },
            
            "zoom": {
                "mode": zoom_mode,
                "rate": self.zoom_rate_slider.value() / 100.0
            }
        }
        
        # Write JSON file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # Get bank names for display
            bank_selections = config['media']['bank_selections']
            bank_names = [self._media_bank[idx]['name'] for idx in bank_selections if idx < len(self._media_bank)]
            
            # Show success message
            result = (
                f"✅ MODE EXPORTED (JSON)\n\n"
                f"Name: {mode_name}\n"
                f"File: {filepath.name}\n"
                f"Location: {filepath.parent}\n\n"
                f"Settings:\n"
                f"  - Spiral: {config['spiral']['type']}, Speed {config['spiral']['rotation_speed']:.1f}x"
                f"{' (Reversed)' if config['spiral']['reverse'] else ''}\n"
                f"  - Media: {config['media']['mode']}, Speed {config['media']['cycle_speed']}\n"
                f"  - Media Banks: {', '.join(bank_names) if bank_names else 'None selected'}\n"
                f"  - Text: {'Enabled' if config['text']['enabled'] else 'Disabled'} ({config['text']['mode']})\n"
                f"  - Zoom: {config['zoom']['mode']}\n\n"
                f"💡 This mode can now be loaded in the launcher!\n"
                f"Note: Spiral colors are controlled globally in launcher settings."
            )
            
            self.status_display.setPlainText(result)
            logging.info(f"[visual_mode] Exported JSON mode '{mode_name}' to {filepath}")
            
        except Exception as e:
            self.status_display.setPlainText(f"❌ ERROR: Failed to export mode\n\n{str(e)}")
            logging.error(f"[visual_mode] Export failed: {e}", exc_info=True)
    
    def save_visual_mode(self):
        """Save current settings to a visual mode file (text format - legacy)."""
        mode_name = self.mode_name_input.text().strip()
        if not mode_name:
            self.status_display.setPlainText("❌ ERROR: Please enter a mode name!")
            return
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"visual_mode_{mode_name.replace(' ', '_')}_{timestamp}.txt"
        filepath = Path(__file__).parent.parent / filename
        
        # Collect all settings
        settings = {
            "mode_name": mode_name,
            "spiral_type": self.spiral_type_combo.currentIndex() + 1,
            "spiral_opacity": self.opacity_slider.value() / 100.0,
            "rotation_speed": self.rotation_speed_slider.value() / 10.0,
            "spiral_reversed": self.spiral_reverse_check.isChecked(),
            "arm_color": self.arm_color,
            "gap_color": self.gap_color,
            "media_mode": self.media_mode_combo.currentIndex(),
            "media_speed": self.media_speed_slider.value(),
            "background_opacity": self.bg_opacity_slider.value() / 100.0,
            "text_enabled": self.text_enabled_check.isChecked(),
            "text_opacity": self.text_opacity_slider.value() / 100.0,
            "text_mode": self.text_mode_combo.currentIndex(),  # 0=CENTERED_SYNC, 1=SUBTEXT
            "text_mode_name": self.text_mode_combo.currentText(),
            "zoom_mode": self.zoom_mode_combo.currentText(),
            "zoom_rate": self.zoom_rate_slider.value() / 100.0,
        }
        
        # Write to file
        with open(filepath, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write(f"VISUAL MODE: {mode_name}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 70 + "\n\n")
            
            f.write("SPIRAL SETTINGS:\n")
            f.write("-" * 70 + "\n")
            type_names = ["", "Logarithmic", "Quadratic", "Linear", "Square Root", "Inverse", "Power", "Sawtooth"]
            f.write(f"  Type: {settings['spiral_type']} - {type_names[settings['spiral_type']]}\n")
            f.write(f"  Opacity: {settings['spiral_opacity']:.2f}\n")
            f.write(f"  Rotation Speed: {settings['rotation_speed']:.1f}x\n")
            f.write(f"  Reversed: {settings['spiral_reversed']}\n")
            f.write(f"  Arm Color: RGB({settings['arm_color'][0]:.3f}, {settings['arm_color'][1]:.3f}, {settings['arm_color'][2]:.3f})\n")
            f.write(f"  Gap Color: RGB({settings['gap_color'][0]:.3f}, {settings['gap_color'][1]:.3f}, {settings['gap_color'][2]:.3f})\n\n")
            
            f.write("MEDIA SETTINGS:\n")
            f.write("-" * 70 + "\n")
            media_modes = ["Images & Videos", "Images Only", "Videos Only"]
            f.write(f"  Mode: {media_modes[settings['media_mode']]}\n")
            f.write(f"  Media Cycling Speed: {settings['media_speed']} (1=slowest, 100=fastest)\n")
            f.write(f"  Background Opacity: {settings['background_opacity']:.2f}\n\n")
            
            f.write("TEXT SETTINGS:\n")
            f.write("-" * 70 + "\n")
            f.write(f"  Enabled: {settings['text_enabled']}\n")
            f.write(f"  Opacity: {settings['text_opacity']:.2f}\n")
            f.write(f"  Mode: {settings['text_mode_name']}\n")
            f.write(f"  Mode ID: {settings['text_mode']} (0=CENTERED_SYNC, 1=SUBTEXT)\n\n")
            
            f.write("ZOOM SETTINGS:\n")
            f.write("-" * 70 + "\n")
            f.write(f"  Mode: {settings['zoom_mode']}\n")
            f.write(f"  Rate: {settings['zoom_rate']:.3f}\n")
            f.write(f"  Max Zoom: 5.0x (hardcoded)\n\n")
            
            f.write("=" * 70 + "\n")
            f.write("USAGE:\n")
            f.write("-" * 70 + "\n")
            f.write("This visual mode can be loaded into MesmerGlass to apply all settings.\n")
            f.write("Implementation requires adding mode loading functionality to launcher.py\n")
        
        # Show confirmation
        result = (
            f"✅ VISUAL MODE SAVED (TEXT)\n\n"
            f"Name: {mode_name}\n"
            f"File: {filename}\n"
            f"Location: {filepath}\n\n"
            f"Settings saved:\n"
            f"  - Spiral: Type {settings['spiral_type']}, Speed {settings['rotation_speed']:.1f}x"
            f"{' (Reversed)' if settings['spiral_reversed'] else ''}\n"
            f"  - Media: {media_modes[settings['media_mode']]}, Speed {settings['media_speed']}\n"
            f"  - Text: {'Enabled' if settings['text_enabled'] else 'Disabled'}\n"
            f"  - Zoom: {settings['zoom_mode']}\n\n"
            f"💡 Use 'Export Mode (JSON)' button for launcher import.\n"
        )
        
        self.status_display.setPlainText(result)
        logging.info(f"[visual_mode] Saved mode '{mode_name}' to {filepath}")
    
    # === Media Bank Handlers ===
    
    def _load_media_bank_config(self):
        """Load Media Bank configuration from shared config file."""
        config_path = PROJECT_ROOT / "media_bank.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._media_bank = json.load(f)
                logging.info(f"[VMC MediaBank] Loaded {len(self._media_bank)} entries from config")
            except Exception as e:
                logging.error(f"[VMC MediaBank] Failed to load config: {e}")
                self._media_bank = []
        else:
            logging.info("[VMC MediaBank] No saved config found - starting with empty bank")
            self._media_bank = []
    
    def _save_media_bank_config(self):
        """Save Media Bank configuration to shared config file."""
        config_path = PROJECT_ROOT / "media_bank.json"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._media_bank, f, indent=2, ensure_ascii=False)
            logging.info(f"[VMC MediaBank] Saved {len(self._media_bank)} entries to config")
        except Exception as e:
            logging.error(f"[VMC MediaBank] Failed to save config: {e}")
    
    def _get_selected_bank_indices(self):
        """Get list of selected Media Bank indices."""
        selected = []
        for i in range(self.list_media_bank.count()):
            item = self.list_media_bank.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                bank_idx = item.data(Qt.ItemDataRole.UserRole)
                selected.append(bank_idx)
        return selected
    
    def _refresh_media_bank_list(self):
        """Populate the Media Bank list with checkboxes."""
        self.list_media_bank.clear()
        
        media_mode = self.media_mode_combo.currentIndex()  # 0=both, 1=images, 2=videos
        
        for idx, entry in enumerate(self._media_bank):
            entry_type = entry["type"]
            entry_name = entry["name"]
            
            # Filter by media mode
            if media_mode == 1 and entry_type == "videos":  # Images only
                continue
            if media_mode == 2 and entry_type == "images":  # Videos only
                continue
            
            # Icon based on type
            if entry_type == "images":
                icon = "🖼️"
            elif entry_type == "videos":
                icon = "🎬"
            else:
                icon = "📁"
            
            # Create item
            item = QListWidgetItem(f"{icon} {entry_name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if entry.get("enabled", True) else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, idx)  # Store bank index
            
            self.list_media_bank.addItem(item)
        
        self._update_bank_info()
    
    def _update_bank_info(self):
        """Update the info label showing selected bank count."""
        selected_count = sum(
            1 for i in range(self.list_media_bank.count())
            if self.list_media_bank.item(i).checkState() == Qt.CheckState.Checked
        )
        total_count = self.list_media_bank.count()
        self.lbl_bank_info.setText(f"Selected: {selected_count} of {total_count} directories")
    
    def _on_add_to_media_bank(self):
        """Add a new directory to the Media Bank."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Add Directory to Media Bank",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not dir_path:
            return
        
        # Ask for name
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self,
            "Name Directory",
            "Enter a name for this directory:",
            text=Path(dir_path).name
        )
        
        if not ok or not name.strip():
            return
        
        # Ask for type
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QRadioButton
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Media Type")
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("What type of media is in this directory?"))
        rb_images = QRadioButton("Images only")
        rb_videos = QRadioButton("Videos only")
        rb_both = QRadioButton("Both images and videos")
        rb_images.setChecked(True)
        
        layout.addWidget(rb_images)
        layout.addWidget(rb_videos)
        layout.addWidget(rb_both)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        # Determine type
        if rb_images.isChecked():
            media_type = "images"
        elif rb_videos.isChecked():
            media_type = "videos"
        else:
            media_type = "both"
        
        # Add to bank
        self._media_bank.append({
            "name": name.strip(),
            "path": str(Path(dir_path)),
            "type": media_type,
            "enabled": True
        })
        
        self._refresh_media_bank_list()
        self._save_media_bank_config()
        logging.info(f"[MediaBank] Added directory: {name} ({media_type}) -> {dir_path}")
    
    def _on_remove_from_media_bank(self):
        """Remove selected directory from Media Bank."""
        current_item = self.list_media_bank.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a directory to remove.")
            return
        
        bank_idx = current_item.data(Qt.ItemDataRole.UserRole)
        entry = self._media_bank[bank_idx]
        
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove '{entry['name']}' from Media Bank?\n\nPath: {entry['path']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self._media_bank[bank_idx]
            self._refresh_media_bank_list()
            self._save_media_bank_config()
            logging.info(f"[MediaBank] Removed directory: {entry['name']}")
    
    def _on_manage_bank(self):
        """Show info about managing the Media Bank."""
        QMessageBox.information(
            self,
            "Media Bank Management",
            "Media Bank Tips:\n\n"
            "✓ Check/uncheck directories to include in this mode\n"
            "✓ Add directories with '➕ Add Directory'\n"
            "✓ Remove directories with '➖ Remove' (select first)\n"
            "✓ Bank selections are saved with each mode\n\n"
            "The launcher will only load media from checked directories!"
        )


def main():
    """Run Visual Mode Creator."""
    logging.basicConfig(
        level=logging.DEBUG,  # Changed to DEBUG for more detailed output
        format='%(levelname)s:%(name)s:%(message)s'
    )
    
    app = QApplication(sys.argv)
    window = VisualModeCreator()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
