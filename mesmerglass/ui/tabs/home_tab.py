"""Home tab - Session Runner mission control.

Main features:
- Session information display
- SessionRunner controls (Start/Pause/Stop/Skip) from Phase 6
- Live preview area (LoomCompositor)
- Quick actions (one-click features)
- Media Bank shortcuts
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QWidget, QFileDialog,
    QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt

from .base_tab import BaseTab
from ..session_runner_tab import SessionRunnerTab
from ..editors import CuelistEditor, PlaybackEditor


class HomeTab(BaseTab):
    """Home tab with session info, SessionRunner controls, live preview, and quick actions."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.session_data: Optional[Dict[str, Any]] = None
        self._setup_ui()
    
    def set_session_data(self, session_data: Dict[str, Any]):
        """Set session data reference and update display."""
        self.session_data = session_data
        self._update_session_display()
        
        # Pass session data to SessionRunnerTab for session mode
        if hasattr(self, 'session_runner_tab'):
            self.session_runner_tab.set_session_data(session_data)
        
        self.logger.info("HomeTab session data set")
    
    def _setup_ui(self):
        """Build the home tab UI with SessionRunner and preview."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Use splitter for resizable sections
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # === LEFT: Session Info + Session Runner Controls ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(12)
        
        # Session Information
        session_info_group = self._create_session_info_section()
        left_layout.addWidget(session_info_group)
        
        # Embed SessionRunnerTab from Phase 6
        # Pass engines from main window
        self.session_runner_tab = SessionRunnerTab(
            parent=self.main_window,
            visual_director=getattr(self.main_window, 'visual_director', None),
            audio_engine=getattr(self.main_window, 'audio_engine', None),
            compositor=getattr(self.main_window, 'compositor', None),
            display_tab=getattr(self.main_window, 'display_tab', None)
        )
        left_layout.addWidget(self.session_runner_tab, 1)
        
        # Quick Actions
        quick_actions_group = self._create_quick_actions()
        left_layout.addWidget(quick_actions_group)
        
        splitter.addWidget(left_panel)
        
        # === RIGHT: Live Preview + Media Bank ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)
        
        # Live Preview (placeholder for LoomCompositor)
        preview_group = self._create_preview_section()
        right_layout.addWidget(preview_group, 1)
        
        # Media Bank
        media_bank_group = self._create_media_bank_section()
        right_layout.addWidget(media_bank_group)
        
        splitter.addWidget(right_panel)
        
        # Set initial sizes (60% session runner, 40% preview)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        
        self.logger.info("HomeTab initialized with SessionRunner integration")
    
    def _create_session_info_section(self) -> QGroupBox:
        """Create session information display section."""
        group = QGroupBox("📋 Session Information")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Session name
        self.session_name_label = QLabel("No session loaded")
        self.session_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(self.session_name_label)
        
        # Session metadata
        self.session_meta_label = QLabel("")
        self.session_meta_label.setStyleSheet("color: #888;")
        self.session_meta_label.setWordWrap(True)
        layout.addWidget(self.session_meta_label)
        
        # Session stats
        self.session_stats_label = QLabel("")
        layout.addWidget(self.session_stats_label)
        
        return group
    
    def _update_session_display(self):
        """Update session information display."""
        if not self.session_data:
            self.session_name_label.setText("No session loaded")
            self.session_meta_label.setText("")
            self.session_stats_label.setText("")
            return
        
        # Display session name
        metadata = self.session_data.get("metadata", {})
        name = metadata.get("name", "Unnamed Session")
        self.session_name_label.setText(name)
        
        # Display metadata
        description = metadata.get("description", "")
        author = metadata.get("author", "")
        meta_parts = []
        if description:
            meta_parts.append(f"📝 {description}")
        if author:
            meta_parts.append(f"👤 {author}")
        self.session_meta_label.setText("\n".join(meta_parts))
        
        # Display stats
        num_playbacks = len(self.session_data.get("playbacks", {}))
        num_cuelists = len(self.session_data.get("cuelists", {}))
        num_cues = sum(len(cl.get("cues", [])) for cl in self.session_data.get("cuelists", {}).values())
        
        stats_text = f"📊 {num_playbacks} playbacks • {num_cuelists} cuelists • {num_cues} cues"
        self.session_stats_label.setText(stats_text)
    
    def _create_quick_actions(self) -> QGroupBox:
        """Create quick actions section."""
        group = QGroupBox("⚡ Quick Actions")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Recent sessions
        btn_recent = QPushButton("📜 Recent Sessions")
        btn_recent.clicked.connect(self._on_recent_sessions)
        layout.addWidget(btn_recent)
        
        # New playback
        btn_playback = QPushButton("🎨 New Playback")
        btn_playback.clicked.connect(self._on_new_playback)
        layout.addWidget(btn_playback)
        
        # New cuelist
        btn_new = QPushButton("➕ New Cuelist")
        btn_new.clicked.connect(self._on_new_cuelist)
        layout.addWidget(btn_new)
        
        return group

    def _create_preview_section(self) -> QGroupBox:
        """Create live preview section."""
        group = QGroupBox("🎥 Live Preview")
        layout = QVBoxLayout(group)
        
        # Placeholder for LoomCompositor preview
        # TODO: Embed OpenGL widget from compositor
        self.preview_label = QLabel("Live preview coming soon...\n\n"
                                    "This will show the current spiral/media\n"
                                    "rendering in real-time.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background-color: #1e1e1e; "
            "border: 2px dashed #555; "
            "color: #888; "
            "padding: 40px; "
            "font-style: italic;"
        )
        layout.addWidget(self.preview_label, 1)
        
        return group
    
    def _create_media_bank_section(self) -> QGroupBox:
        """Create media bank shortcuts section."""
        group = QGroupBox("🏦 Media Bank")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Media bank info
        info_label = QLabel("Quick access to media directories")
        info_label.setStyleSheet("color: #888; font-style: italic; font-size: 10pt;")
        layout.addWidget(info_label)
        
        # Media bank list (shows entries from media_bank.json)
        self.media_bank_list = QListWidget()
        self.media_bank_list.setMaximumHeight(150)
        layout.addWidget(self.media_bank_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        btn_add = QPushButton("➕ Add Directory")
        btn_add.clicked.connect(self._on_add_media_directory)
        btn_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("🗑️ Remove")
        btn_remove.clicked.connect(self._on_remove_media_directory)
        btn_layout.addWidget(btn_remove)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._on_refresh_media_bank)
        btn_layout.addWidget(btn_refresh)
        
        layout.addLayout(btn_layout)
        
        # Load media bank on init
        self._load_media_bank()
        
        return group
    
    def _load_media_bank(self):
        """Load media bank from media_bank.json."""
        try:
            media_bank_path = Path("media_bank.json")
            if media_bank_path.exists():
                with open(media_bank_path, 'r') as f:
                    media_bank = json.load(f)
                
                self.media_bank_list.clear()
                for entry in media_bank:
                    name = entry.get("name", "Unnamed")
                    path = entry.get("path", "")
                    type_icon = "🖼️" if entry.get("type") == "images" else "🎬"
                    item = QListWidgetItem(f"{type_icon} {name} ({path})")
                    self.media_bank_list.addItem(item)
                
                self.logger.info(f"Loaded {len(media_bank)} media bank entries")
            else:
                self.logger.warning("media_bank.json not found")
        except Exception as e:
            self.logger.error(f"Failed to load media bank: {e}", exc_info=True)
    
    def _on_refresh_media_bank(self):
        """Refresh media bank list."""
        self._load_media_bank()
    
    def _on_add_media_directory(self):
        """Add a new media directory to the bank."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Media Directory"
        )
        
        if not directory:
            return
        
        try:
            # Load existing media bank
            media_bank_path = Path("media_bank.json")
            media_bank = []
            if media_bank_path.exists():
                with open(media_bank_path, 'r') as f:
                    media_bank = json.load(f)
            
            # Add new entry
            dir_path = Path(directory)
            media_bank.append({
                "name": dir_path.name,
                "path": str(dir_path),
                "type": "images"  # Default to images (can be changed in MesmerLoom tab)
            })
            
            # Save
            with open(media_bank_path, 'w') as f:
                json.dump(media_bank, f, indent=2)
            
            self._load_media_bank()
            self.mark_dirty()
            self.logger.info(f"Added media directory: {directory}")
        except Exception as e:
            self.logger.error(f"Failed to add media directory: {e}", exc_info=True)
    
    def _on_remove_media_directory(self):
        """Remove selected media directory from the bank."""
        current_item = self.media_bank_list.currentRow()
        if current_item < 0:
            self.logger.warning("No media bank entry selected")
            return
        
        try:
            # Load existing media bank
            media_bank_path = Path("media_bank.json")
            if not media_bank_path.exists():
                return
            
            with open(media_bank_path, 'r') as f:
                media_bank = json.load(f)
            
            # Remove the selected entry
            if current_item < len(media_bank):
                removed_entry = media_bank.pop(current_item)
                
                # Save updated media bank
                with open(media_bank_path, 'w') as f:
                    json.dump(media_bank, f, indent=2)
                
                self.logger.info(f"Removed media directory: {removed_entry.get('name', 'Unknown')}")
                self._load_media_bank()
                self.mark_dirty()
        
        except Exception as e:
            self.logger.error(f"Failed to remove media directory: {e}", exc_info=True)
    
    def _on_recent_sessions(self):
        """Show recent sessions dialog."""
        recent_entries = self.main_window.get_recent_sessions()
        valid_entries = []
        labels = []
        for entry in recent_entries:
            path = Path(entry)
            if not path.exists():
                continue
            valid_entries.append(path)
            labels.append(f"{path.stem} — {path}")

        if not valid_entries:
            QMessageBox.information(
                self,
                "No Recent Sessions",
                "Open a session at least once to populate this list."
            )
            return

        selection, ok = QInputDialog.getItem(
            self,
            "Recent Sessions",
            "Select a session to load:",
            labels,
            0,
            False
        )

        if not ok or not selection:
            return

        selected_index = labels.index(selection)
        chosen_path = valid_entries[selected_index]
        if self.main_window.open_session_from_path(chosen_path):
            # Refresh local reference and UI since session_data gets replaced
            self.session_data = self.main_window.session_data
            self._update_session_display()
    
    def _on_new_cuelist(self):
        """Create a new cuelist."""
        if not self.session_data:
            QMessageBox.warning(
                self,
                "No Session Loaded",
                "Load or start a session before creating a cuelist."
            )
            return

        editor = CuelistEditor(session_data=self.session_data, cuelist_key=None, parent=self)
        editor.saved.connect(lambda *_: self._handle_cuelist_saved())
        editor.exec()
        self.logger.info("Cuelist editor closed from Home tab")

    def _handle_cuelist_saved(self):
        """Refresh UI after a cuelist is saved via the quick action."""
        self.mark_dirty()
        self._update_session_display()
        if hasattr(self.main_window, "cuelists_tab"):
            self.main_window.cuelists_tab.set_session_data(self.session_data)

    def _on_new_playback(self):
        """Create a new playback via the quick action."""
        if not self.session_data:
            QMessageBox.warning(
                self,
                "No Session Loaded",
                "Load or start a session before creating a playback."
            )
            return

        editor = PlaybackEditor(session_data=self.session_data, playback_key=None, parent=self)
        editor.saved.connect(lambda *_: self._handle_playback_saved())
        editor.exec()
        self.logger.info("Playback editor closed from Home tab")

    def _handle_playback_saved(self):
        """Refresh UI after a playback is saved via the quick action."""
        self.mark_dirty()
        self._update_session_display()
        if hasattr(self.main_window, "playbacks_tab"):
            self.main_window.playbacks_tab.set_session_data(self.session_data)
    
    def on_show(self):
        """Called when tab becomes visible."""
        self.logger.debug("HomeTab shown")
        # Refresh media bank when tab is shown
        self._load_media_bank()
        
        # Update SessionRunner dependencies if available
        if self.visual_director:
            self.session_runner_tab.visual_director = self.visual_director
        if self.audio_engine:
            self.session_runner_tab.audio_engine = self.audio_engine
        if self.compositor:
            self.session_runner_tab.compositor = self.compositor
    
    def on_hide(self):
        """Called when tab becomes hidden."""
        self.logger.debug("HomeTab hidden")
