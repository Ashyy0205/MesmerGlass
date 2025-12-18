# VR Setup Guide (MesmerVisor)

This guide covers the **wireless VR client** setup used by MesmerGlass v1.0.

MesmerGlass can stream visuals to a headset running the Android client (**MesmerVisor**). Headset discovery and connection are managed from the **Display** tab.

## Requirements

- A Windows PC running MesmerGlass
- A VR headset (or Android device) capable of installing APKs
- The PC and headset on the same Wi‑Fi network (recommended)

## Install the VR client (MesmerVisor)

1. Download `MesmerVisor.apk` from the MesmerGlass release assets (GitHub Releases)
2. Copy it to your headset / Android device
3. Install the APK
4. Launch **MesmerVisor**

Notes:
- If your headset requires “Unknown sources” / “Install unknown apps”, enable that in headset settings.
- See `MEDIA/vr-client/README.md` for build/install tips if you’re compiling the client yourself.

## Connect from MesmerGlass

1. Start MesmerGlass
2. Open the **Display** tab
3. In the **VR Devices (Wireless)** section:
   - Wait for your headset/device to appear (discovery)
   - Select it and connect
4. Once connected, choose the VR display target(s) the same way you would for monitors

If your headset doesn’t show up:
- Confirm the headset and PC are on the same network
- Try temporarily disabling “AP isolation” / “client isolation” on your router
- Restart MesmerVisor (and then refresh/re-scan in the Display tab)

## Firewall / Networking

- The first time you use wireless VR, Windows may prompt for firewall access. Allow it on **Private networks**.
- Prefer a strong 5GHz Wi‑Fi connection for stable streaming.

## Troubleshooting

- **Discovery never finds the headset**: verify same Wi‑Fi; restart both apps; check router client isolation.
- **Connect succeeds but video is laggy**: switch to 5GHz; reduce network load; move closer to router.
- **Connect fails immediately**: ensure Windows Firewall allowed access; try running MesmerGlass once as admin to accept prompts.


## Using Both Systems Simultaneously

You can use **both VR systems at the same time**:

1. Check **🥽 VR Bridge (Direct PC Headset)**
2. Check **📱 [Your Wireless Device]**
3. Check your **primary monitor**
4. Click **Launch**

Result:
- Desktop monitor shows spiral
- Direct PC headset renders spiral (low latency)
- Wireless Android headset streams spiral (over WiFi)

---

## Display Tab UI Reference

### Monitor Section
```
🖥️ \\.\DISPLAY1  1920x1080  [✓]  ← Primary monitor
🖥️ \\.\DISPLAY2  2560x1440  [ ]  ← Secondary monitor
────────────────────────────────
```

### VR Bridge Section
```
🥽 VR Bridge (Direct PC Headset)  [ ]
   Tooltip: Direct rendering to PC VR headset (Oculus, Vive, Index, WMR) 
            via OpenVR/OpenXR.
            Requires: SteamVR or Oculus software running with headset connected.
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

### Force-Enable VR Bridge
If you prefer environment variables over UI checkboxes:

```powershell
# Enable VR Bridge without UI checkbox
$env:MESMERGLASS_VR = "1"

# Choose backend (optional)
$env:MESMERGLASS_VR_BACKEND = "openvr"  # or "openxr" or "auto"

# Launch
.\.venv\Scripts\python.exe -m mesmerglass
```

**Note**: UI checkbox takes precedence over environment variable

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
# Run diagnostic tool
.\.venv\Scripts\python.exe scripts\vr_diagnostic.py

# Check for:
# - "VR Bridge is in MOCK MODE" = no headset detected
# - "VR BRIDGE IS ACTIVE!" = headset detected
```

### Test VR Streaming
```powershell
# Run diagnostic tool (scans for 10 seconds)
.\.venv\Scripts\python.exe scripts\vr_diagnostic.py

# Check for:
# - "FOUND X VR DEVICE(S)" = discovery working
# - Device name and IP listed
```

### Run Full Test Suite
```powershell
# Test all VR systems
.\.venv\Scripts\python.exe scripts\test_vr_integration.py

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


