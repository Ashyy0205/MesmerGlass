"""Device selection dialog for Buttplug devices."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from ...engine.device_manager import DeviceList, Device

class DeviceSelectionDialog(QDialog):
    """Dialog for selecting Buttplug devices."""
    
    deviceSelected = pyqtSignal(int)  # Device index selected
    
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
        layout.addWidget(self.list_widget)
        
        # Populate list
        for device in device_list.devices:
            if self._device_supports_vibration(device):
                item = QListWidgetItem(f"{device.name}")
                item.setData(Qt.ItemDataRole.UserRole, device.index)
                self.list_widget.addItem(item)
                if device.index == device_list.selected_index:
                    item.setSelected(True)
        
        # Buttons
        button_box = QDialogButtonBox()
        select_button = button_box.addButton("Select", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        
        layout.addWidget(button_box)
        
        # Connect signals
        select_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
    def accept(self):
        """Handle device selection."""
        items = self.list_widget.selectedItems()
        if items:
            device_index = items[0].data(Qt.ItemDataRole.UserRole)
            self.deviceSelected.emit(device_index)
        super().accept()
        
    def _device_supports_vibration(self, device: Device) -> bool:
        """Check if device supports vibration commands."""
        messages = device.device_messages
        scalar_cmds = messages.get("ScalarCmd", [])
        return any(
            cmd.get("ActuatorType") == "Vibrate"
            for cmd in scalar_cmds
        )
