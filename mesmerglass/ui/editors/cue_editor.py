"""Cue Editor Window - Edit cue definitions within cuelists.

Features:
- Edit cue metadata (name, duration)
- Manage playback pool (add/remove playbacks, weights, cycles)
- Manage audio tracks
- Edit transitions (fade in/out)
- Selection mode configuration
"""
from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QSpinBox, QDoubleSpinBox, QComboBox,
    QGroupBox, QFormLayout, QDialogButtonBox, QMessageBox, QFileDialog,
    QTextEdit, QWidget, QScrollArea, QCheckBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QGuiApplication

from mesmerglass.engine.audio_utils import probe_audio_duration, normalize_volume
from mesmerglass.session.cue import AudioRole


class CueEditor(QDialog):
    """Editor window for cue definitions."""
    
    # Signal emitted when cue is saved (passes empty string for session mode, cue dict for legacy)
    saved = pyqtSignal()
    
    def __init__(self, cue_data: Optional[Dict[str, Any]] = None, session_data: Optional[dict] = None, 
                 cuelist_key: Optional[str] = None, cue_index: Optional[int] = None, parent=None):
        """
        Initialize CueEditor.
        
        Two modes:
        1. Legacy mode: cue_data provided, returns modified cue via signal
        2. Session mode: session_data + cuelist_key + cue_index provided, modifies session dict in-place
        
        Args:
            cue_data: Cue dictionary (legacy mode)
            session_data: Reference to session dict (session mode)
            cuelist_key: Key in session["cuelists"] (session mode)
            cue_index: Index in cuelist["cues"] (session mode, None = new cue)
            parent: Parent widget
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        
        # Mode determination
        self.session_data = session_data
        self.cuelist_key = cuelist_key
        self.cue_index = cue_index
        # Session mode means we can access session playbacks, even if not saving to session
        self.is_session_mode = session_data is not None
        
        self.cue_data = cue_data.copy() if cue_data else {}
        self.is_modified = False

        self._audio_state: Dict[AudioRole, Dict[str, Any]] = {}
        self._audio_widgets: Dict[AudioRole, Dict[str, Any]] = {}
        self._hypno_duration_suggestion: Optional[float] = None
        self._duration_manual_override = False
        self._updating_duration_spin = False
        self._reset_audio_state(preserve_widgets=False)

        self.setWindowTitle("Cue Editor")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(420, 480)
        
        self._setup_ui()
        self._apply_responsive_default_size()
        self._update_vibration_controls_state()
        
        # Load data based on mode
        if self.is_session_mode and self.cuelist_key and self.cue_index is not None:
            # Full session mode: Editing existing cue from session
            cuelist = self.session_data.get("cuelists", {}).get(self.cuelist_key)
            if cuelist and 0 <= self.cue_index < len(cuelist.get("cues", [])):
                self.cue_data = cuelist["cues"][self.cue_index].copy()
                self._update_ui_from_data()
            else:
                self.logger.warning(f"Cue index {self.cue_index} not found in cuelist '{self.cuelist_key}'")
                self._create_new()
        elif cue_data:
            # Legacy mode OR hybrid mode (cue_data + session for playback access): load from provided data
            self._update_ui_from_data()
        else:
            # New cue
            self._create_new()
    
    def _build_audio_role_section(self, parent_layout: QVBoxLayout, role: AudioRole, title: str, description: str) -> None:
        """Create UI controls for a specific audio role."""
        box = QGroupBox(title)
        form = QFormLayout(box)

        path_row = QHBoxLayout()
        path_edit = QLineEdit()
        path_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(partial(self._browse_audio_file, role))
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(partial(self._clear_audio_role, role))
        path_row.addWidget(path_edit, 1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(clear_btn)
        form.addRow("File:", path_row)

        volume_spin = QSpinBox()
        volume_spin.setRange(0, 100)
        volume_spin.setSuffix(" %")
        volume_spin.valueChanged.connect(partial(self._on_volume_changed, role))
        form.addRow("Volume:", volume_spin)

        info_label = QLabel("No file selected")
        info_label.setWordWrap(True)
        form.addRow("Info:", info_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #888888;")
            form.addRow(desc_label)

        parent_layout.addWidget(box)
        self._audio_widgets[role] = {
            "path_edit": path_edit,
            "volume_spin": volume_spin,
            "info_label": info_label,
        }

    def _reset_audio_state(self, *, preserve_widgets: bool = True):
        """Initialize per-role audio configuration defaults."""
        self._audio_state = {
            AudioRole.HYPNO: {
                "file": None,
                "volume": 0.85,
                "loop": False,
                "fade_in_ms": 1200,
                "fade_out_ms": 900,
                "duration": None,
            },
            AudioRole.BACKGROUND: {
                "file": None,
                "volume": 0.35,
                "loop": True,
                "fade_in_ms": 600,
                "fade_out_ms": 800,
                "duration": None,
            },
        }
        if not preserve_widgets:
            self._audio_widgets = {}
        self._hypno_duration_suggestion = None
        self._duration_manual_override = False

    def _setup_ui(self):
        """Build the editor UI."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # === BASIC INFO ===
        basic_group = QGroupBox("Cue Information")
        basic_layout = QFormLayout(basic_group)
        
        # Name
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._mark_modified)
        basic_layout.addRow("Name:", self.name_edit)
        
        # Duration
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 36000)  # 1 second to 10 hours
        self.duration_spin.setSuffix(" seconds")
        self.duration_spin.setValue(60)
        self.duration_spin.valueChanged.connect(self._on_duration_spin_changed)
        basic_layout.addRow("Duration:", self.duration_spin)

        self.duration_hint_label = QLabel("Suggested duration: --")
        self.duration_hint_label.setObjectName("durationHintLabel")
        self.duration_hint_label.setStyleSheet("color: #888888;")
        basic_layout.addRow("", self.duration_hint_label)
        
        # Selection Mode
        self.selection_mode_combo = QComboBox()
        self.selection_mode_combo.addItems(["on_cue_start", "on_media_cycle", "random_each_cycle"])
        self.selection_mode_combo.currentTextChanged.connect(self._mark_modified)
        basic_layout.addRow("Selection Mode:", self.selection_mode_combo)
        
        layout.addWidget(basic_group)
        
        # === PLAYBACK POOL ===
        playback_group = QGroupBox("Playback Pool")
        playback_layout = QVBoxLayout(playback_group)
        
        self.playback_list = QListWidget()
        self.playback_list.itemDoubleClicked.connect(self._edit_playback_entry)
        playback_layout.addWidget(self.playback_list, 1)
        
        # Playback buttons
        playback_buttons = QHBoxLayout()
        
        btn_add_playback = QPushButton("➕ Add Playback")
        btn_add_playback.clicked.connect(self._add_playback)
        playback_buttons.addWidget(btn_add_playback)
        
        btn_edit_playback = QPushButton("✏️ Edit")
        btn_edit_playback.clicked.connect(self._edit_selected_playback)
        playback_buttons.addWidget(btn_edit_playback)
        
        btn_remove_playback = QPushButton("➖ Remove")
        btn_remove_playback.clicked.connect(self._remove_playback)
        playback_buttons.addWidget(btn_remove_playback)
        
        playback_buttons.addStretch()
        
        playback_layout.addLayout(playback_buttons)
        
        layout.addWidget(playback_group, 1)
        
        # === AUDIO TRACKS ===
        audio_group = QGroupBox("Audio Layers")
        audio_layout = QVBoxLayout(audio_group)

        self._build_audio_role_section(
            audio_layout,
            AudioRole.HYPNO,
            "Hypno Track",
            "Main hypnosis track. Duration auto-suggests cue length."
        )
        self._build_audio_role_section(
            audio_layout,
            AudioRole.BACKGROUND,
            "Background Track",
            "Ambient loop that automatically repeats to cover the hypno track."
        )
        layout.addWidget(audio_group)

        # === TEXT MESSAGES ===
        text_group = QGroupBox("Custom Text Messages (optional)")
        text_layout = QVBoxLayout(text_group)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Enter custom text messages for this cue, one per line.\nLeave empty to use playback's default text.")
        self.text_edit.setMaximumHeight(100)
        self.text_edit.textChanged.connect(self._mark_modified)
        
        text_layout.addWidget(self.text_edit)
        layout.addWidget(text_group)
        
        # === VIBRATION CONTROLS ===
        vibration_group = QGroupBox("Device Vibration")
        vibration_layout = QVBoxLayout(vibration_group)
        
        # Checkbox
        self.vibrate_checkbox = QCheckBox("Vibrate on Text Cycle")
        self.vibrate_checkbox.stateChanged.connect(self._mark_modified)
        vibration_layout.addWidget(self.vibrate_checkbox)
        
        # Intensity slider
        intensity_container = QHBoxLayout()
        intensity_label_left = QLabel("Intensity:")
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(0, 100)
        self.intensity_slider.setValue(50)
        self.intensity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.intensity_slider.setTickInterval(10)
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        self.intensity_label = QLabel("50%")
        self.intensity_label.setMinimumWidth(40)
        intensity_container.addWidget(intensity_label_left)
        intensity_container.addWidget(self.intensity_slider, 1)
        intensity_container.addWidget(self.intensity_label)
        vibration_layout.addLayout(intensity_container)
        
        layout.addWidget(vibration_group)
        
        # === TRANSITIONS ===
        transitions_group = QGroupBox("Transitions")
        transitions_layout = QFormLayout(transitions_group)
        
        # Transition In
        self.transition_in_type = QComboBox()
        self.transition_in_type.addItems(["fade", "cut", "crossfade"])
        self.transition_in_type.currentTextChanged.connect(self._mark_modified)
        transitions_layout.addRow("Transition In Type:", self.transition_in_type)
        
        self.transition_in_duration = QSpinBox()
        self.transition_in_duration.setRange(0, 10000)
        self.transition_in_duration.setSuffix(" ms")
        self.transition_in_duration.setValue(2000)
        self.transition_in_duration.valueChanged.connect(self._mark_modified)
        transitions_layout.addRow("Transition In Duration:", self.transition_in_duration)
        
        # Transition Out
        self.transition_out_type = QComboBox()
        self.transition_out_type.addItems(["fade", "cut", "crossfade"])
        self.transition_out_type.currentTextChanged.connect(self._mark_modified)
        transitions_layout.addRow("Transition Out Type:", self.transition_out_type)
        
        self.transition_out_duration = QSpinBox()
        self.transition_out_duration.setRange(0, 10000)
        self.transition_out_duration.setSuffix(" ms")
        self.transition_out_duration.setValue(1500)
        self.transition_out_duration.valueChanged.connect(self._mark_modified)
        transitions_layout.addRow("Transition Out Duration:", self.transition_out_duration)
        
        layout.addWidget(transitions_group)
        
        # === DIALOG BUTTONS ===
        button_box = QDialogButtonBox()
        
        btn_save = button_box.addButton("💾 Save", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_save.clicked.connect(self._save)
        
        btn_cancel = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.clicked.connect(self._cancel)
        
        layout.addStretch()

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area, 1)
        outer_layout.addWidget(button_box, 0)

        self._button_box = button_box

    def _apply_responsive_default_size(self) -> None:
        """Resize the dialog based on the current screen so buttons stay visible."""
        preferred = self._calculate_preferred_size(self._current_screen_size())
        self.resize(preferred)

    def _current_screen_size(self) -> Optional[QSize]:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry().size()

    @staticmethod
    def _calculate_preferred_size(screen_size: Optional[QSize]) -> QSize:
        default = QSize(900, 720)
        if screen_size is None:
            return default

        margin_w = 80
        margin_h = 120
        width_limit = max(360, screen_size.width() - margin_w)
        height_limit = max(420, screen_size.height() - margin_h)

        width = min(default.width(), width_limit)
        height = min(default.height(), height_limit)

        if screen_size.width() > 100:
            width = min(width, max(240, screen_size.width() - 12))
        if screen_size.height() > 100:
            height = min(height, max(300, screen_size.height() - 12))

        return QSize(int(width), int(height))
    
    def _create_new(self):
        """Create a new empty cue."""
        self._reset_audio_state()
        self.cue_data = {
            "name": "New Cue",
            "duration_seconds": 60,
            "playback_pool": [],
            "selection_mode": "on_cue_start",
            "transition_in": {
                "type": "fade",
                "duration_ms": 2000
            },
            "transition_out": {
                "type": "fade",
                "duration_ms": 1500
            },
            "audio_tracks": []
        }
        self._update_ui_from_data()
        self.setWindowTitle("Cue Editor - New Cue")
    
    def _update_ui_from_data(self):
        """Update UI widgets from cue_data."""
        # Basic info
        self.name_edit.blockSignals(True)
        self.name_edit.setText(self.cue_data.get("name", ""))
        self.name_edit.blockSignals(False)

        duration_value = self.cue_data.get("duration_seconds", 60)
        self._updating_duration_spin = True
        self.duration_spin.setValue(duration_value)
        self._updating_duration_spin = False
        self._duration_manual_override = False

        selection_mode = self.cue_data.get("selection_mode", "on_cue_start")
        index = self.selection_mode_combo.findText(selection_mode)
        self.selection_mode_combo.blockSignals(True)
        if index >= 0:
            self.selection_mode_combo.setCurrentIndex(index)
        else:
            self.selection_mode_combo.setCurrentIndex(0)
        self.selection_mode_combo.blockSignals(False)
        
        # Vibration settings
        self.vibrate_checkbox.blockSignals(True)
        self.vibrate_checkbox.setChecked(self.cue_data.get("vibrate_on_text_cycle", False))
        self.vibrate_checkbox.blockSignals(False)
        
        intensity = self.cue_data.get("vibration_intensity", 0.5)
        self.intensity_slider.blockSignals(True)
        self.intensity_slider.setValue(int(intensity * 100))
        self.intensity_label.setText(f"{int(intensity * 100)}%")
        self.intensity_slider.blockSignals(False)
        
        # Update enabled state
        self._update_vibration_controls_state()

        # Playback pool
        self.playback_list.clear()
        for entry in self.cue_data.get("playback_pool", []) or []:
            item = QListWidgetItem(self._format_playback_entry_label(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.playback_list.addItem(item)
        
        # Text messages
        self.text_edit.blockSignals(True)
        text_messages = self.cue_data.get("text_messages", [])
        if text_messages:
            self.text_edit.setPlainText('\n'.join(text_messages))
        else:
            self.text_edit.clear()
        self.text_edit.blockSignals(False)
        
        # Transitions
        transition_in = self.cue_data.get("transition_in", {})
        self.transition_in_type.blockSignals(True)
        self.transition_in_type.setCurrentText(transition_in.get("type", "fade"))
        self.transition_in_type.blockSignals(False)
        self.transition_in_duration.blockSignals(True)
        self.transition_in_duration.setValue(transition_in.get("duration_ms", 2000))
        self.transition_in_duration.blockSignals(False)
        
        transition_out = self.cue_data.get("transition_out", {})
        self.transition_out_type.blockSignals(True)
        self.transition_out_type.setCurrentText(transition_out.get("type", "fade"))
        self.transition_out_type.blockSignals(False)
        self.transition_out_duration.blockSignals(True)
        self.transition_out_duration.setValue(transition_out.get("duration_ms", 1500))
        self.transition_out_duration.blockSignals(False)

        self._hydrate_audio_state_from_data()
        self._refresh_audio_fields()
        hypno_state = self._audio_state.get(AudioRole.HYPNO)
        suggestion = hypno_state.get("duration") if hypno_state else None
        if suggestion:
            self._apply_hypno_duration_suggestion(suggestion, force=True)
        else:
            self._apply_hypno_duration_suggestion(None, force=True)
        # Remove legacy video audio fields so they do not persist when editing
        self.cue_data.pop("video_audio", None)
        self.cue_data.pop("enable_video_audio", None)
        self.cue_data.pop("video_audio_volume", None)
    
    def _hydrate_audio_state_from_data(self) -> None:
        """Load audio configuration from cue_data into UI state."""
        raw_tracks: list[Dict[str, Any]] = []
        audio_block = self.cue_data.get("audio")
        if isinstance(audio_block, dict):
            hypno_block = audio_block.get("hypno")
            if isinstance(hypno_block, dict):
                temp = hypno_block.copy()
                temp.setdefault("role", AudioRole.HYPNO.value)
                raw_tracks.append(temp)
            background_block = audio_block.get("background")
            if isinstance(background_block, dict):
                temp = background_block.copy()
                temp.setdefault("role", AudioRole.BACKGROUND.value)
                raw_tracks.append(temp)

        if not raw_tracks:
            raw_tracks = self.cue_data.get("audio_tracks", []) or []

        self._reset_audio_state()
        for idx, track_data in enumerate(raw_tracks):
            role_value = track_data.get("role")
            role = None
            if isinstance(role_value, str):
                try:
                    role = AudioRole(role_value)
                except ValueError:
                    role = None
            if role is None:
                role = AudioRole.HYPNO if idx == 0 else AudioRole.BACKGROUND

            state = self._audio_state.get(role)
            if not state:
                continue

            state["file"] = track_data.get("file")
            state["volume"] = normalize_volume(track_data.get("volume", state["volume"]))
            state["loop"] = track_data.get("loop", state["loop"])
            state["fade_in_ms"] = track_data.get("fade_in_ms", state["fade_in_ms"])
            state["fade_out_ms"] = track_data.get("fade_out_ms", state["fade_out_ms"])
            state["duration"] = track_data.get("duration")

    def _refresh_audio_fields(self) -> None:
        """Apply audio state to widgets and update suggestions."""
        for role, widgets in self._audio_widgets.items():
            state = self._audio_state.get(role, {})
            path = state.get("file") or ""
            widgets["path_edit"].setText(path)

            volume_spin = widgets["volume_spin"]
            volume_spin.blockSignals(True)
            volume_spin.setValue(int(round(state.get("volume", 0.0) * 100)))
            volume_spin.blockSignals(False)

            info_label = widgets["info_label"]
            if path:
                duration = state.get("duration")
                if duration is None:
                    duration = probe_audio_duration(path)
                    state["duration"] = duration
                info_parts = [Path(path).name]
                if duration:
                    info_parts.append(f"{duration:.1f}s")
                if role == AudioRole.BACKGROUND:
                    info_parts.append("loops")
                info_label.setText(" · ".join(info_parts))
            else:
                info_label.setText("No file selected")

        self._update_duration_suggestion_from_state(force=False)

    def _update_duration_suggestion_from_state(self, force: bool) -> None:
        hypno_state = self._audio_state.get(AudioRole.HYPNO)
        duration = None
        if hypno_state and hypno_state.get("file"):
            duration = hypno_state.get("duration")
            if duration is None:
                duration = probe_audio_duration(hypno_state["file"])
                hypno_state["duration"] = duration
            if duration and not force:
                current = self.duration_spin.value()
                self._duration_manual_override = abs(current - duration) > 0.5
        else:
            self._duration_manual_override = False
        self._apply_hypno_duration_suggestion(duration, force=force)

    def _apply_hypno_duration_suggestion(self, duration: Optional[float], force: bool) -> None:
        self._hypno_duration_suggestion = duration
        if duration and (force or not self._duration_manual_override):
            self._updating_duration_spin = True
            self.duration_spin.setValue(max(1, int(round(duration))))
            self._updating_duration_spin = False
            self._duration_manual_override = False
        if not duration and force:
            # No duration available; reset override flag so next detection can update
            self._duration_manual_override = False
        self._refresh_duration_hint_label()

    def _refresh_duration_hint_label(self) -> None:
        if not self._hypno_duration_suggestion:
            self.duration_hint_label.setText("Suggested duration: --")
            return
        text = f"Suggested duration: {self._hypno_duration_suggestion:.1f}s"
        if self._duration_manual_override:
            text += " (manual override)"
        self.duration_hint_label.setText(text)

    def _browse_audio_file(self, role: AudioRole) -> None:
        caption = "Select Hypno Track" if role == AudioRole.HYPNO else "Select Background Track"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            caption,
            str(Path.cwd()),
            "Audio Files (*.mp3 *.wav *.ogg *.flac);;All Files (*.*)"
        )
        if not file_path:
            return

        state = self._audio_state.get(role)
        if not state:
            return

        state["file"] = file_path
        state["duration"] = probe_audio_duration(file_path)
        self._mark_modified()

        if role == AudioRole.HYPNO:
            self._duration_manual_override = False
            self._apply_hypno_duration_suggestion(state["duration"], force=True)
        self._refresh_audio_fields()

    def _clear_audio_role(self, role: AudioRole) -> None:
        state = self._audio_state.get(role)
        if not state or not state.get("file"):
            return
        state["file"] = None
        state["duration"] = None
        self._mark_modified()
        if role == AudioRole.HYPNO:
            self._apply_hypno_duration_suggestion(None, force=True)
        self._refresh_audio_fields()

    def _on_volume_changed(self, role: AudioRole, value: int) -> None:
        state = self._audio_state.get(role)
        if not state:
            return
        state["volume"] = normalize_volume(value / 100.0)
        self._mark_modified()

    def _on_duration_spin_changed(self, _value: int) -> None:
        if self._updating_duration_spin:
            return
        self._duration_manual_override = True
        self._refresh_duration_hint_label()
        self._mark_modified()
    
    def _on_intensity_changed(self, value: int) -> None:
        """Update intensity label when slider changes."""
        self.intensity_label.setText(f"{value}%")
        self._mark_modified()

    def _update_vibration_controls_state(self) -> None:
        """Enable/disable vibration controls based on device connection status."""
        # Check if any devices are connected via MesmerIntifaceServer
        has_connected_devices = False
        
        try:
            # Try to get the server from the parent window chain
            server = None
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, 'mesmer_intiface_server'):
                    server = parent.mesmer_intiface_server
                    break
                parent = parent.parent() if hasattr(parent, 'parent') else None
            
            if server:
                self.logger.debug(f"[vibration] Found MesmerIntifaceServer instance")
                
                # Check if any devices are connected in _bluetooth_devices dict
                if hasattr(server, '_bluetooth_devices'):
                    self.logger.debug(f"[vibration] Found _bluetooth_devices with {len(server._bluetooth_devices)} entries")
                    for addr, device_info in server._bluetooth_devices.items():
                        if hasattr(device_info, 'is_connected') and device_info.is_connected:
                            has_connected_devices = True
                            self.logger.debug(f"[vibration] Found connected device: {addr}")
                            break
                
                # Also check _device_protocols dict as backup
                if not has_connected_devices and hasattr(server, '_device_protocols'):
                    protocol_count = len(server._device_protocols)
                    self.logger.debug(f"[vibration] Found _device_protocols with {protocol_count} entries")
                    has_connected_devices = protocol_count > 0
            else:
                self.logger.debug(f"[vibration] No MesmerIntifaceServer found in parent chain")
        except Exception as e:
            self.logger.debug(f"Could not check device status: {e}", exc_info=True)
        
        self.logger.info(f"[vibration] Setting controls enabled={has_connected_devices}")
        
        # Enable/disable vibration controls
        self.vibrate_checkbox.setEnabled(has_connected_devices)
        self.intensity_slider.setEnabled(has_connected_devices)
        self.intensity_label.setEnabled(has_connected_devices)
        
        if not has_connected_devices:
            # Grey out with tooltip
            self.vibrate_checkbox.setToolTip("No devices connected. Connect devices in the Devices tab.")
            self.intensity_slider.setToolTip("No devices connected. Connect devices in the Devices tab.")
        else:
            self.vibrate_checkbox.setToolTip("")
            self.intensity_slider.setToolTip("")

    def _update_data_from_ui(self):
        """Update cue_data from UI widgets."""
        self.cue_data["name"] = self.name_edit.text()
        self.cue_data["duration_seconds"] = self.duration_spin.value()
        self.cue_data["selection_mode"] = self.selection_mode_combo.currentText()
        
        # Vibration settings
        self.cue_data["vibrate_on_text_cycle"] = self.vibrate_checkbox.isChecked()
        self.cue_data["vibration_intensity"] = self.intensity_slider.value() / 100.0
        
        # Playback pool
        playback_pool = []
        for i in range(self.playback_list.count()):
            item = self.playback_list.item(i)
            entry = item.data(Qt.ItemDataRole.UserRole)
            if entry:
                playback_pool.append(entry)
        self.cue_data["playback_pool"] = playback_pool
        
        # Audio tracks
        audio_tracks = []
        audio_block: Dict[str, Any] = {}
        for role in (AudioRole.HYPNO, AudioRole.BACKGROUND):
            state = self._audio_state.get(role)
            if not state or not state.get("file"):
                continue
            track_dict = {
                "file": state["file"],
                "volume": round(state.get("volume", 0.0), 4),
                "loop": bool(state.get("loop", False)),
                "fade_in_ms": state.get("fade_in_ms", 500),
                "fade_out_ms": state.get("fade_out_ms", 500),
                "role": role.value,
            }
            if state.get("duration"):
                track_dict["duration"] = state["duration"]
            audio_tracks.append(track_dict)
            key = "hypno" if role == AudioRole.HYPNO else "background"
            audio_block[key] = track_dict

        if audio_tracks:
            self.cue_data["audio_tracks"] = audio_tracks
            self.cue_data["audio"] = audio_block
        else:
            self.cue_data.pop("audio_tracks", None)
            self.cue_data.pop("audio", None)

        self.cue_data.pop("video_audio", None)
        self.cue_data.pop("enable_video_audio", None)
        self.cue_data.pop("video_audio_volume", None)
        
        # Text messages
        text_content = self.text_edit.toPlainText().strip()
        if text_content:
            self.cue_data["text_messages"] = [line.strip() for line in text_content.split('\n') if line.strip()]
        elif "text_messages" in self.cue_data:
            del self.cue_data["text_messages"]
        
        # Transitions
        self.cue_data["transition_in"] = {
            "type": self.transition_in_type.currentText(),
            "duration_ms": self.transition_in_duration.value()
        }
        self.cue_data["transition_out"] = {
            "type": self.transition_out_type.currentText(),
            "duration_ms": self.transition_out_duration.value()
        }
    
    def _mark_modified(self):
        """Mark the cue as modified."""
        if not self.is_modified:
            self.is_modified = True
            title = self.windowTitle()
            if not title.endswith(" *"):
                self.setWindowTitle(title + " *")

    def _format_playback_entry_label(self, entry: Dict[str, Any]) -> str:
        """Return a human-friendly label for a playback entry."""
        playback_path = entry.get("playback", "")
        weight = entry.get("weight", 1.0)
        min_duration = entry.get("min_duration_s")
        max_duration = entry.get("max_duration_s")
        min_from_cycles = False
        max_from_cycles = False
        if min_duration is None:
            min_duration = entry.get("min_cycles")
            min_from_cycles = min_duration is not None
        if max_duration is None:
            max_duration = entry.get("max_cycles")
            max_from_cycles = max_duration is not None

        def _coerce_duration(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        min_duration = _coerce_duration(min_duration)
        max_duration = _coerce_duration(max_duration)

        # Legacy entries using cycles map 1 cycle ~= 10s (historic heuristic)
        if min_from_cycles and min_duration is not None:
            min_duration *= 10.0
        if max_from_cycles and max_duration is not None:
            max_duration *= 10.0

        if self.is_session_mode:
            # Look up actual name from session playbacks
            if playback_path and self.session_data:
                playback_data = self.session_data.get("playbacks", {}).get(playback_path)
                if playback_data:
                    display_name = playback_data.get("name", playback_path)
                else:
                    display_name = playback_path or "<missing playback>"
            else:
                display_name = playback_path or "<missing playback>"
        else:
            display_name = Path(playback_path).name if playback_path else "<missing playback>"

        duration_text = ""
        if min_duration or max_duration:
            min_text = f"{min_duration:.0f}" if min_duration else "?"
            max_text = f"{max_duration:.0f}" if max_duration else "?"
            duration_text = f" (duration: {min_text}-{max_text}s)"

        return f"{display_name} [weight: {weight}]{duration_text}"
    
    def _add_playback(self):
        """Add a playback to the pool."""
        if self.is_session_mode:
            # Session mode: show dialog with available playbacks from session
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox, QLabel
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Select Playback from Session")
            layout = QVBoxLayout(dialog)
            
            label = QLabel("Select a playback from the current session:")
            layout.addWidget(label)
            
            # List available playbacks
            playback_list_widget = QListWidget()
            available_playbacks = self.session_data.get("playbacks", {})
            
            if not available_playbacks:
                QMessageBox.warning(self, "No Playbacks", "No playbacks available in current session.\nPlease add playbacks first via the Playbacks tab.")
                return
            
            for key in sorted(available_playbacks.keys()):
                # Show name from JSON, not key
                playback_data = available_playbacks[key]
                display_name = playback_data.get("name", key)
                item = QListWidgetItem(display_name)
                item.setData(Qt.ItemDataRole.UserRole, key)  # Store key as data
                playback_list_widget.addItem(item)
            
            layout.addWidget(playback_list_widget)
            
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            if dialog.exec() == QDialog.DialogCode.Accepted and playback_list_widget.currentItem():
                # Get key from item data (not text, which is the display name)
                playback_key = playback_list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
                
                # Create playback entry (use key for session mode)
                entry = {
                    "playback": playback_key,
                    "weight": 1.0
                }
                
                # Add to list
                item_text = self._format_playback_entry_label(entry)
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.playback_list.addItem(item)
                
                self._mark_modified()
                self.logger.info(f"Added playback from session: {playback_key}")
        else:
            # Legacy file mode: pick playback file
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Playback",
                "mesmerglass/playbacks",
                "Playback Files (*.json);;All Files (*.*)"
            )
            
            if file_path:
                # Create playback entry
                entry = {
                    "playback": file_path,
                    "weight": 1.0
                }
                
                # Add to list
                item_text = self._format_playback_entry_label(entry)
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.playback_list.addItem(item)
                
                self._mark_modified()
                self.logger.info(f"Added playback: {file_path}")
    
    def _edit_playback_entry(self, item: QListWidgetItem):
        """Edit a playback entry (weight, cycles)."""
        entry = item.data(Qt.ItemDataRole.UserRole)
        
        # Create simple dialog for editing
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Playback Entry")
        layout = QVBoxLayout(dialog)
        
        form = QFormLayout()
        
        # Weight
        weight_spin = QDoubleSpinBox()
        weight_spin.setRange(0.1, 10.0)
        weight_spin.setSingleStep(0.1)
        weight_spin.setValue(entry.get("weight", 1.0))
        form.addRow("Weight:", weight_spin)
        
        # Min Duration (seconds)
        min_duration_spin = QDoubleSpinBox()
        min_duration_spin.setRange(0, 300.0)
        min_duration_spin.setSingleStep(1.0)
        min_duration_spin.setSuffix(" s")
        min_duration_spin.setSpecialValueText("Not set")
        min_duration_spin.setValue(entry.get("min_duration_s", entry.get("min_cycles", 0) * 10.0 if entry.get("min_cycles") else 0))
        form.addRow("Min Duration:", min_duration_spin)
        
        # Max Duration (seconds)
        max_duration_spin = QDoubleSpinBox()
        max_duration_spin.setRange(0, 300.0)
        max_duration_spin.setSingleStep(1.0)
        max_duration_spin.setSuffix(" s")
        max_duration_spin.setSpecialValueText("Not set")
        max_duration_spin.setValue(entry.get("max_duration_s", entry.get("max_cycles", 0) * 10.0 if entry.get("max_cycles") else 0))
        form.addRow("Max Duration:", max_duration_spin)
        
        layout.addLayout(form)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update entry
            entry["weight"] = weight_spin.value()
            
            min_val = min_duration_spin.value()
            max_val = max_duration_spin.value()
            
            # Remove old cycle fields
            if "min_cycles" in entry:
                del entry["min_cycles"]
            if "max_cycles" in entry:
                del entry["max_cycles"]
            
            # Save new duration fields
            if min_val > 0:
                entry["min_duration_s"] = min_val
            elif "min_duration_s" in entry:
                del entry["min_duration_s"]
            
            if max_val > 0:
                entry["max_duration_s"] = max_val
            elif "max_duration_s" in entry:
                del entry["max_duration_s"]
            
            # Update item text
            item.setText(self._format_playback_entry_label(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            
            self._mark_modified()
    
    def _edit_selected_playback(self):
        """Edit the currently selected playback."""
        current_item = self.playback_list.currentItem()
        if current_item:
            self._edit_playback_entry(current_item)
        else:
            QMessageBox.warning(self, "No Selection", "Please select a playback to edit.")
    
    def _remove_playback(self):
        """Remove the selected playback from the pool."""
        current_row = self.playback_list.currentRow()
        if current_row >= 0:
            self.playback_list.takeItem(current_row)
            self._mark_modified()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a playback to remove.")
    
    def _save(self):
        """Save the cue (to session or return via signal depending on mode)."""
        # Update data from UI
        self._update_data_from_ui()
        
        # Validate
        if not self.cue_data.get("name"):
            QMessageBox.warning(self, "Validation Error", "Cue name is required.")
            return
        
        if self.cue_data.get("duration_seconds", 0) <= 0:
            QMessageBox.warning(self, "Validation Error", "Duration must be greater than 0.")
            return
        
        # Full session mode: save directly to session if we have cuelist_key and cue_index
        if self.cuelist_key is not None and self.cue_index is not None:
            self._save_to_session()
        else:
            # Hybrid/legacy mode: emit cue data for caller to handle
            self.saved.emit()
            self.logger.info(f"Cue saved (legacy/hybrid): {self.cue_data.get('name')}")
        
        self.accept()
    
    def _save_to_session(self):
        """Save cue to session dict (session mode)."""
        try:
            # Get cuelist from session
            if "cuelists" not in self.session_data:
                self.session_data["cuelists"] = {}
            
            if self.cuelist_key not in self.session_data["cuelists"]:
                self.logger.error(f"Cuelist '{self.cuelist_key}' not found in session")
                QMessageBox.critical(self, "Error", f"Cuelist '{self.cuelist_key}' not found!")
                return
            
            cuelist = self.session_data["cuelists"][self.cuelist_key]
            
            # Ensure cues list exists
            if "cues" not in cuelist:
                cuelist["cues"] = []
            
            if self.cue_index is not None:
                # Update existing cue
                if 0 <= self.cue_index < len(cuelist["cues"]):
                    cuelist["cues"][self.cue_index] = self.cue_data
                    self.logger.info(f"Updated cue at index {self.cue_index} in '{self.cuelist_key}'")
                else:
                    self.logger.error(f"Invalid cue index: {self.cue_index}")
                    QMessageBox.critical(self, "Error", "Invalid cue index!")
                    return
            else:
                # Add new cue
                cuelist["cues"].append(self.cue_data)
                self.logger.info(f"Added new cue to '{self.cuelist_key}'")
            
            # Emit saved signal (no data needed for session mode)
            self.saved.emit()
            
        except Exception as e:
            self.logger.error(f"Failed to save cue to session: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"Failed to save cue:\n{e}")
    
    def _cancel(self):
        """Cancel and close the editor."""
        if self.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.reject()
        else:
            self.reject()
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
