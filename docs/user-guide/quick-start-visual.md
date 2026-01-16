# MesmerGlass Quick Start

This guide gets you from “fresh clone” to “visuals on screen” with the current **session-based** UI.

## 1) Install + launch

From the repo root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# Start the GUI
python -m mesmerglass run
# (or: python run.py)
```

## 2) Create or open a session

In the app:

- **File → New Session** (Ctrl+N), or
- **File → Open Session…** (Ctrl+O) and select a `.session.json`

Tip: the repo ships example sessions in `mesmerglass/sessions/`.

## 3) Pick an output display

Go to the **Display** tab and ensure at least one monitor (or VR output) is selected.

If nothing seems to render, this is almost always the cause.

## 4) Add your media (images/videos/fonts)

Go to the **Home** tab → **Media Bank** section:

1. Click **Add Directory**
2. Choose a folder
3. Label it and choose its type: **images**, **videos**, **both**, or **fonts**
4. Click **Refresh** to force a rescan

Media Bank entries are stored inside the current session file.

## 5) Create playbacks + cues, then run

At a high level:

- **Playbacks** define “what to render” (spiral/media/text/zoom)
- **Cuelists** define “what happens over time” (durations, audio tracks, which playback is active)

Suggested first workflow:

1. **Playbacks** → **New Playback** → configure spiral + media mode
2. **Cuelists** → add a cue → set duration and optional audio
3. **Home** → use SessionRunner **Start**

## Common “nothing works” checklist

- Display tab: at least one monitor selected
- Home tab: session loaded and Media Bank has at least one images/videos folder
- SessionRunner: started (not paused/stopped)
