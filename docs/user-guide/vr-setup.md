# VR Display Setup Guide

## Overview

MesmerGlass supports two VR paths:

### 1. 🥽 VR Bridge (Direct PC Headset)
Head-locked VR output via OpenXR/OpenVR.

This is currently enabled via **CLI flags** when launching the app.

**Supported Headsets:**
- Meta Quest (with Link/Air Link)
- Valve Index
- HTC Vive / Vive Pro
- Windows Mixed Reality headsets
- Any SteamVR-compatible headset

### 2. 📱 VR Streaming (Wireless Android)
Stream visuals to Android VR devices over WiFi.

This is integrated into the GUI via the **Display** tab (it lists discovered wireless headsets).

**Supported Devices:**
- Meta Quest (via Android client app)
- Pico headsets
- Any Android-based VR headset

---

## Quick Start: Direct PC Headset (VR Bridge)

### Setup Steps

1. **Connect Your Headset**
   - Plug in your PC VR headset
   - Launch SteamVR or Oculus app
   - Ensure headset is detected and active

2. **Launch MesmerGlass with VR enabled**
   ```powershell
   python -m mesmerglass run --vr
   ```

3. **(Optional) Keep a desktop preview**
   - Also select a monitor in the **Display** tab

4. Start a session and run it from **Home** (or use whatever content your session contains).

### What You'll See

- **Desktop Monitor**: Spiral overlay (preview)
- **VR Headset**: Same spiral rendering directly
- **Logs**: `[vr] VR Bridge active - headset detected and ready!`

### Troubleshooting

**VR Bridge in mock mode / no headset detected**
- Ensure SteamVR (or your runtime) is running
- Check the headset is powered on and connected
- Try forcing a backend:
   - `python -m mesmerglass run --vr --vr-backend openvr`
   - `python -m mesmerglass run --vr --vr-backend openxr`

**Failed to connect VR bridge**
- Update graphics drivers
- Ensure no other app is using VR exclusively
- Check Windows firewall isn't blocking VR runtime

---

## Quick Start: Wireless VR (Streaming)

### Setup Steps

1. **Install Android VR Client** (on your headset)
   - Install MesmerGlass VR client app (APK in `/MEDIA/vr-client/`)
   - Ensure headset is on the same WiFi network as your PC

2. **Launch MesmerGlass** (on PC)
   ```powershell
   python -m mesmerglass run
   ```
   Discovery service starts automatically!

3. **Start VR Client** (on headset)
   - Open MesmerGlass VR client app
   - App broadcasts "VR_HEADSET_HELLO" on network

4. **Verify Discovery** (on PC)
   - Go to **Display** tab
   - Wait ~2 seconds
   - Device appears under **VR Devices (Wireless)**
   - Example: `📱 Pacific (192.168.1.57)`

5. **Enable Streaming**
   - Check your VR device in the list
   - Also check your primary monitor
   - Start a session and run it from **Home**

6. **Start Streaming**
   - Frames automatically stream to VR headset
   - Monitor shows desktop preview

### What You'll See

- **Desktop Monitor**: Spiral overlay (preview)
- **VR Headset**: Streamed visuals via H.264 (NVENC) or JPEG fallback
- **Display Tab**: Device listed with IP address
- **Auto-refresh**: List updates every 2 seconds

### Troubleshooting

**"No VR devices found"**
- Verify headset on same WiFi as PC
- Check VR client app is running
- Try manual refresh: Click **🔄 Refresh VR** button
- Ensure port 5556 isn't blocked by firewall

**"Device found but no stream"**
- Check WiFi signal strength
- Reduce other network traffic
- Verify the PC is on the same LAN and that ports are open (UDP 5556, TCP 5555)
- Check logs for streaming errors

---

## Using Both Systems Simultaneously

You can use **VR Bridge** (CLI `--vr`) and **Wireless VR streaming** (Display tab device selection) at the same time.

---

## Display Tab UI Reference

### Monitor Section
```
🖥️ \\.\DISPLAY1  1920x1080  [✓]  ← Primary monitor
🖥️ \\.\DISPLAY2  2560x1440  [ ]  ← Secondary monitor
────────────────────────────────
```

### Wireless VR Section
```
VR Devices (Wireless)
📱 Pacific (192.168.1.57)  [✓]  ← Android VR client
📱 Quest2 (192.168.1.102)  [ ]  ← Another device
```

### Quick Actions
```
[Select all] [Primary only] [🔄 Refresh VR]
```

---

## Environment Variables (Optional)

### Prefer CLI flags
VR options are easiest to manage via CLI flags:

```powershell
python -m mesmerglass run --vr
python -m mesmerglass run --vr --vr-backend openvr
python -m mesmerglass run --vr --vr-mock
python -m mesmerglass run --vr --vr-safe-mode
python -m mesmerglass run --vr --vr-minimal
```

