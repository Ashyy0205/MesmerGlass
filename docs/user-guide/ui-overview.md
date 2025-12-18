# MesmerGlass UI Overview (v1.0)

MesmerGlass v1.0 is organized around **sessions** (a `.session.json` file) that contain:
- Playbacks (visual configurations)
- Cuelists (timed sequences of cues)
- Media bank entries (folders for images/videos/fonts)

The GUI is a vertical-tab layout. The key tabs are below.

## Tabs

### 🖥️ Display
Pick where visuals render:
- Select one or more **monitors**.
- Select any discovered **Wireless VR** devices (Android headset app) under “VR Devices (Wireless)”.

Tip: keep your primary monitor checked so you can see the desktop output.

### 🏠 Home
This is the main “mission control” screen:
- Session information
- Session Runner (load/start/pause/stop/skip)
- Live Preview (mirrors the actual output)
- Quick actions (create cuelist/playback, recent sessions)

### 📝 Cuelists
Manage cuelists inside the current session:
- Create/edit cuelists
- Add/reorder cues
- Edit a cue’s playback pool and cue settings

### 🎨 Playbacks
Create and edit playbacks:
- Spiral settings
- Media cycling settings
- Text settings
- Zoom settings

### 🔗 Device
Bluetooth device scanning and connection via MesmerIntiface (built-in). No external Intiface Central is required.

## Typical Workflow

1. Open (or create) a session.
2. In **Display**, check at least one monitor (and optionally a VR device).
3. In **Home**, load a cuelist in the Session Runner.
4. Press **Start**. Use **Pause/Stop/Skip** as needed.

## Notes

- The bottom status bar shows the current session name and selected display summary.
- VR streaming discovery starts automatically; devices appear within a couple seconds when the headset app is running.
