# MesmerVisor - VR Visual Streaming

Stream live-rendered hypnotic visuals from MesmerGlass to VR headsets using GPU-accelerated encoding.

## Quick Start

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

**For NVIDIA GPU users (recommended):**
- Ensures PyAV is installed for hardware H.264 encoding
- 10x better performance and lower latency than CPU JPEG

**System Requirements:**
- NVIDIA GPU with NVENC support (GTX 900+ series, all RTX cards)
- NVIDIA Driver 418+

### 2. Install Android VR Client

- Copy `MEDIA/vr-client/app-debug.apk` to your VR headset
- Install via `adb install app-debug.apk`
- Or use SideQuest / File Manager

### 3. Start Streaming

**Test pattern streaming (no full app):**
```powershell
.\.venv\bin\python -m mesmerglass vr-test --pattern checkerboard
```

**Live visual streaming:**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --fps 30 --encoder auto
```

### 4. Connect VR Headset

- Launch "MesmerGlass VR" app on your headset
- App will automatically discover and connect to the server
- No manual IP entry needed!

---

## Features

### Encoding Options

**Auto-detect (recommended):**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --encoder auto
```
- Automatically selects NVENC if available
- Falls back to CPU JPEG if no hardware encoder

**Force NVENC (H.264 GPU encoding):**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --encoder nvenc --bitrate 2000000
```
- Hardware accelerated
- Low latency (10-20ms)
- Low bandwidth (1-2 Mbps)
- **Zero FPS impact** on spiral rendering

**Force JPEG (CPU fallback):**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --encoder jpeg --quality 25
```
- Works on any GPU
- Optimized for Oculus Go/Quest (quality 25)
- ~60 Mbps bandwidth, stable 20 FPS
- Good visual quality for wireless VR

### Command Options

**vr-stream** - Stream live visuals
```
--host          Server host (default: 0.0.0.0)
--port          TCP streaming port (default: 5555)
--discovery-port UDP discovery port (default: 5556)
--encoder       auto|nvenc|jpeg (default: auto)
--fps           Target FPS (default: 30)
--quality       JPEG quality 1-100 (default: 25, optimized for Oculus Go/Quest)
--bitrate       H.264 bitrate in bps (default: 2000000)
--stereo-offset Stereo parallax px (default: 0=mono)
--intensity     Initial spiral intensity (default: 0.75)
--duration      Stream duration seconds (0=infinite)
```

**vr-test** - Test with generated pattern
```
--pattern       checkerboard|gradient|noise|spiral
--width         Frame width (default: 1920)
--height        Frame height (default: 1080)
--encoder       auto|nvenc|jpeg
--fps           Target FPS
--duration      Duration seconds (0=infinite)
```

---

## Architecture

### GPU-Accelerated Pipeline

```
LoomCompositor (OpenGL)
    ↓ paintGL() renders spiral + media + text
    ↓ glReadPixels() captures RGBA framebuffer
    ↓
FrameEncoder
    ↓ NVENC: Zero-copy GPU H.264 encoding (10ms)
    ↓ JPEG: CPU encoding with cv2 (30ms)
    ↓
VRStreamingServer
    ↓ TCP packet: [size][magic][frameID][sizes][data]
    ↓
Network (WiFi)
    ↓
Android VR Client
    ↓ H.264: MediaCodec hardware decode
    ↓ JPEG: BitmapFactory software decode
    ↓
OpenGL ES Stereo Renderer
```

### Protocol: VRHP (VR Hypnotic Protocol)

**Discovery (UDP port 5556):**
```
Client → Server: "VR_HEADSET_HELLO:Oculus Quest 2"
Server → Client: "VR_SERVER_INFO:5555"
```

**Streaming (TCP port 5555):**
```
Packet Structure:
[4 bytes] Packet size (big-endian int)
[4 bytes] Magic: "VRH3" (H.264 default), "VRH2" (H.264 legacy), or "VRHP" (JPEG)
[4 bytes] Frame ID
[4 bytes] Left eye data size
[4 bytes] Right eye data size
[N bytes] Left eye encoded data
[M bytes] Right eye encoded data
```

---

## Performance Comparison

| Encoder | Latency | Bandwidth | FPS Impact | GPU Req |
|---------|---------|-----------|------------|---------|
| **NVENC H.264** | 10-20ms | 1-2 Mbps | **0 FPS** | NVIDIA GTX 900+ |
| **CPU JPEG** | 50-80ms | 10-20 Mbps | -20 FPS | Any GPU |

**Recommended: Use NVENC for best performance!**

---

## Troubleshooting

### "NVENC not available"

**Check GPU:**
```powershell
.\.venv\bin\python -c "from mesmerglass.mesmervisor import get_gpu_info; import json; print(json.dumps(get_gpu_info(), indent=2))"
```

**Install PyAV:**
```powershell
pip install av
```

**Update NVIDIA Driver:**
- Download from nvidia.com
- Minimum version: 418+

### "Connection refused"

**Check firewall:**
```powershell
netsh advfirewall firewall add rule name="MesmerVisor UDP" dir=in action=allow protocol=UDP localport=5556
netsh advfirewall firewall add rule name="MesmerVisor TCP" dir=in action=allow protocol=TCP localport=5555
```

**Verify same network:**
- PC and VR headset must be on same WiFi
- Use 5GHz WiFi for best performance

### "Low FPS / Stuttering"

**Reduce resolution:**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --fps 20
```

**Lower quality:**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --quality 75
```

**Use NVENC:**
```powershell
.\.venv\bin\python -m mesmerglass vr-stream --encoder nvenc
```

---

## Technical Documentation

See `docs/technical/mesmervisor.md` for:
- Detailed architecture
- OpenGL frame capture
- CUDA/OpenGL interop
- Android client protocol
- Performance optimization
- Development guide

---

## Credits

Based on VR streaming architecture, now fully integrated into MesmerGlass.

**Technologies:**
- PyAV (FFmpeg/NVENC bindings)
- OpenCV (JPEG encoding)
- OpenGL (frame capture)
- TCP/UDP networking
- Android OpenGL ES + MediaCodec

