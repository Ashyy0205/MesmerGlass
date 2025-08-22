"""MessagePackEditor dialog (clean, single implementation).

Provides minimal creation of a message pack with two columns: Message | Weight.
The removed Mode column and pulse stages are intentionally omitted per recent
requirements. Weight is a positive float; fallback to 1 if invalid.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox, QFileDialog,
    QHeaderView
)
import json
from typing import List

from ...content.models import TextItem, SessionPack, build_session_pack


class MessagePackEditor(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Message Pack")
        self.resize(620, 380)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Name field -------------------------------------------------------
        row = QWidget(); rl = QHBoxLayout(row); rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)
        rl.addWidget(QLabel("Name:"))
        self.edit_name = QLineEdit(); self.edit_name.setPlaceholderText("Pack name")
        rl.addWidget(self.edit_name, 1)
        root.addWidget(row)

        # Table ------------------------------------------------------------
        root.addWidget(QLabel("Messages (weighted random)"))
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Message", "Weight"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tbl.setColumnWidth(1, 80)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        root.addWidget(self.tbl, 1)

        # Row buttons ------------------------------------------------------
        row_btns = QWidget(); hb = QHBoxLayout(row_btns); hb.setContentsMargins(0,0,0,0); hb.setSpacing(6)
        self.btn_add = QPushButton("Add Message")
        self.btn_del = QPushButton("Remove")
        self.btn_up = QPushButton("Up")
        self.btn_down = QPushButton("Down")
        for b in (self.btn_add, self.btn_del, self.btn_up, self.btn_down): hb.addWidget(b)
        hb.addStretch(1); root.addWidget(row_btns)

        # Actions ----------------------------------------------------------
        actions = QWidget(); ah = QHBoxLayout(actions); ah.setContentsMargins(0,0,0,0); ah.setSpacing(8)
        self.btn_save = QPushButton("Save To File…"); ah.addWidget(self.btn_save); ah.addStretch(1)
        self.btn_cancel = QPushButton("Cancel"); self.btn_apply = QPushButton("Apply & Close")
        ah.addWidget(self.btn_cancel); ah.addWidget(self.btn_apply); root.addWidget(actions)

        # Signals ----------------------------------------------------------
        self.btn_add.clicked.connect(self._add_row)
        self.btn_del.clicked.connect(self._del_rows)
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(1))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_save.clicked.connect(self._on_save_file)

    # -------------------------- row ops ----------------------------------
    def _add_row(self):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, QTableWidgetItem("New Message"))
        self.tbl.setItem(r, 1, QTableWidgetItem("1"))

    def _del_rows(self):
        rows = {i.row() for i in self.tbl.selectedIndexes()}
        for r in sorted(rows, reverse=True): self.tbl.removeRow(r)

    def _move_selected(self, delta: int):
        sel = self.tbl.currentRow()
        if sel < 0: return
        new = sel + delta
        if not (0 <= new < self.tbl.rowCount()): return
        for c in range(self.tbl.columnCount()):
            a = self.tbl.takeItem(sel, c); b = self.tbl.takeItem(new, c)
            self.tbl.setItem(sel, c, b); self.tbl.setItem(new, c, a)
        self.tbl.setCurrentCell(new, 0)

    # ------------------------ pack build/save ----------------------------
    def _build_pack(self) -> SessionPack:
        name = self.edit_name.text().strip() or "Untitled Pack"
        items: List[TextItem] = []
        for r in range(self.tbl.rowCount()):
            msg = (self.tbl.item(r,0).text() if self.tbl.item(r,0) else "").strip()
            raw_w = (self.tbl.item(r,1).text() if self.tbl.item(r,1) else "1").strip() or "1"
            try: w = float(raw_w)
            except Exception: w = -1.0  # mark invalid -> validator will coerce later
            items.append(TextItem(msg=msg, weight=w))
        data = {
            "version": 1,
            "name": name,
            "text": {"items": [
                {k: v for k, v in {"msg": t.msg, "weight": t.weight}.items() if v is not None}
                for t in items
            ]},
            "pulse": {"stages": []}
        }
        return build_session_pack(data)

    def _on_apply(self):
        try: pack = self._build_pack()
        except Exception as e: QMessageBox.critical(self, "Invalid Pack", str(e)); return
        self.result_pack = pack  # type: ignore[attr-defined]
        self.accept()

    def _on_save_file(self):
        try: pack = self._build_pack()
        except Exception as e: QMessageBox.critical(self, "Invalid Pack", str(e)); return
        fn, _ = QFileDialog.getSaveFileName(self, "Save Message Pack", "message_pack.json", "Message Packs (*.json);;All Files (*.*)")
        if not fn: return
        try:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(pack.to_canonical_dict(), f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Saved", f"Saved to {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
