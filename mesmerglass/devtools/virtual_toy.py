"""Deterministic Virtual Toy for development and CI.

Implements a minimal Buttplug v3 client that connects to a local
Buttplug-compatible server, advertises a single device, and reacts to
ScalarCmd/StopDeviceCmd.

Design goals:
- Deterministic: no randomness; immediate Ok acks; state updates applied
  after a configurable latency using a background task.
- Configurable mapping: linear or ease (gamma curve), with gain and offset.
- Windows-friendly: no long-running blocking operations; clean shutdown.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Literal
import websockets


@dataclass
class VirtualToyState:
    name: str
    index: int
    features: List[Dict[str, int]]
    level: float = 0.0
    is_active: bool = False


def _apply_mapping(raw: float, *, mapping: Literal["linear", "ease"], gain: float, gamma: float, offset: float) -> float:
    # Clamp helper
    def clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))
    x = clamp(raw, 0.0, 1.0)
    if mapping == "ease":
        # Gamma curve: y = x**gamma (gamma>=0); default gamma=1.0 => linear
        try:
            x = x ** max(0.0, float(gamma))
        except Exception:
            pass
    y = x * float(gain) + float(offset)
    return clamp(y, 0.0, 1.0)


class VirtualToy:
    """A virtual toy that implements the Buttplug client protocol.

    Parameters are optional and chosen for deterministic CI behavior.
    """

    def __init__(
        self,
        name: str = "Virtual Test Toy",
        port: int = 12345,
        *,
        latency_ms: int = 0,
        mapping: Literal["linear", "ease"] = "linear",
        gain: float = 1.0,
        gamma: float = 1.0,
        offset: float = 0.0,
        device_index: Optional[int] = None,
    ) -> None:
        self.name = name
        self.port = port
        self.uri = f"ws://127.0.0.1:{port}"
        # Type for client protocol varies across websockets versions; keep loose to avoid type issues
        self._ws: Optional[Any] = None  # noqa: ANN401
        self._msg_id = 0
        self.state = VirtualToyState(
            name=name,
            index=int(device_index) if device_index is not None else 0,
            features=[{"Index": 0, "StepCount": 100}],
            level=0.0,
            is_active=False,
        )
        self.latency_ms = max(0, int(latency_ms))
        self.mapping = mapping
        self.gain = float(gain)
        self.gamma = float(gamma)
        self.offset = float(offset)
        self._listener: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Connect to the server and advertise the device."""
        try:
            self._ws = await websockets.connect(self.uri)
            # Handshake
            await self._send({
                "RequestServerInfo": {
                    "Id": self._next_id(),
                    "ClientName": "Virtual Test Client",
                    "MessageVersion": 3,
                }
            })
            await self._expect_server_info()
            # Advertise device once connected
            await self._advertise_device()
            return True
        except Exception:
            await self.disconnect()
            return False

    async def start_listening(self) -> None:
        """Listen for commands until disconnected."""
        if not self._ws:
            return
        try:
            async for msg in self._ws:
                await self._handle_message(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.state.is_active = False

    async def disconnect(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        if self._listener:
            try:
                self._listener.cancel()
            except Exception:
                pass
            self._listener = None

    async def _handle_message(self, raw_msg: str) -> None:
        try:
            data = json.loads(raw_msg)
        except Exception:
            return
        msgs = data if isinstance(data, list) else [data]
        for msg in msgs:
            if "ScalarCmd" in msg:
                cmd = msg["ScalarCmd"]
                if cmd.get("DeviceIndex") != self.state.index:
                    continue
                scalars = cmd.get("Scalars", [])
                if not scalars:
                    continue
                scalar = float(scalars[0].get("Scalar", 0.0))
                msg_id = cmd.get("Id", 0)
                # Ack immediately for deterministic timing
                await self._send({"Ok": {"Id": msg_id}})
                # Schedule mapped application after latency
                asyncio.create_task(self._apply_after_latency(scalar))
            elif "StopDeviceCmd" in msg:
                cmd = msg["StopDeviceCmd"]
                if cmd.get("DeviceIndex") != self.state.index:
                    continue
                msg_id = cmd.get("Id", 0)
                await self._send({"Ok": {"Id": msg_id}})
                asyncio.create_task(self._apply_after_latency(0.0))
            elif "RequestDeviceList" in msg:
                await self._advertise_device(reply_id=msg.get("RequestDeviceList", {}).get("Id", 0))

    async def _apply_after_latency(self, target: float) -> None:
        # Optional latency simulation
        if self.latency_ms > 0:
            try:
                await asyncio.sleep(self.latency_ms / 1000.0)
            except Exception:
                return
        # Cast mapping to supported literal values at runtime (validated via choices in __init__ defaults)
        mapping: Literal["linear", "ease"] = "ease" if self.mapping == "ease" else "linear"
        mapped = _apply_mapping(
            target,
            mapping=mapping,
            gain=self.gain,
            gamma=self.gamma,
            offset=self.offset,
        )
        self.state.level = float(mapped)
        self.state.is_active = self.state.level > 0.0

    async def _advertise_device(self, reply_id: Optional[int] = None) -> None:
        payload = {
            "DeviceList": {
                "Id": self._next_id() if reply_id is None else reply_id,
                "Devices": [
                    {
                        "DeviceIndex": self.state.index,
                        "DeviceName": self.state.name,
                        "DeviceMessages": {
                            "ScalarCmd": [{"StepCount": 100, "ActuatorType": "Vibrate", "Features": self.state.features}],
                            "StopDeviceCmd": {},
                        },
                    }
                ],
            }
        }
        await self._send(payload)

    async def _send(self, msg: dict) -> None:
        if not self._ws:
            return
        try:
            await self._ws.send(json.dumps([msg]))
        except Exception:
            pass

    async def _expect_server_info(self) -> None:
        ws = self._ws
        if not ws:
            return
        while True:
            raw = await ws.recv()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            msgs = data if isinstance(data, list) else [data]
            for msg in msgs:
                if "ServerInfo" in msg:
                    return

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id
