"""Development tools and debugging features."""

import json
from typing import Dict, Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar,
    QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from ..tests.virtual_toy import VirtualToy
from ..engine.buttplug_server import Device

class DevToolsWindow(QWidget):
    """Development tools window showing virtual toy status."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("MesmerGlass Dev Tools")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        
        # Virtual toys
        self.toys: Dict[str, VirtualToy] = {}
        self.toy_widgets: Dict[str, Dict] = {}
        
        # UI Setup
        self.setup_ui()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_toy_status)
        self.update_timer.start(100)  # Update every 100ms
        
    def setup_ui(self):
        """Setup the UI layout."""
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Header
        header = QLabel("Virtual Toys")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.layout.addWidget(header)
        
        # Add toy button
        add_btn = QPushButton("Add Virtual Toy")
        add_btn.clicked.connect(self.add_virtual_toy)
        self.layout.addWidget(add_btn)
        
        # Status area
        self.status_area = QVBoxLayout()
        self.layout.addLayout(self.status_area)
        
    def add_virtual_toy(self):
        """Add a new virtual toy for testing."""
        toy_id = f"toy_{len(self.toys)}"
        toy = VirtualToy(name=f"Virtual Toy {len(self.toys)}")
        
        # Create toy status widgets
        toy_frame = QWidget()
        toy_layout = QVBoxLayout()
        toy_frame.setLayout(toy_layout)
        
        # Toy header with remove button
        header_layout = QHBoxLayout()
        name_label = QLabel(toy.name)
        name_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(name_label)
        
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self.remove_virtual_toy(toy_id))
        header_layout.addWidget(remove_btn)
        toy_layout.addLayout(header_layout)
        
        # Status
        status_label = QLabel("Status: Disconnected")
        toy_layout.addWidget(status_label)
        
        # Intensity bar
        intensity_bar = QProgressBar()
        intensity_bar.setRange(0, 100)
        intensity_bar.setValue(0)
        toy_layout.addWidget(intensity_bar)
        
        # Store widgets for updates
        self.toy_widgets[toy_id] = {
            "frame": toy_frame,
            "status": status_label,
            "intensity": intensity_bar
        }
        
        # Store toy and add to UI
        self.toys[toy_id] = toy
        self.status_area.addWidget(toy_frame)
        
        # Start the toy
        import asyncio
        asyncio.create_task(toy.connect())
        
    def remove_virtual_toy(self, toy_id: str):
        """Remove a virtual toy."""
        if toy_id in self.toys:
            # Disconnect toy
            toy = self.toys[toy_id]
            import asyncio
            asyncio.create_task(toy.disconnect())
            
            # Remove widgets
            widgets = self.toy_widgets[toy_id]
            self.status_area.removeWidget(widgets["frame"])
            widgets["frame"].deleteLater()
            
            # Clean up
            del self.toys[toy_id]
            del self.toy_widgets[toy_id]
            
    def update_toy_status(self):
        """Update the status display of all toys."""
        for toy_id, toy in self.toys.items():
            widgets = self.toy_widgets[toy_id]
            
            # Update connection status and name
            status = "Connected" if toy._ws else "Disconnected"
            widgets["status"].setText(f"{toy.name} - {status}")
            
            # Update intensity
            widgets["intensity"].setValue(int(toy.state.level * 100))
            
    def closeEvent(self, event):
        """Handle window close."""
        # Disconnect all toys
        import asyncio
        for toy in self.toys.values():
            asyncio.create_task(toy.disconnect())
        super().closeEvent(event)
