from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QSlider, QHBoxLayout, QWidget as QW,
    QPushButton
)
from ..widgets import ToggleSwitch, UnitSpin


# ---------- tiny helpers ----------
def _card(title: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setContentsMargins(0, 0, 0, 0)
    return box

def _row(label: str, widget: QW, trailing: QW | None = None) -> QW:
    w = QW()
    h = QHBoxLayout(w)
    h.setContentsMargins(10, 6, 10, 6)
    h.setSpacing(10)
    lab = QLabel(label); lab.setMinimumWidth(160)
    h.addWidget(lab, 0); h.addWidget(widget, 1)
    if trailing: h.addWidget(trailing, 0)
    return w

def _toggle_line(text: str, tip: str, checked: bool) -> tuple[ToggleSwitch, QW]:
    row = QW()
    h = QHBoxLayout(row); h.setContentsMargins(10, 6, 10, 6); h.setSpacing(10)
    sw = ToggleSwitch(checked)
    lab = QLabel(text); lab.setToolTip(tip)
    h.addWidget(sw, 0); h.addWidget(lab, 0); h.addStretch(1)
    return sw, row

def _pct_label(v: int) -> QLabel:
    lab = QLabel(f"{int(v)}%")
    lab.setMinimumWidth(48)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lab


# ---------- page ----------
class DevicePage(QWidget):
    # signals to launcher
    enableSyncChanged   = pyqtSignal(bool)
    buzzOnFlashChanged  = pyqtSignal(bool)
    buzzIntensityChanged = pyqtSignal(int)      # 0..100
    burstsEnableChanged = pyqtSignal(bool)
    burstMinChanged     = pyqtSignal(int)       # seconds
    burstMaxChanged     = pyqtSignal(int)       # seconds
    burstPeakChanged    = pyqtSignal(int)       # 0..100
    burstMaxMsChanged   = pyqtSignal(int)

    def __init__(
        self,
        *,
        enable_sync: bool,
        buzz_on_flash: bool,
        buzz_intensity_pct: int,
        bursts_enable: bool,
        min_gap_s: int,
        max_gap_s: int,
        peak_pct: int,
        max_ms: int,
        parent=None,
    ):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(12)  # visible gap between bubbles

        # 1) Master bubble
        card_enable = _card("Device sync")
        cv = QVBoxLayout(card_enable); cv.setContentsMargins(12, 8, 12, 8); cv.setSpacing(4)
        self.sw_enable, row_en = _toggle_line(
            "Enable device sync (Buttplug)",
            "Connect to Intiface/Buttplug at ws://127.0.0.1:12345 and drive toys.",
            enable_sync,
        )
        cv.addWidget(row_en)
        root.addWidget(card_enable)

        # 2) Buzz-on-flash bubble (toggle + intensity on separate lines)
        card_buzz = _card("Buzz on flash")
        bv = QVBoxLayout(card_buzz); bv.setContentsMargins(12, 8, 12, 8); bv.setSpacing(4)
        self.sw_buzz, row_bz = _toggle_line(
            "Buzz when the text flashes",
            "Vibrate briefly each time the flash text appears.",
            buzz_on_flash,
        )
        bv.addWidget(row_bz)

        self.sld_buzz = QSlider(Qt.Orientation.Horizontal); self.sld_buzz.setRange(0, 100); self.sld_buzz.setValue(buzz_intensity_pct)
        self.lab_buzz = _pct_label(self.sld_buzz.value())
        bv.addWidget(_row("Intensity", self.sld_buzz, self.lab_buzz))
        root.addWidget(card_buzz)

        # 3) Random bursts bubble (toggle + its fields stacked)
        card_bursts = _card("Random bursts")
        rv = QVBoxLayout(card_bursts); rv.setContentsMargins(12, 8, 12, 8); rv.setSpacing(4)
        self.sw_bursts, row_rb = _toggle_line(
            "Enable random high-intensity bursts",
            "Inject short patterns at random intervals while running.",
            bursts_enable,
        )
        rv.addWidget(row_rb)

        self.spin_min = UnitSpin(5, 300, min_gap_s, "s", step=1,
                                 tooltip="Minimum time between bursts.", width=140)
        rv.addWidget(_row("Minimum gap", self.spin_min))

        self.spin_max = UnitSpin(6, 600, max_gap_s, "s", step=1,
                                 tooltip="Maximum time between bursts.", width=140)
        rv.addWidget(_row("Maximum gap", self.spin_max))

        self.sld_peak = QSlider(Qt.Orientation.Horizontal); self.sld_peak.setRange(10, 100); self.sld_peak.setValue(peak_pct)
        self.lab_peak = _pct_label(self.sld_peak.value())
        rv.addWidget(_row("Peak level", self.sld_peak, self.lab_peak))

        self.spin_max_ms = UnitSpin(200, 8000, max_ms, "ms", step=50,
                                    tooltip="Maximum duration per burst envelope.", width=160)
        rv.addWidget(_row("Burst max duration", self.spin_max_ms))
        root.addWidget(card_bursts)

        root.addStretch(1)

        # wiring
        self.sw_enable.toggled.connect(self.enableSyncChanged.emit)
        self.sw_buzz.toggled.connect(self.buzzOnFlashChanged.emit)
        self.sld_buzz.valueChanged.connect(self._on_buzz_int)
        self.sw_bursts.toggled.connect(self.burstsEnableChanged.emit)
        self.spin_min.valueChanged.connect(self.burstMinChanged.emit)
        self.spin_max.valueChanged.connect(self.burstMaxChanged.emit)
        self.sld_peak.valueChanged.connect(self._on_peak)
        self.spin_max_ms.valueChanged.connect(self.burstMaxMsChanged.emit)

        # reflect toggle enablement
        self._apply_enabled_states()

        self.sw_enable.toggled.connect(lambda _: self._apply_enabled_states())
        self.sw_buzz.toggled.connect(lambda _: self._apply_enabled_states())
        self.sw_bursts.toggled.connect(lambda _: self._apply_enabled_states())

    # --- slots ---
    def _on_buzz_int(self, v: int):
        self.lab_buzz.setText(f"{v}%")
        self.buzzIntensityChanged.emit(v)

    def _on_peak(self, v: int):
        self.lab_peak.setText(f"{v}%")
        self.burstPeakChanged.emit(v)

    # --- ui logic ---
    def _apply_enabled_states(self):
        buzz_enabled = self.sw_enable.isChecked() and self.sw_buzz.isChecked()
        self.sld_buzz.setEnabled(buzz_enabled)

        bursts_enabled = self.sw_enable.isChecked() and self.sw_bursts.isChecked()
        for w in (self.spin_min, self.spin_max, self.sld_peak, self.spin_max_ms):
            w.setEnabled(bursts_enabled)
