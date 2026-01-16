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

_WIN_ABORT_ERRNOS = {995, 10038}


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
                        device_name = parts[1] if len(parts) > 1 else "Unknown Device"
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
                                "type": "vr"  # CRITICAL: Add type field for display filtering
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
            port: TCP streaming port (default 5555)
            discovery_port: UDP discovery port (default 5556)
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
        
        # Create encoder
        if self.encoder_type == EncoderType.NVENC:
            self.encoder = create_encoder(
                EncoderType.NVENC,
                width=self.target_width,
                height=self.target_height,
                fps=fps,
                bitrate=bitrate
            )
            self.protocol_magic = b'VRH2'  # VR H.264
        else:
            self.encoder = create_encoder(
                EncoderType.JPEG,
                width=self.target_width,
                height=self.target_height,
                quality=quality
            )
            self.protocol_magic = b'VRHP'  # VR Hypnotic Protocol (JPEG)
        
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
    
    def create_packet(self, left_frame: bytes, right_frame: bytes, frame_id: int) -> bytes:
        """
        Create network packet with stereo frames
        
        Packet format (ALL PROTOCOLS):
        - Packet size (4 bytes, big-endian int)
        - Header (16 bytes): magic(4) + frame_id(4) + left_size(4) + right_size(4)
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
        header = struct.pack('!4sIII', self.protocol_magic, frame_id, left_size, right_size)
        
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

        # IMPORTANT: Use a fresh encoder per client.
        # If we reuse the encoder across connections, a newly connected client can start mid-GOP
        # (receiving P-frames that reference pictures it never saw), which looks like heavy mosaic
        # until the next IDR. A per-client encoder ensures the first access units are decodable.
        client_encoder: Optional[FrameEncoder] = None
        dump_fp: Optional[object] = None
        dump_started: bool = False

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

        insert_aud = _env_truthy("MESMERGLASS_VRH2_INSERT_AUD")
        nal_diag_mode = (os.environ.get("MESMERGLASS_VRH2_NAL_DIAG") or "").strip().lower()

        frame_log = _env_truthy_default("MESMERGLASS_VRH2_FRAME_LOG", False)

        # Optional debugging: dump raw pre-encode frames to PNG. This decisively answers whether
        # corruption exists before encoding (capture/compositor/race) or only after encoding.
        raw_dump_dir_env = (os.environ.get("MESMERGLASS_VRH2_RAW_DUMP_DIR") or "").strip()
        raw_dump_every = _env_int("MESMERGLASS_VRH2_RAW_DUMP_EVERY", 0)
        raw_dump_max = _env_int("MESMERGLASS_VRH2_RAW_DUMP_MAX", 0)
        deep_copy_input = _env_truthy_default("MESMERGLASS_VRH2_DEEPCOPY_INPUT", False)

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
                client_encoder = create_encoder(
                    EncoderType.NVENC,
                    width=self.target_width,
                    height=self.target_height,
                    fps=self.fps,
                    bitrate=getattr(self.encoder, "bitrate", 50_000_000),
                )
            else:
                client_encoder = create_encoder(
                    EncoderType.JPEG,
                    width=self.target_width,
                    height=self.target_height,
                    quality=getattr(self.encoder, "quality", 25),
                )

            # Producer thread continuously refreshes the *latest* encoded frame.
            # The send loop runs at a steady tick and re-sends the latest encoded bytes when the
            # compositor/callback stalls. This stabilizes pacing (smoothness) even when the
            # source frame rate dips.
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
                    if self.encoder_type == EncoderType.NVENC:
                        return create_encoder(
                            EncoderType.NVENC,
                            width=self.target_width,
                            height=self.target_height,
                            fps=self.fps,
                            bitrate=getattr(self.encoder, "bitrate", 50_000_000),
                        )
                    return create_encoder(
                        EncoderType.JPEG,
                        width=self.target_width,
                        height=self.target_height,
                        quality=getattr(self.encoder, "quality", 25),
                    )
                except Exception as e:
                    logger.warning("[vrh2-reset] Failed to recreate encoder: %s", e)
                    return None

            def _producer_loop():
                nonlocal latest_left, latest_right, latest_generation, last_left_kb, last_right_kb, last_encode_s, produced_frames, last_producer_warn, producer_warn_count, client_encoder
                raw_dump_count = 0
                raw_dump_fail_count = 0
                while self.running and (not stop_producer.is_set()):
                    try:
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
                                    logger.warning("[vrh2-reset] Encoder recreated")

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
                            if deep_copy_input:
                                frame = frame.copy()
                        except Exception:
                            time.sleep(0.005)
                            continue

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

                        encode_start = time.time()
                        # Serialize GPU encode by default; multiple encoders can exist if multiple
                        # clients connect, but not all systems handle parallel NVENC sessions well.
                        with self._encode_lock:
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
                            logger.error("Encoding failed")
                            time.sleep(0.005)
                            continue

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

            # Default: write dumps into the current working directory under dumps/.
            # This avoids using OS temp folders and makes artifacts easy to find next to the project.
            dump_enabled = True
            dump_dir: Optional[Path]
            if dump_dir_raw is None or dump_dir_raw.strip() == "":
                dump_dir = Path.cwd() / "dumps" / "vrh2_dump"
            else:
                token = dump_dir_raw.strip()
                if token.lower() in {"0", "false", "off", "disable", "disabled", "none"}:
                    dump_enabled = False
                    dump_dir = None
                else:
                    candidate = Path(token)
                    dump_dir = candidate if candidate.is_absolute() else (Path.cwd() / candidate)

            if dump_enabled and dump_dir is not None and self.protocol_magic == b"VRH2":
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
            # Protocol: client may send 1-byte control messages at any time.
            #   0x01 => NEED_IDR
            enable_control = _env_truthy_default("MESMERGLASS_VRH2_CONTROL", False)

            need_idr_from_client = False
            last_client_need_idr_at = 0.0

            async def _control_reader() -> None:
                nonlocal need_idr_from_client, last_client_need_idr_at
                # Keep reads tiny; client messages are intentionally minimal.
                loop = asyncio.get_event_loop()
                while self.running:
                    try:
                        data = await loop.sock_recv(client_socket, 16)
                        if not data:
                            return
                        for b in data:
                            if b == 0x01:
                                now_s = time.time()
                                # Rate-limit flagging to avoid log spam if client loops.
                                if (now_s - last_client_need_idr_at) >= 0.10:
                                    need_idr_from_client = True
                                    last_client_need_idr_at = now_s
                            # Unknown bytes are ignored for forward-compat.
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        return
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        # Never let control-channel issues kill the stream.
                        await asyncio.sleep(0.05)

            control_task: Optional[asyncio.Task] = None
            if enable_control and self.protocol_magic == b"VRH2":
                try:
                    control_task = asyncio.create_task(_control_reader())
                    logger.info("[vrh2-ctl] control channel enabled (client may send NEED_IDR)")
                except Exception:
                    control_task = None

            frame_id = 0
            next_frame_ts = time.perf_counter()
            last_produced_at_log = 0
            last_sent_generation = 0

            last_idr_at = None

            recent_sizes = deque(maxlen=max(1, crater_window))
            last_idr_request_frame = -10_000
            last_reset_request_frame = -10_000
            need_idr_resync = False
            
            while self.running:
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

                # Only send when there's a newly produced encoded frame.
                # This avoids flooding the client with duplicate frames when the compositor stalls.
                if gen == last_sent_generation:
                    continue
                last_sent_generation = gen

                # Optional: ensure access units begin with AUD for better decoder resync.
                # Also optionally log NAL composition for tiny/key access units.
                # IMPORTANT: do this only for frames we will actually send/dump, so diagnostics
                # correlate with captured dumps and packet sequence numbers.
                if self.protocol_magic == b"VRH2":
                    # Receiver-driven keyframe request (preferred over size-based heuristics).
                    if need_idr_from_client and hasattr(client_encoder, "request_idr"):
                        if (frame_id - last_idr_request_frame) >= idr_cooldown_frames:
                            need_idr_from_client = False
                            last_idr_request_frame = frame_id
                            try:
                                client_encoder.request_idr()
                                logger.info("[vrh2-idr] requested next IDR (reason=client frame=%d cooldown=%d)", frame_id, idr_cooldown_frames)
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
                if need_idr_resync and self.protocol_magic == b"VRH2":
                    if _h264_access_unit_contains_idr(left_encoded):
                        need_idr_resync = False
                        logger.warning("[vrh2-reset] IDR resync achieved at frame=%d", frame_id)
                    else:
                        # Skip sending/dumping this access unit.
                        frame_id += 1
                        continue

                # Dump access units to disk (left eye only). Optionally wait until first IDR.
                if dump_fp is not None:
                    try:
                        if (not dump_started) and _h264_access_unit_contains_idr(left_encoded):
                            dump_started = True
                        if dump_started:
                            dump_fp.write(left_encoded)
                            # Avoid excessive flush overhead; flush about once per second.
                            if frame_id % 60 == 0:
                                dump_fp.flush()
                    except Exception:
                        # Best-effort; never fail the stream due to debug dumping.
                        pass
                
                # Create packet
                packet = self.create_packet(left_encoded, right_encoded, frame_id)
                packet_size = len(packet)
                self.total_bytes_sent += packet_size
                
                # Send packet (measure send time)
                send_start = time.time()
                try:
                    loop = asyncio.get_event_loop()
                    await loop.sock_sendall(client_socket, packet)
                    send_time = time.time() - send_start
                    self.send_times.append(send_time)
                    
                    frame_id += 1
                    self.frames_sent += 1
                    
                    # Print detailed statistics every 60 frames (1 second at 60fps, 2 seconds at 30fps)
                    if frame_id % 60 == 0:
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
                        
                        logger.warning(f"📊 VR Performance Stats (Frame {frame_id}):")
                        logger.warning(f"   FPS: {window_fps:.1f} send (window) | {actual_fps:.1f} send (avg) | {produced_fps:.1f} produced (window)")
                        logger.warning(f"   Latency: {total_latency_ms:.1f}ms (encode: {avg_encode_ms:.1f}ms, send: {avg_send_ms:.1f}ms)")
                        logger.warning(f"   Bandwidth: {bandwidth_mbps:.2f} Mbps")
                        logger.warning(f"   Frame size: {total_kb:.1f} KB (L: {left_kb:.1f} KB, R: {right_kb:.1f} KB)")
                        
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
                bitrate_mbps = float(getattr(self.encoder, "bitrate", 0)) / 1_000_000.0
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
            self.encoder.close()
        
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
