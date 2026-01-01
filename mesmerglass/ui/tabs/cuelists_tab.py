"""Cuelists Tab - Browse and manage cuelist definitions from session.

Features:
- Read cuelists from session_data['cuelists']
- Table view with columns: Name, # Cues, Duration, Loop Mode, Actions
- Search/filter functionality
- Double-click to open Cuelist Editor
- New Cuelist button
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from .base_tab import BaseTab
from ..editors import CuelistEditor


class CuelistsTab(BaseTab):
    """Tab for browsing and managing cuelist definitions from session."""
    
    # Signal emitted when cuelists are modified
    data_changed = pyqtSignal()
    
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.cuelists: List[Tuple[str, Dict[str, Any]]] = []  # List of (key, data) tuples
        self.session_data: Optional[Dict[str, Any]] = None
        self._selected_cuelist_key: Optional[str] = None
        self._setup_ui()
    
    def set_session_data(self, session_data: Dict[str, Any]):
        """Set session data reference and reload cuelists."""
        self.session_data = session_data
        self._load_cuelists()
        self.logger.info("CuelistsTab session data set")
    
    def _setup_ui(self):
        """Build the cuelists tab UI."""
        # Match the Playbacks list/table styling so selection + rows feel consistent.
        self.setStyleSheet(
            "QTableWidget {"
            "  gridline-color: #333333;"
            "  background-color: #1e1e1e;"
            "  alternate-background-color: #252526;"
            "}"
            "QHeaderView::section {"
            "  background-color: #252526;"
            "  border: 0px;"
            "  padding: 6px;"
            "}"
            "QTableWidget::item {"
            "  padding: 6px;"
            "}"
            "QTableWidget::item:selected {"
            "  background-color: rgba(255, 138, 0, 55);"
            "  color: #ffffff;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # === HEADER: Title + New Button ===
        header_layout = QHBoxLayout()
        
        title = QLabel("📝 Cuelists")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        btn_new = QPushButton("➕ New Cuelist")
        btn_new.clicked.connect(self._on_new_cuelist)
        header_layout.addWidget(btn_new)

        btn_delete = QPushButton("🗑️ Delete Cuelist")
        btn_delete.clicked.connect(self._on_delete_selected_cuelist)
        header_layout.addWidget(btn_delete)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._on_refresh)
        header_layout.addWidget(btn_refresh)
        
        layout.addLayout(header_layout)
        
        # === SEARCH: Filter box ===
        search_layout = QHBoxLayout()
        
        search_label = QLabel("🔍 Search:")
        search_layout.addWidget(search_label)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter by name, description...")
        self.search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_box)
        
        layout.addLayout(search_layout)
        
        # === TABLE: Cuelist list ===
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Name", "# Cues", "Duration", "Loop Mode", "Actions"
        ])

        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        
        # Configure table
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        
        # Stretch columns
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # # Cues
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Duration
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Loop Mode
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # Actions
        self.table.setColumnWidth(4, 170)

        # Center the table so rows don't become a full-width "long bar".
        self.table.setMaximumWidth(1200)
        self.table_container = QWidget()
        table_container_layout = QHBoxLayout(self.table_container)
        table_container_layout.setContentsMargins(0, 0, 0, 0)
        table_container_layout.setSpacing(0)
        table_container_layout.addStretch(1)
        table_container_layout.addWidget(self.table, 10)
        table_container_layout.addStretch(1)

        layout.addWidget(self.table_container, 1)
        
        # === FOOTER: Status ===
        self.status_label = QLabel("No cuelists found")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Load cuelists on init
        self._load_cuelists()
        
        self.logger.info("CuelistsTab initialized")
    
    def _load_cuelists(self):
        """Load cuelists from session data."""
        try:
            self.cuelists = []
            
            if not self.session_data:
                self.logger.warning("No session data available")
                self._update_table()
                return
            
            # Get cuelists dict from session
            cuelists_dict = self.session_data.get("cuelists", {})
            
            # Convert dict to list of (key, data) tuples
            for key, data in cuelists_dict.items():
                # Make a copy and add key for reference
                data_with_key = data.copy()
                data_with_key["_key"] = key
                self.cuelists.append((key, data_with_key))
            
            # Sort by name
            self.cuelists.sort(key=lambda x: x[1].get("name", "").lower())
            
            # Update table
            self._update_table()
            
            # Update status
            self.status_label.setText(f"Found {len(self.cuelists)} cuelist(s)")
            self.logger.info(f"Loaded {len(self.cuelists)} cuelists")
            
        except Exception as e:
            self.logger.error(f"Failed to load cuelists: {e}", exc_info=True)
            self.status_label.setText("Error loading cuelists")
    
    def _update_table(self, filter_text: str = ""):
        """Update table with cuelist data."""
        self.table.setRowCount(0)
        
        # Filter cuelists
        filtered = self.cuelists
        if filter_text:
            filter_lower = filter_text.lower()
            filtered = [
                (key, data) for key, data in self.cuelists
                if filter_lower in data.get("name", "").lower()
            ]
        
        # Populate table
        for key, data in filtered:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Name
            name_item = QTableWidgetItem(data.get("name", "Unnamed"))
            self.table.setItem(row, 0, name_item)
            
            # # Cues
            cues = data.get("cues", [])
            num_cues = len(cues)
            cues_item = QTableWidgetItem(str(num_cues))
            cues_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, cues_item)
            
            # Duration
            duration_sec = 0.0
            for cue in cues:
                if not isinstance(cue, dict):
                    continue
                if "duration_seconds" in cue:
                    try:
                        duration_sec += float(cue.get("duration_seconds") or 0.0)
                        continue
                    except Exception:
                        pass
                if "duration_ms" in cue:
                    try:
                        duration_sec += float(cue.get("duration_ms") or 0.0) / 1000.0
                        continue
                    except Exception:
                        pass
                # Back-compat/other schemas
                if "duration" in cue:
                    try:
                        duration_sec += float(cue.get("duration") or 0.0)
                    except Exception:
                        pass

            duration_str = self._format_duration(duration_sec)

            loop_mode = data.get("loop_mode", "once")
            if str(loop_mode).lower() in ("loop", "ping_pong"):
                duration_str = f"{duration_str} ∞"

            duration_item = QTableWidgetItem(duration_str)
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, duration_item)
            
            # Loop Mode
            loop_item = QTableWidgetItem(loop_mode)
            loop_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, loop_item)
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(8)

            actions_layout.addStretch(1)

            btn_edit = QPushButton("Edit")
            btn_edit.setFixedWidth(52)
            btn_edit.clicked.connect(lambda _checked=False, k=key: self._open_cuelist_editor(k))
            actions_layout.addWidget(btn_edit)

            btn_delete = QPushButton("Delete")
            btn_delete.setFixedWidth(62)
            btn_delete.clicked.connect(lambda _checked=False, k=key: self._delete_cuelist(k))
            actions_layout.addWidget(btn_delete)

            actions_layout.addStretch(1)
            self.table.setCellWidget(row, 4, actions_widget)
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    
    def _on_search_changed(self, text: str):
        """Handle search box text change."""
        self._update_table(filter_text=text)
    
    def _on_refresh(self):
        """Refresh cuelist list."""
        self._load_cuelists()

    def _filtered_cuelists(self) -> List[Tuple[str, Dict[str, Any]]]:
        filter_text = self.search_box.text().lower()
        filtered = self.cuelists
        if filter_text:
            filtered = [
                (key, data) for key, data in self.cuelists
                if filter_text in data.get("name", "").lower()
            ]
        return filtered

    def _get_selected_cuelist_key_from_table(self) -> Optional[str]:
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        filtered = self._filtered_cuelists()
        if current_row >= len(filtered):
            return None
        key, _data = filtered[current_row]
        return key

    def _on_table_selection_changed(self) -> None:
        key = self._get_selected_cuelist_key_from_table()
        if key:
            self._selected_cuelist_key = key

    def _on_delete_selected_cuelist(self) -> None:
        key = self._get_selected_cuelist_key_from_table() or self._selected_cuelist_key
        if not key:
            QMessageBox.information(self, "Delete Cuelist", "Select a cuelist to delete.")
            return
        self._delete_cuelist(key)

    def _open_cuelist_editor(self, cuelist_key: str) -> None:
        if not self.session_data:
            self.logger.warning("Cannot edit cuelist: no session loaded")
            return

        editor = CuelistEditor(session_data=self.session_data, cuelist_key=cuelist_key, parent=self)
        editor.saved.connect(self._on_cuelist_saved)
        editor.exec()

    def _delete_cuelist(self, cuelist_key: str) -> bool:
        if not self.session_data:
            QMessageBox.warning(self, "Delete Cuelist", "No session loaded.")
            return False

        cuelists = self.session_data.get("cuelists")
        if not isinstance(cuelists, dict) or cuelist_key not in cuelists:
            QMessageBox.warning(self, "Delete Cuelist", f"Cuelist '{cuelist_key}' not found in session.")
            return False

        name = cuelists.get(cuelist_key, {}).get("name", cuelist_key)
        reply = QMessageBox.question(
            self,
            "Delete Cuelist",
            f"Delete cuelist '{name}'?\n\nThis will remove it from the current session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        try:
            del cuelists[cuelist_key]
            if self._selected_cuelist_key == cuelist_key:
                self._selected_cuelist_key = None
            self._load_cuelists()
            self.data_changed.emit()
            return True
        except Exception as exc:
            self.logger.error("Failed to delete cuelist %s: %s", cuelist_key, exc, exc_info=True)
            QMessageBox.critical(self, "Delete Cuelist", f"Failed to delete cuelist:\n{exc}")
            return False
    
    def _on_new_cuelist(self):
        """Create a new cuelist."""
        # TODO: Update CuelistEditor to support session mode
        if not self.session_data:
            self.logger.warning("Cannot create cuelist: no session loaded")
            return
        
        # Open editor in session mode (pass session reference and None for key = new)
        editor = CuelistEditor(session_data=self.session_data, cuelist_key=None, parent=self)
        editor.saved.connect(self._on_cuelist_saved)
        editor.exec()
        self.logger.info("Cuelist editor closed (new)")
    
    def _on_double_click(self):
        """Handle double-click on cuelist row."""
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        
        if not self.session_data:
            self.logger.warning("Cannot edit cuelist: no session loaded")
            return
        
        filtered = self._filtered_cuelists()
        
        if current_row >= len(filtered):
            return
        
        key, data = filtered[current_row]

        self._open_cuelist_editor(key)
        self.logger.info(f"Cuelist editor closed: {data.get('name')}")
    
    def _on_cuelist_saved(self):
        """Handle cuelist saved from editor."""
        # Reload cuelists from session and emit change signal
        self._load_cuelists()
        self.data_changed.emit()
        self.logger.debug("Cuelist saved, session marked dirty")
    
    def on_show(self):
        """Called when tab becomes visible."""
        self.logger.debug("CuelistsTab shown")
        # Refresh cuelists when tab is shown
        self._load_cuelists()
    
    def on_hide(self):
        """Called when tab becomes hidden."""
        self.logger.debug("CuelistsTab hidden")
