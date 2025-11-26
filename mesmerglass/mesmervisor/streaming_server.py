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
import numpy as np
import cv2
from typing import Optional, Set, Tuple, Callable
from queue import Queue, Empty

from .frame_encoder import FrameEncoder, create_encoder, encode_stereo_frames
from .gpu_utils import EncoderType, select_encoder

logger = logging.getLogger(__name__)


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
        bitrate: int = 2000000,
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
                width=width,
                height=height,
                fps=fps,
                bitrate=bitrate
            )
            self.protocol_magic = b'VRH2'  # VR H.264
        else:
            self.encoder = create_encoder(
                EncoderType.JPEG,
                width=width,
                height=height,
                quality=quality
            )
            self.protocol_magic = b'VRHP'  # VR Hypnotic Protocol (JPEG)
        
        # Server state
        self.server_socket: Optional[socket.socket] = None
        self.discovery_service: Optional[DiscoveryService] = None
        self.clients = []
        self.running = False
        
        # Frame timing
        self.frame_delay = 1.0 / fps
        self.frames_sent = 0
        self.start_time = time.time()
        
        # Performance tracking
        self.total_bytes_sent = 0
        self.encode_times = []
        self.send_times = []
        self.last_stats_time = time.time()
        
        logger.info(f"VRStreamingServer initialized: {width}x{height} @ {fps} FPS")
        
        # Thread for async server
        self._server_thread: Optional[threading.Thread] = None
        self._server_loop: Optional[asyncio.AbstractEventLoop] = None
    
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
        - Right eye frame data
        
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
        
        try:
            frame_id = 0
            last_frame_time = time.time()
            
            while self.running:
                # Maintain target FPS
                current_time = time.time()
                elapsed = current_time - last_frame_time
                
                if elapsed < self.frame_delay:
                    await asyncio.sleep(self.frame_delay - elapsed)
                
                last_frame_time = time.time()
                
                # Get frame from callback
                if self.frame_callback is None:
                    # No callback - generate test pattern
                    frame = self._generate_test_frame()
                else:
                    frame = self.frame_callback()
                    if frame is None:
                        logger.warning("Frame callback returned None")
                        await asyncio.sleep(0.1)
                        continue
                
                # Downscale to target resolution if needed (for Oculus Go optimization)
                if frame.shape[1] != self.target_width or frame.shape[0] != self.target_height:
                    frame = cv2.resize(frame, (self.target_width, self.target_height), 
                                      interpolation=cv2.INTER_LINEAR)
                
                # Encode stereo frames (measure encoding time)
                encode_start = time.time()
                left_encoded, right_encoded = encode_stereo_frames(
                    self.encoder,
                    frame,
                    self.stereo_offset
                )
                encode_time = time.time() - encode_start
                self.encode_times.append(encode_time)
                
                if not left_encoded or not right_encoded:
                    logger.error("Encoding failed")
                    continue
                
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
                        
                        # Calculate averages for last 60 frames
                        avg_encode_ms = (sum(self.encode_times[-60:]) / min(60, len(self.encode_times))) * 1000 if self.encode_times else 0
                        avg_send_ms = (sum(self.send_times[-60:]) / min(60, len(self.send_times))) * 1000 if self.send_times else 0
                        total_latency_ms = avg_encode_ms + avg_send_ms
                        
                        # Calculate bandwidth
                        bandwidth_mbps = (self.total_bytes_sent * 8) / (runtime * 1_000_000) if runtime > 0 else 0
                        
                        # Calculate frame sizes
                        left_kb = len(left_encoded) / 1024
                        right_kb = len(right_encoded) / 1024
                        total_kb = (len(left_encoded) + len(right_encoded)) / 1024
                        
                        logger.info(f"📊 VR Performance Stats (Frame {frame_id}):")
                        logger.info(f"   FPS: {window_fps:.1f} (window) | {actual_fps:.1f} (avg)")
                        logger.info(f"   Latency: {total_latency_ms:.1f}ms (encode: {avg_encode_ms:.1f}ms, send: {avg_send_ms:.1f}ms)")
                        logger.info(f"   Bandwidth: {bandwidth_mbps:.2f} Mbps")
                        logger.info(f"   Frame size: {total_kb:.1f} KB (L: {left_kb:.1f} KB, R: {right_kb:.1f} KB)")
                        
                        self.last_stats_time = current_time
                        
                        # Keep only last 120 measurements to avoid memory growth
                        if len(self.encode_times) > 120:
                            self.encode_times = self.encode_times[-120:]
                        if len(self.send_times) > 120:
                            self.send_times = self.send_times[-120:]
                
                except (BrokenPipeError, ConnectionResetError):
                    logger.info(f"Client {address} disconnected")
                    break
        
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}", exc_info=True)
        finally:
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
        logger.info(f"Address: {self.host}:{self.port}")
        logger.info(f"Resolution: {self.width}x{self.height}")
        logger.info(f"Target FPS: {self.fps}")
        logger.info(f"Encoder: {self.encoder_type.value.upper()}")
        logger.info(f"Protocol: {self.protocol_magic.decode('ascii')}")
        logger.info("🎯 Server will automatically connect to discovered VR headsets!")
        logger.info("   Just launch the app on your VR headset - no IP entry needed!")
        logger.info("=" * 60)
        
        loop = asyncio.get_event_loop()
        
        try:
            while self.running:
                # Accept new connections
                client_socket, address = await loop.sock_accept(self.server_socket)
                
                # Disable blocking
                client_socket.setblocking(False)
                
                # Add to clients list
                self.clients.append(client_socket)
                
                # Handle client in separate task
                asyncio.create_task(self.handle_client(client_socket, address))
        
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
            except:
                pass
        
        # Close server socket
        if self.server_socket:
            self.server_socket.close()
        
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
