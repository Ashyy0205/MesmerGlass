# MesmerGlass Documentation

Welcome to the MesmerGlass documentation! This directory contains comprehensive guides for users and developers.

## 📚 Documentation Structure

### 📖 User Guide (`/user-guide/`)
Documentation for end users:
- **[Installation](user-guide/installation.md)** - Setup and installation instructions
- **[Features](user-guide/features.md)** - Overview of MesmerGlass features
- **[Device Management](user-guide/device-management.md)** - Managing connected devices
- **[Custom Visual Modes](user-guide/custom-modes.md)** - Creating and loading custom visual modes ✨NEW

### 🛠️ Development (`/development/`)
Documentation for developers:
- **[Development Setup](development/dev-setup.md)** - Setting up development environment
- **[Testing](development/testing.md)** - Running tests and validation
- **[MesmerIntiface Complete](development/mesmerintiface-complete.md)** - Technical implementation details
- **[BLE UUID Inspector](development/ble-inspector.md)** - Discover services & characteristics for new devices

### 🔧 Technical Reference (`/technical/`)
Technical specifications and architecture:
- **[Audio Engine](technical/audio-engine.md)** - Lead-window cue prefetch, async worker queue, Home tab warmup, and adaptive streaming fallback for oversized clips ✨UPDATED
- **[Cuelist Loading Progress](technical/cuelist-loading-progress.md)** - Modal progress dialog that surfaces audio prefetch status ✨NEW
- **[Video Engine](technical/video-engine.md)** - Video overlay system
- **[Device Control](technical/device-control.md)** - Device communication protocols
- **[UI Components](technical/ui-components.md)** - User interface architecture
- **[Cue Audio Layers](technical/cue-audio-layers.md)** - Dual-track hypno/background design, duration hints, CLI parity ✨NEW
- **[GUI Wireframes v2](technical/gui-wireframes-v2.md)** - Complete window layouts plus the new small-screen cue editor guidance ✨UPDATED
- **[Virtual Devices](technical/virtual-devices.md)** - Virtual device simulation
- **[CLI Interface](technical/cli-interface.md)** - Command line interface
- **[Logging Modes](technical/logging-modes.md)** - Preset verbosity levels, burst summaries, and trace filters ✨NEW
- **[Perf Tracing](technical/perf-tracing.md)** - PerfTracer spans, CLI diagnostics, and troubleshooting workflow ✨NEW
- **[Session Packs](technical/sessions.md)** - JSON message pack schema & usage
- **[Text Rendering](technical/text-rendering.md)** - Text display modes, virtual screen targeting, multi-display mirroring ✨UPDATED
- **[Spiral Overlay](technical/spiral-overlay.md)** - Spiral rendering system + LoomWindowCompositor diagnostics ✨UPDATED
- **[MesmerVisor](technical/mesmervisor.md)** - **VR streaming system with JPEG encoding optimized for Oculus Go/Quest** ✨NEW
- **[VR Performance Monitoring](technical/vr-performance-monitoring.md)** - FPS, latency, bandwidth tracking ✨NEW
- **[VR Streaming Integration](technical/vr-streaming-launcher-integration.md)** - Legacy launcher VR display integration ✨NEW
- **[VR Performance Quickstart](technical/vr-performance-quickstart.md)** - Quick guide to viewing VR stats ✨NEW
- **[VR Bridge](technical/vr-bridge.md)** - Head-locked VR streaming via OpenXR (with mock fallback) ✨NEW
- **[Spiral Speed Unification](technical/spiral-speed-unification.md)** - Unified speed system across applications ✨NEW
- **[Spiral Speed Quick Reference](technical/spiral-speed-quick-reference.md)** - Developer integration guide ✨NEW
- **[Unification Pattern Template](technical/unification-pattern-template.md)** - Template for creating unified systems ✨NEW

### 🩹 Fixes (`/fixes/`)
- **[Audio Prefetch Lag](fixes/audio-prefetch-lag.md)** - Async worker wait guard eliminates 1.7 s cue pauses ✨NEW
- **[Playback Pool Duration Enforcement](fixes/playback-pool-duration-fix.md)** - Legacy cues auto-promote to cycle switching so min/max durations work again ✨NEW

## 🚀 Quick Start

1. **Launch the GUI**: `python run.py` (or `python -m mesmerglass run --vr` if you need CLI flags). This opens the Phase 7 MainApplication.
2. **New Users**: Start with [Installation](user-guide/installation.md)
3. **Developers**: Begin with [Development Setup](development/dev-setup.md)
4. **Technical Details**: Explore the [Technical Reference](technical/)
5. **VR Streaming**: See [MesmerVisor](technical/mesmervisor.md) for VR setup (Android client: `mesmerglass/vr/android-client/`, APK: `MEDIA/vr-client/`)
6. **DevTools Page**: In the GUI, press Ctrl+Shift+D to open the DevTools page. It lets you spin up deterministic virtual toys without hardware and view their live intensity.

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

- For detailed command-line interface documentation, refer to the [CLI Reference](../docs/cli.md)
- Launching the GUI via CLI: `python run.py` or `python -m mesmerglass run`
- Quick example: measure a 90° sweep at 60 RPM deterministically
	- `python -m mesmerglass spiral-measure --rpm 60 --delta-deg 90 --mode director --ceil-frame --json`
- Logging flags (`--log-level`, `--log-file`, `--log-format`) may be specified either before or after the subcommand, so `python -m mesmerglass --log-level DEBUG run` and `python -m mesmerglass run --log-level DEBUG` are equivalent.
