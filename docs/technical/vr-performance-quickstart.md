# Quick Start: VR Performance Monitoring

## Overview
The VR streaming system now includes comprehensive performance monitoring to track FPS, latency, bandwidth, and frame sizes.

## Viewing Performance Stats

### 1. Server-side Stats (Python Console)

**What it shows:**
- FPS (frames per second)
- Encode latency (JPEG compression time)
- Send latency (network transmission time)
- Bandwidth (Mbps)
- Frame sizes (left eye, right eye, total)

**How to view:**
Just run the launcher normally - stats appear in the console automatically every 60 frames:

```bash
./.venv/bin/python run.py
```

**Example output:**
```
📊 VR Performance Stats (Frame 60):
   FPS: 30.5 (window) | 30.2 (avg)
   Latency: 45.3ms (encode: 38.2ms, send: 7.1ms)
   Bandwidth: 25.34 Mbps
   Frame size: 105.2 KB (L: 52.6 KB, R: 52.6 KB)
```

### 2. Client-side Stats (Android VR Headset)

**What it shows:**
- Client FPS (frames rendered per second)
- Decode latency (JPEG decompression time)
- Render latency (OpenGL rendering time)
- Bandwidth (received data rate)
- Bytes received

**How to view:**
Use adb logcat while VR is streaming:

```powershell
# Windows PowerShell
& "C:\Users\Ash\AppData\Local\Android\Sdk\platform-tools\adb.exe" logcat | Select-String "VR Client Performance"

# Or use grep on Linux/Mac
adb logcat | grep "VR Client Performance"
```

**Example output:**
```
📊 VR Client Performance Stats (Frame 60):
   Client FPS: 30.1
   Latency: 12.3ms (decode: 8.5ms, render: 3.8ms)
   Bandwidth: 25.10 Mbps
   Bytes received: 6312 KB
```

## Quick Test Procedure

1. **Put on VR headset and start the VR app**
   - Should see blue "SEARCHING FOR SERVER" screen
   - App broadcasts UDP discovery packets

2. **Start launcher on PC**
   ```bash
   ./.venv/bin/python run.py
   ```

3. **Enable VR streaming**
   - Check "VR" box in launcher
   - Select a mode
   - Click "Launch"

4. **Open separate terminal for client stats (optional)**
   ```powershell
   & "C:\Users\Ash\AppData\Local\Android\Sdk\platform-tools\adb.exe" logcat | Select-String "VR Client Performance"
   ```

5. **Watch performance stats**
   - Server stats appear in launcher console
   - Client stats appear in adb logcat terminal
   - Stats update every 60 frames (~2 seconds at 30 FPS)

## What to Look For

### ✅ Good Performance (Oculus Go Optimized - Quality 25)
- **FPS**: 19-21 (stable around 20 FPS target achieved)
- **Server latency**: 94-96ms total (improved from 104-135ms)
- **Client latency**: 10-15ms total
- **Bandwidth**: 60-63 Mbps (73% reduction from quality 85)
- **Visual Quality**: Good and acceptable
- **Stats update regularly every ~3 seconds** (60 frames at 20 FPS)

### ⚠️ Performance Issues

**Low FPS (below 15):**
- Check CPU usage on PC
- Reduce mode complexity
- Close other applications

**High server encode latency (>100ms):**
- Network may be saturated
- Check WiFi signal strength
- Consider reducing complexity

**High client decode latency (>20ms):**
- VR headset CPU overloaded
- Close background apps on headset
- Reduce frame complexity

**High bandwidth (>80 Mbps):**
- Network may be saturated
- Check WiFi signal strength
- Verify quality 25 is active (default in launcher.py)

**Inconsistent FPS:**
- Check for thermal throttling
- Monitor network stability
- Look for background processes

### 📊 Optimization History

**Quality 85 (Initial)**: 230-340 Mbps, 10-18 FPS, 104-135ms latency ❌  
**Quality 50**: 130-160 Mbps, 18-19 FPS ⚠️  
**Quality 35**: 90-100 Mbps, 19-20 FPS ⚠️  
**Quality 25 (Current Default)**: **60-63 Mbps, 20-21 FPS, 94-96ms latency** ✅

## Troubleshooting

### "No stats appearing in console"
- ✅ Make sure VR checkbox is enabled
- ✅ Verify VR client is connected (should see green screen)
- ✅ Wait for 60 frames to elapse (~2 seconds)

### "Client stats not showing in logcat"
- ✅ Verify adb is connected: `adb devices`
- ✅ Check VR app is running and streaming
- ✅ Try filtering differently: `adb logcat *:I | Select-String "Client"`

### "Performance seems poor"
- Check thermal throttling on PC/headset
- Verify network connection (WiFi signal)
- Close unnecessary applications
- Try reducing mode complexity

## Advanced: Continuous Monitoring

### Monitor both server and client simultaneously

**Terminal 1 (Server stats):**
```bash
./.venv/bin/python run.py
```

**Terminal 2 (Client stats):**
```powershell
& "C:\Users\Ash\AppData\Local\Android\Sdk\platform-tools\adb.exe" logcat | Select-String "VR Client Performance"
```

### Save logs to file

**Server:**
Already logged to console, use PowerShell redirection:
```powershell
./.venv/bin/python run.py 2>&1 | Tee-Object -FilePath vr_server_log.txt
```

**Client:**
```powershell
& "C:\Users\Ash\AppData\Local\Android\Sdk\platform-tools\adb.exe" logcat | Select-String "VR Client" | Out-File -FilePath vr_client_log.txt
```

## Performance Metrics Reference

### Server-side (Encoding + Transmission) - Oculus Go Optimized

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| FPS | 19-21 | 17-19 | <17 |
| Encode latency | 90-100ms | 100-110ms | >110ms |
| Send latency | 5-10ms | 10-15ms | >15ms |
| Bandwidth | 60-65 Mbps | 65-75 Mbps | >80 Mbps |

### Client-side (Decoding + Rendering)

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Client FPS | 19-21 | 17-19 | <17 |
| Decode latency | 5-10ms | 10-15ms | >15ms |
| Render latency | 2-5ms | 5-10ms | >10ms |

### End-to-End Target (Quality 25)
**Total latency**: Server encode + send + client decode + render ~94-96ms ✅

Typical breakdown:
- Server encode: ~85ms
- Server send: ~9ms
- Client decode: 8ms
- Client render: 3ms
- **Total: ~105ms** (within acceptable range)

**Note**: Quality 25 is optimized for Oculus Go/Quest over WiFi, trading slightly higher latency for 73% bandwidth reduction and stable FPS.

## Next Steps

After monitoring performance:

1. **If performance is good**: Enjoy VR streaming! 🎉
2. **If latency is high**: Try reducing resolution or quality
3. **If FPS is low**: Check CPU/GPU load, close background apps
4. **If bandwidth is high**: Lower quality setting or frame rate

For detailed optimization guidance, see [docs/technical/vr-performance-monitoring.md](vr-performance-monitoring.md).
