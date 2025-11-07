"""
Text Tab - Message Library Management.

This tab only manages the message library:
- Add new messages
- Edit existing messages  
- Remove messages

All other text settings (opacity, timing, display mode, positioning, etc.)
are controlled by JSON mode files via the MesmerLoom tab.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QScrollArea, QListWidget, QListWidgetItem, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..engine.text_director import TextDirector


class TextTab(QWidget):
    """
    Text Tab - Manages message library only (add/edit/remove).
    
    All other text settings (opacity, timing, mode, positioning) are controlled
    by JSON mode files loaded via MesmerLoom tab.
    """
    
    def __init__(self, text_director: Optional[TextDirector] = None, parent=None):
        super().__init__(parent)
        self.text_director = text_director
        self.logger = logging.getLogger(__name__)
        self._texts = []  # Message library

        self._setup_ui()
        self._load_default_texts()
    
    def _setup_ui(self):
        """Create UI layout - message library management only."""
        layout = QVBoxLayout(self)

        # Info banner
        info = QLabel(
            "📝 Message Library\n\n"
            "Add, edit, and remove text messages that appear in the overlay.\n\n"
            "All other text settings (opacity, timing, display mode, positioning, fonts) "
            "are controlled by JSON mode files in the MesmerLoom tab."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #888; font-size: 11px; padding: 10px; "
            "background: #2a2a2a; border-radius: 5px; border-left: 3px solid #4a9eff;"
        )
        layout.addWidget(info)

        # === Text Library (messages only) ===
        library_group = QGroupBox("Messages")
        library_layout = QVBoxLayout(library_group)

        # Actions: Add / Edit / Remove
        actions = QHBoxLayout()
        btn_add = QPushButton("Add…"); btn_edit = QPushButton("Edit…"); btn_del = QPushButton("Remove")
        btn_add.clicked.connect(self._on_add)
        btn_edit.clicked.connect(self._on_edit)
        btn_del.clicked.connect(self._on_remove)
        actions.addWidget(btn_add); actions.addWidget(btn_edit); actions.addWidget(btn_del); actions.addStretch()
        library_layout.addLayout(actions)

        # Scrollable list of messages
        self.list = QListWidget()
        self.list.setSelectionMode(self.list.SelectionMode.SingleSelection)
        self.list.setMinimumHeight(300)
        library_layout.addWidget(self.list, 1)

        layout.addWidget(library_group, 1)  # Expand to fill space
    
    def _load_default_texts(self):
        """Load default text library."""
        default_texts = [
            "Obey",
            "Submit",
            "Good toy",
            "Mindless",
            "Empty",
            "Blank",
            "Compliant",
            "Docile",
            "Entranced",
            "Drop deeper",
            "Drift down",
            "Let go",
            "Watch the spiral",
            "Focus on my words",
            "You are hypnotized",
            "Deeper and deeper",
            "Sleep",
            "Relax",
            "No thoughts",
            "Just watch",
        ]
        
        self.set_text_library(default_texts)
    
    def set_text_library(self, texts: list[str]):
        """Replace the message list with provided texts."""
        self._texts = list(texts)
        self.list.clear()
        for t in self._texts:
            self.list.addItem(QListWidgetItem(t))
        if self.text_director:
            self.text_director.set_text_library(self._texts, default_split_mode=None, user_set=True)
            self.text_director.set_enabled(True)
        self.logger.info(f"[TextTab] Loaded {len(self._texts)} texts")
    
    # --- message actions ---
    def _on_add(self):
        text, ok = QInputDialog.getText(self, "Add Message", "Message text:")
        if not ok or not text.strip():
            return
        self._texts.append(text.strip())
        self.list.addItem(QListWidgetItem(text.strip()))
        if self.text_director:
            self.text_director.set_text_library(self._texts, default_split_mode=None, user_set=True)
            self.text_director.set_enabled(True)

    def _on_edit(self):
        item = self.list.currentItem()
        if not item:
            return
        current = item.text()
        text, ok = QInputDialog.getText(self, "Edit Message", "Message text:", text=current)
        if not ok or not text.strip():
            return
        new_text = text.strip()
        idx = self.list.currentRow()
        self._texts[idx] = new_text
        item.setText(new_text)
        if self.text_director:
            self.text_director.set_text_library(self._texts, default_split_mode=None, user_set=True)
            self.text_director.set_enabled(True)

    def _on_remove(self):
        row = self.list.currentRow()
        if row < 0:
            return
        self._texts.pop(row)
        self.list.takeItem(row)
        if self.text_director:
            self.text_director.set_text_library(self._texts, default_split_mode=None, user_set=True)
            self.text_director.set_enabled(True)
    
    def set_text_director(self, text_director: TextDirector):
        """Set text director instance.
        
        Args:
            text_director: TextDirector to control
        """
        self.text_director = text_director
