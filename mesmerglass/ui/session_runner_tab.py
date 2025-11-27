"""
Session Runner Tab for Cuelist Execution

Provides UI for:
- Loading and running cuelists
- Real-time session progress visualization
- Playback controls (start/pause/stop/skip)
- Cue timeline with current position
- Session state monitoring
"""

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QFileDialog, QGroupBox,
    QProgressBar, QFrame, QMessageBox, QDialog
)

from mesmerglass.session.audio_prefetch import (
    gather_audio_paths_for_cuelist,
    prefetch_audio_for_cuelist,
)
from mesmerglass.ui.dialogs.cuelist_loading_dialog import CuelistLoadingDialog


class SessionRunnerTab(QWidget):
    """
    Tab for loading and executing cuelist sessions.
    
    Provides real-time visualization of session progress,
    playback controls, and cue timeline.
    """
    
    # Signals
    cuelist_loaded = pyqtSignal(object)  # Emits Cuelist object
    session_started = pyqtSignal()
    session_paused = pyqtSignal()
    session_resumed = pyqtSignal()
    session_stopped = pyqtSignal()
    
    def __init__(self, parent=None, visual_director=None, audio_engine=None, compositor=None, display_tab=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        
        # Dependencies for SessionRunner
        self.visual_director = visual_director
        self.audio_engine = audio_engine
        self.compositor = compositor
        self.display_tab = display_tab  # Reference to DisplayTab for monitor selection
        
        # Session state
        self.cuelist = None
        self.session_runner = None
        self.cuelist_path = None
        
        # Session data for session mode (when working within a .session.json)
        self.session_data = None
        
        # UI update timer (16ms = 60 Hz, matches compositor frame rate)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.setInterval(16)  # 60 Hz updates (matches compositor and zoom timing)
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # === HEADER: Load/Save Controls ===
        header_group = self._create_header_section()
        layout.addWidget(header_group)
        
        # === INFO: Cuelist Information ===
        info_group = self._create_info_section()
        layout.addWidget(info_group)
        
        # === TIMELINE: Visual Progress ===
        timeline_group = self._create_timeline_section()
        layout.addWidget(timeline_group)
        
        # === CONTROLS: Playback Buttons ===
        controls_group = self._create_controls_section()
        layout.addWidget(controls_group)
        
        # === CUE LIST: Cue Details ===
        cuelist_group = self._create_cuelist_section()
        layout.addWidget(cuelist_group, 1)  # Stretch
        
        # === FOOTER: Status ===
        self.status_label = QLabel("No cuelist loaded")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)
    
    def set_session_data(self, session_data: Optional[dict]):
        """
        Set session data for session mode.
        
        Args:
            session_data: Full session dict, or None for file mode
        """
        self.session_data = session_data
        self.logger.debug(f"SessionRunnerTab session_data set: {session_data is not None}")
        self._update_load_button_state()

    def _update_load_button_state(self) -> None:
        """Enable Load button only when a session has cuelists."""

        if not hasattr(self, "btn_load"):
            return

        if not self.session_data:
            self.btn_load.setEnabled(False)
            self.btn_load.setToolTip("Load a session with cuelists to continue")
            return

        has_cuelists = bool(self.session_data.get("cuelists"))
        self.btn_load.setEnabled(has_cuelists)
        if has_cuelists:
            self.btn_load.setToolTip("Load one of the cuelists defined in this session")
        else:
            self.btn_load.setToolTip("Add a cuelist to this session to enable loading")
    
    def _create_header_section(self) -> QGroupBox:
        """Create the header section with Load/Save buttons."""
        group = QGroupBox("Cuelist File")
        layout = QHBoxLayout()
        
        self.btn_load = QPushButton("📂 Load Cuelist...")
        self.btn_load.clicked.connect(self._on_load_cuelist)
        layout.addWidget(self.btn_load)
        
        self.btn_save = QPushButton("💾 Save Cuelist...")
        self.btn_save.clicked.connect(self._on_save_cuelist)
        self.btn_save.setEnabled(False)
        layout.addWidget(self.btn_save)
        
        layout.addStretch()
        
        self.btn_edit = QPushButton("✏️ Edit Cue...")
        self.btn_edit.clicked.connect(self._on_edit_cuelist)
        self.btn_edit.setEnabled(False)
        self.btn_edit.setToolTip("Edit the selected cue's playback pool and custom text messages")
        layout.addWidget(self.btn_edit)
        
        group.setLayout(layout)
        self._update_load_button_state()
        return group
    
    def _create_info_section(self) -> QGroupBox:
        """Create the info section showing cuelist details."""
        group = QGroupBox("Session Information")
        layout = QVBoxLayout()
        
        # Cuelist name
        self.label_cuelist_name = QLabel("<i>No cuelist loaded</i>")
        self.label_cuelist_name.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(self.label_cuelist_name)
        
        # Duration and cue count
        info_layout = QHBoxLayout()
        self.label_duration = QLabel("Duration: --:--")
        self.label_cue_count = QLabel("Cues: 0")
        info_layout.addWidget(self.label_duration)
        info_layout.addSpacing(20)
        info_layout.addWidget(self.label_cue_count)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_timeline_section(self) -> QGroupBox:
        """Create the timeline visualization section."""
        group = QGroupBox("Progress")
        layout = QVBoxLayout()
        
        # Progress bar (overall session)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Not started")
        layout.addWidget(self.progress_bar)
        
        # Current cue info
        self.label_current_cue = QLabel("Current: <i>None</i>")
        layout.addWidget(self.label_current_cue)
        
        # Cycle count
        self.label_cycle_count = QLabel("Cycles: 0")
        layout.addWidget(self.label_cycle_count)
        
        group.setLayout(layout)
        return group
    
    def _create_controls_section(self) -> QGroupBox:
        """Create the playback controls section."""
        group = QGroupBox("Playback Controls")
        layout = QHBoxLayout()
        
        self.btn_start = QPushButton("▶️ Start")
        self.btn_start.clicked.connect(self._on_start_session)
        self.btn_start.setEnabled(False)
        layout.addWidget(self.btn_start)
        
        self.btn_pause = QPushButton("⏸️ Pause")
        self.btn_pause.clicked.connect(self._on_pause_session)
        self.btn_pause.setEnabled(False)
        layout.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("⏹️ Stop")
        self.btn_stop.clicked.connect(self._on_stop_session)
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_stop)
        
        layout.addSpacing(20)
        
        self.btn_skip_next = QPushButton("⏭️ Skip to Next Cue")
        self.btn_skip_next.clicked.connect(self._on_skip_next_cue)
        self.btn_skip_next.setEnabled(False)
        layout.addWidget(self.btn_skip_next)
        
        layout.addStretch()
        
        group.setLayout(layout)
        return group
    
    def _create_cuelist_section(self) -> QGroupBox:
        """Create the cue list display section."""
        group = QGroupBox("Cue List")
        layout = QVBoxLayout()
        
        self.cue_list = QListWidget()
        self.cue_list.setAlternatingRowColors(True)
        layout.addWidget(self.cue_list)
        
        group.setLayout(layout)
        return group
    
    # === Event Handlers ===
    
    def _on_load_cuelist(self):
        """Load cuelist from session or JSON file."""
        # Session mode: Show dialog with session cuelists
        if self.session_data:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QDialogButtonBox
            
            available_cuelists = self.session_data.get("cuelists", {})
            if not available_cuelists:
                self.logger.warning("No cuelists in session")
                self.status_label.setText("⚠️ No cuelists in session")
                return
            
            # Show selection dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Select Cuelist")
            dialog.setMinimumWidth(400)
            
            layout = QVBoxLayout(dialog)
            
            list_widget = QListWidget()
            for cuelist_key, cuelist_data in available_cuelists.items():
                name = cuelist_data.get("name", cuelist_key)
                num_cues = len(cuelist_data.get("cues", []))
                list_widget.addItem(f"{name} ({num_cues} cues) [{cuelist_key}]")
            layout.addWidget(list_widget)
            
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() != QDialog.DialogCode.Accepted or not list_widget.currentItem():
                return
            
            # Extract cuelist key from selection
            selected_text = list_widget.currentItem().text()
            cuelist_key = selected_text.split("[")[-1].split("]")[0]
            
            try:
                from mesmerglass.session.cuelist import Cuelist
                
                # Load from session dict
                cuelist_data = available_cuelists[cuelist_key]
                self.cuelist = Cuelist.from_dict(cuelist_data)
                self.cuelist_path = None  # No file path in session mode
                
                # Validate
                is_valid, error = self.cuelist.validate()
                if not is_valid:
                    self.logger.error(f"Cuelist validation failed: {error}")
                    self.status_label.setText(f"❌ Validation failed: {error}")
                    self.cuelist = None
                    return
                
                # Update UI
                self._display_cuelist_info()
                self._populate_cue_list()
                
                # Enable controls
                self.btn_save.setEnabled(True)
                self.btn_edit.setEnabled(True)
                self.btn_start.setEnabled(True)
                
                self.status_label.setText(f"✅ Loaded: {self.cuelist.name} (from session)")
                prefetch_msg = self._prefetch_audio_for_loaded_cuelist()
                if prefetch_msg:
                    self.status_label.setText(f"{self.status_label.text()} • {prefetch_msg}")
                self.cuelist_loaded.emit(self.cuelist)
                
            except Exception as e:
                self.logger.error(f"Failed to load cuelist from session: {e}", exc_info=True)
                self.status_label.setText(f"❌ Error: {e}")
        
        # File mode: Use file browser
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Load Cuelist",
                "",
                "Cuelist Files (*.cuelist.json *.json);;All Files (*)"
            )
            
            if not file_path:
                return
            
            try:
                from mesmerglass.session.cuelist import Cuelist
                
                self.cuelist_path = Path(file_path)
                self.cuelist = Cuelist.load(self.cuelist_path)
                
                # Validate
                is_valid, error = self.cuelist.validate()
                if not is_valid:
                    self.logger.error(f"Cuelist validation failed: {error}")
                    self.status_label.setText(f"❌ Validation failed: {error}")
                    self.cuelist = None
                    return
                
                # Update UI
                self._display_cuelist_info()
                self._populate_cue_list()
                
                # Enable controls
                self.btn_save.setEnabled(True)
                self.btn_edit.setEnabled(True)
                self.btn_start.setEnabled(True)
                
                self.status_label.setText(f"✅ Loaded: {self.cuelist.name}")
                prefetch_msg = self._prefetch_audio_for_loaded_cuelist()
                if prefetch_msg:
                    self.status_label.setText(f"{self.status_label.text()} • {prefetch_msg}")
                self.cuelist_loaded.emit(self.cuelist)
                
            except Exception as e:
                self.logger.error(f"Failed to load cuelist: {e}", exc_info=True)
                self.status_label.setText(f"❌ Error: {e}")
    
    def _on_save_cuelist(self):
        """Save current cuelist to file."""
        if not self.cuelist:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Cuelist",
            "",
            "Cuelist Files (*.cuelist.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            save_path = Path(file_path)
            self.cuelist.save(save_path)
            self.cuelist_path = save_path
            self.status_label.setText(f"✅ Saved: {save_path.name}")
        except Exception as e:
            self.logger.error(f"Failed to save cuelist: {e}", exc_info=True)
            self.status_label.setText(f"❌ Save error: {e}")
    
    def _on_edit_cuelist(self):
        """Open cuelist editor for selected cue."""
        if not self.cuelist:
            self.status_label.setText("❌ No cuelist loaded")
            return
        
        # Get selected cue
        selected_items = self.cue_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select a cue to edit.")
            return
        
        selected_item = selected_items[0]
        cue_index = self.cue_list.row(selected_item)
        
        if cue_index < 0 or cue_index >= len(self.cuelist.cues):
            return
        
        cue = self.cuelist.cues[cue_index]
        
        # Get available playbacks
        available_playbacks = []
        if self.session_data and "playbacks" in self.session_data:
            available_playbacks = list(self.session_data["playbacks"].keys())
        
        if not available_playbacks:
            QMessageBox.warning(
                self,
                "No Playbacks Available",
                "No playbacks found in session. Please create playbacks first."
            )
            return
        
        # Open cue editor dialog
        from mesmerglass.ui.cue_editor_dialog import CueEditorDialog
        
        dialog = CueEditorDialog(cue, available_playbacks, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh UI
            self._populate_cue_list()
            self.status_label.setText(f"✅ Saved changes to cue '{cue.name}'")

            # Mark session as modified
            if self.session_data:
                # Update session data with modified cuelist
                # Find which cuelist this belongs to
                for cuelist_key, cuelist_data in self.session_data.get("cuelists", {}).items():
                    if cuelist_data.get("name") == self.cuelist.name:
                        # Update the cuelist data
                        self.session_data["cuelists"][cuelist_key] = self.cuelist.to_dict()
                        self.logger.info(f"Updated cuelist '{cuelist_key}' in session data")
                        break

    def _prefetch_audio_for_loaded_cuelist(self) -> Optional[str]:
        """Warm AudioEngine cache for the currently loaded cuelist."""
        if not self.cuelist or not self.audio_engine:
            return None

        audio_paths = gather_audio_paths_for_cuelist(self.cuelist, max_cues=1)
        if not audio_paths:
            return None

        dialog = CuelistLoadingDialog(total_files=len(audio_paths), parent=self)
        dialog.show()

        def _pump_events():
            app = QApplication.instance()
            if app is not None:
                app.processEvents()

        _pump_events()

        failures = 0

        def _on_progress(completed: int, total: int, file_path: str, success: bool) -> None:
            nonlocal failures
            if not success:
                failures += 1
            dialog.update_progress(completed, total, file_path, success)
            _pump_events()

        results: dict[str, bool] = {}
        try:
            results = prefetch_audio_for_cuelist(
                self.audio_engine,
                self.cuelist,
                file_paths=audio_paths,
                progress_callback=_on_progress,
            )
        finally:
            dialog.mark_complete(failures)
            _pump_events()
            dialog.close()

        if not results:
            return None

        ready = sum(1 for ok in results.values() if ok)
        total = len(audio_paths)
        summary = f"🎧 Prefetched {ready}/{total} audio tracks"
        if failures:
            summary += " (check logs)"
        self.logger.info(summary)
        return summary
    
    def _on_start_session(self):
        """Start session execution."""
        if not self.cuelist:
            self.status_label.setText("❌ No cuelist loaded")
            return
        
        if not self.visual_director or not self.audio_engine or not self.compositor:
            self.status_label.setText("❌ Missing dependencies (visual_director/audio/compositor)")
            self.logger.error("Cannot start session: missing dependencies")
            return

        if not self._check_theme_bank_ready():
            return
        
        try:
            from mesmerglass.session.runner import SessionRunner
            from mesmerglass.session.events import SessionEventType
            import json
            from pathlib import Path
            import tempfile
            
            # Resolve playback names to actual JSON files
            # Session stores playbacks as dict, but SessionRunner needs file paths
            if self.session_data and "playbacks" in self.session_data:
                playbacks_dict = self.session_data["playbacks"]
                temp_dir = Path(tempfile.gettempdir()) / "mesmerglass_playbacks"
                temp_dir.mkdir(exist_ok=True)
                
                # Write playback JSON files for each cue's playback_pool
                for cue in self.cuelist.cues:
                    for entry in cue.playback_pool:
                        playback_name = str(entry.playback_path)
                        
                        # If it's just a name (not a path), resolve it from session playbacks
                        if playback_name in playbacks_dict:
                            playback_data = playbacks_dict[playback_name]
                            
                            # Add version field if missing (required by CustomVisual)
                            if "version" not in playback_data:
                                playback_data["version"] = "1.0"
                            
                            playback_file = temp_dir / f"{playback_name}.json"
                            
                            # Write playback JSON
                            playback_file.write_text(json.dumps(playback_data, indent=2))
                            
                            # Update entry to point to actual file
                            entry.playback_path = playback_file
                            
                            self.logger.debug(f"Resolved playback '{playback_name}' -> {playback_file}")
            
            # Create SessionRunner
            self.session_runner = SessionRunner(
                cuelist=self.cuelist,
                visual_director=self.visual_director,
                audio_engine=self.audio_engine,
                compositor=self.compositor,
                display_tab=self.display_tab,  # Pass display selection
                session_data=self.session_data  # Pass session data for playback config access
            )
            
            # Connect events (use .subscribe() not .on())
            self.session_runner.event_emitter.subscribe(
                SessionEventType.CUE_START,
                self._on_cue_started
            )
            self.session_runner.event_emitter.subscribe(
                SessionEventType.CUE_END,
                self._on_cue_ended
            )
            self.session_runner.event_emitter.subscribe(
                SessionEventType.SESSION_STOP,
                self._on_session_ended
            )
            # Note: CYCLE_BOUNDARY event doesn't exist in SessionEventType
            
            # Start session
            self.session_runner.start()
            
            # Update UI
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.btn_skip_next.setEnabled(True)
            
            self.progress_bar.setFormat("Running...")
            self.status_label.setText("▶️ Session started")
            
            # Start UI update timer
            self.update_timer.start()
            
            self.session_started.emit()
            
        except Exception as e:
            self.logger.error(f"Failed to start session: {e}", exc_info=True)
            self.status_label.setText(f"❌ Start error: {e}")
    
    def _on_pause_session(self):
        """Pause/resume session."""
        if not self.session_runner:
            return
        
        try:
            from mesmerglass.session.runner import SessionState
            
            if self.session_runner.state == SessionState.RUNNING:
                self.session_runner.pause()
                self.btn_pause.setText("▶️ Resume")
                self.status_label.setText("⏸️ Session paused")
                self.session_paused.emit()
            elif self.session_runner.state == SessionState.PAUSED:
                self.session_runner.resume()
                self.btn_pause.setText("⏸️ Pause")
                self.status_label.setText("▶️ Session resumed")
                self.session_resumed.emit()
        except Exception as e:
            self.logger.error(f"Failed to pause/resume: {e}", exc_info=True)
            self.status_label.setText(f"❌ Pause error: {e}")
    
    def _on_stop_session(self):
        """Stop session execution."""
        if self.session_runner:
            try:
                self.session_runner.stop()
            except Exception as e:
                self.logger.error(f"Error stopping session: {e}", exc_info=True)
            pass
        
        # Reset UI
        self.update_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸️ Pause")  # Reset pause button text
        self.btn_stop.setEnabled(False)
        self.btn_skip_next.setEnabled(False)
        
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Stopped")
        self.label_current_cue.setText("Current: <i>None</i>")
        self.label_cycle_count.setText("Cycles: 0")
        
        self.status_label.setText("⏹️ Session stopped")
        self.session_stopped.emit()
    
    def _on_skip_next_cue(self):
        """Skip to next cue."""
        if not self.session_runner:
            return
        
        try:
            next_index = self.session_runner.get_current_cue_index() + 1
            if next_index < len(self.cuelist.cues):
                self.session_runner.skip_to_cue(next_index)
                self.status_label.setText(f"⏭️ Skipping to cue {next_index + 1}...")
            else:
                self.status_label.setText("⏭️ Already at last cue")
        except Exception as e:
            self.logger.error(f"Failed to skip: {e}", exc_info=True)
            self.status_label.setText(f"❌ Skip error: {e}")
    
    # === Event Handlers from SessionRunner ===
    
    def _on_cue_started(self, event):
        """Handle CUE_STARTED event."""
        cue_index = event.data.get("cue_index", -1)
        cue_name = event.data.get("cue_name", "Unknown")
        
        self.label_current_cue.setText(f"Current: <b>{cue_name}</b>")
        
        # Highlight active cue in list
        if 0 <= cue_index < self.cue_list.count():
            self.cue_list.setCurrentRow(cue_index)
        
        self.status_label.setText(f"🎬 Started cue: {cue_name}")
    
    def _on_cue_ended(self, event):
        """Handle CUE_ENDED event."""
        pass  # Just for logging if needed
    
    def _on_session_ended(self, event):
        """Handle SESSION_ENDED event."""
        self._on_stop_session()
        self.status_label.setText("✅ Session completed")
    
    def _on_cycle_boundary(self, event):
        """Handle CYCLE_BOUNDARY event."""
        cycle_count = event.data.get("cycle_count", 0)
        self.label_cycle_count.setText(f"Cycles: {cycle_count}")
    
    # === UI Update Methods ===
    
    def _display_cuelist_info(self):
        """Update info section with cuelist details."""
        if not self.cuelist:
            return
        
        self.label_cuelist_name.setText(self.cuelist.name)
        
        total_duration = self.cuelist.total_duration()
        minutes = int(total_duration // 60)
        seconds = int(total_duration % 60)
        self.label_duration.setText(f"Duration: {minutes:02d}:{seconds:02d}")
        
        self.label_cue_count.setText(f"Cues: {len(self.cuelist.cues)}")
    
    def _populate_cue_list(self):
        """Populate the cue list widget."""
        self.cue_list.clear()
        
        if not self.cuelist:
            return
        
        for i, cue in enumerate(self.cuelist.cues):
            duration = cue.duration_seconds
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            
            item_text = f"{i+1}. {cue.name} ({minutes:02d}:{seconds:02d})"
            item = QListWidgetItem(item_text)
            
            # Add metadata
            item.setData(Qt.ItemDataRole.UserRole, i)
            
            self.cue_list.addItem(item)
    
    def _update_ui(self):
        """Update UI with current session state (called periodically)."""
        if not self.session_runner or not self.cuelist:
            return
        
        # === CRITICAL: Call session_runner.update() to advance state machine ===
        # This drives:
        # - visual_director.update() → media cycler advance + async image loading
        # - audio_engine.update() → audio playback
        # - transition detection → cue changes
        if self.session_runner.is_running():
            self.session_runner.update(dt=0.01667)  # 16.67ms timer interval (60 Hz)
        
        # Only update UI if running
        if not self.session_runner.is_running():
            return
        
        # Update progress bar
        total_duration = self.cuelist.total_duration()
        current_cue_idx = self.session_runner.get_current_cue_index()
        
        elapsed = sum(
            cue.duration_seconds for i, cue in enumerate(self.cuelist.cues)
            if i < current_cue_idx
        )
        elapsed += self.session_runner._get_cue_elapsed_time()  # Private method but needed
        
        if total_duration > 0:
            progress_pct = min(100, int((elapsed / total_duration) * 100))
            self.progress_bar.setValue(progress_pct)
            
            # Format time remaining (clamp to 0 to prevent negative display)
            remaining = max(0, total_duration - elapsed)
            mins_remaining = int(remaining // 60)
            secs_remaining = int(remaining % 60)
            self.progress_bar.setFormat(f"{progress_pct}% - {mins_remaining}:{secs_remaining:02d} remaining")
    
    def set_session_runner(self, runner):
        """Set the SessionRunner instance for this tab (deprecated - use constructor)."""
        self.session_runner = runner

    def _check_theme_bank_ready(self) -> bool:
        theme_bank = getattr(self.visual_director, "theme_bank", None) if self.visual_director else None
        if theme_bank is None or not hasattr(theme_bank, "ensure_ready"):
            return True
        try:
            status = theme_bank.ensure_ready(timeout_s=0.25)
        except Exception as exc:
            self.logger.warning(f"ThemeBank readiness probe failed: {exc}")
            return True
        if not status.ready:
            message = (
                f"⚠️ ThemeBank not ready: {status.ready_reason}. "
                "Run 'python -m mesmerglass themebank stats' for diagnostics."
            )
            self.status_label.setText(message)
            self.logger.error("ThemeBank not ready: %s", status.ready_reason)
            return False
        self.logger.info(
            "ThemeBank ready before session start: images=%d videos=%d",
            status.total_images,
            status.total_videos,
        )
        return True
