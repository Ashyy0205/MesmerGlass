"""
Frame Encoding for VR Streaming

Supports both GPU-accelerated H.264 (NVENC) and CPU JPEG encoding.
Automatically selects best available encoder.
"""

import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from .gpu_utils import EncoderType

logger = logging.getLogger(__name__)


class FrameEncoder(ABC):
    """Base class for frame encoders"""
    
    @abstractmethod
    def encode(self, frame: np.ndarray) -> bytes:
        """
        Encode a frame
        
        Args:
            frame: RGB frame as numpy array (height, width, 3) uint8
        
        Returns:
            Encoded frame data as bytes
        """
        pass
    
    @abstractmethod
    def get_encoder_type(self) -> EncoderType:
        """Get the encoder type"""
        pass
    
    @abstractmethod
    def close(self):
        """Release encoder resources"""
        pass


class NVENCEncoder(FrameEncoder):
    """NVIDIA NVENC hardware H.264 encoder"""
    
    def __init__(self, width: int, height: int, fps: int = 30, bitrate: int = 2000000):
        """
        Initialize NVENC encoder
        
        Args:
            width: Frame width
            height: Frame height
            fps: Target frames per second
            bitrate: Target bitrate in bits/second (default 2 Mbps)
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        
        try:
            import av
            self._av = av
            
            # Create in-memory output container
            self.container = av.open('pipe:', 'w', format='h264')
            
            # Create video stream with h264_nvenc codec
            self.stream = self.container.add_stream('h264_nvenc', rate=fps)
            self.stream.width = width
            self.stream.height = height
            self.stream.pix_fmt = 'yuv420p'
            self.stream.bit_rate = bitrate
            
            # NVENC options for low latency
            self.stream.options = {
                'preset': 'llhq',          # Low-latency high quality
                'zerolatency': '1',        # Zero latency mode
                'delay': '0',              # No B-frames
                'rc': 'cbr',               # Constant bitrate
                'gpu': '0',                # GPU index
            }
            
            logger.info(f"NVENC encoder initialized: {width}x{height} @ {fps} FPS, {bitrate/1000000:.1f} Mbps")
            
        except ImportError:
            raise RuntimeError("PyAV not installed. Install with: pip install av")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize NVENC encoder: {e}")
    
    def encode(self, frame: np.ndarray) -> bytes:
        """
        Encode frame using NVENC
        
        Args:
            frame: RGB frame (height, width, 3) uint8
        
        Returns:
            H.264 encoded data
        """
        try:
            # Convert numpy array to VideoFrame
            video_frame = self._av.VideoFrame.from_ndarray(frame, format='rgb24')
            
            # Encode frame
            packets = []
            for packet in self.stream.encode(video_frame):
                packets.append(bytes(packet))
            
            # Return concatenated packets
            return b''.join(packets)
            
        except Exception as e:
            logger.error(f"NVENC encoding error: {e}")
            return b''
    
    def get_encoder_type(self) -> EncoderType:
        return EncoderType.NVENC
    
    def close(self):
        """Close encoder and flush remaining packets"""
        try:
            # Flush encoder
            for packet in self.stream.encode():
                pass  # Discard flush packets
            
            self.container.close()
            logger.info("NVENC encoder closed")
        except Exception as e:
            logger.warning(f"Error closing NVENC encoder: {e}")


class JPEGEncoder(FrameEncoder):
    """CPU JPEG encoder (fallback)"""
    
    def __init__(self, quality: int = 85):
        """
        Initialize JPEG encoder
        
        Args:
            quality: JPEG quality (1-100, default 85)
        """
        self.quality = quality
        
        try:
            import cv2
            self._cv2 = cv2
            
            self.encode_params = [
                int(cv2.IMWRITE_JPEG_QUALITY), quality,
                int(cv2.IMWRITE_JPEG_OPTIMIZE), 1,
            ]
            
            logger.info(f"JPEG encoder initialized: quality={quality}")
            
        except ImportError:
            raise RuntimeError("OpenCV not installed. Install with: pip install opencv-python")
    
    def encode(self, frame: np.ndarray) -> bytes:
        """
        Encode frame as JPEG
        
        Args:
            frame: RGB frame (height, width, 3) uint8
        
        Returns:
            JPEG encoded data
        """
        try:
            # Convert RGB to BGR for OpenCV
            bgr_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2BGR)
            
            # Encode as JPEG
            success, encoded = self._cv2.imencode('.jpg', bgr_frame, self.encode_params)
            
            if not success:
                logger.error("JPEG encoding failed")
                return b''
            
            return encoded.tobytes()
            
        except Exception as e:
            logger.error(f"JPEG encoding error: {e}")
            return b''
    
    def get_encoder_type(self) -> EncoderType:
        return EncoderType.JPEG
    
    def close(self):
        """No cleanup needed for JPEG encoder"""
        logger.info("JPEG encoder closed")


def create_encoder(
    encoder_type: EncoderType,
    width: int,
    height: int,
    fps: int = 30,
    quality: int = 85,
    bitrate: int = 2000000
) -> FrameEncoder:
    """
    Factory function to create appropriate encoder
    
    Args:
        encoder_type: Type of encoder to create
        width: Frame width
        height: Frame height
        fps: Target FPS (for H.264)
        quality: JPEG quality (for JPEG encoder)
        bitrate: Bitrate for H.264 (bits/second)
    
    Returns:
        Configured encoder instance
    
    Raises:
        RuntimeError: If requested encoder cannot be created
    """
    if encoder_type == EncoderType.NVENC:
        return NVENCEncoder(width, height, fps, bitrate)
    
    elif encoder_type == EncoderType.JPEG:
        return JPEGEncoder(quality)
    
    else:
        raise ValueError(f"Unknown encoder type: {encoder_type}")


def encode_stereo_frames(
    encoder: FrameEncoder,
    frame: np.ndarray,
    stereo_offset: int = 0
) -> Tuple[bytes, bytes]:
    """
    Encode stereo frames (left and right eye)
    
    Args:
        encoder: Frame encoder instance
        frame: Source frame (height, width, 3) uint8 RGB
        stereo_offset: Horizontal offset for stereo effect (pixels, 0 = mono)
    
    Returns:
        Tuple of (left_encoded, right_encoded) bytes
    """
    if stereo_offset == 0:
        # Mono mode - same frame for both eyes
        encoded = encoder.encode(frame)
        return (encoded, encoded)
    
    else:
        # Stereo mode - create offset views
        height, width = frame.shape[:2]
        
        # Left eye: shift right
        left_frame = np.roll(frame, stereo_offset, axis=1)
        
        # Right eye: shift left
        right_frame = np.roll(frame, -stereo_offset, axis=1)
        
        # Encode both
        left_encoded = encoder.encode(left_frame)
        right_encoded = encoder.encode(right_frame)
        
        return (left_encoded, right_encoded)


if __name__ == "__main__":
    # Test encoder creation
    logging.basicConfig(level=logging.INFO)
    
    from .gpu_utils import select_encoder, EncoderType
    
    # Auto-select encoder
    encoder_type = select_encoder(EncoderType.AUTO)
    
    # Create test frame
    test_frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    # Create encoder
    if encoder_type == EncoderType.NVENC:
        encoder = create_encoder(EncoderType.NVENC, 1920, 1080, fps=30)
    else:
        encoder = create_encoder(EncoderType.JPEG, 1920, 1080, quality=85)
    
    # Test encode
    encoded = encoder.encode(test_frame)
    print(f"Encoded {len(test_frame.tobytes())} bytes to {len(encoded)} bytes")
    
    encoder.close()
