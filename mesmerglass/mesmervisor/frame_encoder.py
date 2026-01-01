"""
Frame Encoding for VR Streaming

Supports both GPU-accelerated H.264 (NVENC) and CPU JPEG encoding.
Automatically selects best available encoder.
"""

import logging
import numpy as np
import os
import threading
from collections import deque
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

    def request_idr(self) -> None:
        """Request an IDR/keyframe on the next encode (best-effort)."""
        return


class NVENCEncoder(FrameEncoder):
    """H.264 encoder (NVENC or software via libx264).

    Historical name: NVENCEncoder. If codec_name != 'h264_nvenc', this acts as a software H.264 encoder.
    """
    
    def __init__(self, width: int, height: int, fps: int = 30, bitrate: int = 120_000_000, codec_name: Optional[str] = None):
        """
        Initialize NVENC encoder
        
        Args:
            width: Frame width
            height: Frame height
            fps: Target frames per second
            bitrate: Target bitrate in bits/second (default 50 Mbps)
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate

        # Thread-safe flag: streaming server may request an IDR from another thread.
        self._force_idr_next = threading.Event()

        # Diagnostic knobs for investigating intermittent mosaic/corruption:
        # - Reformatting to yuv420p forces a copy into AVFrame-owned planes.
        # - Keeping recent AVFrames alive can cover any internal encoder latency.
        # Default to ON for NVENC: this favors robustness/smoothness over minimal latency.
        refmt_env = (os.environ.get("MESMERGLASS_VRH2_REFORMAT_YUV420P") or "").strip().lower()
        if refmt_env == "":
            self._reformat_yuv420p = True
        else:
            self._reformat_yuv420p = refmt_env in {"1", "true", "on", "yes"}

        keep_n_env = (os.environ.get("MESMERGLASS_VRH2_KEEP_AVFRAMES") or "").strip()
        try:
            # Default to a small buffer for NVENC unless explicitly overridden.
            keep_n = int(keep_n_env) if keep_n_env else 4
        except Exception:
            keep_n = 4
        self._keep_avframes = deque(maxlen=max(0, keep_n)) if keep_n > 0 else None
        
        try:
            import av
            self._av = av

            if codec_name is None:
                codec_name = (os.environ.get("MESMERGLASS_VRH2_H264_CODEC") or "h264_nvenc").strip()
            self.codec_name = codec_name
            
            # Create in-memory output container
            self.container = av.open('pipe:', 'w', format='h264')
            
            # Create video stream. Default is NVENC, but allow libx264 for controlled comparisons.
            self.stream = self.container.add_stream(codec_name, rate=fps)
            self.stream.width = width
            self.stream.height = height
            self.stream.pix_fmt = 'yuv420p'

            # Only force a bitrate for NVENC. libx264 is typically used with CRF.
            if codec_name == "h264_nvenc":
                self.stream.bit_rate = bitrate
            
            # NVENC options tuned for visual quality + robustness.
            # Mesmer visuals are extremely high-frequency; strict CBR tends to macroblock heavily.
            # Default to VBR HQ with a constant-quality target while still capping peak rate.
            # Allow overriding GOP size (keyframe interval) for diagnostics / robustness.
            # Smaller GOP => more frequent IDR => artifacts don't persist as long.
            gop_env = (os.environ.get("MESMERGLASS_H264_GOP") or "").strip()
            if gop_env:
                try:
                    gop = max(1, min(int(gop_env), 300))
                except ValueError:
                    gop = min(fps, 30)
            else:
                gop = min(fps, 30)  # <=1s GOP; at 60fps this is a keyframe every 0.5s
            bufsize = max(int(bitrate * 2), bitrate)

            # Env overrides for rapid tuning (no UX changes required).
            # Examples:
            #   setx MESMERGLASS_NVENC_RC vbr_hq
            #   setx MESMERGLASS_NVENC_CQ 18
            #   setx MESMERGLASS_NVENC_PRESET p7
            rc_mode = (os.environ.get("MESMERGLASS_NVENC_RC") or "vbr_hq").strip()
            cq = (os.environ.get("MESMERGLASS_NVENC_CQ") or "16").strip()
            preset = (os.environ.get("MESMERGLASS_NVENC_PRESET") or "p7").strip()
            qp = (os.environ.get("MESMERGLASS_NVENC_QP") or "").strip()

            if codec_name == "h264_nvenc":
                opts = {
                    'preset': preset,
                    'delay': '0',              # No B-frames
                    'bf': '0',                 # Explicit: no B-frames
                    'g': str(gop),             # GOP size (keyframe interval)
                    'forced-idr': '1',         # Use IDR frames for keyframes (better error recovery)
                    'repeat_headers': '1',     # Repeat SPS/PPS on keyframes for decoder robustness
                    'gpu': '0',                # GPU index
                    # Android/MediaCodec robustness defaults (can be overridden via env):
                    # - baseline: avoids CABAC/B-frames/complex refs on picky decoders
                    # - refs=1: reduces reference chain fragility under corruption
                    # - rc-lookahead=0/zerolatency: avoid delayed reordering behavior
                    'profile': (os.environ.get("MESMERGLASS_H264_PROFILE") or "baseline").strip(),
                    'refs': (os.environ.get("MESMERGLASS_H264_REFS") or "1").strip(),
                    'rc-lookahead': (os.environ.get("MESMERGLASS_H264_LOOKAHEAD") or "0").strip(),
                    'zerolatency': (os.environ.get("MESMERGLASS_H264_ZEROLATENCY") or "1").strip(),
                }

                # Rate control mode.
                # Supported values are FFmpeg-build dependent; on this repo's Windows env we validated:
                #   cbr, vbr, vbr_hq, constqp.
                opts['rc'] = rc_mode
                if rc_mode in {"vbr", "vbr_hq"}:
                    opts['cq'] = cq
                    opts['maxrate'] = str(bitrate)
                    opts['bufsize'] = str(bufsize)
                elif rc_mode == "cbr":
                    opts['maxrate'] = str(bitrate)
                    opts['minrate'] = str(bitrate)
                    opts['bufsize'] = str(bufsize)
                elif rc_mode == "constqp":
                    # NOTE: constqp can produce very high bitrate on noisy content.
                    # Use with care on Wi‑Fi if you see disconnects.
                    # Prefer explicit QP override; fall back to using CQ as QP for backwards compatibility.
                    opts['qp'] = (qp or cq)
                else:
                    # Unknown mode; keep it but avoid adding incompatible knobs.
                    pass

                self.stream.options = opts
            else:
                # Software H.264 path for diagnostics / A-B comparisons.
                x264_preset = (os.environ.get("MESMERGLASS_X264_PRESET") or "veryfast").strip()
                x264_tune = (os.environ.get("MESMERGLASS_X264_TUNE") or "zerolatency").strip()
                x264_crf = (os.environ.get("MESMERGLASS_X264_CRF") or "18").strip()
                x264_profile = (os.environ.get("MESMERGLASS_X264_PROFILE") or "baseline").strip()
                x264_level = (os.environ.get("MESMERGLASS_X264_LEVEL") or "3.1").strip()

                # Ensure SPS/PPS are in-band and repeated so MediaCodec can configure reliably.
                # Also request Access Unit Delimiters (AUD) for more robust access-unit parsing.
                # x264-params is the most portable way to pass these through FFmpeg->x264.
                x264_params_extra = (os.environ.get("MESMERGLASS_X264_PARAMS") or "").strip()
                base_params = "repeat-headers=1:aud=1:scenecut=0"
                x264_params = base_params if not x264_params_extra else (base_params + ":" + x264_params_extra)
                self.stream.options = {
                    'preset': x264_preset,
                    'tune': x264_tune,
                    'crf': x264_crf,
                    'g': str(gop),
                    'keyint_min': str(gop),
                    'profile': x264_profile,
                    'level': x264_level,
                    'x264-params': x264_params,
                }
            
            logger.info(
                "H.264 encoder initialized: codec=%s %sx%s @ %s FPS, target %.1f Mbps (gop=%s rc=%s preset=%s cq=%s qp=%s)",
                codec_name,
                width,
                height,
                fps,
                bitrate / 1_000_000.0,
                gop,
                rc_mode,
                preset,
                cq,
                (qp or ""),
            )
            
        except ImportError:
            raise RuntimeError("PyAV not installed. Install with: pip install av")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize NVENC encoder: {e}")

    def is_nvenc(self) -> bool:
        return getattr(self, "codec_name", "h264_nvenc") == "h264_nvenc"
    
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

            # Optional: force colorspace conversion + copy before encode.
            # This can avoid subtle lifetime/synchronization hazards when the encoder path
            # internally pipelines work and would otherwise reference short-lived numpy memory.
            if self._reformat_yuv420p:
                try:
                    video_frame = video_frame.reformat(format='yuv420p')
                except Exception:
                    # Best-effort; proceed without reformatting.
                    pass

            # Optional: keep recent frames alive across encode calls.
            if self._keep_avframes is not None:
                self._keep_avframes.append(video_frame)

            # Best-effort keyframe request.
            if self._force_idr_next.is_set():
                self._force_idr_next.clear()
                try:
                    # PyAV supports setting pict_type; not all encoders honor it.
                    # Works well with libx264 and is often honored by NVENC too.
                    pt = getattr(getattr(self._av, 'video', None), 'frame', None)
                    picture_type = getattr(pt, 'PictureType', None) if pt is not None else None
                    if picture_type is not None and hasattr(picture_type, 'I'):
                        video_frame.pict_type = picture_type.I
                    else:
                        video_frame.pict_type = 'I'
                except Exception:
                    # If unsupported, just proceed without forcing.
                    pass
            
            # Encode frame
            packets = []
            for packet in self.stream.encode(video_frame):
                packets.append(bytes(packet))
            
            # Return concatenated packets
            return b''.join(packets)
            
        except Exception as e:
            logger.error(f"NVENC encoding error: {e}")
            return b''

    def request_idr(self) -> None:
        self._force_idr_next.set()
    
    def get_encoder_type(self) -> EncoderType:
        # Treat both NVENC and libx264 paths as "H.264" for the server.
        # Use is_nvenc() when you need to know whether this is hardware.
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
            # PyAV/FFmpeg can report EOF during flush/close; treat as benign shutdown noise.
            msg = str(e)
            if "End of file" in msg or "avcodec_send_frame" in msg:
                logger.info("NVENC encoder closed (EOF on flush)")
            else:
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
    bitrate: int = 120_000_000,
    codec_name: Optional[str] = None
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
        return NVENCEncoder(width, height, fps, bitrate, codec_name=codec_name)
    
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
