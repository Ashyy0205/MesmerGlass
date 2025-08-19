from __future__ import annotations
import asyncio, json, threading, time, traceback, contextlib
import os, subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

import websockets  # websockets>=10
from websockets.exceptions import ConnectionClosed
from .buttplug_server import ButtplugServer
from .device_manager import DeviceManager
import logging

WS_URL_DEFAULT = "ws://127.0.0.1:12345"
MESMER_URL_DEFAULT = "ws://127.0.0.1:12350"


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

    @staticmethod
    def launch_intiface() -> bool:
        """Launch Intiface Central if not already running"""
        # Common install locations
        program_files = os.environ.get('PROGRAMFILES', 'C:\\Program Files')
        locations = [
            Path(program_files) / "Intiface" / "Intiface Central" / "Intiface Central.exe",
            Path(program_files) / "IntifaceCentral" / "Intiface Central.exe",
            Path(os.environ.get('LOCALAPPDATA', '')) / "Programs" / "Intiface Central" / "Intiface Central.exe"
        ]
        
        # Try to find and launch Intiface
        for path in locations:
            if path.exists():
                try:
                    subprocess.Popen([str(path)])
                    return True
                except Exception:
                    continue
        return False

    def __init__(self, url: str = WS_URL_DEFAULT, quiet: bool = False, server: Optional[ButtplugServer] = None, use_mesmer: bool = True, allow_auto_select: bool = True) -> None:
        # Respect an explicit URL by default; we'll only override to MesmerIntiface
        # in the common default case (no explicit server provided and using the
        # default classic URL). This keeps tests that pass a custom url/server working.
        self.url = url
        self.quiet = quiet
        self.use_mesmer = use_mesmer  # Use MesmerIntiface instead of external Intiface
        self.allow_auto_select = bool(allow_auto_select)  # Control auto-select behavior

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._enabled = False
        self._should_stop = threading.Event()

        # Websocket client protocol type varies across versions; keep it loose.
        self._ws: Optional[Any] = None
        self._msg_id = 0
        self._device_idx: Optional[int] = None
        self._devices_found = False  # Track if devices have been discovered

        self._pending: list[_PulseReq] = []
        self._last_level: float = 0.0

        # Device manager for tracking connected devices
        self.device_manager = DeviceManager()

        # Use provided server or create a new one
        self._server = server or ButtplugServer(port=int(url.split(":")[-1]))

        # Only override URL to MesmerIntiface when:
        #  - caller opted into Mesmer usage, AND
        #  - no explicit server instance was provided, AND
        #  - the URL wasn't explicitly set to a non-default value.
        # This avoids breaking unit tests that spin up their own server.
        if self.use_mesmer and server is None and (url == WS_URL_DEFAULT or not url):
            self.url = MESMER_URL_DEFAULT

    # ---------------- public API (UI thread) ----------------
    def start(self) -> None:
        if self._enabled:
            return
        
        # Start mock server only if not using MesmerIntiface
        self._enabled = True
        self._should_stop.clear()
        
        if not self.use_mesmer:
            # Only start bundled server if using classic mode
            pass  # Server should be started by launcher
            
        self._thread = threading.Thread(target=self._thread_main, name="PulseEngine", daemon=True)
        self._thread.start()
        if not self.quiet:
            logging.getLogger(__name__).info(
                "pulse engine started mode=%s",
                "MesmerIntiface" if self.use_mesmer else "Classic",
            )

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
        
        # Stop bundled server only if not using MesmerIntiface
        if not self.use_mesmer:
            self._server.stop()
        
        if not self.quiet:
            logging.getLogger(__name__).info("pulse engine stopped")

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
            except (RuntimeError, ValueError):
                # Event loop closed or invalid - ignore
                pass
        else:
            # If we didn't schedule the coroutine (engine disabled or loop missing),
            # explicitly close it to avoid "coroutine was never awaited" warnings.
            # This can happen during shutdown when UI code still calls set_level()/pulse.
            try:
                if hasattr(coro, "close"):
                    coro.close()  # type: ignore[attr-defined]
            except Exception:
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
                    logging.getLogger(__name__).warning("session error: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 8.0)

    async def _connect_and_run(self) -> None:
        if not self.quiet:
            logging.getLogger(__name__).info("connecting %s ...", self.url)
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
            logging.getLogger(__name__).debug(">> %s", payload)

    async def _expect_server_info(self) -> None:
        # Wait until we see a ServerInfo message
        ws = self._ws
        if not ws:
            return
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            if not self.quiet:
                logging.getLogger(__name__).debug("<< %s", raw)
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
        while not self._devices_found and self._ws:
            await asyncio.sleep(5.0)
            
            # Check if we have available devices before starting more scans
            device_list = self.device_manager.get_device_list()
            if device_list and device_list.devices:
                logging.getLogger(__name__).info(
                    "Found %d devices, stopping auto-scan", len(device_list.devices)
                )
                self._devices_found = True  # Set flag to prevent further scanning
                break
                
            try:
                logging.getLogger(__name__).debug("Starting scan for devices...")
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

    async def _on_message(self, raw: Any) -> None:
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8", errors="ignore")
            except Exception:
                return
        if not self.quiet:
            logging.getLogger(__name__).debug("<< %s", raw)
        try:
            data = json.loads(raw)
        except Exception:
            return
        items = data if isinstance(data, list) else [data]
        for msg in items:
            if "Error" in msg:
                if not self.quiet:
                    logging.getLogger(__name__).error("server error: %s", msg.get("Error"))
            elif "DeviceList" in msg:
                devices = msg["DeviceList"].get("Devices", [])
                if devices and not self._devices_found:
                    self._devices_found = True  # Mark that devices have been found
                    logging.getLogger(__name__).info(
                        "Device list received devices=%d stopping auto-scan",
                        len(devices),
                    )
                    
                for dev in devices:
                    self._maybe_select_device(dev)
                await self._drain_pending()
            elif "DeviceAdded" in msg:
                if not self._devices_found:
                    self._devices_found = True  # Mark that devices have been found
                    logging.getLogger(__name__).info("New device added, stopping auto-scan")
                    
                self._maybe_select_device(msg["DeviceAdded"])
                await self._drain_pending()
            elif "DeviceRemoved" in msg:
                removed_idx = msg["DeviceRemoved"].get("DeviceIndex")
                if removed_idx is not None:
                    self.device_manager.remove_device(removed_idx)
                    if removed_idx == self._device_idx:
                        self._device_idx = None
                        if not self.quiet:
                            logging.getLogger(__name__).info("device idx=%s disconnected", removed_idx)

    def _maybe_select_device(self, dev: dict) -> None:
        # Add device to device manager
        self.device_manager.add_device(dev)

        # If we already have a device selected, do nothing.
        if self._device_idx is not None:
            return

        # Prefer explicit selection from the device manager (e.g., UI choice),
        # regardless of allow_auto_select.
        selected_idx = self.device_manager.get_selected_index()
        if selected_idx is not None:
            self._device_idx = selected_idx
            if not self.quiet:
                logging.getLogger(__name__).info(
                    "using selected device idx=%s name=%s",
                    selected_idx,
                    dev.get("DeviceName"),
                )
            return

        # If auto-select is disabled, stop here.
        if not self.allow_auto_select:
            return

        # Auto-select first vibrator-capable device as a fallback.
        idx = dev.get("DeviceIndex")
        msgs = dev.get("DeviceMessages", {})
        scalars = msgs.get("ScalarCmd", [])
        for s in scalars:
            if s.get("ActuatorType") == "Vibrate":
                self._device_idx = idx
                if not self.quiet:
                    logging.getLogger(__name__).info(
                        "auto-selected device idx=%s name=%s", idx, dev.get("DeviceName")
                    )
                break
                
    def select_device_by_index(self, device_idx: Optional[int]) -> bool:
        """Manually select a device by index. Returns True if selection changed."""
        if self.device_manager.select_device(device_idx):
            self._device_idx = device_idx
            if not self.quiet:
                if device_idx is not None:
                    logging.getLogger(__name__).info(
                        "manually selected device idx=%s; stopping auto-scan", device_idx
                    )
                else:
                    logging.getLogger(__name__).info("cleared device selection")
            return True
        return False

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
