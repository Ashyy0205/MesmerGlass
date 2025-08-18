"""Bluetooth Device Scanner

Pure Python Bluetooth Low Energy device discovery using the bleak library.
Scans for and identifies sex toys and haptic devices that support the Buttplug protocol.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass
from bleak import BleakScanner, BleakClient, BLEDevice
from bleak.backends.device import BLEDevice as BLEDeviceType

@dataclass
class BluetoothDeviceInfo:
    """Information about a discovered Bluetooth device."""
    address: str
    name: Optional[str]
    rssi: int
    manufacturer_data: Dict[int, bytes]
    service_uuids: List[str]
    device_type: Optional[str] = None
    protocol: Optional[str] = None
    is_connected: bool = False

class BluetoothDeviceScanner:
    """Bluetooth LE device scanner for sex toys and haptic devices."""
    
    # Known service UUIDs for popular sex toy manufacturers
    KNOWN_SERVICE_UUIDS = {
        # Lovense devices
        "0000fff0-0000-1000-8000-00805f9b34fb": "lovense",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e": "lovense_uart",
        "5a300001-0023-4bd4-bbd5-a6920e4c5653": "lovense_v2",  # Lovense Hush and newer devices
        
        # We-Vibe devices  
        "f000aa80-0451-4000-b000-000000000000": "we_vibe",
        
        # Kiiroo devices
        "88f80580-0000-01e6-aace-0002a5d5c51b": "kiiroo",
        
        # Generic sex toy services
        "0000180f-0000-1000-8000-00805f9b34fb": "battery_service",
        "0000180a-0000-1000-8000-00805f9b34fb": "device_info_service",
    }
    
    # Manufacturer data company IDs
    KNOWN_MANUFACTURERS = {
        0x0001: "lovense",
        0x0002: "we_vibe", 
        0x0003: "kiiroo",
    }
    
    def __init__(self):
        self._scanning = False
        self._scanner = None
        self._discovered_devices: Dict[str, BluetoothDeviceInfo] = {}
        self._device_callbacks: List[Callable[[List[BluetoothDeviceInfo]], None]] = []
        self._connected_clients: Dict[str, BleakClient] = {}
        
        # Setup logging with console output
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(logging.INFO)
        
        # Add console handler if not already present
        if not self._logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('[bluetooth] %(message)s')
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)
            
        self._shutdown = False
        
    def add_device_callback(self, callback: Callable[[List[BluetoothDeviceInfo]], None]) -> None:
        """Add callback for device discovery updates."""
        self._device_callbacks.append(callback)
        
    def remove_device_callback(self, callback: Callable[[List[BluetoothDeviceInfo]], None]) -> None:
        """Remove device callback."""
        if callback in self._device_callbacks:
            self._device_callbacks.remove(callback)
            
    async def start_scanning(self, duration: Optional[float] = None) -> bool:
        """Start scanning for Bluetooth devices.
        
        Args:
            duration: How long to scan in seconds. None for indefinite.
            
        Returns:
            True if scanning started successfully.
        """
        if self._scanning:
            return True
            
        try:
            self._scanning = True
            self._logger.info("Starting Bluetooth LE device scan")
            
            # Start scanning with device detection callback
            self._scanner = BleakScanner(detection_callback=self._on_device_detected)
            await self._scanner.start()
            
            if duration:
                await asyncio.sleep(duration)
                await self._scanner.stop()
                self._scanning = False
                self._scanner = None
            
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to start scanning: {e}")
            self._scanning = False
            self._scanner = None
            return False
            
    async def stop_scanning(self) -> None:
        """Stop device scanning."""
        if not self._scanning:
            return
            
        try:
            self._scanning = False
            if self._scanner:
                await self._scanner.stop()
                self._scanner = None
            self._logger.info("Stopped Bluetooth LE device scan")
        except Exception as e:
            self._logger.error(f"Error stopping scanner: {e}")
        finally:
            self._scanning = False
            self._scanner = None
        
    def is_scanning(self) -> bool:
        """Check if currently scanning."""
        return self._scanning
        
    def get_discovered_devices(self) -> List[BluetoothDeviceInfo]:
        """Get list of discovered devices."""
        return list(self._discovered_devices.values())
        
    def get_device_by_address(self, address: str) -> Optional[BluetoothDeviceInfo]:
        """Get device info by Bluetooth address."""
        return self._discovered_devices.get(address)
        
    async def connect_device(self, address: str) -> bool:
        """Connect to a specific device.
        
        Args:
            address: Bluetooth address of device to connect to.
            
        Returns:
            True if connection successful.
        """
        device_info = self._discovered_devices.get(address)
        if not device_info:
            self._logger.error(f"Device {address} not found")
            return False
            
        if address in self._connected_clients:
            self._logger.info(f"Device {address} already connected")
            return True
            
        try:
            # Create BLE device object for connection
            ble_device = await self._find_ble_device(address)
            if not ble_device:
                self._logger.error(f"Could not find BLE device {address}")
                return False
                
            # Connect to device
            client = BleakClient(ble_device)
            await client.connect()
            
            if client.is_connected:
                self._connected_clients[address] = client
                device_info.is_connected = True
                self._logger.info(f"Connected to device: {device_info.name or address}")
                
                # Discover services
                await self._discover_device_services(client, device_info)
                
                # Notify callbacks
                self._notify_device_callbacks()
                return True
            else:
                self._logger.error(f"Failed to connect to {address}")
                return False
                
        except Exception as e:
            self._logger.error(f"Error connecting to device {address}: {e}")
            return False
            
    async def disconnect_device(self, address: str) -> bool:
        """Disconnect from a specific device.
        
        Args:
            address: Bluetooth address of device to disconnect from.
            
        Returns:
            True if disconnection successful.
        """
        if address not in self._connected_clients:
            return True
            
        try:
            client = self._connected_clients[address]
            await client.disconnect()
            del self._connected_clients[address]
            
            device_info = self._discovered_devices.get(address)
            if device_info:
                device_info.is_connected = False
                
            self._logger.info(f"Disconnected from device: {address}")
            self._notify_device_callbacks()
            return True
            
        except Exception as e:
            self._logger.error(f"Error disconnecting from device {address}: {e}")
            return False
            
    async def send_command(self, address: str, characteristic_uuid: str, data: bytes) -> bool:
        """Send command to connected device.
        
        Args:
            address: Bluetooth address of target device.
            characteristic_uuid: UUID of characteristic to write to.
            data: Command data to send.
            
        Returns:
            True if command sent successfully.
        """
        if address not in self._connected_clients:
            self._logger.error(f"Device {address} not connected")
            return False
            
        try:
            client = self._connected_clients[address]
            await client.write_gatt_char(characteristic_uuid, data)
            return True
            
        except Exception as e:
            self._logger.error(f"Error sending command to {address}: {e}")
            return False
            
    def _on_device_detected(self, device: BLEDeviceType, advertisement_data) -> None:
        """Handle detected Bluetooth device."""
        # Skip if shutting down
        if self._shutdown:
            return
            
        try:
            # Extract device information
            device_info = BluetoothDeviceInfo(
                address=device.address,
                name=device.name,
                rssi=advertisement_data.rssi,
                manufacturer_data=advertisement_data.manufacturer_data,
                service_uuids=[str(uuid) for uuid in advertisement_data.service_uuids]
            )
            
            # Log all detected devices for debugging
            self._logger.info(f"Detected BLE device: {device.name or 'Unknown'} ({device.address}) RSSI: {advertisement_data.rssi}")
            if device_info.service_uuids:
                self._logger.info(f"  Service UUIDs: {device_info.service_uuids}")
            if device_info.manufacturer_data:
                self._logger.info(f"  Manufacturer data: {device_info.manufacturer_data}")
            
            # Check if this looks like a sex toy
            device_type, protocol = self._identify_device(device_info)
            if device_type:
                device_info.device_type = device_type
                device_info.protocol = protocol
                
                # Store/update device
                self._discovered_devices[device.address] = device_info
                
                self._logger.info(f"✅ Identified {device_type} device: {device.name or device.address}")
                
                # Notify callbacks (but not if shutting down)
                if not self._shutdown:
                    self._notify_device_callbacks()
            else:
                # For debugging: store unidentified devices too
                device_info.device_type = "unknown"
                device_info.protocol = "unknown"
                self._discovered_devices[device.address] = device_info
                
                # Notify callbacks for all devices during development
                if not self._shutdown:
                    self._notify_device_callbacks()
                
        except Exception as e:
            if not self._shutdown:  # Don't log errors during shutdown
                self._logger.error(f"Error processing detected device: {e}")
            
    def _identify_device(self, device_info: BluetoothDeviceInfo) -> tuple[Optional[str], Optional[str]]:
        """Identify device type and protocol from advertisement data.
        
        Args:
            device_info: Device information from advertisement.
            
        Returns:
            Tuple of (device_type, protocol) or (None, None) if not recognized.
        """
        # Check service UUIDs
        for service_uuid in device_info.service_uuids:
            service_uuid_lower = service_uuid.lower()
            if service_uuid_lower in self.KNOWN_SERVICE_UUIDS:
                protocol = self.KNOWN_SERVICE_UUIDS[service_uuid_lower]
                return ("sex_toy", protocol)
                
        # Check manufacturer data
        for company_id in device_info.manufacturer_data:
            if company_id in self.KNOWN_MANUFACTURERS:
                protocol = self.KNOWN_MANUFACTURERS[company_id]
                return ("sex_toy", protocol)
                
        # Check device name patterns (more comprehensive)
        if device_info.name:
            name_lower = device_info.name.lower()
            
            # Known brands
            brand_patterns = [
                "lovense", "we-vibe", "kiiroo", "satisfyer", "lelo", "wevibe",
                "fleshlight", "ohmibod", "mysteryvibe", "magic motion", "svakom",
                "calor", "edge", "hush", "lush", "nora", "max", "osci", "sync",
                "pivot", "nova", "domi", "ferri", "diamo", "mission", "ambi"
            ]
            
            for pattern in brand_patterns:
                if pattern in name_lower:
                    return ("sex_toy", "generic")
                    
            # Generic patterns that might indicate adult toys
            generic_patterns = ["vibe", "toy", "pulse", "intimate", "pleasure"]
            for pattern in generic_patterns:
                if pattern in name_lower:
                    return ("potential_sex_toy", "generic")
                
        return (None, None)
        
    async def _find_ble_device(self, address: str) -> Optional[BLEDeviceType]:
        """Find BLE device object by address for connection."""
        try:
            devices = await BleakScanner.discover()
            for device in devices:
                if device.address == address:
                    return device
            return None
        except Exception as e:
            self._logger.error(f"Error finding BLE device {address}: {e}")
            return None
            
    async def _discover_device_services(self, client: BleakClient, device_info: BluetoothDeviceInfo) -> None:
        """Discover and log device services and characteristics."""
        try:
            services = client.services
            self._logger.info(f"Device {device_info.address} services:")
            
            for service in services:
                self._logger.info(f"  Service: {service.uuid}")
                for char in service.characteristics:
                    self._logger.info(f"    Characteristic: {char.uuid} (properties: {char.properties})")
                    
        except Exception as e:
            self._logger.error(f"Error discovering services for {device_info.address}: {e}")
            
    def _notify_device_callbacks(self) -> None:
        """Notify all callbacks of device list changes."""
        if self._shutdown:
            return
            
        devices = self.get_discovered_devices()
        for callback in self._device_callbacks:
            try:
                callback(devices)
            except Exception as e:
                if not self._shutdown:  # Don't log errors during shutdown
                    self._logger.error(f"Error in device callback: {e}")
                
    async def shutdown(self) -> None:
        """Shutdown scanner and disconnect all devices."""
        self._shutdown = True
        
        # Stop scanning first
        await self.stop_scanning()
        
        # Disconnect all connected devices
        for address in list(self._connected_clients.keys()):
            await self.disconnect_device(address)
            
        self._discovered_devices.clear()
        self._device_callbacks.clear()
        self._logger.info("Bluetooth scanner shutdown complete")
