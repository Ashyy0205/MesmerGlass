from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QSlider,
    QComboBox, QGroupBox, QHBoxLayout
)
from ..widgets import UnitSpin


def _card(title: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setContentsMargins(0, 0, 0, 0)
    return box


def _row(label: str, widget: QWidget, value_label: QLabel | None = None) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(8, 6, 8, 6)
    h.setSpacing(10)
    lab = QLabel(label)
    lab.setMinimumWidth(160)
    h.addWidget(lab, 0)
    h.addWidget(widget, 1)
    if value_label:
        value_label.setMinimumWidth(48)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(value_label, 0)
    return w


def _pct_label(v: int) -> QLabel:
    lab = QLabel(f"{int(v)}%")
    return lab


class TextFxPage(QWidget):
    # signals to launcher
    textChanged = pyqtSignal(str)
    fontRequested = pyqtSignal()
    colorRequested = pyqtSignal()
    textScaleChanged = pyqtSignal(int)
    fxModeChanged = pyqtSignal(str)
    fxIntensityChanged = pyqtSignal(int)
    flashIntervalChanged = pyqtSignal(int)
    flashWidthChanged = pyqtSignal(int)

    def __init__(
        self,
        *,
        text: str,
        text_scale_pct: int,
        fx_mode: str,
        fx_intensity: int,
        flash_interval_ms: int,
        flash_width_ms: int,
        parent=None,
    ):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(10)

        # --- Text card ---
        card_text = _card("Text & FX")
        cv = QVBoxLayout(card_text)
        cv.setContentsMargins(12, 10, 12, 12)
        cv.setSpacing(4)

        # Message (single line)
        self.ed_text = QLineEdit(text)
        self.ed_text.setToolTip("Message that flashes on screen.")
        cv.addWidget(_row("Message", self.ed_text))

        # Font (one line)
        self.btn_font = QPushButton("Choose font…")
        self.btn_font.setToolTip("Pick font for the message text.")
        cv.addWidget(_row("Font", self.btn_font))

        # Color (one line)
        self.btn_color = QPushButton("Choose color…")
        self.btn_color.setToolTip("Pick the text color.")
        cv.addWidget(_row("Color", self.btn_color))

        # Size slider (one line)
        self.sld_txt_scale = QSlider(Qt.Orientation.Horizontal)
        self.sld_txt_scale.setRange(8, 60)
        self.sld_txt_scale.setValue(int(text_scale_pct))
        self.sld_txt_scale.setToolTip("Text size as % of screen height.")
        self.lab_txt_scale = _pct_label(self.sld_txt_scale.value())
        cv.addWidget(_row("Size (% of screen height)", self.sld_txt_scale, self.lab_txt_scale))

        # FX combobox (one line)
        self.cmb_fx = QComboBox()
        self.cmb_fx.addItems(["Breath + Sway", "Shimmer", "Tunnel", "Subtle"])
        self.cmb_fx.setCurrentText(fx_mode)
        self.cmb_fx.setToolTip("Animation style for the text.")
        cv.addWidget(_row("FX style", self.cmb_fx))

        # FX intensity (one line)
        self.sld_fx_int = QSlider(Qt.Orientation.Horizontal)
        self.sld_fx_int.setRange(0, 100)
        self.sld_fx_int.setValue(int(fx_intensity))
        self.sld_fx_int.setToolTip("How strongly the animation is applied.")
        self.lab_fx_pct = _pct_label(self.sld_fx_int.value())
        cv.addWidget(_row("FX intensity", self.sld_fx_int, self.lab_fx_pct))

        root.addWidget(card_text)

        # --- Flash card (each setting on its own line) ---
        card_flash = _card("Flash")
        fv = QVBoxLayout(card_flash)
        fv.setContentsMargins(12, 10, 12, 12)
        fv.setSpacing(4)

        self.spin_interval = UnitSpin(
            200, 10000, flash_interval_ms, "ms", step=50,
            tooltip="Time between flashes; if device sync is on, the toy will buzz at this cadence.",
            width=160
        )
        fv.addWidget(_row("Interval", self.spin_interval))

        self.spin_width = UnitSpin(
            50, 3000, flash_width_ms, "ms", step=25,
            tooltip="How long each flash stays visible.",
            width=160
        )
        fv.addWidget(_row("Width", self.spin_width))

        root.addWidget(card_flash)
        root.addStretch(1)

        # wire signals
        self.ed_text.textChanged.connect(self.textChanged.emit)
        self.btn_font.clicked.connect(self.fontRequested.emit)
        self.btn_color.clicked.connect(self.colorRequested.emit)
        self.sld_txt_scale.valueChanged.connect(self._on_txt_scale)
        self.cmb_fx.currentTextChanged.connect(self.fxModeChanged.emit)
        self.sld_fx_int.valueChanged.connect(self._on_fx_int)
        self.spin_interval.valueChanged.connect(self.flashIntervalChanged.emit)
        self.spin_width.valueChanged.connect(self.flashWidthChanged.emit)

    # slots
    def _on_txt_scale(self, v: int):
        self.lab_txt_scale.setText(f"{v}%")
        self.textScaleChanged.emit(v)

    def _on_fx_int(self, v: int):
        self.lab_fx_pct.setText(f"{v}%")
        self.fxIntensityChanged.emit(v)
