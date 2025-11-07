"""VR streaming integration for MesmerGlass launcher.

Provides UDP discovery and TCP streaming to Android VR clients.
"""

import socket
import threading
import logging
import time
import struct
import numpy as np
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


@dataclass
class VRClient:
    """Discovered VR client."""
    ip: str
    port: int
    name: str
    last_seen: float
    
    def __str__(self):
        return f"{self.name} ({self.ip}:{self.port})"


class VRDiscovery:
    """UDP-based VR client discovery - listens for client announcements."""
    
    DISCOVERY_PORT = 8766  # UDP port to listen for client hellos
    CLIENT_TIMEOUT = 5.0  # seconds
    
    def __init__(self):
        self.running = False
        self.clients: Dict[str, VRClient] = {}
        self.lock = threading.Lock()
        self.discovery_thread: Optional[threading.Thread] = None
        self.on_client_found: Optional[Callable[[VRClient], None]] = None
        self.on_client_lost: Optional[Callable[[VRClient], None]] = None
        self.logger = logging.getLogger(__name__)
        
    def start(self):
        """Start listening for VR client announcements."""
        if self.running:
            return
            
        self.running = True
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()
        self.logger.info("VR discovery started - listening on UDP port %d", self.DISCOVERY_PORT)
        
    def stop(self):
        """Stop discovery."""
        self.running = False
        if self.discovery_thread:
            self.discovery_thread.join(timeout=2.0)
        self.logger.info("VR discovery stopped")
        
    def get_clients(self) -> List[VRClient]:
        """Get list of currently discovered clients."""
        with self.lock:
            # Remove stale clients
            now = time.time()
            stale = [k for k, v in self.clients.items() 
                    if now - v.last_seen > self.CLIENT_TIMEOUT]
            for key in stale:
                client = self.clients.pop(key)
                self.logger.info("VR client timeout: %s", client)
                if self.on_client_lost:
                    try:
                        self.on_client_lost(client)
                    except Exception as e:
                        self.logger.error("Error in on_client_lost callback: %s", e)
                        
            return list(self.clients.values())
            
    def _discovery_loop(self):
        """Background thread that listens for VR client announcements."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        
        try:
            sock.bind(('', self.DISCOVERY_PORT))
            self.logger.info("📡 Listening for VR client announcements on port %d", self.DISCOVERY_PORT)
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    message = data.decode('utf-8').strip()
                    self.logger.info("📨 Received UDP from %s: %s", addr, message)
                    
                    # Expected format: "MESMERGLASS_VR_CLIENT:DeviceName:Port"
                    if message.startswith("MESMERGLASS_VR_CLIENT:"):
                        self._handle_client_hello(message, addr[0])
                        
                        # Send acknowledgment back to client
                        response = b"MESMERGLASS_VR_SERVER_ACK"
                        sock.sendto(response, addr)
                        self.logger.info("✅ Sent ACK to %s", addr)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error("Discovery receive error: %s", e)
                        
        except Exception as e:
            self.logger.error("Failed to bind discovery socket: %s", e)
        finally:
            sock.close()
        
    def _handle_client_hello(self, message: str, client_ip: str):
        """Handle VR client hello announcement."""
        try:
            self.logger.info("Processing client hello: %s from %s", message, client_ip)
            
            # Parse: "MESMERGLASS_VR_CLIENT:DeviceName:Port"
            parts = message.split(':')
            if len(parts) < 3:
                self.logger.warning("Invalid hello format: %s", message)
                return
                
            client_name = parts[1]
            client_port = int(parts[2])
            
            client_key = f"{client_ip}:{client_port}"
            
            with self.lock:
                if client_key not in self.clients:
                    client = VRClient(
                        ip=client_ip,
                        port=client_port,
                        name=client_name,
                        last_seen=time.time()
                    )
                    self.clients[client_key] = client
                    self.logger.info("✅ VR client discovered: %s (%s:%d)", client_name, client_ip, client_port)
                    if self.on_client_found:
                        try:
                            self.on_client_found(client)
                        except Exception as e:
                            self.logger.error("Error in on_client_found callback: %s", e)
                else:
                    self.clients[client_key].last_seen = time.time()
                    self.logger.debug("Updated last_seen for %s", client_key)
                    
        except Exception as e:
            self.logger.error("Failed to parse client hello: %s", e)
            self.logger.error("Error handling discovery response: %s", e)


class VRStreaming:
    """VR streaming manager - integrates with LoomCompositor."""
    
    def __init__(self):
        self.active_client: Optional[VRClient] = None
        self.streaming = False
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self._stream_thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._compositor = None  # Will be set by launcher
        self._target_fps = 60
        self._jpeg_quality = 50  # Reduced from 85 for better performance (lower bandwidth)
        
        # Target resolution for VR streaming (optimized for Oculus Go: 2048x1024)
        # Oculus Go has 2x 1024x1024 displays = 2048x1024 total
        self._target_width = 2048
        self._target_height = 1024
        
    def set_compositor(self, compositor):
        """Set the compositor to capture frames from."""
        self._compositor = compositor
        self.logger.info("VR streaming compositor set: %s", compositor)
        
    def set_client(self, client: Optional[VRClient]):
        """Set the active streaming client."""
        with self.lock:
            if client != self.active_client:
                self.logger.info("VR streaming client changed: %s -> %s", 
                               self.active_client, client)
                self.active_client = client
                
    def start_streaming(self):
        """Start streaming to active client."""
        if not HAS_CV2:
            self.logger.error("OpenCV not available - cannot stream")
            return False
            
        with self.lock:
            if not self.active_client:
                self.logger.warning("Cannot start streaming: no active client")
                return False
                
            if self.streaming:
                self.logger.warning("Already streaming")
                return True
                
            self.streaming = True
            
        # Start streaming thread
        self._stream_thread = threading.Thread(target=self._streaming_loop, daemon=True)
        self._stream_thread.start()
        self.logger.info("VR streaming started to %s", self.active_client)
        return True
            
    def stop_streaming(self):
        """Stop streaming."""
        with self.lock:
            if not self.streaming:
                return
            self.streaming = False
            
        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
            
        # Wait for thread
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None
            
        self.logger.info("VR streaming stopped")
            
    def is_streaming(self) -> bool:
        """Check if currently streaming."""
        with self.lock:
            return self.streaming and self.active_client is not None
            
    def get_active_client(self) -> Optional[VRClient]:
        """Get the current streaming target."""
        with self.lock:
            return self.active_client
            
    def _streaming_loop(self):
        """Main streaming loop - runs in background thread."""
        client = None
        with self.lock:
            client = self.active_client
            
        if not client:
            self.logger.error("Streaming loop started without client")
            return
            
        try:
            # Connect to client
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)
            self._socket.connect((client.ip, client.port))
            self.logger.info("Connected to VR client at %s:%d", client.ip, client.port)
            
            frame_interval = 1.0 / self._target_fps
            frame_count = 0
            start_time = time.time()
            
            while self.streaming:
                frame_start = time.time()
                
                try:
                    # Capture frame from compositor
                    frame = self._capture_frame()
                    
                    if frame is not None:
                        # Encode and send
                        self._send_frame(frame, frame_count)
                        frame_count += 1
                        
                        # Log FPS every 60 frames
                        if frame_count % 60 == 0:
                            elapsed = time.time() - start_time
                            fps = frame_count / elapsed
                            self.logger.info("VR streaming: %.1f FPS, sent %d frames", fps, frame_count)
                    
                    # Frame pacing
                    frame_time = time.time() - frame_start
                    sleep_time = frame_interval - frame_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        
                except Exception as e:
                    self.logger.error("Error in streaming loop: %s", e)
                    break
                    
        except Exception as e:
            self.logger.error("Failed to connect to VR client: %s", e)
        finally:
            if self._socket:
                try:
                    self._socket.close()
                except:
                    pass
                self._socket = None
            with self.lock:
                self.streaming = False
                
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture current frame from compositor and downscale to target resolution."""
        if not self._compositor:
            return None
            
        try:
            # Get frame from compositor using OpenGL
            if hasattr(self._compositor, 'grab_framebuffer'):
                # QOpenGLWidget method
                image = self._compositor.grab_framebuffer()
                # Convert QImage to numpy array
                width = image.width()
                height = image.height()
                ptr = image.constBits()
                ptr.setsize(height * width * 4)
                arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
                # Convert RGBA to RGB and flip vertically (OpenGL is upside down)
                frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
                frame = cv2.flip(frame, 0)
                
                # Downscale to target resolution if different
                if width != self._target_width or height != self._target_height:
                    frame = cv2.resize(frame, (self._target_width, self._target_height), 
                                      interpolation=cv2.INTER_LINEAR)
                    
                return frame
            elif hasattr(self._compositor, 'grabFramebuffer'):
                # QOpenGLWindow method
                image = self._compositor.grabFramebuffer()
                width = image.width()
                height = image.height()
                ptr = image.constBits()
                ptr.setsize(height * width * 4)
                arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
                frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
                frame = cv2.flip(frame, 0)
                
                # Downscale to target resolution if different
                if width != self._target_width or height != self._target_height:
                    frame = cv2.resize(frame, (self._target_width, self._target_height), 
                                      interpolation=cv2.INTER_LINEAR)
                
                return frame
                
        except Exception as e:
            self.logger.error("Failed to capture frame: %s", e)
            
        return None
        
    def _send_frame(self, frame: np.ndarray, frame_id: int):
        """Encode and send frame to client."""
        if not self._socket:
            return
            
        try:
            # Encode as JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality]
            success, encoded = cv2.imencode('.jpg', frame, encode_params)
            
            if not success:
                self.logger.error("Failed to encode frame")
                return
                
            frame_data = encoded.tobytes()
            frame_size = len(frame_data)
            
            # Send packet: magic(4) + frame_id(4) + frame_size(4) + frame_data
            magic = b'VRHP'
            header = struct.pack('!4sII', magic, frame_id, frame_size)
            
            self._socket.sendall(header)
            self._socket.sendall(frame_data)
            
        except Exception as e:
            self.logger.error("Failed to send frame: %s", e)
            raise
