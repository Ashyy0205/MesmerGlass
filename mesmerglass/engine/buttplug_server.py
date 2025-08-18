"""Buttplug protocol server implementation for device control."""

import asyncio
import json
import threading
import websockets
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass

@dataclass
class Device:
    """Represents a connected device."""
    index: int
    name: str
    device_messages: Dict[str, dict]

class DeviceList:
    """Manages a list of connected devices."""
    def __init__(self):
        self.devices: List[Device] = []
        self.selected_idx: Optional[int] = None
    
    @property
    def selected(self) -> Optional[Device]:
        """Get currently selected device."""
        if self.selected_idx is not None and 0 <= self.selected_idx < len(self.devices):
            return self.devices[self.selected_idx]
        return None

class DeviceManager:
    """Manages device discovery and selection."""
    def __init__(self):
        self._device_list = DeviceList()
        
    def get_device_list(self) -> DeviceList:
        """Get current device list."""
        return self._device_list
        
    def select_device(self, idx: Optional[int]) -> bool:
        """Select a device by index."""
        if idx is None:
            self._device_list.selected_idx = None
            return True
        if 0 <= idx < len(self._device_list.devices):
            self._device_list.selected_idx = idx
            return True
        return False

class ButtplugServer:
    """A Buttplug protocol server that handles device communication."""
    
    def __init__(self, port: int = 12345):
        self.port = port
        self._msg_id = 0
        self._stop = False
        self._thread = None
        self._clients = set()
        
        # Device management
        self._device_manager = DeviceManager()
        self._device_callbacks: List[Callable[[DeviceList], None]] = []
        
    def add_device_callback(self, callback: Callable[[DeviceList], None]) -> None:
        """Add callback for device list changes."""
        self._device_callbacks.append(callback)
        
    def remove_device_callback(self, callback: Callable[[DeviceList], None]) -> None:
        """Remove device callback."""
        if callback in self._device_callbacks:
            self._device_callbacks.remove(callback)
            
    def get_device_list(self) -> DeviceList:
        """Get current device list."""
        return self._device_manager.get_device_list()
        
    def select_device(self, idx: Optional[int]) -> None:
        """Select device to use."""
        if self._device_manager.select_device(idx):
            self._notify_device_callbacks()
            
    def _notify_device_callbacks(self) -> None:
        """Notify all callbacks of device list changes."""
        device_list = self._device_manager.get_device_list()
        for callback in self._device_callbacks:
            try:
                callback(device_list)
            except Exception as e:
                print(f"[server] Error in device callback: {e}")
        
    def start(self):
        """Start the WebSocket server."""
        # Run the async server in a new thread
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        print(f"[server] Server thread started with port {self.port}")
        
    def stop(self):
        """Stop the server."""
        self._stop = True
        print("[server] Stopping server...")
        
    def _run_server(self):
        """Run the WebSocket server in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_server():
            print(f"[server] Starting server on port {self.port}")
            async with websockets.serve(self._handle_client, "127.0.0.1", self.port):
                print("[server] Ready for connections")
                # Keep running until stopped
                while not self._stop:
                    await asyncio.sleep(1)
                    
        try:
            loop.run_until_complete(run_server())
        finally:
            loop.close()
                
    async def _handle_client(self, websocket):
        """Handle client connection."""
        try:
            self._clients.add(websocket)
            print("[server] Client connected")
            async for message in websocket:
                await self._process_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print("[server] Client disconnected")
        finally:
            self._clients.remove(websocket)
            
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
                            "ServerName": "MesmerGlass Virtual Server"
                        }
                    })
                    
                elif "RequestDeviceList" in msg:
                    # Send current device list
                    device_list = self._device_manager.get_device_list()
                    await self._send(websocket, {
                        "DeviceList": {
                            "Id": msg["RequestDeviceList"]["Id"],
                            "Devices": [
                                {
                                    "DeviceIndex": dev.index,
                                    "DeviceName": dev.name,
                                    "DeviceMessages": dev.device_messages
                                }
                                for dev in device_list.devices
                            ]
                        }
                    })
                    
                elif "StartScanning" in msg:
                    # Start scanning for devices
                    print("[server] Starting device scan")
                    msg_id = msg["StartScanning"]["Id"]
                    await self._send(websocket, {
                        "Ok": {
                            "Id": msg_id
                        }
                    })
                    
                elif "DeviceList" in msg:
                    # Handle device registration
                    device_list = msg["DeviceList"]
                    print("[server] Received device list")
                    current_devices = {(d.name, d.index) for d in self._device_manager._device_list.devices}
                    for device_info in device_list.get("Devices", []):
                        # Check if device already registered
                        device_key = (device_info["DeviceName"], device_info["DeviceIndex"])
                        if device_key not in current_devices:
                            # Add new device to our manager
                            device = Device(
                                index=device_info["DeviceIndex"],
                                name=device_info["DeviceName"],
                                device_messages=device_info.get("DeviceMessages", {})
                            )
                            self._device_manager._device_list.devices.append(device)
                            print(f"[server] Registered device: {device.name}")
                            # Notify callbacks of device list change
                            self._notify_device_callbacks()
                    # Send acknowledgment
                    if "Id" in device_list:
                        await self._send(websocket, {
                            "Ok": {
                                "Id": device_list["Id"]
                            }
                        })
                    
                elif "ScalarCmd" in msg:
                    cmd = msg["ScalarCmd"]
                    if "Id" in cmd:
                        msg_id = cmd["Id"]
                        print(f"[server] ScalarCmd received (id={msg_id})")
                        # Forward command to other clients
                        for client in self._clients:
                            if client != websocket:
                                await client.send(raw)
                        # Send acknowledgment back
                        await self._send(websocket, {
                            "Ok": {
                                "Id": msg_id
                            }
                        })
                        
                elif "StopDeviceCmd" in msg:
                    cmd = msg["StopDeviceCmd"]
                    if "Id" in cmd:
                        msg_id = cmd["Id"]
                        print(f"[server] StopDeviceCmd received (id={msg_id})")
                        # Forward command to other clients
                        for client in self._clients:
                            if client != websocket:
                                await client.send(raw)
                        # Send acknowledgment back
                        await self._send(websocket, {
                            "Ok": {
                                "Id": msg_id
                            }
                        })
                        
        except Exception as e:
            print(f"[server] Error processing message: {e}")
            
    async def _send(self, websocket, msg: dict):
        """Send a message to the client."""
        payload = json.dumps([msg])
        await websocket.send(payload)
        
    def _next_id(self) -> int:
        """Generate the next message ID."""
        self._msg_id += 1
        return self._msg_id