### Other VR Flags
```powershell
# Force mock mode (testing without headset)
$env:MESMERGLASS_VR_MOCK = "1"

# Enable VR-safe compositor mode (offscreen FBO)
$env:MESMERGLASS_VR_SAFE = "1"

# Minimal VR mode (disable media/text subsystems)
$env:MESMERGLASS_VR_MINIMAL = "1"
```

---

## Backend Selection

VR Bridge supports two backends:

### OpenVR (Recommended)
- Native SteamVR integration
- Best compatibility with Valve Index, Vive
- Lower latency
- More stable

### OpenXR (Fallback)
- Cross-platform VR standard
- Better for WMR headsets
- Works when OpenVR unavailable

### Auto Mode (Default)
Tries OpenVR first, falls back to OpenXR, then mock mode.

**To force a backend:**
```powershell
$env:MESMERGLASS_VR_BACKEND = "openvr"  # or "openxr"
```

---

## Testing VR Setup

### Test VR Bridge
```powershell
python -m mesmerglass run --vr --vr-mock
```

### Test VR Streaming
You can validate the streaming server without launching the full GUI:

```powershell
# Start a streaming server and wait for clients
python -m mesmerglass vr-stream --encoder auto --fps 30

# Send a generated test pattern (useful for pipeline debugging)
python -m mesmerglass vr-test
```

### Run Full Test Suite
```powershell
python -m mesmerglass vr-selftest

# Test UI integration
.\.venv\Scripts\python.exe scripts\test_vr_bridge_ui.py
```

---

## Performance Tips

### VR Bridge (Direct Headset)
- **Target framerate**: Match headset refresh rate (90Hz/120Hz)
- **GPU load**: Direct rendering is efficient (same as monitor)
- **Latency**: < 5ms added overhead
- **Best for**: Maximum quality and responsiveness

### VR Streaming (Wireless)
- **Target framerate**: 60fps (network limited)
- **GPU load**: Encoding adds 10-20% overhead
- **Latency**: 20-50ms (WiFi dependent)
- **Best for**: Wireless freedom, multiple viewers

### Optimize Both
- Reduce spiral layer count for performance
- Lower resolution on non-VR displays
- Disable diagnostics in VR mode
- Use wired network for streaming when possible

---

## Comparison Table

| Feature | VR Bridge | VR Streaming |
|---------|-----------|--------------|
| **Latency** | < 5ms | 20-50ms |
| **Quality** | Native resolution | Compressed (H264/HEVC) |
| **Setup** | Wired headset required | WiFi only |
| **Compatibility** | PC VR headsets | Android VR devices |
| **GPU Cost** | Minimal | Encoding overhead |
| **Multiple Viewers** | Single headset | Multiple clients |
| **Discovery** | Automatic (SteamVR) | Network broadcast |
| **Display List** | ✅ UI checkbox | ✅ Auto-discovered |

---

## FAQ

### Q: Can I use both VR systems together?
**A:** Yes! Check both in the Display tab.

### Q: Does VR Bridge work without environment variables?
**A:** Yes! Just check it in the Display tab.

### Q: Why don't I see my PC VR headset in the device list?
**A:** VR Bridge doesn't show device details - just check the checkbox and it auto-detects your headset.

### Q: My wireless VR device isn't appearing
**A:** Ensure:
1. VR client app is running on headset
2. Headset on same WiFi as PC  
3. Click "🔄 Refresh VR" button
4. Check firewall allows UDP port 5556

### Q: Can I use VR without a desktop monitor?
**A:** Yes - just check VR Bridge or wireless device without checking monitors. However, you'll lose the desktop preview.

### Q: What's the difference between OpenVR and OpenXR?
**A:** OpenVR is SteamVR's native API (best for Valve/HTC). OpenXR is a cross-platform standard (best for WMR). Auto mode tries both.

### Q: Does this work with Meta Quest standalone mode?
**A:** Use **VR Streaming** for standalone. Use **VR Bridge** when Quest is connected to PC via Link/Air Link.

---

## Changelog

### November 19, 2025
- ✅ Added VR Bridge to Display tab UI
- ✅ Eliminated environment variable requirement
- ✅ Added tooltips and status indicators
- ✅ Improved headset detection logging
- ✅ Preserved backward compatibility with `MESMERGLASS_VR=1`
- ✅ Created test scripts for verification

---

## Support

**Logs Location**: Check terminal output for `[vr]` messages

**Test Scripts**:
- `scripts/vr_diagnostic.py` - Real-time status
- `scripts/test_vr_integration.py` - Full test suite
- `scripts/test_vr_bridge_ui.py` - UI integration tests

**Common Issues**: See Troubleshooting sections above

**Documentation**: `docs/technical/vr-*.md`
