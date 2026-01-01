"""
VR Streaming Server

TCP/UDP server for streaming live visuals to VR headsets.
Supports automatic device discovery via UDP broadcast.
"""

import asyncio
import socket
import struct
import logging
import time
import threading
import zlib
from collections import deque
import numpy as np
import cv2
from typing import Optional, Set, Tuple, Callable
from queue import Queue, Empty

from pathlib import Path
import os
import datetime

from .frame_encoder import FrameEncoder, create_encoder, encode_stereo_frames
from .gpu_utils import EncoderType, select_encoder

logger = logging.getLogger(__name__)

# Windows-specific benign shutdown/cancel artifacts.
# - 995: operation aborted
# - 10038: socket operation on non-socket
# - 6: invalid handle (often shows up when cancelling overlapped futures during loop teardown)
_WIN_ABORT_ERRNOS = {6, 995, 10038}


class DiscoveryService:
    """UDP discovery service for automatic VR headset detection"""
    
    def __init__(self, discovery_port: int = 5556, streaming_port: int = 5555, manual_devices: list = None):
        """
        Initialize discovery service
        
        Args:
            discovery_port: UDP port for discovery broadcasts (5556 - original working port)
            streaming_port: TCP port for streaming (5555 - original working port)
            manual_devices: List of manually configured devices [{"ip": str, "name": str}]
        """
        self.discovery_port = discovery_port
        self.streaming_port = streaming_port
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.discovered_devices: dict = {}  # {ip: {"name": str, "ip": str, "last_seen": float}}
        self.manual_device_ips: set = set()  # Track which devices are manual (never expire)
        self._devices_lock = threading.Lock()  # CRITICAL: Protect discovered_devices from race conditions
        
        # Add manually configured devices (for when broadcast discovery fails)
        if manual_devices:
            with self._devices_lock:
                for device in manual_devices:
                    ip = device.get("ip")
                    name = device.get("name", "Manual Device")
                    self.discovered_devices[ip] = {
                        "name": name,
                        "ip": ip,
                        "last_seen": time.time(),
                        "manual": True,  # Flag to prevent expiration
                        "type": "vr"  # Add type field
                    }
                    self.manual_device_ips.add(ip)
                    logger.info(f"📱 Manually added VR device: {name} at {ip}")
    
    @property
    def discovered_clients(self):
        """Get list of discovered clients in launcher-compatible format"""
        with self._devices_lock:
            # Remove stale devices (not seen in last 30 seconds), but NEVER remove manual devices
            current_time = time.time()
            
            # DEBUG: Log state before filtering
            logger.info(f"🔍 discovered_clients property called:")
            logger.info(f"   Current time: {current_time}")
            logger.info(f"   discovered_devices dict: {len(self.discovered_devices)} entries")
            for ip, info in self.discovered_devices.items():
                age = current_time - info.get("last_seen", 0)
                logger.info(f"     → {ip}: name={info.get('name')}, last_seen={info.get('last_seen')}, age={age:.1f}s, manual={info.get('manual', False)}")
            
            stale_ips = [ip for ip, info in self.discovered_devices.items() 
                         if not info.get("manual", False) and current_time - info.get("last_seen", 0) > 30]
            
            logger.info(f"   Stale IPs to remove: {stale_ips}")
            
            for ip in stale_ips:
                del self.discovered_devices[ip]
            
            # Update last_seen for manual devices to keep them fresh
            for ip in self.manual_device_ips:
                if ip in self.discovered_devices:
                    self.discovered_devices[ip]["last_seen"] = current_time
            
            # Return list of client info dicts
            result = list(self.discovered_devices.values())
            logger.info(f"   Returning {len(result)} clients")
            return result
    
    def start(self):
        """Start discovery service"""
        if self.running:
            logger.warning("Discovery service already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.thread.start()
        logger.info(f"🔍 Discovery service started on port {self.discovery_port}")
    
    def stop(self):
        """Stop discovery service"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.socket:
            self.socket.close()
        logger.info("Discovery service stopped")
    
    def _discovery_loop(self):
        """Background thread that listens for VR headset announcements"""
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Enable broadcast reception
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            self.socket.bind(('', self.discovery_port))
            self.socket.settimeout(1.0)
            
            logger.info(f"📡 Listening for VR headsets on 0.0.0.0:{self.discovery_port}...")
            logger.info(f"📡 Broadcast reception enabled, ready for VR_HEADSET_HELLO packets")
            
            # Heartbeat counter for debugging
            heartbeat_counter = 0
            
            while self.running:
                try:
                    # Log heartbeat every 30 iterations (~30 seconds with 1s timeout)
                    heartbeat_counter += 1
                    if heartbeat_counter % 30 == 0:
                        with self._devices_lock:
                            logger.info(f"💓 Discovery service alive, {len(self.discovered_devices)} devices known")
                    
                    data, addr = self.socket.recvfrom(1024)
                    message = data.decode('utf-8')
                    logger.info(f"📥 Received UDP packet: {message[:80]} from {addr[0]}:{addr[1]}")
                    
                    if message.startswith("VR_HEADSET_HELLO"):
                        # Parse message: "VR_HEADSET_HELLO:device_name"
                        parts = message.split(":", 1)
                        raw = parts[1] if len(parts) > 1 else "Unknown Device"

                        # Backwards-compatible extension:
                        # "VR_HEADSET_HELLO:device_name:type" where type is one of vr/tv/phone/flat.
                        device_type = "vr"
                        device_name = raw
                        if ":" in raw:
                            maybe_name, maybe_type = raw.rsplit(":", 1)
                            if maybe_type.strip().lower() in {"vr", "tv", "phone", "flat"}:
                                device_name = maybe_name
                                device_type = maybe_type.strip().lower()
                        client_ip = addr[0]
                        
                        # Store or update device info (THREAD-SAFE)
                        with self._devices_lock:
                            if client_ip not in self.discovered_devices:
                                logger.info(f"✅ NEW VR headset discovered: {device_name} at {client_ip}")
                            else:
                                logger.info(f"🔄 VR headset refresh: {device_name} at {client_ip}")
                            
                            self.discovered_devices[client_ip] = {
                                "name": device_name,
                                "ip": client_ip,
                                "last_seen": time.time(),
                                "type": device_type  # vr/tv/phone/flat
                            }
                        
                        # Send back server info
                        response = f"VR_SERVER_INFO:{self.streaming_port}"
                        self.socket.sendto(response.encode('utf-8'), addr)
                        logger.info(f"📤 Sent VR_SERVER_INFO:{self.streaming_port} to {client_ip}:{addr[1]}")
                    else:
                        logger.warning(f"❓ Unknown UDP message: {message[:80]} from {addr[0]}")
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Discovery error: {e}")
        
        except Exception as e:
            logger.error(f"Discovery service crashed: {e}")
        finally:
            if self.socket:
                self.socket.close()


class VRStreamingServer:
    """Main VR streaming server with TCP transport"""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5555,
        discovery_port: int = 5556,
        encoder_type: EncoderType = EncoderType.AUTO,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        quality: int = 25,  # VERY aggressive: 85→50→35→25 for Oculus Go low-res displays
        bitrate: int = 120_000_000,
        stereo_offset: int = 0,
        frame_callback: Optional[Callable[[], Optional[np.ndarray]]] = None
    ):
        """
        Initialize VR streaming server
        
        Args:
            host: Server host address
            port: TCP streaming port (8765 for Android client)
            discovery_port: UDP discovery port (8766 for Android client)
            encoder_type: Encoder to use (AUTO, NVENC, or JPEG)
            width: Frame width
            height: Frame height
            fps: Target frames per second
            quality: JPEG quality (1-100, ignored for NVENC)
            bitrate: H.264 bitrate (bits/second, ignored for JPEG)
            stereo_offset: Stereo parallax offset (pixels, 0 = mono)
            frame_callback: Function that returns RGB frames (height, width, 3) uint8
        """
        self.host = host
        self.port = port
        self.discovery_port = discovery_port
        self.width = width
        self.height = height
        self.fps = fps
        self.stereo_offset = stereo_offset
        self.frame_callback = frame_callback

        # Allow runtime bitrate override without changing code.
        # Expected in bits/sec, e.g. 150000000 for 150 Mbps.
        bitrate_env = (os.environ.get("MESMERGLASS_VRH2_BITRATE") or "").strip()
        if bitrate_env:
            try:
                bitrate = int(float(bitrate_env))
            except ValueError:
                logger.warning("Invalid MESMERGLASS_VRH2_BITRATE=%r (expected integer bits/sec)", bitrate_env)
            else:
                # Clamp to something sane to avoid accidental gigabit settings.
                bitrate = max(1_000_000, min(bitrate, 500_000_000))
                logger.info("VRH2 bitrate override: %.1f Mbps", bitrate / 1_000_000.0)
        
        # Target resolution optimization (Oculus Go: 2048x1024)
        # Downscale to match VR headset native resolution
        self.target_width = 2048
        self.target_height = 1024
        
        # Select encoder
        self.encoder_type = select_encoder(encoder_type)
        logger.info(f"Selected encoder: {self.encoder_type.value.upper()}")

        # Store encoder configuration. Encoder instances are created per-client in handle_client.
        # This avoids reserving an NVENC session before any client connects.
        self.bitrate = bitrate
        self.quality = quality
        self.encoder: Optional[FrameEncoder] = None
        # Protocol magic:
        # - VRHP: JPEG
        # - VRH2: H.264 (legacy header)
        # - VRH3: H.264 (extended header includes fps_milli)
        # Default to VRH3 for H.264 to improve client smoothness (timed playout scheduling).
        self.protocol_magic = (b"VRH3" if self.encoder_type == EncoderType.NVENC else b"VRHP")

        # Optional: enable VRH3 on the wire for H.264 clients.
        # VRH3 extends the VRH2 header with fps_milli for smoother client playout scheduling.
        protocol_env = (os.environ.get("MESMERGLASS_VRH2_PROTOCOL") or "").strip().lower()
        if protocol_env in {"vrh2", "vrh3"}:
            if self.encoder_type == EncoderType.NVENC:
                self.protocol_magic = (b"VRH3" if protocol_env == "vrh3" else b"VRH2")
                logger.info("VRH2 protocol override: %s", protocol_env)
            else:
                logger.warning(
                    "MESMERGLASS_VRH2_PROTOCOL=%r ignored (current encoder=%s)",
                    protocol_env,
                    self.encoder_type.value,
                )
        
        # Server state
        self.server_socket: Optional[socket.socket] = None
        self.discovery_service: Optional[DiscoveryService] = None
        self.clients = []
        self._client_tasks: set[asyncio.Task] = set()
        self.running = False
        
        # Frame timing
        self.frame_delay = 1.0 / fps
        self.frames_sent = 0
        self.start_time = time.time()
        self._last_callback_warn = 0.0
        self._callback_warn_count = 0
        
        # Performance tracking
        self.total_bytes_sent = 0
        self.encode_times = []
        self.send_times = []
        self.last_stats_time = time.time()
        
        logger.info(f"VRStreamingServer initialized: {width}x{height} @ {fps} FPS")
        
        # Thread for async server
        self._server_thread: Optional[threading.Thread] = None
        self._server_loop: Optional[asyncio.AbstractEventLoop] = None

        # Encoder instances are not guaranteed thread-safe. If multiple clients connect, or if we
        # run capture/encode in a background thread, we must serialize access.
        self._encode_lock = threading.Lock()

        # Circuit breaker: if NVENC init/encode starts failing, temporarily stop trying it.
        # This avoids repeated avcodec_open2(h264_nvenc) spam and reconnect storms.
        self._nvenc_disabled_until: float = 0.0
        self._nvenc_last_failure_s: float = 0.0
        self._nvenc_failures: int = 0
    
    def start_server(self):
        """
        Start VR streaming server in background thread (synchronous wrapper for async start)
        
        This is the entry point for Qt/GUI applications that need to start the server
        without blocking the main thread.
        """
        if self.running:
            logger.warning("Server already running")
            return
        
        def run_async_server():
            """Run async server in background thread"""
            self._server_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._server_loop)

            def _loop_exception_handler(loop, context):
                exc = context.get("exception")
                err = getattr(exc, "winerror", getattr(exc, "errno", None)) if exc else None
                if isinstance(exc, OSError) and err in _WIN_ABORT_ERRNOS:
                    logger.info("VR streaming server ignored WinError %s during shutdown", err)
                    return
                asyncio.default_exception_handler(context)

            self._server_loop.set_exception_handler(_loop_exception_handler)
            try:
                self._server_loop.run_until_complete(self.start())
            except Exception as e:
                logger.error(f"Server error: {e}", exc_info=True)
            finally:
                self._server_loop.close()
        
        # Start server in background thread
        self._server_thread = threading.Thread(target=run_async_server, daemon=True)
        self._server_thread.start()
        logger.info("VR streaming server thread started")
    
    def stop_server(self):
        """
        Stop VR streaming server (synchronous wrapper for async stop)
        """
        if not self.running:
            return
        
        if self._server_loop and self._server_thread:
            # Schedule stop in the server's event loop
            asyncio.run_coroutine_threadsafe(self.stop(), self._server_loop)
            self._server_thread.join(timeout=2.0)
            logger.info("VR streaming server stopped")
    
    def create_packet(
        self,
        left_frame: bytes,
        right_frame: bytes,
        frame_id: int,
        protocol_magic: Optional[bytes] = None,
        fps_milli: Optional[int] = None,
    ) -> bytes:
        """
        Create network packet with stereo frames
        
        Packet format:
        - Packet size (4 bytes, big-endian int)
        - Header (VRHP/VRH2 = 16 bytes): magic(4) + frame_id(4) + left_size(4) + right_size(4)
        - Header (VRH3 = 20 bytes): magic(4) + frame_id(4) + left_size(4) + right_size(4) + fps_milli(4)
        - Left eye frame data
        - Right eye frame data (optional; right_size may be 0 to indicate "reuse left")
        
        Args:
            left_frame: Encoded left eye frame
            right_frame: Encoded right eye frame
            frame_id: Frame sequence number
        
        Returns:
            Complete packet as bytes
        """
        left_size = len(left_frame)
        right_size = len(right_frame)
        
        # Create header
        magic = self.protocol_magic if protocol_magic is None else protocol_magic
        if magic == b"VRH3":
            # fps_milli is required for VRH3; fall back to server fps if missing.
            fps_milli_eff = int(fps_milli) if fps_milli is not None else int(float(getattr(self, "fps", 30) or 30) * 1000.0)
            header = struct.pack('!4sIIII', magic, frame_id, left_size, right_size, fps_milli_eff)
        else:
            header = struct.pack('!4sIII', magic, frame_id, left_size, right_size)
        
        # Combine header + frames
        packet_data = header + left_frame + right_frame
        
        # Prepend packet size (ALL protocols need this for the Android client)
        packet_size = len(packet_data)
        size_header = struct.pack('!I', packet_size)
        return size_header + packet_data
    
    async def handle_client(self, client_socket: socket.socket, address: tuple):
        """
        Handle connected VR client
        
        Args:
            client_socket: Client socket
            address: Client address tuple
        """
        logger.info(f"🎯 Client connected from {address}")

        client_ip = str(address[0])
        client_port = int(address[1])
        client_id = f"{client_ip}:{client_port}"

        # Best-effort lookup: prefer device name from UDP discovery (VR_HEADSET_HELLO).
        device_name: Optional[str] = None
        try:
            ds = getattr(self, "discovery_service", None)
            if ds is not None:
                lock = getattr(ds, "_devices_lock", None)
                devices = getattr(ds, "discovered_devices", None)
                if lock is not None and devices is not None:
                    with lock:
                        info = devices.get(client_ip)
                        if isinstance(info, dict):
                            maybe = info.get("name")
                            if maybe:
                                device_name = str(maybe)
        except Exception:
            device_name = None

        # Publish connection state for the Performance UI (best-effort; never fail streaming).
        try:
            from mesmerglass.engine.streaming_telemetry import streaming_telemetry

            streaming_telemetry.set_connected(
                client_id,
                True,
                address=client_id,
                device_name=device_name,
                protocol=(self.protocol_magic.decode("ascii", errors="ignore") if self.protocol_magic else None),
                bitrate_bps=int(getattr(self, "bitrate", 0) or 0) or None,
            )
        except Exception:
            pass

        # IMPORTANT: Use a fresh encoder per client.
        # If we reuse the encoder across connections, a newly connected client can start mid-GOP
        # (receiving P-frames that reference pictures it never saw), which looks like heavy mosaic
        # until the next IDR. A per-client encoder ensures the first access units are decodable.
        client_encoder: Optional[FrameEncoder] = None
        client_protocol_magic = self.protocol_magic
        use_vrh3 = (client_protocol_magic == b"VRH3")
        client_encoder_type = self.encoder_type
        # Per-client bitrate used when (re)creating the H.264 encoder.
        # This enables adaptive bitrate control without changing global server state.
        client_bitrate = int(getattr(self, "bitrate", 50_000_000))
        dump_fp: Optional[object] = None
        dump_started: bool = False
        dump_lock = threading.Lock()
        force_disconnect = threading.Event()

        # In VRH2 (H.264) mode we must not drop inter-coded pictures.
        # If the sender loop can't keep up, skipping P-frames breaks reference chains and
        # manifests as mosaics on the client until the next IDR.
        # We apply backpressure so the producer encodes at the effective send rate.
        consumed_lock = threading.Lock()
        consumed_generation: int = 0

        def _mark_generation_consumed(gen: int) -> None:
            nonlocal consumed_generation
            with consumed_lock:
                if gen > consumed_generation:
                    consumed_generation = gen

        def _get_consumed_generation() -> int:
            with consumed_lock:
                return consumed_generation

        def _env_truthy(name: str) -> bool:
            v = os.environ.get(name)
            if v is None:
                return False
            return v.strip().lower() not in {"", "0", "false", "off", "no", "disabled", "disable"}

        def _env_truthy_default(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() not in {"", "0", "false", "off", "no", "disabled", "disable"}

        def _env_int(name: str, default: int) -> int:
            v = os.environ.get(name)
            if v is None:
                return default
            try:
                return int(v.strip())
            except Exception:
                return default

        def _env_float(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None:
                return default
            try:
                return float(v.strip())
            except Exception:
                return default

        # Adaptive quality/latency (VRH2): server-side bitrate control based on observed send congestion.
        adaptive_enabled = _env_truthy_default("MESMERGLASS_VRH2_ADAPTIVE", False)
        adaptive_min_bitrate = max(1_000_000, _env_int("MESMERGLASS_VRH2_ADAPTIVE_MIN_BITRATE", 8_000_000))
        adaptive_max_bitrate = max(adaptive_min_bitrate, _env_int("MESMERGLASS_VRH2_ADAPTIVE_MAX_BITRATE", 120_000_000))
        adaptive_step_ratio = max(0.01, min(_env_float("MESMERGLASS_VRH2_ADAPTIVE_STEP_RATIO", 0.15), 0.90))
        adaptive_cooldown_s = max(0.0, _env_float("MESMERGLASS_VRH2_ADAPTIVE_COOLDOWN_S", 3.0))
        adaptive_warmup_s = max(0.0, _env_float("MESMERGLASS_VRH2_ADAPTIVE_WARMUP_S", 5.0))
        adaptive_send_ms_hi = max(0.1, _env_float("MESMERGLASS_VRH2_ADAPTIVE_SEND_MS_HI", 6.0))
        adaptive_send_ms_lo = max(0.05, _env_float("MESMERGLASS_VRH2_ADAPTIVE_SEND_MS_LO", 2.0))
        adaptive_fps_lo_ratio = max(0.1, min(_env_float("MESMERGLASS_VRH2_ADAPTIVE_FPS_LO_RATIO", 0.90), 0.99))
        adaptive_fps_hi_ratio = max(adaptive_fps_lo_ratio, min(_env_float("MESMERGLASS_VRH2_ADAPTIVE_FPS_HI_RATIO", 0.98), 1.05))
        # If the client reports its playout buffer, bias decisions toward avoiding underflow
        # (smoothness-first), even if that increases latency.
        adaptive_client_buffer_ms_lo = _env_int("MESMERGLASS_VRH2_ADAPTIVE_CLIENT_BUFFER_MS_LO", 80)
        adaptive_client_buffer_ms_hi = _env_int("MESMERGLASS_VRH2_ADAPTIVE_CLIENT_BUFFER_MS_HI", 250)
        adaptive_client_stats_max_age_s = max(0.1, _env_float("MESMERGLASS_VRH2_ADAPTIVE_CLIENT_STATS_MAX_AGE_S", 2.0))
        adaptive_last_change_s = 0.0

        def _adaptive_next_bitrate(cur: int, direction: str) -> int:
            # direction: 'down' or 'up'
            step = max(250_000, int(float(cur) * adaptive_step_ratio))
            if direction == 'down':
                nxt = cur - step
            else:
                nxt = cur + step
            return int(max(adaptive_min_bitrate, min(adaptive_max_bitrate, nxt)))

        def _h264_codec_available(name: str) -> bool:
            try:
                import av
                av.codec.Codec(name, 'w')
                return True
            except Exception:
                return False

        insert_aud = _env_truthy("MESMERGLASS_VRH2_INSERT_AUD")
        nal_diag_mode = (os.environ.get("MESMERGLASS_VRH2_NAL_DIAG") or "").strip().lower()

        frame_log = _env_truthy_default("MESMERGLASS_VRH2_FRAME_LOG", False)

        # Optional debugging: dump raw pre-encode frames to PNG. This decisively answers whether
        # corruption exists before encoding (capture/compositor/race) or only after encoding.
        raw_dump_dir_env = (os.environ.get("MESMERGLASS_VRH2_RAW_DUMP_DIR") or "").strip()
        raw_dump_every = _env_int("MESMERGLASS_VRH2_RAW_DUMP_EVERY", 0)
        raw_dump_max = _env_int("MESMERGLASS_VRH2_RAW_DUMP_MAX", 0)
        # IMPORTANT: Default to deep-copying the input for NVENC.
        # Many render/capture pipelines reuse a stable numpy buffer; without an explicit copy
        # the encoder can observe the buffer being mutated mid-encode under load/soak.
        deep_copy_input = _env_truthy_default(
            "MESMERGLASS_VRH2_DEEPCOPY_INPUT",
            (self.encoder_type == EncoderType.NVENC),
        )

        # Log the effective value even when no env vars are set.
        logger.warning(
            "[vrh2-input] deep_copy_input_effective=%s (encoder_type=%s)",
            ("1" if deep_copy_input else "0"),
            getattr(self.encoder_type, "value", str(self.encoder_type)),
        )

        if (
            ("MESMERGLASS_VRH2_RAW_DUMP_DIR" in os.environ)
            or ("MESMERGLASS_VRH2_RAW_DUMP_EVERY" in os.environ)
            or ("MESMERGLASS_VRH2_RAW_DUMP_MAX" in os.environ)
            or ("MESMERGLASS_VRH2_DEEPCOPY_INPUT" in os.environ)
        ):
            logger.warning(
                "[vrh2-raw] config: dir_env=%r every=%d max=%d deep_copy=%s",
                raw_dump_dir_env,
                raw_dump_every,
                raw_dump_max,
                ("1" if deep_copy_input else "0"),
            )

        raw_dump_dir: Optional[Path] = None
        if raw_dump_dir_env and raw_dump_every > 0:
            try:
                raw_dump_dir = Path(raw_dump_dir_env)
                if not raw_dump_dir.is_absolute():
                    raw_dump_dir = Path.cwd() / raw_dump_dir
                raw_dump_dir.mkdir(parents=True, exist_ok=True)
                logger.warning(
                    "[vrh2-raw] enabled: dir=%s every=%d max=%s deep_copy=%s",
                    str(raw_dump_dir),
                    raw_dump_every,
                    (raw_dump_max if raw_dump_max > 0 else ""),
                    ("1" if deep_copy_input else "0"),
                )
            except Exception as e:
                raw_dump_dir = None
                logger.warning("[vrh2-raw] failed to init dump dir: %s", e)

        # Safety valve: optionally request IDR on next frame when we detect a suspiciously tiny/crater access unit.
        # NOTE: Tiny P-slices can be perfectly valid (e.g. static scenes with SKIP macroblocks), so this is opt-in.
        idr_on_tiny = _env_truthy_default("MESMERGLASS_VRH2_IDR_ON_TINY", False)
        idr_tiny_bytes = _env_int("MESMERGLASS_VRH2_TINY_BYTES", 192)
        idr_on_crater = _env_truthy_default("MESMERGLASS_VRH2_IDR_ON_CRATER", False)
        crater_window = _env_int("MESMERGLASS_VRH2_CRATER_WINDOW", 30)
        crater_factor = _env_float("MESMERGLASS_VRH2_CRATER_FACTOR", 10.0)
        crater_min_median = _env_int("MESMERGLASS_VRH2_CRATER_MIN_MEDIAN", 4096)
        idr_cooldown_frames = max(0, _env_int("MESMERGLASS_VRH2_IDR_COOLDOWN_FRAMES", 15))
        # More reliable recovery: reset encoder (per-client) and resync at next IDR.
        reset_on_anomaly = _env_truthy_default("MESMERGLASS_VRH2_RESET_ON_ANOMALY", False)
        reset_cooldown_frames = max(0, _env_int("MESMERGLASS_VRH2_RESET_COOLDOWN_FRAMES", 120))
        strip_sei = _env_truthy("MESMERGLASS_VRH2_STRIP_SEI")

        # Optional debugging: input frame integrity instrumentation.
        # These knobs help detect producer-side corruption/races *before* encode.
        #
        # - MESMERGLASS_VRH2_INPUT_CRC=1
        #     Logs a sampled CRC32 of the (resized) RGB input frame.
        # - MESMERGLASS_VRH2_INPUT_CRC_DOUBLE=1
        #     Computes CRC twice (once before encode, once immediately before encode under lock)
        #     and warns if they differ (indicates concurrent mutation / buffer reuse race).
        # - MESMERGLASS_VRH2_INPUT_CRC_STRIDE=4
        #     Sampling stride for CRC (higher = cheaper, less sensitive). 1 = full frame.
        # - MESMERGLASS_VRH2_INPUT_PTR_LOG=1
        #     Logs the numpy data pointer for the captured frame buffer.
        input_crc_log = _env_truthy_default("MESMERGLASS_VRH2_INPUT_CRC", False)
        input_crc_double = _env_truthy_default("MESMERGLASS_VRH2_INPUT_CRC_DOUBLE", False)
        input_crc_stride = max(1, _env_int("MESMERGLASS_VRH2_INPUT_CRC_STRIDE", 4))
        input_ptr_log = _env_truthy_default("MESMERGLASS_VRH2_INPUT_PTR_LOG", False)

        def _crc32_sample_rgb(frame_rgb: "np.ndarray") -> int:
            try:
                if input_crc_stride <= 1:
                    data = frame_rgb.tobytes()
                else:
                    # Sample spatially to reduce overhead while still catching most corruption.
                    data = frame_rgb[::input_crc_stride, ::input_crc_stride].tobytes()
                return zlib.crc32(data) & 0xFFFFFFFF
            except Exception:
                return 0

        def _iter_annexb_nals(data: bytes):
            # Yield (nal_type, nal_payload_size) for Annex-B streams.
            if not data:
                return
            n = len(data)
            starts = []
            i = 0
            while i + 3 < n:
                if data[i] == 0 and data[i + 1] == 0:
                    if data[i + 2] == 1:
                        starts.append((i, 3))
                        i += 3
                        continue
                    if i + 4 < n and data[i + 2] == 0 and data[i + 3] == 1:
                        starts.append((i, 4))
                        i += 4
                        continue
                i += 1

            for idx, (pos, start_len) in enumerate(starts):
                hdr = pos + start_len
                if hdr >= n:
                    continue
                nxt = starts[idx + 1][0] if idx + 1 < len(starts) else n
                nal_type = data[hdr] & 0x1F
                payload_size = max(0, nxt - hdr)
                yield nal_type, payload_size

        def _iter_annexb_nal_units(data: bytes):
            # Yield (nal_type, nal_unit_bytes_without_start_code) for Annex-B streams.
            if not data:
                return
            n = len(data)
            starts = []
            i = 0
            while i + 3 < n:
                if data[i] == 0 and data[i + 1] == 0:
                    if data[i + 2] == 1:
                        starts.append((i, 3))
                        i += 3
                        continue
                    if i + 4 < n and data[i + 2] == 0 and data[i + 3] == 1:
                        starts.append((i, 4))
                        i += 4
                        continue
                i += 1

            for idx, (pos, start_len) in enumerate(starts):
                hdr = pos + start_len
                if hdr >= n:
                    continue
                nxt = starts[idx + 1][0] if idx + 1 < len(starts) else n
                unit = data[hdr:nxt]
                if not unit:
                    continue
                nal_type = unit[0] & 0x1F
                yield nal_type, unit

        def _h264_ebsp_to_rbsp(ebsp: bytes) -> bytes:
            # Remove emulation-prevention bytes (0x03 after 0x0000) per H.264 spec.
            if not ebsp:
                return ebsp
            out = bytearray()
            zeros = 0
            for b in ebsp:
                if zeros >= 2 and b == 0x03:
                    zeros = 0
                    continue
                out.append(b)
                if b == 0:
                    zeros += 1
                else:
                    zeros = 0
            return bytes(out)

        class _BitReader:
            __slots__ = ("_data", "_bitpos", "_n")

            def __init__(self, data: bytes):
                self._data = data
                self._bitpos = 0
                self._n = len(data) * 8

            def _read_bit(self) -> int:
                if self._bitpos >= self._n:
                    raise EOFError()
                byte_i = self._bitpos >> 3
                bit_i = 7 - (self._bitpos & 7)
                self._bitpos += 1
                return (self._data[byte_i] >> bit_i) & 1

            def read_bits(self, nbits: int) -> int:
                v = 0
                for _ in range(nbits):
                    v = (v << 1) | self._read_bit()
                return v

            def read_ue(self) -> int:
                # Unsigned Exp-Golomb.
                zeros = 0
                while True:
                    bit = self._read_bit()
                    if bit == 0:
                        zeros += 1
                        if zeros > 31:
                            raise ValueError("UE too large")
                    else:
                        break
                if zeros == 0:
                    return 0
                return (1 << zeros) - 1 + self.read_bits(zeros)

        def _h264_slice_header_brief(nal_unit: bytes):
            # Best-effort parse of the first few fields in slice header:
            # first_mb_in_slice (ue), slice_type (ue), pic_parameter_set_id (ue)
            # We do NOT attempt full parsing (needs SPS/PPS).
            try:
                if not nal_unit or len(nal_unit) < 2:
                    return None
                nal_type = nal_unit[0] & 0x1F
                if nal_type not in (1, 5):
                    return None
                rbsp = _h264_ebsp_to_rbsp(nal_unit[1:])
                br = _BitReader(rbsp)
                first_mb = br.read_ue()
                slice_type = br.read_ue()
                pps_id = br.read_ue()
                return (first_mb, slice_type, pps_id)
            except Exception:
                return None

        def _h264_insert_aud_if_missing(data: bytes) -> bytes:
            # Access Unit Delimiter NAL (type 9) with primary_pic_type=7 (111) + rbsp_trailing_bits.
            # Common byte pattern: 00 00 00 01 09 F0
            if not data:
                return data

            # If stream doesn't look Annex-B, don't touch it.
            if not (data.startswith(b"\x00\x00\x01") or data.startswith(b"\x00\x00\x00\x01")):
                return data

            # If first NAL is already an AUD, don't double-insert.
            for nal_type, _sz in _iter_annexb_nals(data):
                return data if nal_type == 9 else (b"\x00\x00\x00\x01\x09\xF0" + data)
            return data

        def _h264_strip_sei_nals(data: bytes) -> bytes:
            # Remove SEI (nal type 6) NAL units from Annex-B. Best-effort.
            if not data:
                return data
            if not (data.startswith(b"\x00\x00\x01") or data.startswith(b"\x00\x00\x00\x01")):
                return data

            n = len(data)
            starts = []
            i = 0
            while i + 3 < n:
                if data[i] == 0 and data[i + 1] == 0:
                    if data[i + 2] == 1:
                        starts.append((i, 3))
                        i += 3
                        continue
                    if i + 4 < n and data[i + 2] == 0 and data[i + 3] == 1:
                        starts.append((i, 4))
                        i += 4
                        continue
                i += 1

            if not starts:
                return data

            out = bytearray()
            for idx, (pos, start_len) in enumerate(starts):
                hdr = pos + start_len
                if hdr >= n:
                    continue
                nxt = starts[idx + 1][0] if idx + 1 < len(starts) else n
                nal_type = data[hdr] & 0x1F
                if nal_type == 6:
                    continue
                out += data[pos:nxt]

            return bytes(out) if out else data

        def _maybe_log_nal_diag(label: str, frame_id: int, data: bytes) -> None:
            if not nal_diag_mode:
                return

            total = len(data)
            nal_types = []
            has_key = False
            for t, _sz in _iter_annexb_nals(data):
                nal_types.append(t)
                if t in (5, 7, 8):
                    has_key = True

            if not nal_types:
                # Not Annex-B or empty; still log if asked.
                if nal_diag_mode == "all":
                    logger.warning("[vrh2-nal] %s frame=%d bytes=%d nals=0 (non-AnnexB?)", label, frame_id, total)
                return

            is_tiny = total < 2048
            if (nal_diag_mode == "all") or is_tiny or has_key:
                # Compact type histogram.
                counts = {}
                for t in nal_types:
                    counts[t] = counts.get(t, 0) + 1
                # Stable ordering for readability.
                ordered = " ".join([f"{k}:{counts[k]}" for k in sorted(counts.keys())])

                # For slice NALs, try to log first_mb_in_slice / slice_type / pps_id.
                slice_briefs = []
                try:
                    for t, unit in _iter_annexb_nal_units(data):
                        if t in (1, 5):
                            brief = _h264_slice_header_brief(unit)
                            if brief is not None:
                                first_mb, slice_type, pps_id = brief
                                slice_briefs.append(f"{t}@mb{first_mb}:st{slice_type}:pps{pps_id}")
                except Exception:
                    slice_briefs = []

                slices_str = (" slices=[" + ",".join(slice_briefs[:8]) + "]") if slice_briefs else ""
                logger.warning(
                    "[vrh2-nal] %s frame=%d bytes=%d nals=%d types=[%s]%s",
                    label,
                    frame_id,
                    total,
                    len(nal_types),
                    ordered,
                    slices_str,
                )

        def _h264_access_unit_contains_idr(data: bytes) -> bool:
            # Annex-B scan for IDR slices (NAL type 5).
            if not data:
                return False
            n = len(data)
            i = 0
            while i + 4 < n:
                if data[i] == 0 and data[i + 1] == 0:
                    start_len = 0
                    if data[i + 2] == 1:
                        start_len = 3
                    elif data[i + 2] == 0 and data[i + 3] == 1:
                        start_len = 4
                    if start_len:
                        hdr = i + start_len
                        if hdr < n:
                            nal_type = data[hdr] & 0x1F
                            if nal_type == 5:
                                return True
                        i = hdr + 1
                        continue
                i += 1
            return False
        
        try:
            if self.encoder_type == EncoderType.NVENC:
                now_s = time.time()
                if now_s < getattr(self, "_nvenc_disabled_until", 0.0):
                    # Circuit breaker active for NVENC. Switch to software H.264.
                    if _h264_codec_available('libx264'):
                        logger.warning(
                            "NVENC disabled for %.1fs more; using libx264 (%s) for client %s",
                            (self._nvenc_disabled_until - now_s),
                            ("VRH3" if use_vrh3 else "VRH2"),
                            address,
                        )
                        client_encoder = create_encoder(
                            EncoderType.NVENC,
                            width=self.target_width,
                            height=self.target_height,
                            fps=self.fps,
                            bitrate=client_bitrate,
                            codec_name="libx264",
                        )
                        client_protocol_magic = (b"VRH3" if use_vrh3 else b"VRH2")
                        client_encoder_type = EncoderType.NVENC
                    else:
                        logger.warning(
                            "NVENC disabled for %.1fs more; libx264 unavailable, using JPEG for client %s",
                            (self._nvenc_disabled_until - now_s),
                            address,
                        )
                        client_encoder = create_encoder(
                            EncoderType.JPEG,
                            width=self.target_width,
                            height=self.target_height,
                            quality=getattr(self, "quality", 25),
                        )
                        client_protocol_magic = b"VRHP"
                        client_encoder_type = EncoderType.JPEG
                else:
                    try:
                        client_encoder = create_encoder(
                            EncoderType.NVENC,
                            width=self.target_width,
                            height=self.target_height,
                            fps=self.fps,
                            bitrate=client_bitrate,
                            codec_name="h264_nvenc",
                        )
                        client_protocol_magic = (b"VRH3" if use_vrh3 else b"VRH2")
                        client_encoder_type = EncoderType.NVENC
                    except Exception as e:
                        # NVENC can fail on some systems due to driver/runtime issues or session limits.
                        # Prefer falling back to software H.264 (VRH2) to keep the smooth decode path.
                        logger.warning("NVENC init failed for client %s: %s", address, e)
                        try:
                            self._nvenc_failures = int(getattr(self, "_nvenc_failures", 0)) + 1
                            self._nvenc_last_failure_s = time.time()
                            # Back off progressively (min 15s, max 5m).
                            cooldown = min(300.0, max(15.0, float(self._nvenc_failures) * 15.0))
                            self._nvenc_disabled_until = time.time() + cooldown
                            logger.warning("NVENC circuit breaker tripped: cooldown=%.1fs", cooldown)
                        except Exception:
                            pass
                        if _h264_codec_available('libx264'):
                            logger.warning("Falling back to libx264 (%s) for client %s", ("VRH3" if use_vrh3 else "VRH2"), address)
                            client_encoder = create_encoder(
                                EncoderType.NVENC,
                                width=self.target_width,
                                height=self.target_height,
                                fps=self.fps,
                                bitrate=client_bitrate,
                                codec_name="libx264",
                            )
                            client_protocol_magic = (b"VRH3" if use_vrh3 else b"VRH2")
                            client_encoder_type = EncoderType.NVENC
                        else:
                            logger.warning("libx264 unavailable; falling back to JPEG for client %s", address)
                            client_encoder = create_encoder(
                                EncoderType.JPEG,
                                width=self.target_width,
                                height=self.target_height,
                                quality=getattr(self, "quality", 25),
                            )
                            client_protocol_magic = b"VRHP"
                            client_encoder_type = EncoderType.JPEG
            else:
                client_encoder = create_encoder(
                    EncoderType.JPEG,
                    width=self.target_width,
                    height=self.target_height,
                    quality=getattr(self, "quality", 25),
                )
                client_protocol_magic = b"VRHP"
                client_encoder_type = EncoderType.JPEG

            # Ask for a clean keyframe soon after (re)configure.
            # This reduces the chance of starting on a non-IDR picture if the encoder
            # has internal buffering or if we re-use a warm encoder configuration.
            if client_protocol_magic in {b"VRH2", b"VRH3"} and client_encoder is not None and hasattr(client_encoder, "request_idr"):
                try:
                    client_encoder.request_idr()
                    logger.info("[vrh2-idr] requested initial IDR (reason=connect)")
                except Exception:
                    pass

            # Producer thread continuously refreshes the *latest* encoded frame.
            # IMPORTANT: For H.264, do NOT blindly re-send the same access unit when the producer
            # hasn't advanced. Re-decoding repeated P-frames can break DPB/reference state on some
            # hardware decoders and manifest as worsening mosaics over time.
            # If the producer stalls, we simply hold the last decoded frame on the client.
            latest_lock = threading.Lock()
            latest_ready = threading.Event()
            stop_producer = threading.Event()
            latest_left: Optional[bytes] = None
            latest_right: Optional[bytes] = None
            latest_generation: int = 0
            last_left_kb: float = 0.0
            last_right_kb: float = 0.0
            last_encode_s: float = 0.0

            mono_packet = (self.stereo_offset == 0)

            produced_frames = 0
            last_producer_warn = 0.0
            producer_warn_count = 0

            reset_encoder_requested = threading.Event()

            def _recreate_client_encoder() -> Optional[FrameEncoder]:
                # Create a new encoder instance with the same configuration.
                try:
                    if client_encoder_type == EncoderType.NVENC:
                        return create_encoder(
                            EncoderType.NVENC,
                            width=self.target_width,
                            height=self.target_height,
                            fps=self.fps,
                            bitrate=client_bitrate,
                        )
                    return create_encoder(
                        EncoderType.JPEG,
                        width=self.target_width,
                        height=self.target_height,
                        quality=getattr(self, "quality", 25),
                    )
                except Exception as e:
                    logger.warning("[vrh2-reset] Failed to recreate encoder: %s", e)
                    return None

            def _producer_loop():
                nonlocal latest_left, latest_right, latest_generation, last_left_kb, last_right_kb, last_encode_s, produced_frames, last_producer_warn, producer_warn_count, client_encoder, client_protocol_magic, client_encoder_type, dump_fp
                raw_dump_count = 0
                raw_dump_fail_count = 0
                last_ptr_logged = None
                consecutive_failures = 0

                # IMPORTANT: Encode at (approximately) the configured streaming FPS.
                # If we encode faster than we send, the send loop will effectively drop frames.
                # Dropping H.264 P-frames can break reference chains and manifests as mosaics until the next IDR.
                frame_interval_s = float(getattr(self, "frame_delay", 1.0 / max(1, int(getattr(self, "fps", 30)))))
                next_encode_ts = time.perf_counter()

                while self.running and (not stop_producer.is_set()) and (not force_disconnect.is_set()):
                    try:
                        # VRH2 backpressure: ensure we never get more than 1 access unit ahead
                        # of what the sender has consumed. This prevents dropping P-frames.
                        if client_protocol_magic in {b"VRH2", b"VRH3"}:
                            with latest_lock:
                                pending_gen = latest_generation
                            if pending_gen > _get_consumed_generation():
                                time.sleep(0.001)
                                continue

                        # Throttle encode to target FPS.
                        now_ts = time.perf_counter()
                        sleep_s = next_encode_ts - now_ts
                        if sleep_s > 0:
                            # Small sleeps keep CPU reasonable without adding jitter.
                            time.sleep(min(sleep_s, 0.01))
                            continue
                        next_encode_ts += frame_interval_s
                        if next_encode_ts < now_ts:
                            # If we fell behind (GC / spike), resync.
                            next_encode_ts = now_ts

                        if reset_encoder_requested.is_set():
                            # Reset encoder under the encode lock to avoid concurrent usage.
                            reset_encoder_requested.clear()
                            with self._encode_lock:
                                try:
                                    if client_encoder is not None:
                                        client_encoder.close()
                                except Exception as e:
                                    # Only log when raw dumping is enabled, to avoid noise.
                                    logger.warning("[vrh2-raw] write failed: %s", e)
                                new_enc = _recreate_client_encoder()
                                if new_enc is not None:
                                    client_encoder = new_enc
                                    try:
                                        if hasattr(client_encoder, "request_idr"):
                                            client_encoder.request_idr()
                                    except Exception:
                                        pass
                                    logger.warning("[vrh2-reset] Encoder recreated (forced IDR)")

                        if self.frame_callback is None:
                            frame = self._generate_test_frame()
                        else:
                            frame = self.frame_callback()

                        # Ensure the encoder sees a stable, contiguous RGB buffer. If the producer
                        # returns a reused buffer that can be modified concurrently, enabling
                        # MESMERGLASS_VRH2_DEEPCOPY_INPUT=1 can eliminate "valid but garbage" frames.
                        if frame is None:
                            time.sleep(0.005)
                            continue
                        try:
                            frame = np.ascontiguousarray(frame)
                        except Exception:
                            time.sleep(0.005)
                            continue

                        if input_ptr_log:
                            try:
                                ptr = int(frame.__array_interface__["data"][0])
                                # Log only on changes to reduce noise.
                                if last_ptr_logged != ptr:
                                    last_ptr_logged = ptr
                                    logger.info(
                                        "[vrh2-inptr] gen=%d ptr=0x%x shape=%s contiguous=%s",
                                        produced_frames,
                                        ptr,
                                        str(getattr(frame, "shape", "")),
                                        ("1" if (hasattr(frame, "flags") and bool(frame.flags["C_CONTIGUOUS"])) else "0"),
                                    )
                            except Exception:
                                pass

                        # Optional: write raw frames to disk for forensics.
                        if raw_dump_dir is not None and raw_dump_every > 0:
                            if (produced_frames % raw_dump_every) == 0 and (raw_dump_max <= 0 or raw_dump_count < raw_dump_max):
                                try:
                                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                                    crc = zlib.crc32(frame.tobytes()) & 0xFFFFFFFF
                                    out_path = raw_dump_dir / f"vrh2_raw_{produced_frames:06d}_{ts}_crc{crc:08x}.png"
                                    # Keep a .png extension so OpenCV can select an encoder.
                                    tmp_path = raw_dump_dir / f".{out_path.stem}.tmp.png"
                                    # Frame is documented as RGB; OpenCV expects BGR.
                                    bgr = frame[:, :, ::-1] if (frame.ndim == 3 and frame.shape[2] == 3) else frame
                                    ok = cv2.imwrite(str(tmp_path), bgr)
                                    if not ok:
                                        raise RuntimeError("cv2.imwrite returned False")
                                    try:
                                        os.replace(str(tmp_path), str(out_path))
                                    except Exception:
                                        # Best-effort fallback.
                                        try:
                                            if not out_path.exists():
                                                os.rename(str(tmp_path), str(out_path))
                                        except Exception:
                                            pass
                                    raw_dump_count += 1
                                    logger.info(
                                        "[vrh2-raw] wrote gen=%d path=%s crc=%08x shape=%s",
                                        produced_frames,
                                        str(out_path),
                                        crc,
                                        str(getattr(frame, "shape", "")),
                                    )
                                except Exception as e:
                                    raw_dump_fail_count += 1
                                    # Don't spam: log the first few failures then sample.
                                    if raw_dump_fail_count <= 3 or (produced_frames % 60) == 0:
                                        logger.warning("[vrh2-raw] write failed gen=%d dir=%s: %s", produced_frames, str(raw_dump_dir), e)

                        if frame is None:
                            producer_warn_count += 1
                            now_s = time.time()
                            if now_s - last_producer_warn >= 1.0:
                                if producer_warn_count > 5:
                                    logger.warning("Frame callback returned None x%d (last %.1fs)", producer_warn_count, now_s - last_producer_warn)
                                else:
                                    logger.warning("Frame callback returned None")
                                last_producer_warn = now_s
                                producer_warn_count = 0
                            time.sleep(0.01)
                            continue

                        # Downscale to target resolution if needed (for Oculus Go optimization)
                        if frame.shape[1] != self.target_width or frame.shape[0] != self.target_height:
                            frame = cv2.resize(
                                frame,
                                (self.target_width, self.target_height),
                                interpolation=cv2.INTER_LINEAR,
                            )

                        # Ensure the encoder sees a stable buffer for the duration of encode.
                        if deep_copy_input:
                            try:
                                frame = frame.copy()
                            except Exception:
                                time.sleep(0.005)
                                continue

                        # Compute a sampled CRC of the *actual* RGB input that will be encoded.
                        crc_before = 0
                        if input_crc_log or input_crc_double:
                            crc_before = _crc32_sample_rgb(frame)
                            if input_crc_log:
                                logger.info(
                                    "[vrh2-incrc] gen=%d crc=%08x stride=%d shape=%s",
                                    produced_frames,
                                    crc_before,
                                    input_crc_stride,
                                    str(getattr(frame, "shape", "")),
                                )

                        encode_start = time.time()
                        # Serialize GPU encode by default; multiple encoders can exist if multiple
                        # clients connect, but not all systems handle parallel NVENC sessions well.
                        with self._encode_lock:
                            if input_crc_double:
                                try:
                                    crc_now = _crc32_sample_rgb(frame)
                                    if crc_before and crc_now and (crc_now != crc_before):
                                        logger.warning(
                                            "[vrh2-incrc] MUTATED gen=%d before=%08x now=%08x stride=%d",
                                            produced_frames,
                                            crc_before,
                                            crc_now,
                                            input_crc_stride,
                                        )
                                except Exception:
                                    pass
                            left_encoded, right_encoded = encode_stereo_frames(
                                client_encoder,
                                frame,
                                self.stereo_offset,
                            )
                        encode_time = time.time() - encode_start
                        last_encode_s = encode_time
                        self.encode_times.append(encode_time)

                        if mono_packet:
                            right_encoded = b''

                        if not left_encoded or ((not mono_packet) and (not right_encoded)):
                            consecutive_failures += 1
                            if (
                                client_protocol_magic in {b"VRH2", b"VRH3"}
                                and consecutive_failures >= 3
                                and client_encoder is not None
                                and hasattr(client_encoder, "get_encoder_type")
                                and client_encoder.get_encoder_type() == EncoderType.NVENC
                                and (getattr(client_encoder, "is_nvenc", lambda: True)())
                            ):
                                # NVENC can become unusable mid-run. Don't switch codecs mid-connection:
                                # MediaCodec may fail if SPS/PPS/profile changes under it.
                                # Instead, trip the circuit breaker and force a disconnect so the client reconnects
                                # and reconfigures cleanly (new connection uses libx264 VRH2 during cooldown).
                                logger.warning("[vrh2-fallback] NVENC encode failing; forcing reconnect (next connection will use libx264 VRH2)")
                                try:
                                    self._nvenc_failures = int(getattr(self, "_nvenc_failures", 0)) + 1
                                    self._nvenc_last_failure_s = time.time()
                                    cooldown = min(300.0, max(15.0, float(self._nvenc_failures) * 15.0))
                                    self._nvenc_disabled_until = time.time() + cooldown
                                    logger.warning("NVENC circuit breaker tripped: cooldown=%.1fs", cooldown)
                                except Exception:
                                    pass
                                force_disconnect.set()
                            logger.error("Encoding failed")
                            time.sleep(0.005)
                            continue

                        consecutive_failures = 0

                        with latest_lock:
                            latest_left = left_encoded
                            latest_right = right_encoded
                            last_left_kb = len(left_encoded) / 1024.0
                            last_right_kb = len(right_encoded) / 1024.0
                            latest_generation += 1
                            produced_frames += 1
                            latest_ready.set()

                        # Keep only last 120 measurements to avoid memory growth
                        if len(self.encode_times) > 120:
                            self.encode_times = self.encode_times[-120:]

                    except Exception as e:
                        logger.error("Producer thread error: %s", e, exc_info=True)
                        time.sleep(0.05)

            producer_thread = threading.Thread(target=_producer_loop, daemon=True)
            producer_thread.start()

            # Optional debugging: dump the outgoing left-eye H.264 access units to disk.
            # This lets you validate the stream with ffplay (distinguish encoder/packetization vs client decode).
            #
            # Usage (PowerShell):
            #   $env:MESMERGLASS_VRH2_DUMP_DIR = "C:\\temp"
            #   $env:MESMERGLASS_VRH2_DUMP_START = "idr"   # (default) or "immediate"
            #
            # The dump is a raw elementary stream (.h264) and is written per client connection.
            dump_dir_raw = os.environ.get("MESMERGLASS_VRH2_DUMP_DIR")
            dump_start_mode = (os.environ.get("MESMERGLASS_VRH2_DUMP_START") or "idr").strip().lower()

            # Dumps are opt-in (heavy disk I/O). Enable only when MESMERGLASS_VRH2_DUMP_DIR is set.
            dump_enabled = False
            dump_dir: Optional[Path]
            if dump_dir_raw is None or dump_dir_raw.strip() == "":
                dump_dir = None
            else:
                token = dump_dir_raw.strip()
                if token.lower() in {"0", "false", "off", "disable", "disabled", "none"}:
                    dump_enabled = False
                    dump_dir = None
                else:
                    dump_enabled = True
                    candidate = Path(token)
                    dump_dir = candidate if candidate.is_absolute() else (Path.cwd() / candidate)

            if dump_enabled and dump_dir is not None and client_protocol_magic in {b"VRH2", b"VRH3"}:
                try:
                    dump_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_host = str(address[0]).replace(":", "_").replace(".", "-")
                    safe_port = str(address[1])
                    out_path = dump_dir / f"vrh2_{safe_host}_{safe_port}_{ts}.h264"
                    dump_fp = open(out_path, "wb")
                    dump_started = (dump_start_mode != "idr")
                    logger.warning(
                        "[vrh2-dump] Writing raw H.264 to %s (start=%s)",
                        str(out_path),
                        "immediate" if dump_started else "idr",
                    )
                except Exception as e:
                    dump_fp = None
                    logger.warning("[vrh2-dump] Failed to open dump file in %s: %s", str(dump_dir), e)

            # Optional: allow the receiver to request a keyframe over the same TCP socket.
            # This is far more reliable than guessing corruption from access-unit byte size.
            # Protocol: client may send control messages at any time.
            #   0x01                => NEED_IDR
            #   0x02 + int32 + int32 => STATS (buffer_ms, fps_milli) big-endian
            #   0x02 + int32 + int32 + int32 => STATS (buffer_ms, fps_milli, decode_avg_ms)
            # Enable by default: client can send 0x01 to request an IDR.
            # This is a no-op unless the client actually sends control bytes.
            enable_control = _env_truthy_default("MESMERGLASS_VRH2_CONTROL", True)

            need_idr_from_client = False
            last_client_need_idr_at = 0.0

            client_buffer_ms: Optional[int] = None
            client_fps_milli: Optional[int] = None
            client_decode_avg_ms: Optional[int] = None
            last_client_stats_at = 0.0

            async def _control_reader() -> None:
                nonlocal need_idr_from_client, last_client_need_idr_at
                nonlocal client_buffer_ms, client_fps_milli, client_decode_avg_ms, last_client_stats_at
                # Keep reads tiny; client messages are intentionally minimal.
                loop = asyncio.get_event_loop()
                rx = bytearray()
                while self.running:
                    try:
                        data = await loop.sock_recv(client_socket, 16)
                        if not data:
                            return
                        rx.extend(data)
                        while rx:
                            msg = rx[0]
                            if msg == 0x01:
                                del rx[0]
                                now_s = time.time()
                                # Rate-limit flagging to avoid log spam if client loops.
                                if (now_s - last_client_need_idr_at) >= 0.10:
                                    need_idr_from_client = True
                                    last_client_need_idr_at = now_s
                            elif msg == 0x02:
                                # Need full payload: 1 + 8 bytes (or 1 + 12 for extended stats)
                                if len(rx) < 1 + 8:
                                    break
                                try:
                                    # Backward compatible parsing: accept either 2-int or 3-int payloads.
                                    if len(rx) >= 1 + 12:
                                        payload = bytes(rx[1 : 1 + 12])
                                        del rx[: 1 + 12]
                                        buf_ms, fps_milli, dec_ms = struct.unpack("!iii", payload)
                                        client_decode_avg_ms = int(dec_ms)
                                    else:
                                        payload = bytes(rx[1:9])
                                        del rx[:9]
                                        buf_ms, fps_milli = struct.unpack("!ii", payload)
                                    client_buffer_ms = int(buf_ms)
                                    client_fps_milli = int(fps_milli)
                                    last_client_stats_at = time.time()

                                    # Mirror client stats into UI telemetry.
                                    try:
                                        from mesmerglass.engine.streaming_telemetry import streaming_telemetry

                                        streaming_telemetry.update_client_stats(
                                            client_id,
                                            buffer_ms=client_buffer_ms,
                                            fps_milli=client_fps_milli,
                                            decode_avg_ms=(
                                                float(client_decode_avg_ms)
                                                if client_decode_avg_ms is not None
                                                else None
                                            ),
                                        )
                                    except Exception:
                                        pass
                                except Exception:
                                    # Ignore malformed payload.
                                    continue
                            else:
                                # Unknown byte: discard one for forward-compat.
                                del rx[0]
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        return
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        # Never let control-channel issues kill the stream.
                        await asyncio.sleep(0.05)

            control_task: Optional[asyncio.Task] = None
            if enable_control and client_protocol_magic in {b"VRH2", b"VRH3"}:
                try:
                    control_task = asyncio.create_task(_control_reader())
                    logger.info("[vrh2-ctl] control channel enabled (client may send NEED_IDR)")
                except Exception:
                    control_task = None

            # frame_id: internal loop counter (advances even when dropping during resync)
            # wire_frame_id: sequence number sent to client (advances only on successful sends)
            frame_id = 0
            wire_frame_id = 0
            next_frame_ts = time.perf_counter()
            last_produced_at_log = 0
            last_sent_generation = 0

            last_idr_at = None

            recent_sizes = deque(maxlen=max(1, crater_window))
            last_idr_request_frame = -10_000
            last_reset_request_frame = -10_000
            # For VRH2 (H.264), start by dropping access units until we see an IDR.
            # This avoids feeding the decoder P-frames before it has a valid reference picture.
            need_idr_resync = (client_protocol_magic in {b"VRH2", b"VRH3"})
            # Only complete resync on IDRs from generations >= this value.
            # When we request an IDR/reset, we bump this to gen+1 to avoid clearing resync
            # due to an IDR from the *previous* encoder state.
            resync_min_generation = 0
            if need_idr_resync:
                logger.info("[vrh2-idr] initial resync=drop-until-idr")
            
            while self.running:
                if force_disconnect.is_set():
                    break
                # Maintain target FPS
                now = time.perf_counter()
                sleep_s = next_frame_ts - now
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
                else:
                    # If we're behind, don't try to "catch up" by sending bursts.
                    # Resync to avoid jitter/latency spikes.
                    next_frame_ts = now

                next_frame_ts += self.frame_delay

                # Wait for the producer to deliver at least one encoded frame.
                if not latest_ready.is_set():
                    await asyncio.sleep(0.002)
                    continue

                with latest_lock:
                    left_encoded = latest_left
                    right_encoded = latest_right
                    left_kb = last_left_kb
                    right_kb = last_right_kb
                    gen = latest_generation

                if not left_encoded:
                    await asyncio.sleep(0.002)
                    continue

                # Only send when the producer has advanced.
                # Holding the last decoded frame is safer than re-sending old compressed pictures.
                if gen == last_sent_generation:
                    await asyncio.sleep(0.001)
                    continue

                # Optional: ensure access units begin with AUD for better decoder resync.
                # Also optionally log NAL composition for tiny/key access units.
                # IMPORTANT: do this only for frames we will actually send/dump, so diagnostics
                # correlate with captured dumps and packet sequence numbers.
                if client_protocol_magic in {b"VRH2", b"VRH3"}:
                    # Receiver-driven keyframe request (preferred over size-based heuristics).
                    if need_idr_from_client and hasattr(client_encoder, "request_idr"):
                        if (frame_id - last_idr_request_frame) >= idr_cooldown_frames:
                            need_idr_from_client = False
                            last_idr_request_frame = frame_id
                            try:
                                client_encoder.request_idr()
                                # Drop outgoing access units until we see an IDR.
                                # This avoids feeding the decoder additional P-frames while its reference
                                # chain is known-bad (mosaic corruption can persist until the next IDR).
                                need_idr_resync = True
                                resync_min_generation = max(resync_min_generation, int(gen) + 1)

                                # NVENC does not always honor per-frame pict_type forcing; the most reliable
                                # way to guarantee a clean IDR quickly is to recreate the encoder.
                                # Only do this for the hardware NVENC path, and rate-limit to avoid thrash.
                                try:
                                    reset_on_client_idr = _env_truthy_default("MESMERGLASS_VRH2_RESET_ON_CLIENT_IDR", True)
                                    is_hw_nvenc = bool(getattr(client_encoder, "is_nvenc", lambda: False)())
                                    reset_cooldown = max(15, idr_cooldown_frames)
                                    if reset_on_client_idr and is_hw_nvenc and (frame_id - last_reset_request_frame) >= reset_cooldown:
                                        last_reset_request_frame = frame_id
                                        reset_encoder_requested.set()
                                        resync_min_generation = max(resync_min_generation, int(gen) + 1)
                                        logger.warning(
                                            "[vrh2-reset] requested encoder reset (reason=client-idr frame=%d cooldown=%d)",
                                            frame_id,
                                            reset_cooldown,
                                        )
                                except Exception:
                                    pass

                                logger.info(
                                    "[vrh2-idr] requested next IDR (reason=client frame=%d cooldown=%d); resync=drop-until-idr",
                                    frame_id,
                                    idr_cooldown_frames,
                                )
                            except Exception:
                                pass

                    if insert_aud:
                        left_encoded = _h264_insert_aud_if_missing(left_encoded)
                        if right_encoded:
                            right_encoded = _h264_insert_aud_if_missing(right_encoded)

                    if strip_sei:
                        left_encoded = _h264_strip_sei_nals(left_encoded)
                        if right_encoded:
                            right_encoded = _h264_strip_sei_nals(right_encoded)

                    # Per-frame telemetry (opt-in): log AU size + IDR cadence.
                    if frame_log:
                        try:
                            is_idr = _h264_access_unit_contains_idr(left_encoded)
                            now_idr_t = time.perf_counter()
                            if is_idr or (last_idr_at is None):
                                if is_idr:
                                    last_idr_at = now_idr_t
                            ms_since_idr = (0.0 if (last_idr_at is None) else ((now_idr_t - last_idr_at) * 1000.0))
                            logger.info(
                                "[vrh2-frame] id=%d idr=%d bytesL=%d bytesR=%d since_idr_ms=%.1f encode_ms=%.1f",
                                frame_id,
                                (1 if is_idr else 0),
                                len(left_encoded) if left_encoded else 0,
                                len(right_encoded) if right_encoded else 0,
                                ms_since_idr,
                                (float(last_encode_s) * 1000.0 if last_encode_s is not None else 0.0),
                            )
                        except Exception:
                            pass

                    _maybe_log_nal_diag("L", frame_id, left_encoded)
                    if right_encoded:
                        _maybe_log_nal_diag("R", frame_id, right_encoded)

                    # Detect anomalies and request an IDR on the next encoded frame.
                    # We do this after reading the actual bytes that will be sent.
                    try:
                        cur_size = len(left_encoded)
                        recent_sizes.append(cur_size)
                        median = None
                        if idr_on_crater and len(recent_sizes) >= max(8, min(16, recent_sizes.maxlen)):
                            s = sorted(recent_sizes)
                            median = s[len(s) // 2]
                        is_tiny = idr_on_tiny and (cur_size > 0) and (cur_size < idr_tiny_bytes)
                        is_crater = False
                        if idr_on_crater and median is not None and median >= crater_min_median:
                            is_crater = cur_size < (median / max(1e-6, crater_factor))

                        if (is_tiny or is_crater):
                            reason = "tiny" if is_tiny else "crater"

                            # Prefer reset+IDR resync if enabled (more reliable than pict_type forcing).
                            if reset_on_anomaly and (frame_id - last_reset_request_frame) >= reset_cooldown_frames:
                                last_reset_request_frame = frame_id
                                need_idr_resync = True
                                reset_encoder_requested.set()
                                resync_min_generation = max(resync_min_generation, int(gen) + 1)
                                logger.warning(
                                    "[vrh2-reset] requested encoder reset (reason=%s frame=%d bytes=%d median=%s cooldown=%d)",
                                    reason,
                                    frame_id,
                                    cur_size,
                                    (int(median) if median is not None else ""),
                                    reset_cooldown_frames,
                                )
                            elif hasattr(client_encoder, "request_idr") and (frame_id - last_idr_request_frame) >= idr_cooldown_frames:
                                # Fallback: best-effort keyframe request.
                                last_idr_request_frame = frame_id
                                client_encoder.request_idr()
                                logger.warning(
                                    "[vrh2-idr] requested next IDR (reason=%s frame=%d bytes=%d median=%s cooldown=%d)",
                                    reason,
                                    frame_id,
                                    cur_size,
                                    (int(median) if median is not None else ""),
                                    idr_cooldown_frames,
                                )
                    except Exception:
                        pass

                # If we're resyncing after a reset, drop frames until we see an IDR.
                if need_idr_resync and client_protocol_magic in {b"VRH2", b"VRH3"}:
                    if gen < resync_min_generation:
                        # Ensure we don't accidentally clear resync on a pre-reset generation.
                        last_sent_generation = gen
                        _mark_generation_consumed(gen)
                        frame_id += 1
                        continue

                    if _h264_access_unit_contains_idr(left_encoded):
                        need_idr_resync = False
                        logger.warning("[vrh2-reset] IDR resync achieved at frame=%d", frame_id)
                    else:
                        # Skip sending/dumping this access unit.
                        last_sent_generation = gen
                        _mark_generation_consumed(gen)
                        frame_id += 1
                        continue

                # Dump access units to disk (left eye only). Optionally wait until first IDR.
                if dump_fp is not None:
                    try:
                        if (not dump_started) and _h264_access_unit_contains_idr(left_encoded):
                            dump_started = True
                        if dump_started:
                            with dump_lock:
                                if dump_fp is not None:
                                    dump_fp.write(left_encoded)
                                    # Avoid excessive flush overhead; flush about once per second.
                                    if frame_id % 60 == 0:
                                        dump_fp.flush()
                    except Exception:
                        # Best-effort; never fail the stream due to debug dumping.
                        pass
                
                # Create packet
                packet = self.create_packet(
                    left_encoded,
                    right_encoded,
                    wire_frame_id,
                    protocol_magic=client_protocol_magic,
                    fps_milli=(int(float(getattr(self, "fps", 30) or 30) * 1000.0) if client_protocol_magic == b"VRH3" else None),
                )
                packet_size = len(packet)
                self.total_bytes_sent += packet_size
                
                # Send packet (measure send time)
                send_start = time.time()
                try:
                    loop = asyncio.get_event_loop()
                    await loop.sock_sendall(client_socket, packet)
                    send_time = time.time() - send_start
                    self.send_times.append(send_time)

                    # Mark this producer generation as consumed/sent.
                    last_sent_generation = gen
                    _mark_generation_consumed(gen)
                    
                    frame_id += 1
                    wire_frame_id += 1
                    self.frames_sent += 1
                    
                    # Print detailed statistics every 60 frames (1 second at 60fps, 2 seconds at 30fps)
                    if wire_frame_id % 60 == 0:
                        current_time = time.time()
                        runtime = current_time - self.start_time
                        stats_window = current_time - self.last_stats_time
                        
                        actual_fps = self.frames_sent / runtime if runtime > 0 else 0
                        window_fps = 60 / stats_window if stats_window > 0 else 0
                        produced_window = produced_frames - last_produced_at_log
                        produced_fps = (produced_window / stats_window) if stats_window > 0 else 0
                        last_produced_at_log = produced_frames
                        
                        # Calculate averages for last ~60 produced frames
                        avg_encode_ms = (sum(self.encode_times[-60:]) / min(60, len(self.encode_times))) * 1000 if self.encode_times else 0
                        avg_send_ms = (sum(self.send_times[-60:]) / min(60, len(self.send_times))) * 1000 if self.send_times else 0
                        total_latency_ms = avg_encode_ms + avg_send_ms
                        
                        # Calculate bandwidth
                        bandwidth_mbps = (self.total_bytes_sent * 8) / (runtime * 1_000_000) if runtime > 0 else 0
                        
                        # Calculate frame sizes (latest)
                        total_kb = left_kb + right_kb
                        
                        logger.warning(f"📊 VR Performance Stats (Frame {wire_frame_id}):")
                        logger.warning(f"   FPS: {window_fps:.1f} send (window) | {actual_fps:.1f} send (avg) | {produced_fps:.1f} produced (window)")
                        logger.warning(
                            f"   Server time: {total_latency_ms:.1f}ms (encode: {avg_encode_ms:.1f}ms, sock_send: {avg_send_ms:.1f}ms)"
                        )
                        if client_buffer_ms is not None:
                            age_s = time.time() - float(last_client_stats_at or 0.0)
                            logger.warning(f"   Client buffer: {int(client_buffer_ms)} ms (age: {age_s:.2f}s)")
                        logger.warning(f"   Bandwidth: {bandwidth_mbps:.2f} Mbps")
                        logger.warning(f"   Frame size: {total_kb:.1f} KB (L: {left_kb:.1f} KB, R: {right_kb:.1f} KB)")

                        # Publish to UI telemetry.
                        try:
                            from mesmerglass.engine.streaming_telemetry import streaming_telemetry

                            streaming_telemetry.update_server_stats(
                                client_id,
                                protocol=(
                                    client_protocol_magic.decode("ascii", errors="ignore")
                                    if client_protocol_magic is not None
                                    else None
                                ),
                                bitrate_bps=int(client_bitrate) if client_bitrate else None,
                                send_fps=float(window_fps),
                                produced_fps=float(produced_fps),
                                encode_avg_ms=float(avg_encode_ms),
                                send_avg_ms=float(avg_send_ms),
                                bandwidth_mbps=float(bandwidth_mbps),
                                frame_kb=float(total_kb),
                                client_buffer_ms=(int(client_buffer_ms) if client_buffer_ms is not None else None),
                                client_fps_milli=(int(client_fps_milli) if client_fps_milli is not None else None),
                            )
                        except Exception:
                            pass

                        # Adaptive bitrate: react to sustained congestion and slowly recover.
                        # Applies to VRH2/VRH3, and is rate-limited to avoid encoder thrash.
                        if adaptive_enabled and client_protocol_magic in {b"VRH2", b"VRH3"} and (not need_idr_resync):
                            try:
                                now_s = time.time()
                                # Avoid reacting to startup transients / first IDR resets.
                                if adaptive_warmup_s > 0.0 and (runtime < adaptive_warmup_s):
                                    raise RuntimeError("warmup")
                                target_fps = float(getattr(self, "fps", 30) or 30)
                                should_wait = (adaptive_cooldown_s > 0.0) and ((now_s - adaptive_last_change_s) < adaptive_cooldown_s)
                                if not should_wait:
                                    too_slow_fps = window_fps < (target_fps * adaptive_fps_lo_ratio)
                                    healthy_fps = window_fps >= (target_fps * adaptive_fps_hi_ratio)
                                    too_slow_send = avg_send_ms >= adaptive_send_ms_hi
                                    healthy_send = avg_send_ms <= adaptive_send_ms_lo

                                    # Client feedback (if available) takes priority for smoothness.
                                    has_client_stats = (
                                        (client_buffer_ms is not None)
                                        and ((now_s - float(last_client_stats_at)) <= adaptive_client_stats_max_age_s)
                                    )
                                    client_buf = int(client_buffer_ms) if client_buffer_ms is not None else 0

                                    new_bitrate = client_bitrate
                                    direction = None
                                    if has_client_stats and (client_buf < adaptive_client_buffer_ms_lo) and (client_bitrate > adaptive_min_bitrate):
                                        direction = 'down'
                                        new_bitrate = _adaptive_next_bitrate(client_bitrate, 'down')
                                    elif has_client_stats and (client_buf > adaptive_client_buffer_ms_hi) and healthy_send and (client_bitrate < adaptive_max_bitrate):
                                        direction = 'up'
                                        new_bitrate = _adaptive_next_bitrate(client_bitrate, 'up')
                                    elif (too_slow_fps or too_slow_send) and (client_bitrate > adaptive_min_bitrate):
                                        direction = 'down'
                                        new_bitrate = _adaptive_next_bitrate(client_bitrate, 'down')
                                    elif healthy_fps and healthy_send and (client_bitrate < adaptive_max_bitrate):
                                        direction = 'up'
                                        new_bitrate = _adaptive_next_bitrate(client_bitrate, 'up')

                                    if direction is not None and new_bitrate != client_bitrate:
                                        client_bitrate = new_bitrate
                                        adaptive_last_change_s = now_s
                                        # Apply change safely: reset encoder and resync on next IDR.
                                        need_idr_resync = True
                                        resync_min_generation = max(resync_min_generation, int(gen) + 1)
                                        reset_encoder_requested.set()
                                        logger.warning(
                                            "[vrh2-adapt] bitrate_%s => %.1f Mbps (send_ms=%.2f fps=%.1f target=%.1f client_buf_ms=%s)",
                                            direction,
                                            (client_bitrate / 1_000_000.0),
                                            float(avg_send_ms),
                                            float(window_fps),
                                            float(target_fps),
                                            (str(client_buffer_ms) if has_client_stats else "n/a"),
                                        )
                            except Exception:
                                pass
                        
                        self.last_stats_time = current_time
                        
                        # Keep only last 120 measurements to avoid memory growth
                        if len(self.send_times) > 120:
                            self.send_times = self.send_times[-120:]
                
                except (BrokenPipeError, ConnectionResetError) as e:
                    logger.info("Client %s disconnected (%s)", address, e.__class__.__name__)
                    break
                except OSError as e:
                    # Windows often surfaces disconnects as OSError with WinError codes.
                    logger.info("Client %s disconnected (OSError: %s)", address, e)
                    break
        
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}", exc_info=True)
        finally:
            # Publish disconnection state for UI telemetry.
            try:
                from mesmerglass.engine.streaming_telemetry import streaming_telemetry

                streaming_telemetry.set_connected(client_id, False)
            except Exception:
                pass

            try:
                if control_task is not None:
                    control_task.cancel()
            except Exception:
                pass

            try:
                stop_producer.set()
                producer_thread.join(timeout=1.0)
            except Exception:
                pass

            try:
                if client_encoder is not None:
                    client_encoder.close()
            except Exception:
                pass

            try:
                if dump_fp is not None:
                    dump_fp.flush()
                    dump_fp.close()
            except Exception:
                pass

            client_socket.close()
            if client_socket in self.clients:
                self.clients.remove(client_socket)
    
    def _generate_test_frame(self) -> np.ndarray:
        """Generate test pattern frame"""
        # Simple checkerboard pattern
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Animated checkerboard
        t = time.time()
        offset = int(t * 50) % 64
        
        for y in range(0, self.height, 32):
            for x in range(0, self.width, 32):
                if ((x + y + offset) // 32) % 2 == 0:
                    frame[y:y+32, x:x+32] = [255, 0, 255]  # Magenta
                else:
                    frame[y:y+32, x:x+32] = [0, 255, 255]  # Cyan
        
        return frame
    
    async def start(self):
        """Start the VR streaming server"""
        if self.running:
            logger.warning("Server already running")
            return
        
        self.running = True
        
        # Start discovery service
        self.discovery_service = DiscoveryService(self.discovery_port, self.port)
        self.discovery_service.start()
        
        # Create TCP socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Disable Nagle's algorithm for lower latency
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        # Bind and listen
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.setblocking(False)
        
        logger.info("=" * 60)
        logger.info("🎮 VR STREAMING SERVER STARTED")
        logger.info("=" * 60)
        logger.warning(f"Address: {self.host}:{self.port}")
        logger.warning(f"Resolution: {self.target_width}x{self.target_height} (source {self.width}x{self.height})")
        logger.warning(f"Target FPS: {self.fps}")
        logger.warning(f"Encoder: {self.encoder_type.value.upper()}")
        if self.encoder_type == EncoderType.NVENC:
            try:
                bitrate_mbps = float(getattr(self, "bitrate", 0)) / 1_000_000.0
                if bitrate_mbps > 0:
                    logger.warning(f"Bitrate: {bitrate_mbps:.1f} Mbps")
            except Exception:
                pass
        logger.warning(f"Protocol: {self.protocol_magic.decode('ascii')}")
        logger.info("🎯 Server will automatically connect to discovered VR headsets!")
        logger.info("   Just launch the app on your VR headset - no IP entry needed!")
        logger.info("=" * 60)
        
        loop = asyncio.get_event_loop()
        
        try:
            while self.running:
                try:
                    client_socket, address = await loop.sock_accept(self.server_socket)
                except OSError as exc:
                    err = getattr(exc, "winerror", exc.errno)
                    if err in _WIN_ABORT_ERRNOS:
                        logger.info("VR streaming server accept loop aborted during shutdown")
                        break
                    raise
                
                # Disable blocking
                client_socket.setblocking(False)

                # Prefer low-latency and resilience on the accepted connection.
                try:
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
                try:
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except Exception:
                    pass
                try:
                    # Larger send buffer helps smooth over short Wi‑Fi hiccups.
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1_048_576)
                except Exception:
                    pass
                
                # Add to clients list
                self.clients.append(client_socket)
                
                # Handle client in separate task and track it for clean shutdown
                task = asyncio.create_task(self.handle_client(client_socket, address))
                self._client_tasks.add(task)
                task.add_done_callback(lambda t: self._client_tasks.discard(t))
        
        except KeyboardInterrupt:
            logger.info("\nShutting down server...")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the server and close all connections"""
        logger.info("Closing connections...")
        
        self.running = False
        
        # Stop discovery service
        if self.discovery_service:
            self.discovery_service.stop()
        
        # Close client connections
        for client in self.clients:
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()
        
        # Cancel outstanding client tasks
        if self._client_tasks:
            for task in list(self._client_tasks):
                task.cancel()
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
            self._client_tasks.clear()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None
        
        # Close encoder
        if self.encoder:
            try:
                self.encoder.close()
            except Exception:
                pass
            self.encoder = None
        
        logger.info("Server stopped")


async def run_test_server(
    pattern: str = "checkerboard",
    duration: int = 0,
    **kwargs
):
    """
    Run test server with generated pattern
    
    Args:
        pattern: Test pattern type (checkerboard, gradient, noise)
        duration: Duration in seconds (0 = infinite)
        **kwargs: Additional arguments for VRStreamingServer
    """
    logger.info(f"Starting test server with pattern: {pattern}")
    
    def test_frame_generator() -> np.ndarray:
        """Generate test pattern frames"""
        width = kwargs.get('width', 1920)
        height = kwargs.get('height', 1080)
        
        if pattern == "checkerboard":
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            t = time.time()
            offset = int(t * 50) % 64
            
            for y in range(0, height, 32):
                for x in range(0, width, 32):
                    if ((x + y + offset) // 32) % 2 == 0:
                        frame[y:y+32, x:x+32] = [255, 0, 255]
                    else:
                        frame[y:y+32, x:x+32] = [0, 255, 255]
        
        elif pattern == "gradient":
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            t = time.time()
            for y in range(height):
                color = int((y / height * 255 + t * 50) % 255)
                frame[y, :] = [color, 255 - color, 128]
        
        elif pattern == "noise":
            frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        
        else:
            frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        return frame
    
    # Create server with test generator
    server = VRStreamingServer(frame_callback=test_frame_generator, **kwargs)
    
    # Run for specified duration
    try:
        if duration > 0:
            logger.info(f"Running test for {duration} seconds...")
            await asyncio.wait_for(server.start(), timeout=duration)
        else:
            await server.start()
    except asyncio.TimeoutError:
        # Expected when duration expires
        logger.info(f"Test completed after {duration} seconds")
        await server.stop()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        await server.stop()


if __name__ == "__main__":
    # Test server
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        server = VRStreamingServer(
            encoder_type=EncoderType.AUTO,
            width=1920,
            height=1080,
            fps=30
        )
        await server.start()
    
    asyncio.run(main())
