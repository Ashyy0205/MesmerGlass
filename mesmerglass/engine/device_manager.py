"""Device management for Buttplug protocol.

Adds multi-select support while preserving the legacy single-select API used by
some tests. Selections refer to Buttplug DeviceIndex values.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable, Set


@dataclass
class Device:
    """Represents a discovered device (Buttplug semantics)."""
    index: int
    name: str
    features: List[Dict]
    device_messages: Dict


@dataclass
class DeviceList:
    """List of available devices with selection (legacy single-select)."""
    devices: List[Device]
    selected_index: Optional[int] = None


class DeviceManager:
    """Manages device discovery and selection (multi-select capable)."""

    def __init__(self):
        self._devices: Dict[int, Device] = {}
        # Back-compat single selection
        self._selected_index: Optional[int] = None
        # New: multi-select (subset of device indices)
        self._selected_indices: Set[int] = set()

    # -------- Discovery --------
    def add_device(self, device_info: Dict) -> None:
        """Add or update a device from protocol message (Buttplug messages)."""
        idx = device_info.get("DeviceIndex")
        if idx is None:
            return
        device = Device(
            index=idx,
            name=device_info.get("DeviceName", f"Device {idx}"),
            features=device_info.get("DeviceMessages", {}).get("ScalarCmd", [{}])[0].get("Features", []),
            device_messages=device_info.get("DeviceMessages", {}),
        )
        self._devices[idx] = device

    def remove_device(self, idx: int) -> None:
        """Remove a device by index; clear selections referencing it."""
        if idx in self._devices:
            del self._devices[idx]
        if self._selected_index == idx:
            self._selected_index = None
        if idx in self._selected_indices:
            self._selected_indices.discard(idx)

    def clear(self) -> None:
        """Clear all devices and selections."""
        self._devices.clear()
        self._selected_index = None
        self._selected_indices.clear()

    # -------- Selection (back-compat single-select) --------
    def select_device(self, idx: Optional[int]) -> bool:
        """Select a single device (legacy behavior).

        Returns True if selection changed. Also mirrors to multi-select set
        (selected_indices = {idx} or empty when cleared).
        """
        if idx is not None and idx not in self._devices:
            return False
        if idx != self._selected_index:
            self._selected_index = idx
            self._selected_indices = set([idx]) if idx is not None else set()
            return True
        return False

    def get_selected_index(self) -> Optional[int]:
        return self._selected_index

    def get_selected_device(self) -> Optional[Device]:
        if self._selected_index is None:
            return None
        return self._devices.get(self._selected_index)

    def get_device_list(self) -> DeviceList:
        return DeviceList(list(self._devices.values()), selected_index=self._selected_index)

    # -------- Selection (multi-select API) --------
    def select_devices(self, indices: Optional[Iterable[int]]) -> None:
        """Replace selection with the given iterable of indices (or clear if None)."""
        if indices is None:
            self._selected_indices.clear()
            self._selected_index = None
            return
        s = {i for i in indices if i in self._devices}
        self._selected_indices = s
        # Keep single-select mirror as the lowest index for back-compat
        self._selected_index = (min(s) if s else None)

    def add_selected(self, idx: int) -> bool:
        if idx not in self._devices:
            return False
        before = set(self._selected_indices)
        self._selected_indices.add(idx)
        if self._selected_index is None:
            self._selected_index = idx
        return before != self._selected_indices

    def remove_selected(self, idx: int) -> bool:
        before = set(self._selected_indices)
        self._selected_indices.discard(idx)
        if self._selected_index == idx:
            self._selected_index = (min(self._selected_indices) if self._selected_indices else None)
        return before != self._selected_indices

    def get_selected_indices(self) -> List[int]:
        return sorted(self._selected_indices)

