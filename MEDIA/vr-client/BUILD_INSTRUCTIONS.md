# MesmerVisor Client APK Build Instructions

## App Name Updated

The Android VR receiver has been renamed to **"MesmerVisor Client"** (previously "Hypnotic VR Receiver").

Changes include:
- ✅ Updated app name in `strings.xml`
- ✅ Added MediaCodec H.264 hardware decoding
- ✅ Protocol auto-detection (VRH2 vs VRHP)
- ✅ Toast notifications for protocol detection

## Prerequisites

You need Android SDK installed. Choose one option:

### Option 1: Android Studio (Recommended)

**Download**: https://developer.android.com/studio

**Why?** Includes everything: SDK, build tools, emulator, debugger.

**Installation**:
1. Download Android Studio installer
2. Run installer (default options are fine)
3. First launch will download SDK (~5 GB)
4. Wait for initial setup to complete

### Option 2: SDK Command-line Tools

**Download**: https://developer.android.com/studio#command-tools

**Why?** Smaller download if you only need to build APKs.

**Installation**:
1. Extract to `C:\Android\Sdk\cmdline-tools\latest\`
2. Set ANDROID_HOME: `$env:ANDROID_HOME = "C:\Android\Sdk"`
3. Add to PATH: `$env:PATH += ";C:\Android\Sdk\cmdline-tools\latest\bin"`
4. Accept licenses: `sdkmanager --licenses`
5. Install build tools:
   ```powershell
   sdkmanager "platforms;android-34" "build-tools;34.0.0"
   ```

## Build Instructions

### Method A: Android Studio (GUI)

1. **Open Project**:
   ```
   Open Android Studio
   → File → Open
   → Navigate to: MesmerGlass\mesmerglass\vr\android-client
   → Click OK
   ```

2. **Wait for Gradle Sync**:
   - First time: 5-10 minutes (downloads dependencies)
   - Status shown in bottom panel
   - Wait until "Gradle sync finished" appears

3. **Build APK**:
   ```
   Build → Build Bundle(s) / APK(s) → Build APK(s)
   ```
   OR
   ```
   Build → Build APK
   ```

4. **Locate APK**:
   - Click "locate" in notification bubble
   - Or navigate manually:
     ```
     mesmerglass\vr\android-client\app\build\outputs\apk\debug\app-debug.apk
     ```

5. **Copy to Distribution** (PowerShell):
   ```powershell
   cd MesmerGlass
   Copy-Item "mesmerglass\vr\android-client\app\build\outputs\apk\debug\app-debug.apk" "MEDIA\vr-client\MesmerGlass-VR-Client.apk"
   ```

### Method B: Command Line (Gradle)

1. **Set SDK Location** (if not set globally):
   ```powershell
   cd MesmerGlass\mesmerglass\vr\android-client
   
   # Option 1: Environment variable
   $env:ANDROID_HOME = "C:\Users\$env:USERNAME\AppData\Local\Android\Sdk"
   
   # Option 2: local.properties file
   "sdk.dir=C:\\Users\\$env:USERNAME\\AppData\\Local\\Android\\Sdk" | Out-File -FilePath "local.properties" -Encoding ASCII
   ```

2. **Build APK**:
   ```powershell
   .\gradlew.bat assembleDebug
   ```

3. **Copy to Distribution**:
   ```powershell
   Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "..\..\MEDIA\vr-client\mesmervisor-client.apk"
   ```

## Build Output

**APK Details**:
- **Filename**: `app-debug.apk` (or `mesmervisor-client.apk` after copying)
- **Size**: ~10-15 MB (debug), ~5-8 MB (release)
- **Package**: `com.hypnotic.vrreceiver`
- **App Name**: MesmerVisor Client
- **Version**: 1.0
- **Min SDK**: Android 5.0 (API 21)
- **Target SDK**: Android 14 (API 34)

## Installation on VR Device

### Method 1: ADB over USB

```powershell
# Enable Developer Mode and USB Debugging on device
# Connect device via USB

adb devices  # Verify device appears
adb install -r MEDIA\vr-client\mesmervisor-client.apk
```

**Note**: `-r` flag reinstalls if already installed (preserves data)

### Method 2: SideQuest (Oculus Quest)

1. **Install SideQuest**: https://sidequestvr.com/setup-howto
2. **Enable Developer Mode** on Quest:
   - Open Oculus app on phone
   - Settings → [Your Device] → Developer Mode → Enable
3. **Connect Quest** via USB-C cable
4. **Open SideQuest** on PC
5. **Allow USB debugging** on Quest (popup in headset)
6. **Install APK**:
   - Drag `mesmervisor-client.apk` to SideQuest window
   - Or click "Install APK from folder" button
7. **Launch**:
   - In Quest: Library → Unknown Sources → MesmerVisor Client

### Method 3: Wireless ADB

```powershell
# Get device IP: Quest Settings → Wi-Fi → [Your Network] → Advanced
# Enable ADB over network (requires USB connection first):
adb tcpip 5555

# Disconnect USB, then connect wirelessly:
adb connect <QUEST_IP>:5555

# Install APK:
adb install -r MEDIA\vr-client\mesmervisor-client.apk
```

## Verification

### Check Installation

```powershell
# List installed packages
adb shell pm list packages | Select-String "hypnotic"
# Expected output: package:com.hypnotic.vrreceiver

# Get package info
adb shell dumpsys package com.hypnotic.vrreceiver | Select-String "versionName"
# Expected output: versionName=1.0
```

### Launch App

```powershell
# Launch from command line
adb shell am start -n com.hypnotic.vrreceiver/.MainActivity

