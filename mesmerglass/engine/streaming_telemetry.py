"""Thread-safe streaming telemetry snapshot for the UI.

The VR streaming server runs on its own thread / event loop. The Qt UI polls
for a lightweight snapshot to display streaming-related metrics.

This avoids importing the full streaming server into the UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import time


@dataclass(frozen=True)
class StreamingClientSnapshot:
    client_id: str
    connected: bool
    address: str | None
    device_name: str | None

    protocol: str | None
    bitrate_bps: int | None

    send_fps: float | None
    produced_fps: float | None

    encode_avg_ms: float | None
    send_avg_ms: float | None
    bandwidth_mbps: float | None
    frame_kb: float | None

    client_buffer_ms: int | None
    client_fps_milli: int | None

    client_decode_avg_ms: float | None

    last_client_stats_age_s: float | None
    last_update_age_s: float | None


@dataclass(frozen=True)
class StreamingSnapshot:
    clients: list[StreamingClientSnapshot]


class StreamingTelemetry:
    def __init__(self) -> None:
        self._lock = Lock()

        # client_id -> mutable state
        self._clients: dict[str, dict] = {}

    def _ensure_client(self, client_id: str) -> dict:
        st = self._clients.get(client_id)
        if st is None:
            st = {
                "connected": False,
                "address": None,
                "device_name": None,
                "protocol": None,
                "bitrate_bps": None,
                "send_fps": None,
                "produced_fps": None,
                "encode_avg_ms": None,
                "send_avg_ms": None,
                "bandwidth_mbps": None,
                "frame_kb": None,
                "client_buffer_ms": None,
                "client_fps_milli": None,
                "client_decode_avg_ms": None,
                "last_client_stats_t": None,
                "last_update_t": None,
            }
            self._clients[client_id] = st
        return st

    def set_connected(
        self,
        client_id: str,
        connected: bool,
        *,
        address: str | None = None,
        device_name: str | None = None,
        protocol: str | None = None,
        bitrate_bps: int | None = None,
    ) -> None:
        now = time.time()
        with self._lock:
            st = self._ensure_client(str(client_id))
            st["connected"] = bool(connected)
            if address is not None:
                st["address"] = str(address)
            if device_name is not None:
                st["device_name"] = str(device_name)
            if protocol is not None:
                st["protocol"] = str(protocol)
            if bitrate_bps is not None:
                st["bitrate_bps"] = int(bitrate_bps)
            st["last_update_t"] = now

    def update_client_stats(
        self,
        client_id: str,
        *,
        buffer_ms: int | None,
        fps_milli: int | None,
        decode_avg_ms: float | None = None,
    ) -> None:
        now = time.time()
        with self._lock:
            st = self._ensure_client(str(client_id))
            if buffer_ms is not None:
                st["client_buffer_ms"] = int(buffer_ms)
            if fps_milli is not None:
                st["client_fps_milli"] = int(fps_milli)
            if decode_avg_ms is not None:
                st["client_decode_avg_ms"] = float(decode_avg_ms)
            st["last_client_stats_t"] = now
            st["last_update_t"] = now

    def update_server_stats(
        self,
        client_id: str,
        *,
        protocol: str | None = None,
        bitrate_bps: int | None = None,
        send_fps: float | None = None,
        produced_fps: float | None = None,
        encode_avg_ms: float | None = None,
        send_avg_ms: float | None = None,
        bandwidth_mbps: float | None = None,
        frame_kb: float | None = None,
        client_buffer_ms: int | None = None,
        client_fps_milli: int | None = None,
    ) -> None:
        now = time.time()
        with self._lock:
            st = self._ensure_client(str(client_id))
            if protocol is not None:
                st["protocol"] = str(protocol)
            if bitrate_bps is not None:
                st["bitrate_bps"] = int(bitrate_bps)
            if send_fps is not None:
                st["send_fps"] = float(send_fps)
            if produced_fps is not None:
                st["produced_fps"] = float(produced_fps)
            if encode_avg_ms is not None:
                st["encode_avg_ms"] = float(encode_avg_ms)
            if send_avg_ms is not None:
                st["send_avg_ms"] = float(send_avg_ms)
            if bandwidth_mbps is not None:
                st["bandwidth_mbps"] = float(bandwidth_mbps)
            if frame_kb is not None:
                st["frame_kb"] = float(frame_kb)
            if client_buffer_ms is not None:
                st["client_buffer_ms"] = int(client_buffer_ms)
            if client_fps_milli is not None:
                st["client_fps_milli"] = int(client_fps_milli)

            st["last_update_t"] = now

    def snapshot(self) -> StreamingSnapshot:
        now = time.time()
        with self._lock:
            items = list(self._clients.items())

        clients: list[StreamingClientSnapshot] = []
        for client_id, st in items:
            last_client_stats_t = st.get("last_client_stats_t")
            last_update_t = st.get("last_update_t")
            last_client_stats_age_s = None
            if last_client_stats_t is not None:
                last_client_stats_age_s = max(0.0, now - float(last_client_stats_t))
            last_update_age_s = None
            if last_update_t is not None:
                last_update_age_s = max(0.0, now - float(last_update_t))

            clients.append(
                StreamingClientSnapshot(
                    client_id=str(client_id),
                    connected=bool(st.get("connected", False)),
                    address=st.get("address"),
                    device_name=st.get("device_name"),
                    protocol=st.get("protocol"),
                    bitrate_bps=st.get("bitrate_bps"),
                    send_fps=st.get("send_fps"),
                    produced_fps=st.get("produced_fps"),
                    encode_avg_ms=st.get("encode_avg_ms"),
                    send_avg_ms=st.get("send_avg_ms"),
                    bandwidth_mbps=st.get("bandwidth_mbps"),
                    frame_kb=st.get("frame_kb"),
                    client_buffer_ms=st.get("client_buffer_ms"),
                    client_fps_milli=st.get("client_fps_milli"),
                    client_decode_avg_ms=st.get("client_decode_avg_ms"),
                    last_client_stats_age_s=last_client_stats_age_s,
                    last_update_age_s=last_update_age_s,
                )
            )

        # Stable ordering for display: device_name then client_id.
        clients.sort(key=lambda c: ((c.device_name or "").lower(), c.client_id.lower()))
        return StreamingSnapshot(clients=clients)


streaming_telemetry = StreamingTelemetry()

__all__ = [
    "StreamingClientSnapshot",
    "StreamingSnapshot",
    "StreamingTelemetry",
    "streaming_telemetry",
]
