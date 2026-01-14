# Installation Guide

MesmerGlass is primarily a **Python desktop app** (PyQt6 + OpenGL). Most users only need Python, a working GPU driver, and optional media folders.

## Prerequisites

### System requirements (recommended)

- Windows 10/11 (other OSes may work, but Windows is the main target)
- Python 3.12 (64-bit)
- A GPU/driver that supports OpenGL (for the compositor)

### Optional hardware

- Bluetooth LE adapter (only if you want device synchronization)
- VR headset(s) (only if you want VR Bridge or wireless streaming)

## Install (Windows)

From the repo root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Launch

```powershell
python -m mesmerglass run

# Legacy entry point (still supported)
python run.py
```

## Device control (optional)

MesmerGlass ships with **MesmerIntiface** (a built-in Bluetooth device server). In the GUI it is started automatically on `ws://127.0.0.1:12350`.

- You do **not** need Intiface Central for the default workflow.
- If you already use an external Buttplug server (e.g. Intiface Central), MesmerGlass can still interoperate via the Buttplug protocol.

## Media setup (images/videos/fonts)

MesmerGlass loads media via a per-session **Media Bank**.

1. Launch the app
2. **File → New Session** (or open an existing session)
3. Go to **Home → Media Bank**
4. **Add Directory** and classify it as `images`, `videos`, `both`, or `fonts`

These folders are saved into your `.session.json` file.

## Verify your install

```powershell
# Quick CLI smoke test (no UI)
python -m mesmerglass selftest

# Optional: run tests
python -m mesmerglass test-run fast
```

## Common install issues

### “Nothing renders” / black preview

- Update GPU drivers
- Ensure OpenGL is available on the machine (RDP/VMs can break this)
- Try running without VR flags first (`python -m mesmerglass run`)

### Bluetooth device not found

- Confirm the device supports BLE and is in pairing mode
- On Windows: ensure Bluetooth is enabled and the adapter is present
- Try the Device tab scan again after toggling Bluetooth
