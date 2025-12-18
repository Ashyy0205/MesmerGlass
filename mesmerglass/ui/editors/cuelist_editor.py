"""Cuelist Editor Window - Edit .cuelist.json files.

Features:
- Edit cuelist metadata (name, description, author, loop mode)
- Add/remove/reorder cues
- Double-click cue to open Cue Editor
- Save/Save As functionality
- Validation before save
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QTextEdit, QMessageBox,
    QFileDialog, QGroupBox, QFormLayout, QDialogButtonBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon

from .cue_editor import CueEditor


class CuelistEditor(QDialog):
    """Editor window for cuelist files and session cuelists."""
    
    # Signal emitted when cuelist is saved
    saved = pyqtSignal(str)  # file path (empty string for session mode)
    
    def __init__(self, file_path: Optional[Path] = None, session_data: Optional[dict] = None, cuelist_key: Optional[str] = None, parent=None):
        """
        Initialize CuelistEditor.
        
        Two modes:
        1. File mode: file_path provided, saves to file
        2. Session mode: session_data + cuelist_key provided, modifies session dict in-place
        
        Args:
            file_path: Path to cuelist JSON file (file mode)
            session_data: Reference to session dict (session mode)
            cuelist_key: Key in session["cuelists"] (session mode, None = new cuelist)
            parent: Parent widget
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        
        # Mode determination
        self.file_path = file_path
        self.session_data = session_data
        self.cuelist_key = cuelist_key
        self.is_session_mode = session_data is not None
        
        self.cuelist_data: Dict[str, Any] = {}
        self.is_modified = False
        
        self.setWindowTitle("Cuelist Editor")
        self.setModal(True)
        self.resize(700, 600)
        
        self._setup_ui()
        
        # Load data based on mode
        if self.is_session_mode:
            if self.cuelist_key:
                # Editing existing cuelist from session
                cuelist_data = self.session_data.get("cuelists", {}).get(self.cuelist_key)
                if cuelist_data:
                    self._load_from_dict(cuelist_data)
                else:
                    self.logger.warning(f"Cuelist key '{self.cuelist_key}' not found in session")
                    self._create_new()
            else:
                # Creating new cuelist in session
                self._create_new()
        elif file_path:
            # File mode: load from file
            self._load_file(file_path)
        else:
            # File mode: new file
            self._create_new()
    
    def _setup_ui(self):
        """Build the editor UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # === METADATA SECTION ===
        metadata_group = QGroupBox("Cuelist Metadata")
        metadata_layout = QFormLayout(metadata_group)
        
        # Name
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._mark_modified)
        metadata_layout.addRow("Name:", self.name_edit)
        
        # Description
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(60)
        self.description_edit.textChanged.connect(self._mark_modified)
        metadata_layout.addRow("Description:", self.description_edit)
        
        # Author
        self.author_edit = QLineEdit()
        self.author_edit.textChanged.connect(self._mark_modified)
        metadata_layout.addRow("Author:", self.author_edit)
        
        # Loop Mode
        self.loop_mode_combo = QComboBox()
        self.loop_mode_combo.addItems(["once", "loop"])
        self.loop_mode_combo.currentTextChanged.connect(self._mark_modified)
        metadata_layout.addRow("Loop Mode:", self.loop_mode_combo)
        
        # Transition Mode
        self.transition_mode_combo = QComboBox()
        self.transition_mode_combo.addItems(["snap", "fade"])
        self.transition_mode_combo.currentTextChanged.connect(self._mark_modified)
        self.transition_mode_combo.currentTextChanged.connect(self._on_transition_mode_changed)
        metadata_layout.addRow("Cue Transition:", self.transition_mode_combo)
        
        # Transition Duration (only enabled for fade mode)
        self.transition_duration_spin = QSpinBox()
        self.transition_duration_spin.setRange(100, 10000)
        self.transition_duration_spin.setSuffix(" ms")
        self.transition_duration_spin.setValue(2000)
        self.transition_duration_spin.valueChanged.connect(self._mark_modified)
        metadata_layout.addRow("Fade Duration:", self.transition_duration_spin)
        
        layout.addWidget(metadata_group)
        
        # === CUES SECTION ===
        cues_group = QGroupBox("Cues")
        cues_layout = QVBoxLayout(cues_group)
        
        # Cue list
        self.cues_list = QListWidget()
        self.cues_list.itemDoubleClicked.connect(self._edit_cue)
        cues_layout.addWidget(self.cues_list, 1)
        
        # Cue buttons
        cue_buttons_layout = QHBoxLayout()
        
        btn_add_cue = QPushButton("➕ Add Cue")
        btn_add_cue.clicked.connect(self._add_cue)
        cue_buttons_layout.addWidget(btn_add_cue)
        
        btn_edit_cue = QPushButton("✏️ Edit Cue")
        btn_edit_cue.clicked.connect(self._edit_selected_cue)
        cue_buttons_layout.addWidget(btn_edit_cue)
        
        btn_remove_cue = QPushButton("➖ Remove Cue")
        btn_remove_cue.clicked.connect(self._remove_cue)
        cue_buttons_layout.addWidget(btn_remove_cue)
        
        btn_move_up = QPushButton("⬆️ Move Up")
        btn_move_up.clicked.connect(self._move_cue_up)
        cue_buttons_layout.addWidget(btn_move_up)
        
        btn_move_down = QPushButton("⬇️ Move Down")
        btn_move_down.clicked.connect(self._move_cue_down)
        cue_buttons_layout.addWidget(btn_move_down)
        
        cue_buttons_layout.addStretch()
        
        cues_layout.addLayout(cue_buttons_layout)
        
        layout.addWidget(cues_group, 1)
        
        # === DIALOG BUTTONS ===
        button_box = QDialogButtonBox()
        
        btn_save = button_box.addButton("💾 Save", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_save.clicked.connect(self._save)
        
        btn_save_as = button_box.addButton("💾 Save As...", QDialogButtonBox.ButtonRole.ActionRole)
        btn_save_as.clicked.connect(self._save_as)
        
        btn_cancel = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.clicked.connect(self._cancel)
        
        layout.addWidget(button_box)
    
    def _create_new(self):
        """Create a new empty cuelist."""
        self.cuelist_data = {
            "name": "New Cuelist",
            "description": "",
            "version": "1.0",
            "author": "",
            "loop_mode": "once",
            "cues": []
        }
        self._update_ui_from_data()
        self.setWindowTitle("Cuelist Editor - New Cuelist")
    
    def _load_file(self, file_path: Path):
        """Load cuelist from file."""
        try:
            with open(file_path, 'r') as f:
                self.cuelist_data = json.load(f)
            
            self._load_from_dict(self.cuelist_data)
            self.setWindowTitle(f"Cuelist Editor - {file_path.name}")
            self.is_modified = False
            self.logger.info(f"Loaded cuelist: {file_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to load cuelist: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load cuelist:\n{e}"
            )
    
    def _load_from_dict(self, data: dict):
        """Load cuelist from data dictionary (used by both file and session modes)."""
        self.cuelist_data = data.copy()
        self._update_ui_from_data()
    
    def _update_ui_from_data(self):
        """Update UI widgets from cuelist_data."""
        # Metadata
        self.name_edit.setText(self.cuelist_data.get("name", ""))
        self.description_edit.setPlainText(self.cuelist_data.get("description", ""))
        self.author_edit.setText(self.cuelist_data.get("author", ""))
        
        loop_mode = self._normalize_loop_mode(self.cuelist_data.get("loop_mode", "once"))
        self.cuelist_data["loop_mode"] = loop_mode
        index = self.loop_mode_combo.findText(loop_mode)
        if index >= 0:
            self.loop_mode_combo.setCurrentIndex(index)
        
        # Transition settings
        transition_mode = self.cuelist_data.get("transition_mode", "snap")
        index = self.transition_mode_combo.findText(transition_mode)
        if index >= 0:
            self.transition_mode_combo.setCurrentIndex(index)
        
        transition_duration = self.cuelist_data.get("transition_duration_ms", 2000.0)
        self.transition_duration_spin.setValue(int(transition_duration))
        
        # Enable/disable duration spinbox based on mode
        self._on_transition_mode_changed(transition_mode)
        
        # Cues
        self.cues_list.clear()
        for cue in self.cuelist_data.get("cues", []):
            cue_name = cue.get("name", "Unnamed Cue")
            duration = cue.get("duration_seconds", 0)
            num_playbacks = len(cue.get("playback_pool", []))
            
            item_text = f"{cue_name} ({duration}s, {num_playbacks} playbacks)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, cue)
            self.cues_list.addItem(item)
    
    def _update_data_from_ui(self):
        """Update cuelist_data from UI widgets."""
        self.cuelist_data["name"] = self.name_edit.text()
        self.cuelist_data["description"] = self.description_edit.toPlainText()
        self.cuelist_data["author"] = self.author_edit.text()
        self.cuelist_data["loop_mode"] = self._normalize_loop_mode(self.loop_mode_combo.currentText())
        self.cuelist_data["transition_mode"] = self.transition_mode_combo.currentText()
        self.cuelist_data["transition_duration_ms"] = float(self.transition_duration_spin.value())
        self.cuelist_data["version"] = "1.0"
        
        # Cues are already stored in the list items
        cues = []
        for i in range(self.cues_list.count()):
            item = self.cues_list.item(i)
            cue_data = item.data(Qt.ItemDataRole.UserRole)
            if cue_data:
                cues.append(cue_data)
        self.cuelist_data["cues"] = cues
    
    def _mark_modified(self):
        """Mark the cuelist as modified."""
        if not self.is_modified:
            self.is_modified = True
            title = self.windowTitle()
            if not title.endswith(" *"):
                self.setWindowTitle(title + " *")
    
    def _on_transition_mode_changed(self, mode: str):
        """Enable/disable transition duration spinbox based on mode."""
        # Duration spinbox only enabled for fade mode
        self.transition_duration_spin.setEnabled(mode == "fade")

    def _normalize_loop_mode(self, value: str) -> str:
        """Return a UI-safe loop mode string (only once/loop)."""
        normalized = (value or "once").strip().lower()
        if normalized in ("loop", "loop_cues", "loop-count", "loop_count", "ping_pong", "ping-pong"):
            return "loop"
        return "once"
    
    def _add_cue(self):
        """Add a new cue."""
        # Create a basic cue structure
        new_cue = {
            "name": f"New Cue {self.cues_list.count() + 1}",
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
        
        # Add to list
        item_text = f"{new_cue['name']} ({new_cue['duration_seconds']}s, 0 playbacks)"
        item = QListWidgetItem(item_text)
        item.setData(Qt.ItemDataRole.UserRole, new_cue)
        self.cues_list.addItem(item)
        
        self._mark_modified()
        self.logger.info(f"Added new cue: {new_cue['name']}")
    
    def _edit_cue(self, item: QListWidgetItem):
        """Edit a cue using the CueEditor."""
        cue_data = item.data(Qt.ItemDataRole.UserRole)
        cue_index = self.cues_list.row(item)  # Get the index of this cue in the list
        
        # Open CueEditor in appropriate mode
        if self.is_session_mode:
            # Session mode: Check if CUELIST exists in session yet
            # (new cuelists and their cues aren't in session until Save button clicked)
            cuelist = self.session_data.get("cuelists", {}).get(self.cuelist_key) if self.cuelist_key else None
            cuelist_exists_in_session = cuelist is not None
            
            if cuelist_exists_in_session:
                # Cuelist exists in session - check if THIS cue exists
                cue_exists_in_session = (
                    "cues" in cuelist and 
                    0 <= cue_index < len(cuelist.get("cues", []))
                )
                
                if cue_exists_in_session:
                    # Cue exists in session - pass cuelist_key and cue_index for direct editing
                    editor = CueEditor(
                        cue_data=cue_data, 
                        session_data=self.session_data, 
                        cuelist_key=self.cuelist_key,
                        cue_index=cue_index,
                        parent=self
                    )
                    # In session mode, CueEditor saves directly to session_data
                    # We just need to refresh the UI from the session data
                    editor.saved.connect(lambda: self._refresh_cue_in_list_from_session(item, cue_index))
                else:
                    # Cuelist exists but this is a new cue added after last save
                    # Use hybrid mode (session access but no direct save)
                    editor = CueEditor(
                        cue_data=cue_data, 
                        session_data=self.session_data,
                        parent=self
                    )
                    editor.saved.connect(lambda: self._update_cue_in_list(item, editor.cue_data))
            else:
                # Cuelist doesn't exist in session yet - use hybrid mode
                # CueEditor will have session_data for playback pool access but will emit cue_data
                editor = CueEditor(
                    cue_data=cue_data, 
                    session_data=self.session_data,
                    parent=self
                )
                editor.saved.connect(lambda: self._update_cue_in_list(item, editor.cue_data))
        else:
            # Legacy file mode
            editor = CueEditor(cue_data=cue_data, parent=self)
            editor.saved.connect(lambda updated_cue: self._update_cue_in_list(item, updated_cue))
        
        editor.exec()
    
    def _refresh_cue_in_list_from_session(self, item: QListWidgetItem, cue_index: int):
        """Refresh a cue in the list from session data after editing (session mode)."""
        if not self.is_session_mode or not self.cuelist_key:
            return
        
        cuelist = self.session_data.get("cuelists", {}).get(self.cuelist_key)
        if not cuelist or "cues" not in cuelist:
            return
        
        cues = cuelist["cues"]
        if 0 <= cue_index < len(cues):
            updated_cue = cues[cue_index]
            
            # Update item data
            item.setData(Qt.ItemDataRole.UserRole, updated_cue)
            
            # Update item text
            name = updated_cue.get("name", "Unnamed Cue")
            duration = updated_cue.get("duration_seconds", 0)
            num_playbacks = len(updated_cue.get("playback_pool", []))
            
            item.setText(f"{name} ({duration}s, {num_playbacks} playbacks)")
            
            self._mark_modified()
            self.logger.info(f"Refreshed cue from session: {name}")
    
    def _update_cue_in_list(self, item: QListWidgetItem, updated_cue: Dict[str, Any]):
        """Update a cue in the list after editing."""
        # Update item data
        item.setData(Qt.ItemDataRole.UserRole, updated_cue)
        
        # Update item text
        name = updated_cue.get("name", "Unnamed Cue")
        duration = updated_cue.get("duration_seconds", 0)
        num_playbacks = len(updated_cue.get("playback_pool", []))
        
        item.setText(f"{name} ({duration}s, {num_playbacks} playbacks)")
        
        self._mark_modified()
        self.logger.info(f"Updated cue: {name}")
    
    def _edit_selected_cue(self):
        """Edit the currently selected cue."""
        current_item = self.cues_list.currentItem()
        if current_item:
            self._edit_cue(current_item)
        else:
            QMessageBox.warning(self, "No Selection", "Please select a cue to edit.")
    
    def _remove_cue(self):
        """Remove the selected cue."""
        current_row = self.cues_list.currentRow()
        if current_row >= 0:
            item = self.cues_list.item(current_row)
            cue_data = item.data(Qt.ItemDataRole.UserRole)
            cue_name = cue_data.get("name", "Unnamed")
            
            reply = QMessageBox.question(
                self,
                "Remove Cue",
                f"Remove cue '{cue_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.cues_list.takeItem(current_row)
                self._mark_modified()
                self.logger.info(f"Removed cue: {cue_name}")
        else:
            QMessageBox.warning(self, "No Selection", "Please select a cue to remove.")
    
    def _move_cue_up(self):
        """Move the selected cue up."""
        current_row = self.cues_list.currentRow()
        if current_row > 0:
            item = self.cues_list.takeItem(current_row)
            self.cues_list.insertItem(current_row - 1, item)
            self.cues_list.setCurrentRow(current_row - 1)
            self._mark_modified()
        else:
            QMessageBox.information(self, "Cannot Move", "Cue is already at the top.")
    
    def _move_cue_down(self):
        """Move the selected cue down."""
        current_row = self.cues_list.currentRow()
        if current_row >= 0 and current_row < self.cues_list.count() - 1:
            item = self.cues_list.takeItem(current_row)
            self.cues_list.insertItem(current_row + 1, item)
            self.cues_list.setCurrentRow(current_row + 1)
            self._mark_modified()
        else:
            QMessageBox.information(self, "Cannot Move", "Cue is already at the bottom.")
    
    def _save(self):
        """Save the cuelist (to session or file depending on mode)."""
        if self.is_session_mode:
            self._save_to_session()
        else:
            if not self.file_path:
                self._save_as()
                return
            self._save_to_file(self.file_path)
    
    def _save_to_session(self):
        """Save cuelist to session dict (session mode)."""
        try:
            # Update data from UI
            self._update_data_from_ui()
            
            # Validate
            if not self.cuelist_data.get("name"):
                QMessageBox.warning(self, "Validation Error", "Cuelist name is required.")
                return
            
            # Determine key and check if we need to rename
            old_key = self.cuelist_key
            new_key_suggestion = self.cuelist_data["name"].replace(' ', '_').lower()
            
            if self.cuelist_key:
                # Editing existing cuelist
                # Check if name changed significantly enough to warrant key rename
                if new_key_suggestion != self.cuelist_key:
                    # Offer to rename key
                    reply = QMessageBox.question(
                        self,
                        "Rename Cuelist Key?",
                        f"The cuelist name has changed.\n\n"
                        f"Current key: {self.cuelist_key}\n"
                        f"Suggested key: {new_key_suggestion}\n\n"
                        f"Update the key? This will update references in session runtime state.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        # Ensure new key is unique
                        base_key = new_key_suggestion
                        counter = 1
                        while new_key_suggestion in self.session_data.get("cuelists", {}) and new_key_suggestion != self.cuelist_key:
                            new_key_suggestion = f"{base_key}_{counter}"
                            counter += 1
                        
                        # Update runtime state if this cuelist is active
                        self._update_cuelist_references(old_key, new_key_suggestion)
                        
                        # Remove old key, use new key
                        if old_key in self.session_data.get("cuelists", {}):
                            del self.session_data["cuelists"][old_key]
                        key = new_key_suggestion
                        self.cuelist_key = new_key_suggestion  # Update for future saves
                    else:
                        # Keep old key
                        key = self.cuelist_key
                else:
                    # Key is fine, keep it
                    key = self.cuelist_key
            else:
                # New cuelist - generate key from name
                key = new_key_suggestion
                # Ensure uniqueness
                base_key = key
                counter = 1
                while key in self.session_data.get("cuelists", {}):
                    key = f"{base_key}_{counter}"
                    counter += 1
                self.cuelist_key = key  # Save for future reference
            
            # Update session dict
            if "cuelists" not in self.session_data:
                self.session_data["cuelists"] = {}
            
            self.session_data["cuelists"][key] = self.cuelist_data
            
            self.is_modified = False
            title = self.windowTitle().replace(" *", "")
            self.setWindowTitle(title)
            
            self.logger.info(f"Saved cuelist to session: {key}")
            self.saved.emit("")  # Empty string for session mode
            
            QMessageBox.information(self, "Saved", f"Cuelist saved to session:\n{key}")
            
        except Exception as e:
            self.logger.error(f"Failed to save cuelist to session: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"Failed to save cuelist:\n{e}")
    
    def _update_cuelist_references(self, old_key: str, new_key: str):
        """Update references to a cuelist key in session runtime state.
        
        Args:
            old_key: Old cuelist key
            new_key: New cuelist key
        """
        try:
            # Update runtime state if this cuelist is currently active
            runtime = self.session_data.get("runtime", {})
            if runtime.get("active_cuelist") == old_key:
                runtime["active_cuelist"] = new_key
                self.logger.info(f"[CuelistEditor] Updated active_cuelist from '{old_key}' to '{new_key}'")
        
        except Exception as e:
            self.logger.error(f"[CuelistEditor] Failed to update cuelist references: {e}", exc_info=True)
    
    def _save_to_file(self, file_path: Path):
        """Save cuelist to file (file mode)."""
        try:
            # Update data from UI
            self._update_data_from_ui()
            
            # Validate
            if not self.cuelist_data.get("name"):
                QMessageBox.warning(self, "Validation Error", "Cuelist name is required.")
                return
            
            # Save to file
            with open(file_path, 'w') as f:
                json.dump(self.cuelist_data, f, indent=2)
            
            self.is_modified = False
            title = self.windowTitle().replace(" *", "")
            self.setWindowTitle(title)
            
            self.logger.info(f"Saved cuelist: {self.file_path}")
            self.saved.emit(str(self.file_path))
            
            QMessageBox.information(self, "Saved", f"Cuelist saved successfully:\n{self.file_path.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to save cuelist: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"Failed to save cuelist:\n{e}")
    
    def _save_as(self):
        """Save the cuelist to a new file (file mode only)."""
        if self.is_session_mode:
            # In session mode, just save to session
            self._save_to_session()
            return
        
        # Update data from UI first
        self._update_data_from_ui()
        
        # Suggest a filename
        suggested_name = self.cuelist_data.get("name", "new_cuelist").replace(" ", "_").lower()
        suggested_name = f"{suggested_name}.cuelist.json"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Cuelist As",
            f"cuelists/{suggested_name}",
            "Cuelist Files (*.cuelist.json);;All Files (*.*)"
        )
        
        if file_path:
            self.file_path = Path(file_path)
            self._save_to_file(self.file_path)
            self._save()
    
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
