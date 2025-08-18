"""MesmerIntiface Server

Main server implementation that integrates Bluetooth device scanning and control
with the existing Buttplug protocol WebSocket interface. This provides a complete
replacement for Intiface Central within MesmerGlass.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
from ..buttplug_server import ButtplugServer, Device, DeviceList
from .bluetooth_scanner import BluetoothDeviceScanner, BluetoothDeviceInfo
from .device_protocols import DeviceProtocolManager, DeviceProtocol
from .device_database import DeviceDatabase, DeviceDefinition

class MesmerIntifaceServer(ButtplugServer):
    """Enhanced Buttplug server with real Bluetooth device support."""
    
    def __init__(self, port: int = 12345):
        super().__init__(port)
        
        # Bluetooth components
        self._bluetooth_scanner = BluetoothDeviceScanner()
        self._device_database = DeviceDatabase()
        self._protocol_manager = DeviceProtocolManager()
        
        # Device tracking
        self._bluetooth_devices: Dict[str, BluetoothDeviceInfo] = {}
        self._device_protocols: Dict[str, DeviceProtocol] = {}
        self._device_index_map: Dict[str, int] = {}  # address -> buttplug index
        self._next_device_index = 1
        
        # Setup logging
        self._logger = logging.getLogger(__name__)
        
        # Connect scanner callbacks
        self._bluetooth_scanner.add_device_callback(self._on_bluetooth_devices_changed)
        
    async def start_real_scanning(self) -> bool:
        """Start scanning for real Bluetooth devices.
        
        Returns:
            True if scanning started successfully
        """
        try:
            success = await self._bluetooth_scanner.start_scanning()
            if success:
                self._logger.info("Started Bluetooth device scanning")
            return success
        except Exception as e:
            self._logger.error(f"Failed to start Bluetooth scanning: {e}")
            return False
            
    async def stop_real_scanning(self) -> None:
        """Stop Bluetooth device scanning."""
        try:
            await self._bluetooth_scanner.stop_scanning()
            self._logger.info("Stopped Bluetooth device scanning")
        except Exception as e:
            self._logger.error(f"Error stopping Bluetooth scanning: {e}")
            
    def is_real_scanning(self) -> bool:
        """Check if Bluetooth scanning is active."""
        return self._bluetooth_scanner.is_scanning()
        
    async def connect_real_device(self, device_index: int) -> bool:
        """Connect to a real Bluetooth device.
        
        Args:
            device_index: Buttplug device index
            
        Returns:
            True if connection successful
        """
        # Find device by index
        address = None
        for addr, idx in self._device_index_map.items():
            if idx == device_index:
                address = addr
                break
                
        if not address:
            self._logger.error(f"Device index {device_index} not found")
            return False
            
        try:
            # Connect via Bluetooth scanner
            success = await self._bluetooth_scanner.connect_device(address)
            if success:
                # Initialize protocol
                await self._initialize_device_protocol(address)
                self._logger.info(f"Connected to device index {device_index}")
                
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to connect to device {device_index}: {e}")
            return False
            
    async def disconnect_real_device(self, device_index: int) -> bool:
        """Disconnect from a real Bluetooth device.
        
        Args:
            device_index: Buttplug device index
            
        Returns:
            True if disconnection successful
        """
        # Find device address
        address = None
        for addr, idx in self._device_index_map.items():
            if idx == device_index:
                address = addr
                break
                
        if not address:
            return True  # Already disconnected
            
        try:
            # Disconnect via Bluetooth scanner
            success = await self._bluetooth_scanner.disconnect_device(address)
            
            # Clean up protocol
            if address in self._device_protocols:
                del self._device_protocols[address]
                
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to disconnect device {device_index}: {e}")
            return False
            
    async def send_real_device_command(self, device_index: int, command_type: str, **kwargs) -> bool:
        """Send command to a real device.
        
        Args:
            device_index: Buttplug device index
            command_type: Type of command ('vibrate', 'rotate', 'stop', etc.)
            **kwargs: Command parameters
            
        Returns:
            True if command sent successfully
        """
        # Find device address
        address = None
        for addr, idx in self._device_index_map.items():
            if idx == device_index:
                address = addr
                break
                
        if not address or address not in self._device_protocols:
            self._logger.error(f"Device {device_index} not connected or no protocol")
            return False
            
        try:
            protocol = self._device_protocols[address]
            
            if command_type == "vibrate":
                intensity = kwargs.get("intensity", 0.0)
                actuator_index = kwargs.get("actuator_index", 0)
                return await protocol.vibrate(intensity, actuator_index)
                
            elif command_type == "rotate":
                speed = kwargs.get("speed", 0.0)
                clockwise = kwargs.get("clockwise", True)
                actuator_index = kwargs.get("actuator_index", 0)
                return await protocol.rotate(speed, clockwise, actuator_index)
                
            elif command_type == "linear":
                position = kwargs.get("position", 0.0)
                duration_ms = kwargs.get("duration_ms", 1000)
                actuator_index = kwargs.get("actuator_index", 0)
                return await protocol.linear(position, duration_ms, actuator_index)
                
            elif command_type == "stop":
                return await protocol.stop()
                
            else:
                self._logger.error(f"Unknown command type: {command_type}")
                return False
                
        except Exception as e:
            self._logger.error(f"Failed to send {command_type} command to device {device_index}: {e}")
            return False
            
    async def _process_message(self, websocket, raw: str):
        """Enhanced message processing with real device support."""
        try:
            import json
            data = json.loads(raw)
            msgs = data if isinstance(data, list) else [data]
            
            for msg in msgs:
                # Enhanced StartScanning with real devices
                if "StartScanning" in msg:
                    msg_id = msg["StartScanning"]["Id"]
                    self._logger.info("Starting real device scan")
                    
                    success = await self.start_real_scanning()
                    if success:
                        await self._send(websocket, {"Ok": {"Id": msg_id}})
                    else:
                        await self._send(websocket, {
                            "Error": {
                                "Id": msg_id,
                                "ErrorMessage": "Failed to start Bluetooth scanning"
                            }
                        })
                    continue
                    
                # Enhanced StopScanning
                elif "StopScanning" in msg:
                    msg_id = msg["StopScanning"]["Id"]
                    await self.stop_real_scanning()
                    await self._send(websocket, {"Ok": {"Id": msg_id}})
                    continue
                    
                # Enhanced ScalarCmd with real device control
                elif "ScalarCmd" in msg:
                    cmd = msg["ScalarCmd"]
                    msg_id = cmd.get("Id", 0)
                    device_index = cmd.get("DeviceIndex", 0)
                    
                    if "Scalars" in cmd and cmd["Scalars"]:
                        scalar_info = cmd["Scalars"][0]
                        intensity = scalar_info.get("Scalar", 0.0)
                        actuator_index = scalar_info.get("Index", 0)
                        
                        # Send to real device
                        success = await self.send_real_device_command(
                            device_index, 
                            "vibrate", 
                            intensity=intensity,
                            actuator_index=actuator_index
                        )
                        
                        if success:
                            await self._send(websocket, {"Ok": {"Id": msg_id}})
                        else:
                            await self._send(websocket, {
                                "Error": {
                                    "Id": msg_id,
                                    "ErrorMessage": f"Failed to control device {device_index}"
                                }
                            })
                    continue
                    
                # Enhanced StopDeviceCmd
                elif "StopDeviceCmd" in msg:
                    cmd = msg["StopDeviceCmd"]
                    msg_id = cmd.get("Id", 0)
                    device_index = cmd.get("DeviceIndex", 0)
                    
                    success = await self.send_real_device_command(device_index, "stop")
                    if success:
                        await self._send(websocket, {"Ok": {"Id": msg_id}})
                    else:
                        await self._send(websocket, {
                            "Error": {
                                "Id": msg_id,
                                "ErrorMessage": f"Failed to stop device {device_index}"
                            }
                        })
                    continue
                    
            # Fall back to parent for other messages
            await super()._process_message(websocket, raw)
            
        except Exception as e:
            self._logger.error(f"Error processing enhanced message: {e}")
            
    def _on_bluetooth_devices_changed(self, devices: List[BluetoothDeviceInfo]) -> None:
        """Handle changes in discovered Bluetooth devices."""
        try:
            # Update our device tracking
            self._bluetooth_devices = {dev.address: dev for dev in devices}
            
            # Convert to Buttplug devices and update device manager
            buttplug_devices = []
            
            for device in devices:
                # Skip devices that aren't sex toys
                if not device.device_type:
                    continue
                    
                # Assign Buttplug device index if new
                if device.address not in self._device_index_map:
                    self._device_index_map[device.address] = self._next_device_index
                    self._next_device_index += 1
                    
                device_index = self._device_index_map[device.address]
                
                # Identify device capabilities
                device_def = self._device_database.identify_device(
                    device.name, 
                    device.service_uuids
                )
                
                # Create Buttplug device messages based on capabilities
                device_messages = {}
                
                if device_def:
                    capabilities = device_def.capabilities
                    
                    # Add ScalarCmd for vibrators
                    if "vibrate" in capabilities:
                        vibrator_count = capabilities["vibrate"]
                        scalar_features = []
                        for i in range(vibrator_count):
                            scalar_features.append({
                                "Index": i,
                                "StepCount": 20,  # Lovense uses 0-20 scale
                                "ActuatorType": "Vibrate"
                            })
                        device_messages["ScalarCmd"] = scalar_features
                        
                    # Add RotateCmd for rotators
                    if "rotate" in capabilities:
                        rotator_count = capabilities["rotate"]
                        rotate_features = []
                        for i in range(rotator_count):
                            rotate_features.append({
                                "Index": i,
                                "StepCount": 20
                            })
                        device_messages["RotateCmd"] = rotate_features
                        
                else:
                    # Default vibrator capability
                    device_messages["ScalarCmd"] = [{
                        "Index": 0,
                        "StepCount": 20,
                        "ActuatorType": "Vibrate"
                    }]
                    
                # Always add stop command
                device_messages["StopDeviceCmd"] = {}
                
                # Create Buttplug device
                buttplug_device = Device(
                    index=device_index,
                    name=device.name or f"Device {device.address}",
                    device_messages=device_messages
                )
                
                buttplug_devices.append(buttplug_device)
                
            # Update device manager
            self._device_manager._device_list.devices = buttplug_devices
            
            # Notify callbacks
            self._notify_device_callbacks()
            
            self._logger.info(f"Updated device list: {len(buttplug_devices)} devices")
            
        except Exception as e:
            self._logger.error(f"Error updating devices: {e}")
            
    async def _initialize_device_protocol(self, address: str) -> bool:
        """Initialize protocol for a connected device."""
        try:
            device_info = self._bluetooth_devices.get(address)
            if not device_info:
                return False
                
            # Get device definition
            device_def = self._device_database.identify_device(
                device_info.name,
                device_info.service_uuids
            )
            
            protocol_name = device_def.protocol if device_def else device_info.protocol or "generic"
            
            # Create protocol instance
            protocol = self._protocol_manager.create_protocol(
                protocol_name,
                address,
                device_info.name or address
            )
            
            if protocol:
                # Initialize with Bluetooth client
                client = self._bluetooth_scanner._connected_clients.get(address)
                if client:
                    success = await protocol.initialize(client)
                    if success:
                        self._device_protocols[address] = protocol
                        self._logger.info(f"Initialized {protocol_name} protocol for {address}")
                        return True
                        
            return False
            
        except Exception as e:
            self._logger.error(f"Failed to initialize protocol for {address}: {e}")
            return False
            
    def get_device_list(self) -> "DeviceList":
        """Get the current device list."""
        return self._device_manager._device_list
    
    def _add_virtual_device(self, device_info: Dict) -> None:
        """Add a virtual device for testing purposes."""
        # Create Device object from device_info
        device = Device(
            index=device_info["DeviceIndex"],
            name=device_info["DeviceName"], 
            device_messages=device_info.get("DeviceMessages", {})
        )
        
        # Add to device list
        self._device_manager._device_list.devices.append(device)
        
        # Broadcast device addition to connected clients
        if self._clients:
            message = json.dumps([{
                "DeviceAdded": device_info
            }])
            
            for client in list(self._clients):
                try:
                    asyncio.create_task(client.send(message))
                except Exception:
                    self._clients.discard(client)
    
    async def shutdown(self) -> None:
        """Shutdown server and cleanup resources."""
        try:
            # Stop scanning
            await self.stop_real_scanning()
            
            # Disconnect all devices
            for address in list(self._device_protocols.keys()):
                device_index = self._device_index_map.get(address)
                if device_index:
                    await self.disconnect_real_device(device_index)
                    
            # Shutdown Bluetooth scanner
            await self._bluetooth_scanner.shutdown()
            
            # Call parent shutdown
            super().stop()
            
            self._logger.info("MesmerIntiface server shutdown complete")
            
        except Exception as e:
            self._logger.error(f"Error during shutdown: {e}")
            
    def get_status(self) -> Dict:
        """Get comprehensive server status."""
        bluetooth_devices = list(self._bluetooth_devices.values())
        connected_devices = [dev for dev in bluetooth_devices if dev.is_connected]
        
        return {
            "server_running": not self._stop,
            "bluetooth_scanning": self.is_real_scanning(),
            "discovered_devices": len(bluetooth_devices),
            "connected_devices": len(connected_devices),
            "active_protocols": len(self._device_protocols),
            "buttplug_devices": len(self._device_manager._device_list.devices),
            "device_types": list(set(dev.device_type for dev in bluetooth_devices if dev.device_type)),
            "supported_protocols": self._protocol_manager.get_supported_protocols()
        }
