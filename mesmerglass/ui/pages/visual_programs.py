"""Visual Programs UI page - control Trance visual programs."""

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QPushButton, QHBoxLayout,
    QComboBox, QProgressBar
)


def _card(title: str) -> QGroupBox:
    """Create a titled group box."""
    box = QGroupBox(title)
    box.setContentsMargins(0, 0, 0, 0)
    return box


def _row(label: str, widget: QWidget, trailing: QWidget | None = None) -> QWidget:
    """Create a horizontal row with label and widget."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(10, 6, 10, 6)
    h.setSpacing(10)
    lab = QLabel(label)
    lab.setMinimumWidth(160)
    h.addWidget(lab, 0)
    h.addWidget(widget, 1)
    if trailing:
        h.addWidget(trailing, 0)
    return w


class VisualProgramsPage(QWidget):
    """Visual Programs control panel.
    
    Provides UI for:
    - Selecting visual program (7 types)
    - Start/stop/pause controls
    - Progress display
    - Visual info (name, description, frame count)
    
    Signals:
        visualSelected(int): User selected visual program by index
        startRequested(): User clicked Start
        stopRequested(): User clicked Stop
        pauseRequested(): User clicked Pause/Resume
        resetRequested(): User clicked Reset
    """
    
    # Signals
    visualSelected = pyqtSignal(int)
    startRequested = pyqtSignal()
    stopRequested = pyqtSignal()
    pauseRequested = pyqtSignal()
    resetRequested = pyqtSignal()
    customModeRequested = pyqtSignal(str)  # Emits path to custom mode JSON file
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self._is_playing = False
        self._is_paused = False
        
        # Layout
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(12)
        
        # ===== Visual Selection Card =====
        card_selection = _card("Visual Program Selection")
        sel_layout = QVBoxLayout(card_selection)
        sel_layout.setContentsMargins(12, 8, 12, 8)
        sel_layout.setSpacing(4)
        
        # Visual dropdown
        self.visual_combo = QComboBox()
        self.visual_combo.setToolTip("Select a visual program to run")
        self.visual_combo.currentIndexChanged.connect(self._on_visual_changed)
        sel_layout.addWidget(_row("Visual Program", self.visual_combo))
        
        # Description label
        self.description_label = QLabel("Select a visual program to see description")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #888; font-style: italic;")
        sel_layout.addWidget(self.description_label)
        
        root.addWidget(card_selection)
        
        # ===== Quick Start Guide =====
        card_guide = _card("📖 Quick Start Guide")
        guide_layout = QVBoxLayout(card_guide)
        guide_layout.setContentsMargins(12, 8, 12, 8)
        guide_layout.setSpacing(4)
        
        guide_text = QLabel(
            "<b>How to use Visual Programs:</b><br>"
            "1️⃣ Go to <b>🌀 MesmerLoom</b> tab → Check 'Enable Spiral'<br>"
            "2️⃣ Return here → Select a visual program above<br>"
            "3️⃣ Click <b>Start</b> button below<br>"
            "4️⃣ Click <b>Launch</b> button (bottom of window)<br>"
            "<br>"
            "<i>Test media is automatically loaded from MEDIA folder.<br>"
            "You should see a dropdown list of 7 visual programs.</i>"
        )
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #555; padding: 8px; background: #f0f0f0; border-radius: 4px;")
        guide_layout.addWidget(guide_text)
        
        root.addWidget(card_guide)
        
        # ===== Playback Controls Card =====
        card_playback = _card("Playback Controls")
        play_layout = QVBoxLayout(card_playback)
        play_layout.setContentsMargins(12, 8, 12, 8)
        play_layout.setSpacing(4)
        
        # Buttons row
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(10, 6, 10, 6)
        button_layout.setSpacing(8)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.setToolTip("Start the selected visual program")
        self.start_btn.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.start_btn)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setToolTip("Pause/resume the visual program")
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        self.pause_btn.setEnabled(False)
        button_layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setToolTip("Stop the visual program")
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip("Reset visual to beginning")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        self.reset_btn.setEnabled(False)
        button_layout.addWidget(self.reset_btn)
        
        button_layout.addStretch()
        
        play_layout.addWidget(button_row)
        
        root.addWidget(card_playback)
        
        # ===== Progress Card =====
        card_progress = _card("Progress")
        prog_layout = QVBoxLayout(card_progress)
        prog_layout.setContentsMargins(12, 8, 12, 8)
        prog_layout.setSpacing(4)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        prog_layout.addWidget(_row("Progress", self.progress_bar))
        
        # Frame counter
        self.frame_label = QLabel("Frame: 0")
        prog_layout.addWidget(_row("", self.frame_label))
        
        # Status
        self.status_label = QLabel("Status: Stopped")
        self.status_label.setStyleSheet("color: #888;")
        prog_layout.addWidget(_row("", self.status_label))
        
        root.addWidget(card_progress)
        
        # ===== Custom Modes Card (Future: Primary Visual System) =====
        card_custom = _card("📦 Custom Modes (New!)")
        custom_layout = QVBoxLayout(card_custom)
        custom_layout.setContentsMargins(12, 8, 12, 8)
        custom_layout.setSpacing(4)
        
        # Info label
        custom_info = QLabel(
            "<b>Custom modes</b> are JSON files created with the Visual Mode Creator.<br>"
            "They will eventually replace built-in Visual Programs with full customization."
        )
        custom_info.setWordWrap(True)
        custom_info.setStyleSheet("color: #555; font-size: 11px; padding: 4px;")
        custom_layout.addWidget(custom_info)
        
        # Custom mode file selection
        self.custom_mode_path_label = QLabel("No custom mode loaded")
        self.custom_mode_path_label.setWordWrap(True)
        self.custom_mode_path_label.setStyleSheet("color: #888; font-style: italic; font-size: 10px;")
        
        self.load_custom_btn = QPushButton("📂 Load Custom Mode...")
        self.load_custom_btn.setToolTip("Browse for a .json mode file created with Visual Mode Creator")
        self.load_custom_btn.clicked.connect(self._on_load_custom_clicked)
        
        custom_layout.addWidget(_row("Mode File", self.custom_mode_path_label, self.load_custom_btn))
        
        root.addWidget(card_custom)
        
        root.addStretch(1)
        
        # ===== Update Timer =====
        # Poll visual director for progress updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_update_timer)
        self.update_timer.setInterval(100)  # 10 Hz update
    
    # ===== Public Methods =====
    
    def set_visual_programs(self, programs: list[tuple[str, str]]) -> None:
        """Set available visual programs.
        
        Args:
            programs: List of (name, description) tuples
        """
        self.visual_combo.blockSignals(True)
        self.visual_combo.clear()
        
        for name, description in programs:
            self.visual_combo.addItem(name)
            # Store description in item data
            index = self.visual_combo.count() - 1
            self.visual_combo.setItemData(index, description, Qt.ItemDataRole.ToolTipRole)
        
        self.visual_combo.blockSignals(False)
        
        # Show first description
        if programs:
            self.description_label.setText(programs[0][1])
    
    def set_progress(self, progress: float, frame_count: int) -> None:
        """Update progress display.
        
        Args:
            progress: Progress from 0.0 to 1.0
            frame_count: Current frame number
        """
        progress_pct = int(progress * 100)
        self.progress_bar.setValue(progress_pct)
        self.frame_label.setText(f"Frame: {frame_count}")
    
    def set_status(self, status: str) -> None:
        """Update status label.
        
        Args:
            status: Status text (e.g., "Playing", "Paused", "Stopped")
        """
        self.status_label.setText(f"Status: {status}")
        
        # Color coding
        if "Playing" in status:
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        elif "Paused" in status:
            self.status_label.setStyleSheet("color: #FFC107; font-weight: bold;")
        elif "Stopped" in status:
            self.status_label.setStyleSheet("color: #888;")
        elif "Complete" in status:
            self.status_label.setStyleSheet("color: #2196F3; font-weight: bold;")
    
    def set_playing(self, playing: bool, paused: bool = False) -> None:
        """Update UI for playing state.
        
        Args:
            playing: True if visual is playing
            paused: True if paused (only valid if playing=True)
        """
        self._is_playing = playing
        self._is_paused = paused
        
        # Update button states
        self.start_btn.setEnabled(not playing)
        self.stop_btn.setEnabled(playing)
        self.pause_btn.setEnabled(playing)
        self.reset_btn.setEnabled(playing)
        
        # Update pause button text
        if paused:
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")
        
        # Update status
        if not playing:
            self.set_status("Stopped")
        elif paused:
            self.set_status("Paused")
        else:
            self.set_status("Playing")
        
        # Start/stop update timer
        if playing and not paused:
            self.update_timer.start()
        else:
            self.update_timer.stop()
    
    # ===== Slots =====
    
    def _on_visual_changed(self, index: int) -> None:
        """Visual program selection changed."""
        if index >= 0:
            # Update description
            description = self.visual_combo.itemData(index, Qt.ItemDataRole.ToolTipRole)
            if description:
                self.description_label.setText(description)
            
            # Emit signal
            self.visualSelected.emit(index)
    
    def _on_start_clicked(self) -> None:
        """Start button clicked."""
        self.startRequested.emit()
    
    def _on_stop_clicked(self) -> None:
        """Stop button clicked."""
        self.stopRequested.emit()
    
    def _on_pause_clicked(self) -> None:
        """Pause button clicked."""
        self.pauseRequested.emit()
    
    def _on_reset_clicked(self) -> None:
        """Reset button clicked."""
        self.resetRequested.emit()
    
    def _on_load_custom_clicked(self) -> None:
        """Load Custom Mode button clicked - open file dialog."""
        from PyQt6.QtWidgets import QFileDialog
        from pathlib import Path
        
        # Default to modes directory
        default_dir = Path(__file__).parent.parent.parent / "modes"
        if not default_dir.exists():
            default_dir = Path.home()
        
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Custom Visual Mode",
            str(default_dir),
            "JSON Mode Files (*.json);;All Files (*)"
        )
        
        if filepath:
            self.custom_mode_path_label.setText(Path(filepath).name)
            self.custom_mode_path_label.setStyleSheet("color: #2196F3; font-weight: bold;")
            self.customModeRequested.emit(filepath)
    
    def _on_update_timer(self) -> None:
        """Update timer fired - request progress update from launcher."""
        # This will be connected by launcher to call set_progress()
        pass
    
    # ===== Getters =====
    
    def get_selected_visual(self) -> int:
        """Get currently selected visual program index.
        
        Returns:
            Visual program index (0-6)
        """
        return self.visual_combo.currentIndex()
    
    def is_playing(self) -> bool:
        """Check if visual is playing.
        
        Returns:
            True if playing
        """
        return self._is_playing
    
    def is_paused(self) -> bool:
        """Check if visual is paused.
        
        Returns:
            True if paused
        """
        return self._is_paused
    
    # ===== Custom Mode Control =====
    
    def lock_visual_selector(self) -> None:
        """Disable visual program dropdown when custom mode is active.
        
        Custom modes bypass the visual program selector - they load directly
        via CustomVisual. Disabling the dropdown prevents confusion and
        ensures custom mode settings aren't overridden by built-in visuals.
        """
        self.visual_combo.setEnabled(False)
        # Update selection card title to indicate custom mode active
        # (The card title is set in _card() helper, would need refactoring to update dynamically)
    
    def unlock_visual_selector(self) -> None:
        """Re-enable visual program dropdown when switching to built-in visuals.
        
        Built-in visuals use the dropdown selector, so it needs to be enabled
        for normal operation.
        """
        self.visual_combo.setEnabled(True)
