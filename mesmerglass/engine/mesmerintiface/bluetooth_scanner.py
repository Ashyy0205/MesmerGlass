"""Bluetooth Device Scanner

Pure Python Bluetooth Low Energy device discovery using the bleak library.
Scans for and identifies sex toys and haptic devices that support the Buttplug protocol.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass
import time  # monotonic timing for connection maintenance without relying on event loop time
from bleak import BleakScanner, BleakClient  # BLEDevice type imported below from backend for typing only
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
    
    def __init__(self, *, log_unknown: bool = False, repeat_interval: float = 30.0, verbose: bool = False):
        self._scanning = False
        self._scanner = None
        self._discovered_devices: Dict[str, BluetoothDeviceInfo] = {}
        self._device_callbacks: List[Callable[[List[BluetoothDeviceInfo]], None]] = []
        self._connected_clients: Dict[str, BleakClient] = {}
        # Maintenance / logging controls
        self._log_unknown = log_unknown
        self._repeat_interval = repeat_interval  # seconds between repeat INFO logs per device
        self._verbose = verbose
        self._last_log_times: Dict[str, float] = {}  # address -> last INFO log monotonic time
        self._seen_addresses: Set[str] = set()  # track addresses we've seen to avoid repeated 'first seen' logs for unknowns
        # Counters for summary-only mode
        self._adv_total = 0
        self._adv_identified = 0
        
        # Setup logging with console output
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(logging.INFO)
    # Rely on application/global logging config; avoid attaching our own stream handler
    # to prevent writing to closed streams during test runner shutdown.
            
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
            # Reset advertisement counters at scan start
            self._adv_total = 0
            self._adv_identified = 0
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
            # Emit summary line if any advertisements were seen
            try:
                if self._adv_total:
                    self._logger.info(
                        f"Scan found {self._adv_total} BLE advertisements ({self._adv_identified} recognized)"
                    )
            except Exception:
                pass
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
        """Handle detected Bluetooth device.

        Logging strategy:
        - Identify first; only log unknown devices at INFO if configured (_log_unknown or verbose).
        - Throttle per-address INFO logs using _last_log_times & repeat interval.
        - Always record address in _seen_addresses so we don't treat unknowns as perpetually new.
        """
        if self._shutdown:
            return
        try:
            addr = device.address
            # Count every advertisement
            self._adv_total += 1
            first_seen = addr not in self._seen_addresses
            if first_seen:
                self._seen_addresses.add(addr)

            device_info = BluetoothDeviceInfo(
                address=addr,
                name=device.name,
                rssi=advertisement_data.rssi,
                manufacturer_data=advertisement_data.manufacturer_data,
                service_uuids=[str(uuid) for uuid in advertisement_data.service_uuids],
            )
            device_type, protocol = self._identify_device(device_info)
            if device_type:
                self._adv_identified += 1
                device_info.device_type = device_type
                device_info.protocol = protocol
                self._discovered_devices[addr] = device_info
                # Throttle identified device logging (always at least once)
                now = time.monotonic(); last = self._last_log_times.get(addr, 0.0)
                if self._verbose or (now - last >= self._repeat_interval) or first_seen:
                    self._last_log_times[addr] = now
                    self._logger.info(
                        f"✅ Identified {device_type} device: {device.name or addr} RSSI: {advertisement_data.rssi}"
                    )
                else:
                    self._logger.debug(
                        f"BLE adv (id {device_type}): {device.name or addr} RSSI {advertisement_data.rssi}"
                    )
                if not self._shutdown:
                    try:
                        self._notify_device_callbacks()
                    except RuntimeError as e:
                        if "Event loop is closed" in str(e):
                            self._logger.debug("Callback skipped: event loop closed during shutdown")
                        else:
                            raise
            else:
                # Unknown device path: suppress per-device INFO in summary-only mode unless verbose/log_unknown
                if self._verbose or self._log_unknown:
                    now = time.monotonic(); last = self._last_log_times.get(addr, 0.0)
                    if self._verbose or (now - last >= self._repeat_interval) or first_seen:
                        self._last_log_times[addr] = now
                        self._logger.info(
                            f"Detected BLE device: {device.name or 'Unknown'} ({addr}) RSSI: {advertisement_data.rssi}"
                        )
                    else:
                        self._logger.debug(
                            f"BLE adv: {device.name or 'Unknown'} ({addr}) RSSI {advertisement_data.rssi}"
                        )
                # Not storing unknown devices to keep discovered list focused, unless future need arises.
        except Exception as e:
            if not self._shutdown:
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
        # Disable further logging from this component to avoid emitting to closed streams
        try:
            self._logger.info("Bluetooth scanner shutdown complete")
            self._logger.handlers.clear()
            self._logger.propagate = False
            self._logger.disabled = True
        except Exception:
            # Be defensive; shutdown should not raise
            pass

    # ------------------------------------------------------------------
    # Connection maintenance (no continuous scan)                       
    # ------------------------------------------------------------------
    async def _discover_once(self) -> List[BLEDeviceType]:
        """Perform a one-shot discovery (no continuous advertising callback).

        Separated for easier mocking in tests.
        """
        try:
            return await BleakScanner.discover()
        except Exception as e:
            self._logger.debug(f"One-shot discover failed: {e}")
            return []

    async def maintain_connections(self, addresses: List[str]) -> Dict[str, str]:
        """Ensure provided device addresses remain connected without continuous scanning.

        For each address:
        - If an active BleakClient is connected: status 'ok'.
        - Else attempt a one-shot discovery and reconnect: 'reconnected' on success, 'failed' on failure.

        Returns mapping address -> status.
        """
        results: Dict[str, str] = {}
        # Skip if shutting down or currently scanning (avoid contention with active scan)
        if self._shutdown:
            return results
        # Build quick lookup of one-shot discovery results only if any address needs reconnection.
        reconnect_needed = [
            a for a in addresses
            if not (a in self._connected_clients and self._connected_clients[a].is_connected)
        ]
        discovered_devices: List[BLEDeviceType] = []
        if reconnect_needed:
            discovered_devices = await self._discover_once()
        discover_map = {d.address: d for d in discovered_devices}
        for addr in addresses:
            try:
                if addr in self._connected_clients and self._connected_clients[addr].is_connected:
                    results[addr] = 'ok'
                    continue
                # Need reconnect
                if addr not in discover_map:
                    results[addr] = 'failed'
                    continue
                client = BleakClient(discover_map[addr])
                try:
                    await client.connect()
                except Exception as e:
                    self._logger.debug(f"Reconnect attempt failed for {addr}: {e}")
                    results[addr] = 'failed'
                    continue
                if client.is_connected:
                    self._connected_clients[addr] = client
                    di = self._discovered_devices.get(addr)
                    if di:
                        di.is_connected = True
                    results[addr] = 'reconnected'
                else:
                    results[addr] = 'failed'
            except Exception as e:
                self._logger.debug(f"Maintenance error for {addr}: {e}")
                results[addr] = 'failed'
        # Summarize log at INFO level (compact)
        if results:
            ok = sum(1 for s in results.values() if s == 'ok')
            rc = sum(1 for s in results.values() if s == 'reconnected')
            fail = sum(1 for s in results.values() if s == 'failed')
            self._logger.info(
                f"Connection maintenance: {ok} ok, {rc} reconnected, {fail} failed"
            )
        return results

    def set_verbose(self, verbose: bool) -> None:
        """Enable/disable verbose advertisement logging at runtime."""
        self._verbose = verbose
