# Quick Build Reference - MesmerVisor Client APK

**App Name**: MesmerVisor Client (renamed from "Hypnotic VR Receiver")  
**Status**: Code ready, APK build pending

---

## Fast Track (30 minutes)

### Step 1: Install Android Studio (10 min download + 5 min install)

1. Download: https://developer.android.com/studio
2. Run installer (accept defaults)
3. First launch downloads SDK (~5 GB)

### Step 2: Build APK (5 min)

```powershell
# Open Android Studio
# File → Open → Select: C:\Users\Ash\Desktop\MesmerGlass\mesmerglass\vr\android-client
# Wait for Gradle sync (5 min first time)
# Build → Build APK
```

### Step 3: Copy APK (instant)

```powershell
Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "..\..\MEDIA\vr-client\mesmervisor-client.apk"
```

### Step 4: Install on Quest (2 min)

**Via SideQuest** (easiest):
1. Install SideQuest: https://sidequestvr.com
2. Enable Developer Mode on Quest
3. Connect Quest via USB-C
4. Drag `mesmervisor-client.apk` to SideQuest
5. Launch from Library → Unknown Sources

**Via ADB** (if familiar):
```powershell
adb install -r MEDIA\vr-client\mesmervisor-client.apk
```

---

## Alternative: Command Line Build

**If you already have Android SDK**:

```powershell
cd C:\Users\Ash\Desktop\MesmerGlass\mesmerglass\vr\android-client

# Set SDK location (adjust path if needed)
$env:ANDROID_HOME = "C:\Users\$env:USERNAME\AppData\Local\Android\Sdk"

# Build
.\gradlew.bat assembleDebug

# Copy
Copy-Item "app\build\outputs\apk\debug\app-debug.apk" "..\..\MEDIA\vr-client\mesmervisor-client.apk"
```

---

## Expected Output

**APK Location**: `app\build\outputs\apk\debug\app-debug.apk`  
**APK Size**: ~10-15 MB (debug), ~5-8 MB (release)  
**App Name**: MesmerVisor Client  
**Package**: com.hypnotic.vrreceiver  
**Version**: 1.0

---

## Verify It Worked

```powershell
# Check APK info
adb shell pm list packages | Select-String "hypnotic"
# Expected: package:com.hypnotic.vrreceiver

# Launch app
adb shell am start -n com.hypnotic.vrreceiver/.MainActivity

# In VR headset:
# Library → Unknown Sources → "MesmerVisor Client" (should show new name)
```

---

## Common Errors

**"SDK location not found"**:
```powershell
# Install Android Studio (includes SDK)
# OR set ANDROID_HOME manually:
$env:ANDROID_HOME = "C:\Users\$env:USERNAME\AppData\Local\Android\Sdk"
```

**"Build tools not found"**:
```powershell
# In Android Studio:
# Tools → SDK Manager → SDK Tools → Android SDK Build-Tools → Install
```

**"ADB device not found"**:
- Enable USB Debugging on Quest (Settings → System → Developer)
- Allow USB debugging popup in headset
- Try different USB cable (must support data, not charge-only)

---

## Full Documentation

For detailed instructions, troubleshooting, and release builds:
- `BUILD_APK.md` (this folder) - Comprehensive build guide
- `../../MEDIA/vr-client/BUILD_INSTRUCTIONS.md` - Installation guide
- `../../MESMERVISOR_COMPLETE.md` - Full project summary

---

## Test VR Streaming

After installing APK:

```powershell
# On PC:
cd C:\Users\Ash\Desktop\MesmerGlass
python -m mesmerglass vr-stream

# In VR headset:
# Launch "MesmerVisor Client"
# Should auto-discover PC and start streaming
```

**Expected**: Spiral visuals streaming at 60 FPS (H.264) or 30 FPS (JPEG)

---

**Time Budget**: 30 min (with Android Studio) or 5 min (if SDK already installed)  
**Disk Space**: ~10 GB (Android Studio) or ~3 GB (SDK only)  
**Prerequisites**: Windows PowerShell, USB-C cable, Oculus Quest (or compatible VR headset)

---

**Quick Start**: Install Android Studio → Open project → Build APK → Done
