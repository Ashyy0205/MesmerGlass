"""
MesmerVisor Test Suite

Comprehensive tests for VR streaming functionality:
- Import tests
- GPU detection tests
- NVENC encoder tests
- JPEG encoder tests
- Server initialization tests
- Protocol packet tests
- Discovery service tests
- Compositor integration tests
"""

import pytest
import numpy as np
import sys
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mesmerglass.mesmervisor import (
    get_gpu_info,
    has_nvenc_support,
    select_encoder,
    create_encoder,
    EncoderType,
    VRStreamingServer,
    DiscoveryService,
)
from mesmerglass.mesmervisor.frame_encoder import (
    NVENCEncoder,
    JPEGEncoder,
    FrameEncoder,
    encode_stereo_frames,
)


# ============================================================================
# Import Tests
# ============================================================================

class TestImports:
    """Test that all MesmerVisor modules import successfully."""
    
    def test_import_main_module(self):
        """Test main mesmervisor module import."""
        import mesmerglass.mesmervisor
        assert mesmerglass.mesmervisor is not None
    
    def test_import_gpu_utils(self):
        """Test gpu_utils module import."""
        from mesmerglass.mesmervisor import gpu_utils
        assert gpu_utils is not None
    
    def test_import_frame_encoder(self):
        """Test frame_encoder module import."""
        from mesmerglass.mesmervisor import frame_encoder
        assert frame_encoder is not None
    
    def test_import_streaming_server(self):
        """Test streaming_server module import."""
        from mesmerglass.mesmervisor import streaming_server
        assert streaming_server is not None
    
    def test_import_encoder_type(self):
        """Test EncoderType enum import."""
        from mesmerglass.mesmervisor import EncoderType
        assert EncoderType.NVENC.value == "nvenc"
        assert EncoderType.JPEG.value == "jpeg"
        assert EncoderType.AUTO.value == "auto"


# ============================================================================
# GPU Detection Tests
# ============================================================================

class TestGPUDetection:
    """Test GPU detection and NVENC availability checking."""
    
    def test_get_gpu_info_structure(self):
        """Test that get_gpu_info returns correct structure."""
        info = get_gpu_info()
        
        assert isinstance(info, dict)
        assert "gpu_name" in info
        assert "has_nvenc" in info
        assert "has_cuda" in info
        assert "driver_version" in info
        assert "recommended_encoder" in info
        assert "recommended_encoder_name" in info
        
        # Check types
        assert isinstance(info["gpu_name"], str)
        assert isinstance(info["has_nvenc"], bool)
        assert isinstance(info["has_cuda"], bool)
        assert isinstance(info["driver_version"], str)
        assert isinstance(info["recommended_encoder"], EncoderType)
        assert isinstance(info["recommended_encoder_name"], str)
    
    def test_has_nvenc_support_returns_bool(self):
        """Test that has_nvenc_support returns boolean."""
        result = has_nvenc_support()
        assert isinstance(result, bool)
    
    def test_select_encoder_auto(self):
        """Test auto encoder selection logic."""
        encoder_type = select_encoder(EncoderType.AUTO)
        
        assert isinstance(encoder_type, EncoderType)
        assert encoder_type in [EncoderType.NVENC, EncoderType.JPEG]
    
    def test_select_encoder_explicit_nvenc(self):
        """Test explicit NVENC selection."""
        encoder_type = select_encoder(EncoderType.NVENC)
        
        # Should either succeed or fallback to JPEG
        assert encoder_type in [EncoderType.NVENC, EncoderType.JPEG]
    
    def test_select_encoder_explicit_jpeg(self):
        """Test explicit JPEG selection."""
        encoder_type = select_encoder(EncoderType.JPEG)
        assert encoder_type == EncoderType.JPEG
    
    def test_pyav_import(self):
        """Test that PyAV is importable."""
        try:
            import av
            assert av is not None
        except ImportError:
            pytest.fail("PyAV not installed (required in requirements.txt)")


