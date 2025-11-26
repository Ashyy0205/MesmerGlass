"""
Cue Editor Dialog

Provides UI for editing cue properties including:
- Cue name and duration
- Playback pool entries with weights and durations
- Custom text messages per playback entry
- Selection mode and transitions
"""

import logging
from typing import Optional, List
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
    QListWidget, QListWidgetItem, QTextEdit, QDialogButtonBox,
    QWidget, QFormLayout, QMessageBox, QScrollArea
)

from ..session.cue import Cue, PlaybackEntry, PlaybackSelectionMode


class PlaybackEntryEditor(QWidget):
    """Widget for editing a single playback pool entry."""
    
    removed = pyqtSignal()  # Emitted when user clicks remove
    
    def __init__(self, entry: PlaybackEntry, available_playbacks: List[str], parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.entry = entry
        
        self._init_ui(available_playbacks)
        self._load_entry()
    
    def _init_ui(self, available_playbacks: List[str]):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # === Playback Selection ===
        playback_row = QHBoxLayout()
        playback_row.addWidget(QLabel("Playback:"))
        
        self.playback_combo = QComboBox()
        self.playback_combo.addItems(available_playbacks)
        self.playback_combo.setMinimumWidth(150)
        playback_row.addWidget(self.playback_combo, 1)
        
        # Remove button
        self.btn_remove = QPushButton("✕")
        self.btn_remove.setFixedSize(30, 30)
        self.btn_remove.setToolTip("Remove this playback entry")
        self.btn_remove.clicked.connect(self.removed.emit)
        playback_row.addWidget(self.btn_remove)
        
        layout.addLayout(playback_row)
        
        # === Weight and Duration ===
        params_row = QHBoxLayout()
        
        # Weight
        params_row.addWidget(QLabel("Weight:"))
        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0.1, 10.0)
        self.weight_spin.setSingleStep(0.1)
        self.weight_spin.setDecimals(1)
        self.weight_spin.setValue(1.0)
        self.weight_spin.setToolTip("Selection probability weight (higher = more likely)")
        params_row.addWidget(self.weight_spin)
        
        params_row.addSpacing(16)
        
        # Min Duration
        params_row.addWidget(QLabel("Min Duration (s):"))
        self.min_duration_spin = QDoubleSpinBox()
        self.min_duration_spin.setRange(1.0, 300.0)
        self.min_duration_spin.setSingleStep(1.0)
        self.min_duration_spin.setDecimals(1)
        self.min_duration_spin.setValue(5.0)
        self.min_duration_spin.setToolTip("Minimum time before switching")
        params_row.addWidget(self.min_duration_spin)
        
        params_row.addSpacing(8)
        
        # Max Duration
        params_row.addWidget(QLabel("Max Duration (s):"))
        self.max_duration_spin = QDoubleSpinBox()
        self.max_duration_spin.setRange(1.0, 300.0)
        self.max_duration_spin.setSingleStep(1.0)
        self.max_duration_spin.setDecimals(1)
        self.max_duration_spin.setValue(10.0)
        self.max_duration_spin.setToolTip("Maximum time before forced switch")
        params_row.addWidget(self.max_duration_spin)
        
        params_row.addStretch()
        layout.addLayout(params_row)
        
        # === Custom Text Messages ===
        text_group = QGroupBox("Custom Text Messages (optional)")
        text_group.setToolTip("Override playback's text with custom messages for this cue")
        text_layout = QVBoxLayout()
        
        self.text_edit = QTextEdit()
        self.text_edit.setMaximumHeight(80)
        self.text_edit.setPlaceholderText("Enter text messages, one per line.\nLeave empty to use playback's default text.")
        text_layout.addWidget(self.text_edit)
        
        text_group.setLayout(text_layout)
        layout.addWidget(text_group)
        
        # Style the widget
        self.setStyleSheet("""
            PlaybackEntryEditor {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
    
    def _load_entry(self):
        """Load entry data into UI."""
        # Playback selection
        playback_name = str(self.entry.playback_path)
        if playback_name.endswith('.json'):
            playback_name = Path(playback_name).stem
        
        index = self.playback_combo.findText(playback_name)
        if index >= 0:
            self.playback_combo.setCurrentIndex(index)
        
        # Weight
        self.weight_spin.setValue(self.entry.weight)
        
        # Durations
        if self.entry.min_duration_s is not None:
            self.min_duration_spin.setValue(self.entry.min_duration_s)
        if self.entry.max_duration_s is not None:
            self.max_duration_spin.setValue(self.entry.max_duration_s)
        
        # Text messages
        if self.entry.text_messages:
            self.text_edit.setPlainText('\n'.join(self.entry.text_messages))
    
    def save_to_entry(self):
        """Save UI data back to entry."""
        self.entry.playback_path = Path(self.playback_combo.currentText())
        self.entry.weight = self.weight_spin.value()
        self.entry.min_duration_s = self.min_duration_spin.value()
        self.entry.max_duration_s = self.max_duration_spin.value()
        
        # Parse text messages
        text_content = self.text_edit.toPlainText().strip()
        if text_content:
            self.entry.text_messages = [
                line.strip() for line in text_content.split('\n')
                if line.strip()
            ]
        else:
            self.entry.text_messages = None


class CueEditorDialog(QDialog):
    """Dialog for editing a cue's properties."""
    
    def __init__(self, cue: Cue, available_playbacks: List[str], parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.cue = cue
        self.available_playbacks = available_playbacks
        self.entry_editors: List[PlaybackEntryEditor] = []
        
        self.setWindowTitle(f"Edit Cue: {cue.name}")
        self.setSizeGripEnabled(True)
        
        self._init_ui()
        self._load_cue()
        self._apply_responsive_default_size()
    
    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(12, 12, 12, 12)

        # === Basic Properties ===
        basic_group = QGroupBox("Basic Properties")
        basic_layout = QFormLayout()
        
        # Name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter cue name")
        basic_layout.addRow("Name:", self.name_edit)
        
        # Duration
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(1.0, 3600.0)
        self.duration_spin.setSingleStep(5.0)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSuffix(" seconds")
        self.duration_spin.setToolTip("Total duration of this cue")
        basic_layout.addRow("Duration:", self.duration_spin)
        
        # Selection Mode
        self.selection_mode_combo = QComboBox()
        self.selection_mode_combo.addItems([
            "on_cue_start - Select once at start",
            "on_media_cycle - Switch at each media cycle"
        ])
        self.selection_mode_combo.setToolTip("When to select playbacks from the pool")
        basic_layout.addRow("Selection Mode:", self.selection_mode_combo)
        
        basic_group.setLayout(basic_layout)
        content_layout.addWidget(basic_group)
        
        # === Playback Pool ===
        pool_group = QGroupBox("Playback Pool")
        pool_layout = QVBoxLayout()
        
        # Header with add button
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Configure playback entries and their custom text:"))
        header_row.addStretch()
        
        self.btn_add_entry = QPushButton("+ Add Playback")
        self.btn_add_entry.clicked.connect(self._add_playback_entry)
        header_row.addWidget(self.btn_add_entry)
        pool_layout.addLayout(header_row)
        
        # Scroll area for entries
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(300)
        
        self.entries_container = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_container)
        self.entries_layout.setSpacing(8)
        self.entries_layout.addStretch()
        
        scroll.setWidget(self.entries_container)
        pool_layout.addWidget(scroll)
        
        pool_group.setLayout(pool_layout)
        content_layout.addWidget(pool_group, 1)  # Stretch
        content_layout.addStretch()

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area, 1)
        
        # === Dialog Buttons ===
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 0)
        self._button_box = buttons
    
    def _load_cue(self):
        """Load cue data into UI."""
        # Basic properties
        self.name_edit.setText(self.cue.name)
        self.duration_spin.setValue(self.cue.duration_seconds)
        
        # Selection mode
        if self.cue.selection_mode == PlaybackSelectionMode.ON_CUE_START:
            self.selection_mode_combo.setCurrentIndex(0)
        else:
            self.selection_mode_combo.setCurrentIndex(1)
        
        # Playback pool entries
        for entry in self.cue.playback_pool:
            self._add_playback_entry(entry)

    def _apply_responsive_default_size(self):
        preferred = self._calculate_preferred_size(self._current_screen_size())
        self.resize(preferred)

    def _current_screen_size(self) -> Optional[QSize]:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry().size()

    @staticmethod
    def _calculate_preferred_size(screen_size: Optional[QSize]) -> QSize:
        default = QSize(860, 700)
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
    
    def _add_playback_entry(self, entry: Optional[PlaybackEntry] = None):
        """Add a new playback entry editor."""
        if entry is None:
            # Create default entry
            entry = PlaybackEntry(
                playback_path=Path(self.available_playbacks[0] if self.available_playbacks else "playback"),
                weight=1.0,
                min_duration_s=5.0,
                max_duration_s=10.0,
                text_messages=None
            )
        
        editor = PlaybackEntryEditor(entry, self.available_playbacks, self)
        editor.removed.connect(lambda e=editor: self._remove_entry(e))
        
        # Insert before stretch
        self.entries_layout.insertWidget(len(self.entry_editors), editor)
        self.entry_editors.append(editor)
    
    def _remove_entry(self, editor: PlaybackEntryEditor):
        """Remove a playback entry editor."""
        if len(self.entry_editors) <= 1:
            QMessageBox.warning(
                self,
                "Cannot Remove",
                "At least one playback entry is required."
            )
            return
        
        self.entry_editors.remove(editor)
        editor.deleteLater()
    
    def _save_and_close(self):
        """Save changes and close dialog."""
        # Validate
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Cue name cannot be empty.")
            return
        
        if not self.entry_editors:
            QMessageBox.warning(self, "Validation Error", "At least one playback entry is required.")
            return
        
        # Validate durations
        for i, editor in enumerate(self.entry_editors, 1):
            min_dur = editor.min_duration_spin.value()
            max_dur = editor.max_duration_spin.value()
            
            if min_dur > max_dur:
                QMessageBox.warning(
                    self, 
                    "Validation Error", 
                    f"Entry {i}: Min duration ({min_dur}s) cannot exceed max duration ({max_dur}s)."
                )
                return
        
        # Save basic properties
        self.cue.name = self.name_edit.text().strip()
        self.cue.duration_seconds = self.duration_spin.value()
        
        # Save selection mode
        if self.selection_mode_combo.currentIndex() == 0:
            self.cue.selection_mode = PlaybackSelectionMode.ON_CUE_START
        else:
            self.cue.selection_mode = PlaybackSelectionMode.ON_MEDIA_CYCLE
        
        # Save playback pool
        self.cue.playback_pool.clear()
        for editor in self.entry_editors:
            editor.save_to_entry()
            self.cue.playback_pool.append(editor.entry)
        
        self.logger.info(f"Saved cue '{self.cue.name}' with {len(self.cue.playback_pool)} playback entries")
        self.accept()
