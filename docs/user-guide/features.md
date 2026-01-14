# Features

MesmerGlass is a **session runner + realtime compositor**. Sessions are saved as `.session.json` and can be run either through the GUI or headlessly via CLI tools.

## Visuals (MesmerLoom)

- GPU-driven spiral rendering with configurable type/speed/opacity
- Media compositing:
  - Images (ThemeBank-driven cache + lookahead)
  - Videos (buffered streaming)
- Text overlays (synchronized with media cycles or on their own cadence)

## Sessions, cues, and playbacks

- **Playbacks**: reusable “render recipes” (spiral + media + text + zoom)
- **Cuelists**: ordered cues with durations and audio
- **Session Runner**: start/pause/stop/skip with a live preview

## Audio

- Multi-track audio roles (e.g. hypno/background)
- Looping, fades, and streaming fallback for oversized files

## Device synchronization (optional)

- Built-in Bluetooth device control via **MesmerIntiface** (no external server required)
- Buttplug protocol support for interoperability and testing

## VR options (optional)

- **VR Bridge**: head-locked VR via OpenXR (with mock fallback)
- **Wireless VR streaming (MesmerVisor)**: LAN discovery + TCP streaming to Android VR clients

## CLI automation + diagnostics

- `instructions` runner for deterministic repro scripts
- `themebank` readiness checks
- `cuelist` / `mode-verify` / `spiral-measure` tools for headless validation