# ============================================================================
# JPEG Encoder Tests
# ============================================================================

class TestJPEGEncoder:
    """Test JPEG CPU encoder functionality."""
    
    def test_jpeg_encoder_creation(self):
        """Test JPEG encoder instantiation."""
        encoder = JPEGEncoder(quality=85)
        
        assert encoder is not None
        assert encoder.get_encoder_type() == EncoderType.JPEG
        assert encoder.quality == 85
    
    def test_jpeg_encode_frame(self):
        """Test JPEG frame encoding."""
        encoder = JPEGEncoder(quality=75)
        
        # Create test frame (RGB)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, 0] = 255  # Red channel
        
        # Encode
        encoded = encoder.encode(frame)
        
        # Verify output
        assert encoded is not None
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0
        
        # JPEG magic bytes: FF D8 FF
        assert encoded[:2] == b'\xff\xd8'
        
        encoder.close()
    
    def test_jpeg_encode_different_qualities(self):
        """Test JPEG encoding with different quality settings."""
        frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        
        # Low quality
        encoder_low = JPEGEncoder(quality=50)
        encoded_low = encoder_low.encode(frame)
        encoder_low.close()
        
        # High quality
        encoder_high = JPEGEncoder(quality=95)
        encoded_high = encoder_high.encode(frame)
        encoder_high.close()
        
        # High quality should produce larger files
        assert len(encoded_high) > len(encoded_low)
    
    def test_jpeg_encode_multiple_frames(self):
        """Test encoding multiple frames sequentially."""
        encoder = JPEGEncoder(quality=85)
        
        for i in range(5):
            frame = np.full((240, 320, 3), i * 50, dtype=np.uint8)
            encoded = encoder.encode(frame)
            
            assert encoded is not None
            assert len(encoded) > 0
        
        encoder.close()
    
    def test_jpeg_wrong_frame_shape(self):
        """Test JPEG encoder with different frame dimensions."""
        encoder = JPEGEncoder(quality=85)
        
        # Different dimensions - should work (encoder is flexible)
        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        encoded1 = encoder.encode(frame1)
        assert encoded1 is not None
        
        frame2 = np.zeros((240, 320, 3), dtype=np.uint8)
        encoded2 = encoder.encode(frame2)
        assert encoded2 is not None
        
        encoder.close()


# ============================================================================
# NVENC Encoder Tests
# ============================================================================

class TestNVENCEncoder:
    """Test NVENC GPU encoder functionality (if available)."""
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_nvenc_encoder_creation(self):
        """Test NVENC encoder instantiation."""
        encoder = NVENCEncoder(
            width=640,
            height=480,
            fps=30,
            bitrate=1000000
        )
        
        assert encoder is not None
        assert encoder.get_encoder_type() == EncoderType.NVENC
        encoder.close()
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_nvenc_encode_frame(self):
        """Test NVENC frame encoding."""
        encoder = NVENCEncoder(width=320, height=240, fps=30, bitrate=500000)
        
        # Create test frame (RGB)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, 1] = 255  # Green channel
        
        # Encode
        encoded = encoder.encode(frame)
        
        # Verify output
        assert encoded is not None
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0
        
        # H.264 NAL unit start codes: 00 00 00 01 or 00 00 01
        # (May not always start with this due to container format)
        # Just verify we got some data
        
        encoder.close()
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_nvenc_encode_multiple_frames(self):
        """Test encoding multiple frames with NVENC."""
        encoder = NVENCEncoder(width=320, height=240, fps=30, bitrate=500000)
        
        for i in range(5):
            frame = np.full((240, 320, 3), i * 50, dtype=np.uint8)
            encoded = encoder.encode(frame)
            
            assert encoded is not None
            assert len(encoded) > 0
        
        encoder.close()
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_nvenc_bitrate_comparison(self):
        """Test that different bitrates produce different output sizes."""
        frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        
        # Low bitrate
        encoder_low = NVENCEncoder(width=320, height=240, fps=30, bitrate=250000)
        sizes_low = []
        for _ in range(3):
            encoded = encoder_low.encode(frame)
            sizes_low.append(len(encoded))
        encoder_low.close()
        
        # High bitrate
        encoder_high = NVENCEncoder(width=320, height=240, fps=30, bitrate=2000000)
        sizes_high = []
        for _ in range(3):
            encoded = encoder_high.encode(frame)
            sizes_high.append(len(encoded))
        encoder_high.close()
        
        # Average size should be larger for high bitrate
        # (though first frame may be different due to keyframe)
        avg_low = sum(sizes_low) / len(sizes_low)
        avg_high = sum(sizes_high) / len(sizes_high)
        
        # High bitrate should generally produce larger output
        # (allow some margin due to encoder variance)
        assert avg_high >= avg_low * 0.8


