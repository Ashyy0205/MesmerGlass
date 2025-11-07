# Building MesmerVisor Client APK

## Prerequisites

You need Android SDK installed. You have two options:

### Option 1: Android Studio (Recommended)

1. **Install Android Studio**: Download from https://developer.android.com/studio
2. **Open Project**: 
   - Open Android Studio
   - File → Open
   - Select: `C:\Users\Ash\Desktop\MesmerGlass\mesmerglass\vr\android-client`
3. **Sync Gradle**: Wait for Gradle sync to complete (may take 5-10 minutes first time)
4. **Build APK**:
   - Build → Build Bundle(s) / APK(s) → Build APK(s)
   - Or use menu: Build → Build APK
5. **Locate APK**:
   - Path: `app\build\outputs\apk\debug\app-debug.apk`
6. **Copy to Distribution**:
   ```powershell
   Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "..\..\MEDIA\vr-client\mesmervisor-client.apk"
   ```

### Option 2: Command Line (SDK Required)

If you have Android SDK installed separately:

1. **Set ANDROID_HOME**:
   ```powershell
   # Find your Android SDK location (usually in AppData\Local\Android\Sdk)
   $env:ANDROID_HOME = "C:\Users\Ash\AppData\Local\Android\Sdk"
   
   # Or create local.properties file:
   "sdk.dir=C:\\Users\\Ash\\AppData\\Local\\Android\\Sdk" | Out-File -FilePath "local.properties" -Encoding ASCII
   ```

2. **Build APK**:
   ```powershell
   cd mesmerglass\vr\android-client
   .\gradlew.bat assembleDebug
   ```

3. **Copy to Distribution**:
   ```powershell
   Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "..\..\MEDIA\vr-client\mesmervisor-client.apk"
   ```

## What Changed

The APK now includes:

- ✅ **App Name**: Changed from "Hypnotic VR Receiver" to "MesmerVisor Client"
- ✅ **H.264 Support**: MediaCodec hardware decoding for VRH2 protocol
- ✅ **Protocol Detection**: Auto-detects VRH2 (H.264) vs VRHP (JPEG)
- ✅ **JPEG Fallback**: BitmapFactory software decoding for compatibility
- ✅ **Toast Notifications**: Shows detected protocol on connection

## Build Output

**Expected Output**:
- **File**: `app\build\outputs\apk\debug\app-debug.apk`
- **Size**: ~10-15 MB (debug build)
- **Package**: `com.hypnotic.vrreceiver`
- **Version**: 1.0
- **Min SDK**: 21 (Android 5.0)
- **Target SDK**: 34 (Android 14)

## Installation

### Method 1: ADB (USB Debugging)

```powershell
# Enable USB debugging on Android device
# Connect via USB
adb devices  # Verify device connected
adb install -r MEDIA\vr-client\mesmervisor-client.apk
```

### Method 2: SideQuest (Oculus Quest)

1. Install SideQuest: https://sidequestvr.com/
2. Enable Developer Mode on Quest
3. Connect Quest via USB
4. Open SideQuest
5. Drag `mesmervisor-client.apk` to SideQuest window
6. Launch from "Unknown Sources" in Quest library

### Method 3: Wireless ADB

```powershell
# Get device IP from Settings → About → Status
adb connect <DEVICE_IP>:5555
adb install -r MEDIA\vr-client\mesmervisor-client.apk
```

## Verification

After building and installing:

```powershell
# Verify APK info
adb shell pm list packages | Select-String "hypnotic"
# Expected: package:com.hypnotic.vrreceiver

# Check app name
adb shell dumpsys package com.hypnotic.vrreceiver | Select-String -Pattern "applicationInfo"
```

## Troubleshooting

### SDK Not Found

**Error**: `SDK location not found`

**Solution 1**: Install Android Studio (includes SDK)

**Solution 2**: Download SDK standalone:
- Download SDK Command-line Tools: https://developer.android.com/studio#command-tools
- Extract to `C:\Android\Sdk`
- Set ANDROID_HOME environment variable
- Install build tools: `sdkmanager "build-tools;34.0.0" "platforms;android-34"`

### Gradle Build Failed

**Error**: `Could not resolve all dependencies`

**Solution**: 
- Check internet connection (Gradle downloads dependencies)
- Clear Gradle cache: `.\gradlew.bat clean`
- Try again: `.\gradlew.bat assembleDebug`

### Missing Build Tools

**Error**: `Failed to find Build Tools revision X.Y.Z`

**Solution**: 
- Open Android Studio
- Tools → SDK Manager
- SDK Tools tab → Check "Android SDK Build-Tools"
- Click "Apply" to install

## Release Build (Optional)

For a smaller, optimized APK:

1. **Generate Signing Key** (one-time):
   ```powershell
   keytool -genkey -v -keystore mesmervisor-release.keystore -alias mesmervisor -keyalg RSA -keysize 2048 -validity 10000
   ```

2. **Build Release APK**:
   ```powershell
   .\gradlew.bat assembleRelease
   ```

3. **Sign APK**:
   ```powershell
   jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 -keystore mesmervisor-release.keystore app\build\outputs\apk\release\app-release-unsigned.apk mesmervisor
   ```

4. **Optimize APK**:
   ```powershell
   zipalign -v 4 app\build\outputs\apk\release\app-release-unsigned.apk MEDIA\vr-client\mesmervisor-client-signed.apk
   ```

Release APK will be ~5-8 MB (ProGuard optimized).

## Next Steps

After building successfully:

1. ✅ Copy APK to `MEDIA\vr-client\mesmervisor-client.apk`
2. ✅ Install on VR device via ADB or SideQuest
3. ✅ Start MesmerGlass: `python -m mesmerglass vr-stream`
4. ✅ Launch "MesmerVisor Client" on VR device
5. ✅ Enjoy hypnotic visuals in VR!

---

**Note**: If you don't have Android SDK installed and don't want to install it, you can request a pre-built APK from someone who has the development environment set up, or use the existing "Hypnotic VR Receiver" APK (works with JPEG protocol only, but H.264 support requires rebuild).
