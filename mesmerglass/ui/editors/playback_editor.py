"""
Playback Editor - Edit visual playback configurations.

1:1 match with Visual Mode Creator (scripts/visual_mode_creator.py).
Features live preview using LoomCompositor, SpiralDirector, and TextDirector.

Opens playback JSON files and allows editing of:
- Spiral settings (type, speed, colors, opacity, reverse)
- Media settings (mode, cycling speed, fade duration, bank selections)
- Text settings (enabled, mode, opacity)
- Zoom settings (mode, rate)

Layout: Preview on left (2/3 width), controls on right (1/3 width, scrollable)
"""

import sys
import json
import logging
import cv2
from pathlib import Path
from typing import Optional
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSlider, QCheckBox, QTextEdit,
    QGroupBox, QMessageBox, QFileDialog, QColorDialog,
    QScrollArea, QFrame, QListWidget, QListWidgetItem,
    QDialogButtonBox
)
from PyQt6.QtGui import QColor, QGuiApplication

logger = logging.getLogger(__name__)

# Import compositor and directors for live preview
try:
    from mesmerglass.mesmerloom.compositor import LoomCompositor
    from mesmerglass.mesmerloom.spiral import SpiralDirector
    from mesmerglass.content.texture import upload_image_to_gpu
    from mesmerglass.content import media
    from mesmerglass.content.text_renderer import TextRenderer, SplitMode
    from mesmerglass.engine.text_director import TextDirector
    import cv2
    import numpy as np
    PREVIEW_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Preview components not available: {e}")
    PREVIEW_AVAILABLE = False