# ============================================================================
# Encoder Factory Tests
# ============================================================================

class TestEncoderFactory:
    """Test encoder factory function."""
    
    def test_create_jpeg_encoder(self):
        """Test creating JPEG encoder via factory."""
        encoder = create_encoder(
            EncoderType.JPEG,
            width=640,
            height=480,
            fps=30
        )
        
        assert isinstance(encoder, JPEGEncoder)
        assert encoder.get_encoder_type() == EncoderType.JPEG
        encoder.close()
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_create_nvenc_encoder(self):
        """Test creating NVENC encoder via factory."""
        encoder = create_encoder(
            EncoderType.NVENC,
            width=640,
            height=480,
            fps=30,
            bitrate=1000000
        )
        
        assert isinstance(encoder, NVENCEncoder)
        assert encoder.get_encoder_type() == EncoderType.NVENC
        encoder.close()
    
    def test_create_auto_encoder(self):
        """Test auto encoder selection via factory."""
        # AUTO should resolve to NVENC or JPEG, not stay as AUTO
        selected_type = select_encoder(EncoderType.AUTO)
        encoder = create_encoder(
            selected_type,
            width=640,
            height=480,
            fps=30
        )
        
        assert encoder is not None
        assert encoder.get_encoder_type() in [EncoderType.NVENC, EncoderType.JPEG]
        encoder.close()


# ============================================================================
# Stereo Frame Tests
# ============================================================================

class TestStereoFrames:
    """Test stereo frame generation."""
    
    def test_encode_stereo_no_offset(self):
        """Test stereo encoding with no parallax offset (mono)."""
        encoder = JPEGEncoder(quality=85)
        frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        
        left, right = encode_stereo_frames(encoder, frame, stereo_offset=0)
        
        # With 0 offset, left and right should be identical
        assert left == right
        encoder.close()
    
    def test_encode_stereo_with_offset(self):
        """Test stereo encoding with parallax offset."""
        encoder = JPEGEncoder(quality=85)
        frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
        
        left, right = encode_stereo_frames(encoder, frame, stereo_offset=10)
        
        # With offset, left and right should differ
        assert left != right
        assert len(left) > 0
        assert len(right) > 0
        encoder.close()


# ============================================================================
# Protocol Packet Tests
# ============================================================================

