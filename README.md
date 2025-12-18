<img width="1024" height="1024" alt="mesmerglass_aperture_solar" src="https://github.com/user-attachments/assets/f95bcaf5-f21e-4364-bd93-c736410b545a" />

# MesmerGlass

**MesmerGlass** is a sophisticated desktop overlay application that creates hypnotic visual experiences with synchronized device control. Built with PyQt6, it provides real-time video effects (via the **MesmerLoom** visuals engine), text animations, and seamless device synchronization through our pure Python **MesmerIntiface** system.

## ✨ Features

- **🎬 MesmerLoom (visuals engine)** - Real-time video compositor & spiral overlay
- **📝 Text & Visual Effects** - Customizable text animations with hypnotic effects
- **🎮 Device Control** - Native Bluetooth device control without external dependencies
- **🎵 Audio Synchronization** - Audio-reactive effects and synchronization
- **🔧 Developer Tools** - Built-in debugging and testing tools
- **🖥️ Multi-Display Support** - Span effects across multiple monitors
- **🎯 Click-Through Interface** - Non-intrusive overlay that doesn't interfere with other applications
- **🌀 Spiral Overlay** - GPU-driven animated spiral composited over video with live UI controls (intensity, blend, parameters)
- **🥽 VR Streaming** - Stream to Oculus Go/Quest with optimized JPEG encoding (quality 25, ~60 Mbps, stable 20 FPS)

## 🚀 Quick Start

### Prerequisites
- **Windows 10/11, macOS, or Linux**
- **Python 3.12+** (64-bit)
- **Bluetooth LE support** (for device control)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Ashyy0205/MesmerGlass.git
   cd MesmerGlass
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv .venv

   # Windows
   .\.venv\Scripts\activate

   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run MesmerGlass:** (new unified CLI)
   ```bash
   python -m mesmerglass run
   ```
   Legacy: `python run.py` still works (deprecated; see docs/migration/run-py-deprecation.md).

## 🪟 Building a standalone Windows executable

You can bundle MesmerGlass (including Python and dependencies) into a portable folder using PyInstaller:

1. Ensure your virtual environment is active and install the build dependency:
   ```powershell
   pip install pyinstaller
   ```
2. Run the helper script:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/build_windows_exe.ps1 -Version 1.0.0
   ```

This creates `dist\MesmerGlass\MesmerGlass.exe` with the `mesmerglass_aperture_solar.ico` icon. Copy that folder to any Windows PC and run the `.exe` directly—no Python runtime required.

## 🎮 Device Control with MesmerIntiface

MesmerGlass includes **MesmerIntiface** - a pure Python implementation for direct Bluetooth device control:

### ✅ **No External Dependencies**
- No Rust compilation required
- No Intiface Central needed
- Direct Bluetooth LE communication

### 🔧 **Supported Devices**
- **Lovense**: Lush, Max, Nora, Edge, Hush, Domi, Calor
- **We-Vibe**: Sync, Pivot, Nova
- **Extensible** for additional manufacturers

### 📡 **Quick Device Setup**
1. Enable Bluetooth on your system
2. Put your device in pairing mode
3. In MesmerGlass: **Device Sync** → **Scan for devices**
4. Select your device and start your session!

## 📚 Documentation

### 📖 **User Guides**
- [📥 Installation Guide](docs/user-guide/installation.md) - Detailed setup instructions
- [⚡ Features Overview](docs/user-guide/features.md) - Complete feature walkthrough  
- [🎮 Device Management](docs/user-guide/device-management.md) - Device setup and control

### 🛠️ **Development**
- [🔧 Development Setup](docs/development/dev-setup.md) - Setup development environment
- [🧪 Testing Guide](docs/development/testing.md) - Running tests and validation
- [📋 MesmerIntiface Technical](docs/development/mesmerintiface-complete.md) - Implementation details

### 🔍 **Technical Reference**
- [🎵 Audio Engine](docs/technical/audio-engine.md) - Audio processing system
- [🎬 Video Engine](docs/technical/video-engine.md) - Video overlay architecture
- [📡 Device Control](docs/technical/device-control.md) - Communication protocols
- [🌀 Spiral Overlay](docs/technical/spiral-overlay.md) - MesmerLoom spiral parameters & rendering
- [🥽 VR Streaming (MesmerVisor)](docs/technical/mesmervisor.md) - VR streaming system with JPEG encoding optimized for Oculus Go/Quest
- [🛠 CLI Reference](docs/cli.md)

## 🧪 Testing

Run the comprehensive test suite to validate functionality:

### Quick Testing
```bash
# Run all tests (replaces run_tests.py)
python -m mesmerglass test-run

# Run only fast tests (excludes slow integration tests)
python -m mesmerglass test-run fast

# Verbose
python -m mesmerglass test-run -v

# With coverage
python -m mesmerglass test-run -c
```

### Test Categories
```bash
# Unit tests only
python -m mesmerglass test-run unit

# Integration tests
python -m mesmerglass test-run integration

# Bluetooth functionality tests
python -m mesmerglass test-run bluetooth

# Slow tests only
python -m mesmerglass test-run slow
```

### Manual Testing
```bash
# Test device control directly
python -m pytest mesmerglass/tests/test_device_control.py -v

# Test Bluetooth functionality
python -m pytest mesmerglass/tests/test_bluetooth.py -v
```

## 🏗️ Project Structure

```
MesmerGlass/
├── mesmerglass/                    # Main application code
│   ├── engine/                     # Core engines
│   │   ├── mesmerintiface/        # Pure Python device control
│   │   ├── audio.py               # Audio processing
│   │   ├── video.py               # Video overlay
│   │   └── pulse.py               # Device synchronization
│   ├── mesmervisor/               # VR streaming server (JPEG encoding)
│   ├── vr/                        # VR integration
│   │   └── android-client/        # Android VR client source code
│   ├── ui/                        # User interface
│   └── tests/                     # Comprehensive test suite
├── MEDIA/                         # Media assets
│   ├── vr-client/                 # Built VR APK for distribution
│   ├── Fonts/
│   ├── Images/
│   └── Videos/
├── docs/                          # Documentation
│   ├── user-guide/               # User documentation
│   ├── development/              # Developer guides  
│   └── technical/                # Technical references
├── run.py                         # Deprecated shim (use python -m mesmerglass)
└── requirements.txt              # Dependencies
```

## 🤝 Contributing

We welcome contributions! Please see our [development documentation](docs/development/) for:

- [Development Setup](docs/development/dev-setup.md)
- [Testing Guidelines](docs/development/testing.md)
- Code style and conventions

## 🛠️ System Requirements

### Minimum Requirements
- **OS**: Windows 10, macOS 10.15, or Linux (Ubuntu 20.04+)
- **Python**: 3.12 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **GPU**: DirectX 11/OpenGL 3.3 compatible

### For Device Control
- **Bluetooth LE**: Built-in or USB adapter
- **Supported Devices**: See [device compatibility](docs/user-guide/device-management.md)

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- 📖 **Documentation**: Start with our [user guides](docs/user-guide/)
- 🐛 **Issues**: Report bugs on [GitHub Issues](https://github.com/Ashyy0205/MesmerGlass/issues)
- 💬 **Discussions**: Join conversations in [GitHub Discussions](https://github.com/Ashyy0205/MesmerGlass/discussions)

---

**⚠️ Disclaimer**: MesmerGlass is designed for consensual adult use only. Always ensure proper consent and communication when using device control features.
