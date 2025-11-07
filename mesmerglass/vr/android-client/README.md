# MesmerVisor Client (Android VR Receiver)

**App Name**: MesmerVisor Client  
**Package**: com.hypnotic.vrreceiver  
**Version**: 0.7

Android VR client for receiving and displaying hypnotic visuals from MesmerGlass in virtual reality.

## Features

- **Dual-Protocol Support**:
  - **VRH2** (H.264): GPU hardware decoding via MediaCodec (recommended)
  - **VRHP** (JPEG): CPU software decoding via BitmapFactory (fallback)
- **Automatic Protocol Detection**: Detects server protocol via magic bytes
- **Auto-Discovery**: Finds MesmerGlass server via UDP broadcast
- **Stereo VR Rendering**: Side-by-side rendering for VR headsets
- **Low Latency**: Hardware-accelerated decoding for minimal delay
- **Aspect Ratio Preservation**: Maintains 16:9 video aspect in VR viewport

## Supported Devices

- Oculus Quest / Quest 2 / Quest 3
- Oculus Go
- Google Cardboard (Android)
- Any Android device with VR support

## Requirements

- **Android Version**: 5.0 (Lollipop) or higher
- **OpenGL ES**: 3.0+
- **WiFi**: Same network as MesmerGlass server
- **Permissions**: INTERNET (granted automatically)

## Building

### Prerequisites

- Android Studio Hedgehog (2023.1.1) or later
- Android SDK API 21+ (minimum)
- Android SDK API 34+ (target)
- Gradle 8.0+

### Build Steps

1. Open project in Android Studio:
   ```bash
   cd mesmerglass/vr/android-client
   # Open in Android Studio
   ```

2. Sync Gradle dependencies:
   ```
   File → Sync Project with Gradle Files
   ```

3. Build APK:
   ```
   Build → Build Bundle(s) / APK(s) → Build APK(s)
   ```

4. APK location:
   ```
   app/build/outputs/apk/debug/app-debug.apk
   ```

### Command-Line Build

```bash
cd mesmerglass/vr/android-client

# Debug build
./gradlew assembleDebug

# Release build (requires signing)
./gradlew assembleRelease
```

## Installation

### Method 1: ADB (Development)

```bash
adb install app-debug.apk
```

### Method 2: SideQuest (Oculus)

1. Enable Developer Mode on Quest
2. Connect Quest via USB
3. Open SideQuest
4. Drag APK to SideQuest window
5. Launch from "Unknown Sources" in Quest library

### Method 3: File Transfer

1. Copy APK to device storage
2. Use a file manager app to install
3. Enable "Install from Unknown Sources" if prompted

## Usage

### Auto-Discovery Mode (Recommended)

1. **Start MesmerGlass server**:
   ```bash
   python -m mesmerglass vr-stream
   ```

2. **Launch VR app** on Android device

3. **Wait for auto-discovery**:
   - App broadcasts "VR_HEADSET_HELLO" on UDP port 5556
   - Server responds with TCP port 5555
   - Connection established automatically

4. **Streaming begins**:
   - Blue screen → Searching for server
   - Green screen → Server found, connecting
   - Black screen → Streaming active

### Manual Connection (Fallback)

If auto-discovery fails, check:

1. **Same WiFi network**: PC and VR device must be on same network
2. **Firewall rules**: Allow UDP 5556 and TCP 5555
3. **Server IP**: Note MesmerGlass server IP from console output

## Protocol Details

### VRH2 (H.264 Hardware)

**Magic Bytes**: `56 52 48 32` ("VRH2")

**Encoding**: NVENC H.264 GPU encoding

**Decoding**: MediaCodec hardware decoding

**Performance**:
- Latency: 10-20ms
- Bandwidth: 1-2 Mbps @ 30 FPS
- CPU Usage: <5%
- GPU Usage: <10%

**Advantages**:
- ✅ Ultra-low latency
- ✅ Minimal bandwidth
- ✅ Hardware accelerated
- ✅ No CPU overhead

**Requirements**:
- NVIDIA GPU on server (GTX 900+, RTX)
- Android MediaCodec H.264 support (most modern devices)

### VRHP (JPEG Software)

**Magic Bytes**: `56 52 48 50` ("VRHP")

**Encoding**: OpenCV JPEG CPU encoding

**Decoding**: BitmapFactory software decoding

**Performance**:
- Latency: 50-80ms
- Bandwidth: 10-20 Mbps @ 30 FPS
- CPU Usage: 10-15% (server), 5-10% (client)

**Advantages**:
- ✅ Universal compatibility
- ✅ Simple implementation
- ✅ Predictable quality

**Use Cases**:
- AMD/Intel GPU systems
- Testing/development
- Fallback mode

## Packet Format

### Header Structure (20 bytes)

```
Offset | Size | Type   | Field
-------|------|--------|-------------
0      | 4    | uint32 | Packet Size (big-endian)
4      | 4    | ASCII  | Magic ("VRH2" or "VRHP")
8      | 4    | uint32 | Frame ID
12     | 4    | uint32 | Left Eye Size
16     | 4    | uint32 | Right Eye Size
20     | N    | bytes  | Left Eye Data
20+N   | M    | bytes  | Right Eye Data
```

