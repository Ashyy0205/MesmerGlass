"""Playbacks Tab - Browse and manage playback definitions from session.

Features:
- Display playbacks from session_data['playbacks']
- Grid/list view toggle
- Preview thumbnails (spiral color preview)
- Search/filter functionality
- Double-click to open Playback Editor
- Shows name, description, spiral type, media mode
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGridLayout, QWidget, QFrame, QScrollArea, QButtonGroup, QRadioButton
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPalette

from .base_tab import BaseTab
from ..editors import PlaybackEditor


class PlaybackCard(QFrame):
    """Card widget for displaying a single playback in grid mode."""
    
    def __init__(self, playback_key: str, playback_data: Dict[str, Any], tab_widget, parent=None):
        super().__init__(parent)
        self.playback_key = playback_key
        self.playback_data = playback_data
        self.tab_widget = tab_widget  # Reference to PlaybacksTab
        self._setup_ui()
        
        # Make clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Styling is handled by PlaybacksTab stylesheet via the "selected" property.
        self.setProperty("selected", False)
    
    def _setup_ui(self):
        """Build card layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # === COLOR PREVIEW ===
        color_preview = QWidget()
        color_preview.setFixedSize(120, 80)
        
        # Extract spiral color
        spiral = self.playback_data.get("spiral", {})
        arm_color = spiral.get("arm_color", [0.0, 0.8, 1.0])  # Default cyan
        
        # Convert to RGB 0-255
        r = int(arm_color[0] * 255)
        g = int(arm_color[1] * 255)
        b = int(arm_color[2] * 255)
        
        color_preview.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid #555;")
        layout.addWidget(color_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # === NAME ===
        name = self.playback_data.get("name", "Unnamed")
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)
        
        # === DESCRIPTION ===
        description = self.playback_data.get("description", "")
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #aaa; font-size: 9pt;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        
        # === METADATA ===
        spiral_type = spiral.get("type", "logarithmic")
        if isinstance(spiral_type, int):
            type_names = ["logarithmic", "archimedean", "fermat", "hyperbolic"]
            spiral_type = type_names[spiral_type] if 0 <= spiral_type < 4 else f"type_{spiral_type}"
        
        media_mode = self.playback_data.get("media", {}).get("mode", "none")
        
        meta_label = QLabel(f"🌀 {spiral_type} | 🎨 {media_mode}")
        meta_label.setStyleSheet("color: #888; font-size: 9pt;")
        layout.addWidget(meta_label)
        
        layout.addStretch()
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click."""
        self.tab_widget._on_card_double_click(self.playback_key, self.playback_data)

    def mousePressEvent(self, event):
        """Handle single click selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.tab_widget._select_playback(self.playback_key)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        # Re-polish so Qt reapplies QSS for the new property value.
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class PlaybacksTab(BaseTab):
    """Tab for browsing playback definitions from session."""
    
    # Signal emitted when playback data changes
    data_changed = pyqtSignal()
    
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.session_data: Optional[Dict[str, Any]] = None
        self.playbacks: List[tuple[str, Dict[str, Any]]] = []  # List of (key, data) tuples
        self.view_mode: str = "grid"  # "grid" or "list"
        self._selected_playback_key: Optional[str] = None
        self._card_widgets_by_key: dict[str, PlaybackCard] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the playbacks tab UI."""
        # Local QSS: keep card selection subtle and consistent with the app theme.
        # Uses the same accent color already present across the app.
        self.setStyleSheet(
            "PlaybackCard {"
            "  background-color: #252526;"
            "  border: 1px solid #3c3c3c;"
            "  border-radius: 6px;"
            "}"
            "PlaybackCard[selected=\"true\"] {"
            "  border-left: 3px solid #FF8A00;"
            "  border-top: 1px solid #3c3c3c;"
            "  border-right: 1px solid #3c3c3c;"
            "  border-bottom: 1px solid #3c3c3c;"
            "  background-color: #1e1e1e;"
            "}"
            "PlaybackCard:hover {"
            "  border-color: #555555;"
            "}"
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
        
        # === HEADER: Title + View Toggle + New Button ===
        header_layout = QHBoxLayout()
        
        title = QLabel("🎨 Playbacks")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # View mode toggle
        view_label = QLabel("View:")
        header_layout.addWidget(view_label)
        
        self.radio_grid = QRadioButton("Grid")
        self.radio_grid.setChecked(True)
        self.radio_grid.toggled.connect(self._on_view_mode_changed)
        header_layout.addWidget(self.radio_grid)
        
        self.radio_list = QRadioButton("List")
        self.radio_list.toggled.connect(self._on_view_mode_changed)
        header_layout.addWidget(self.radio_list)
        
        header_layout.addSpacing(20)
        
        btn_new = QPushButton("➕ New Playback")
        btn_new.clicked.connect(self._on_new_playback)
        header_layout.addWidget(btn_new)

        btn_delete = QPushButton("🗑️ Delete Playback")
        btn_delete.clicked.connect(self._on_delete_selected_playback)
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
        self.search_box.setPlaceholderText("Filter by name, description, spiral type...")
        self.search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_box)
        
        layout.addLayout(search_layout)
        
        # === CONTENT: Grid or List ===
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Grid view
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(12)
        
        self.grid_scroll.setWidget(self.grid_container)
        self.content_layout.addWidget(self.grid_scroll)
        
        # Table view
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Name", "Description", "Spiral Type", "Media Mode", "Actions"
        ])

        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_table_double_click)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 170)

        # Center the list/table view so rows don't become a full-width "long bar".
        self.table.setMaximumWidth(1200)
        self.table_container = QWidget()
        table_container_layout = QHBoxLayout(self.table_container)
        table_container_layout.setContentsMargins(0, 0, 0, 0)
        table_container_layout.setSpacing(0)
        table_container_layout.addStretch(1)
        table_container_layout.addWidget(self.table, 10)
        table_container_layout.addStretch(1)

        self.content_layout.addWidget(self.table_container)
        self.table_container.hide()  # Start with grid view
        
        layout.addWidget(self.content_widget, 1)
        
        # === FOOTER: Status ===
        self.status_label = QLabel("No playbacks found")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Load playbacks on init
        self._load_playbacks()
        
        self.logger.info("PlaybacksTab initialized")
    
    def set_session_data(self, session_data: Dict[str, Any]):
        """Set session data and reload playbacks.
        
        Args:
            session_data: Reference to session dictionary
        """
        self.session_data = session_data
        self._load_playbacks()
        self.logger.info(f"Session data set: {len(self.playbacks)} playbacks")
    
    def _load_playbacks(self):
        """Load playbacks from session data."""
        try:
            self.playbacks = []
            
            if self.session_data is None:
                self.logger.warning("No session data available")
                self.status_label.setText("No session loaded")
                self._update_view()
                return
            
            playbacks_dict = self.session_data.get("playbacks", {})
            
            # Convert dict to list of (key, data) tuples
            for key, data in playbacks_dict.items():
                # Add key to data for reference
                data_with_key = data.copy()
                data_with_key["_key"] = key
                self.playbacks.append((key, data_with_key))
            
            # Sort by name
            self.playbacks.sort(key=lambda x: x[1].get("name", "").lower())
            
            # Update view
            self._update_view()
            
            # Update status
            self.status_label.setText(f"Found {len(self.playbacks)} playback(s)")
            self.logger.info(f"Loaded {len(self.playbacks)} playbacks")
            
        except Exception as e:
            self.logger.error(f"Failed to load playbacks: {e}", exc_info=True)
            self.status_label.setText("Error loading playbacks")
    
    def _update_view(self, filter_text: str = ""):
        """Update the current view (grid or list)."""
        if self.view_mode == "grid":
            self._update_grid(filter_text)
        else:
            self._update_table(filter_text)
    
    def _update_grid(self, filter_text: str = ""):
        """Update grid view with playback cards."""
        self._card_widgets_by_key = {}

        # Clear existing cards
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Filter playbacks
        filtered = self.playbacks
        if filter_text:
            filter_lower = filter_text.lower()
            filtered = [
                (key, data) for key, data in self.playbacks
                if filter_lower in data.get("name", "").lower() or
                   filter_lower in data.get("description", "").lower() or
                   filter_lower in str(data.get("spiral", {}).get("type", "")).lower()
            ]
        
        # Add cards (4 per row)
        row = 0
        col = 0
        for key, data in filtered:
            card = PlaybackCard(key, data, self, self)
            card.set_selected(bool(self._selected_playback_key == key))
            self._card_widgets_by_key[key] = card
            self.grid_layout.addWidget(card, row, col)
            
            col += 1
            if col >= 4:
                col = 0
                row += 1
        
        # Add stretch to push cards to top
        self.grid_layout.setRowStretch(row + 1, 1)
    
    def _update_table(self, filter_text: str = ""):
        """Update table view with playback data."""
        self.table.setRowCount(0)
        
        # Filter playbacks
        filtered = self.playbacks
        if filter_text:
            filter_lower = filter_text.lower()
            filtered = [
                (key, data) for key, data in self.playbacks
                if filter_lower in data.get("name", "").lower() or
                   filter_lower in data.get("description", "").lower() or
                   filter_lower in str(data.get("spiral", {}).get("type", "")).lower()
            ]
        
        # Populate table
        for key, data in filtered:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Store key in row data
            self.table.setItem(row, 0, QTableWidgetItem(key))  # Hidden column for key
            
            # Name
            name_item = QTableWidgetItem(data.get("name", "Unnamed"))
            self.table.setItem(row, 0, name_item)
            
            # Description
            desc_item = QTableWidgetItem(data.get("description", ""))
            self.table.setItem(row, 1, desc_item)
            
            # Spiral Type
            spiral = data.get("spiral", {})
            spiral_type = spiral.get("type", "logarithmic")
            if isinstance(spiral_type, int):
                type_names = ["logarithmic", "archimedean", "fermat", "hyperbolic"]
                spiral_type = type_names[spiral_type] if 0 <= spiral_type < 4 else f"type_{spiral_type}"
            
            type_item = QTableWidgetItem(str(spiral_type))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, type_item)
            
            # Media Mode
            media_mode = data.get("media", {}).get("mode", "none")
            media_item = QTableWidgetItem(str(media_mode))
            media_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, media_item)
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(8)

            actions_layout.addStretch(1)

            btn_edit = QPushButton("Edit")
            btn_edit.setFixedWidth(52)
            btn_edit.clicked.connect(lambda _checked=False, k=key, d=data: self._on_card_double_click(k, d))
            actions_layout.addWidget(btn_edit)

            btn_delete = QPushButton("Delete")
            btn_delete.setFixedWidth(62)
            btn_delete.clicked.connect(lambda _checked=False, k=key: self._delete_playback(k))
            actions_layout.addWidget(btn_delete)

            actions_layout.addStretch(1)
            self.table.setCellWidget(row, 4, actions_widget)
    
    def _on_view_mode_changed(self, checked: bool):
        """Handle view mode toggle."""
        if not checked:
            return
        
        if self.radio_grid.isChecked():
            self.view_mode = "grid"
            self.grid_scroll.show()
            self.table_container.hide()
        else:
            self.view_mode = "list"
            self.grid_scroll.hide()
            self.table_container.show()
        
        # Update view
        self._update_view(self.search_box.text())
        self.logger.debug(f"View mode changed to: {self.view_mode}")
    
    def _on_search_changed(self, text: str):
        """Handle search box text change."""
        self._update_view(filter_text=text)
    
    def _on_refresh(self):
        """Refresh playback list."""
        self._load_playbacks()

    def _on_table_selection_changed(self) -> None:
        if self.view_mode != "list":
            return
        key = self._get_selected_playback_key_from_table()
        if key:
            self._selected_playback_key = key

    def _get_selected_playback_key_from_table(self) -> Optional[str]:
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        filter_text = self.search_box.text().lower()
        filtered = self.playbacks
        if filter_text:
            filtered = [
                (key, data) for key, data in self.playbacks
                if filter_text in data.get("name", "").lower() or
                   filter_text in data.get("description", "").lower() or
                   filter_text in str(data.get("spiral", {}).get("type", "")).lower()
            ]

        if current_row >= len(filtered):
            return None
        key, _data = filtered[current_row]
        return key

    def _select_playback(self, playback_key: str) -> None:
        self._selected_playback_key = playback_key
        for key, card in self._card_widgets_by_key.items():
            card.set_selected(bool(key == playback_key))

    def _on_delete_selected_playback(self) -> None:
        key = None
        if self.view_mode == "list":
            key = self._get_selected_playback_key_from_table()
        else:
            key = self._selected_playback_key

        if not key:
            QMessageBox.information(self, "Delete Playback", "Select a playback to delete.")
            return

        self._delete_playback(key)

    def _count_playback_references(self, playback_key: str) -> int:
        if not self.session_data:
            return 0
        cuelists = self.session_data.get("cuelists", {})
        if not isinstance(cuelists, dict):
            return 0

        refs = 0
        for _cuelist_key, cuelist_data in cuelists.items():
            if not isinstance(cuelist_data, dict):
                continue
            for cue in cuelist_data.get("cues", []) or []:
                if not isinstance(cue, dict):
                    continue
                pool = cue.get("playback_pool", []) or []
                for entry in pool:
                    if isinstance(entry, dict) and entry.get("playback") == playback_key:
                        refs += 1
        return refs

    def _delete_playback(self, playback_key: str) -> bool:
        if not self.session_data:
            QMessageBox.warning(self, "Delete Playback", "No session loaded.")
            return False

        playbacks = self.session_data.get("playbacks")
        if not isinstance(playbacks, dict) or playback_key not in playbacks:
            QMessageBox.warning(self, "Delete Playback", f"Playback '{playback_key}' not found in session.")
            return False

        ref_count = self._count_playback_references(playback_key)
        if ref_count > 0:
            QMessageBox.warning(
                self,
                "Delete Playback",
                f"Cannot delete '{playback_key}' because it is referenced by {ref_count} cue entry(ies).\n\n"
                f"Remove it from cuelists first, then delete.",
            )
            return False

        name = playbacks.get(playback_key, {}).get("name", playback_key)
        reply = QMessageBox.question(
            self,
            "Delete Playback",
            f"Delete playback '{name}'?\n\nThis will remove it from the current session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        try:
            del playbacks[playback_key]
            if self._selected_playback_key == playback_key:
                self._selected_playback_key = None
            self._load_playbacks()
            self.data_changed.emit()
            return True
        except Exception as exc:
            self.logger.error("Failed to delete playback %s: %s", playback_key, exc, exc_info=True)
            QMessageBox.critical(self, "Delete Playback", f"Failed to delete playback:\n{exc}")
            return False
    
    def _on_new_playback(self):
        """Create a new playback."""
        # TODO: Update PlaybackEditor to support session mode
        # For now, check if session is available
        if not self.session_data:
            self.logger.warning("Cannot create playback: no session loaded")
            return
        
        # Open editor in session mode (pass session reference and None for key = new)
        editor = PlaybackEditor(session_data=self.session_data, playback_key=None, parent=self)
        editor.saved.connect(self._on_playback_saved)
        editor.exec()
        self.logger.info("Playback editor closed (new)")
    
    def _on_card_double_click(self, playback_key: str, playback_data: Dict[str, Any]):
        """Handle double-click on playback card."""
        if not self.session_data:
            self.logger.warning("Cannot edit playback: no session loaded")
            return
        
        # Open playback editor in session mode
        editor = PlaybackEditor(session_data=self.session_data, playback_key=playback_key, parent=self)
        editor.saved.connect(self._on_playback_saved)
        editor.exec()
        self.logger.info(f"Playback editor closed: {playback_data.get('name')}")
    
    def _on_table_double_click(self):
        """Handle double-click on table row."""
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        
        # Get search filter
        filter_text = self.search_box.text().lower()
        
        # Get filtered playbacks
        filtered = self.playbacks
        if filter_text:
            filtered = [
                (key, data) for key, data in self.playbacks
                if filter_text in data.get("name", "").lower() or
                   filter_text in data.get("description", "").lower() or
                   filter_text in str(data.get("spiral", {}).get("type", "")).lower()
            ]
        
        if current_row >= len(filtered):
            return
        
        key, data = filtered[current_row]
        self._on_card_double_click(key, data)
    
    def _on_playback_saved(self):
        """Handle playback saved from editor."""
        # Reload playbacks from session and emit change signal
        self._load_playbacks()
        self.data_changed.emit()
        self.logger.debug("Playback saved, session marked dirty")
    
    def on_show(self):
        """Called when tab becomes visible."""
        self.logger.debug("PlaybacksTab shown")
        # Refresh playbacks when tab is shown
        self._load_playbacks()
    
    def on_hide(self):
        """Called when tab becomes hidden."""
        self.logger.debug("PlaybacksTab hidden")