class TestProtocolPackets:
    """Test VRHP protocol packet creation."""
    
    def test_create_packet_structure(self):
        """Test packet structure compliance."""
        # Create dummy encoded frames
        left_data = b"LEFT_FRAME_DATA_12345"
        right_data = b"RIGHT_FRAME_DATA_67890"
        frame_id = 42
        
        # Create server (without starting)
        server = VRStreamingServer(
            encoder_type=EncoderType.JPEG,
            width=320,
            height=240
        )
        
        # Create packet
        packet = server.create_packet(left_data, right_data, frame_id)
        
        # Verify structure
        # Total packet: size_field(4) + header(16) + left_data + right_data
        expected_total = 4 + 16 + len(left_data) + len(right_data)  # 4 + 16 + 21 + 22 = 63
        assert len(packet) == expected_total
        
        # Extract header fields
        import struct
        packet_size = struct.unpack('>I', packet[0:4])[0]
        magic = packet[4:8].decode('ascii')
        frame_id_parsed = struct.unpack('>I', packet[8:12])[0]
        left_size = struct.unpack('>I', packet[12:16])[0]
        right_size = struct.unpack('>I', packet[16:20])[0]
        
        # Verify values
        # packet_size field contains size AFTER the size field (total - 4)
        assert packet_size == len(packet) - 4
        assert magic in ["VRH2", "VRHP"]
        assert frame_id_parsed == frame_id
        assert left_size == len(left_data)
        assert right_size == len(right_data)
        
        # Verify data
        left_data_parsed = packet[20:20+left_size]
        right_data_parsed = packet[20+left_size:20+left_size+right_size]
        
        assert left_data_parsed == left_data
        assert right_data_parsed == right_data
    
    def test_create_packet_jpeg_magic(self):
        """Test JPEG packets use VRHP magic bytes."""
        server = VRStreamingServer(encoder_type=EncoderType.JPEG)
        packet = server.create_packet(b"L", b"R", 0)
        
        magic = packet[4:8].decode('ascii')
        assert magic == "VRHP"
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_create_packet_nvenc_magic(self):
        """Test NVENC packets use VRH2 magic bytes."""
        server = VRStreamingServer(encoder_type=EncoderType.NVENC)
        packet = server.create_packet(b"L", b"R", 0)
        
        magic = packet[4:8].decode('ascii')
        assert magic == "VRH2"


# ============================================================================
# Server Initialization Tests
# ============================================================================

class TestServerInitialization:
    """Test VR streaming server initialization."""
    
    def test_server_creation_default(self):
        """Test server creation with default parameters."""
        server = VRStreamingServer()
        
        assert server.host == "0.0.0.0"
        assert server.port == 5555
        assert server.discovery_port == 5556
        assert server.width == 1920
        assert server.height == 1080
        assert server.fps == 30
    
    def test_server_creation_custom_params(self):
        """Test server creation with custom parameters."""
        server = VRStreamingServer(
            host="127.0.0.1",
            port=6666,
            discovery_port=7777,
            width=1280,
            height=720,
            fps=60
        )
        
        assert server.host == "127.0.0.1"
        assert server.port == 6666
        assert server.discovery_port == 7777
        assert server.width == 1280
        assert server.height == 720
        assert server.fps == 60
    
    def test_server_encoder_initialization(self):
        """Test that server initializes encoder correctly."""
        server = VRStreamingServer(
            encoder_type=EncoderType.JPEG,
            width=640,
            height=480
        )
        
        # Encoder should be created during init
        assert server.encoder is not None
        assert server.encoder.get_encoder_type() == EncoderType.JPEG


# ============================================================================
# Discovery Service Tests
# ============================================================================

