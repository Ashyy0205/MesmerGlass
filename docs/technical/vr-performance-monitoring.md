# VR Performance Monitoring

## Overview

Comprehensive performance monitoring system for VR streaming, tracking frame rate, latency breakdown, bandwidth usage, and frame sizes.

## Architecture

### Server-side Metrics (Python)
Location: `mesmerglass/engine/vr/streaming_server.py`

**Tracks:**
- Frame encoding time (JPEG compression)
- Network send time (TCP transmission)
- Total bytes sent
- Frame sizes (per-eye and total)
- FPS (window and average)

**Output Format:**
```
📊 VR Performance Stats (Frame 60):
   FPS: 30.5 (window) | 30.2 (avg)
   Latency: 45.3ms (encode: 38.2ms, send: 7.1ms)
   Bandwidth: 25.34 Mbps
   Frame size: 105.2 KB (L: 52.6 KB, R: 52.6 KB)
```

### Client-side Metrics (Android)
Location: `mesmerglass/vr/android-client/app/src/main/java/com/hypnotic/vrreceiver/MainActivity.kt`

**Tracks:**
- Frame decode time (JPEG decompression)
- Render time (OpenGL texture upload + draw)
- Total bytes received
- Client-side FPS
- Total latency (decode + render)

**Output Format:**
```
📊 VR Client Performance Stats (Frame 60):
   Client FPS: 30.1
   Latency: 12.3ms (decode: 8.5ms, render: 3.8ms)
   Bandwidth: 25.10 Mbps
   Bytes received: 6312 KB
```

## Performance Tracking Fields

### Server (`VRStreamingServer`)
```python
self.frames_sent = 0              # Total frames sent
self.start_time = time.time()     # Session start time
self.total_bytes_sent = 0         # Total bytes transmitted
self.encode_times = []            # Encoding time per frame (ms)
self.send_times = []              # Send time per frame (ms)
self.last_stats_time = time.time() # Last stats log time
```

### Client (`MainActivity`)
```kotlin
private var framesReceived = 0           // Total frames received
private var bytesReceived: Long = 0      // Bytes in current stats window
private var lastStatsTime = System.currentTimeMillis()
private var decodeTimes = mutableListOf<Long>()  // Decode time per frame (ms)
private var renderTimes = mutableListOf<Long>()  // Render time per frame (ms)
```

## Measurement Points

### Server-side Measurements

**Encode Time:**
```python
encode_start = time.time()
left_encoded, right_encoded = encode_stereo_frames(
    self.encoder, frame, self.stereo_offset
)
encode_time = time.time() - encode_start
self.encode_times.append(encode_time)
```

**Send Time:**
```python
send_start = time.time()
await loop.sock_sendall(client_socket, packet)
send_time = time.time() - send_start
self.send_times.append(send_time)
```

**Packet Size:**
```python
packet = self.create_packet(left_encoded, right_encoded, frame_id)
packet_size = len(packet)
self.total_bytes_sent += packet_size
```

### Client-side Measurements

**Decode Time:**
```kotlin
val decodeStart = System.currentTimeMillis()
val leftBitmap = BitmapFactory.decodeByteArray(leftFrameData, 0, leftFrameData!!.size)
// ... decode right eye ...
val decodeTime = System.currentTimeMillis() - decodeStart
decodeTimes.add(decodeTime)
```

**Render Time:**
```kotlin
val renderStart = System.currentTimeMillis()
// ... OpenGL operations (texture upload, rendering) ...
val renderTime = System.currentTimeMillis() - renderStart
renderTimes.add(renderTime)
```

**Bytes Received:**
```kotlin
synchronized(frameLock) {
    leftFrameData = leftData
    rightFrameData = rightData
    bytesReceived += leftData.size.toLong() + rightData.size.toLong()
}
```

## Stats Logging

Both server and client log detailed statistics **every 60 frames**:

### Server Statistics
- **Window FPS**: FPS for last 60 frames
- **Average FPS**: Overall FPS since streaming started
- **Encode latency**: Average JPEG encoding time
- **Send latency**: Average TCP send time
- **Total latency**: Encode + send
- **Bandwidth**: Total data rate in Mbps
- **Frame sizes**: Left eye, right eye, and total KB

