"""
GPU Detection and Capability Checking

Determines available GPU encoders (NVENC, QuickSync, etc.)
and selects optimal encoding strategy.
"""

import os
import logging
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EncoderType(Enum):
    """Available encoder types"""
    NVENC = "nvenc"      # NVIDIA hardware encoder
    JPEG = "jpeg"        # CPU JPEG fallback
    AUTO = "auto"        # Auto-detect best available


def has_nvenc_support() -> bool:
    """
    Check if NVENC hardware encoding is available
    
    Returns:
        True if NVENC is available, False otherwise
    """
    try:
        import av
        
        # Try to find h264_nvenc codec
        codec = av.codec.Codec('h264_nvenc', 'w')
        
        # NVENC available
        logger.info("NVENC (NVIDIA hardware encoder) detected and available")
        return True
        
    except (ImportError, av.AVError) as e:
        logger.info(f"NVENC not available: {e}")
        return False
    except Exception as e:
        logger.warning(f"Error checking NVENC support: {e}")
        return False


def get_gpu_info() -> Dict[str, Any]:
    """
    Get detailed GPU information
    
    Returns:
        Dictionary with GPU details:
        - has_nvenc: bool
        - has_cuda: bool
        - gpu_name: str
        - driver_version: str
        - recommended_encoder: EncoderType
    """
    info = {
        'has_nvenc': False,
        'has_cuda': False,
        'gpu_name': 'Unknown',
        'driver_version': 'Unknown',
        'recommended_encoder': EncoderType.JPEG
    }
    
    # Check for NVENC
    info['has_nvenc'] = has_nvenc_support()
    
    # Try to get CUDA/GPU info
    try:
        import pycuda.driver as cuda
        import pycuda.autoinit
        
        info['has_cuda'] = True
        device = cuda.Device(0)
        info['gpu_name'] = device.name()
        
        # Get driver version
        driver_version = cuda.get_driver_version()
        info['driver_version'] = f"{driver_version // 1000}.{(driver_version % 1000) // 10}"
        
    except ImportError:
        logger.debug("PyCUDA not available - CUDA info unavailable")
    except Exception as e:
        logger.debug(f"Error getting CUDA info: {e}")
    
    # Determine recommended encoder
    if info['has_nvenc']:
        recommended_encoder = EncoderType.NVENC
        logger.info(f"Recommended encoder: NVENC (GPU: {info['gpu_name']})")
    else:
        recommended_encoder = EncoderType.JPEG
        logger.info("Recommended encoder: CPU JPEG (no hardware encoder detected)")
    
    # Keep EncoderType enum for internal use
    info['recommended_encoder'] = recommended_encoder
    # Add string version for JSON serialization
    info['recommended_encoder_name'] = recommended_encoder.value
    
    return info


def get_gpu_info_json() -> Dict[str, Any]:
    """
    Get GPU info as a JSON-serializable dictionary
    
    Returns:
        Dictionary with GPU details (all values are JSON-serializable)
    """
    info = get_gpu_info()
    # Convert EncoderType enum to string for JSON serialization
    if isinstance(info['recommended_encoder'], EncoderType):
        info['recommended_encoder'] = info['recommended_encoder'].value
    return info


def select_encoder(requested: EncoderType = EncoderType.AUTO) -> EncoderType:
    """
    Select optimal encoder based on hardware and user preference
    
    Args:
        requested: User-requested encoder type (AUTO, NVENC, or JPEG)
    
    Returns:
        Selected encoder type
    
    Raises:
        RuntimeError: If requested encoder is not available
    """
    if requested == EncoderType.AUTO:
        # Auto-detect best encoder
        gpu_info = get_gpu_info()
        selected = gpu_info['recommended_encoder']
        logger.info(f"Auto-selected encoder: {selected.value}")
        return selected
    
    elif requested == EncoderType.NVENC:
        # User explicitly requested NVENC
        if has_nvenc_support():
            logger.info("Using NVENC (user requested)")
            return EncoderType.NVENC
        else:
            raise RuntimeError(
                "NVENC requested but not available. "
                "Ensure you have an NVIDIA GPU with driver 418+ installed, "
                "and PyAV is installed: pip install av"
            )
    
    elif requested == EncoderType.JPEG:
        # User explicitly requested JPEG
        logger.info("Using CPU JPEG (user requested)")
        return EncoderType.JPEG
    
    else:
        raise ValueError(f"Unknown encoder type: {requested}")


def log_encoder_info():
    """Log detailed encoder information for diagnostics"""
    logger.info("=" * 60)
    logger.info("MesmerVisor GPU Encoder Detection")
    logger.info("=" * 60)
    
    gpu_info = get_gpu_info()
    
    logger.info(f"GPU Name: {gpu_info['gpu_name']}")
    logger.info(f"Driver Version: {gpu_info['driver_version']}")
    logger.info(f"CUDA Available: {gpu_info['has_cuda']}")
    logger.info(f"NVENC Available: {gpu_info['has_nvenc']}")
    
    # Handle both enum and string values
    encoder = gpu_info['recommended_encoder']
    encoder_name = encoder.value.upper() if isinstance(encoder, EncoderType) else encoder.upper()
    logger.info(f"Recommended Encoder: {encoder_name}")
    
    # Check PyAV availability
    try:
        import av
        logger.info(f"PyAV Version: {av.__version__}")
        
        # List available encoders
        encoders = []
        for name in ['h264_nvenc', 'libx264', 'mjpeg']:
            try:
                codec = av.codec.Codec(name, 'w')
                encoders.append(name)
            except:
                pass
        
        logger.info(f"Available Codecs: {', '.join(encoders)}")
        
    except ImportError:
        logger.warning("PyAV not installed - NVENC unavailable")
        logger.warning("Install with: pip install av")
    
    logger.info("=" * 60)


if __name__ == "__main__":
    # Test GPU detection
    logging.basicConfig(level=logging.INFO)
    log_encoder_info()
