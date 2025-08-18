"""Virtual toy implementation for testing the Buttplug protocol."""

import asyncio
import json
import websockets
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class VirtualToyState:
    """Represents the current state of a virtual toy."""
    name: str
    index: int
    features: List[Dict[str, int]]
    level: float = 0.0
    is_active: bool = False

class VirtualToy:
    """A virtual toy that implements the Buttplug client protocol."""
    
    def __init__(self, name: str = "Virtual Test Toy", port: int = 12345):
        self.name = name
        self.port = port
        self.uri = f"ws://127.0.0.1:{port}"
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self.state = VirtualToyState(
            name=name,
            index=0,
            features=[{"Index": 0, "StepCount": 100}],
            level=0.0,
            is_active=False
        )
        
    async def connect(self) -> bool:
        """Connect to the Buttplug server."""
        try:
            print(f"[virtual-toy] Connecting to {self.uri}")
            self._ws = await websockets.connect(self.uri)
            print(f"[virtual-toy] Connected to {self.uri}")
            
            # Perform handshake
            await self._send({
                "RequestServerInfo": {
                    "Id": self._next_id(),
                    "ClientName": "Virtual Test Client",
                    "MessageVersion": 3
                }
            })
            print("[virtual-toy] Sent handshake")
            await self._expect_server_info()
            # Force initial device list advertisement
            await self._send({
                "DeviceList": {
                    "Id": self._next_id(),
                    "Devices": [{
                        "DeviceIndex": self.state.index,
                        "DeviceName": self.state.name,
                        "DeviceMessages": {
                            "ScalarCmd": [{"StepCount": 100, "ActuatorType": "Vibrate", "Features": self.state.features}],
                            "StopDeviceCmd": {}
                        }
                    }]
                }
            })
            print("[virtual-toy] Connected successfully")
            return True
        except Exception as e:
            print(f"[virtual-toy] Connection failed: {e}")
            return False
            
    async def disconnect(self):
        """Disconnect from the server."""
        if self._ws:
            await self._ws.close()
            self._ws = None
            self.state.is_active = False
            print("[virtual-toy] Disconnected from server")
            
    async def start_listening(self):
        """Start listening for commands from the server."""
        if not self._ws:
            print("[virtual-toy] Cannot listen - not connected")
            return
            
        print("[virtual-toy] Started listening for commands")
        try:
            async for msg in self._ws:
                print(f"[virtual-toy] Received message: {msg}")
                await self._handle_message(msg)
        except websockets.exceptions.ConnectionClosed:
            print("[virtual-toy] Disconnected from server")
            self.state.is_active = False
            
    async def _handle_message(self, raw_msg: str):
        """Handle incoming messages from the server."""
        try:
            data = json.loads(raw_msg)
            msgs = data if isinstance(data, list) else [data]
            
            for msg in msgs:
                if "ScalarCmd" in msg:
                    cmd = msg["ScalarCmd"]
                    print(f"[virtual-toy] ScalarCmd received: {cmd}")
                    if cmd["DeviceIndex"] == self.state.index and "Scalars" in cmd:
                        scalar = cmd["Scalars"][0]["Scalar"]
                        # Update state before sending ack
                        self.state.level = float(scalar)
                        self.state.is_active = scalar > 0
                        # Send acknowledgment
                        await self._send({
                            "Ok": {
                                "Id": msg.get("Id", 0)
                            }
                        })
                        print(f"[virtual-toy] Level updated to {self.state.level:.1%}")
                        
                elif "StopDeviceCmd" in msg:
                    cmd = msg["StopDeviceCmd"]
                    if cmd["DeviceIndex"] == self.state.index:
                        self.state.level = 0.0
                        self.state.is_active = False
                        print("[virtual-toy] Stopped")
                        await self._send({
                            "Ok": {
                                "Id": msg.get("Id", 0)
                            }
                        })
                        
                elif "RequestDeviceList" in msg:
                    print("[virtual-toy] Received device list request")
                    await self._send({
                        "DeviceList": {
                            "Id": msg.get("Id", 0),
                            "Devices": [{
                                "DeviceIndex": self.state.index,
                                "DeviceName": self.state.name,
                                "DeviceMessages": {
                                    "ScalarCmd": [{"StepCount": 100, "ActuatorType": "Vibrate", "Features": self.state.features}],
                                    "StopDeviceCmd": {}
                                }
                            }]
                        }
                    })
        except Exception as e:
            print(f"[virtual-toy] Error processing message: {e}")
            
    async def _send(self, msg: dict):
        """Send a message to the server."""
        if not self._ws:
            return
        payload = json.dumps([msg])
        await self._ws.send(payload)
        
    async def _expect_server_info(self) -> None:
        """Wait for ServerInfo message during handshake."""
        if not self._ws:
            return
        while True:
            try:
                raw = await self._ws.recv()
                data = json.loads(raw)
                msgs = data if isinstance(data, list) else [data]
                for msg in msgs:
                    if "ServerInfo" in msg:
                        # Send device info
                        await self._send({
                            "DeviceList": {
                                "Id": self._next_id(),
                                "Devices": [{
                                    "DeviceIndex": self.state.index,
                                    "DeviceName": self.state.name,
                                    "DeviceMessages": {
                                        "ScalarCmd": [{"StepCount": 100, "ActuatorType": "Vibrate", "Features": self.state.features}],
                                        "StopDeviceCmd": {}
                                    }
                                }]
                            }
                        })
                        return
            except Exception as e:
                print(f"[virtual-toy] Handshake error: {e}")
                continue
                
    def _next_id(self) -> int:
        """Generate next message ID."""
        self._msg_id += 1
        return self._msg_id
        
    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._ws:
            await self._ws.close()
            self._ws = None
            print("[virtual-toy] Disconnected")