### Client Statistics
- **Client FPS**: Frames rendered per second
- **Decode latency**: Average JPEG decode time
- **Render latency**: Average OpenGL render time
- **Total latency**: Decode + render
- **Bandwidth**: Received data rate in Mbps
- **Bytes received**: Total KB in stats window

## Memory Management

Both implementations use circular buffers to prevent memory growth:

```python
# Server: Keep only last 120 measurements
if len(self.encode_times) > 120:
    self.encode_times = self.encode_times[-120:]
if len(self.send_times) > 120:
    self.send_times = self.send_times[-120:]
```

```kotlin
// Client: Keep only last 120 measurements
if (decodeTimes.size > 120) {
    decodeTimes.subList(0, decodeTimes.size - 120).clear()
}
if (renderTimes.size > 120) {
    renderTimes.subList(0, renderTimes.size - 120).clear()
}
```

## Performance Targets

### Target Metrics
- **FPS**: 30 (configurable)
- **End-to-end latency**: <50ms
- **Bandwidth**: <30 Mbps
- **Dropped frames**: 0

### Latency Breakdown
```
Server Encode (30-40ms)
  ↓
Server Send (5-10ms)
  ↓
Network Transit (varies)
  ↓
Client Decode (5-10ms)
  ↓
Client Render (2-5ms)
  ↓
Total: <50ms target
```

## Viewing Performance Data

### Server Logs
Performance stats appear in the launcher console output:
```bash
./.venv/bin/python run.py
# or
./.venv/bin/python -m mesmerglass
```

Look for lines starting with:
```
📊 VR Performance Stats (Frame 60):
```

### Client Logs (Android)
Use adb logcat to view client performance:
```bash
adb logcat | Select-String "VR Client Performance"
```

Output example:
```
📊 VR Client Performance Stats (Frame 60):
   Client FPS: 30.1
   Latency: 12.3ms (decode: 8.5ms, render: 3.8ms)
   Bandwidth: 25.10 Mbps
```

## Interpreting Results

### Good Performance
- **Server FPS**: 29-31 (stable around target)
- **Client FPS**: 29-31 (matching server)
- **Server latency**: 40-50ms total
- **Client latency**: 10-15ms total
- **Bandwidth**: 20-30 Mbps
- **No frame drops**

### Performance Issues

**Low FPS:**
- Check CPU usage on server
- Reduce resolution or quality
- Verify hardware acceleration

**High Encode Latency (>50ms):**
- Lower JPEG quality
- Reduce resolution
- Check CPU load

**High Decode Latency (>15ms):**
- Android device CPU overloaded
- Try different JPEG decoder
- Reduce frame complexity

**High Bandwidth (>40 Mbps):**
- Lower JPEG quality
- Reduce resolution
- Check network capacity

## Optimization Tips

### Reduce Latency
1. Lower JPEG quality (trade quality for speed)
2. Reduce resolution if acceptable
3. Use hardware-accelerated encoding/decoding
4. Minimize other background processes

### Reduce Bandwidth
1. Lower JPEG quality setting
2. Reduce frame rate if motion is smooth enough
3. Use more aggressive compression

### Improve FPS Stability
1. Ensure consistent frame timing on server
2. Use dedicated GPU if available
3. Monitor for thermal throttling
4. Close unnecessary applications

## Testing Performance

### Basic Test
1. Start VR app (broadcasts discovery)
2. Start launcher with mode
3. Check VR box, load mode, Launch
4. Watch console for server stats (every 60 frames)
5. Run `adb logcat` for client stats

### Stress Test
1. Run for extended period (5+ minutes)
2. Monitor for performance degradation
3. Check thermal throttling
4. Verify no memory leaks

### Network Test
1. Test on different networks (WiFi vs. wired)
2. Monitor bandwidth usage
3. Check for packet loss
4. Test with network congestion

## Troubleshooting

### Server Stats Not Appearing
- Check logger configuration
- Verify streaming is active
- Look for errors in console

### Client Stats Not Appearing
- Check `adb logcat` output
- Verify app is receiving frames
- Look for exceptions in logcat

### Inconsistent FPS
- Check for frame drops
- Monitor CPU usage
- Look for thermal throttling
- Check for garbage collection pauses

### High Latency
- Profile individual components
- Check network conditions
- Verify no CPU throttling
- Consider resolution/quality reduction
