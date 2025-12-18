# MesmerGlass Documentation

Welcome to the MesmerGlass documentation! This directory contains comprehensive guides for users and developers.

## 📚 Documentation Structure

### 📖 User Guide (`/user-guide/`)
Documentation for end users:
- **[Installation](user-guide/installation.md)** - Setup and installation instructions
- **[UI Overview](user-guide/ui-overview.md)** - Tour of the v1.0 tabs and workflow
- **[Features](user-guide/features.md)** - Overview of MesmerGlass features
- **[Device Management](user-guide/device-management.md)** - Managing connected devices
- **[VR Setup](user-guide/vr-setup.md)** - Wireless VR client setup (MesmerVisor)
- **[Custom Visual Modes](user-guide/custom-modes.md)** - Creating and loading custom visual modes
- **[Quick Start Visual](user-guide/quick-start-visual.md)** - Quick “get visuals on screen” walkthrough

## 🚀 Quick Start

1. **Launch the GUI**: `python -m mesmerglass run`
2. **New Users**: Start with [Installation](user-guide/installation.md)
3. **Learn the UI**: Read [UI Overview](user-guide/ui-overview.md)
4. **VR Streaming**: Start with [VR Setup](user-guide/vr-setup.md) (download the APK from release assets)

## 📝 Contributing

When adding new documentation:
- Place user-facing docs in `/user-guide/`
- Place development docs in `/development/`
- Place technical specs in `/technical/`
- Update this README with new document links

## 🆘 Support

If you need help:
1. Check the relevant documentation section
2. Open an issue on the project repository

## 📜 CLI Reference

- For detailed command-line interface documentation, refer to the [CLI Reference](cli.md)
- Launching the GUI via CLI: `python -m mesmerglass run`
- Quick example: measure a 90° sweep at 60 RPM deterministically
	- `python -m mesmerglass spiral-measure --rpm 60 --delta-deg 90 --mode director --ceil-frame --json`
- Logging flags (`--log-level`, `--log-file`, `--log-format`) may be specified either before or after the subcommand, so `python -m mesmerglass --log-level DEBUG run` and `python -m mesmerglass run --log-level DEBUG` are equivalent.
