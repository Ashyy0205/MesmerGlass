from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QSlider, QPushButton, QHBoxLayout
)


# --- small helpers (page-local) ---
def _card(title: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setContentsMargins(0, 0, 0, 0)
    return box

def _row(label: str, widget: QWidget, trailing: QWidget | None = None) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(10, 6, 10, 6)
    h.setSpacing(10)
    lab = QLabel(label); lab.setMinimumWidth(160)
    h.addWidget(lab, 0)
    h.addWidget(widget, 1)
    if trailing:
        h.addWidget(trailing, 0)
    return w

def _pct_label(pct: int) -> QLabel:
    lab = QLabel(f"{pct}%")
    lab.setMinimumWidth(48)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lab


class AudioPage(QWidget):
    """
    Two ‘bubbles’:
      - Primary audio: File … / Volume (%)
      - Secondary audio: File … / Volume (%)

    The page only *requests* loads; the launcher handles file dialogs and audio engine.
    """
    # tell the launcher to open a file dialog
    load1Requested = pyqtSignal()
    load2Requested = pyqtSignal()
    # sliders -> launcher (0..100)
    vol1Changed = pyqtSignal(int)
    vol2Changed = pyqtSignal(int)

    def __init__(self,
                 *,
                 file1: str,
                 file2: str,
                 vol1_pct: int,
                 vol2_pct: int,
                 parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(12)

        # --- Primary bubble ---
        card1 = _card("Primary audio")
        c1 = QVBoxLayout(card1); c1.setContentsMargins(12, 8, 12, 8); c1.setSpacing(4)

        self.lbl1 = QLabel(file1 or "(none)")
        btn1 = QPushButton("Load…"); btn1.setToolTip("Choose a music/ambience track (streams if large).")
        btn1.clicked.connect(self.load1Requested.emit)
        c1.addWidget(_row("File", btn1, self.lbl1))

        self.sld1 = QSlider(Qt.Orientation.Horizontal); self.sld1.setRange(0, 100); self.sld1.setValue(vol1_pct)
        self.lab1 = _pct_label(self.sld1.value())
        self.sld1.setToolTip("Primary audio volume.")
        self.sld1.valueChanged.connect(self._on_vol1)
        c1.addWidget(_row("Volume", self.sld1, self.lab1))

        root.addWidget(card1)

        # --- Secondary bubble ---
        card2 = _card("Secondary audio")
        c2 = QVBoxLayout(card2); c2.setContentsMargins(12, 8, 12, 8); c2.setSpacing(4)

        self.lbl2 = QLabel(file2 or "(none)")
        btn2 = QPushButton("Load…"); btn2.setToolTip("Choose a short loop/overlay.")
        btn2.clicked.connect(self.load2Requested.emit)
        c2.addWidget(_row("File", btn2, self.lbl2))

        self.sld2 = QSlider(Qt.Orientation.Horizontal); self.sld2.setRange(0, 100); self.sld2.setValue(vol2_pct)
        self.lab2 = _pct_label(self.sld2.value())
        self.sld2.setToolTip("Secondary audio volume.")
        self.sld2.valueChanged.connect(self._on_vol2)
        c2.addWidget(_row("Volume", self.sld2, self.lab2))

        root.addWidget(card2)
        root.addStretch(1)

    # ----- slots / helpers -----
    def _on_vol1(self, v: int):
        self.lab1.setText(f"{v}%")
        self.vol1Changed.emit(v)

    def _on_vol2(self, v: int):
        self.lab2.setText(f"{v}%")
        self.vol2Changed.emit(v)

    # called by launcher after a successful pick
    def set_file1_label(self, name: str):
        self.lbl1.setText(name or "(none)")

    def set_file2_label(self, name: str):
        self.lbl2.setText(name or "(none)")

    def set_vols(self, v1_pct: int | None = None, v2_pct: int | None = None):
        if v1_pct is not None:
            self.sld1.blockSignals(True)
            self.sld1.setValue(v1_pct)
            self.lab1.setText(f"{v1_pct}%")
            self.sld1.blockSignals(False)
        if v2_pct is not None:
            self.sld2.blockSignals(True)
            self.sld2.setValue(v2_pct)
            self.lab2.setText(f"{v2_pct}%")
            self.sld2.blockSignals(False)