### Discovery Protocol (UDP)

**Client → Server (Broadcast to 255.255.255.255:5556)**:
```
VR_HEADSET_HELLO:<device_name>
```

**Server → Client (Unicast response)**:
```
VR_SERVER_INFO:<tcp_port>
```

## Troubleshooting

### Issue: "Searching for Server" Forever

**Solutions**:
1. Check WiFi connection (same network as PC)
2. Restart MesmerGlass server
3. Check firewall (allow UDP 5556, TCP 5555)
4. Try different WiFi band (2.4GHz vs 5GHz)

### Issue: Black Screen, No Video

**Solutions**:
1. Check MesmerGlass console for errors
2. Verify streaming is active (`vr-stream` command)
3. Check network bandwidth (ping server)
4. Restart VR app

### Issue: Choppy/Stuttering Video

**Solutions**:
1. Switch to 5GHz WiFi band
2. Move closer to router
3. Reduce FPS: `--fps 20`
4. Lower quality (JPEG only): `--quality 70`
5. Use NVENC if available (auto-detected)

### Issue: "Protocol: UNKNOWN"

**Solutions**:
1. Update MesmerGlass to latest version
2. Check server is using VRHP or VRH2 protocol
3. Verify packet format matches spec

### Issue: H.264 Decoder Init Failed

**Causes**:
- Device doesn't support H.264 hardware decoding
- MediaCodec not available on device

**Solutions**:
1. Server will auto-fallback to JPEG
2. Force JPEG mode: `--encoder jpeg`
3. Check Android version (need 5.0+)

## Development

### Project Structure

```
android-vr-receiver/
├── app/
│   ├── src/main/
│   │   ├── java/com/hypnotic/vrreceiver/
│   │   │   └── MainActivity.kt         # Main activity
│   │   ├── cpp/                        # Native code (if any)
│   │   ├── res/                        # Resources
│   │   └── AndroidManifest.xml
│   └── build.gradle                    # App-level Gradle
├── build.gradle                        # Project-level Gradle
└── settings.gradle
```

### Key Classes

- **MainActivity**: Main activity, GL renderer, frame processing
- **NetworkReceiver**: TCP streaming client, protocol detection
- **DiscoveryService**: UDP broadcast listener
- **StreamProtocol**: Enum for VRH2/VRHP/UNKNOWN

### Adding New Features

1. **Custom Shaders**: Edit `VERTEX_SHADER` / `FRAGMENT_SHADER` constants
2. **UI Overlays**: Add UI in `onDrawFrame()` after stereo rendering
3. **Settings**: Add SharedPreferences for user config
4. **Analytics**: Add frame rate counter, latency measurement

### Debugging

**Enable ADB Logging**:
```bash
adb logcat | grep -E "vrreceiver|MainActivity"
```

**Check Network Traffic**:
```bash
adb shell netstat | grep 5555
```

**Monitor Performance**:
```bash
adb shell dumpsys gfxinfo com.hypnotic.vrreceiver
```

## Performance Optimization

### Client-Side

1. **Use H.264**: Ensure MediaCodec is initialized successfully
2. **Reduce Resolution**: Lower res = less decode time
3. **Disable Vsync**: For minimum latency (may cause tearing)
4. **Close Background Apps**: Free up CPU/GPU resources

### Server-Side

1. **Use NVENC**: Enable GPU encoding
2. **Reduce FPS**: `--fps 30` or lower
3. **Lower Bitrate**: `--bitrate 1500000` (H.264 only)
4. **Disable Other Visuals**: Focus GPU on VR streaming

### Network

1. **5GHz WiFi**: Better throughput, less congestion
2. **QoS**: Prioritize streaming traffic on router
3. **Direct Connection**: Connect Quest to PC via WiFi hotspot
4. **Wired Backhaul**: Wire PC to router for stability

## Known Limitations

1. **H.264 Surface Output**: Currently not implemented (would enable zero-copy)
2. **Mono Rendering**: No true stereo parallax (both eyes see same image)
3. **No Head Tracking**: Passive display only (no 6DOF)
4. **Fixed Resolution**: 1920x1080 (not dynamic)
5. **No Audio**: Video only (no audio streaming)

## Future Enhancements

- [ ] H.264 MediaCodec surface rendering (zero-copy)
- [ ] True stereo parallax support (depth offset)
- [ ] Head tracking integration (Oculus SDK)
- [ ] Dynamic resolution scaling
- [ ] Audio streaming support
- [ ] Settings UI (quality, FPS, etc.)
- [ ] Frame rate/latency overlay
- [ ] Reconnection on disconnect
- [ ] Multiple server support

## License

Part of MesmerGlass project. See main repository for license details.

## Credits

- VR streaming architecture integrated into MesmerGlass
- Adapted for hypnotic visual system with VRHP protocol
- MediaCodec H.264 and JPEG software decoding
- Optimized for Oculus Go/Quest wireless streaming

---

**MesmerGlass VR Receiver v0.7**  
Compatible with MesmerGlass 0.7+  
Android 5.0+ (API 21+)
