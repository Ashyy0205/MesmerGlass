"""Display Tab - Monitor and VR display selection.

Features:
- List physical monitors with resolution info
- List discovered VR clients (wireless headsets)
- Checkboxes for selecting displays
- Quick select buttons (All, Primary only)
- Refresh VR button to rediscover devices
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

from .base_tab import BaseTab


class DisplayTab(BaseTab):
    """Tab for selecting monitor and VR display outputs."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._last_vr_refresh = 0  # Timestamp of last VR refresh to prevent spam
        self._suppress_item_changed = False
        
        # Store reference to MainApplication (parent becomes QStackedWidget after addTab)
        self._main_app = parent
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the display tab UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # === HEADER: Title ===
        title = QLabel("🖥️ Displays")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title)
        
        # === MONITORS SECTION ===
        monitors_label = QLabel("<b>Monitors</b>")
        monitors_label.setStyleSheet("font-size: 11pt;")
        layout.addWidget(monitors_label)
        
        # === DISPLAY LIST ===
        self.list_displays = QListWidget()
        self.list_displays.itemChanged.connect(self._on_display_item_changed)
        
        # Add physical monitors (default: check first one = primary)
        self._suppress_item_changed = True
        primary_screen = QGuiApplication.primaryScreen()
        for idx, screen in enumerate(QGuiApplication.screens()):
            geometry = screen.geometry()
            item_text = f"🖥️ {screen.name()}  {geometry.width()}x{geometry.height()}"
            item = QListWidgetItem(item_text)
            # Make item checkable
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            # Check primary screen by default
            if screen == primary_screen:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, {"type": "monitor", "screen": screen})
            self.list_displays.addItem(item)
        
        # Add separator
        separator = QListWidgetItem("─" * 40)
        separator.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
        self.list_displays.addItem(separator)
        
        # Add VR section label
        vr_label_item = QListWidgetItem("VR Devices (Wireless)")
        vr_label_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
        self.list_displays.addItem(vr_label_item)
        
        # Refresh VR devices
        self._refresh_vr_displays()

        self._suppress_item_changed = False
        self._push_selection_to_status_bar()
        
        layout.addWidget(self.list_displays, 1)
        
        # === QUICK SELECT BUTTONS ===
        quick_row = QWidget()
        quick_layout = QHBoxLayout(quick_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        
        quick_label = QLabel("Quick select:")
        quick_label.setMinimumWidth(160)
        quick_layout.addWidget(quick_label)
        
        btn_sel_all = QPushButton("Select all")
        btn_sel_all.clicked.connect(self._select_all_displays)
        quick_layout.addWidget(btn_sel_all)
        
        btn_sel_pri = QPushButton("Primary only")
        btn_sel_pri.clicked.connect(self._select_primary_display)
        quick_layout.addWidget(btn_sel_pri)
        
        btn_refresh_vr = QPushButton("🔄 Refresh VR")
        btn_refresh_vr.clicked.connect(self._refresh_vr_displays)
        quick_layout.addWidget(btn_refresh_vr)
        
        quick_layout.addStretch()
        
        layout.addWidget(quick_row)
        
        # === FOOTER: Info ===
        info_label = QLabel(
            "💡 Select displays where visuals will appear.\n"
            "   📱 Wireless VR: Android headsets via WiFi (auto-discovered)"
        )
        info_label.setStyleSheet("color: #888; font-style: italic;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.logger.info("DisplayTab initialized")

    def _push_selection_to_status_bar(self) -> None:
        summary = self._get_selected_displays_summary()
        setter = getattr(self._main_app, "set_status_display", None)
        if callable(setter):
            setter(summary)

    def _get_selected_displays_summary(self) -> str:
        monitors: list[str] = []
        vrs: list[str] = []

        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            if not item:
                continue
            if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                continue
            if item.checkState() != Qt.CheckState.Checked:
                continue

            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue

            if data.get("type") == "monitor":
                screen = data.get("screen")
                name = getattr(screen, "name", lambda: "Monitor")()
                monitors.append(str(name))
            elif data.get("type") == "vr":
                client = data.get("client") or {}
                label = client.get("name") or client.get("ip") or "VR"
                vrs.append(str(label))

        if not monitors and not vrs:
            return "No display selected"

        parts: list[str] = []
        if monitors:
            parts.append(f"Monitors: {len(monitors)}")
        if vrs:
            parts.append(f"VR: {len(vrs)}")
        return " | ".join(parts)

    def _on_display_item_changed(self, item: QListWidgetItem) -> None:
        if self._suppress_item_changed:
            return
        if not item or not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return

        self._push_selection_to_status_bar()
        self.mark_dirty()
    
    
    def _refresh_vr_displays(self):
        """Refresh the VR devices section in the displays list."""
        import time

        if self.list_displays is None:
            return
        
        # Prevent rapid repeated refreshes (cooldown: 2 seconds)
        current_time = time.time()
        if current_time - self._last_vr_refresh < 2.0:
            self.logger.debug(f"Skipping VR refresh (cooldown: {current_time - self._last_vr_refresh:.1f}s since last)")
            return
        
        self._last_vr_refresh = current_time
        self.logger.debug("Starting VR display refresh")
        
        self._suppress_item_changed = True

        # Save the checked state of existing VR items (by client IP)
        checked_ips = set()
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict):
                if data.get("type") == "vr" and item.checkState() == Qt.CheckState.Checked:
                    client_info = data.get("client")
                    if client_info:
                        checked_ips.add(client_info.get("ip"))
        
        # Find indices of monitors, separator, label, and VR devices
        last_monitor_idx = -1
        separator_idx = -1
        vr_label_idx = -1
        vr_device_indices = []
        
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            text = item.text()
            
            # Track last monitor
            if data and isinstance(data, dict) and data.get("type") == "monitor":
                last_monitor_idx = i
            # Track separator
            elif "─" in text and separator_idx == -1:
                separator_idx = i
            # Track VR label
            elif "VR Devices" in text and vr_label_idx == -1:
                vr_label_idx = i
            # Track VR devices
            elif data and isinstance(data, dict) and data.get("type") == "vr":
                vr_device_indices.append(i)
        
        # Remove existing VR devices (in reverse order to preserve indices)
        for idx in reversed(vr_device_indices):
            self.list_displays.takeItem(idx)
        
        # Ensure separator exists in correct position (after monitors)
        if separator_idx == -1:
            separator = QListWidgetItem("─" * 40)
            separator.setFlags(Qt.ItemFlag.NoItemFlags)
            insert_pos = last_monitor_idx + 1
            self.list_displays.insertItem(insert_pos, separator)
            separator_idx = insert_pos
            # Adjust vr_label_idx if it exists and is after insertion
            if vr_label_idx >= insert_pos:
                vr_label_idx += 1
        
        # Ensure VR label exists in correct position (after separator)
        if vr_label_idx == -1:
            vr_label_item = QListWidgetItem("VR Devices (Wireless)")
            vr_label_item.setFlags(Qt.ItemFlag.NoItemFlags)
            insert_pos = separator_idx + 1
            self.list_displays.insertItem(insert_pos, vr_label_item)
            vr_label_idx = insert_pos
        
        # Get discovered VR clients from main window's VR discovery service
        discovered_clients = []
        vr_discovery_service = getattr(self._main_app, 'vr_discovery_service', None)
        
        self.logger.info(f"🔍 DEBUG: parent()={self.parent()}, vr_discovery_service={vr_discovery_service}")
        
        if vr_discovery_service:
            try:
                # Discovery service tracks clients that have broadcast "VR_HEADSET_HELLO"
                self.logger.info(f"🔍 DEBUG: About to call discovered_clients property...")
                discovered_clients = getattr(vr_discovery_service, 'discovered_clients', [])
                self.logger.info(f"Discovery service returned {len(discovered_clients)} VR clients")
                for client in discovered_clients:
                    self.logger.info(f"  → {client.get('name')} at {client.get('ip')}")
            except Exception as e:
                self.logger.error(f"Error getting VR clients from discovery: {e}")
        else:
            self.logger.warning(f"⚠️  No VR discovery service available (_main_app.vr_discovery_service is None!)")
        
        if discovered_clients:
            # Add VR client items after the VR label (make them checkable and selectable)
            insert_pos = vr_label_idx + 1
            self.logger.info(f"Adding {len(discovered_clients)} VR devices starting at position {insert_pos}")
            for client_info in discovered_clients:
                name = client_info.get("name", "Unknown VR Device")
                ip = client_info.get("ip", "0.0.0.0")
                item_text = f"📱 {name} ({ip})"
                item = QListWidgetItem(item_text)
                
                # Restore checked state if this client was previously checked
                if ip in checked_ips:
                    item.setCheckState(Qt.CheckState.Checked)
                    self.logger.info(f"  Restoring checked state for {name}")
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
                
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, {"type": "vr", "client": client_info})
                self.list_displays.insertItem(insert_pos, item)
                self.logger.info(f"  Added VR device: {item_text} at position {insert_pos}")
                insert_pos += 1  # Increment for next VR device
        else:
            self.logger.info("No VR devices to add")
        
        # Log final list count
        total_items = self.list_displays.count()
        self.logger.info(f"VR refresh complete: {len(discovered_clients)} devices found, total list items: {total_items}")

        self._suppress_item_changed = False
        self._push_selection_to_status_bar()

    
    def _select_all_displays(self):
        """Select all displays (monitors and VR)."""
        self._suppress_item_changed = True
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            if item and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Checked)

        self._suppress_item_changed = False
        self._push_selection_to_status_bar()
        
        self.logger.info("Selected all displays")
        self.mark_dirty()
    
    def _select_primary_display(self):
        """Select only the primary monitor."""
        self._suppress_item_changed = True
        # Uncheck all
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            if item and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(Qt.CheckState.Unchecked)
        
        # Check first monitor (primary)
        if self.list_displays.count() > 0:
            first_item = self.list_displays.item(0)
            if first_item and first_item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                first_item.setCheckState(Qt.CheckState.Checked)
        
        self._suppress_item_changed = False
        self._push_selection_to_status_bar()

        self.logger.info("Selected primary display only")
        self.mark_dirty()
    
    def get_selected_displays(self) -> List[Dict[str, Any]]:
        """Get list of selected displays.
        
        Returns:
            List of dicts with keys:
            - type: "monitor" or "vr"
            - screen: QScreen object (for monitors)
            - client: dict with VR client info (for VR)
        """
        selected = []
        
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and isinstance(data, dict):
                    selected.append(data)
        
        return selected
    
    def on_show(self):
        """Called when tab becomes visible."""
        self.logger.debug("DisplayTab shown")
        # Refresh VR devices when tab is shown
        self._refresh_vr_displays()
    
    def on_hide(self):
        """Called when tab becomes hidden."""
        self.logger.debug("DisplayTab hidden")
