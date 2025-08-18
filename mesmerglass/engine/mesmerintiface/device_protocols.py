"""Device Protocol Manager

Handles device-specific communication protocols for various sex toy manufacturers.
Each protocol implements the specific command format and characteristics for
device control.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class DeviceCapabilities:
    """Capabilities of a specific device."""
    has_vibrator: bool = False
    has_rotator: bool = False
    has_linear: bool = False
    has_battery: bool = False
    vibrator_count: int = 0
    rotator_count: int = 0
    linear_count: int = 0

class DeviceProtocol(ABC):
    """Abstract base class for device communication protocols."""
    
    def __init__(self, device_address: str, device_name: str):
        self.device_address = device_address
        self.device_name = device_name
        self.capabilities = DeviceCapabilities()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    @abstractmethod
    async def initialize(self, client) -> bool:
        """Initialize protocol with connected device client."""
        pass
        
    @abstractmethod
    async def vibrate(self, intensity: float, actuator_index: int = 0) -> bool:
        """Send vibration command to device."""
        pass
        
    @abstractmethod
    async def stop(self) -> bool:
        """Stop all device activity."""
        pass
        
    async def rotate(self, speed: float, clockwise: bool = True, actuator_index: int = 0) -> bool:
        """Send rotation command to device (if supported)."""
        return False
        
    async def linear(self, position: float, duration_ms: int, actuator_index: int = 0) -> bool:
        """Send linear movement command to device (if supported).""" 
        return False
        
    async def get_battery_level(self) -> Optional[int]:
        """Get device battery level (if supported)."""
        return None

class LovenseProtocol(DeviceProtocol):
    """Protocol implementation for Lovense devices."""
    
    # Lovense v1 service and characteristic UUIDs (older devices)
    SERVICE_UUID_V1 = "0000fff0-0000-1000-8000-00805f9b34fb"
    TX_CHAR_UUID_V1 = "0000fff2-0000-1000-8000-00805f9b34fb"  # Write
    RX_CHAR_UUID_V1 = "0000fff1-0000-1000-8000-00805f9b34fb"  # Notify
    
    # Lovense v2 service and characteristic UUIDs (newer devices like LVS-Hush)
    SERVICE_UUID_V2 = "5a300001-0023-4bd4-bbd5-a6920e4c5653"
    TX_CHAR_UUID_V2 = "5a300002-0023-4bd4-bbd5-a6920e4c5653"  # Write
    RX_CHAR_UUID_V2 = "5a300003-0023-4bd4-bbd5-a6920e4c5653"  # Notify
    
    def __init__(self, device_address: str, device_name: str):
        super().__init__(device_address, device_name)
        self._client = None
        self._device_type = self._identify_device_type(device_name)
        self._setup_capabilities()
        self._notification_active = False
        
        # Protocol version detection
        self._protocol_version = None
        self.SERVICE_UUID = None
        self.TX_CHAR_UUID = None
        self.RX_CHAR_UUID = None
        
    def _identify_device_type(self, name: str) -> str:
        """Identify specific Lovense device type from name."""
        if not name:
            return "unknown"
            
        name_lower = name.lower()
        if "max" in name_lower:
            return "max"
        elif "nora" in name_lower:
            return "nora"
        elif "lush" in name_lower:
            return "lush"
        elif "hush" in name_lower:
            return "hush"
        elif "edge" in name_lower:
            return "edge"
        elif "domi" in name_lower:
            return "domi"
        else:
            return "generic"
            
    def _setup_capabilities(self):
        """Setup device capabilities based on device type."""
        device_type = self._device_type
        
        if device_type == "max":
            self.capabilities.has_vibrator = True
            self.capabilities.vibrator_count = 1
        elif device_type == "nora":
            self.capabilities.has_vibrator = True
            self.capabilities.has_rotator = True
            self.capabilities.vibrator_count = 1
            self.capabilities.rotator_count = 1
        elif device_type in ["lush", "hush", "domi"]:
            self.capabilities.has_vibrator = True
            self.capabilities.vibrator_count = 1
        elif device_type == "edge":
            self.capabilities.has_vibrator = True
            self.capabilities.vibrator_count = 2
        else:
            # Generic Lovense device
            self.capabilities.has_vibrator = True
            self.capabilities.vibrator_count = 1
            
        # All Lovense devices have battery
        self.capabilities.has_battery = True
        
    async def initialize(self, client) -> bool:
        """Initialize Lovense protocol with connected client."""
        try:
            self._client = client
            
            # Detect protocol version by checking available services
            services = client.services
            v2_service = None
            v1_service = None
            
            for service in services:
                if service.uuid.lower() == self.SERVICE_UUID_V2.lower():
                    v2_service = service
                elif service.uuid.lower() == self.SERVICE_UUID_V1.lower():
                    v1_service = service
                    
            # Prefer v2 if available, fall back to v1
            if v2_service:
                self._logger.info(f"Detected Lovense v2 protocol for {self.device_name}")
                self.is_v2_protocol = True
                self.SERVICE_UUID = self.SERVICE_UUID_V2
                self.TX_CHAR_UUID = self.TX_CHAR_UUID_V2
                self.RX_CHAR_UUID = self.RX_CHAR_UUID_V2
            elif v1_service:
                self._logger.info(f"Detected Lovense v1 protocol for {self.device_name}")
                self.is_v2_protocol = False
                self.SERVICE_UUID = self.SERVICE_UUID_V1
                self.TX_CHAR_UUID = self.TX_CHAR_UUID_V1
                self.RX_CHAR_UUID = self.RX_CHAR_UUID_V1
            else:
                self._logger.error(f"No compatible Lovense service found for {self.device_name}")
                return False
            
            # Subscribe to notifications if available
            try:
                await client.start_notify(self.RX_CHAR_UUID, self._on_notification)
                self._notification_active = True
                self._logger.info(f"Subscribed to notifications on {self.RX_CHAR_UUID}")
            except Exception as e:
                self._logger.warning(f"Could not subscribe to notifications: {e}")
                
            self._logger.info(f"Initialized Lovense protocol for {self.device_name} using {'v2' if self.is_v2_protocol else 'v1'} UUIDs")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to initialize Lovense protocol: {e}")
            return False
            
    async def vibrate(self, intensity: float, actuator_index: int = 0) -> bool:
        """Send vibration command to Lovense device.
        
        Args:
            intensity: Vibration intensity (0.0 to 1.0)
            actuator_index: Which vibrator to control (for multi-vibrator devices)
        """
        if not self._client:
            return False
            
        try:
            # Convert intensity to Lovense scale (0-20)
            level = int(intensity * 20)
            level = max(0, min(20, level))
            
            # Build command based on device type and actuator
            if self._device_type == "edge" and actuator_index < 2:
                # Edge has two vibrators
                command = f"Vibrate1:{level};" if actuator_index == 0 else f"Vibrate2:{level};"
            else:
                # Single vibrator devices
                command = f"Vibrate:{level};"
                
            # Send command
            await self._client.write_gatt_char(
                self.TX_CHAR_UUID, 
                command.encode('utf-8')
            )
            
            self._logger.debug(f"Sent vibrate command: {command}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to send vibrate command: {e}")
            return False
            
    async def rotate(self, speed: float, clockwise: bool = True, actuator_index: int = 0) -> bool:
        """Send rotation command to Lovense device (Nora only)."""
        if not self._client or self._device_type != "nora":
            return False
            
        try:
            # Convert speed to Lovense scale (0-20)
            level = int(speed * 20)
            level = max(0, min(20, level))
            
            # Direction: True = clockwise, False = counter-clockwise
            direction = "True" if clockwise else "False"
            command = f"Rotate:{level},{direction};"
            
            await self._client.write_gatt_char(
                self.TX_CHAR_UUID,
                command.encode('utf-8')
            )
            
            self._logger.debug(f"Sent rotate command: {command}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to send rotate command: {e}")
            return False
            
    async def stop(self) -> bool:
        """Stop all Lovense device activity."""
        if not self._client:
            return False
            
        try:
            # Stop all functions
            commands = ["Vibrate:0;"]
            
            if self._device_type == "edge":
                commands.extend(["Vibrate1:0;", "Vibrate2:0;"])
            elif self._device_type == "nora":
                commands.append("Rotate:0;")
                
            # Send all stop commands
            for command in commands:
                await self._client.write_gatt_char(
                    self.TX_CHAR_UUID,
                    command.encode('utf-8')
                )
                
            self._logger.debug("Sent stop commands")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to send stop command: {e}")
            return False
            
    async def cleanup(self) -> bool:
        """Clean up the protocol, stopping notifications."""
        if not self._client:
            return True
            
        try:
            # Stop notifications if they were started
            if self._notification_active and self.RX_CHAR_UUID:
                try:
                    await self._client.stop_notify(self.RX_CHAR_UUID)
                    self._notification_active = False
                    self._logger.debug("Stopped notifications")
                except Exception as e:
                    self._logger.warning(f"Could not stop notifications: {e}")
                    
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to cleanup protocol: {e}")
            return False
            
    async def get_battery_level(self) -> Optional[int]:
        """Get battery level from Lovense device."""
        if not self._client:
            return None
            
        try:
            # Request battery level
            command = "Battery;"
            await self._client.write_gatt_char(
                self.TX_CHAR_UUID,
                command.encode('utf-8')
            )
            
            # Note: Response will come via notification
            return None  # Async response
            
        except Exception as e:
            self._logger.error(f"Failed to request battery level: {e}")
            return None
            
    def _on_notification(self, sender, data: bytearray):
        """Handle notifications from Lovense device."""
        # Completely silent callback during shutdown to avoid event loop errors
        if not self._notification_active:
            return
            
        try:
            message = data.decode('utf-8')
            self._logger.debug(f"Received notification: {message}")
            
            # Parse battery responses
            if message.startswith("Battery:"):
                battery_level = int(message.split(":")[1])
                self._logger.info(f"Battery level: {battery_level}%")
                
        except Exception:
            # Completely silent - ignore all errors during notification processing
            # This prevents the "Event loop is closed" errors from showing up
            pass

class WeVibeProtocol(DeviceProtocol):
    """Protocol implementation for We-Vibe devices."""
    
    # We-Vibe service UUID (example)
    SERVICE_UUID = "f000aa80-0451-4000-b000-000000000000"
    CONTROL_CHAR_UUID = "f000aa81-0451-4000-b000-000000000000"
    
    def __init__(self, device_address: str, device_name: str):
        super().__init__(device_address, device_name)
        self._client = None
        self.capabilities.has_vibrator = True
        self.capabilities.vibrator_count = 1
        
    async def initialize(self, client) -> bool:
        """Initialize We-Vibe protocol."""
        try:
            self._client = client
            self._logger.info(f"Initialized We-Vibe protocol for {self.device_name}")
            return True
        except Exception as e:
            self._logger.error(f"Failed to initialize We-Vibe protocol: {e}")
            return False
            
    async def vibrate(self, intensity: float, actuator_index: int = 0) -> bool:
        """Send vibration command to We-Vibe device."""
        if not self._client:
            return False
            
        try:
            # Convert intensity to We-Vibe format (implementation would be device-specific)
            level = int(intensity * 255)  # Example: 0-255 scale
            command = bytes([0x01, level])  # Example command format
            
            await self._client.write_gatt_characteristic(
                self.CONTROL_CHAR_UUID,
                command
            )
            
            self._logger.debug(f"Sent We-Vibe vibrate command: {level}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to send We-Vibe vibrate command: {e}")
            return False
            
    async def stop(self) -> bool:
        """Stop We-Vibe device."""
        return await self.vibrate(0.0)

class DeviceProtocolManager:
    """Manages device protocol implementations."""
    
    PROTOCOL_MAP = {
        "lovense": LovenseProtocol,
        "lovense_uart": LovenseProtocol,
        "we_vibe": WeVibeProtocol,
        "generic": LovenseProtocol,  # Default to Lovense for generic devices
    }
    
    @classmethod
    def create_protocol(cls, protocol_name: str, device_address: str, device_name: str) -> Optional[DeviceProtocol]:
        """Create appropriate protocol instance for device.
        
        Args:
            protocol_name: Name of protocol to use
            device_address: Bluetooth address of device
            device_name: Name of device
            
        Returns:
            Protocol instance or None if unsupported
        """
        protocol_class = cls.PROTOCOL_MAP.get(protocol_name)
        if protocol_class:
            return protocol_class(device_address, device_name)
        return None
        
    @classmethod
    def get_supported_protocols(cls) -> List[str]:
        """Get list of supported protocol names."""
        return list(cls.PROTOCOL_MAP.keys())
