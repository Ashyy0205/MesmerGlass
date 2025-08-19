"""Device selection dialog for Buttplug devices."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal
from ...engine.device_manager import DeviceList, Device

class DeviceSelectionDialog(QDialog):
    """Dialog for selecting Buttplug devices (now supports multi-select)."""

    deviceSelected = pyqtSignal(int)      # Single device index selected (back-compat)
    devicesSelected = pyqtSignal(object)  # List[int] of selected device indices
    
    def __init__(self, device_list: DeviceList, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Device")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel(
            "Select a device to use with MesmerGlass. "
            "Only devices that support vibration are shown."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Device list
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        layout.addWidget(self.list_widget)
        
        # Populate list
        for device_idx, device in enumerate(device_list.devices):
            if self._device_supports_vibration(device):
                item = QListWidgetItem(f"{device.name}")
                item.setData(Qt.ItemDataRole.UserRole, device.index)
                self.list_widget.addItem(item)
                # Check if this device index is selected (back-compat mirror)
                if getattr(device_list, "selected_index", None) == device.index:
                    item.setSelected(True)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # Rename Ok to Select for clarity
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Select")

        layout.addWidget(button_box)

        # Connect signals
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
    def accept(self):
        """Handle device selection (emit single and multi-select signals)."""
        items = self.list_widget.selectedItems()
        if items:
            indices = [it.data(Qt.ItemDataRole.UserRole) for it in items]
            # Emit multi-select list
            self.devicesSelected.emit(indices)
            # Emit single-select for first item (back-compat callers)
            self.deviceSelected.emit(indices[0])
        super().accept()
        
    def _device_supports_vibration(self, device: Device) -> bool:
        """Check if device supports vibration commands."""
        messages = device.device_messages
        scalar_cmds = messages.get("ScalarCmd", [])
        return any(
            cmd.get("ActuatorType") == "Vibrate"
            for cmd in scalar_cmds
        )
