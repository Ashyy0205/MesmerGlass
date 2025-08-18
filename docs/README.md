# MesmerGlass Documentation

## Overview
MesmerGlass is a sophisticated video overlay and device control application that synchronizes visual effects with connected devices.

## Features
- Real-time video overlay and effects
- Text and visual effect synchronization
- Device control via Buttplug protocol
- Virtual device testing support
- Developer mode with debugging tools
- CLI interface for testing and automation

## Quick Start
1. Installation:
   ```powershell
   # Clone the repository
   git clone https://github.com/Ashyy0205/MesmerGlass.git
   cd MesmerGlass

   # Create and activate virtual environment
   python -m venv .venv
   .\.venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt
   ```

2. Running the Application:
   ```powershell
   # Start GUI mode
   python run.py

   # Or use CLI mode
   python run.py --help
   ```

## Core Components
- [Video Engine](video-engine.md) - Handles video playback and effects
- [Audio Engine](audio-engine.md) - Processes audio input and synchronization
- [Device Control](device-control.md) - Manages device connections and commands
- [UI Components](ui-components.md) - User interface and control panels
- [CLI Interface](cli-interface.md) - Command-line tools and testing

## Development Guide
- [Setting Up Dev Environment](dev-setup.md)
- [Testing Guide](testing.md)
- [Virtual Device Testing](virtual-devices.md)
- [Contributing Guidelines](contributing.md)

## Usage Guides
- [Basic Usage](basic-usage.md)
- [Advanced Features](advanced-features.md)
- [Troubleshooting](troubleshooting.md)

## Support
For issues and feature requests, please use the [GitHub Issues](https://github.com/Ashyy0205/MesmerGlass/issues) page.