# Project root for media_bank.json
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class PlaybackEditor(QDialog):
    """
    Playback Editor - 1:1 match with Visual Mode Creator.
    
    Features:
    - Live preview using LoomCompositor (1280x720)
    - SpiralDirector for spiral rendering
    - TextDirector for text overlay
    - Media cycling (images + videos)
    - Real-time preview updates
    - Save/Save As to JSON
    """
    
    # Signal emitted when playback is saved
    saved = pyqtSignal(str)  # file path
    
    # Speed calibration constant (matches VMC exactly)
    SPEED_GAIN = 10.0  # Calibrates modern RPM to match legacy "feel" (x4 old ≈ x40 new)
    
    def __init__(self, file_path: Optional[Path] = None, session_data: Optional[dict] = None, playback_key: Optional[str] = None, parent=None):
        """
        Initialize PlaybackEditor.
        
        Two modes:
        1. File mode: file_path provided, saves to file
        2. Session mode: session_data + playback_key provided, modifies session dict in-place
        
        Args:
            file_path: Path to playback JSON file (file mode)
            session_data: Reference to session dict (session mode)
            playback_key: Key in session["playbacks"] (session mode, None = new playback)
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Mode determination
        self.file_path = file_path
        self.session_data = session_data
        self.playback_key = playback_key
        self.is_session_mode = session_data is not None
        self.is_modified = False
        
        self.setWindowTitle("Playback Editor")
        self.setModal(True)
        self.resize(1200, 700)
        
        # Initialize state
        self.text_renderer = None
        self.text_director = None
        self.video_cap = None
        self.video_fps = 30.0
        self.video_frame_timer = None
        self.current_video_file = None
        self.video_first_frame = False
        self._media_bank = []
        
        self._setup_ui()
        
        # Load media bank
        self._load_media_bank_config()
        self._refresh_media_bank_list()
        
        # Load data based on mode
        loaded_data = False
        if self.is_session_mode:
            if self.playback_key:
                # Editing existing playback from session
                playback_data = self.session_data.get("playbacks", {}).get(self.playback_key)
                if playback_data:
                    self._load_from_dict(playback_data)
                    loaded_data = True
                else:
                    logger.warning(f"Playback key '{self.playback_key}' not found in session")
                    self._create_new()
            else:
                # Creating new playback in session
                self._create_new()
        elif file_path:
            # File mode: load from file
            self._load_file(file_path)
            loaded_data = True
        else:
            # File mode: new file
            self._create_new()
        
        # Initialize after compositor is ready
        QTimer.singleShot(500, self._initialize_text_system)
        QTimer.singleShot(500, self._load_test_images)
        
        # Start timers
        if PREVIEW_AVAILABLE:
            self.timer = QTimer()
            self.timer.timeout.connect(self._update_spiral)
            self.timer.start(33)  # 30 FPS (matches launcher)
            
            self.render_timer = QTimer()
            self.render_timer.timeout.connect(self._update_render)
            self.render_timer.start(33)
            
            # Initialize fade duration (0.5s default for smooth transitions)
            self.compositor.set_fade_duration(0.5)
            
            # Update initial state only if we didn't load data
            # (if we loaded data, the setCurrentIndex calls already updated the director)
            if not loaded_data:
                self._on_spiral_type_changed(2)  # Linear
                self._on_rotation_speed_changed(40)
                self._on_zoom_rate_changed(20)
    
    def _setup_ui(self):
        """Build the editor UI (matches VMC layout exactly)."""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(15)
        
        # === Left side: Preview (2/3 width) ===
        preview_container = QVBoxLayout()
        
        preview_label = QLabel("Live Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        preview_container.addWidget(preview_label)
        
        # Add stretch before to center vertically
        preview_container.addStretch(1)
        
        if PREVIEW_AVAILABLE:
            # Create compositor with 16:9 aspect ratio (matches VMC exactly)
            # Create spiral director first
            self.director = SpiralDirector()
            
            # Create compositor with director
            self.compositor = LoomCompositor(
                director=self.director,
                parent=self,
                trace=False,
                sim_flag=False,
                force_flag=False
            )
            # Smaller size for better window fit
            self.compositor.setMinimumSize(640, 360)
            self.compositor.setMaximumSize(640, 360)
            self.compositor.set_active(True)
            preview_container.addWidget(self.compositor, alignment=Qt.AlignmentFlag.AlignCenter)

            # Ensure preview text scales against the live window resolution
            QTimer.singleShot(0, self._apply_preview_virtual_size)
        else:
            preview_placeholder = QLabel("Preview not available\n(missing dependencies)")
            preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview_placeholder.setStyleSheet("background: #333; color: #999; font-size: 16px; padding: 50px;")
            preview_container.addWidget(preview_placeholder)
        
        # Add stretch after to center vertically
        preview_container.addStretch(1)
        
        main_layout.addLayout(preview_container, stretch=2)
        
        # === Right side: Controls (1/3 width, scrollable) ===
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumWidth(350)
        scroll.setMaximumWidth(450)
        
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
        self.mode_name_input.textChanged.connect(self._mark_modified)
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
        self.spiral_type_combo.currentIndexChanged.connect(self._on_spiral_type_changed)
        spiral_layout.addWidget(self.spiral_type_combo)
        
        # Spiral Opacity
        spiral_layout.addWidget(QLabel("Spiral Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(80)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_label = QLabel("80%")
        spiral_layout.addWidget(self.opacity_slider)
        spiral_layout.addWidget(self.opacity_label)
        
        # Rotation Speed
        spiral_layout.addWidget(QLabel("Rotation Speed:"))
        self.rotation_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_speed_slider.setRange(40, 400)  # 4.0 to 40.0x
        self.rotation_speed_slider.setValue(40)
        self.rotation_speed_slider.valueChanged.connect(self._on_rotation_speed_changed)
        self.rotation_speed_label = QLabel("4.0x")
        spiral_layout.addWidget(self.rotation_speed_slider)
        spiral_layout.addWidget(self.rotation_speed_label)
        
        # Spiral Reverse Direction
        self.spiral_reverse_check = QCheckBox("Reverse Spiral Direction")
        self.spiral_reverse_check.setChecked(False)
        self.spiral_reverse_check.stateChanged.connect(self._on_spiral_reverse_changed)
        spiral_layout.addWidget(self.spiral_reverse_check)
        
        # Spiral Colors
        color_layout = QHBoxLayout()
        self.arm_color_btn = QPushButton("Arm Color")
        self.arm_color_btn.clicked.connect(lambda: self._pick_color("arm"))
        self.gap_color_btn = QPushButton("Gap Color")
        self.gap_color_btn.clicked.connect(lambda: self._pick_color("gap"))
        color_layout.addWidget(self.arm_color_btn)
        color_layout.addWidget(self.gap_color_btn)
        spiral_layout.addLayout(color_layout)
        
        # Store colors
        self.arm_color = (1.0, 1.0, 1.0)  # White default
        self.gap_color = (0.0, 0.0, 0.0)  # Black default
        self._refresh_color_buttons()
        
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
        self.media_mode_combo.setCurrentIndex(0)  # Images & Videos default
        self.media_mode_combo.currentIndexChanged.connect(self._on_media_mode_changed)
        media_layout.addWidget(self.media_mode_combo)
        
        # Media Cycling Speed
        media_layout.addWidget(QLabel("Media Cycling Speed:"))
        self.media_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.media_speed_slider.setRange(1, 100)  # 1 = slowest (10s), 100 = fastest (0.05s)
        self.media_speed_slider.setValue(50)  # Medium speed default
        self.media_speed_slider.valueChanged.connect(self._on_media_speed_changed)
        self.media_speed_label = QLabel("50 (Medium)")
        media_layout.addWidget(self.media_speed_slider)
        media_layout.addWidget(self.media_speed_label)
        
        # Background Opacity (not in JSON, but in VMC for preview)
        media_layout.addWidget(QLabel("Background Opacity:"))
        self.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(100)
        self.bg_opacity_slider.valueChanged.connect(self._on_bg_opacity_changed)
        self.bg_opacity_label = QLabel("100%")
        media_layout.addWidget(self.bg_opacity_slider)
        media_layout.addWidget(self.bg_opacity_label)
        
        # Fade Duration
        media_layout.addWidget(QLabel("Media Fade Duration:"))
        self.fade_duration_slider = QSlider(Qt.Orientation.Horizontal)
        self.fade_duration_slider.setRange(0, 50)  # 0 to 5.0 seconds
        self.fade_duration_slider.setValue(5)  # Default 0.5 seconds
        self.fade_duration_slider.valueChanged.connect(self._on_fade_duration_changed)
        self.fade_duration_label = QLabel("0.5s")
        media_layout.addWidget(self.fade_duration_slider)
        media_layout.addWidget(self.fade_duration_label)
        
        # Media Bank Selection
        media_layout.addWidget(QLabel("─" * 30))
        media_layout.addWidget(QLabel("Media Bank Selection:"))
        media_layout.addWidget(QLabel("Select which directories this mode uses:"))
        
        # Media Bank list with checkboxes
        self.list_media_bank = QListWidget()
        self.list_media_bank.setMaximumHeight(150)
        self.list_media_bank.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_media_bank.itemChanged.connect(self._on_bank_selection_changed)
        media_layout.addWidget(self.list_media_bank)
        
        # Info label
        self.lbl_bank_info = QLabel("")
        self.lbl_bank_info.setStyleSheet("color: #666; font-size: 9pt;")
        media_layout.addWidget(self.lbl_bank_info)
        
        controls_layout.addWidget(media_group)
        
        # === Text Settings ===
        text_group = QGroupBox("Text Settings")
        text_layout = QVBoxLayout(text_group)
        
        # Text Enabled
        self.text_enabled_check = QCheckBox("Enable Text Overlay")
        self.text_enabled_check.setChecked(True)
        self.text_enabled_check.stateChanged.connect(self._on_text_enabled_changed)
        text_layout.addWidget(self.text_enabled_check)
        
        # Text Opacity
        text_layout.addWidget(QLabel("Text Opacity:"))
        self.text_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity_slider.setRange(0, 100)
        self.text_opacity_slider.setValue(80)
        self.text_opacity_slider.valueChanged.connect(self._on_text_opacity_changed)
        self.text_opacity_label = QLabel("80%")
        text_layout.addWidget(self.text_opacity_slider)
        text_layout.addWidget(self.text_opacity_label)
        
        # Text Display Mode
        text_layout.addWidget(QLabel("Text Display Mode:"))
        self.text_mode_combo = QComboBox()
        self.text_mode_combo.addItems([
            "Centered (Synced with Media)",
            "Scrolling Carousel (Wallpaper)"
        ])
        self.text_mode_combo.setCurrentIndex(0)  # Default to centered
        self.text_mode_combo.currentIndexChanged.connect(self._on_text_mode_changed)
        text_layout.addWidget(self.text_mode_combo)

        # Text sync toggle + manual speed
        self.text_sync_check = QCheckBox("Sync text with media cycle")
        self.text_sync_check.setChecked(True)
        self.text_sync_check.stateChanged.connect(self._on_text_sync_changed)
        text_layout.addWidget(self.text_sync_check)
        self._preferred_text_sync = True

        manual_speed_box = QVBoxLayout()
        manual_speed_box.addWidget(QLabel("Manual Text Speed:"))
        self.text_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_speed_slider.setRange(1, 100)
        self.text_speed_slider.setValue(50)
        self.text_speed_slider.valueChanged.connect(self._on_text_cycle_speed_changed)
        self.text_speed_slider.setEnabled(False)
        self.text_speed_label = QLabel()
        self.text_speed_label.setEnabled(False)
        manual_speed_box.addWidget(self.text_speed_slider)
        manual_speed_box.addWidget(self.text_speed_label)
        text_layout.addLayout(manual_speed_box)
        self._refresh_text_speed_label()
        
        # Info label
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
        self.zoom_mode_combo.currentIndexChanged.connect(self._mark_modified)
        zoom_layout.addWidget(self.zoom_mode_combo)
        
        # Zoom Rate
        zoom_layout.addWidget(QLabel("Zoom Rate:"))
        self.zoom_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_rate_slider.setRange(0, 500)  # 0.0 to 5.0
        self.zoom_rate_slider.setValue(20)  # 0.2 default
        self.zoom_rate_slider.valueChanged.connect(self._on_zoom_rate_changed)
        self.zoom_rate_label = QLabel("0.200")
        zoom_layout.addWidget(self.zoom_rate_slider)
        zoom_layout.addWidget(self.zoom_rate_label)
        
        controls_layout.addWidget(zoom_group)
        
        # === Action Buttons ===
        button_layout = QVBoxLayout()
        
        self.preview_info = QLabel("Preview: Adjust settings and see live preview")
        self.preview_info.setStyleSheet("color: #666; font-style: italic;")
        button_layout.addWidget(self.preview_info)
        
        # Save button
        self.save_button = QPushButton("💾 Save Playback")
        self.save_button.clicked.connect(self._save_playback)
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
        
        # Save As button
        self.save_as_button = QPushButton("📁 Save As...")
        self.save_as_button.clicked.connect(self._save_as_playback)
        self.save_as_button.setStyleSheet("""
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
        button_layout.addWidget(self.save_as_button)
        
        # Close button
        self.close_button = QPushButton("✖ Close")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        
        # Status display
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(120)
        self.status_display.setStyleSheet("background: #f9f9f9; font-family: monospace; font-size: 10px;")
        self.status_display.setPlainText("Ready to edit playback...")
        button_layout.addWidget(self.status_display)
        
        controls_layout.addLayout(button_layout)
        controls_layout.addStretch()
        
        # Initialize state
        self.manual_zoom_rate = None
        self.image_files = []
        self.video_files = []
        self.current_media_index = 0
        self.current_media_list = []
    
    # === Initialization Methods ===
    
    def _initialize_text_system(self):
        """Initialize text rendering after OpenGL context is ready."""
        if not PREVIEW_AVAILABLE:
            return
        
        logger.info("[PlaybackEditor] initialize_text_system() called")
        
        try:
            self.text_renderer = TextRenderer()
            logger.info("[PlaybackEditor] TextRenderer created successfully")
            
            self.text_director = TextDirector(
                text_renderer=self.text_renderer,
                compositor=self.compositor
            )
            logger.info("[PlaybackEditor] TextDirector created successfully")
            
            # Load sample text library
            sample_texts = [
                "Focus on my words",
                "Let your mind relax",
                "Deeper and deeper",
                "Feel the spiral pull you in",
                "Your thoughts are fading"
            ]
            self.text_director.set_text_library(sample_texts, default_split_mode=SplitMode.CENTERED_SYNC)
            self.text_director.set_enabled(True)
            self._apply_text_sync_settings()
            logger.info("[PlaybackEditor] Text system initialized successfully")
        except Exception as e:
            logger.error(f"[PlaybackEditor] Failed to initialize text system: {e}")

    def _determine_live_resolution(self) -> tuple[int, int]:
        """Pick the screen resolution that the preview should mimic."""
        screen = None

        try:
            window_handle = self.windowHandle()
            if window_handle:
                screen = window_handle.screen()
        except Exception:
            screen = None

        if screen is None and PREVIEW_AVAILABLE:
            try:
                comp_handle = self.compositor.windowHandle() if hasattr(self.compositor, "windowHandle") else None
                if comp_handle:
                    screen = comp_handle.screen()
            except Exception:
                screen = None

        if screen is None:
            screen = QGuiApplication.primaryScreen()

        if screen:
            size = screen.size()
            return max(1, size.width()), max(1, size.height())
        return (1920, 1080)

    def _apply_preview_virtual_size(self) -> None:
        """Override the preview compositor's logical size to match live output."""
        if not PREVIEW_AVAILABLE or not hasattr(self, "compositor"):
            return

        width, height = self._determine_live_resolution()
        try:
            self.compositor.set_virtual_screen_size(width, height)
            logger.info(f"[PlaybackEditor] Preview virtual screen set to {width}x{height}")
        except Exception as exc:
            logger.warning(f"[PlaybackEditor] Failed to set preview virtual size: {exc}")
    
    def _load_test_images(self):
        """Load test media from selected Media Bank entries."""
        if not PREVIEW_AVAILABLE:
            return
        
        # CRITICAL: Stop existing media cycle timer to prevent speed carryover
        if hasattr(self, 'image_cycle_timer') and self.image_cycle_timer is not None:
            if self.image_cycle_timer.isActive():
                self.image_cycle_timer.stop()
                logger.debug("[PlaybackEditor] Stopped media cycle timer before reloading media")
        
        selected_indices = self._get_selected_bank_indices()
        
        if not selected_indices:
            logger.warning("[PlaybackEditor] No Media Bank entries selected!")
            self.image_files = []
            self.video_files = []
            return
        
        logger.info(f"[PlaybackEditor] Loading media from {len(selected_indices)} selected bank entries")
        
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
        
        # Load images
        self.image_files = []
        for image_dir in image_dirs:
            if image_dir.exists():
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                    self.image_files.extend(list(image_dir.glob(ext)))
        
        self.image_files.sort()
        
        # Load videos
        self.video_files = []
        for video_dir in video_dirs:
            if video_dir.exists():
                for ext in ['*.mp4', '*.webm', '*.mkv', '*.avi', '*.mov']:
                    self.video_files.extend(list(video_dir.glob(ext)))
        
        self.video_files.sort()
        
        logger.info(f"[PlaybackEditor] Media scan complete: {len(self.image_files)} images, {len(self.video_files)} videos")
        
        self.current_media_index = 0
        self.current_media_list = []
        
        # Build media list based on mode
        self._rebuild_media_list()
        
        if self.current_media_list:
            self._load_next_media()
            
            # Start media cycling timer
            self.image_cycle_timer = QTimer()
            self.image_cycle_timer.timeout.connect(self._cycle_media)
            self._update_cycle_interval()
    
    # === Spiral Control Handlers ===
    
    def _compute_rpm(self, x_value: float, reversed_flag: bool) -> float:
        """Map UI "x" value (e.g., 4.0..40.0) to actual RPM with calibration."""
        rpm = float(x_value) * float(self.SPEED_GAIN)
        return -rpm if reversed_flag else rpm
    
    def _on_spiral_type_changed(self, index):
        """Handle spiral type change."""
        if not PREVIEW_AVAILABLE:
            return
        
        spiral_type = index + 1
        self.director.set_spiral_type(spiral_type)
        self._mark_modified()
        
        type_names = {
            1: "Logarithmic", 2: "Quadratic", 3: "Linear",
            4: "Square Root", 5: "Inverse", 6: "Power", 7: "Sawtooth"
        }
        logger.info(f"[PlaybackEditor] Spiral type: {type_names.get(spiral_type, spiral_type)}")
    
    def _on_opacity_changed(self, value):
        """Handle opacity slider."""
        if not PREVIEW_AVAILABLE:
            return
        
        opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")
        try:
            self.director.set_opacity(opacity)
        except Exception:
            self.director.set_intensity(opacity)
        self._mark_modified()
    
    def _on_rotation_speed_changed(self, value):
        """Handle rotation speed slider."""
        if not PREVIEW_AVAILABLE:
            return
        
        x_val = value / 10.0
        reversed_flag = self.spiral_reverse_check.isChecked()
        rpm = self._compute_rpm(x_val, reversed_flag)
        
        print(f"[PlaybackEditor SLIDER] value={value}, x_val={x_val:.1f}, rpm={rpm:.1f}", flush=True)
        
        self.rotation_speed_label.setText(f"{abs(x_val):.1f}x")
        self.rotation_speed_label.setToolTip(f"≈ {abs(rpm):.1f} RPM{' (reverse)' if reversed_flag else ''}")
        self.director.set_rotation_speed(rpm)
        self._mark_modified()
        
        logger.info(f"[PlaybackEditor] Rotation speed set: x={x_val:.1f} → rpm={rpm:.1f}")
    
    def _on_spiral_reverse_changed(self, state):
        """Handle spiral reverse checkbox."""
        logger.info(f"[PlaybackEditor] Spiral reverse changed: {state == 2}")
        self._on_rotation_speed_changed(self.rotation_speed_slider.value())
        self._mark_modified()
    
    def _pick_color(self, which: str):
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
                if PREVIEW_AVAILABLE:
                    self.director.set_arm_color(*rgb)
            else:
                self.gap_color = rgb
                if PREVIEW_AVAILABLE:
                    self.director.set_gap_color(*rgb)
            
            self._refresh_color_buttons()
            self._mark_modified()

    def _refresh_color_buttons(self):
        """Sync color button backgrounds with current RGB tuples."""
        if hasattr(self, "arm_color_btn"):
            arm_qcolor = QColor.fromRgbF(*self.arm_color)
            self.arm_color_btn.setStyleSheet(f"background-color: {arm_qcolor.name()};")
        if hasattr(self, "gap_color_btn"):
            gap_qcolor = QColor.fromRgbF(*self.gap_color)
            self.gap_color_btn.setStyleSheet(f"background-color: {gap_qcolor.name()};")

    @staticmethod
    def _clamp_color_tuple(values, fallback):
        """Return safe (r,g,b) tuple with components clamped to [0,1]."""
        try:
            r, g, b = values  # type: ignore
        except Exception:
            r, g, b = fallback
        def _clamp(component):
            try:
                return max(0.0, min(1.0, float(component)))
            except Exception:
                return 0.0
        return (_clamp(r), _clamp(g), _clamp(b))

    def _apply_spiral_colors_to_preview(self):
        """Push stored arm/gap colors into preview director (if active)."""
        if PREVIEW_AVAILABLE and hasattr(self, "director") and self.director:
            self.director.set_arm_color(*self.arm_color)
            self.director.set_gap_color(*self.gap_color)
        self._refresh_color_buttons()
    
    # === Media Control Handlers ===
    
    def _on_media_mode_changed(self, index):
        """Handle media mode change."""
        mode_names = ["Images & Videos", "Images Only", "Videos Only"]
        logger.info(f"[PlaybackEditor] Media mode changed to: {mode_names[index]}")
        
        self._refresh_media_bank_list()
        self._rebuild_media_list()
        
        # Trigger media reload after mode change
        if PREVIEW_AVAILABLE:
            QTimer.singleShot(100, self._load_test_images)
        
        self._mark_modified()
    
    def _on_media_speed_changed(self, value):
        """Handle media speed slider."""
        speed_desc, interval_s = self._describe_cycle_speed(value)
        self.media_speed_label.setText(f"{value} ({speed_desc}) - {interval_s:.2f}s")
        
        if PREVIEW_AVAILABLE:
            self._update_cycle_interval()
        
        self._mark_modified()

    def _describe_cycle_speed(self, value: int) -> tuple[str, float]:
        """Return descriptor + seconds for a 1-100 cycle speed (matches media slider)."""
        import math
        value = max(1, min(100, int(value)))
        normalized = (value - 1) / 99.0
        interval_ms = 10000 * math.pow(0.005, normalized)
        interval_s = interval_ms / 1000.0
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
        return speed_desc, interval_s

    def _is_carousel_mode(self) -> bool:
        return self.text_mode_combo.currentIndex() == 1

    def _enforce_text_sync_policy(self):
        """Force manual timing whenever the carousel mode is active."""
        carousel = self._is_carousel_mode()
        if carousel:
            if self.text_sync_check.isEnabled():
                self._preferred_text_sync = self.text_sync_check.isChecked()
            if self.text_sync_check.isChecked():
                self.text_sync_check.blockSignals(True)
                self.text_sync_check.setChecked(False)
                self.text_sync_check.blockSignals(False)
            self.text_sync_check.setEnabled(False)
            manual_allowed = True
        else:
            if not self.text_sync_check.isEnabled():
                self.text_sync_check.setEnabled(True)
                self.text_sync_check.blockSignals(True)
                self.text_sync_check.setChecked(self._preferred_text_sync)
                self.text_sync_check.blockSignals(False)
            manual_allowed = not self.text_sync_check.isChecked()
        self.text_speed_slider.setEnabled(manual_allowed)
        self.text_speed_label.setEnabled(manual_allowed)

    def _cycle_speed_to_frames(self, value: int) -> int:
        """Convert 1-100 slider value to frames at 60 FPS (shared with CustomVisual)."""
        import math
        value = max(1, min(100, int(value)))
        normalized = (value - 1) / 99.0
        interval_ms = 10000 * math.pow(0.005, normalized)
        return max(1, round((interval_ms / 1000.0) * 60.0))
    
    def _on_bg_opacity_changed(self, value):
        """Handle background opacity slider."""
        opacity = value / 100.0
        self.bg_opacity_label.setText(f"{value}%")
        # Note: Not saved to JSON, only for preview
    
    def _on_fade_duration_changed(self, value):
        """Handle fade duration slider."""
        duration_s = value / 10.0
        self.fade_duration_label.setText(f"{duration_s:.1f}s")
        
        if PREVIEW_AVAILABLE:
            self.compositor.set_fade_duration(duration_s)
        
        self._mark_modified()
    
    # === Text Control Handlers ===
    
    def _on_text_enabled_changed(self, state):
        """Handle text enabled checkbox."""
        if not PREVIEW_AVAILABLE:
            return
        
        enabled = state == 2
        if self.text_director:
            self.text_director.set_enabled(enabled)
            logger.info(f"[PlaybackEditor] Text rendering: {'enabled' if enabled else 'disabled'}")
        
        self._mark_modified()
    
    def _on_text_opacity_changed(self, value):
        """Handle text opacity slider."""
        opacity = value / 100.0
        self.text_opacity_label.setText(f"{value}%")
        
        if PREVIEW_AVAILABLE and self.compositor:
            self.compositor.set_text_opacity(opacity)
        
        self._mark_modified()
    
    def _on_text_mode_changed(self, index):
        """Handle text mode combo box."""
        self._enforce_text_sync_policy()
        self._apply_text_sync_settings()
        if not PREVIEW_AVAILABLE:
            self._mark_modified()
            return
        
        mode = SplitMode.CENTERED_SYNC if index == 0 else SplitMode.SUBTEXT
        if self.text_director:
            self.text_director.set_all_split_mode(mode)
            self.text_director._current_split_mode = mode
            
            if self.text_director._current_text:
                self.text_director._render_current_text()
            
            logger.info(f"[PlaybackEditor] Text mode changed to: {mode.name}")
        
        self._mark_modified()

    def _on_text_sync_changed(self, state):
        """Enable/disable manual text speed control and update director."""
        sync_enabled = state == Qt.CheckState.Checked
        if self.text_sync_check.isEnabled():
            self._preferred_text_sync = sync_enabled
        self._enforce_text_sync_policy()
        self._refresh_text_speed_label()
        self._apply_text_sync_settings()
        self._mark_modified()

    def _on_text_cycle_speed_changed(self, value):
        """Update manual text speed label + preview when slider moves."""
        self._refresh_text_speed_label(value)
        if self._is_carousel_mode() or not self.text_sync_check.isChecked():
            self._apply_text_sync_settings()
        self._mark_modified()

    def _apply_text_sync_settings(self):
        """Push sync/manual timing settings into the preview text director."""
        if not self.text_director:
            return
        frames = self._cycle_speed_to_frames(self.text_speed_slider.value())
        self.text_director.configure_sync(
            sync_with_media=self.text_sync_check.isChecked(),
            frames_per_text=frames
        )

    def _refresh_text_speed_label(self, value: int | None = None):
        if value is None:
            value = self.text_speed_slider.value()
        desc, interval = self._describe_cycle_speed(value)
        self.text_speed_label.setText(f"{value} ({desc}) - {interval:.2f}s")
    
    # === Zoom Control Handlers ===
    
    def _on_zoom_rate_changed(self, value):
        """Handle zoom rate slider."""
        if not PREVIEW_AVAILABLE:
            return
        
        import time
        rate = value / 100.0
        self.zoom_rate_label.setText(f"{rate:.3f}")
        
        self.manual_zoom_rate = rate
        self.compositor._zoom_rate = rate
        self.compositor._zoom_start_time = time.time()
        self.compositor._zoom_current = 1.0
        
        self._mark_modified()
    
    # === Media Loading Methods ===
    
    def _rebuild_media_list(self):
        """Rebuild media list based on current mode."""
        if not PREVIEW_AVAILABLE:
            return
        
        media_mode = self.media_mode_combo.currentIndex()
        
        if media_mode == 0:  # Images & Videos
            self.current_media_list = self.image_files + self.video_files
        elif media_mode == 1:  # Images Only
            self.current_media_list = self.image_files
        else:  # Videos Only
            self.current_media_list = self.video_files
        
        self.current_media_index = 0
        logger.info(f"[PlaybackEditor] Media list rebuilt: {len(self.current_media_list)} items")
    
    def _update_cycle_interval(self):
        """Update cycling timer interval based on speed setting."""
        if not PREVIEW_AVAILABLE or not hasattr(self, 'image_cycle_timer'):
            return
        
        speed = self.media_speed_slider.value()
        
        import math
        normalized = (speed - 1) / 99.0
        interval_ms = int(10000 * math.pow(0.005, normalized))
        
        self.image_cycle_timer.setInterval(interval_ms)
        self.image_cycle_timer.start()
        logger.info(f"[PlaybackEditor] Cycle interval updated: {interval_ms}ms (speed={speed})")
    
    def _cycle_media(self):
        """Cycle to next media item."""
        if not PREVIEW_AVAILABLE or not self.current_media_list:
            return
        
        self.current_media_index = (self.current_media_index + 1) % len(self.current_media_list)
        self._load_next_media()
    
    def _load_next_media(self):
        """Load the next media item (image or video) in cycle."""
        if not PREVIEW_AVAILABLE or not self.current_media_list:
            return
        
        try:
            media_file = self.current_media_list[self.current_media_index]
            logger.info(f"[PlaybackEditor] Loading media {self.current_media_index + 1}/{len(self.current_media_list)}: {media_file.name}")
            
            if media_file.suffix.lower() in ['.jpg', '.png', '.jpeg', '.bmp', '.gif', '.webp']:
                self._stop_video()
                self._load_image(media_file)
            else:
                self._load_video(media_file)
        except Exception as e:
            logger.error(f"[PlaybackEditor] Failed to load media: {e}")
    
    def _load_image(self, image_file):
        """Load a specific image file."""
        if not PREVIEW_AVAILABLE:
            return
        
        try:
            image_data = media.load_image_sync(image_file)
            
            self.compositor.makeCurrent()
            texture_id = upload_image_to_gpu(image_data)
            
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
                3: "linear"  # Disabled
            }
            mode = zoom_mode_map[self.zoom_mode_combo.currentIndex()]
            
            self.compositor.start_zoom_animation(
                start_zoom=1.0,
                duration_frames=9999,
                mode=mode
            )
            
            if self.manual_zoom_rate is not None:
                import time
                self.compositor._zoom_rate = self.manual_zoom_rate
                self.compositor._zoom_start_time = time.time()
                self.compositor._zoom_current = 1.0
            
            self.compositor.update()
            
            # Trigger text change
            if self.text_director:
                self.text_director.on_media_change()
            
            logger.info(f"[PlaybackEditor] Loaded image: {image_file.name}")
        except Exception as e:
            logger.error(f"[PlaybackEditor] Failed to load image: {e}")
    
    def _load_video(self, video_file):
        """Load and start playing a video file."""
        if not PREVIEW_AVAILABLE:
            return
        
        try:
            self._stop_video()
            
            self.video_cap = cv2.VideoCapture(str(video_file))
            
            if not self.video_cap.isOpened():
                logger.error(f"[PlaybackEditor] Failed to open video: {video_file.name}")
                return
            
            self.video_fps = self.video_cap.get(cv2.CAP_PROP_FPS)
            if self.video_fps <= 0:
                self.video_fps = 30.0
            
            self.current_video_file = video_file
            self.video_first_frame = True
            
            self.video_frame_timer = QTimer()
            self.video_frame_timer.timeout.connect(self._update_video_frame)
            frame_interval_ms = int(1000.0 / self.video_fps)
            self.video_frame_timer.start(frame_interval_ms)
            
            # Start zoom animation
            zoom_mode_map = {
                0: "exponential",
                1: "pulse",
                2: "linear",
                3: "linear"
            }
            mode = zoom_mode_map[self.zoom_mode_combo.currentIndex()]
            
            self.compositor.start_zoom_animation(
                start_zoom=1.0,
                duration_frames=9999,
                mode=mode
            )
            
            if self.manual_zoom_rate is not None:
                import time
                self.compositor._zoom_rate = self.manual_zoom_rate
                self.compositor._zoom_start_time = time.time()
                self.compositor._zoom_current = 1.0
            
            logger.info(f"[PlaybackEditor] Video started: {video_file.name}")
        except Exception as e:
            logger.error(f"[PlaybackEditor] Failed to load video: {e}")
    
    def _update_video_frame(self):
        """Update video frame."""
        if not PREVIEW_AVAILABLE or not self.video_cap:
            return
        
        try:
            ret, frame = self.video_cap.read()
            
            if not ret:
                # Loop video
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.video_cap.read()
                
                if not ret:
                    self._stop_video()
                    return
            
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width = frame_rgb.shape[:2]
            
            # Make OpenGL context current
            self.compositor.makeCurrent()
            
            # Get current zoom from compositor (managed by zoom animation)
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
            logger.error(f"[PlaybackEditor] Video frame error: {e}")
            self._stop_video()
    
    def _stop_video(self):
        """Stop any playing video."""
        if self.video_frame_timer:
            self.video_frame_timer.stop()
            self.video_frame_timer = None
        
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
        
        self.current_video_file = None
    
    # === Update Methods ===
    
    def _update_spiral(self):
        """Update spiral animation."""
        if not PREVIEW_AVAILABLE:
            return
        
        # Track tick rate for debugging
        if not hasattr(self, '_spiral_tick_count'):
            self._spiral_tick_count = 0
            self._spiral_tick_rate_start = None
            self._spiral_tick_rate_count = 0
            self._spiral_last_time = None  # For delta-time measurement
        
        self._spiral_tick_count += 1
        
        # Measure actual delta-time instead of assuming 1/30.0
        import time
        current_time = time.time()
        if self._spiral_last_time is not None:
            dt = current_time - self._spiral_last_time
        else:
            dt = 1/30.0  # First frame fallback
        self._spiral_last_time = current_time
        
        # Log tick rate every 30 ticks
        if self._spiral_tick_count % 30 == 0:
            if self._spiral_tick_rate_start is None:
                self._spiral_tick_rate_start = current_time
                self._spiral_tick_rate_count = 0
            else:
                self._spiral_tick_rate_count += 30
                elapsed = current_time - self._spiral_tick_rate_start
                actual_fps = self._spiral_tick_rate_count / elapsed if elapsed > 0 else 0
                logger.info(f"[_update_spiral] Tick rate: {actual_fps:.1f} FPS (target: 30 FPS, avg dt: {1/actual_fps if actual_fps > 0 else 0:.4f}s)")
        
        # Update spiral parameters using measured dt
        self.director.update(dt)
        
        # Cache uniforms to prevent compositor from calling update() again
        cached_uniforms = self.director.export_uniforms()
        self.compositor._uniforms_cache = cached_uniforms
        logger.debug(f"[_update_spiral] Set compositor._uniforms_cache (phase={cached_uniforms.get('phase', 'N/A')})")
        
        self.compositor.update_zoom_animation()
        self.compositor.update()
    
    def _update_render(self):
        """Update text director and compositor rendering."""
        if not PREVIEW_AVAILABLE:
            return
        
        if self.text_director:
            self.text_director.update()
        
        self.compositor.update()
    
    # === Media Bank Methods ===
    
    def _load_media_bank_config(self):
        """Load Media Bank configuration from shared config file."""
        config_path = PROJECT_ROOT / "media_bank.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._media_bank = json.load(f)
                logger.info(f"[PlaybackEditor] Loaded {len(self._media_bank)} entries from media bank")
            except Exception as e:
                logger.error(f"[PlaybackEditor] Failed to load media bank config: {e}")
                self._media_bank = []
        else:
            logger.info("[PlaybackEditor] No media bank config found")
            self._media_bank = []
    
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
        
        media_mode = self.media_mode_combo.currentIndex()
        
        for idx, entry in enumerate(self._media_bank):
            entry_type = entry["type"]
            entry_name = entry["name"]
            
            # Filter by media mode
            if media_mode == 1 and entry_type == "videos":
                continue
            if media_mode == 2 and entry_type == "images":
                continue
            
            # Icon based on type
            if entry_type == "images":
                icon = "🖼️"
            elif entry_type == "videos":
                icon = "🎬"
            else:
                icon = "📁"
            
            item = QListWidgetItem(f"{icon} {entry_name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Default to checked (select all banks by default)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            
            self.list_media_bank.addItem(item)
        
        self._update_bank_info()
    
    def _on_bank_selection_changed(self):
        """Handle media bank checkbox changes - reload media."""
        self._update_bank_info()
        
        # Reload media with new selection
        if PREVIEW_AVAILABLE:
            logger.info("[PlaybackEditor] Media bank selection changed, reloading media...")
            QTimer.singleShot(100, self._load_test_images)
    
    def _update_bank_info(self):
        """Update the info label showing selected bank count."""
        selected_count = sum(
            1 for i in range(self.list_media_bank.count())
            if self.list_media_bank.item(i).checkState() == Qt.CheckState.Checked
        )
        total_count = self.list_media_bank.count()
        self.lbl_bank_info.setText(f"Selected: {selected_count} of {total_count} directories")
        self._mark_modified()
    
    # === File Operations ===
    
    def _create_new(self):
        """Create new playback with defaults."""
        self.mode_name_input.setText("New Playback")
        self.status_display.setPlainText("New playback created. Configure settings and save.")
        
        # Set defaults (already set in UI)
        self.is_modified = False
    
    def _load_file(self, file_path: Path):
        """Load playback from JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Loaded playback: {file_path}")
            self._load_from_dict(data)
            
            self.status_display.setPlainText(f"Loaded: {file_path.name}")
            self.is_modified = False
        except Exception as e:
            logger.error(f"Failed to load playback: {e}")
            QMessageBox.critical(self, "Load Error", f"Failed to load playback:\n{e}")
    
    def _load_from_dict(self, data: dict):
        """Load playback settings from data dictionary (used by both file and session modes)."""
        # CRITICAL: Stop existing media cycle timer to prevent speed carryover
        if hasattr(self, 'image_cycle_timer') and self.image_cycle_timer is not None:
            if self.image_cycle_timer.isActive():
                self.image_cycle_timer.stop()
                logger.debug("[PlaybackEditor] Stopped media cycle timer before loading new playback")
        
        # CRITICAL: Reset compositor zoom to prevent zoom rate carryover
        if PREVIEW_AVAILABLE and hasattr(self, 'compositor') and self.compositor:
            if hasattr(self.compositor, 'reset_zoom'):
                self.compositor.reset_zoom()
                logger.debug("[PlaybackEditor] Reset compositor zoom before loading new playback")
        
        # Load metadata
        self.mode_name_input.setText(data.get("name", "Unnamed"))
        
        # Load spiral settings
        spiral = data.get("spiral", {})
        spiral_type = spiral.get("type", "linear")
        type_map = {
            "logarithmic": 0, "quadratic": 1, "linear": 2,
            "sqrt": 3, "inverse": 4, "power": 5, "sawtooth": 6
        }
        self.spiral_type_combo.setCurrentIndex(type_map.get(spiral_type, 2))
        
        # Rotation speed: stored as RPM, convert to slider value (x10)
        rpm = spiral.get("rotation_speed", 40.0)
        x_val = rpm / self.SPEED_GAIN
        print(f"[PlaybackEditor LOAD] rpm={rpm}, x_val={x_val}, slider_value={int(x_val * 10)}", flush=True)
        self.rotation_speed_slider.setValue(int(x_val * 10))
        
        # CRITICAL: Explicitly set rotation speed on director since slider valueChanged
        # may not fire during initialization
        if hasattr(self, 'director') and self.director:
            reversed_flag = spiral.get("reverse", False)
            final_rpm = -rpm if reversed_flag else rpm
            self.director.set_rotation_speed(final_rpm)
            print(f"[PlaybackEditor LOAD] Explicitly set director RPM: {final_rpm:.1f}", flush=True)
        
        self.opacity_slider.setValue(int(spiral.get("opacity", 0.8) * 100))
        self.spiral_reverse_check.setChecked(spiral.get("reverse", False))

        # Spiral colors (optional per-playback fields)
        self.arm_color = self._clamp_color_tuple(spiral.get("arm_color"), (1.0, 1.0, 1.0))
        self.gap_color = self._clamp_color_tuple(spiral.get("gap_color"), (0.0, 0.0, 0.0))
        self._apply_spiral_colors_to_preview()
        
        # Load media settings
        media_data = data.get("media", {})
        media_mode = media_data.get("mode", "both")
        mode_map = {"both": 0, "images": 1, "videos": 2}
        self.media_mode_combo.setCurrentIndex(mode_map.get(media_mode, 0))
        
        self.media_speed_slider.setValue(media_data.get("cycle_speed", 50))
        self.fade_duration_slider.setValue(int(media_data.get("fade_duration", 0.5) * 10))
        
        # Load bank selections
        bank_selections = media_data.get("bank_selections", [])
        self._refresh_media_bank_list()
        
        # If file has bank_selections, apply them; otherwise keep all checked
        if bank_selections:
            for i in range(self.list_media_bank.count()):
                item = self.list_media_bank.item(i)
                bank_idx = item.data(Qt.ItemDataRole.UserRole)
                item.setCheckState(
                    Qt.CheckState.Checked if bank_idx in bank_selections else Qt.CheckState.Unchecked
                )
        # else: keep all checked (default from _refresh_media_bank_list)
        
        # Load text settings
        text_data = data.get("text", {})
        self.text_enabled_check.setChecked(text_data.get("enabled", True))
        self.text_opacity_slider.setValue(int(text_data.get("opacity", 0.8) * 100))
        
        text_mode = text_data.get("mode", "centered_sync")
        mode_map = {"centered_sync": 0, "subtext": 1}
        self.text_mode_combo.setCurrentIndex(mode_map.get(text_mode, 0))

        # Text sync + manual speed
        manual_speed = int(text_data.get("manual_cycle_speed", 50))
        manual_speed = max(1, min(100, manual_speed))
        sync_with_media = text_data.get("sync_with_media", True)
        self.text_speed_slider.blockSignals(True)
        self.text_speed_slider.setValue(manual_speed)
        self.text_speed_slider.blockSignals(False)
        self.text_sync_check.blockSignals(True)
        self.text_sync_check.setChecked(sync_with_media)
        self.text_sync_check.blockSignals(False)
        self._preferred_text_sync = sync_with_media
        self._refresh_text_speed_label()
        self._enforce_text_sync_policy()
        self._apply_text_sync_settings()
        
        # Load zoom settings
        zoom_data = data.get("zoom", {})
        zoom_mode = zoom_data.get("mode", "exponential")
        mode_map = {"exponential": 0, "pulse": 1, "linear": 2, "none": 3}
        self.zoom_mode_combo.setCurrentIndex(mode_map.get(zoom_mode, 0))
        
        self.zoom_rate_slider.setValue(int(zoom_data.get("rate", 0.2) * 100))
        
        # Reload media with new bank selections
        if PREVIEW_AVAILABLE:
            QTimer.singleShot(100, self._load_test_images)
    
    def _save_playback(self):
        """Save playback (to session or file depending on mode)."""
        if self.is_session_mode:
            self._save_to_session()
        else:
            if not self.file_path:
                self._save_as_playback()
                return
            self._do_save_file(self.file_path)
    
    def _save_as_playback(self):
        """Save playback to new file (file mode only)."""
        if self.is_session_mode:
            # In session mode, just save to session
            self._save_to_session()
            return
        
        default_dir = PROJECT_ROOT / "mesmerglass" / "playbacks"
        default_dir.mkdir(parents=True, exist_ok=True)
        
        mode_name = self.mode_name_input.text().strip()
        default_filename = f"{mode_name.replace(' ', '_').lower()}.json"
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Playback",
            str(default_dir / default_filename),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filepath:
            self.file_path = Path(filepath)
            self._do_save_file(self.file_path)
    
    def _save_to_session(self):
        """Save playback to session dict (session mode)."""
        try:
            mode_name = self.mode_name_input.text().strip()
            if not mode_name:
                QMessageBox.warning(self, "Validation Error", "Please enter a mode name!")
                return
            
            # Build playback config dict
            config = self._build_config_dict()
            
            # Determine key (use existing or generate from name)
            if self.playback_key:
                key = self.playback_key
            else:
                # Generate key from name (for new playback)
                key = mode_name.replace(' ', '_').lower()
                # Ensure uniqueness
                base_key = key
                counter = 1
                while key in self.session_data.get("playbacks", {}):
                    key = f"{base_key}_{counter}"
                    counter += 1
            
            # Update session dict
            if "playbacks" not in self.session_data:
                self.session_data["playbacks"] = {}
            
            self.session_data["playbacks"][key] = config
            
            self.status_display.setPlainText(f"✅ Saved to session: {key}")
            self.is_modified = False
            logger.info(f"[PlaybackEditor] Saved playback to session: {key}")
            
            # Emit saved signal (empty string since no file)
            self.saved.emit("")
            
            QMessageBox.information(self, "Save Successful", f"Playback saved to session:\n{key}")
            
        except Exception as e:
            logger.error(f"[PlaybackEditor] Session save failed: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save playback:\n{e}")
    
    def _build_config_dict(self) -> dict:
        """Build playback configuration dictionary (shared by file and session save)."""
        mode_name = self.mode_name_input.text().strip()
        
        # Build JSON config
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
        
        # Compute calibrated RPM for export
        x_val = self.rotation_speed_slider.value() / 10.0
        export_rpm = self._compute_rpm(x_val, False)  # magnitude only, reverse is separate
        
        return {
            "version": "1.0",
            "name": mode_name,
            "description": f"Custom playback created on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            
            "spiral": {
                "type": spiral_type_names[spiral_type_index] if spiral_type_index < len(spiral_type_names) else "logarithmic",
                "rotation_speed": export_rpm,
                "opacity": self.opacity_slider.value() / 100.0,
                "reverse": self.spiral_reverse_check.isChecked(),
                "arm_color": [round(c, 4) for c in self.arm_color],
                "gap_color": [round(c, 4) for c in self.gap_color]
            },
            
            "media": {
                "mode": media_modes[media_mode_index] if media_mode_index < len(media_modes) else "both",
                "cycle_speed": self.media_speed_slider.value(),
                "fade_duration": self.fade_duration_slider.value() / 10.0,
                "use_theme_bank": True,
                "paths": [],
                "shuffle": False,
                "bank_selections": self._get_selected_bank_indices()
            },
            
            "text": {
                "enabled": self.text_enabled_check.isChecked(),
                "mode": text_modes[text_mode_index] if text_mode_index < len(text_modes) else "centered_sync",
                "opacity": self.text_opacity_slider.value() / 100.0,
                "use_theme_bank": True,
                "library": [],
                "sync_with_media": self.text_sync_check.isChecked() and not self._is_carousel_mode(),
                "manual_cycle_speed": self.text_speed_slider.value()
            },
            
            "zoom": {
                "mode": zoom_mode,
                "rate": self.zoom_rate_slider.value() / 100.0
            }
        }
    
    def _do_save_file(self, filepath: Path):
        """Perform file save operation (file mode)."""
        try:
            mode_name = self.mode_name_input.text().strip()
            if not mode_name:
                QMessageBox.warning(self, "Validation Error", "Please enter a mode name!")
                return
            
            # Build config using shared method
            config = self._build_config_dict()
            
            # Write JSON file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.status_display.setPlainText(f"✅ Saved: {filepath.name}")
            self.is_modified = False
            logger.info(f"[PlaybackEditor] Saved playback to {filepath}")
            
            # Emit saved signal
            self.saved.emit(str(filepath))
            
            QMessageBox.information(self, "Save Successful", f"Playback saved to:\n{filepath}")
            
        except Exception as e:
            logger.error(f"[PlaybackEditor] Save failed: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save playback:\n{e}")
    
    def _mark_modified(self):
        """Mark the playback as modified."""
        self.is_modified = True
        title = "Playback Editor"
        if self.file_path:
            title += f" - {self.file_path.name}"
        if self.is_modified:
            title += " *"
        self.setWindowTitle(title)
    
    def closeEvent(self, event):
        """Handle window close event."""
        if self.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Save:
                self._save_playback()
                if self.is_modified:  # Save was cancelled
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        
        # Stop timers
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'render_timer'):
            self.render_timer.stop()
        if hasattr(self, 'image_cycle_timer'):
            self.image_cycle_timer.stop()
        
        self._stop_video()
        
        event.accept()
