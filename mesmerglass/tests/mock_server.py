"""Test server for MesmerGlass device testing."""

import asyncio
import json
import websockets
from typing import Optional, Dict

class MockServer:
    """A mock Buttplug server that simulates a device."""
    
    def __init__(self, port: int = 12345):
        self.port = port
        self._msg_id = 0
        self._devices: Dict[int, Dict] = {}
        self._stop = False
        
    async def start(self):
        """Start the WebSocket server."""
        print(f"[mock] Starting server on port {self.port}")
        async with websockets.serve(self._handle_client, "127.0.0.1", self.port):
            # Add a mock device
            self._devices[0] = {
                "DeviceIndex": 0,
                "DeviceName": "Test Vibrator",
                "DeviceMessages": {
                    "ScalarCmd": [
                        {"StepCount": 100, "ActuatorType": "Vibrate", "Features": [{"Index": 0, "StepCount": 100}]}
                    ],
                    "StopDeviceCmd": {}
                }
            }
            print("[mock] Ready with Test Vibrator device")
            
            # Keep running until stopped
            while not self._stop:
                await asyncio.sleep(1)
                
    async def _handle_client(self, websocket):
        """Handle client connection."""
        try:
            async for message in websocket:
                await self._process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print("[mock] Client disconnected")
            
    async def _process_message(self, websocket, raw: str):
        """Process incoming messages."""
        try:
            data = json.loads(raw)
            msgs = data if isinstance(data, list) else [data]
            
            for msg in msgs:
                if "RequestServerInfo" in msg:
                    await self._send(websocket, {
                        "ServerInfo": {
                            "Id": msg["RequestServerInfo"]["Id"],
                            "MessageVersion": 3,
                            "MaxPingTime": 0,
                            "ServerName": "Mock Server"
                        }
                    })
                    
                elif "RequestDeviceList" in msg:
                    await self._send(websocket, {
                        "DeviceList": {
                            "Id": msg["RequestDeviceList"]["Id"],
                            "Devices": list(self._devices.values())
                        }
                    })
                    
                elif "StartScanning" in msg:
                    # Immediately notify about our mock device
                    await self._send(websocket, {
                        "DeviceAdded": {
                            "Id": self._next_id(),
                            **self._devices[0]
                        }
                    })
                    
                elif "ScalarCmd" in msg:
                    cmd = msg["ScalarCmd"]
                    if cmd["DeviceIndex"] == 0:  # Our test device
                        scalar = cmd["Scalars"][0]["Scalar"]
                        print(f"[mock] Vibration level: {scalar:.1%}")
                        
                elif "StopDeviceCmd" in msg:
                    cmd = msg["StopDeviceCmd"]
                    if cmd["DeviceIndex"] == 0:  # Our test device
                        print("[mock] Stopped")
                        
        except Exception as e:
            print(f"[mock] Error processing message: {e}")
            
    async def _send(self, websocket, msg: dict):
        """Send a message to the client."""
        payload = json.dumps([msg])
        await websocket.send(payload)
        
    def _next_id(self) -> int:
        """Generate the next message ID."""
        self._msg_id += 1
        return self._msg_id

async def main():
    """Run the mock server."""
    print("Starting mock Buttplug server...")
    print("1. Start MesmerGlass")
    print("2. Go to the Device tab")
    print("3. Enable device sync")
    print("4. Try the buzz features")
    print()
    
    server = MockServer()
    await server.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
