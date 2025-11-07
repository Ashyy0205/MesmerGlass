# VR Client Distribution

This folder contains the Android VR client APK for MesmerGlass VR streaming.

## Files

- `mesmerglass-vr-receiver.apk` - Android VR client application
- `README.md` - Installation and usage instructions (this file)

## Quick Start

### 1. Install APK on Android VR Device

**Method A: ADB (Recommended for Developers)**
```bash
adb install mesmerglass-vr-receiver.apk
```

**Method B: SideQuest (Recommended for Oculus Quest)**
1. Enable Developer Mode on Quest
2. Connect Quest to PC via USB
3. Open SideQuest application
4. Drag `mesmerglass-vr-receiver.apk` to SideQuest window
5. Launch from "Unknown Sources" in Quest library

**Method C: Manual Transfer**
1. Copy APK to device via USB or cloud storage
2. Use file manager app on device to open APK
3. Enable "Install from Unknown Sources" if prompted
4. Follow installation prompts

### 2. Start MesmerGlass VR Streaming

On your PC, run:
```bash
# Auto-detect encoder (NVENC or JPEG)
python -m mesmerglass vr-stream

# Force NVENC H.264 (best performance)
python -m mesmerglass vr-stream --encoder nvenc --fps 30

# Force JPEG (optimized for Oculus Go/Quest)
python -m mesmerglass vr-stream --encoder jpeg --quality 25
```

### 3. Launch VR App

1. Put on VR headset
2. Go to "Unknown Sources" or "Library"
3. Launch "MesmerGlass VR Receiver"
4. Wait for auto-discovery (blue → green → black screen)
5. Enjoy hypnotic visuals in VR!

## Protocol Support

The VR client automatically detects and supports both streaming protocols:

### VRH2 (H.264 Hardware) - Recommended
- **Server**: Requires NVIDIA GPU (GTX 900+, RTX)
- **Client**: Android 5.0+ with MediaCodec support
- **Latency**: 10-20ms
- **Bandwidth**: 1-2 Mbps @ 30 FPS
- **Quality**: Excellent with motion compensation

### VRHP (JPEG Software) - Fallback
- **Server**: Any GPU (AMD, Intel, NVIDIA)
- **Client**: Any Android device
- **Latency**: 50-80ms
- **Bandwidth**: 10-20 Mbps @ 30 FPS
- **Quality**: Excellent, but higher bandwidth

## Network Requirements

- **WiFi**: 5GHz recommended (2.4GHz works but higher latency)
- **Same Network**: PC and VR device must be on same WiFi
- **Firewall**: Allow UDP 5556 and TCP 5555
- **Bandwidth**: 2 Mbps minimum (H.264), 20 Mbps minimum (JPEG)

## Troubleshooting

### Can't Find Server

1. **Check WiFi**: Ensure PC and VR device on same network
2. **Check Firewall**: 
   ```bash
   # Windows PowerShell
   netsh advfirewall firewall add rule name="MesmerVisor UDP" dir=in action=allow protocol=UDP localport=5556
   netsh advfirewall firewall add rule name="MesmerVisor TCP" dir=in action=allow protocol=TCP localport=5555
   ```
3. **Check Server**: Verify MesmerGlass is running `vr-stream` command
4. **Check IP**: Note server IP from console, ping from VR device

### Choppy/Stuttering Video

1. **Switch to 5GHz WiFi**: Less congestion, better throughput
2. **Move Closer to Router**: Reduce signal interference
3. **Reduce FPS**: `--fps 20` for lower bandwidth
4. **Lower Quality** (JPEG only): `--quality 70`
5. **Use NVENC**: Auto-selected if available

### Black Screen, No Video

1. **Restart App**: Force close and relaunch
2. **Restart Server**: Stop and restart `vr-stream` command
3. **Check Console**: Look for errors in MesmerGlass terminal
4. **Check Protocol**: Should see "Protocol: H.264 (GPU)" or "Protocol: JPEG (CPU)"

### Audio Not Working

- **Note**: VR client currently supports video only (no audio streaming)
- Audio from PC will continue playing on PC speakers/headphones

## Building from Source

If you need to rebuild the APK:

1. Open Android Studio
2. Open project: `mesmerglass/vr/android-client/`
3. Build → Build Bundle(s) / APK(s) → Build APK(s)
4. APK location: `app/build/outputs/apk/debug/app-debug.apk`
5. Copy to this folder and rename to `MesmerGlass-VR-Client.apk`

Or via command line:
```bash
cd mesmerglass/vr/android-client
./gradlew assembleDebug
cp app/build/outputs/apk/debug/app-debug.apk ../../../MEDIA/vr-client/MesmerGlass-VR-Client.apk
```

## Technical Details

**App Package**: `com.hypnotic.vrreceiver`

**Permissions**: 
- INTERNET (auto-granted)

**OpenGL ES**: 3.0+

**Android Version**: 5.0+ (API 21+)

**Supported Devices**:
- Oculus Quest / Quest 2 / Quest 3
- Oculus Go
- Google Cardboard
- Any Android VR device

**Discovery Protocol**:
- UDP broadcast on port 5556
- Device sends: `VR_HEADSET_HELLO:<device_name>`
- Server responds: `VR_SERVER_INFO:<tcp_port>`

**Streaming Protocol**:
- TCP connection on port 5555
- Packet format: size(4) + magic(4) + frame_id(4) + left_size(4) + right_size(4) + left_data + right_data
- Magic bytes: `VRH2` (H.264) or `VRHP` (JPEG)

## Support

For issues or questions:
1. Check documentation: `docs/technical/mesmervisor.md`
2. Check logs: `adb logcat | grep vrreceiver`
3. File issue on GitHub repository

---

**MesmerGlass VR Client v0.7**  
Compatible with MesmerGlass 0.7+
