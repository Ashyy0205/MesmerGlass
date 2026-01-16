# Custom Media Directories (Media Bank)

## Overview

MesmerGlass loads images/videos/fonts from directories you choose. In the current UI, this is configured per-session via the **Media Bank**.

Each Media Bank entry points at a folder and declares its type:

- `images`
- `videos`
- `both` (images + videos)
- `fonts`

These entries are stored inside the session JSON under `media_bank`.

## Usage (GUI)

1. Create or open a session (`.session.json`)
2. Go to **Home → Media Bank**
3. Click **Add Directory**
4. Choose folder + type
5. Click **Refresh** to force a rescan

## Supported file types

### Images
- `.jpg`, `.jpeg`
- `.png`
- `.gif`
- `.webp`

### Videos
- `.mp4`
- `.webm`
- `.mkv`
- `.avi`

## Technical notes

- Media Bank entries rebuild ThemeBank (images/videos) and the font library (fonts).
- Paths are stored as absolute paths inside the session JSON.

## Use Cases

### Using External Libraries
Point to your existing image/video collections without copying files into `MEDIA/`:
- Photography libraries
- Video editing projects
- Downloaded content packs
- Network/cloud storage locations

### Organizing Content by Type
```
C:/Media/
  /HypnoSpirals/    <- Set as Images directory
  /VisualEffects/   <- Set as Videos directory
```

### Testing New Content
Quickly test new visuals without moving them into the main `MEDIA/` structure.

### Portable Setup
Keep your MesmerGlass installation separate from your large media library.

## Troubleshooting (CLI)

```powershell
# Readiness summary
python -m mesmerglass themebank stats

# Exit 0 when at least one usable media item exists; exit 3 when empty
python -m mesmerglass themebank selftest --timeout 10
```
