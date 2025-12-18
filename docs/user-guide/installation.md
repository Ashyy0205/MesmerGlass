# Installation Guide

## Prerequisites

### Python Requirements
- Python 3.12 (64-bit) from [python.org](https://www.python.org/downloads/)
- Virtual environment setup
- pip and wheel packages

### System Requirements
- Windows 10/11
- 4GB RAM minimum (8GB recommended)
- OpenGL 2.0+ capable GPU
- DirectX 11+ for multi-monitor support

## Step-by-Step Installation

### 1. Python Installation
1. Download Python 3.12 (64-bit) from [python.org](https://www.python.org/downloads/)
2. Run installer
   - ✅ Check "Add python.exe to PATH"
   - ✅ Check "Create shortcuts for installed applications"
   - ✅ Check "Add Python to environment variables"

### 2. Virtual Environment Setup
```powershell
# Create virtual environment
py -3.12 -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and wheel
python -m pip install --upgrade pip wheel
```

### 3. Dependencies Installation

#### Method 1: Using requirements.txt
```powershell
pip install -r requirements.txt
```

#### Method 2: Manual Installation
```powershell
pip install pyqt6
pip install opencv-python
pip install av
pip install pygame
pip install websockets
pip install numpy
```

### 4. Device Integration (Optional)

MesmerGlass v1.0 includes **MesmerIntiface** (built-in Bluetooth device control). You can scan/connect devices directly from the **Device** tab.

### 5. Media Setup
1. Create directories:
   ```
   MesmerGlass/
   ├── media/
   │   ├── video/
   │   ├── audio/
   │   └── fonts/
   ```
2. Add your media files:
   - Videos: MP4, MOV, AVI formats supported
   - Audio: MP3, WAV, OGG formats supported
   - Fonts: TTF, OTF formats supported

## Troubleshooting Common Installation Issues

### Python PATH Issues
```powershell
# Check Python installation
py --version

# Check pip installation
py -3.12 -m pip --version

# Repair PATH if needed
py -3.12 -m ensurepip
```

### Virtual Environment Problems
```powershell
# Deactivate if active
deactivate

# Remove and recreate
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Dependency Installation Failures
```powershell
# Clear pip cache
pip cache purge

# Force reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

## Post-Installation Verification

### Test Environment
```powershell
# Activate environment
.\.venv\Scripts\Activate.ps1

# Run application
python -m mesmerglass run

# Run tests
python -m pytest
```

### Verify Features
1. Launch application
2. Test video playback
3. Test audio playback
4. Test device connection (if applicable)
5. Test multi-monitor support

## Updating

### Update Dependencies
```powershell
pip install --upgrade -r requirements.txt
```

### Update Application
```powershell
git pull
pip install -r requirements.txt
```
