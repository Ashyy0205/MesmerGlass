from __future__ import annotations
import asyncio, json, threading, time, traceback, contextlib
from dataclasses import dataclass
from typing import Optional, Any

import websockets  # websockets>=10
from websockets.exceptions import ConnectionClosed

WS_URL_DEFAULT = "ws://127.0.0.1:12345"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class _PulseReq:
    level: float   # 0..1
    ms: int        # duration


class PulseEngine:
    """
    Minimal Buttplug v3 client (ScalarCmd Vibrate) over websockets.

    - Non-blocking: runs its own asyncio loop in a thread.
    - Auto connect + handshake (RequestServerInfo v3).
    - StartScanning and periodic re-scan until a device is picked.
    - Auto reconnect.
    - Queues pulses while no device is ready.
    """

    def __init__(self, url: str = WS_URL_DEFAULT, quiet: bool = False) -> None:
        self.url = url
        self.quiet = quiet

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._enabled = False
        self._should_stop = threading.Event()

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self._device_idx: Optional[int] = None

        self._pending: list[_PulseReq] = []
        self._last_level: float = 0.0

    # ---------------- public API (UI thread) ----------------
    def start(self) -> None:
        if self._enabled:
            return
        self._enabled = True
        self._should_stop.clear()
        self._thread = threading.Thread(target=self._thread_main, name="PulseEngine", daemon=True)
        self._thread.start()
        if not self.quiet:
            print("[pulse] started")

    def stop(self, quiet: Optional[bool] = None) -> None:
        if quiet is not None:
            self.quiet = quiet
        self._enabled = False
        self._should_stop.set()
        loop = self._loop
        if loop:
            asyncio.run_coroutine_threadsafe(self._close_ws(), loop)
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=1.5)
        self._thread = None
        if not self.quiet:
            print("[pulse] stopped")

    def set_level(self, level: float) -> None:
        level = float(clamp(level, 0.0, 1.0))
        self._last_level = level
        self._submit_coroutine(self._send_scalar(level))

    def pulse(self, level: float, ms: int) -> None:
        level = float(clamp(level, 0.0, 1.0))
        ms = max(10, int(ms))
        if not self._loop:
            self._pending.append(_PulseReq(level, ms))
            return
        self._submit_coroutine(self._do_pulse(level, ms))

    # ---------------- loop/thread ----------------
    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            try:
                for task in asyncio.all_tasks(loop=self._loop):
                    task.cancel()
            except Exception:
                pass
            self._loop.close()
            self._loop = None

    def _submit_coroutine(self, coro: Any) -> None:
        loop = self._loop
        if loop and self._enabled:
            try:
                asyncio.run_coroutine_threadsafe(coro, loop)
            except RuntimeError:
                pass

    # ---------------- core async flow ----------------
    async def _main(self) -> None:
        backoff = 0.5
        while self._enabled and not self._should_stop.is_set():
            try:
                await self._connect_and_run()
                backoff = 0.5
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.quiet:
                    print(f"[pulse] session error: {e}")
                    traceback.print_exc(limit=1)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 8.0)

    async def _connect_and_run(self) -> None:
        if not self.quiet:
            print(f"[pulse] connecting {self.url} ...")
        async with websockets.connect(
            self.url,
            ping_interval=20,
            ping_timeout=10,
            max_size=1_000_000,
        ) as ws:
            self._ws = ws
            self._device_idx = None

            # Handshake (messages must be wrapped in an array)
            await self._send({"RequestServerInfo": {
                "Id": self._next_id(),
                "ClientName": "MesmerGlass",
                "MessageVersion": 3
            }})
            await self._expect_server_info()

            # Device discovery
            await self._send({"RequestDeviceList": {"Id": self._next_id()}})
            await self._send({"StartScanning": {"Id": self._next_id()}})

            rescan_task = asyncio.create_task(self._rescan_until_device())
            await self._drain_pending()

            try:
                async for raw in ws:
                    await self._on_message(raw)
            finally:
                rescan_task.cancel()
                with contextlib.suppress(Exception):
                    await rescan_task

    # ---------------- helpers ----------------
    async def _close_ws(self) -> None:
        ws = self._ws
        self._ws = None
        if ws:
            with contextlib.suppress(Exception):
                await ws.close()

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def _send(self, obj: dict) -> None:
        """
        Send one Buttplug message — framed as a single-element ARRAY per v3 spec.
        """
        ws = self._ws
        if not ws:
            return
        # One-element array framing (required by some server builds)
        payload = json.dumps([obj], separators=(",", ":"))
        await ws.send(payload)
        if not self.quiet:
            print(">>", payload)

    async def _expect_server_info(self) -> None:
        # Wait until we see a ServerInfo message
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            if not self.quiet:
                print("<<", raw)
            try:
                data = json.loads(raw)
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if "ServerInfo" in item:
                    return
                # Some servers may send an Error before ServerInfo; keep looping.

    async def _rescan_until_device(self) -> None:
        while self._device_idx is None and self._ws:
            await asyncio.sleep(5.0)
            try:
                await self._send({"StartScanning": {"Id": self._next_id()}})
                await self._send({"RequestDeviceList": {"Id": self._next_id()}})
            except Exception:
                return

    async def _drain_pending(self) -> None:
        if not self._pending or self._device_idx is None:
            return
        for req in self._pending[:]:
            asyncio.create_task(self._do_pulse(req.level, req.ms))
            self._pending.remove(req)

    async def _on_message(self, raw: str) -> None:
        if not self.quiet:
            print("<<", raw)
        try:
            data = json.loads(raw)
        except Exception:
            return
        items = data if isinstance(data, list) else [data]
        for msg in items:
            if "Error" in msg:
                if not self.quiet:
                    print(f"[pulse] server error: {msg.get('Error')}")
            elif "DeviceList" in msg:
                for dev in msg["DeviceList"].get("Devices", []):
                    self._maybe_select_device(dev)
                await self._drain_pending()
            elif "DeviceAdded" in msg:
                self._maybe_select_device(msg["DeviceAdded"])
                await self._drain_pending()
            elif "DeviceRemoved" in msg:
                if msg["DeviceRemoved"].get("DeviceIndex") == self._device_idx:
                    self._device_idx = None

    def _maybe_select_device(self, dev: dict) -> None:
        if self._device_idx is not None:
            return
        idx = dev.get("DeviceIndex")
        msgs = dev.get("DeviceMessages", {})
        scalars = msgs.get("ScalarCmd", [])
        for s in scalars:
            if s.get("ActuatorType") == "Vibrate":
                self._device_idx = idx
                if not self.quiet:
                    print(f"[pulse] selected device idx={idx} name={dev.get('DeviceName')}")
                break

    # ---------------- commands ----------------
    async def _send_scalar(self, level: float) -> None:
        if self._device_idx is None:
            self._pending.append(_PulseReq(level, ms=0))
            return
        await self._send({
            "ScalarCmd": {
                "Id": self._next_id(),
                "DeviceIndex": self._device_idx,
                "Scalars": [{"Index": 0, "Scalar": float(clamp(level, 0.0, 1.0)), "ActuatorType": "Vibrate"}],
            }
        })

    async def _do_pulse(self, level: float, ms: int) -> None:
        if self._device_idx is None:
            self._pending.append(_PulseReq(level, ms))
            return
        await self._send_scalar(level)
        try:
            await asyncio.sleep(ms / 1000.0)
        finally:
            try:
                await self._send({"StopDeviceCmd": {"Id": self._next_id(), "DeviceIndex": self._device_idx}})
            except Exception:
                await self._send_scalar(0.0)
