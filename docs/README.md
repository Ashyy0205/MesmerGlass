# MesmerGlass Documentation

Welcome to the MesmerGlass documentation.

If you’re new here: MesmerGlass is a **session-based** PyQt6/OpenGL visual compositor with optional device control and VR output/streaming.

## 📚 Documentation Structure

### 📖 User Guide (`/user-guide/`)
Documentation for end users:
- **[Installation](user-guide/installation.md)** - Setup and installation instructions
- **[UI Overview](user-guide/ui-overview.md)** - What each tab does (Display/Home/Cuelists/Playbacks/Device/Performance)
- **[Quick Start](user-guide/quick-start-visual.md)** - Create/open a session, configure Media Bank, run a cuelist
- **[Features](user-guide/features.md)** - Overview of MesmerGlass features
- **[Device Management](user-guide/device-management.md)** - Managing connected devices
- **[VR Setup](user-guide/vr-setup.md)** - Wireless VR (Display tab) and CLI VR flags
- **[Custom Modes](user-guide/custom-modes.md)** - How “modes” map to Playbacks in sessions

### 🛠️ Development (`/development/`)
Documentation for developers:
- **[Development Setup](development/dev-setup.md)** - Setting up development environment
- **[Testing](development/testing.md)** - Running tests and validation
- **[MesmerIntiface Complete](development/mesmerintiface-complete.md)** - Technical implementation details
- **[BLE UUID Inspector](development/ble-inspector.md)** - Discover services & characteristics for new devices

### 🔧 Technical Reference (`/technical/`)
Technical specifications and architecture:
- **[Audio Engine](technical/audio-engine.md)**
- **[Video Engine](technical/video-engine.md)**
- **[Device Control](technical/device-control.md)**
- **[CLI Interface](technical/cli-interface.md)**
- **[Spiral Overlay](technical/spiral-overlay.md)**
- **[VR Bridge](technical/vr-bridge.md)**
- **[MesmerVisor](technical/mesmervisor.md)**

### 🩹 Fixes (`/fixes/`)
- **[Audio Prefetch Lag](fixes/audio-prefetch-lag.md)** - Async worker wait guard eliminates 1.7 s cue pauses ✨NEW
- **[Playback Pool Duration Enforcement](fixes/playback-pool-duration-fix.md)** - Legacy cues auto-promote to cycle switching so min/max durations work again ✨NEW

## 🚀 Quick Start

1. **Launch the GUI**: `python -m mesmerglass run` (legacy: `python run.py`).
2. **New users**: Start with [Installation](user-guide/installation.md) and [Quick Start](user-guide/quick-start-visual.md)
3. **Developers**: Begin with [Development Setup](development/dev-setup.md)
4. **Technical details**: Browse the [Technical Reference](technical/)

## 📝 Contributing

When adding new documentation:
- Place user-facing docs in `/user-guide/`
- Place development docs in `/development/`
- Place technical specs in `/technical/`
- Update this README with new document links

## 🆘 Support

If you need help:
1. Check the relevant documentation section
2. Review [Testing](development/testing.md) for troubleshooting
3. Open an issue on the project repository

## 📜 CLI Reference

- For detailed command-line interface documentation, refer to the [CLI Reference](cli.md)
- Launching the GUI via CLI: `python -m mesmerglass run`
- Logging flags (`--log-level`, `--log-file`, `--log-format`) may be specified either before or after the subcommand.
