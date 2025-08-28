"""Device Database

Database of known sex toys and their communication protocols.
Based on the Buttplug device configuration database.
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass

@dataclass
class DeviceDefinition:
    """Definition of a known device and its capabilities."""
    name: str
    manufacturer: str
    protocol: str
    bluetooth_names: List[str]
    service_uuids: List[str]
    characteristics: Dict[str, str]
    capabilities: Dict[str, int]  # e.g., {"vibrate": 1, "rotate": 1}

class DeviceDatabase:
    """Database of known device configurations."""
    
    # Known device definitions based on Buttplug device config
    DEVICE_DEFINITIONS = [
        # Lovense devices
        DeviceDefinition(
            name="Lovense Lush",
            manufacturer="Lovense",
            protocol="lovense",
            bluetooth_names=["LVS-Lush", "LVS-Z001"],
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"
            },
            capabilities={"vibrate": 1}
        ),
        
        DeviceDefinition(
            name="Lovense Max",
            manufacturer="Lovense", 
            protocol="lovense",
            bluetooth_names=["LVS-Max", "LVS-A001"],
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"
            },
            capabilities={"vibrate": 1}
        ),
        
        DeviceDefinition(
            name="Lovense Nora",
            manufacturer="Lovense",
            protocol="lovense", 
            bluetooth_names=["LVS-Nora", "LVS-C001"],
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"
            },
            capabilities={"vibrate": 1, "rotate": 1}
        ),
        
        DeviceDefinition(
            name="Lovense Edge",
            manufacturer="Lovense",
            protocol="lovense",
            bluetooth_names=["LVS-Edge", "LVS-P001"],
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"
            },
            capabilities={"vibrate": 2}  # Dual vibrators
        ),
        
        DeviceDefinition(
            name="Lovense Hush",
            manufacturer="Lovense",
            protocol="lovense",
            bluetooth_names=["LVS-Hush", "LVS-Z002"],
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"
            },
            capabilities={"vibrate": 1}
        ),
        
        DeviceDefinition(
            name="Lovense Domi",
            manufacturer="Lovense",
            protocol="lovense",
            bluetooth_names=["LVS-Domi", "LVS-W001"],
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"
            },
            capabilities={"vibrate": 1}
        ),

        # Lovense Diamo (cock ring) shares classic Lovense service/characteristics
        DeviceDefinition(
            name="Lovense Diamo",
            manufacturer="Lovense",
            protocol="lovense",
            bluetooth_names=["LVS-Diamo", "LVS-R001"],  # R001 observed in BLE adverts
            service_uuids=["0000fff0-0000-1000-8000-00805f9b34fb"],  # standard Lovense service
            characteristics={
                "tx": "0000fff2-0000-1000-8000-00805f9b34fb",  # write
                "rx": "0000fff1-0000-1000-8000-00805f9b34fb"   # notify
            },
            capabilities={"vibrate": 1}
        ),
        
        # We-Vibe devices
        DeviceDefinition(
            name="We-Vibe Sync",
            manufacturer="We-Vibe",
            protocol="we_vibe",
            bluetooth_names=["Sync"],
            service_uuids=["f000aa80-0451-4000-b000-000000000000"],
            characteristics={
                "control": "f000aa81-0451-4000-b000-000000000000"
            },
            capabilities={"vibrate": 2}
        ),
        
        # Add more devices as needed...
    ]
    
    def __init__(self):
        self._devices_by_name: Dict[str, DeviceDefinition] = {}
        self._devices_by_uuid: Dict[str, List[DeviceDefinition]] = {}
        self._build_indexes()
        
    def _build_indexes(self):
        """Build lookup indexes for faster device identification."""
        for device in self.DEVICE_DEFINITIONS:
            # Index by Bluetooth names
            for name in device.bluetooth_names:
                self._devices_by_name[name.lower()] = device
                
            # Index by service UUIDs
            for uuid in device.service_uuids:
                uuid_lower = uuid.lower()
                if uuid_lower not in self._devices_by_uuid:
                    self._devices_by_uuid[uuid_lower] = []
                self._devices_by_uuid[uuid_lower].append(device)
                
    def identify_device_by_name(self, bluetooth_name: str) -> Optional[DeviceDefinition]:
        """Identify device by its Bluetooth advertisement name.
        
        Args:
            bluetooth_name: Name from Bluetooth advertisement
            
        Returns:
            DeviceDefinition if found, None otherwise
        """
        if not bluetooth_name:
            return None
            
        # Direct lookup
        exact_match = self._devices_by_name.get(bluetooth_name.lower())
        if exact_match:
            return exact_match
            
        # Partial matching for devices with variable naming
        name_lower = bluetooth_name.lower()
        for device in self.DEVICE_DEFINITIONS:
            for known_name in device.bluetooth_names:
                if known_name.lower() in name_lower or name_lower in known_name.lower():
                    return device
                    
        return None
        
    def identify_device_by_service_uuid(self, service_uuid: str) -> List[DeviceDefinition]:
        """Identify possible devices by service UUID.
        
        Args:
            service_uuid: Bluetooth service UUID
            
        Returns:
            List of possible DeviceDefinitions
        """
        return self._devices_by_uuid.get(service_uuid.lower(), [])
        
    def identify_device(self, bluetooth_name: Optional[str], service_uuids: List[str]) -> Optional[DeviceDefinition]:
        """Identify device using multiple identification methods.
        
        Args:
            bluetooth_name: Bluetooth advertisement name
            service_uuids: List of advertised service UUIDs
            
        Returns:
            Best matching DeviceDefinition or None
        """
        # First try name-based identification (most reliable)
        if bluetooth_name:
            device = self.identify_device_by_name(bluetooth_name)
            if device:
                return device
                
        # Then try service UUID matching
        for uuid in service_uuids:
            possible_devices = self.identify_device_by_service_uuid(uuid)
            if possible_devices:
                # Return first match (could be improved with scoring)
                return possible_devices[0]
                
        return None
        
    def get_device_by_name(self, name: str) -> Optional[DeviceDefinition]:
        """Get device definition by exact name match."""
        for device in self.DEVICE_DEFINITIONS:
            if device.name.lower() == name.lower():
                return device
        return None
        
    def get_all_devices(self) -> List[DeviceDefinition]:
        """Get all known device definitions."""
        return self.DEVICE_DEFINITIONS.copy()
        
    def get_devices_by_manufacturer(self, manufacturer: str) -> List[DeviceDefinition]:
        """Get all devices from a specific manufacturer."""
        return [
            device for device in self.DEVICE_DEFINITIONS 
            if device.manufacturer.lower() == manufacturer.lower()
        ]
        
    def get_supported_protocols(self) -> Set[str]:
        """Get set of all supported protocols."""
        return {device.protocol for device in self.DEVICE_DEFINITIONS}
        
    def get_devices_by_protocol(self, protocol: str) -> List[DeviceDefinition]:
        """Get all devices using a specific protocol."""
        return [
            device for device in self.DEVICE_DEFINITIONS
            if device.protocol.lower() == protocol.lower()
        ]
        
    def add_custom_device(self, device: DeviceDefinition) -> None:
        """Add a custom device definition.
        
        Args:
            device: Custom device definition to add
        """
        self.DEVICE_DEFINITIONS.append(device)
        
        # Update indexes
        for name in device.bluetooth_names:
            self._devices_by_name[name.lower()] = device
            
        for uuid in device.service_uuids:
            uuid_lower = uuid.lower()
            if uuid_lower not in self._devices_by_uuid:
                self._devices_by_uuid[uuid_lower] = []
            self._devices_by_uuid[uuid_lower].append(device)
