# MesmerGlass UI Overview

MesmerGlass is a **session-based** desktop overlay app. The main window uses **vertical tabs** and a standard **File menu** for creating/opening/saving `.session.json` files.

## Main tabs

### 🖥️ Display
Choose where MesmerGlass renders:

- Monitors (one or more)
- Wireless VR clients (auto-discovered on your LAN via UDP/5556)

If nothing appears when you start a session, this is the first tab to check.

### 🏠 Home (Session Runner)
“Mission control” for actually running your content:

- Session info (name, cue counts)
- SessionRunner controls (start/pause/stop/skip)
- Live preview (mirrors the compositor output)
- **Media Bank**: add folders containing images/videos/fonts for this session

### 📝 Cuelists
Browse and edit cue sequences inside the loaded session.

Use this tab to:
- Add/edit cues
- Set cue durations
- Configure per-cue audio tracks (hypno/background roles)

### 🎨 Playbacks
Browse and edit “playback definitions” inside the loaded session.

Playbacks define what gets rendered while cues run:
- Spiral parameters
- Media mode (images/videos/both)
- Text mode and cadence
- Zoom/acceleration parameters

### 🔗 Device
Optional Bluetooth device control via **MesmerIntiface** (built-in). This tab is for scanning/connecting devices and checking status.

### 📊 Performance
Frame timing / throughput views intended for debugging smoothness and VR streaming stability.

### 🛠️ DevTools
Placeholder in the current build.

## File menu

- **File → New Session**: start fresh
- **File → Open Session…**: load an existing `.session.json`
- **File → Save / Save As…**: persist edits
- **File → Import/Export Cuelist…**: move cuelists between sessions

## Keyboard shortcuts

Global playback controls:

- `Ctrl+Space`: play/resume
- `Ctrl+Shift+Space`: pause
- `Ctrl+Alt+Space`: stop
- `Ctrl+1`: exit
