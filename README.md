# MesmerGlass 🌟

**MesmerGlass** is a sophisticated desktop overlay application that creates hypnotic visual experiences with synchronized device control. Built with PyQt6, it provides real-time video effects, text animations, and seamless device synchronization through our pure Python **MesmerIntiface** system.

## ✨ Features

- **🎬 Video Overlay System** - Real-time video effects and overlays across multiple displays
- **📝 Text & Visual Effects** - Customizable text animations with hypnotic effects
- **🎮 Device Control** - Native Bluetooth device control without external dependencies
- **🎵 Audio Synchronization** - Audio-reactive effects and synchronization
- **🔧 Developer Tools** - Built-in debugging and testing tools
- **🖥️ Multi-Display Support** - Span effects across multiple monitors
- **🎯 Click-Through Interface** - Non-intrusive overlay that doesn't interfere with other applications

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

4. **Run MesmerGlass:**
   ```bash
   python run.py
   ```

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

## 🎯 Examples

Explore our example scripts in the [`examples/`](examples/) directory:

### Device Control
```bash
# Full MesmerIntiface demonstration
python examples/device_control/demo_mesmer_intiface.py

# Basic device testing
python examples/device_control/basic_device_test.py
```

### Testing & Validation
```bash
# Integration validation
python examples/testing/integration_validation.py
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
│   ├── ui/                        # User interface
│   └── tests/                     # Test suite
├── docs/                          # Documentation
│   ├── user-guide/               # User documentation
│   ├── development/              # Developer guides  
│   └── technical/                # Technical references
├── examples/                      # Example scripts
│   ├── device_control/           # Device control examples
│   └── testing/                  # Testing utilities
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
