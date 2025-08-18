"""Device management for Buttplug protocol."""

from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class Device:
    """Represents a connected device."""
    index: int
    name: str
    features: List[Dict]
    device_messages: Dict

@dataclass
class DeviceList:
    """List of available devices with selection."""
    devices: List[Device]
    selected_index: Optional[int] = None

class DeviceManager:
    """Manages device discovery and selection."""
    
    def __init__(self):
        self._devices: Dict[int, Device] = {}
        self._selected_index: Optional[int] = None
        
    def add_device(self, device_info: Dict) -> None:
        """Add or update a device from protocol message."""
        idx = device_info.get("DeviceIndex")
        if idx is not None:
            device = Device(
                index=idx,
                name=device_info.get("DeviceName", f"Device {idx}"),
                features=device_info.get("DeviceMessages", {}).get("ScalarCmd", [{}])[0].get("Features", []),
                device_messages=device_info.get("DeviceMessages", {})
            )
            self._devices[idx] = device
            
    def remove_device(self, idx: int) -> None:
        """Remove a device by index."""
        if idx in self._devices:
            del self._devices[idx]
            if self._selected_index == idx:
                self._selected_index = None
                
    def select_device(self, idx: Optional[int]) -> bool:
        """Select a device by index. Returns True if selection changed."""
        if idx is not None and idx not in self._devices:
            return False
        if idx != self._selected_index:
            self._selected_index = idx
            return True
        return False
    
    def get_selected_index(self) -> Optional[int]:
        """Get the index of the currently selected device."""
        return self._selected_index
    
    def get_device_list(self) -> DeviceList:
        """Get list of all devices and current selection."""
        return DeviceList(
            devices=list(self._devices.values()),
            selected_index=self._selected_index
        )
    
    def get_selected_device(self) -> Optional[Device]:
        """Get currently selected device."""
        if self._selected_index is None:
            return None
        return self._devices.get(self._selected_index)
    
    def clear(self) -> None:
        """Clear all devices."""
        self._devices.clear()
        self._selected_index = None
