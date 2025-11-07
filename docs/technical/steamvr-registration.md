# SteamVR Application Registration Guide

## The Problem

SteamVR's OpenXR runtime requires applications to be registered with a specific executable path. When running MesmerGlass directly via `python.exe`, SteamVR:

1. ✅ Accepts all frames and renders correctly
2. ✅ Creates valid OpenXR session
3. ❌ **Refuses to exit loading screen** because `python.exe` isn't a registered SteamVR app
4. ❌ Generates error: `VRInitError_Init_Retry` and quits after timeout

The solution: Create a registered launcher executable that SteamVR recognizes.

---

## Solution 1: Compiled Launcher (Recommended)

### Step 1: Build the Launcher

Run the build script to create `mesmerglass_launcher.exe`:

```powershell
.\build_launcher.ps1
```

This creates a standalone executable that SteamVR can register.

### Step 2: Register with SteamVR

1. **Open SteamVR Settings**
   - Click SteamVR menu (top left) → Settings
   - Or right-click SteamVR tray icon → Settings

2. **Add Application Manifest**
   - Go to: **Developer** tab
   - Click: **Add Application Manifest**
   - Browse to: `C:\Users\Ash\Desktop\MesmerGlass\mesmerglass.vrmanifest`
   - Click **Open**

3. **Verify Registration**
   - You should see "MesmerGlass - OpenXR VR Hypnosis" in the app list
   - Status should show as registered

### Step 3: Launch MesmerGlass

**Option A: Via SteamVR Dashboard**
- Open SteamVR Dashboard (press System button on controller)
- Go to Library
- Select "MesmerGlass"
- Click Launch

**Option B: Direct Launch**
```powershell
.\mesmerglass_launcher.exe
```

**Option C: With Arguments**
```powershell
.\mesmerglass_launcher.exe vr-selftest
```

---

## Solution 2: Batch File (Quick Alternative)

If you don't want to compile an .exe, use the batch file:

### Step 1: Update Manifest

Edit `mesmerglass.vrmanifest` and change:
```json
"binary_path_windows": "C:\\Users\\Ash\\Desktop\\MesmerGlass\\mesmerglass_launcher.bat"
```

### Step 2: Register with SteamVR

Follow the same registration steps as Solution 1, Step 2.

### Step 3: Launch

Double-click `mesmerglass_launcher.bat` or launch from SteamVR.

---

## Solution 3: Switch to ALVR Runtime (Testing Only)

For quick testing without registration:

1. **Set ALVR as Active OpenXR Runtime**
   ```powershell
   # In SteamVR Settings → Developer
   # "Set OpenXR Runtime" → Choose ALVR
   ```

2. **Restart SteamVR and ALVR**

3. **Run Directly via Python**
   ```powershell
   .\.venv\Scripts\python.exe -m mesmerglass vr-selftest
   ```

ALVR's runtime doesn't require app registration, so the loading screen will exit immediately.

**Note**: This bypasses SteamVR features like overlays and advanced tracking.

---

## Verification

After registering the app, check that:

### In SteamVR Logs (`vrserver.txt`)
**BEFORE (Broken)**:
```
[Error] - [Input] LoadActionManifest failed. Could not find action manifest for app '...'
Refusing because app start error VRInitError_Init_Retry
```

**AFTER (Fixed)**:
```
[Info] - [Input] Successfully loaded action manifest for mesmerglass
Starting scene application: mesmerglass
```

### In VR Headset
- ✅ **Loading screen exits** within 1-2 seconds
- ✅ **Solid color rendering visible** (green/magenta test pattern)
- ✅ **No grid environment** after app starts

---

## Troubleshooting

### "Application not found in SteamVR Library"
- Ensure manifest is registered: SteamVR Settings → Developer → Application Manifests
- Check that `binary_path_windows` points to the correct absolute path
- Restart SteamVR after registering

### "Still stuck on loading screen"
- Verify the .exe or .bat actually launches MesmerGlass (check console output)
- Check SteamVR logs for `VRInitError` messages
- Try Solution 3 (ALVR runtime) to confirm rendering works

### "PyInstaller not found"
```powershell
.\.venv\Scripts\pip install pyinstaller
```

### "Icon file not found"
The build script looks for `MEDIA\Images\icon.ico`. If it doesn't exist:
- Remove the `--icon` line from `build_launcher.ps1`
- Or create a simple icon file

---

## Technical Details

### Why This Is Needed

SteamVR identifies OpenXR apps by their **executable path**. When you run:
```
python.exe -m mesmerglass
```

SteamVR generates a dynamic key:
```
system.generated.openxr.mesmerglass.python.exe
```

But there's no registered app with that key, so SteamVR:
- Creates the OpenXR session ✅
- Accepts all frames ✅
- Composites them **under** the loading grid ❌
- Never transitions to "Scene Application" state ❌

By creating a dedicated launcher executable registered in `mesmerglass.vrmanifest`, SteamVR recognizes it as a legitimate application and immediately transitions to scene rendering.

### What Gets Registered

The `.vrmanifest` file tells SteamVR:
- **App Key**: `mesmerglass` (unique identifier)
- **Executable Path**: `mesmerglass_launcher.exe`
- **Action Manifest**: `actions.json` (input/controller bindings)
- **Display Name**: "MesmerGlass - OpenXR VR Hypnosis"

This is the same mechanism used by all VR games and applications.

---

## Next Steps After Registration

Once MesmerGlass is registered and launching properly:

1. **Test with real content**
   ```powershell
   .\mesmerglass_launcher.exe
   ```

2. **Integrate actual visuals**
   - The current test renders solid colors
   - Replace with spiral rendering from your main app

3. **Add controller support**
   - Expand `actions.json` with button/trigger actions
   - Implement input handling in `vr_bridge.py`

4. **Create desktop overlay mode**
   - Can use same launcher with different arguments
   - SteamVR supports dashboard overlays via manifest

---

## Summary

| Method                   | Pros                                  | Cons                            | Loading Screen Fix |
| ------------------------ | ------------------------------------- | ------------------------------- | ------------------ |
| Compiled .exe launcher   | ✅ Full SteamVR integration            | Requires PyInstaller            | ✅ Yes              |
| Batch file launcher      | ✅ No compilation needed               | Less professional               | ✅ Yes              |
| ALVR runtime             | ✅ Quick testing, no registration      | ❌ Loses SteamVR features        | ✅ Yes              |
| Direct python.exe        | ✅ Simple development                  | ❌ **Loading screen never exits** | ❌ No               |

**Recommended**: Use the compiled launcher for production, ALVR runtime for quick testing during development.
