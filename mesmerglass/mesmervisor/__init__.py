"""
MesmerVisor - VR Visual Streaming System

Streams live-rendered hypnotic visuals from MesmerGlass to VR headsets
using GPU-accelerated encoding (NVENC H.264 or CPU JPEG fallback).

Components:
- streaming_server.py: TCP/UDP server with auto-discovery
- frame_encoder.py: GPU-accelerated H.264 or CPU JPEG encoding
- gpu_utils.py: GPU detection and capability checking

Protocol: VRHP (VR Hypnotic Protocol)
- UDP Discovery: Port 5556
- TCP Streaming: Port 5555
"""

from .gpu_utils import (
    has_nvenc_support,
    get_gpu_info,
    get_gpu_info_json,
    select_encoder,
    log_encoder_info,
    EncoderType
)

from .frame_encoder import (
    FrameEncoder,
    NVENCEncoder,
    JPEGEncoder,
    create_encoder,
    encode_stereo_frames
)

from .streaming_server import (
    VRStreamingServer,
    DiscoveryService
)

__all__ = [
    'has_nvenc_support',
    'get_gpu_info',
    'get_gpu_info_json',
    'select_encoder',
    'log_encoder_info',
    'EncoderType',
    'FrameEncoder',
    'NVENCEncoder',
    'JPEGEncoder',
    'create_encoder',
    'encode_stereo_frames',
    'VRStreamingServer',
    'DiscoveryService',
]

__version__ = '1.0.0'