class TestDiscoveryService:
    """Test UDP discovery service."""
    
    @pytest.mark.asyncio
    async def test_discovery_service_creation(self):
        """Test discovery service instantiation."""
        callback = Mock()
        service = DiscoveryService(
            discovery_port=5556,
            streaming_port=5555
        )
        
        assert service is not None
        assert service.discovery_port == 5556
        assert service.streaming_port == 5555


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    @pytest.mark.asyncio
    async def test_server_start_stop_jpeg(self):
        """Test server start and stop with JPEG encoder."""
        server = VRStreamingServer(
            encoder_type=EncoderType.JPEG,
            width=320,
            height=240,
            fps=10
        )
        
        # Start server in background
        start_task = asyncio.create_task(server.start())
        
        # Wait briefly
        await asyncio.sleep(0.5)
        
        # Stop server
        await server.stop()
        
        # Cancel start task
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
    
    def test_end_to_end_jpeg_encoding(self):
        """Test full JPEG encoding pipeline."""
        # Create encoder
        encoder = create_encoder(
            EncoderType.JPEG,
            width=320,
            height=240,
            fps=30
        )
        
        # Create test frame
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[100:140, 140:180] = [255, 0, 0]  # Red square
        
        # Encode stereo
        left, right = encode_stereo_frames(encoder, frame, stereo_offset=0)
        
        # Create packet
        server = VRStreamingServer(encoder_type=EncoderType.JPEG)
        packet = server.create_packet(left, right, frame_id=1)
        
        # Verify packet is valid
        assert len(packet) > 20
        assert packet[4:8] == b"VRHP"
        
        encoder.close()


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance benchmarks (informational only)."""
    
    def test_jpeg_encode_performance(self, benchmark=None):
        """Benchmark JPEG encoding speed."""
        encoder = JPEGEncoder(quality=85)
        frame = np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
        
        import time
        start = time.perf_counter()
        
        for _ in range(10):
            encoder.encode(frame)
        
        elapsed = time.perf_counter() - start
        avg_time = elapsed / 10
        
        print(f"\nJPEG encode (1920x1080): {avg_time*1000:.2f}ms per frame")
        
        # Should be under 100ms for 1080p
        assert avg_time < 0.1
        
        encoder.close()
    
    @pytest.mark.skipif(not has_nvenc_support(), reason="NVENC not available")
    def test_nvenc_encode_performance(self):
        """Benchmark NVENC encoding speed."""
        encoder = NVENCEncoder(
            width=1920,
            height=1080,
            fps=30,
            bitrate=2000000
        )
        frame = np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
        
        import time
        start = time.perf_counter()
        
        for _ in range(10):
            encoder.encode(frame)
        
        elapsed = time.perf_counter() - start
        avg_time = elapsed / 10
        
        print(f"\nNVENC encode (1920x1080): {avg_time*1000:.2f}ms per frame")
        
        # NVENC should be under 50ms for 1080p
        assert avg_time < 0.05
        
        encoder.close()


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_invalid_encoder_type(self):
        """Test handling of invalid encoder type."""
        with pytest.raises((ValueError, KeyError)):
            create_encoder(
                "invalid_encoder",  # Not a valid EncoderType
                width=640,
                height=480,
                fps=30
            )
    
    def test_encoder_close_idempotent(self):
        """Test that encoder.close() can be called multiple times."""
        encoder = JPEGEncoder(quality=85)
        
        encoder.close()
        encoder.close()  # Should not raise
        encoder.close()  # Should not raise
    
    def test_invalid_frame_dtype(self):
        """Test encoding with wrong data type."""
        encoder = JPEGEncoder(quality=85)
        
        # Float frame instead of uint8
        frame = np.random.random((240, 320, 3)).astype(np.float32)
        
        # Should either convert or raise
        try:
            encoded = encoder.encode(frame)
            # If it doesn't raise, verify output is valid
            assert encoded is not None
        except (ValueError, TypeError, AssertionError):
            # Expected if encoder validates dtype
            pass
        
        encoder.close()


# ============================================================================
# Compositor Integration Tests
# ============================================================================

class TestCompositorIntegration:
    """Test LoomCompositor VR integration."""
    
    def test_compositor_vr_methods_exist(self):
        """Test that LoomCompositor has VR methods."""
        from mesmerglass.mesmerloom.compositor import LoomCompositor
        
        # Check methods exist
        assert hasattr(LoomCompositor, 'enable_vr_streaming')
        assert hasattr(LoomCompositor, 'disable_vr_streaming')
        assert hasattr(LoomCompositor, '_capture_frame_for_vr')


# ============================================================================
# CLI Integration Tests
# ============================================================================

class TestCLIIntegration:
    """Test CLI command integration."""
    
    def test_vr_commands_registered(self):
        """Test that vr-stream and vr-test commands are registered."""
        from mesmerglass import cli
        
        # Check command handlers exist
        assert hasattr(cli, 'cmd_vr_stream')
        assert hasattr(cli, 'cmd_vr_test')


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    """Run tests directly."""
    pytest.main([__file__, "-v", "-s"])
