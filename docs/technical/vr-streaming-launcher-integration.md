# VR Streaming Launcher Integration

## Overview

VR streaming is now fully integrated into the MesmerGlass launcher as a display option. Users can select VR devices alongside physical monitors in the Displays tab.

## Features

### Display Selection
- **Monitors Section**: Lists all physical displays with resolution
- **VR Devices Section**: Lists discovered VR headsets (wireless)
- **Checkboxes**: Select any combination of monitors and VR devices
- **Refresh Button**: Manually refresh VR device list
- **Auto-refresh**: VR devices update automatically every 2 seconds

### VR Discovery
- **Protocol**: UDP broadcast on port 5556
- **Message Format**: `VR_HEADSET_HELLO:<device_name>`
- **Server Response**: `VR_SERVER_INFO:5555`
- **Auto-detection**: VR headsets appear automatically when running the Android app

### VR Streaming
- **Protocol**: TCP streaming on port 5555
- **Encoding**: JPEG (quality 25 optimized for Oculus Go/Quest, ~25KB per frame)
- **Frame Rate**: 30 FPS target (achieves stable 20 FPS)
- **Resolution**: 1920x1080 (downscaled to 2048x1024 for VR)
- **Performance**: ~60 Mbps bandwidth, 94-96ms latency, good visual quality
- **Packet Format**: 4-byte size header + 16-byte header (VRHP magic) + frame data
- **Source**: Captures from spiral window's compositor (fullscreen rendering)

## Usage

### Launch with VR Streaming

1. **Open Launcher**: Start MesmerGlass application
2. **Go to Displays Tab**: Click "Displays" in the tab bar
3. **Start VR App**: Launch the VR receiver app on your headset
4. **Wait for Discovery**: VR device appears in "VR Devices (Wireless)" section
5. **Select Device**: Check the box next to the VR device
6. **Optional**: Also select physical monitors for local preview
7. **Click Launch**: Start streaming to VR headset

### VR-Only Mode

If you select **only** VR devices (no monitors):
- Spiral window is created but **minimized**
- Compositor continues rendering in background
- All visuals stream to VR headset only
- Lower CPU usage (no visible window updates)

### Monitor + VR Mode

If you select **both monitors and VR**:
- Spiral window displays on selected monitors (fullscreen)
- Same visuals stream to VR headset simultaneously
- Perfect synchronization between local and VR display

## Technical Details

### Components

1. **VRStreamingServer** (`mesmervisor/streaming_server.py`)
   - TCP server on port 5555
   - Frame encoding and packet creation
   - Client connection management

2. **DiscoveryService** (`mesmervisor/streaming_server.py`)
   - UDP listener on port 5556
   - Responds to VR_HEADSET_HELLO broadcasts
   - Tracks discovered clients

3. **JPEGEncoder** (`mesmervisor/frame_encoder.py`)
   - Hardware-accelerated JPEG encoding
   - Quality 25 (optimized for Oculus Go/Quest)
   - ~25KB per frame at 1920x1080 (downscaled to 2048x1024)

### Frame Capture Flow

```
Compositor paintGL() 
  → frame_drawn signal emitted
  → on_frame_ready() callback
  → glReadPixels() captures RGB frame
  → JPEGEncoder.encode() compresses to JPEG
  → VRStreamingServer.send_frame() transmits to clients
```

### Packet Format

```
[4 bytes]  Packet size (big-endian uint32)  ← Prevents OutOfMemoryError!
[16 bytes] Header:
           magic(4):      "VRHP"
           frame_id(4):   Sequence number
           left_size(4):  JPEG size (left eye)
           right_size(4): JPEG size (right eye)
[variable] Left eye JPEG data
[variable] Right eye JPEG data
```

**Critical**: The 4-byte size header is **mandatory**. Without it, the Android client reads "VRHP" as the packet size (1,448,233,040 bytes) and crashes with OutOfMemoryError.

### Integration Points

#### Launcher.__init__()
```python
self.vr_streaming_server = None  # Created on-demand
self.vr_discovery_service = None
self._vr_streaming_active = False
```

