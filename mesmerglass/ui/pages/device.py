from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QSlider, QHBoxLayout, QWidget as QW,
    QPushButton, QDialog
)
from ..widgets import ToggleSwitch, UnitSpin
from ..dialogs.device_selection import DeviceSelectionDialog
from ...engine.device_manager import DeviceList


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
    scanDevicesRequested = pyqtSignal()         # Request device scan
    deviceSelected      = pyqtSignal(int)       # Device index selected
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
        self._current_device_list = None  # Track available devices

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(12)  # visible gap between bubbles

        # 1) Master bubble
        card_enable = _card("Device sync")
        cv = QVBoxLayout(card_enable); cv.setContentsMargins(12, 8, 12, 8); cv.setSpacing(4)
        
        # Connection toggle
        self.sw_enable, row_en = _toggle_line(
            "Enable device sync (Buttplug)",
            "Connect to Intiface/Buttplug at ws://127.0.0.1:12345 and drive toys.",
            enable_sync,
        )
        cv.addWidget(row_en)
        
        # Device scanning and selection
        scan_widget = QWidget()
        scan_layout = QHBoxLayout(scan_widget)
        scan_layout.setContentsMargins(10, 6, 10, 6)
        scan_layout.setSpacing(10)
        
        # Device control row
        self.scan_button = QPushButton("Scan for devices")
        self.scan_button.setToolTip("Search for available Buttplug devices")
        self.scan_button.clicked.connect(self._on_scan_clicked)
        scan_layout.addWidget(self.scan_button)
        
        self.select_button = QPushButton("Select device")
        self.select_button.setToolTip("Choose which device to use")
        self.select_button.clicked.connect(self._on_select_clicked)
        self.select_button.setEnabled(False)  # Enable when devices found
        scan_layout.addWidget(self.select_button)
        
        self.device_label = QLabel("No devices found")
        self.device_label.setStyleSheet("color: gray;")
        scan_layout.addWidget(self.device_label, 1)  # Give label remaining space
        
        cv.addWidget(scan_widget)
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
        
    def _on_scan_clicked(self):
        """Request a device scan."""
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scanning...")
        self.scanDevicesRequested.emit()
        
    def _on_select_clicked(self):
        """Show device selection dialog."""
        if not self._current_device_list:
            return
            
        dialog = DeviceSelectionDialog(self._current_device_list, self)
        dialog.deviceSelected.connect(self._on_device_selected)
        dialog.exec()
        
    def _on_device_selected(self, device_idx: int):
        """Handle device selection."""
        self.deviceSelected.emit(device_idx)
        
    def reset_scan_button(self):
        """Reset scan button to normal state."""
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan for devices")
        
    def update_device_list(self, device_list: "DeviceList"):
        """Update UI with new device list."""
        import logging
        log = logging.getLogger(__name__)
        log.info("DevicePage.update_device_list with %d devices", len(device_list.devices))
        for device in device_list.devices:
            log.debug("   - Device: %s (index: %s)", device.name, device.index)
            
        self._current_device_list = device_list
        
        # Always restore scan button state
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan for devices")
        log.debug("Scan button reset to normal state")
        
        # Update device status
        num_devices = len(device_list.devices)
        if num_devices == 0:
            log.debug("   No devices found - updating label")
            self.device_label.setText("No devices found")
            self.device_label.setStyleSheet("color: gray;")
            self.select_button.setEnabled(False)
        else:
            log.debug("   Found %d devices - updating label", num_devices)
        if device_list.selected_idx is not None:
            log.info("Selected device at list index %s", device_list.selected_idx)
            selected_device = device_list.devices[device_list.selected_idx]
            log.info("Using device: %s", selected_device.name)
            self.device_label.setText(f"Using: {selected_device.name}")
            self.device_label.setStyleSheet("color: green;")
        else:
            log.info("No device selected")
            self.device_label.setText(f"{num_devices} device{'s' if num_devices != 1 else ''} found")
            self.device_label.setStyleSheet("color: white;")
            self.select_button.setEnabled(True)
            
        # Refresh enabled states
        self._apply_enabled_states()

    # --- ui logic ---
    def _apply_enabled_states(self):
        buzz_enabled = self.sw_enable.isChecked() and self.sw_buzz.isChecked()
        self.sld_buzz.setEnabled(buzz_enabled)

        bursts_enabled = self.sw_enable.isChecked() and self.sw_bursts.isChecked()
        for w in (self.spin_min, self.spin_max, self.sld_peak, self.spin_max_ms):
            w.setEnabled(bursts_enabled)
            
        # Device controls
        scan_enabled = self.sw_enable.isChecked()
        self.scan_button.setEnabled(scan_enabled)
        self.select_button.setEnabled(scan_enabled and bool(self._current_device_list and self._current_device_list.devices))