# Or launch from VR headset:
# Library → Unknown Sources → MesmerVisor Client
```

## Troubleshooting

### SDK Location Not Found

**Error**:
```
SDK location not found. Define a valid SDK location with an ANDROID_HOME 
environment variable or by setting the sdk.dir path in your project's 
local properties file
```

**Solution**:
```powershell
# Check if ANDROID_HOME is set
$env:ANDROID_HOME

# If empty, set it (adjust path for your installation):
$env:ANDROID_HOME = "C:\Users\$env:USERNAME\AppData\Local\Android\Sdk"

# Or create local.properties:
"sdk.dir=C:\\Users\\$env:USERNAME\\AppData\\Local\\Android\\Sdk" | Out-File -FilePath "mesmerglass\vr\android-client\local.properties" -Encoding ASCII
```

### Gradle Build Failed

**Error**: Various Gradle errors

**Solution**:
```powershell
cd mesmerglass\vr\android-client

# Clean build cache
.\gradlew.bat clean

# Re-download dependencies
.\gradlew.bat --refresh-dependencies

# Build again
.\gradlew.bat assembleDebug
```

### Build Tools Not Found

**Error**: `Android SDK Build Tools X.X.X not installed`

**Solution**:
```powershell
# List installed SDK packages
sdkmanager --list_installed

# Install missing build tools
sdkmanager "build-tools;34.0.0"
```

### ADB Device Not Found

**Error**: `adb: no devices/emulators found`

**Solution**:
1. **Enable USB Debugging** on device:
   - Oculus Quest: Settings → System → Developer → USB Connection Dialog → Enable
2. **Allow USB Debugging** popup in headset
3. **Restart ADB**:
   ```powershell
   adb kill-server
   adb start-server
   adb devices
   ```
4. **Check USB cable**: Must be data cable, not charge-only

### App Not Appearing in Quest

**Solution**:
- Check **Library → Unknown Sources** (not in main library)
- Reinstall with `-r` flag: `adb install -r mesmervisor-client.apk`
- Check logs: `adb logcat | Select-String "hypnotic"`

### App Crashes on Launch

**Debug**:
```powershell
# Clear app data
adb shell pm clear com.hypnotic.vrreceiver

# Check logcat for errors
adb logcat -c  # Clear log
adb shell am start -n com.hypnotic.vrreceiver/.MainActivity
adb logcat | Select-String "AndroidRuntime"
```

## Release Build (Production)

For production deployment, build a signed release APK:

### 1. Create Keystore

```powershell
cd mesmerglass\vr\android-client

keytool -genkeypair -v `
  -keystore mesmervisor-release-key.jks `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000 `
  -alias mesmervisor-key
```

**Important**: Save keystore password securely!

### 2. Configure Signing

Create `keystore.properties`:
```properties
storeFile=mesmervisor-release-key.jks
storePassword=YOUR_STORE_PASSWORD
keyAlias=mesmervisor-key
keyPassword=YOUR_KEY_PASSWORD
```

Update `app/build.gradle`:
```gradle
android {
    signingConfigs {
        release {
            def keystorePropertiesFile = rootProject.file("keystore.properties")
            def keystoreProperties = new Properties()
            keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
            
            storeFile file(keystoreProperties['storeFile'])
            storePassword keystoreProperties['storePassword']
            keyAlias keystoreProperties['keyAlias']
            keyPassword keystoreProperties['keyPassword']
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}
```

### 3. Build Release APK

```powershell
.\gradlew.bat assembleRelease
```

Output: `app\build\outputs\apk\release\app-release.apk`

### 4. Verify Signature

```powershell
# Check APK signature
jarsigner -verify -verbose -certs app\build\outputs\apk\release\app-release.apk

# Expected: "jar verified"
```

## Version Management

To update app version:

1. **Edit** `app/build.gradle`:
   ```gradle
   android {
       defaultConfig {
           versionCode 2         // Increment for each release
           versionName "1.1"     // Semantic version
       }
   }
   ```

2. **Rebuild APK**

3. **Update** distribution folder:
   ```powershell
   Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "..\..\MEDIA\vr-client\mesmervisor-client-v1.1.apk"
   ```

## Distribution Checklist

Before distributing APK:

- [ ] App name shows "MesmerVisor Client" (not "Hypnotic VR Receiver")
- [ ] Version number incremented
- [ ] H.264 support tested on target device
- [ ] JPEG fallback tested (if H.264 unavailable)
- [ ] Auto-discovery tested on local network
- [ ] Toast notifications working (protocol detection)
- [ ] Performance tested (60+ FPS streaming)
- [ ] Signed with release keystore (for production)
- [ ] README.md updated with version info
- [ ] Change log created

## Support

**Build Issues**:
- See detailed guide: `mesmerglass/vr/android-client/BUILD_APK.md`
- Check Gradle logs for specific errors
- Verify Android SDK installation

**Installation Issues**:
- Enable Developer Mode on VR device
- Check USB debugging is enabled
- Use SideQuest for easier installation

**Runtime Issues**:
- Check network connectivity (PC and VR on same network)
- Verify MesmerVisor server running: `python -m mesmerglass vr-stream`
- Check firewall settings (allow TCP 8765, UDP 8766)

---

**Last Updated**: January 2025  
**App Version**: 1.0  
**Target Devices**: Oculus Quest 1/2/3, Quest Pro, Pico 4, any Android VR device with OpenGL ES 3.0+
