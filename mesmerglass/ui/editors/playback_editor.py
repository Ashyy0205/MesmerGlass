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
import random
import time
import threading
import traceback
import cv2
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import contextmanager
import difflib
import re
import os

from PyQt6.QtCore import Qt, QTimer, QCoreApplication, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSlider, QCheckBox, QTextEdit,
    QGroupBox, QMessageBox, QFileDialog, QColorDialog,
    QScrollArea, QFrame, QListWidget, QListWidgetItem,
    QDialogButtonBox
)
from PyQt6.QtGui import QColor, QGuiApplication

from mesmerglass.content.media_scan import scan_font_directory, scan_media_directory
from mesmerglass.platform_paths import get_user_data_dir, ensure_dir

logger = logging.getLogger(__name__)

# Import compositor and directors for live preview
try:
    from mesmerglass.mesmerloom.compositor import LoomCompositor
    from mesmerglass.mesmerloom.spiral import SpiralDirector
    from mesmerglass.content.texture import upload_image_to_gpu
    from mesmerglass.content import media
    from mesmerglass.content.text_renderer import TextRenderer, SplitMode
    from mesmerglass.engine.text_director import TextDirector
    from mesmerglass.content.themebank import ThemeBank
    from mesmerglass.content.theme import ThemeConfig
    from mesmerglass.content.simple_video_streamer import SimpleVideoStreamer
    from mesmerglass.mesmerloom.visual_director import VisualDirector
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

    # Thread-safe signal to deliver media scan results back to the UI thread.
    # Args: token, image_paths, video_paths, font_paths
    media_scan_completed = pyqtSignal(int, object, object, object)
    
    # Speed calibration constant (matches VMC exactly)
    SPEED_GAIN = 10.0  # Calibrates modern RPM to match legacy "feel" (x4 old ≈ x40 new)

    # Accelerate preset targets
    ACCEL_ROTATION_START_X = 4.0
    ACCEL_ROTATION_END_X = 24.0
    ACCEL_MEDIA_START_SPEED = 50
    ACCEL_MEDIA_END_SPEED = 100
    ACCEL_ZOOM_START_RATE = 0.4
    ACCEL_ZOOM_END_RATE = 3.0
    ACCEL_MEDIA_UPDATE_COOLDOWN = 0.15  # seconds between accelerate-driven timer updates
    ACCEL_AUTO_ENABLE_DELAY_MS = 2500  # delay before reenabling accelerate presets on load
    
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
        self._accelerate_start_time = None
        self._accelerate_progress = 0.0
        self._accelerate_overriding = False
        self._accelerate_rotation_start_x = None
        self._accelerate_media_start_speed = None
        self._accelerate_zoom_start_rate = None
        self._accelerate_last_media_speed = None
        self._accelerate_media_speed_target = None
        self._accelerate_media_speed_smoothed = None
        self._accelerate_hidden_disabled = False
        self._accelerate_auto_enable_pending = False
        self._accelerate_auto_enable_scheduled = False
        self._accelerate_auto_enable_timer = None
        self._last_cycle_interval_ms = None
        self._cycle_debug_last_tick = None
        self._cycle_debug_last_media = None
        self._text_init_delay_cycles = 2  # defer text init until a couple of stable cycles
        self._text_init_triggered = False
        self._accelerate_last_interval_update_ts = None
        self._accelerate_overdue_throttled = False
        self._accelerate_overdue_throttle_last_log_ts = None
        self._trace_last_operation = None
        self._trace_last_operation_duration_ms = None
        self._trace_last_operation_finished_ts = None
        self._trace_slow_threshold_ms = 500.0
        self._trace_last_stack_dump_ts = None
        self._trace_stack_dump_cooldown_s = 5.0
        self._trace_stack_dump_inflight = False
        self._ui_thread_ident = threading.get_ident()
        self._cycle_watchdog_timer = None
        self._cycle_watchdog_token = None
        self._cycle_watchdog_timeout_factor = 5.0
        self._cycle_debug_expected_fire_ts = None
        self._cycle_debug_last_handler_duration_ms = None
        self._cycle_debug_overdue_logged = False
        self._cycle_debug_overdue_restart_active = False
        self._cycle_debug_overdue_restart_count = 0
        self._cycle_debug_last_overdue_restart_ts = None
        self._spiral_last_update_begin_ts = None
        self._spiral_last_update_finish_ts = None
        self._spiral_last_update_duration_ms = None
        self._spiral_last_update_dt_ms = None
        self._spiral_update_inflight = False
        self._spiral_tick_rate_last_fps = None
        self._spiral_tick_rate_last_avg_dt_ms = None
        self._spiral_tick_rate_last_report_ts = None

        # --- Live-parity preview engine (VisualDirector + ThemeBank + CustomVisual) ---
        # When enabled, we stop the PlaybackEditor-specific media cycling timers and
        # instead tick the same pipeline used by cuelist playback.
        self._preview_engine_requested = bool(PREVIEW_AVAILABLE)
        self._preview_engine_enabled = False
        self._preview_theme_bank = None
        self._preview_video_streamer = None
        self._preview_visual_director = None
        self._preview_last_tick_perf = None
        self._preview_config_reload_timer = None
        self._preview_config_reload_reason = None
        self._preview_playback_path = None

        self._initialize_editor()

        try:
            self.media_scan_completed.connect(self._on_media_scan_completed)
        except Exception:
            pass

    def _on_media_scan_completed(self, scan_token: int, image_paths: object, video_paths: object, font_paths: object) -> None:
        """Apply worker-thread scan results on the UI thread."""

        if getattr(self, "_media_scan_token", None) != scan_token:
            return

        try:
            image_list = list(image_paths or [])
            video_list = list(video_paths or [])
            font_list = list(font_paths or [])
        except Exception:
            image_list, video_list, font_list = [], [], []

        self.image_files = [Path(p) for p in image_list]
        self.video_files = [Path(p) for p in video_list]

        # Deduplicate fonts while preserving order
        deduped_fonts: list[str] = []
        seen_fonts: set[str] = set()
        for font_path in font_list:
            key = str(font_path).lower()
            if key in seen_fonts:
                continue
            seen_fonts.add(key)
            deduped_fonts.append(str(font_path))

        logger.info(
            "[PlaybackEditor] Media scan complete: %d images, %d videos, %d fonts",
            len(self.image_files),
            len(self.video_files),
            len(deduped_fonts),
        )

        # Many users run with WARNING-level console logs; surface the result there too.
        logger.warning(
            "[PlaybackEditor] Media scan result: %d images, %d videos, %d fonts",
            len(self.image_files),
            len(self.video_files),
            len(deduped_fonts),
        )

        try:
            self.status_display.setPlainText(
                f"✅ Media scan complete.\n"
                f"Images: {len(self.image_files)}\n"
                f"Videos: {len(self.video_files)}\n"
                f"Fonts: {len(deduped_fonts)}"
            )
        except Exception:
            pass

        if not self.image_files and not self.video_files:
            logger.warning(
                "[PlaybackEditor] No media discovered for selected banks (check paths/types/permissions)."
            )
            try:
                self.status_display.setPlainText(
                    "⚠️ No media found for selected banks.\n"
                    "Check Media Bank paths (especially after corrections like Image&Video), "
                    "and verify the folders contain supported file types."
                )
            except Exception:
                pass

        self.current_media_index = 0
        self.current_media_list = []

        self._pending_font_bank_fonts = deduped_fonts
        if deduped_fonts:
            self._apply_preview_font_from_bank()

        # If live-parity preview is active, rebuild the ThemeBank from scan results.
        # Otherwise fall back to legacy preview behavior below.
        if self._is_live_parity_preview_enabled():
            self._rebuild_preview_theme_bank(
                image_files=self.image_files,
                video_files=self.video_files,
                fonts=deduped_fonts,
            )
            self._schedule_preview_config_reload(reason="media_scan_completed")
            return

        self._rebuild_media_list()

        if self.current_media_list:
            self._load_next_media()

            # Start (or replace) the media cycling timer.
            # Ensure we never end up with multiple active timers calling _cycle_media.
            old_timer = getattr(self, "image_cycle_timer", None)
            if old_timer is not None:
                try:
                    old_timer.stop()
                except Exception:
                    pass
                try:
                    old_timer.timeout.disconnect(self._cycle_media)
                except Exception:
                    pass
                try:
                    old_timer.deleteLater()
                except Exception:
                    pass

            self.image_cycle_timer = QTimer(self)
            self.image_cycle_timer.timeout.connect(self._cycle_media)
            self._last_cycle_interval_ms = None

            # Set initial cycle interval (will be overridden by acceleration if enabled)
            self._update_cycle_interval(reason="initial_media_load")

    def _reset_cycle_debug_state(self):
        self._cycle_debug_last_tick = None
        self._cycle_debug_expected_fire_ts = None
        self._cycle_debug_last_media = None
        self._cycle_debug_last_handler_duration_ms = None
        self._cycle_debug_overdue_logged = False
        self._cycle_debug_overdue_restart_active = False
        self._cycle_debug_overdue_restart_count = 0
        self._cycle_debug_last_overdue_restart_ts = None
        self._accelerate_overdue_throttled = False
        self._accelerate_overdue_throttle_last_log_ts = None

    def _initialize_editor(self):
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
            self._refresh_media_bank_list()
        elif self.file_path:
            # File mode: load from file
            self._load_file(self.file_path)
            loaded_data = True
        else:
            # File mode: new file
            self._create_new()
            self._refresh_media_bank_list()
        
        # Initialize after compositor is ready
        # For live-parity preview we want the real playback pipeline, not test images.
        if PREVIEW_AVAILABLE:
            QTimer.singleShot(0, self._initialize_text_system)
            QTimer.singleShot(0, self._init_live_parity_preview_engine)
            # Kick off a scan so selected media banks populate the preview ThemeBank.
            QTimer.singleShot(50, self._load_test_images)
        else:
            QTimer.singleShot(500, self._load_test_images)
        
        # Start timers
        if PREVIEW_AVAILABLE:
            # Drive preview at ~60fps so VisualDirector's frame-based cyclers match live playback.
            self.timer = QTimer()
            self.timer.timeout.connect(self._preview_tick)
            self.timer.start(16)
            
            # Legacy render_timer is not needed when we run a unified tick.
            self.render_timer = None
            
            # Let fades be controlled by the playback config (for live parity).
            # Default to instant swaps unless the loaded playback specifies otherwise.
            fade_duration = 0.0
            if isinstance(getattr(self, "playback_data", None), dict):
                try:
                    fade_duration = float(
                        (self.playback_data.get("media", {}) or {}).get("fade_duration", 0.0) or 0.0
                    )
                except (TypeError, ValueError):
                    fade_duration = 0.0
            fade_duration = max(0.0, float(fade_duration or 0.0))
            self.compositor.set_fade_duration(fade_duration)
            
            # Update initial state only if we didn't load data
            # (if we loaded data, the setCurrentIndex calls already updated the director)
            if not loaded_data:
                self._on_spiral_type_changed(2)  # Linear
                self._on_rotation_speed_changed(40)
                self._on_zoom_rate_changed(20)

        # Initialize accelerate timing once UI + timers are ready
        self._reset_accelerate_progress()

    def _is_live_parity_preview_enabled(self) -> bool:
        return bool(getattr(self, "_preview_engine_enabled", False) and getattr(self, "_preview_visual_director", None) is not None)

    def _maybe_schedule_preview_reload(self, *, reason: str, delay_ms: int = 140) -> None:
        """Debounced preview reload for UI edits.

        This is intentionally a no-op when the live-parity preview engine is not
        requested/enabled, or when a bulk load operation is in progress.
        """

        if not getattr(self, "_preview_engine_requested", False):
            return
        if getattr(self, "_suppress_preview_reload", False):
            return
        if not self._is_live_parity_preview_enabled():
            return
        self._schedule_preview_config_reload(reason=reason, delay_ms=delay_ms)

    def _init_live_parity_preview_engine(self) -> None:
        """Initialize VisualDirector+ThemeBank preview so behavior matches live compositor."""

        if not PREVIEW_AVAILABLE:
            return

        # Stop legacy cycling as early as possible to prevent double-driving.
        self._stop_legacy_media_timers_for_live_preview()

        if getattr(self, "_preview_engine_enabled", False):
            return

        try:
            # Create video streamer + empty ThemeBank (replaced after media scan).
            self._preview_video_streamer = SimpleVideoStreamer(buffer_size=180, prefill_frames=24)

            theme = ThemeConfig(
                name="Preview",
                enabled=True,
                image_path=[],
                animation_path=[],
                font_path=[],
                text_line=[],
            )
            self._preview_theme_bank = ThemeBank(
                themes=[theme],
                root_path=Path("."),
                image_cache_size=256,
            )
            self._preview_theme_bank.set_active_themes(primary_index=1)

            # Create visual director using the SAME integration as live playback.
            self._preview_visual_director = VisualDirector(
                theme_bank=self._preview_theme_bank,
                compositor=self.compositor,
                text_renderer=getattr(self, "text_renderer", None),
                video_streamer=self._preview_video_streamer,
                text_director=getattr(self, "text_director", None),
                mesmer_server=None,
            )

            # Wire text change callback to director if supported (matches MainApplication).
            if self.text_director is not None and hasattr(self.text_director, "_on_text_change"):
                try:
                    self.text_director._on_text_change = self._preview_visual_director._on_change_text
                except Exception:
                    pass

            self._preview_engine_enabled = True

            # Debounced preview reload (write JSON + CustomVisual.reload_from_disk())
            self._preview_config_reload_timer = QTimer(self)
            self._preview_config_reload_timer.setSingleShot(True)
            self._preview_config_reload_timer.timeout.connect(self._reload_live_parity_preview_from_ui)

            # Create stable on-disk preview playback path in persistent user data dir.
            preview_dir = ensure_dir(get_user_data_dir("MesmerGlass") / "preview")
            self._preview_playback_path = preview_dir / "playback_editor_preview.json"

            # Initial load.
            # If a scan already completed before we initialized, rebuild ThemeBank now.
            if getattr(self, "image_files", None) or getattr(self, "video_files", None) or getattr(self, "_pending_font_bank_fonts", None):
                self._rebuild_preview_theme_bank(
                    image_files=getattr(self, "image_files", []) or [],
                    video_files=getattr(self, "video_files", []) or [],
                    fonts=getattr(self, "_pending_font_bank_fonts", []) or [],
                )
            self._schedule_preview_config_reload(reason="init")
            logger.info("[PlaybackEditor] Live-parity preview engine initialized")

        except Exception as exc:
            self._preview_engine_enabled = False
            self._preview_visual_director = None
            logger.warning(f"[PlaybackEditor] Live-parity preview engine init failed: {exc}")

    def _stop_legacy_media_timers_for_live_preview(self) -> None:
        """Stop editor-owned media timers so VisualDirector is the sole driver."""

        # Stop legacy image cycle timer
        old_timer = getattr(self, "image_cycle_timer", None)
        if old_timer is not None:
            try:
                old_timer.stop()
            except Exception:
                pass
            try:
                old_timer.timeout.disconnect(self._cycle_media)
            except Exception:
                pass
            try:
                old_timer.deleteLater()
            except Exception:
                pass
        self.image_cycle_timer = None

        # Stop legacy cv2 video path
        try:
            self._stop_video()
        except Exception:
            pass

    def _rebuild_preview_theme_bank(self, *, image_files: list[Path], video_files: list[Path], fonts: list[str]) -> None:
        if not self._is_live_parity_preview_enabled():
            return

        try:
            theme = ThemeConfig(
                name="Preview",
                enabled=True,
                image_path=[str(p) for p in (image_files or [])],
                animation_path=[str(p) for p in (video_files or [])],
                font_path=[],
                text_line=[],
            )
            tb = ThemeBank(
                themes=[theme],
                root_path=Path("."),
                image_cache_size=256,
            )
            tb.set_active_themes(primary_index=1)
            if fonts:
                tb.set_font_library(fonts)

            self._preview_theme_bank = tb
            self._preview_visual_director.theme_bank = tb
            if getattr(self._preview_visual_director, "current_visual", None) is not None:
                try:
                    self._preview_visual_director.current_visual.theme_bank = tb
                except Exception:
                    pass

            logger.info(
                "[PlaybackEditor] Preview ThemeBank rebuilt: %d images, %d videos, %d fonts",
                len(image_files or []),
                len(video_files or []),
                len(fonts or []),
            )
        except Exception as exc:
            logger.warning(f"[PlaybackEditor] Failed to rebuild preview ThemeBank: {exc}")

    def _schedule_preview_config_reload(self, *, reason: str, delay_ms: int = 120) -> None:
        if not self._is_live_parity_preview_enabled():
            return

        if self._preview_config_reload_timer is None:
            return

        self._preview_config_reload_reason = reason
        try:
            self._preview_config_reload_timer.start(max(0, int(delay_ms)))
        except Exception:
            pass

    def _reload_live_parity_preview_from_ui(self) -> None:
        """Write current UI config to preview file and reload CustomVisual in-place."""

        if not self._is_live_parity_preview_enabled():
            return

        if self._preview_playback_path is None:
            return

        try:
            config = self._build_config_dict()
            ensure_dir(self._preview_playback_path.parent)
            with open(self._preview_playback_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Load the preview playback once, then reload in place for subsequent edits.
            if getattr(self._preview_visual_director, "current_visual", None) is None:
                loaded = self._preview_visual_director.load_playback(self._preview_playback_path)
                if loaded:
                    self._preview_visual_director.start_playback()
                else:
                    return
            else:
                visual = self._preview_visual_director.current_visual
                if hasattr(visual, "reload_from_disk"):
                    visual.reload_from_disk()
                elif hasattr(visual, "reapply_all_settings"):
                    # Fallback if reload is unavailable.
                    visual.reapply_all_settings()

        except Exception as exc:
            logger.warning(f"[PlaybackEditor] Preview reload failed: {exc}")

    def _preview_tick(self) -> None:
        """Unified preview tick (~60fps) to match live playback behavior."""

        if not PREVIEW_AVAILABLE:
            return

        now = time.perf_counter()
        last = self._preview_last_tick_perf
        self._preview_last_tick_perf = now
        if last is None:
            dt = 1.0 / 60.0
        else:
            dt = max(0.0, min(0.1, now - last))

        # Update spiral at the same cadence as media/visual frames.
        try:
            # When live-parity preview is enabled, CustomVisual drives accelerate;
            # avoid the editor's separate accelerate logic.
            if not self._is_live_parity_preview_enabled():
                self._update_accelerate_effects()
            self.director.update(dt)
            cached_uniforms = self.director.export_uniforms()
            self.compositor._uniforms_cache = cached_uniforms
        except Exception:
            pass

        # Advance the real visual pipeline (ThemeBank async_update + cyclers + video).
        if self._is_live_parity_preview_enabled():
            try:
                self._preview_visual_director.update()
            except Exception:
                pass

        # Drive compositor animations + text updates.
        try:
            self.compositor.update_zoom_animation()
        except Exception:
            pass

        try:
            if self.text_director:
                self.text_director.update()
        except Exception:
            pass

        try:
            self.compositor.update()
        except Exception:
            pass
    
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
            # Allow accelerated zoom to climb continuously until media swap
            if hasattr(self.compositor, "set_max_zoom_before_reset"):
                self.compositor.set_max_zoom_before_reset(None)
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
        self.text_color = (1.0, 1.0, 1.0)  # Text overlay default
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
        
        fade_info = QLabel("Media fades have been disabled (instant cuts).")
        fade_info.setStyleSheet("color: #777; font-size: 9pt;")
        media_layout.addWidget(fade_info)
        
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

        # Text color picker
        self.text_color_btn = QPushButton("Text Color")
        self.text_color_btn.clicked.connect(self._pick_text_color)
        text_layout.addWidget(self.text_color_btn)

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
        self._refresh_text_color_button()
        
        # === Zoom Settings ===
        zoom_group = QGroupBox("Zoom Settings")
        zoom_layout = QVBoxLayout(zoom_group)
        
        # Zoom Mode
        zoom_layout.addWidget(QLabel("Zoom Mode:"))
        self.zoom_mode_combo = QComboBox()
        self.zoom_mode_combo.addItems([
            "Exponential (Falling In)",
            "Disabled"
        ])
        self.zoom_mode_combo.setCurrentIndex(0)  # Exponential default
        self.zoom_mode_combo.currentIndexChanged.connect(self._on_zoom_mode_changed)
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

        # === Accelerate Settings ===
        accel_group = QGroupBox("Accelerate Settings")
        accel_layout = QVBoxLayout(accel_group)

        self.accelerate_enable_check = QCheckBox("Enable accelerate ramp")
        self.accelerate_enable_check.setChecked(False)
        self.accelerate_enable_check.stateChanged.connect(self._on_accelerate_enabled_changed)
        accel_layout.addWidget(self.accelerate_enable_check)

        accel_layout.addWidget(QLabel("Ramp Duration (seconds):"))
        self.accelerate_duration_slider = QSlider(Qt.Orientation.Horizontal)
        self.accelerate_duration_slider.setRange(5, 120)  # 5s to 2 minutes
        self.accelerate_duration_slider.setValue(30)
        self.accelerate_duration_slider.valueChanged.connect(self._on_accelerate_duration_changed)
        accel_layout.addWidget(self.accelerate_duration_slider)

        self.accelerate_duration_label = QLabel("30s")
        accel_layout.addWidget(self.accelerate_duration_label)

        self.accelerate_state_label = QLabel("Disabled")
        self.accelerate_state_label.setStyleSheet("color: #666; font-size: 10px;")
        accel_layout.addWidget(self.accelerate_state_label)

        accel_hint = QLabel("Ramp targets: rotation 4→90, media 50→100, zoom 0.4→3.0")
        accel_hint.setStyleSheet("color: #777; font-size: 9px;")
        accel_hint.setWordWrap(True)
        accel_layout.addWidget(accel_hint)

        controls_layout.addWidget(accel_group)
        
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
        self._capture_accelerate_start_values()
        self._pending_font_bank_fonts: list[str] = []
    
    # === Initialization Methods ===
    
    def _initialize_text_system(self):
        """Initialize text rendering after OpenGL context is ready."""
        if not PREVIEW_AVAILABLE:
            return
        
        logger.info("[PlaybackEditor] initialize_text_system() called")
        
        with self._trace_operation("initialize_text_system"):
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
                self._apply_text_color_to_preview()
                if self._pending_font_bank_fonts:
                    self._apply_preview_font_from_bank()
                logger.info("[PlaybackEditor] Text system initialized successfully")
            except Exception as e:
                logger.error(f"[PlaybackEditor] Failed to initialize text system: {e}")

    def _maybe_schedule_text_system_init(self):
        """Delay text initialization until after a few media cycles complete."""
        if (not PREVIEW_AVAILABLE or self.text_director or self._text_init_triggered
                or self._text_init_delay_cycles is None):
            return

        self._text_init_delay_cycles -= 1
        if self._text_init_delay_cycles > 0:
            logger.info(
                "[PlaybackEditor] Text init deferred: waiting %s more cycle(s)",
                self._text_init_delay_cycles
            )
            return

        self._text_init_delay_cycles = None
        self._text_init_triggered = True
        logger.info("[PlaybackEditor] Text init warm-up complete; scheduling renderer setup")
        QTimer.singleShot(0, self._initialize_text_system)

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

        try:
            self.status_display.setPlainText("🔄 Scanning selected media banks…")
        except Exception:
            pass
        
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

        # Run directory scans off the UI thread. Some banks can be network shares
        # with deep folder structures (thousands of files) and will otherwise
        # freeze the editor.
        self._media_scan_token = getattr(self, "_media_scan_token", 0) + 1
        scan_token = self._media_scan_token
        
        def _scan_worker():
            def _normalize_entry_type(raw: object) -> str:
                value = str(raw or "").strip().lower()
                if value in ("images", "image", "img", "pics", "pictures", "photo", "photos"):
                    return "images"
                if value in ("videos", "video", "vid", "movie", "movies"):
                    return "videos"
                if value in ("fonts", "font", "typeface", "typefaces"):
                    return "fonts"
                if value in ("both", "all", "mixed"):
                    return "both"
                # Default to 'both' to be forgiving with legacy/unknown values.
                return "both"

            def _safe_exists(path: Path) -> bool:
                try:
                    return path.exists()
                except Exception:
                    return False

            def _resolve_directory_path(raw: Path) -> Path:
                """Best-effort correction for missing path segments.

                Mirrors the main application's media-bank path correction so the
                Playback Editor preview sees the same media.
                """
                candidate = raw
                if _safe_exists(candidate):
                    return candidate

                parts = list(candidate.parts)
                if not parts:
                    return candidate

                # Drive anchor like 'V:\\' or UNC like '\\\\server\\share'.
                anchor = Path(parts[0])
                start_index = 1
                if len(parts) >= 2 and parts[0].startswith('\\\\'):
                    anchor = Path('\\\\' + parts[0].lstrip('\\'))
                    if len(parts) >= 2:
                        anchor = Path('\\\\' + parts[0].lstrip('\\')) / parts[1]
                        start_index = 2

                current = anchor
                if not _safe_exists(current):
                    return candidate

                remaining = parts[start_index:]
                for segment in remaining:
                    next_path = current / segment
                    if _safe_exists(next_path):
                        current = next_path
                        continue

                    try:
                        siblings = [p.name for p in current.iterdir() if p.is_dir()]
                    except Exception:
                        return candidate

                    matches = difflib.get_close_matches(segment, siblings, n=1, cutoff=0.75)
                    if not matches:
                        # Combined folder name fallback: "Image&Video" → parent if Image/Video exist
                        if any(ch in segment for ch in ("&", "+")):
                            parts_guess = [p.strip() for p in re.split(r"[&+]", segment) if p.strip()]
                            existing_parts = [p for p in parts_guess if _safe_exists(current / p)]
                            if existing_parts:
                                logger.warning(
                                    "[PlaybackEditor] Media bank folder '%s' not found under %s; using parent (found subfolders: %s)",
                                    segment,
                                    current,
                                    ", ".join(existing_parts),
                                )
                                return current
                        return candidate

                    corrected = matches[0]
                    logger.warning(
                        "[PlaybackEditor] Media bank path segment '%s' not found under %s; using '%s'",
                        segment,
                        current,
                        corrected,
                    )
                    current = current / corrected

                return current

            # Collect directories by type
            image_dirs: list[Path] = []
            video_dirs: list[Path] = []
            font_dirs: list[Path] = []

            for idx in selected_indices:
                if idx >= len(self._media_bank):
                    continue

                entry = self._media_bank[idx]
                entry_path = Path(entry.get("path", ""))
                entry_type = _normalize_entry_type(entry.get("type"))

                if not _safe_exists(entry_path):
                    resolved = _resolve_directory_path(entry_path)
                    if resolved != entry_path and _safe_exists(resolved):
                        logger.warning(
                            "[PlaybackEditor] Using corrected media bank path for '%s': %s -> %s",
                            entry.get("name", "Unnamed"),
                            entry_path,
                            resolved,
                        )
                        entry_path = resolved

                if entry_type in ("images", "both"):
                    image_dirs.append(entry_path)
                if entry_type in ("videos", "both"):
                    video_dirs.append(entry_path)
                if entry_type == "fonts":
                    font_dirs.append(entry_path)

            image_files: list[Path] = []
            video_files: list[Path] = []
            font_files: list[str] = []

            # Use the shared recursive scanner (matches the cuelist runner behavior)
            for image_dir in image_dirs:
                try:
                    imgs, _vids = scan_media_directory(image_dir)
                    image_files.extend(Path(p) for p in imgs)
                except Exception as exc:
                    logger.warning("[PlaybackEditor] Failed to scan image bank %s: %s", image_dir, exc)

            for video_dir in video_dirs:
                try:
                    # Include .mov for the preview editor (legacy behavior).
                    _imgs, vids = scan_media_directory(
                        video_dir,
                        video_exts=(".mp4", ".webm", ".mkv", ".avi", ".mov"),
                    )
                    video_files.extend(Path(p) for p in vids)
                except Exception as exc:
                    logger.warning("[PlaybackEditor] Failed to scan video bank %s: %s", video_dir, exc)

            for font_dir in font_dirs:
                try:
                    font_files.extend(scan_font_directory(font_dir))
                except Exception as exc:
                    logger.warning("[PlaybackEditor] Failed to scan font bank %s: %s", font_dir, exc)

            # Sort deterministically
            image_files.sort(key=lambda p: str(p).lower())
            video_files.sort(key=lambda p: str(p).lower())

            # Emit results back to the UI thread safely.
            self.media_scan_completed.emit(
                scan_token,
                [str(p) for p in image_files],
                [str(p) for p in video_files],
                list(font_files),
            )

        try:
            t = threading.Thread(target=_scan_worker, daemon=True)
            self._media_scan_thread = t
            t.start()
        except Exception as exc:
            logger.error("[PlaybackEditor] Failed to start media scan thread: %s", exc)
            self.image_files = []
            self.video_files = []
            return

    def _apply_preview_font_from_bank(self):
        """Shuffle and apply a cached media-bank font to the preview text director."""
        if not PREVIEW_AVAILABLE or not self.text_director:
            return

        if (hasattr(self.text_director, "has_user_font_override")
                and self.text_director.has_user_font_override()):
            logger.info("[PlaybackEditor] Font override active; skipping media bank font preview")
            return

        if not self._pending_font_bank_fonts:
            return

        try:
            font_path = random.choice(self._pending_font_bank_fonts)
        except Exception:
            return

        if hasattr(self.text_director, "set_font_path"):
            self.text_director.set_font_path(font_path, user_set=False)
            try:
                display_name = Path(font_path).name
            except Exception:
                display_name = font_path
            logger.info(f"[PlaybackEditor] Preview font set to {display_name}")

    @contextmanager
    def _trace_operation(self, label: str):
        start_perf = time.perf_counter()
        # Record that this operation is currently executing so stall logs point here.
        self._trace_last_operation = f"{label} (in-progress)"
        self._trace_last_operation_duration_ms = None
        self._trace_last_operation_finished_ts = None
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_perf) * 1000.0
            self._trace_last_operation = label
            self._trace_last_operation_duration_ms = duration_ms
            self._trace_last_operation_finished_ts = time.time()

            if duration_ms >= self._trace_slow_threshold_ms:
                logger.warning(
                    "[PlaybackEditor] [CycleDebug] Operation '%s' exceeded %.0fms (took %.1fms)",
                    label,
                    self._trace_slow_threshold_ms,
                    duration_ms,
                )

    @contextmanager
    def _cycle_phase_timer(self, phase: str, timings: list):
        """Lightweight phase timing helper for CycleDebug instrumentation.

        The Playback Editor uses this from the preview timer handler. If the
        timings list is provided, we append (phase, duration_ms) tuples.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            try:
                duration_ms = (time.perf_counter() - start) * 1000.0
                if isinstance(timings, list):
                    timings.append((phase, duration_ms))
            except Exception:
                pass

    def _describe_last_operation(self) -> str:
        if not self._trace_last_operation:
            return "no recorded operation"

        duration_ms = self._trace_last_operation_duration_ms or 0.0
        finished_ts = self._trace_last_operation_finished_ts
        ago_ms = None
        if finished_ts is not None:
            ago_ms = (time.time() - finished_ts) * 1000.0

        if ago_ms is None:
            return f"{self._trace_last_operation} (duration {duration_ms:.1f}ms, finish time unknown)"

        return (
            f"{self._trace_last_operation} (duration {duration_ms:.1f}ms, "
            f"finished {ago_ms:.1f}ms ago)"
        )

    def _format_spiral_activity_state(self) -> str:
        now = time.time()

        def fmt_ms(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.1f}ms"

        begin_age_ms = None
        finish_age_ms = None
        if self._spiral_last_update_begin_ts is not None:
            begin_age_ms = (now - self._spiral_last_update_begin_ts) * 1000.0
        if self._spiral_last_update_finish_ts is not None:
            finish_age_ms = (now - self._spiral_last_update_finish_ts) * 1000.0

        duration_label = fmt_ms(self._spiral_last_update_duration_ms)
        dt_label = fmt_ms(self._spiral_last_update_dt_ms)

        fps_label = "n/a"
        if self._spiral_tick_rate_last_fps is not None:
            fps_label = f"{self._spiral_tick_rate_last_fps:.1f}fps"

        avg_dt_label = fmt_ms(self._spiral_tick_rate_last_avg_dt_ms)

        fps_age_label = "n/a"
        if self._spiral_tick_rate_last_report_ts is not None:
            fps_age_label = fmt_ms((now - self._spiral_tick_rate_last_report_ts) * 1000.0)

        return (
            "inflight={} last_begin_age={} last_finish_age={} last_duration={} "
            "last_dt={} last_fps={} last_fps_age={} last_avg_dt={}"
        ).format(
            self._spiral_update_inflight,
            fmt_ms(begin_age_ms),
            fmt_ms(finish_age_ms),
            duration_label,
            dt_label,
            fps_label,
            fps_age_label,
            avg_dt_label,
        )

    def _log_spiral_correlation(self, context_label: str, tick_delta_ms: float | None, interval_ms: float | None):
        spiral_state = self._format_spiral_activity_state()
        tick_label = "n/a" if tick_delta_ms is None else f"{tick_delta_ms:.1f}ms"
        interval_label = "n/a" if interval_ms is None else f"{interval_ms:.1f}ms"
        logger.warning(
            "[PlaybackEditor] [CycleDebug] Spiral correlation (%s): Δtick=%s interval=%s %s",
            context_label,
            tick_label,
            interval_label,
            spiral_state,
        )

    def _log_overdue_context(
        self,
        elapsed_since_tick_ms: float,
        elapsed_threshold_ms: float,
        reference_interval_ms: int,
        previous_interval_ms: int | None,
        interval_ms: int,
        speed: float,
        reason_label: str,
        pending_interval_before_ms: float | None,
        remaining_before_ms: float | None,
    ) -> None:
        """Log context when the preview media-cycle timer appears overdue.

        Diagnostic-only. Must never raise.
        """
        try:
            prev_label = "n/a" if previous_interval_ms is None else f"{previous_interval_ms}"
            pending_label = "n/a" if pending_interval_before_ms is None else f"{pending_interval_before_ms:.1f}"
            remaining_label = "n/a" if remaining_before_ms is None else f"{remaining_before_ms:.1f}"
            logger.warning(
                "[PlaybackEditor] [CycleDebug] Timer overdue (%s): elapsed=%.1fms threshold=%.1fms "
                "ref=%dms prev=%s new=%dms speed=%.1f pending=%sms remaining=%sms last_op=%s",
                reason_label,
                elapsed_since_tick_ms,
                elapsed_threshold_ms,
                reference_interval_ms,
                prev_label,
                interval_ms,
                speed,
                pending_label,
                remaining_label,
                self._describe_last_operation(),
            )
        except Exception:
            pass

    def _log_stack_snapshot(self, reason: str, max_frames: int = 20, frame=None):
        now = time.time()
        if (
            self._trace_last_stack_dump_ts is not None
            and (now - self._trace_last_stack_dump_ts) < self._trace_stack_dump_cooldown_s
        ):
            return

        if self._trace_stack_dump_inflight:
            return

        if frame is None:
            if threading.get_ident() == self._ui_thread_ident:
                try:
                    frame = sys._getframe()
                except Exception:
                    frame = None
            if frame is None:
                frame = self._get_ui_thread_frame()

        if frame is None:
            logger.warning(
                "[PlaybackEditor] [CycleDebug] Unable to capture stack for %s (frame unavailable)",
                reason,
            )
            self._trace_last_stack_dump_ts = now
            return

        self._trace_last_stack_dump_ts = now
        self._trace_stack_dump_inflight = True

        def _format_and_log_stack(frame_ref):
            try:
                stack_text = "".join(traceback.format_stack(frame_ref, limit=max_frames))
                logger.warning(
                    "[PlaybackEditor] [CycleDebug] UI thread stack snapshot (%s):\n%s",
                    reason,
                    stack_text,
                )
            except Exception as exc:
                logger.warning(
                    "[PlaybackEditor] [CycleDebug] Failed to format stack (%s): %s",
                    reason,
                    exc,
                )
            finally:
                self._trace_stack_dump_inflight = False

        threading.Thread(
            target=_format_and_log_stack,
            name="PlaybackStackDump",
            args=(frame,),
            daemon=True,
        ).start()

    def _record_expected_cycle_tick(self, interval_ms: Optional[int]):
        if not PREVIEW_AVAILABLE or interval_ms is None or interval_ms <= 0:
            self._cycle_debug_expected_fire_ts = None
            return
        self._cycle_debug_expected_fire_ts = time.time() + (interval_ms / 1000.0)

    def _get_ui_thread_frame(self):
        try:
            frames = sys._current_frames()
        except Exception:
            return None
        return frames.get(self._ui_thread_ident)

    def _schedule_cycle_watchdog(self, interval_ms: int):
        """Set a watchdog that captures the UI-thread stack if the next tick never arrives."""
        if interval_ms <= 0:
            self._cancel_cycle_watchdog()
            return

        timeout_s = max(0.25, (interval_ms / 1000.0) * self._cycle_watchdog_timeout_factor)
        token = object()
        timer = threading.Timer(
            timeout_s,
            self._on_cycle_watchdog_timeout,
            args=(interval_ms, timeout_s, token),
        )
        timer.daemon = True
        self._cancel_cycle_watchdog()
        self._cycle_watchdog_timer = timer
        self._cycle_watchdog_token = token
        timer.start()

    def _cancel_cycle_watchdog(self):
        timer = self._cycle_watchdog_timer
        if timer is not None:
            timer.cancel()
        self._cycle_watchdog_timer = None
        self._cycle_watchdog_token = None

    def _on_cycle_watchdog_timeout(self, interval_ms: int, timeout_s: float, token):
        if token is not self._cycle_watchdog_token:
            return

        self._cycle_watchdog_timer = None
        self._cycle_watchdog_token = None
        frame = self._get_ui_thread_frame()
        self._log_stack_snapshot(
            reason=(
                f"cycle_watchdog interval={interval_ms}ms timeout={timeout_s * 1000:.0f}ms"
            ),
            frame=frame,
        )
    
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
        self._maybe_schedule_preview_reload(reason="spiral_type")
    
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
        self._maybe_schedule_preview_reload(reason="spiral_opacity")
    
    def _set_rotation_speed_preview(self, slider_value: int) -> float:
        """Apply the rotation slider value to the preview and return RPM."""
        if not PREVIEW_AVAILABLE:
            return 0.0

        x_val = slider_value / 10.0
        reversed_flag = self.spiral_reverse_check.isChecked()
        rpm = self._compute_rpm(x_val, reversed_flag)

        self.rotation_speed_label.setText(f"{abs(x_val):.1f}x")
        self.rotation_speed_label.setToolTip(f"≈ {abs(rpm):.1f} RPM{' (reverse)' if reversed_flag else ''}")
        self.director.set_rotation_speed(rpm)
        return rpm

    def _on_rotation_speed_changed(self, value):
        """Handle rotation speed slider."""
        if not PREVIEW_AVAILABLE:
            return
        
        rpm = self._set_rotation_speed_preview(value)
        x_val = value / 10.0
        print(f"[PlaybackEditor SLIDER] value={value}, x_val={x_val:.1f}, rpm={rpm:.1f}", flush=True)
        self._mark_modified()
        self._capture_accelerate_start_values()
        
        logger.info(f"[PlaybackEditor] Rotation speed set: x={x_val:.1f} → rpm={rpm:.1f}")
        self._maybe_schedule_preview_reload(reason="rotation_speed", delay_ms=160)
    
    def _on_spiral_reverse_changed(self, state):
        """Handle spiral reverse checkbox."""
        logger.info(f"[PlaybackEditor] Spiral reverse changed: {state == 2}")
        self._on_rotation_speed_changed(self.rotation_speed_slider.value())
        self._mark_modified()
        self._maybe_schedule_preview_reload(reason="spiral_reverse")
    
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
            self._maybe_schedule_preview_reload(reason=f"spiral_color_{which}")

    def _pick_text_color(self):
        """Allow the user to override the text overlay color."""
        current = QColor.fromRgbF(*self.text_color)
        color = QColorDialog.getColor(current, self, "Pick Text Color")

        if color.isValid():
            self.text_color = (color.redF(), color.greenF(), color.blueF())
            self._apply_text_color_to_preview()
            self._mark_modified()
            self._maybe_schedule_preview_reload(reason="text_color")

    def _refresh_color_buttons(self):
        """Sync color button backgrounds with current RGB tuples."""
        if hasattr(self, "arm_color_btn"):
            arm_qcolor = QColor.fromRgbF(*self.arm_color)
            self.arm_color_btn.setStyleSheet(f"background-color: {arm_qcolor.name()};")
        if hasattr(self, "gap_color_btn"):
            gap_qcolor = QColor.fromRgbF(*self.gap_color)
            self.gap_color_btn.setStyleSheet(f"background-color: {gap_qcolor.name()};")
        self._refresh_text_color_button()

    def _refresh_text_color_button(self):
        """Update text color button styling to match stored color."""
        if hasattr(self, "text_color_btn"):
            text_qcolor = QColor.fromRgbF(*self.text_color)
            self.text_color_btn.setStyleSheet(f"background-color: {text_qcolor.name()};")

    def _apply_text_color_to_preview(self):
        """Push stored text color into the preview text director."""
        if PREVIEW_AVAILABLE and self.text_director:
            r, g, b = self.text_color
            try:
                self.text_director.set_text_color(r, g, b)
            except Exception as exc:
                logger.warning(f"[PlaybackEditor] Failed to set preview text color: {exc}")
        self._refresh_text_color_button()

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
        self._maybe_schedule_preview_reload(reason="media_mode")
    
    def _on_media_speed_changed(self, value):
        """Handle media speed slider."""
        speed_desc, interval_s = self._describe_cycle_speed(value)
        self.media_speed_label.setText(f"{value} ({speed_desc}) - {interval_s:.2f}s")
        
        if PREVIEW_AVAILABLE and not self._is_live_parity_preview_enabled():
            self._update_cycle_interval(reason="media_speed_slider")
        
        self._mark_modified()
        self._capture_accelerate_start_values()
        self._maybe_schedule_preview_reload(reason="media_speed", delay_ms=160)

    def _describe_cycle_speed(self, value: float) -> tuple[str, float]:
        """Return descriptor + seconds for a 1-100 cycle speed (matches media slider)."""
        import math
        value = max(1.0, min(100.0, float(value)))
        normalized = (value - 1.0) / 99.0
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
        self._maybe_schedule_preview_reload(reason="text_enabled")
    
    def _on_text_opacity_changed(self, value):
        """Handle text opacity slider."""
        opacity = value / 100.0
        self.text_opacity_label.setText(f"{value}%")
        
        if PREVIEW_AVAILABLE and self.compositor:
            self.compositor.set_text_opacity(opacity)
        
        self._mark_modified()
        self._maybe_schedule_preview_reload(reason="text_opacity")
    
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
        self._maybe_schedule_preview_reload(reason="text_mode")

    def _on_text_sync_changed(self, state):
        """Enable/disable manual text speed control and update director."""
        sync_enabled = state == Qt.CheckState.Checked
        if self.text_sync_check.isEnabled():
            self._preferred_text_sync = sync_enabled
        self._enforce_text_sync_policy()
        self._refresh_text_speed_label()
        self._apply_text_sync_settings()
        self._mark_modified()
        self._maybe_schedule_preview_reload(reason="text_sync")

    def _on_text_cycle_speed_changed(self, value):
        """Update manual text speed label + preview when slider moves."""
        self._refresh_text_speed_label(value)
        if self._is_carousel_mode() or not self.text_sync_check.isChecked():
            self._apply_text_sync_settings()
        self._mark_modified()
        self._maybe_schedule_preview_reload(reason="text_speed", delay_ms=180)

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
    
    def _apply_zoom_rate(
        self,
        rate: float,
        mark_modified: bool = True,
        store_manual: bool = True,
        reset_animation: bool = True
    ):
        """Push a zoom rate into the preview compositor."""
        if not PREVIEW_AVAILABLE:
            return

        self.zoom_rate_label.setText(f"{rate:.3f}")
        if store_manual:
            self.manual_zoom_rate = rate
        self.compositor._zoom_rate = rate
        if reset_animation:
            self.compositor._zoom_start_time = time.time()
            self.compositor._zoom_current = 1.0

        if mark_modified:
            self._mark_modified()

    def _on_zoom_rate_changed(self, value):
        """Handle zoom rate slider."""
        self._apply_zoom_rate(value / 100.0, mark_modified=True, reset_animation=False)
        self._capture_accelerate_start_values()
        self._maybe_schedule_preview_reload(reason="zoom_rate", delay_ms=160)

    def _on_zoom_mode_changed(self, _index: int) -> None:
        """Handle zoom mode changes.

        Zoom mode affects how CustomVisual restarts zoom animations in live playback,
        so the preview needs a config reload.
        """

        self._mark_modified()
        self._maybe_schedule_preview_reload(reason="zoom_mode")

    # === Accelerate Controls ===

    def _capture_accelerate_start_values(self):
        """Record the current slider-driven values used to seed accelerate ramps."""
        if hasattr(self, "rotation_speed_slider"):
            self._accelerate_rotation_start_x = self.rotation_speed_slider.value() / 10.0
        if hasattr(self, "media_speed_slider"):
            self._accelerate_media_start_speed = float(self.media_speed_slider.value())
        if hasattr(self, "zoom_rate_slider"):
            self._accelerate_zoom_start_rate = self.zoom_rate_slider.value() / 100.0

    def _resolve_accelerate_rotation_start(self) -> float:
        if self._accelerate_rotation_start_x is not None:
            return float(self._accelerate_rotation_start_x)
        if hasattr(self, "rotation_speed_slider"):
            return self.rotation_speed_slider.value() / 10.0
        return self.ACCEL_ROTATION_START_X

    def _resolve_accelerate_media_start(self) -> float:
        if self._accelerate_media_start_speed is not None:
            return float(self._accelerate_media_start_speed)
        if hasattr(self, "media_speed_slider"):
            return float(self.media_speed_slider.value())
        return self.ACCEL_MEDIA_START_SPEED

    def _resolve_accelerate_zoom_start(self) -> float:
        if self._accelerate_zoom_start_rate is not None:
            return float(self._accelerate_zoom_start_rate)
        if hasattr(self, "zoom_rate_slider"):
            return self.zoom_rate_slider.value() / 100.0
        return self.ACCEL_ZOOM_START_RATE

    def _on_accelerate_enabled_changed(self, state):
        """Enable/disable accelerate ramp controls."""
        enabled = state == Qt.CheckState.Checked
        self._accelerate_auto_enable_pending = False
        self._accelerate_auto_enable_scheduled = False
        self._cancel_accelerate_auto_enable_timer()
        if self._accelerate_hidden_disabled:
            self._set_accelerate_hidden_disabled(False)

        self._mark_modified()
        if not self._is_live_parity_preview_enabled():
            self._reset_accelerate_progress()

        if not enabled and self._accelerate_overriding:
            self._accelerate_overriding = False
            self._restore_base_dynamic_controls()
        self._update_accelerate_state_label()
        self._maybe_schedule_preview_reload(reason="accelerate_enabled")


    def _on_accelerate_duration_changed(self, value):
        """Update label + restart ramp when duration slider changes."""
        self._update_accelerate_duration_label(value)
        if self._is_accelerate_enabled() and not self._is_live_parity_preview_enabled():
            self._reset_accelerate_progress()
        self._mark_modified()
        self._maybe_schedule_preview_reload(reason="accelerate_duration", delay_ms=200)

    def _update_accelerate_duration_label(self, value):
        if hasattr(self, "accelerate_duration_label"):
            self.accelerate_duration_label.setText(f"{value:.0f}s")

    def _is_accelerate_enabled(self) -> bool:
        return hasattr(self, "accelerate_enable_check") and self.accelerate_enable_check.isChecked()

    def _is_accelerate_active(self) -> bool:
        return self._is_accelerate_enabled() and not self._accelerate_hidden_disabled

    def _set_accelerate_hidden_disabled(self, hidden: bool) -> None:
        if self._accelerate_hidden_disabled == hidden:
            return
        logger.info(f"[PlaybackEditor] _set_accelerate_hidden_disabled: {self._accelerate_hidden_disabled} -> {hidden}")
        self._accelerate_hidden_disabled = hidden
        if hidden:
            if self._accelerate_overriding:
                self._accelerate_overriding = False
                self._restore_base_dynamic_controls()
            self._update_accelerate_state_label()
            return
        if self._is_accelerate_enabled():
            # When releasing hidden-disabled, start accelerate timing and immediately trigger
            # the first interval update.
            logger.info("[PlaybackEditor] Releasing hidden-disabled flag, starting acceleration timer")
            self._accelerate_start_time = time.time()
            self._accelerate_progress = 0.0
            self._accelerate_overriding = False
            self._update_accelerate_state_label()
            # Don't force an immediate media swap here. Live playback doesn't
            # swap media just because accelerate re-syncs; it only changes timing.
            try:
                self._update_cycle_interval(reason="accelerate_release_hidden", restart_timer=True)
            except Exception:
                pass
        else:
            logger.info("[PlaybackEditor] Accelerate not enabled when releasing hidden-disabled")
            self._update_accelerate_state_label()

    def _update_accelerate_state_label(
        self, *, progress: float | None = None, rotation: float | None = None,
        media: float | None = None, zoom: float | None = None
    ) -> None:
        if not hasattr(self, "accelerate_state_label"):
            return
        if not self._is_accelerate_enabled():
            self.accelerate_state_label.setText("Disabled")
            return
        if self._accelerate_hidden_disabled:
            self.accelerate_state_label.setText("Synchronizing presets...")
            return
        if None not in (progress, rotation, media, zoom):
            self.accelerate_state_label.setText(
                f"{progress * 100:5.1f}% • rot {rotation:.1f}x • media {media:.0f} • zoom {zoom:.2f}"
            )
            return
        self.accelerate_state_label.setText("Ready")

    def _reset_accelerate_progress(self):
        """Reset accelerate timing window."""
        if not hasattr(self, "accelerate_enable_check"):
            return

        is_active = self._is_accelerate_active()
        logger.info(f"[PlaybackEditor] _reset_accelerate_progress called: is_active={is_active}")
        
        if is_active:
            self._accelerate_start_time = time.time()
            self._accelerate_progress = 0.0
            # Clear ramp bookkeeping so freshly loaded playbacks restart timers immediately
            self._accelerate_overriding = False
            self._accelerate_last_media_speed = None
            self._accelerate_media_speed_target = None
            self._accelerate_media_speed_smoothed = None
            self._accelerate_last_interval_update_ts = None

            # Don't force an immediate media swap. Restart the timer using the
            # accelerate start speed so timing matches live playback behavior.
            try:
                self._update_cycle_interval(
                    speed_override=self._resolve_accelerate_media_start(),
                    restart_timer=True,
                    reason="accelerate_reset",
                )
            except Exception:
                pass
        else:
            self._accelerate_start_time = None
            self._accelerate_progress = 0.0
            self._accelerate_overriding = False
            self._accelerate_last_media_speed = None
            self._accelerate_media_speed_target = None
            self._accelerate_media_speed_smoothed = None
            self._accelerate_last_interval_update_ts = None
        self._update_accelerate_state_label()

    def _schedule_accelerate_auto_enable(self):
        if not self._accelerate_auto_enable_pending or self._accelerate_auto_enable_scheduled:
            return
        self._accelerate_auto_enable_scheduled = True
        delay_ms = self.ACCEL_AUTO_ENABLE_DELAY_MS
        logger.info(
            "[PlaybackEditor] Scheduling accelerate auto-enable in %.1fs",
            delay_ms / 1000.0,
        )
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._auto_enable_accelerate_if_pending)
        timer.start(delay_ms)
        self._accelerate_auto_enable_timer = timer

    def _cancel_accelerate_auto_enable_timer(self):
        timer = self._accelerate_auto_enable_timer
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            pass
        timer.deleteLater()
        self._accelerate_auto_enable_timer = None
        self._accelerate_auto_enable_scheduled = False

    def _auto_enable_accelerate_if_pending(self):
        self._cancel_accelerate_auto_enable_timer()
        if not self._accelerate_auto_enable_pending:
            return
        self._accelerate_auto_enable_pending = False
        if not hasattr(self, "accelerate_enable_check"):
            return
        if not self._is_accelerate_enabled():
            logger.info("[PlaybackEditor] Auto-enabling accelerate preset after startup")
            self.accelerate_enable_check.setChecked(True)
            return
        if self._accelerate_hidden_disabled:
            logger.info("[PlaybackEditor] Releasing hidden accelerate disable after startup")
            self._set_accelerate_hidden_disabled(False)

    def _update_accelerate_effects(self):
        """Apply accelerate overrides each frame when enabled."""
        if not PREVIEW_AVAILABLE or not hasattr(self, "accelerate_enable_check"):
            return

        if not self._is_accelerate_active():
            # If hidden-disabled, keep current state (don't restore) - we're waiting for timers to stabilize
            if not self._accelerate_hidden_disabled:
                if self._accelerate_overriding:
                    self._accelerate_overriding = False
                    self._restore_base_dynamic_controls()
            self._update_accelerate_state_label()
            return

        if self._accelerate_start_time is None:
            self._accelerate_start_time = time.time()

        duration = max(0.1, float(self.accelerate_duration_slider.value()))
        elapsed = time.time() - self._accelerate_start_time
        progress = max(0.0, min(1.0, elapsed / duration))
        self._accelerate_progress = progress

        rotation_start = self._resolve_accelerate_rotation_start()
        media_start = self._resolve_accelerate_media_start()
        zoom_start = self._resolve_accelerate_zoom_start()

        rotation_target = max(rotation_start, self.ACCEL_ROTATION_END_X)
        media_target = max(media_start, self.ACCEL_MEDIA_END_SPEED)
        zoom_target = max(zoom_start, self.ACCEL_ZOOM_END_RATE)

        rotation_x = rotation_start + (rotation_target - rotation_start) * progress
        media_speed = media_start + (media_target - media_start) * progress
        zoom_rate = zoom_start + (zoom_target - zoom_start) * progress

        self._apply_accelerate_rotation(rotation_x)
        self._apply_accelerate_media_speed(media_speed)
        self._apply_accelerate_zoom_rate(zoom_rate)

        self._update_accelerate_state_label(
            progress=progress,
            rotation=rotation_x,
            media=media_speed,
            zoom=zoom_rate,
        )

        self._accelerate_overriding = True

    def _apply_accelerate_rotation(self, x_value: float):
        if not PREVIEW_AVAILABLE or not hasattr(self, "director"):
            return
        reversed_flag = self.spiral_reverse_check.isChecked()
        rpm = self._compute_rpm(x_value, reversed_flag)
        self.director.set_rotation_speed(rpm)

    def _apply_accelerate_media_speed(self, speed: float):
        if not PREVIEW_AVAILABLE or not hasattr(self, "image_cycle_timer") or self.image_cycle_timer is None:
            return

        self._accelerate_media_speed_target = speed

        if self._cycle_debug_overdue_restart_active:
            self._accelerate_overdue_throttled = True
            now = time.time()
            if (
                self._accelerate_overdue_throttle_last_log_ts is None
                or (now - self._accelerate_overdue_throttle_last_log_ts) >= 1.0
            ):
                self._accelerate_overdue_throttle_last_log_ts = now
                logger.info(
                    "[PlaybackEditor] [CycleDebug] Accelerate timer update deferred (overdue restart guard active)"
                )
            return

        smoothed_speed = self._accelerate_media_speed_smoothed
        max_delta_per_update = 1.0
        if smoothed_speed is None:
            smoothed_speed = speed
        else:
            delta = speed - smoothed_speed
            if abs(delta) > max_delta_per_update:
                smoothed_speed += max_delta_per_update if delta > 0 else -max_delta_per_update
            else:
                smoothed_speed = speed
        smoothed_speed = max(1.0, min(100.0, smoothed_speed))
        self._accelerate_media_speed_smoothed = smoothed_speed

        if (
            self._accelerate_last_media_speed is not None
            and abs(self._accelerate_last_media_speed - smoothed_speed) < 0.25
        ):
            return

        needs_restart = self._accelerate_last_media_speed is None
        self._accelerate_last_media_speed = smoothed_speed
        now = time.time()
        if (not needs_restart and self._accelerate_last_interval_update_ts is not None and
                (now - self._accelerate_last_interval_update_ts) < self.ACCEL_MEDIA_UPDATE_COOLDOWN):
            return

        self._accelerate_last_interval_update_ts = now
        self._update_cycle_interval(
            speed_override=smoothed_speed,
            restart_timer=needs_restart,
            reason="accelerate_override",
        )

    def _apply_accelerate_zoom_rate(self, rate: float):
        if not PREVIEW_AVAILABLE:
            return
        self._apply_zoom_rate(rate, mark_modified=False, store_manual=False, reset_animation=False)

    def _restore_base_dynamic_controls(self):
        """Return preview-controlled values to user sliders."""
        if not PREVIEW_AVAILABLE:
            return

        self._set_rotation_speed_preview(self.rotation_speed_slider.value())
        self._apply_zoom_rate(self.zoom_rate_slider.value() / 100.0, mark_modified=False)
        self._accelerate_last_media_speed = None
        self._accelerate_media_speed_target = None
        self._accelerate_media_speed_smoothed = None
        self._last_cycle_interval_ms = None
        self._accelerate_last_interval_update_ts = None
        self._update_cycle_interval(reason="restore_base_dynamic_controls")

        self._update_accelerate_state_label()
    
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
    
    def _update_cycle_interval(
        self,
        speed_override: float | None = None,
        restart_timer: bool = True,
        reason: str | None = None,
    ):
        """Update cycling timer interval based on speed setting (optionally overridden)."""
        if not PREVIEW_AVAILABLE or not hasattr(self, 'image_cycle_timer') or self.image_cycle_timer is None:
            return
        
        with self._trace_operation("update_cycle_interval"):
            reason_label = reason or "unspecified"
            if speed_override is None:
                speed = float(self.media_speed_slider.value())
            else:
                speed = float(speed_override)
            speed = max(1.0, min(100.0, speed))
            
            import math
            normalized = (speed - 1.0) / 99.0
            interval_ms = int(10000 * math.pow(0.005, normalized))

            previous_interval_ms = self._last_cycle_interval_ms
            needs_restart = previous_interval_ms != interval_ms
            shrinking_interval = (
                previous_interval_ms is not None
                and interval_ms < previous_interval_ms
            )
            self._last_cycle_interval_ms = interval_ms

            timer_active_before = self.image_cycle_timer.isActive()
            pending_interval_before_ms = None
            remaining_before_ms = None
            if timer_active_before:
                pending_interval_before_ms = self.image_cycle_timer.interval()
                remaining_before_ms = self.image_cycle_timer.remainingTime()
            self.image_cycle_timer.setInterval(interval_ms)

            elapsed_since_tick_ms = None
            if self._cycle_debug_last_tick is not None:
                elapsed_since_tick_ms = (time.time() - self._cycle_debug_last_tick) * 1000.0

            reference_interval_ms = interval_ms
            if previous_interval_ms is not None:
                reference_interval_ms = max(interval_ms, previous_interval_ms)
            elapsed_threshold_factor = 1.25
            if reason_label == "accelerate_override":
                elapsed_threshold_factor = 2.0
            elapsed_threshold_ms = reference_interval_ms * elapsed_threshold_factor

            effective_pending_ms = pending_interval_before_ms or reference_interval_ms
            shrink_extra_ms = 0.0
            if pending_interval_before_ms is not None:
                shrink_extra_ms = max(0.0, pending_interval_before_ms - interval_ms)
            requested_change_ms = 0.0
            if previous_interval_ms is not None:
                requested_change_ms = abs(previous_interval_ms - interval_ms)

            elapsed_threshold_ms = max(
                elapsed_threshold_ms,
                effective_pending_ms + shrink_extra_ms,
            )
            if requested_change_ms > 0.0:
                elapsed_threshold_ms = max(
                    elapsed_threshold_ms,
                    reference_interval_ms + requested_change_ms,
                )

            overdue_elapsed = False
            if timer_active_before and elapsed_since_tick_ms is not None:
                overdue_elapsed = elapsed_since_tick_ms >= elapsed_threshold_ms
                if overdue_elapsed:
                    if not self._cycle_debug_overdue_logged:
                        self._cycle_debug_overdue_logged = True
                        self._log_overdue_context(
                            elapsed_since_tick_ms,
                            elapsed_threshold_ms,
                            reference_interval_ms,
                            previous_interval_ms,
                            interval_ms,
                            speed,
                            reason_label,
                            pending_interval_before_ms,
                            remaining_before_ms,
                        )
                        self._log_spiral_correlation(
                            "timer_overdue",
                            elapsed_since_tick_ms,
                            interval_ms,
                        )
                else:
                    self._cycle_debug_overdue_logged = False
            else:
                self._cycle_debug_overdue_logged = False

            overdue_remaining = False
            if remaining_before_ms is not None:
                overdue_threshold = interval_ms * 2.5
                overdue_remaining = remaining_before_ms > overdue_threshold

            shrinking_but_waiting = (
                shrinking_interval
                and remaining_before_ms is not None
                and remaining_before_ms > interval_ms * 1.25
            )

            remaining_before_label = "n/a"
            if remaining_before_ms is not None:
                remaining_before_label = f"{remaining_before_ms:.1f}ms"

            elapsed_since_tick_label = "n/a"
            if elapsed_since_tick_ms is not None:
                elapsed_since_tick_label = f"{elapsed_since_tick_ms:.1f}ms"

            pending_interval_label = "n/a"
            if pending_interval_before_ms is not None:
                pending_interval_label = f"{pending_interval_before_ms:.1f}ms"
            elapsed_threshold_label = f"{elapsed_threshold_ms:.1f}ms"

            logger.info(
                "[PlaybackEditor] [CycleDebug] Interval request (%s): speed=%.1f interval=%dms active=%s remaining=%s restart_flag=%s",
                reason_label,
                speed,
                interval_ms,
                timer_active_before,
                remaining_before_label,
                restart_timer,
            )

            should_restart = False
            restart_trigger = None

            if not self.image_cycle_timer.isActive():
                should_restart = True
            elif overdue_elapsed or overdue_remaining:
                if overdue_remaining:
                    logger.debug(
                        "[PlaybackEditor] Restarting timer due to long pending timeout (remaining %.1fms > %.1fms)",
                        remaining_before_ms,
                        interval_ms * 2.5,
                    )
                should_restart = True
                if overdue_elapsed:
                    restart_trigger = "overdue_elapsed"
                else:
                    restart_trigger = "overdue_remaining"
            elif needs_restart:
                if restart_timer:
                    should_restart = True
                else:
                    if shrinking_but_waiting:
                        should_restart = True
                        logger.debug(
                            "[PlaybackEditor] Forcing restart because interval shrank (remaining %.1fms > target %.1fms)",
                            remaining_before_ms,
                            interval_ms * 1.25,
                        )
                    else:
                        logger.debug(
                            "[PlaybackEditor] Skipping timer restart (elapsed %.1fms < threshold %.1fms)",
                            elapsed_since_tick_ms,
                            interval_ms * 1.25,
                        )

            if reason_label == "accelerate_override":
                logger.info(
                    "[PlaybackEditor] [CycleDebug] Interval decision diagnostics: needs_restart=%s elapsed_since_tick=%s overdue_elapsed=%s overdue_remaining=%s remaining_before=%s pending_interval=%s elapsed_threshold=%s shrinking_but_waiting=%s should_restart=%s",
                    needs_restart,
                    elapsed_since_tick_label,
                    overdue_elapsed,
                    overdue_remaining,
                    remaining_before_label,
                    pending_interval_label,
                    elapsed_threshold_label,
                    shrinking_but_waiting,
                    should_restart,
                )

            if should_restart:
                self.image_cycle_timer.start(interval_ms)
                self._record_expected_cycle_tick(interval_ms)
                if restart_trigger:
                    self._record_overdue_restart(
                        restart_trigger,
                        elapsed_since_tick_ms,
                        interval_ms,
                        remaining_before_ms,
                    )
                logger.info(
                    "[PlaybackEditor] [CycleDebug] Timer %s (interval=%dms, overdue_elapsed=%s, overdue_remaining=%s, reason=%s)",
                    "restarted",
                    interval_ms,
                    overdue_elapsed,
                    overdue_remaining,
                    reason_label,
                )
            else:
                if self.image_cycle_timer.isActive():
                    self.image_cycle_timer.setInterval(interval_ms)
                    if interval_ms > 0:
                        base_time = self._cycle_debug_last_tick or time.time()
                        self._cycle_debug_expected_fire_ts = base_time + (interval_ms / 1000.0)
                    else:
                        self._cycle_debug_expected_fire_ts = None
                logger.info(
                    "[PlaybackEditor] [CycleDebug] Timer left running (interval=%dms, overdue_elapsed=%s, overdue_remaining=%s, reason=%s)",
                    interval_ms,
                    overdue_elapsed,
                    overdue_remaining,
                    reason_label,
                )
            logger.info(
                "[PlaybackEditor] Cycle interval updated: %dms (speed=%.1f, reason=%s)",
                interval_ms,
                speed,
                reason_label,
            )

            if self.image_cycle_timer.isActive():
                self._schedule_cycle_watchdog(interval_ms)
            else:
                self._cancel_cycle_watchdog()
    
    def _cycle_media(self):
        """Cycle to next media item."""
        try:
            logger.debug("[PlaybackEditor] _cycle_media called - CODE VERSION 2025-11-27")
            if not PREVIEW_AVAILABLE or not self.current_media_list:
                return
        except Exception:
            return

        handler_start_perf = time.perf_counter()
        handler_start_wall = None
        phase_timings = []
        with self._cycle_phase_timer("cancel_watchdog", phase_timings):
            with self._trace_operation("cycle_media_cancel_watchdog"):
                self._cancel_cycle_watchdog()

        with self._cycle_phase_timer("compute_tick_delta", phase_timings):
            with self._trace_operation("cycle_media_compute_tick_delta"):
                now = time.time()
                handler_start_wall = now
                tick_delta_ms = None
                if self._cycle_debug_last_tick is not None:
                    tick_delta_ms = (now - self._cycle_debug_last_tick) * 1000.0
                self._cycle_debug_last_tick = now
                interval_ms = self.image_cycle_timer.interval()

        if handler_start_wall is None:
            handler_start_wall = time.time()

        expected_fire_ts = self._cycle_debug_expected_fire_ts
        expected_fire_label = "unknown"
        handler_start_label = datetime.fromtimestamp(handler_start_wall).strftime("%H:%M:%S.%f")[:-3]
        fire_delta_label = "n/a"
        if expected_fire_ts is not None:
            expected_fire_label = datetime.fromtimestamp(expected_fire_ts).strftime("%H:%M:%S.%f")[:-3]
            fire_delta_ms = (handler_start_wall - expected_fire_ts) * 1000.0
            fire_delta_label = f"{fire_delta_ms:+.1f}ms"
        tick_delta_label = "first" if tick_delta_ms is None else f"{tick_delta_ms:.1f}ms"
        logger.info(
            "[PlaybackEditor] [CycleDebug] Timer handler BEGIN: expected=%s actual=%s delta=%s interval=%dms Δtick=%s",
            expected_fire_label,
            handler_start_label,
            fire_delta_label,
            interval_ms,
            tick_delta_label,
        )

        if self._cycle_debug_overdue_restart_active:
            self._cycle_debug_overdue_restart_active = False
            guard_log = "released"
            if self._accelerate_overdue_throttled:
                self._accelerate_overdue_throttled = False
                self._accelerate_overdue_throttle_last_log_ts = None
                guard_log = "release+accelerate_resume"
            logger.info(
                "[PlaybackEditor] [CycleDebug] Overdue restart guard %s at tick (Δtick=%s, interval=%sms)",
                guard_log,
                tick_delta_label,
                interval_ms,
            )

        stall_detected = (
            tick_delta_ms is not None
            and interval_ms > 0
            and tick_delta_ms >= interval_ms * 5
        )
        if stall_detected:
            with self._cycle_phase_timer("handle_stall", phase_timings):
                with self._trace_operation("cycle_media_handle_stall"):
                    logger.warning(
                        "[PlaybackEditor] [CycleDebug] Timer stall detected: Δtick=%.1fms (interval=%sms). Last op: %s",
                        tick_delta_ms,
                        interval_ms,
                        self._describe_last_operation(),
                    )
                    self._log_stack_snapshot("timer_stall")
                    self._log_spiral_correlation("timer_stall", tick_delta_ms, interval_ms)

        with self._cycle_phase_timer("select_next_media", phase_timings):
            with self._trace_operation("cycle_media_select_next"):
                next_index = (self.current_media_index + 1) % len(self.current_media_list)
                if tick_delta_ms is None:
                    logger.info(
                        "[PlaybackEditor] [CycleDebug] Timer tick → media index %s/%s (first tick, interval=%sms)",
                        next_index + 1,
                        len(self.current_media_list),
                        interval_ms
                    )
                else:
                    logger.info(
                        "[PlaybackEditor] [CycleDebug] Timer tick → media index %s/%s (Δtick=%.1fms, interval=%sms)",
                        next_index + 1,
                        len(self.current_media_list),
                        tick_delta_ms,
                        interval_ms
                    )

        self.current_media_index = next_index
        with self._cycle_phase_timer("load_next_media", phase_timings):
            self._load_next_media(from_cycle=True)

        with self._cycle_phase_timer("schedule_watchdog", phase_timings):
            with self._trace_operation("cycle_media_schedule_watchdog"):
                if hasattr(self, "image_cycle_timer") and self.image_cycle_timer is not None:
                    self._schedule_cycle_watchdog(self.image_cycle_timer.interval())
                    self._record_expected_cycle_tick(self.image_cycle_timer.interval())
                else:
                    self._record_expected_cycle_tick(None)

        handler_duration_ms = (time.perf_counter() - handler_start_perf) * 1000.0
        self._cycle_debug_last_handler_duration_ms = handler_duration_ms
        handler_end_label = datetime.fromtimestamp(time.time()).strftime("%H:%M:%S.%f")[:-3]
        next_expected_ts = self._cycle_debug_expected_fire_ts
        next_expected_label = "unknown"
        if next_expected_ts is not None:
            next_expected_label = datetime.fromtimestamp(next_expected_ts).strftime("%H:%M:%S.%f")[:-3]
        logger.info(
            "[PlaybackEditor] [CycleDebug] Timer handler END: duration=%.1fms next_expected=%s finished=%s stall=%s",
            handler_duration_ms,
            next_expected_label,
            handler_end_label,
            stall_detected,
        )
        phase_timings.append(("handler_total", handler_duration_ms))

        phase_report_reason = None
        if stall_detected:
            phase_report_reason = "stall"
        elif (
            self._accelerate_overriding
            and tick_delta_ms is not None
            and interval_ms > 0
            and tick_delta_ms >= interval_ms * 3
        ):
            phase_report_reason = "accelerate_delay"

        if phase_report_reason:
            self._log_cycle_phase_diagnostics(phase_timings, phase_report_reason, tick_delta_ms)
    
    def _record_overdue_restart(
        self,
        trigger: str,
        elapsed_since_tick_ms: float | None,
        interval_ms: int,
        remaining_before_ms: float | None,
    ):
        now = time.time()
        gap_label = "first"
        if self._cycle_debug_last_overdue_restart_ts is not None:
            gap_ms = (now - self._cycle_debug_last_overdue_restart_ts) * 1000.0
            gap_label = f"{gap_ms:.1f}ms"
        self._cycle_debug_last_overdue_restart_ts = now
        self._cycle_debug_overdue_restart_count += 1
        self._cycle_debug_overdue_restart_active = True

        elapsed_label = "n/a" if elapsed_since_tick_ms is None else f"{elapsed_since_tick_ms:.1f}ms"
        remaining_label = "n/a" if remaining_before_ms is None else f"{remaining_before_ms:.1f}ms"

        logger.warning(
            "[PlaybackEditor] [CycleDebug] Overdue restart #%d (%s): elapsed=%s interval=%dms remaining_before=%s since_last=%s",
            self._cycle_debug_overdue_restart_count,
            trigger,
            elapsed_label,
            interval_ms,
            remaining_label,
            gap_label,
        )

    def _load_next_media(self, *, from_cycle: bool = False):
        """Load the next media item (image or video) in cycle."""
        if not PREVIEW_AVAILABLE or not self.current_media_list:
            return
        
        with self._trace_operation("load_next_media"):
            media_load_start = time.perf_counter()
            try:
                media_file = self.current_media_list[self.current_media_index]

                now = time.time()
                since_tick_ms = None
                if self._cycle_debug_last_tick is not None:
                    since_tick_ms = (now - self._cycle_debug_last_tick) * 1000.0
                since_media_ms = None
                if self._cycle_debug_last_media is not None:
                    since_media_ms = (now - self._cycle_debug_last_media) * 1000.0

                if since_tick_ms is None:
                    timing_note = "Δtick=first"
                else:
                    timing_note = f"Δtick={since_tick_ms:.1f}ms"
                if since_media_ms is None:
                    timing_note = f"{timing_note}, Δmedia=first"
                else:
                    timing_note = f"{timing_note}, Δmedia={since_media_ms:.1f}ms"

                logger.info(
                    "[PlaybackEditor] [CycleDebug] Loading media %s/%s: %s (%s)",
                    self.current_media_index + 1,
                    len(self.current_media_list),
                    media_file.name,
                    timing_note
                )
                self._cycle_debug_last_media = now
                
                if media_file.suffix.lower() in ['.jpg', '.png', '.jpeg', '.jfif', '.bmp', '.gif', '.webp']:
                    self._stop_video()
                    self._load_image(media_file)
                else:
                    self._load_video(media_file)

                if from_cycle:
                    self._maybe_schedule_text_system_init()

                total_ms = (time.perf_counter() - media_load_start) * 1000.0
                logger.info(
                    "[PlaybackEditor] [CycleDebug] Media load total %.1fms (%s)",
                    total_ms,
                    media_file.name,
                )
            except Exception as e:
                logger.error(f"[PlaybackEditor] Failed to load media: {e}")
    
    def _load_image(self, image_file):
        """Load a specific image file."""
        if not PREVIEW_AVAILABLE:
            return
        
        with self._trace_operation("load_image"):
            try:
                overall_start = time.perf_counter()
                image_data = media.load_image_sync(image_file)
                if image_data is None:
                    logger.warning("[PlaybackEditor] Image decode returned None: %s", image_file.name)
                    return
                decode_ms = (time.perf_counter() - overall_start) * 1000.0
                
                self.compositor.makeCurrent()
                upload_start = time.perf_counter()
                texture_id = upload_image_to_gpu(image_data)
                upload_ms = (time.perf_counter() - upload_start) * 1000.0
                
                self.compositor.set_background_texture(
                    texture_id,
                    zoom=1.0,
                    image_width=image_data.width,
                    image_height=image_data.height
                )
                
                # Start zoom animation
                if self.zoom_mode_combo.currentIndex() == 0:
                    if hasattr(self.compositor, "set_zoom_animation_enabled"):
                        self.compositor.set_zoom_animation_enabled(True)
                    self.compositor.start_zoom_animation(
                        start_zoom=1.0,
                        duration_frames=9999,
                        mode="exponential",
                    )
                else:
                    if hasattr(self.compositor, "set_zoom_animation_enabled"):
                        self.compositor.set_zoom_animation_enabled(False)
                    if hasattr(self.compositor, "set_background_zoom"):
                        self.compositor.set_background_zoom(1.0)

                # Keep whatever zoom rate is currently active (manual slider value
                # or accelerate override) without resetting the zoom timeline.
                
                self.compositor.update()
                
                # Trigger text change
                if self.text_director:
                    self.text_director.on_media_change()
                
                total_ms = (time.perf_counter() - overall_start) * 1000.0
                logger.info(
                    "[PlaybackEditor] [CycleDebug] Image timings %s decode=%.1fms upload=%.1fms total=%.1fms",
                    image_file.name,
                    decode_ms,
                    upload_ms,
                    total_ms,
                )
                logger.info(f"[PlaybackEditor] Loaded image: {image_file.name}")
            except Exception as e:
                logger.error(f"[PlaybackEditor] Failed to load image: {e}")
    
    def _load_video(self, video_file):
        """Load and start playing a video file."""
        if not PREVIEW_AVAILABLE:
            return
        
        with self._trace_operation("load_video"):
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
                if self.zoom_mode_combo.currentIndex() == 0:
                    if hasattr(self.compositor, "set_zoom_animation_enabled"):
                        self.compositor.set_zoom_animation_enabled(True)
                    self.compositor.start_zoom_animation(
                        start_zoom=1.0,
                        duration_frames=9999,
                        mode="exponential",
                    )
                else:
                    if hasattr(self.compositor, "set_zoom_animation_enabled"):
                        self.compositor.set_zoom_animation_enabled(False)
                    if hasattr(self.compositor, "set_background_zoom"):
                        self.compositor.set_background_zoom(1.0)

                # Keep whatever zoom rate is currently active (manual slider value
                # or accelerate override) without resetting the zoom timeline.
                
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
        update_start_wall = time.time()
        update_start_perf = time.perf_counter()
        self._spiral_last_update_begin_ts = update_start_wall
        self._spiral_update_inflight = True

        try:
            # When live-parity preview is active, CustomVisual handles accelerate.
            if not self._is_live_parity_preview_enabled():
                self._update_accelerate_effects()

            # Track tick rate for debugging
            if not hasattr(self, '_spiral_tick_count'):
                self._spiral_tick_count = 0
                self._spiral_tick_rate_start = None
                self._spiral_tick_rate_count = 0
                self._spiral_last_time = None  # For delta-time measurement
            
            self._spiral_tick_count += 1
            
            # Measure actual delta-time instead of assuming 1/30.0
            current_time = time.time()
            if self._spiral_last_time is not None:
                dt = current_time - self._spiral_last_time
            else:
                dt = 1/30.0  # First frame fallback
            self._spiral_last_time = current_time
            self._spiral_last_update_dt_ms = dt * 1000.0
            
            # Log tick rate every 30 ticks
            if self._spiral_tick_count % 30 == 0:
                if self._spiral_tick_rate_start is None:
                    self._spiral_tick_rate_start = current_time
                    self._spiral_tick_rate_count = 0
                else:
                    self._spiral_tick_rate_count += 30
                    elapsed = current_time - self._spiral_tick_rate_start
                    actual_fps = self._spiral_tick_rate_count / elapsed if elapsed > 0 else 0
                    avg_dt_s = (1 / actual_fps) if actual_fps > 0 else 0.0
                    logger.info(f"[_update_spiral] Tick rate: {actual_fps:.1f} FPS (target: 30 FPS, avg dt: {avg_dt_s:.4f}s)")
                    self._spiral_tick_rate_last_fps = actual_fps
                    self._spiral_tick_rate_last_avg_dt_ms = avg_dt_s * 1000.0 if actual_fps > 0 else None
                    self._spiral_tick_rate_last_report_ts = current_time
            
            # Update spiral parameters using measured dt
            self.director.update(dt)
            
            # Cache uniforms to prevent compositor from calling update() again
            cached_uniforms = self.director.export_uniforms()
            self.compositor._uniforms_cache = cached_uniforms
            logger.debug(f"[_update_spiral] Set compositor._uniforms_cache (phase={cached_uniforms.get('phase', 'N/A')})")
            
            self.compositor.update_zoom_animation()
            self.compositor.update()
        finally:
            self._spiral_last_update_finish_ts = time.time()
            self._spiral_last_update_duration_ms = (time.perf_counter() - update_start_perf) * 1000.0
            self._spiral_update_inflight = False
    
    def _update_render(self):
        """Update text director and compositor rendering."""
        if not PREVIEW_AVAILABLE:
            return
        
        if self.text_director:
            self.text_director.update()
        
        self.compositor.update()
    
    # === Media Bank Methods ===
    
    def _load_media_bank_config(self):
        """Load Media Bank configuration from the active session when available."""
        if self.is_session_mode and self.session_data is not None:
            media_bank = self.session_data.get("media_bank", [])
            self._media_bank = list(media_bank)
            logger.info(
                f"[PlaybackEditor] Loaded {len(self._media_bank)} session media bank entries"
            )
            return

        # Standalone/file mode fallback
        config_path = PROJECT_ROOT / "media_bank.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._media_bank = json.load(f)
                logger.info(
                    f"[PlaybackEditor] Loaded {len(self._media_bank)} entries from media_bank.json"
                )
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
        with self._trace_operation("refresh_media_bank_list"):
            self.list_media_bank.clear()
            
            media_mode = self.media_mode_combo.currentIndex()

            def _normalize_entry_type(raw: object) -> str:
                value = str(raw or "").strip().lower()
                if value in ("images", "image", "img", "pics", "pictures", "photo", "photos"):
                    return "images"
                if value in ("videos", "video", "vid", "movie", "movies"):
                    return "videos"
                if value in ("fonts", "font", "typeface", "typefaces"):
                    return "fonts"
                if value in ("both", "all", "mixed"):
                    return "both"
                return "both"

            if not self._media_bank:
                self.lbl_bank_info.setText("No media banks defined")
                logger.warning("[PlaybackEditor] Media bank list is empty")
                return
            
            for idx, entry in enumerate(self._media_bank):
                entry_type = _normalize_entry_type(entry.get("type"))
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
                elif entry_type == "fonts":
                    icon = "🔤"
                else:
                    icon = "🌀"
                
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
        self._maybe_schedule_preview_reload(reason="bank_selection", delay_ms=220)
    
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
        self._suppress_preview_reload = True
        # CRITICAL: Stop existing media cycle timer to prevent speed carryover
        if hasattr(self, 'image_cycle_timer') and self.image_cycle_timer is not None:
            if self.image_cycle_timer.isActive():
                self.image_cycle_timer.stop()
                logger.debug("[PlaybackEditor] Stopped media cycle timer before loading new playback")
        self._reset_cycle_debug_state()
        
        # CRITICAL: Reset compositor zoom to prevent zoom rate carryover
        if PREVIEW_AVAILABLE and hasattr(self, 'compositor') and self.compositor:
            if hasattr(self.compositor, 'reset_zoom'):
                self.compositor.reset_zoom()
                logger.debug("[PlaybackEditor] Reset compositor zoom before loading new playback")
        
        try:
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
                # If filtering by media mode hid all selected indices, don't leave the user
                # with zero visible banks selected (which would scan nothing).
                any_checked = any(
                    self.list_media_bank.item(i).checkState() == Qt.CheckState.Checked
                    for i in range(self.list_media_bank.count())
                )
                if not any_checked and self.list_media_bank.count() > 0:
                    logger.warning(
                        "[PlaybackEditor] bank_selections did not match visible banks; selecting all visible banks"
                    )
                    for i in range(self.list_media_bank.count()):
                        self.list_media_bank.item(i).setCheckState(Qt.CheckState.Checked)
            # else: keep all checked (default from _refresh_media_bank_list)

            # Load text settings
            text_data = data.get("text", {})
            self.text_enabled_check.setChecked(text_data.get("enabled", True))
            self.text_opacity_slider.setValue(int(text_data.get("opacity", 0.8) * 100))

            text_mode = text_data.get("mode", "centered_sync")
            mode_map = {"centered_sync": 0, "subtext": 1}
            self.text_mode_combo.setCurrentIndex(mode_map.get(text_mode, 0))

            self.text_color = self._clamp_color_tuple(text_data.get("color"), (1.0, 1.0, 1.0))
            self._apply_text_color_to_preview()

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
            mode_map = {"exponential": 0, "none": 1}
            # Treat any legacy modes as exponential.
            self.zoom_mode_combo.setCurrentIndex(mode_map.get(zoom_mode, 0))

            saved_zoom_rate = float(zoom_data.get("rate", 0.2))
            self.zoom_rate_slider.setValue(int(saved_zoom_rate * 100))
            self._apply_zoom_rate(saved_zoom_rate, mark_modified=False)

            # Load accelerate settings
            accel_data = data.get("accelerate", {})
            accel_enabled = bool(accel_data.get("enabled", False))
            accel_duration = float(accel_data.get("duration", 30))
            accel_start_rotation = accel_data.get("start_rotation_x")
            accel_start_media = accel_data.get("start_media_speed")
            accel_start_zoom = accel_data.get("start_zoom_rate")

            try:
                self._accelerate_rotation_start_x = float(accel_start_rotation)
            except (TypeError, ValueError):
                self._accelerate_rotation_start_x = self.rotation_speed_slider.value() / 10.0

            try:
                self._accelerate_media_start_speed = float(accel_start_media)
            except (TypeError, ValueError):
                self._accelerate_media_start_speed = float(self.media_speed_slider.value())

            try:
                self._accelerate_zoom_start_rate = float(accel_start_zoom)
            except (TypeError, ValueError):
                self._accelerate_zoom_start_rate = self.zoom_rate_slider.value() / 100.0

            self._cancel_accelerate_auto_enable_timer()
            self._accelerate_auto_enable_pending = False
            self._accelerate_auto_enable_scheduled = False

            self.accelerate_enable_check.blockSignals(True)
            self.accelerate_enable_check.setChecked(accel_enabled)
            self.accelerate_enable_check.blockSignals(False)

            if accel_enabled:
                # Start acceleration immediately without any delay
                logger.info(f"[PlaybackEditor] Starting acceleration immediately for loaded playback")
                self._accelerate_hidden_disabled = False
                self._reset_accelerate_progress()
                # CRITICAL: Immediately update compositor effects to prevent visual snap
                # Without this, media cycles immediately but spiral/zoom don't update until next frame
                self._update_accelerate_effects()
                logger.info(f"[PlaybackEditor] Applied initial acceleration visual effects")
            else:
                self._accelerate_hidden_disabled = False
                self._update_accelerate_state_label()

            self.accelerate_duration_slider.blockSignals(True)
            duration_clamped = max(self.accelerate_duration_slider.minimum(), min(self.accelerate_duration_slider.maximum(), int(accel_duration)))
            self.accelerate_duration_slider.setValue(duration_clamped)
            self.accelerate_duration_slider.blockSignals(False)

            self._update_accelerate_duration_label(duration_clamped)

            # Reload media with new bank selections
            if PREVIEW_AVAILABLE:
                QTimer.singleShot(100, self._load_test_images)
            # NOTE: Don't call _reset_accelerate_progress() here - already called above for accel_enabled
            # Calling it again would reset the start time and cause delays
            self._capture_accelerate_start_values()
        finally:
            self._suppress_preview_reload = False
            self._maybe_schedule_preview_reload(reason="load_from_dict", delay_ms=50)
    
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
        
        from mesmerglass.platform_paths import ensure_dir, get_user_data_dir
        default_dir = ensure_dir(get_user_data_dir() / "playbacks")
        
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
            
            # Determine key and check if we need to rename
            old_key = self.playback_key
            new_key_suggestion = mode_name.replace(' ', '_').lower()
            
            if self.playback_key:
                # Editing existing playback
                # Check if name changed significantly enough to warrant key rename
                if new_key_suggestion != self.playback_key:
                    # Offer to rename key
                    reply = QMessageBox.question(
                        self,
                        "Rename Playback Key?",
                        f"The playback name has changed.\n\n"
                        f"Current key: {self.playback_key}\n"
                        f"Suggested key: {new_key_suggestion}\n\n"
                        f"Update the key? This will update all references in cuelists.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        # Ensure new key is unique
                        base_key = new_key_suggestion
                        counter = 1
                        while new_key_suggestion in self.session_data.get("playbacks", {}) and new_key_suggestion != self.playback_key:
                            new_key_suggestion = f"{base_key}_{counter}"
                            counter += 1
                        
                        # Update all references in cuelists
                        self._update_playback_references(old_key, new_key_suggestion)
                        
                        # Remove old key, use new key
                        if old_key in self.session_data.get("playbacks", {}):
                            del self.session_data["playbacks"][old_key]
                        key = new_key_suggestion
                        self.playback_key = new_key_suggestion  # Update for future saves
                    else:
                        # Keep old key
                        key = self.playback_key
                else:
                    # Key is fine, keep it
                    key = self.playback_key
            else:
                # New playback - generate key from name
                key = new_key_suggestion
                # Ensure uniqueness
                base_key = key
                counter = 1
                while key in self.session_data.get("playbacks", {}):
                    key = f"{base_key}_{counter}"
                    counter += 1
                self.playback_key = key  # Save for future reference
            
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
    
    def _update_playback_references(self, old_key: str, new_key: str):
        """Update all references to a playback key in cuelists and cues.
        
        Args:
            old_key: Old playback key
            new_key: New playback key
        """
        try:
            cuelists = self.session_data.get("cuelists", {})
            updated_count = 0
            
            for cuelist_key, cuelist_data in cuelists.items():
                cues = cuelist_data.get("cues", [])
                for cue in cues:
                    playback_pool = cue.get("playback_pool", [])
                    for entry in playback_pool:
                        if entry.get("playback") == old_key:
                            entry["playback"] = new_key
                            updated_count += 1
            
            if updated_count > 0:
                logger.info(f"[PlaybackEditor] Updated {updated_count} playback references from '{old_key}' to '{new_key}'")
        
        except Exception as e:
            logger.error(f"[PlaybackEditor] Failed to update playback references: {e}", exc_info=True)
    
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
            "Disabled": "none",
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
                "fade_duration": 0.0,
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
                "manual_cycle_speed": self.text_speed_slider.value(),
                "color": [round(c, 4) for c in self.text_color]
            },
            
            "zoom": {
                "mode": zoom_mode,
                "rate": self.zoom_rate_slider.value() / 100.0
            },

            "accelerate": {
                "enabled": self.accelerate_enable_check.isChecked(),
                "duration": self.accelerate_duration_slider.value(),
                "start_rotation_x": round(self._resolve_accelerate_rotation_start(), 4),
                "start_media_speed": round(self._resolve_accelerate_media_start(), 4),
                "start_zoom_rate": round(self._resolve_accelerate_zoom_start(), 4)
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
        if hasattr(self, 'render_timer') and getattr(self, 'render_timer', None) is not None:
            try:
                self.render_timer.stop()
            except Exception:
                pass
        if hasattr(self, 'image_cycle_timer'):
            if getattr(self, 'image_cycle_timer', None) is not None:
                try:
                    self.image_cycle_timer.stop()
                except Exception:
                    pass
        self._cancel_cycle_watchdog()
        
        self._stop_video()

        # Stop preview video streamer if active
        if getattr(self, "_preview_video_streamer", None) is not None:
            try:
                self._preview_video_streamer.stop()
            except Exception:
                pass
        
        event.accept()

