"""Device Control Tab - Bluetooth device scanning and connection."""

import asyncio
import logging
import qasync
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QGroupBox, QTextEdit, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from .base_tab import BaseTab


class DevicesTab(BaseTab):
    """Tab for managing Bluetooth device connections via MesmerIntiface."""
    
    device_connected = pyqtSignal(int)  # Emitted when device is connected
    device_disconnected = pyqtSignal(int)  # Emitted when device is disconnected
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.logger = logging.getLogger(__name__)
        
        # Track scanning state
        self._is_scanning = False
        self._scan_timer = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the device control interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("🔗 Device Control")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #569cd6;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel(
            "Scan for and connect to Bluetooth devices using MesmerIntiface.\n"
            "Supported devices: Lovense, We-Vibe, and more."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #d4d4d4; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        # Status summary bar
        status_bar = QWidget()
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(10, 5, 10, 5)
        status_bar.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                border-radius: 4px;
            }
        """)
        
        self.status_summary = QLabel("📊 Devices: 0 discovered | 0 connected")
        self.status_summary.setStyleSheet("color: #d4d4d4; font-weight: bold;")
        status_bar_layout.addWidget(self.status_summary)
        
        status_bar_layout.addStretch()
        layout.addWidget(status_bar)
        
        # Splitter for devices list and log
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # === Device Scanning Section ===
        scan_group = QGroupBox("Bluetooth Devices")
        scan_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #d4d4d4;
                border: 2px solid #3c3c3c;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        scan_layout = QVBoxLayout(scan_group)
        
        # Scan controls
        controls_layout = QHBoxLayout()
        
        self.scan_button = QPushButton("🔍 Start Scanning")
        self.scan_button.clicked.connect(self._toggle_scanning)
        self.scan_button.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 13px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #808080;
            }
        """)
        controls_layout.addWidget(self.scan_button)
        
        self.scan_status = QLabel("Not scanning")
        self.scan_status.setStyleSheet("color: #808080; font-style: italic;")
        controls_layout.addWidget(self.scan_status)
        
        controls_layout.addStretch()
        scan_layout.addLayout(controls_layout)
        
        # Device list
        self.device_list = QListWidget()
        self.device_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #2d2d30;
                border-left: 3px solid transparent;
            }
            QListWidget::item:selected {
                background-color: rgba(14, 99, 156, 0.45);
                border-left: 3px solid #FF8A00;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #2a2d2e;
            }
        """)
        self.device_list.itemDoubleClicked.connect(self._on_device_double_clicked)
        scan_layout.addWidget(self.device_list)
        
        # Connection controls
        connect_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("🔗 Connect Selected")
        self.connect_button.clicked.connect(self._connect_selected_device)
        self.connect_button.setEnabled(False)
        self.connect_button.setStyleSheet("""
            QPushButton {
                background-color: #107c10;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0f8b0f;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #808080;
            }
        """)
        connect_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("❌ Disconnect")
        self.disconnect_button.clicked.connect(self._disconnect_device)
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.setStyleSheet("""
            QPushButton {
                background-color: #a80000;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c50000;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #808080;
            }
        """)
        connect_layout.addWidget(self.disconnect_button)
        
        # Test button
        self.test_button = QPushButton("⚡ Test Vibration")
        self.test_button.clicked.connect(self._test_all_devices)
        self.test_button.setEnabled(False)
        self.test_button.setStyleSheet("""
            QPushButton {
                background-color: #8a2be2;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #9d4eed;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #808080;
            }
        """)
        connect_layout.addWidget(self.test_button)
        
        connect_layout.addStretch()
        scan_layout.addLayout(connect_layout)
        
        splitter.addWidget(scan_group)
        
        # === Connection Log Section ===
        log_group = QGroupBox("Connection Log")
        log_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #d4d4d4;
                border: 2px solid #3c3c3c;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.log_text.clear)
        clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: none;
                padding: 6px 12px;
                font-size: 11px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        log_layout.addWidget(clear_log_btn)
        
        splitter.addWidget(log_group)
        
        # Set initial sizes (60% devices, 40% log)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        
        # Enable selection change tracking
        self.device_list.itemSelectionChanged.connect(self._on_selection_changed)
        
    def _log(self, message: str):
        """Add a message to the connection log with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color-code messages based on emoji/content
        if "✅" in message or "Connected" in message:
            color = "#4ec9b0"  # cyan-green for success
        elif "❌" in message or "ERROR" in message or "Failed" in message:
            color = "#f48771"  # light red for errors
        elif "⚠️" in message or "WARNING" in message:
            color = "#dcdcaa"  # yellow for warnings
        elif "🔍" in message or "Scanning" in message:
            color = "#569cd6"  # blue for info
        elif "⚡" in message:
            color = "#c586c0"  # purple for test actions
        else:
            color = "#d4d4d4"  # default gray
            
        formatted_message = f'<span style="color: #808080;">[{timestamp}]</span> <span style="color: {color};">{message}</span>'
        self.log_text.append(formatted_message)
        
        # Auto-scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        
    def _toggle_scanning(self):
        """Toggle Bluetooth scanning on/off."""
        if not self._is_scanning:
            self._start_scanning()
        else:
            self._stop_scanning()
            
    def _start_scanning(self):
        """Start Bluetooth device scanning."""
        self._log("🔍 Starting Bluetooth scan...")
        
        # Get MesmerIntifaceServer from main window
        mesmer_server = getattr(self.main_window, 'mesmer_intiface_server', None)
        if not mesmer_server:
            self._log("❌ ERROR: MesmerIntiface server not available")
            return
        
        # Define async scan operation
        async def start_scan():
            try:
                success = await mesmer_server.start_real_scanning()
                if success:
                    self._is_scanning = True
                    self.scan_button.setText("⏹️ Stop Scanning")
                    self.scan_status.setText("Scanning for devices...")
                    self.scan_status.setStyleSheet("color: #569cd6; font-style: italic;")
                    self._log("✅ Scanning started successfully")
                    
                    # Start periodic device list refresh
                    self._scan_timer = QTimer()
                    self._scan_timer.timeout.connect(self._refresh_device_list)
                    self._scan_timer.start(1000)  # Refresh every second
                else:
                    self._log("❌ Failed to start scanning")
            except Exception as e:
                self._log(f"❌ ERROR: {e}")
                self.logger.error(f"Failed to start scanning: {e}", exc_info=True)
        
        # Schedule async operation using asyncio.create_task
        asyncio.create_task(start_scan())
        
    def _stop_scanning(self):
        """Stop Bluetooth device scanning."""
        self._log("⏹️ Stopping Bluetooth scan...")
        
        # Stop refresh timer
        if self._scan_timer:
            self._scan_timer.stop()
            self._scan_timer = None
        
        # Get MesmerIntifaceServer
        mesmer_server = getattr(self.main_window, 'mesmer_intiface_server', None)
        if not mesmer_server:
            return
        
        # Define async stop operation
        async def stop_scan():
            try:
                await mesmer_server.stop_real_scanning()
                self._is_scanning = False
                self.scan_button.setText("🔍 Start Scanning")
                self.scan_status.setText("Not scanning")
                self.scan_status.setStyleSheet("color: #808080; font-style: italic;")
                self._log("✅ Scanning stopped")
            except Exception as e:
                self._log(f"❌ ERROR: {e}")
                self.logger.error(f"Failed to stop scanning: {e}", exc_info=True)
        
        # Schedule async operation using asyncio.create_task
        asyncio.create_task(stop_scan())
        
    def _refresh_device_list(self):
        """Refresh the list of discovered devices with enhanced display."""
        mesmer_server = getattr(self.main_window, 'mesmer_intiface_server', None)
        if not mesmer_server:
            return
            
        # Get device list from server
        device_list = mesmer_server.get_device_list()
        
        # Count connected devices
        connected_count = sum(1 for d in device_list.devices if getattr(d, 'is_connected', False))
        total_count = len(device_list.devices)
        
        # Update status summary
        self.status_summary.setText(f"📊 Devices: {total_count} discovered | {connected_count} connected")
        
        # Store current selection
        current_selection = None
        selected_items = self.device_list.selectedItems()
        if selected_items:
            current_device = selected_items[0].data(Qt.ItemDataRole.UserRole)
            if current_device:
                current_selection = getattr(current_device, 'index', None)
        
        # Clear and repopulate list
        self.device_list.clear()
        
        if not device_list.devices:
            item = QListWidgetItem("No devices found")
            item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
            item.setForeground(QColor("#808080"))
            self.device_list.addItem(item)
            self._update_button_states()
            return
            
        for device in device_list.devices:
            is_connected = getattr(device, 'is_connected', False)
            
            # Status indicator
            status_icon = "🟢" if is_connected else "🔴"
            status_text = "Connected" if is_connected else "Disconnected"
            
            # Build display text with multiple lines
            line1 = f"{status_icon} {device.name}"
            line2 = f"   Status: {status_text}"
            
            # Add device type if available
            if hasattr(device, 'device_messages') and device.device_messages:
                features = []
                if 'ScalarCmd' in device.device_messages:
                    vibrator_count = len(device.device_messages['ScalarCmd'])
                    features.append(f"{vibrator_count}x Vibrator")
                if 'RotateCmd' in device.device_messages:
                    features.append("Rotator")
                if features:
                    line2 += f" | {', '.join(features)}"
            
            text = f"{line1}\n{line2}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, device)
            
            # Color-code the border based on connection status
            if is_connected:
                # Make connected devices stand out with green tint
                item.setForeground(QColor("#4ec9b0"))
            else:
                item.setForeground(QColor("#d4d4d4"))
            
            self.device_list.addItem(item)
            
            # Restore selection if this was the previously selected device
            if current_selection is not None and getattr(device, 'index', None) == current_selection:
                item.setSelected(True)
        
        self._update_button_states()
        
    def _on_selection_changed(self):
        """Handle device selection changes."""
        self._update_button_states()
    
    def _update_button_states(self):
        """Update the enabled state of all buttons based on current state."""
        selected_items = self.device_list.selectedItems()
        has_selection = len(selected_items) > 0
        
        # Check if selected device is connected
        selected_is_connected = False
        if has_selection:
            device = selected_items[0].data(Qt.ItemDataRole.UserRole)
            if device:
                selected_is_connected = getattr(device, 'is_connected', False)
        
        # Connect button: enabled if device selected and not connected
        self.connect_button.setEnabled(has_selection and not selected_is_connected)
        
        # Disconnect button: enabled if device selected and connected
        self.disconnect_button.setEnabled(has_selection and selected_is_connected)
        
        # Test button: enabled if ANY device is connected (not just selected one)
        has_any_connected = any(
            hasattr(self.device_list.item(i).data(Qt.ItemDataRole.UserRole), 'is_connected') and
            self.device_list.item(i).data(Qt.ItemDataRole.UserRole).is_connected
            for i in range(self.device_list.count())
            if self.device_list.item(i).data(Qt.ItemDataRole.UserRole)
        )
        self.test_button.setEnabled(has_any_connected)
        
    def _is_device_connected(self) -> bool:
        """Check if the selected device is connected."""
        # TODO: Implement connection state tracking
        return False
    
    def _test_all_devices(self):
        """Send a test vibration to all connected devices."""
        self._log("⚡ Sending test vibration to all connected devices...")
        
        # Get MesmerIntifaceServer from main window
        mesmer_server = getattr(self.main_window, 'mesmer_intiface_server', None)
        if not mesmer_server:
            self._log("❌ ERROR: MesmerIntiface server not available")
            return
        
        # Define async test operation
        async def test_devices():
            try:
                results = await mesmer_server.test_all_devices()
                
                if not results:
                    self._log("⚠️ No connected devices to test")
                    return
                    
                # Log results for each device
                for device_name, success in results.items():
                    if success:
                        self._log(f"✅ Test vibration sent to {device_name}")
                    else:
                        self._log(f"❌ Test vibration failed for {device_name}")
                        
            except Exception as e:
                self._log(f"❌ ERROR testing devices: {e}")
                self.logger.error(f"Failed to test devices: {e}", exc_info=True)
        
        # Schedule async operation
        asyncio.create_task(test_devices())
        
    def _on_device_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on device to toggle connection."""
        device = item.data(Qt.ItemDataRole.UserRole)
        if not device:
            return
            
        is_connected = getattr(device, 'is_connected', False)
        
        if is_connected:
            # Disconnect if already connected
            self._disconnect_device()
        else:
            # Connect if not connected
            self._connect_device(device)
            
    def _connect_selected_device(self):
        """Connect to the selected device."""
        items = self.device_list.selectedItems()
        if not items:
            return
            
        device = items[0].data(Qt.ItemDataRole.UserRole)
        if device:
            self._connect_device(device)
            
    def _connect_device(self, device):
        """Connect to a specific device."""
        self._log(f"🔗 Connecting to {device.name}...")
        
        mesmer_server = getattr(self.main_window, 'mesmer_intiface_server', None)
        if not mesmer_server:
            self._log("❌ ERROR: MesmerIntiface server not available")
            return
        
        # Define async connect operation
        async def connect():
            try:
                success = await mesmer_server.connect_real_device(device.index)
                if success:
                    self._log(f"✅ Connected to {device.name}")
                    self.device_connected.emit(device.index)
                    self._refresh_device_list()  # Refresh to update connection state
                else:
                    self._log(f"❌ Failed to connect to {device.name}")
            except Exception as e:
                self._log(f"❌ ERROR: {e}")
                self.logger.error(f"Failed to connect to device: {e}", exc_info=True)
        
        # Schedule async operation using asyncio.create_task
        asyncio.create_task(connect())
        
    def _disconnect_device(self):
        """Disconnect the selected device."""
        items = self.device_list.selectedItems()
        if not items:
            return
            
        device = items[0].data(Qt.ItemDataRole.UserRole)
        if not device:
            return
            
        self._log(f"❌ Disconnecting from {device.name}...")
        
        mesmer_server = getattr(self.main_window, 'mesmer_intiface_server', None)
        if not mesmer_server:
            return
        
        # Define async disconnect operation
        async def disconnect():
            try:
                success = await mesmer_server.disconnect_real_device(device.index)
                if success:
                    self._log(f"✅ Disconnected from {device.name}")
                    self.device_disconnected.emit(device.index)
                    self._refresh_device_list()  # Refresh to update connection state
                else:
                    self._log(f"❌ Failed to disconnect from {device.name}")
            except Exception as e:
                self._log(f"❌ ERROR: {e}")
                self.logger.error(f"Failed to disconnect device: {e}", exc_info=True)
        
        # Schedule async operation using asyncio.create_task
        asyncio.create_task(disconnect())