#### Launcher.launch()
```python
if vr_clients:
    # Create streaming server with JPEG encoder (quality 25 optimized for Oculus Go/Quest)
    encoder = JPEGEncoder(quality=25)
    self.vr_streaming_server = VRStreamingServer(
        width=1920, height=1080, fps=30,
        encoder=encoder, protocol_magic=b'VRHP'
    )
    
    # Start discovery service
    self.vr_discovery_service = DiscoveryService(
        discovery_port=5556, server_port=5555
    )
    self.vr_discovery_service.start()
    
    # Start streaming server
    self.vr_streaming_server.start_server()
    
    # Connect to compositor frame signal
    streaming_compositor.frame_drawn.connect(on_frame_ready)
    self._vr_streaming_active = True
```

#### Launcher.stop_all()
```python
self._vr_streaming_active = False
if self.vr_streaming_server:
    self.vr_streaming_server.stop_server()
if self.vr_discovery_service:
    self.vr_discovery_service.stop()
```

## Performance

### Measured Performance (JPEG Quality 25 - Oculus Go Optimized)
- **Encoding Time**: ~15ms per frame
- **Frame Size**: 25-30KB per frame (73% reduction from quality 85)
- **Network Bandwidth**: ~60 Mbps at target 30 FPS (achieves stable 20 FPS)
- **Latency**: 94-96ms end-to-end (improved from 104-135ms)
- **CPU Usage**: ~10-15% (encoding + OpenGL)
- **Visual Quality**: Good and acceptable for wireless VR streaming

### Historical Optimization
- **Quality 85 (Initial)**: 230-340 Mbps, 10-18 FPS, 104-135ms latency
- **Quality 50 (First Test)**: 130-160 Mbps, 18-19 FPS
- **Quality 35 (Second Test)**: 90-100 Mbps, 19-20 FPS
- **Quality 25 (Final)**: **60-63 Mbps, 20-21 FPS, 94-96ms latency** ✅

### Optimization Notes
- JPEG quality 25 is optimal for Oculus Go/Quest over WiFi
- Quality setting is hardcoded in launcher.py (line 2342) as production default
- Hardware acceleration used when available (NVENC)
- Frame capture is fast (~2ms with glReadPixels)
- Stable 20 FPS achieved at quality 25 (target is 30 FPS)

## Troubleshooting

### VR Device Not Appearing
1. Check VR app is running on headset
2. Verify both PC and headset on same network
3. Check firewall allows UDP 5556 and TCP 5555
4. Click "🔄 Refresh VR" button manually

### Connection Issues
1. Check network connectivity (ping VR headset IP)
2. Verify ports not blocked by firewall
3. Check Android app logs for errors
4. Try restarting VR app

### Black Screen in VR
1. Verify compositor is rendering (check monitor display)
2. Check spiral is enabled (toggle MesmerLoom)
3. Verify intensity is not zero
4. Check VR app is receiving packets (network monitor)

### Crashes
1. Verify packet format includes 4-byte size header
2. Check frame sizes are reasonable (<1MB)
3. Monitor Android logcat for OutOfMemoryError
4. Verify JPEG encoding is working

## Future Enhancements

### Planned Features
- H.264/H.265 encoding for lower bandwidth
- Multiple simultaneous VR clients
- Client-specific encoding settings
- Bandwidth adaptation (dynamic quality)
- Stereoscopic 3D support (separate left/right eyes)

### CLI Access
VR streaming is also available via CLI:
```bash
python -m mesmerglass vr-stream --intensity 0.75 --fps 30 --encoder jpeg
```

See `docs/cli.md` for full CLI documentation.

## Related Documentation
- [VR Streaming Server](vr-streaming-server.md) - Server implementation details
- [Frame Encoding](frame-encoding.md) - Encoding options and performance
- [CLI Interface](cli-interface.md) - Command-line VR streaming
- [Network Configuration](network-configuration.md) - Port and firewall setup
