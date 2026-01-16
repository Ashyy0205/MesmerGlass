# MesmerVisor Technical Documentation

**VR Visual Streaming System for MesmerGlass**

Version: 0.7.0  
Date: November 2025  
Status: Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Encoder Comparison](#encoder-comparison)
4. [Protocol Specification](#protocol-specification)
5. [Frame Capture Pipeline](#frame-capture-pipeline)
6. [GPU Requirements](#gpu-requirements)
7. [Installation](#installation)
8. [Usage](#usage)
9. [Performance Tuning](#performance-tuning)
10. [Troubleshooting](#troubleshooting)
11. [Development Guide](#development-guide)
12. [API Reference](#api-reference)

---

## Overview

MesmerVisor is a VR streaming subsystem that captures live-rendered hypnotic visuals from MesmerGlass and streams them to VR headsets using GPU-accelerated encoding.

### Key Features

- **GPU-Accelerated Encoding**: NVENC H.264 hardware encoding for zero-latency streaming
- **CPU Fallback**: JPEG encoding for systems without NVIDIA GPUs
- **Auto-Discovery**: UDP broadcast for automatic headset detection
- **Low Latency**: 10-20ms end-to-end latency with NVENC
- **High Quality**: 1920x1080 @ 30-60 FPS with configurable bitrate
- **Protocol Compatibility**: VRHP (JPEG), VRH2 (legacy H.264), VRH3 (H.264 + fps_milli)

### System Requirements

**Minimum:**
- Windows 10/11
- Any OpenGL-capable GPU
- 4GB RAM
- WiFi network

**Recommended (for NVENC):**
- NVIDIA GPU (GTX 900+ series or RTX)
- NVIDIA Driver 418+
- 8GB RAM
- 5GHz WiFi network

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MesmerVisor Architecture                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MesmerGlass Application (Qt + OpenGL)               │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  LoomCompositor (QOpenGLWidget) OR             │  │  │
│  │  │  LoomWindowCompositor (QOpenGLWindow)          │  │  │
│  │  │  - Spiral shader rendering                     │  │  │
│  │  │  - Image/video overlay                         │  │  │
│  │  │  - Text rendering                              │  │  │
│  │  │  - VR frame capture hook (optional)           │  │  │
│  │  └────────────────┬───────────────────────────────┘  │  │
│  │                   │ glReadPixels() - RGB(A)          │  │
│  └───────────────────┼───────────────────────────────────┘  │
│                      │                                       │
│  ┌───────────────────▼───────────────────────────────────┐  │
│  │  FrameEncoder (CPU Thread)                           │  │
│  │  ┌──────────────┐         ┌──────────────┐          │  │
│  │  │ NVENCEncoder │   OR    │ JPEGEncoder  │          │  │
│  │  │ (GPU H.264)  │         │ (CPU JPEG)   │          │  │
│  │  └──────┬───────┘         └──────┬───────┘          │  │
│  │         │ 10-20ms                │ 30-50ms            │  │
│  └─────────┼────────────────────────┼────────────────────┘  │
│            │                        │                       │
│  ┌─────────▼────────────────────────▼────────────────────┐  │
│  │  VRStreamingServer (TCP + UDP)                       │  │
│  │  ┌────────────────────┐  ┌────────────────────────┐  │  │
│  │  │ DiscoveryService   │  │ StreamingService       │  │  │
│  │  │ UDP Port 5556      │  │ TCP Port 5555          │  │  │
│  │  │ Broadcast/Listen   │  │ Packet transmission    │  │  │
│  │  └────────────────────┘  └────────────────────────┘  │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │ Network (WiFi)                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│  Android VR Client (Oculus Quest / Go)                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MainActivity (GLSurfaceView.Renderer)               │  │
│  │  ┌────────────────────┐  ┌────────────────────────┐  │  │
│  │  │ DiscoveryService   │  │ NetworkReceiver        │  │  │
│  │  │ UDP Broadcast      │  │ TCP Frame reception    │  │  │
│  │  └────────┬───────────┘  └──────┬─────────────────┘  │  │
│  │           │                     │                     │  │
│  │  ┌────────▼─────────────────────▼─────────────────┐  │  │
│  │  │ Frame Decoder                                   │  │  │
│  │  │ - MediaCodec (H.264 hardware)                  │  │  │
│  │  │ - BitmapFactory (JPEG software)                │  │  │
│  │  └────────┬────────────────────────────────────────┘  │  │
│  │           │                                           │  │
│  │  ┌────────▼────────────────────────────────────────┐  │  │
│  │  │ OpenGL ES Stereo Renderer                       │  │  │
│  │  │ - Left eye viewport (0, 0, w/2, h)             │  │  │
│  │  │ - Right eye viewport (w/2, 0, w/2, h)          │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Render Phase**: LoomCompositor renders spiral + media to OpenGL framebuffer
2. **Capture Phase**: `glReadPixels()` captures RGBA pixels (only when VR active)
3. **Encode Phase**: FrameEncoder compresses to H.264 or JPEG
4. **Packet Phase**: VRStreamingServer wraps in protocol packet
5. **Network Phase**: TCP sends packet to connected clients
6. **Decode Phase**: Android MediaCodec/BitmapFactory decodes frame
7. **Display Phase**: OpenGL ES renders stereo to VR display

---

## Encoder Comparison

### NVENC H.264 (Recommended)

**Technology**: NVIDIA hardware encoder (dedicated silicon)

**Advantages:**
- ✅ **Zero CPU/GPU rendering overhead** (separate encoder chip)
- ✅ **Ultra-low latency**: 10-20ms encode time
- ✅ **Low bandwidth**: 1-2 Mbps with inter-frame compression
- ✅ **No FPS impact**: 60 FPS maintained during streaming
- ✅ **Better quality**: H.264 motion compensation

**Disadvantages:**
- ⚠️ Requires NVIDIA GPU (GTX 900+, RTX)
- ⚠️ Requires NVIDIA driver 418+
- ⚠️ Requires PyAV library

**Use Cases:**
- Production streaming
- High frame rate requirements (60 FPS)
- Low-bandwidth networks (WiFi)
- Multiple simultaneous streams

### CPU JPEG (Fallback)

**Technology**: OpenCV CPU JPEG compression

**Advantages:**
- ✅ **Universal compatibility** (works on any GPU)
- ✅ **Simple implementation** (no driver requirements)
- ✅ **Predictable quality** (no compression artifacts)

**Disadvantages:**
- ⚠️ **Higher latency**: 30-50ms encode time
- ⚠️ **High bandwidth**: 10-20 Mbps (no inter-frame compression)
- ⚠️ **FPS impact**: Reduces to 30-40 FPS during streaming
- ⚠️ **CPU overhead**: 10-15% CPU usage

**Use Cases:**
- Testing/development
- AMD/Intel GPU systems
- Short demo sessions
- Single stream scenarios

### Performance Matrix

| Metric | NVENC H.264 | CPU JPEG | Improvement |
|--------|-------------|----------|-------------|
| **Encode Latency** | 10-20ms | 30-50ms | **2-3x faster** |
| **Total Latency** | 50-80ms | 100-150ms | **2x faster** |
| **Bandwidth** | 1-2 Mbps | 10-20 Mbps | **10x lower** |
| **FPS Impact** | 0 FPS | -20 FPS | **No degradation** |
| **CPU Usage** | <1% | 10-15% | **15x lower** |
| **GPU Rendering Impact** | 0% | 0% | **Equal** |
| **Quality (1080p)** | Excellent | Excellent | **Equal** |

**Recommendation**: Use NVENC for all production deployments. Reserve JPEG for testing or non-NVIDIA systems.

---

## Protocol Specification

### Wire Protocols (VRHP / VRH2 / VRH3)

#### Discovery Protocol (UDP Port 5556)

**Client → Server (Broadcast)**
```
Format: ASCII string
Content: "VR_HEADSET_HELLO:<device_name>" OR "VR_HEADSET_HELLO:<device_name>:<type>"
Example: "VR_HEADSET_HELLO:Oculus Quest 2"
Example: "VR_HEADSET_HELLO:Quest 3:vr"
```

`<type>` is optional and currently accepts: `vr`, `tv`, `phone`, `flat`.

**Server → Client (Unicast)**
```
Format: ASCII string
Content: "VR_SERVER_INFO:<tcp_port>"
Example: "VR_SERVER_INFO:5555"
```

**Discovery Sequence:**
```
1. Client broadcasts "VR_HEADSET_HELLO:..." every 2 seconds
2. Server receives broadcast and extracts client IP from UDP packet
3. Server responds with "VR_SERVER_INFO:5555" to client IP
4. Client extracts TCP port and connects
```

#### Streaming Protocol (TCP Port 5555)

**Packet Structure:**
```
┌────────────────────────────────────────────────────────┐
│                    TCP Stream                          │
├────────────────────────────────────────────────────────┤
│                                                         │
│  Packet 1:                                             │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Packet Size (4 bytes, big-endian uint32)        │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ Magic Bytes (4 bytes ASCII)                      │ │
│  │   - "VRH3" = H.264 encoding (default; includes fps_milli) │ │
│  │   - "VRH2" = H.264 encoding (legacy)              │ │
│  │   - "VRHP" = JPEG encoding                       │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ Frame ID (4 bytes, big-endian uint32)           │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ Left Eye Size (4 bytes, big-endian uint32)      │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ Right Eye Size (4 bytes, big-endian uint32)     │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ fps_milli (4 bytes, big-endian uint32) [VRH3 only]│ │
│  ├──────────────────────────────────────────────────┤ │
│  │ Left Eye Data (variable, encoded frame)         │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ Right Eye Data (variable, encoded frame)        │ │
│  └──────────────────────────────────────────────────┘ │
│                                                         │
│  Packet 2: (same structure)                            │
│  ...                                                    │
└─────────────────────────────────────────────────────────┘
```

**Header Details:**

| Field | Size | Type | Description |
|-------|------|------|-------------|
| Packet Size | 4 bytes | uint32 (big-endian) | Total size of packet (header + data) |
| Magic | 4 bytes | ASCII | Protocol identifier |
| Frame ID | 4 bytes | uint32 (big-endian) | Sequential frame counter |
| Left Size | 4 bytes | uint32 (big-endian) | Size of left eye data in bytes |
| Right Size | 4 bytes | uint32 (big-endian) | Size of right eye data in bytes (0 may mean “reuse left” for mono) |
| fps_milli | 4 bytes | uint32 (big-endian) | Only present for `VRH3`: $\text{fps}\times 1000$ (used for client-side pacing) |
| Left Data | N bytes | Binary | Encoded left eye frame (H.264 or JPEG) |
| Right Data | M bytes | Binary | Encoded right eye frame (H.264 or JPEG) |

**Example Packet (NVENC):**
```
Packet Size: 0x00003A42 (14914 bytes)
Magic:       0x56524833 ("VRH3")  (default)
             0x56524832 ("VRH2")  (legacy)
Frame ID:    0x0000007B (123)
Left Size:   0x00001D21 (7457 bytes)
Right Size:  0x00001D21 (7457 bytes)
fps_milli:   0x00007530 (30000)  # 30.000 FPS
Left Data:   [7457 bytes of H.264 NAL units]
Right Data:  [7457 bytes of H.264 NAL units]
```

**Example Packet (JPEG):**
```
Packet Size: 0x00032840 (206912 bytes)
Magic:       0x56524850 ("VRHP")
Frame ID:    0x0000007B (123)
Left Size:   0x00019420 (103456 bytes)
Right Size:  0x00019420 (103456 bytes)
Left Data:   [103456 bytes of JPEG data]
Right Data:  [103456 bytes of JPEG data]
```

**Network Characteristics:**

| Protocol | Port | Transport | Reliability | Ordering |
|----------|------|-----------|-------------|----------|
| Discovery | 5556 | UDP | No | No |
| Streaming | 5555 | TCP | Yes | Yes |

**TCP Socket Options:**
- `SO_REUSEADDR`: Allow port reuse
- `TCP_NODELAY`: Disable Nagle's algorithm (reduce latency)
- Non-blocking I/O with asyncio

---

## Frame Capture Pipeline

### OpenGL Frame Capture

MesmerVisor streaming captures frames from the compositor on the **Qt/GL thread**.
The streaming server runs on a **background thread** and must never call OpenGL.

**Method**: `glReadPixels()` synchronous pixel transfer

**Location**: compositor render loop (after all rendering complete)

**Code Flow (conceptual):**
```python
def paintGL(self):
    # 1. Render spiral shader
    self._render_spiral(uniforms)
    
    # 2. Render background images/videos
    self._render_background(w_px, h_px)
    
    # 3. Render text overlays
    self._render_text_overlays(w_px, h_px)
    
    # 4. Capture frame for VR/preview (if enabled)
    if self._vr_capture_enabled or self._preview_capture_enabled:
        self._capture_frame_for_vr(w_px, h_px)  # emits a numpy RGB frame
```

**Capture Implementation (high level):**
```python
def _capture_frame_for_vr(self, w_px: int, h_px: int) -> None:
    from OpenGL import GL
    import numpy as np
    
    # Read framebuffer (RGB or RGBA depending on compositor)
    pixels = GL.glReadPixels(0, 0, w_px, h_px, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    
    # Convert to numpy array
    frame_rgb = np.frombuffer(pixels, dtype=np.uint8).reshape(h_px, w_px, 3)
    
    # Flip vertically (OpenGL origin is bottom-left)
    frame_rgb = np.flipud(frame_rgb)
    
    # Emit frame to attached callback(s) (Qt signal or direct callback)
    self.frame_ready.emit(frame_rgb)
```

### Capture API Contract (Canonical)

Both compositor implementations support the same capture interface:

```python
compositor.enable_vr_streaming(frame_callback)
compositor.disable_vr_streaming()
```

The callback receives a `numpy.ndarray` shaped `(h, w, 3)` in RGB `uint8`.

### Threading Model (Why the cache exists)

- Qt calls `paintGL()` / `paintGL`-equivalent on the GL thread; capture happens there.
- The streaming server encodes + sends from its own thread/event loop.
- The supported pattern is: callback stores the *latest* frame into a lock-protected cache, and the server polls via `frame_callback()`.

This prevents crashes/artifacts from accidentally calling OpenGL outside the GL context.

**Performance Characteristics:**

| Resolution | glReadPixels Time | Memory Transfer | FPS Impact |
|------------|-------------------|-----------------|------------|
| 1920x1080 | 5-10ms | 6.2 MB | 0 (async) |
| 2560x1440 | 10-15ms | 11.1 MB | 0 (async) |
| 3840x2160 | 20-30ms | 24.9 MB | -5 FPS |

**Optimization Notes:**
- Only activates when `enable_vr_streaming()` called
- Zero overhead when VR streaming disabled
- Future optimization: Use PBO (Pixel Buffer Objects) for async transfer

### Alternative: Direct Texture Access (Future)

**Planned Enhancement**: CUDA/OpenGL interop for zero-copy encoding

```python
# Future implementation
def _capture_frame_for_vr_zerocopy(self):
    # Register OpenGL texture with CUDA
    cuda_surface = self._vr_encoder.register_gl_texture(self._fbo_texture_id)
    
    # Encode directly from GPU texture (no CPU transfer!)
    self._vr_encoder.encode_from_cuda(cuda_surface)
```

**Benefits:**
- Zero CPU/GPU memory transfer
- 0ms capture latency
- No `glReadPixels()` overhead
- Requires CUDA + OpenGL interop

---

## GPU Requirements

### NVENC Compatibility

**Supported GPUs:**

| Generation | Architecture | NVENC Version | Status |
|------------|--------------|---------------|--------|
| GTX 900 Series | Maxwell | NVENC 2nd Gen | ✅ Supported |
| GTX 1000 Series | Pascal | NVENC 3rd Gen | ✅ Supported |
| RTX 2000 Series | Turing | NVENC 4th Gen | ✅ **Recommended** |
| RTX 3000 Series | Ampere | NVENC 5th Gen | ✅ **Best** |
| RTX 4000 Series | Ada Lovelace | NVENC 6th Gen | ✅ **Best** |

**Minimum Requirements:**
- NVIDIA Driver: 418.81+
- CUDA Compute Capability: 5.0+
- VRAM: 2GB+

**Checking NVENC Support:**
```powershell
# Check GPU name
nvidia-smi --query-gpu=name --format=csv,noheader

# Check driver version
nvidia-smi --query-gpu=driver_version --format=csv,noheader

# Check via MesmerVisor
.\.venv\Scripts\python.exe -c "from mesmerglass.mesmervisor import get_gpu_info; info = get_gpu_info(); print('NVENC:', info['has_nvenc'])"
```

### AMD/Intel GPU Support

**Status**: JPEG encoding only (no hardware H.264 encoder exposed via PyAV)

**AMD VCE/VCN**: Not supported (no Python bindings)
**Intel Quick Sync**: Not supported (no Python bindings)

**Recommendation**: Use JPEG encoder for non-NVIDIA systems

---

## Installation

### Prerequisites

```powershell
# Python 3.11+
python --version

# Virtualenv (recommended)
python -m venv .venv
.\.venv\Scripts\activate

# Install MesmerGlass
pip install -r requirements.txt
```

### Dependencies

**Core (included in requirements.txt):**
```
PyQt6>=6.5.0
opencv-python>=4.8.0
numpy>=1.24.0
av>=10.0.0              # PyAV for NVENC
```

**System:**
- NVIDIA Driver 418+ (for NVENC)
- FFmpeg libraries (bundled with PyAV)

### Verification

```powershell
# Test imports
.\.venv\Scripts\python.exe -c "from mesmerglass.mesmervisor import VRStreamingServer, get_gpu_info; print('OK')"

# Check GPU capabilities
.\.venv\Scripts\python.exe -c "from mesmerglass.mesmervisor import get_gpu_info; info = get_gpu_info(); print('NVENC:', info['has_nvenc']); print('GPU:', info['gpu_name'])"

# Run test server
.\.venv\Scripts\python.exe -m mesmerglass vr-test --pattern checkerboard --duration 5
```

---

## Usage

### CLI Commands

#### vr-stream: Live Visual Streaming

**Basic Usage:**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-stream
```

**Full Options:**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-stream \
  --host 0.0.0.0 \
  --port 5555 \
  --discovery-port 5556 \
  --encoder auto \
  --fps 30 \
  --quality 25 \
  --bitrate 2000000 \
  --stereo-offset 0 \
  --intensity 0.75 \
  --duration 0
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--host` | string | `0.0.0.0` | Server bind address |
| `--port` | int | `5555` | TCP streaming port |
| `--discovery-port` | int | `5556` | UDP discovery port |
| `--encoder` | choice | `auto` | Encoder: `auto`, `nvenc`, `jpeg` |
| `--fps` | int | `30` | Target frames per second |
| `--quality` | int | `85` | JPEG quality (1-100). Recommended `25` for Oculus Go/Quest; session streaming defaults to `25`. Ignored for NVENC. |
| `--bitrate` | int | `2000000` | H.264 bitrate in bps (ignored for JPEG). Consider higher values for LAN (e.g. 50–120 Mbps). |
| `--stereo-offset` | int | `0` | Stereo parallax offset in pixels (0=mono) |
| `--intensity` | float | `0.75` | Initial spiral intensity (0.0-1.0) |
| `--duration` | float | `0` | Stream duration in seconds (0=infinite) |

**Examples:**

```powershell
# Auto-detect encoder, default settings (quality 25 optimized for Oculus Go)
.\.venv\Scripts\python.exe -m mesmerglass vr-stream

# Force NVENC with high bitrate
.\.venv\Scripts\python.exe -m mesmerglass vr-stream --encoder nvenc --bitrate 4000000 --fps 60

# Force JPEG with custom quality (default 25 is optimal)
.\.venv\Scripts\python.exe -m mesmerglass vr-stream --encoder jpeg --quality 25

# Stream for 60 seconds then stop
.\.venv\Scripts\python.exe -m mesmerglass vr-stream --duration 60
```

#### vr-test: Test Pattern Streaming

**Basic Usage:**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-test --pattern checkerboard --duration 10
```

**Full Options:**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-test \
  --pattern checkerboard \
  --host 0.0.0.0 \
  --port 5555 \
  --discovery-port 5556 \
  --encoder auto \
  --fps 30 \
  --width 1920 \
  --height 1080 \
  --quality 25 \
  --duration 10
```

**Test Patterns:**
- `checkerboard`: Animated black/magenta/cyan grid
- `gradient`: Horizontal color gradient
- `noise`: Random RGB noise
- `spiral`: Rotating spiral pattern (requires full app)

---

## Performance Tuning

### Encoder Selection Strategy

**Decision Tree:**
```
Has NVENC? 
├─ Yes → Use NVENC (best performance)
└─ No → Has AMD/Intel GPU?
       ├─ Yes → Use JPEG (only option)
       └─ No → Use JPEG (fallback)
```

**Auto-Detection Code:**
```python
from mesmerglass.mesmervisor import select_encoder, EncoderType

# Auto-select best encoder
encoder_type = select_encoder(EncoderType.AUTO)
print(f"Selected: {encoder_type.value}")
```

### Bitrate Optimization

**NVENC H.264 Bitrate Guide:**

| Resolution | FPS | Bitrate (Low) | Bitrate (Medium) | Bitrate (High) |
|------------|-----|---------------|------------------|----------------|
| 1280x720 | 30 | 1 Mbps | 1.5 Mbps | 2 Mbps |
| 1920x1080 | 30 | 2 Mbps | 3 Mbps | 4 Mbps |
| 1920x1080 | 60 | 4 Mbps | 6 Mbps | 8 Mbps |
| 2560x1440 | 30 | 4 Mbps | 6 Mbps | 8 Mbps |

**JPEG Quality Guide:**

| Quality | File Size | Visual Quality | Use Case |
|---------|-----------|----------------|----------|
| 60-70 | Small | Good | Testing/debugging |
| 75-85 | Medium | Excellent | **Recommended** |
| 90-100 | Large | Perfect | High-end only |

### Network Optimization

**WiFi Recommendations:**
- Use **5GHz band** (less congestion, higher throughput)
- Place router close to VR headset
- Disable other WiFi devices during streaming
- Use QoS (Quality of Service) to prioritize streaming traffic

**Bandwidth Requirements:**

| Encoder | Resolution | FPS | Bandwidth | WiFi Gen |
|---------|------------|-----|-----------|----------|
| NVENC | 1920x1080 | 30 | 2 Mbps | WiFi 4+ |
| NVENC | 1920x1080 | 60 | 4 Mbps | WiFi 5+ |
| JPEG | 1920x1080 | 30 | 15 Mbps | WiFi 5+ |

**Latency Breakdown:**

| Component | NVENC | JPEG |
|-----------|-------|------|
| Frame capture | 5-10ms | 5-10ms |
| Encoding | 10-20ms | 30-50ms |
| Network (WiFi) | 10-30ms | 10-30ms |
| Decoding | 5-10ms | 10-20ms |
| **Total** | **30-70ms** | **55-110ms** |

### Resolution Scaling

**Performance vs Quality:**

```python
# Lower resolution = better performance
.\.venv\Scripts\python.exe -m mesmerglass vr-test --width 1280 --height 720  # 720p

# Standard resolution
.\.venv\Scripts\python.exe -m mesmerglass vr-test --width 1920 --height 1080  # 1080p

# High resolution (requires powerful system)
.\.venv\Scripts\python.exe -m mesmerglass vr-test --width 2560 --height 1440  # 1440p
```

---

## Troubleshooting

### Common Issues

#### 1. "NVENC not available"

**Symptoms:**
```
INFO: Recommended encoder: CPU JPEG (no hardware encoder detected)
```

**Diagnosis:**
```powershell
# Check GPU detection
nvidia-smi

# Check PyAV codecs
.\.venv\Scripts\python.exe -c "import av; print([c.name for c in av.codec.codecs_available if 'nvenc' in c.name])"
```

**Solutions:**

**A. Update NVIDIA Driver**
```powershell
# Check current driver
nvidia-smi --query-gpu=driver_version --format=csv,noheader

# Download latest from nvidia.com (minimum 418.81)
```

**B. Reinstall PyAV**
```powershell
pip uninstall av
pip install av --no-cache-dir
```

**C. Check GPU Compatibility**
```powershell
# GTX 900+ or RTX series required
nvidia-smi --query-gpu=name --format=csv,noheader
```

#### 2. "Connection refused" / Firewall Block

**Symptoms:**
```
ERROR: [Errno 10061] No connection could be made because the target machine actively refused it
```

**Solutions:**

**A. Allow Firewall (Windows)**
```powershell
# UDP Discovery
netsh advfirewall firewall add rule name="MesmerVisor UDP" dir=in action=allow protocol=UDP localport=5556

# TCP Streaming
netsh advfirewall firewall add rule name="MesmerVisor TCP" dir=in action=allow protocol=TCP localport=5555
```

**B. Check Port Availability**
```powershell
# Check if ports in use
netstat -an | findstr "5555"
netstat -an | findstr "5556"
```

**C. Verify Network**
```powershell
# Check IP address
ipconfig | findstr IPv4

# Test connectivity from VR headset
ping <PC_IP_ADDRESS>
```

#### 3. Low FPS / Stuttering

**Symptoms:**
- Choppy video in VR
- FPS drops below 20
- High network latency

**Solutions:**

**A. Reduce Resolution**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-stream --fps 20
```

**B. Lower Quality (JPEG only)**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-stream --encoder jpeg --quality 70
```

**C. Use NVENC (if available)**
```powershell
.\.venv\Scripts\python.exe -m mesmerglass vr-stream --encoder nvenc
```

**D. Check WiFi**
```powershell
# Switch to 5GHz band
# Move closer to router
# Disable other devices
```

#### 4. "TimeoutError" on Shutdown

**Symptoms:**
```
asyncio.exceptions.TimeoutError
```

**Explanation**: This is expected behavior when `--duration` is set. The server times out gracefully after the specified duration.

**Solution**: Ignore this error or press Ctrl+C to stop manually.

#### 5. No Client Connection

**Symptoms:**
```
INFO: Waiting for VR clients to connect...
(no client ever connects)
```

**Diagnosis:**
```powershell
# Check if server is listening
netstat -an | findstr "5555"

# Check discovery service
# (should see UDP 5556 listening)
```

**Solutions:**

**A. Verify Android App**
- Ensure VR app is installed
- Launch app on headset
- Check app has network permissions

**B. Same Network**
- PC and VR headset must be on same WiFi
- No VPN/tunnel or network isolation

**VPN / Tunnel Gotcha (Common on Windows):**
- If a VPN installs routes that prefer a virtual interface, the headset may discover the server but fail to connect (or connect times out).
- Symptoms often include source IPs in carrier-grade NAT ranges (e.g. `100.64.0.0/10`) and TCP connect timeouts to your LAN IP (e.g. `192.168.x.x`).

Quick checks:
```powershell
ipconfig | findstr IPv4
route print | findstr 192.168.
```

**C. Manual IP Entry (fallback)**
- Note PC IP: `ipconfig`
- Enter manually in Android app (if supported)

#### 6. Client Connects But No Video / “Flashing” Status

**Symptoms:**
- The Android client repeatedly changes connection/status colors.
- Server shows discovery/connection logs, but no frames are displayed.

**Likely Causes & Fixes:**

**A. No frames are being captured**
- VR streaming requires capture to be enabled on the compositor via `enable_vr_streaming(frame_callback)`.
- If the server is running but capture is not attached, the server will have nothing to encode/send.

Sanity check (server side):
- Look for logs indicating capture attached, e.g. `VR streaming enabled (LoomWindowCompositor)`.
- If you see errors like `object has no attribute 'enable_vr_streaming'`, update to a compositor that implements the capture API.

**B. GL thread vs server thread mismatch**
- Never call OpenGL from the server thread. Always capture on the GL thread, cache the latest RGB frame, and have the server poll via `frame_callback()`.

---

## Development Guide

### Module Structure

```
mesmerglass/
├── mesmervisor/
│   ├── __init__.py           # Module exports
│   ├── gpu_utils.py          # GPU detection & encoder selection
│   ├── frame_encoder.py      # NVENC + JPEG encoders
│   ├── streaming_server.py   # TCP/UDP server
│   └── README.md             # Quick start guide
├── mesmerloom/
│   └── compositor.py         # Frame capture integration
├── cli.py                    # Command handlers
└── tests/
    └── test_mesmervisor.py   # Test suite
```

### Adding New Encoders

**Example: Adding Intel QuickSync**

1. **Create encoder class:**
```python
# frame_encoder.py
class QuickSyncEncoder(FrameEncoder):
    def __init__(self, width, height, fps, bitrate):
        import av
        self.container = av.open('pipe:', 'w', format='h264')
        self.stream = self.container.add_stream('h264_qsv', rate=fps)
        # ... configure QuickSync options
    
    def encode(self, frame):
        # ... encoding logic
        return encoded_data
    
    def get_encoder_type(self):
        return EncoderType.QUICKSYNC
```

2. **Update EncoderType enum:**
```python
# gpu_utils.py
class EncoderType(Enum):
    NVENC = "nvenc"
    JPEG = "jpeg"
    QUICKSYNC = "quicksync"  # Add new type
    AUTO = "auto"
```

3. **Update detection:**
```python
# gpu_utils.py
def has_quicksync_support() -> bool:
    try:
        codec = av.codec.Codec('h264_qsv', 'w')
        return True
    except:
        return False
```

4. **Update factory:**
```python
# frame_encoder.py
def create_encoder(encoder_type, ...):
    if encoder_type == EncoderType.QUICKSYNC:
        return QuickSyncEncoder(width, height, fps, bitrate)
    # ... existing encoders
```

### Testing

**Run test suite:**
```powershell
.\.venv\Scripts\python.exe -m pytest mesmerglass/tests/test_mesmervisor.py -v
```

**Manual testing:**
```powershell
# Test GPU detection
.\.venv\Scripts\python.exe -c "from mesmerglass.mesmervisor import get_gpu_info; print(get_gpu_info())"

# Test NVENC encoder
.\.venv\Scripts\python.exe -m mesmerglass vr-test --pattern checkerboard --encoder nvenc --duration 3

# Test JPEG encoder
.\.venv\Scripts\python.exe -m mesmerglass vr-test --pattern gradient --encoder jpeg --duration 3
```

### Debugging

**Enable verbose logging:**
```powershell
$env:MESMERGLASS_LOG_LEVEL="DEBUG"
.\.venv\Scripts\python.exe -m mesmerglass vr-stream
```

**Network packet capture:**
```powershell
# Use Wireshark to inspect TCP 5555 traffic
# Filter: tcp.port == 5555
```

**Performance profiling:**
```python
import cProfile
import pstats

cProfile.run('cmd_vr_test(args)', 'profile.stats')
stats = pstats.Stats('profile.stats')
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## API Reference

### VRStreamingServer

**Class**: `mesmerglass.mesmervisor.VRStreamingServer`

**Constructor:**
```python
VRStreamingServer(
    host: str = "0.0.0.0",
    port: int = 5555,
    discovery_port: int = 5556,
    encoder_type: EncoderType = EncoderType.AUTO,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    quality: int = 25,
    bitrate: int = 2000000,
    stereo_offset: int = 0,
    frame_callback: Optional[Callable] = None
)
```

**Methods:**
- `async start()`: Start server and begin streaming
- `async stop()`: Stop server and cleanup resources
- `create_packet(left, right, frame_id)`: Create protocol packet

**Example:**
```python
import asyncio
from mesmerglass.mesmervisor import VRStreamingServer, EncoderType

def frame_generator():
    # Return RGB numpy array (height, width, 3) uint8
    return generate_frame()

server = VRStreamingServer(
    encoder_type=EncoderType.NVENC,
    fps=30,
    frame_callback=frame_generator
)

asyncio.run(server.start())
```

### FrameEncoder

**Base Class**: `mesmerglass.mesmervisor.FrameEncoder`

**Abstract Methods:**
- `encode(frame: np.ndarray) -> bytes`: Encode RGB frame
- `get_encoder_type() -> EncoderType`: Return encoder type
- `close()`: Cleanup resources

**Factory Function:**
```python
from mesmerglass.mesmervisor import create_encoder, EncoderType

# Create NVENC encoder
encoder = create_encoder(
    EncoderType.NVENC,
    width=1920,
    height=1080,
    fps=30,
    bitrate=2000000
)

# Encode frame
rgb_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
encoded = encoder.encode(rgb_frame)

# Cleanup
encoder.close()
```

### GPU Utilities

**Functions:**
```python
from mesmerglass.mesmervisor import (
    has_nvenc_support,
    get_gpu_info,
    select_encoder,
    log_encoder_info
)

# Check NVENC availability
if has_nvenc_support():
    print("NVENC available")

# Get detailed GPU info
info = get_gpu_info()
print(f"GPU: {info['gpu_name']}")
print(f"NVENC: {info['has_nvenc']}")
print(f"Recommended: {info['recommended_encoder_name']}")

# Auto-select encoder
encoder_type = select_encoder(EncoderType.AUTO)

# Log diagnostics
log_encoder_info()
```

### LoomCompositor VR Integration

**Methods (works for both compositor types):**
```python
from mesmerglass.mesmerloom import LoomCompositor

compositor = LoomCompositor(director)

# Enable VR streaming
def frame_callback(rgb_frame):
    # Process captured frame
    print(f"Frame: {rgb_frame.shape}")

compositor.enable_vr_streaming(frame_callback)

# Disable VR streaming
compositor.disable_vr_streaming()
```

---

## Appendix

### References

- [NVIDIA NVENC Documentation](https://developer.nvidia.com/nvidia-video-codec-sdk)
- [PyAV Documentation](https://pyav.org/)
- [Android VR Client Source](../../../mesmerglass/vr/android-client/)
- [VR Client APK](../../../MEDIA/vr-client/MesmerGlass-VR-Client.apk)

### Performance Optimization

**Oculus Go/Quest Optimized Settings (Production Default)**:
- **JPEG Quality**: 25 (locked in launcher.py)
- **Resolution**: 2048x1024 (downscaled from 1920x1080)
- **Target FPS**: 30
- **Achieved Performance**:
  - Bandwidth: ~60 Mbps (73% reduction from quality 85)
  - FPS: Stable 20-21
  - Latency: 94-96ms
  - Visual Quality: Good and acceptable

These settings provide the optimal balance between performance and quality for wireless VR streaming over WiFi to mobile VR headsets.

### Changelog

**Version 0.7.0 (November 2025)**
- Initial release
- NVENC H.264 support
- JPEG CPU fallback
- UDP auto-discovery
- TCP streaming protocol
- CLI integration
- Performance optimization for Oculus Go/Quest
- Quality 25 as production default

### License

Part of MesmerGlass project. See LICENSE file for details.

### Contact

For issues or questions, please file an issue on the MesmerGlass GitHub repository.

---

**End of Documentation**
