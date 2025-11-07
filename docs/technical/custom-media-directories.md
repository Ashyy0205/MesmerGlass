# Custom Media Directories

## Overview
MesmerGlass can now load images and videos from custom directories instead of being restricted to the default `MEDIA/Images` and `MEDIA/Videos` folders.

**Custom directories are global launcher settings** - they apply to ALL modes and persist across sessions. This allows you to organize your media library however you want without being tied to the MEDIA folder structure.

## Usage

### In Launcher (MesmerLoom Tab) - Primary Interface

1. Open the **MesmerLoom** tab in the launcher
2. In the **Media Directories** section:
   - Click **Browse...** next to Images to select a custom images folder
   - Click **Browse...** next to Videos to select a custom videos folder
3. Click **Apply** to reload the media library with your selected directories
4. Settings persist - custom directories will be used for all future sessions until cleared

### In Visual Mode Creator (VMC) - For Preview

1. Open **Visual Mode Creator** (`python scripts\visual_mode_creator.py`)
2. In the **Media Settings** section, scroll down to **Custom Media Directories**:
   - Click **Browse...** next to Images to select a custom images folder
   - Click **Browse...** next to Videos to select a custom videos folder
   - Click **Apply Directories** to reload the preview with selected media

**Note:** VMC settings are temporary and only affect the preview. They are NOT saved to mode files.

### Reverting to Defaults

- Click **Clear** next to either directory to revert to the default `MEDIA/Images` or `MEDIA/Videos` folder
- Click **Apply** to reload

## Supported File Types

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

## Technical Details

### Path Handling
- **Default directories**: Uses `MEDIA/Images` and `MEDIA/Videos`
- **Custom directories**: Absolute paths stored in launcher settings (persistent)

### Settings Persistence
Custom directories are stored in the launcher's settings/config (implementation pending):
- Launcher remembers your custom directories across sessions
- All modes use the same global media directories
- Changes take effect immediately via ThemeBank rebuild

### ThemeBank Rebuild
When you click **Apply**:
1. Scans selected directories for supported file types
2. Creates a new `ThemeConfig` with the media lists
3. Initializes a new `ThemeBank` instance
4. Activates the theme for immediate use
5. All loaded modes now use media from custom directories

### Integration Points
- `panel_mesmerloom.py`: UI controls for directory selection (launcher - persistent)
- `visual_mode_creator.py`: UI controls for directory selection (VMC - preview only)
- `launcher.py`: `_rebuild_media_library()` method handles scanning and ThemeBank rebuild
- `theme.py`: `ThemeConfig` stores media paths
- `themebank.py`: Manages theme selection and media serving

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

## Limitations
- Subdirectories are **not** scanned recursively (files must be in the root of selected directory)
- Only one custom directory per media type at a time
- Changes require clicking **Apply** - not automatic
- Custom directories are **global** - all modes share the same media library

## Future Enhancements
- Recursive directory scanning
- Multiple directory support (union of files)
- Subdirectory organization (e.g., by theme/mood)
- Auto-reload on directory changes (file watcher)
- Settings persistence (save custom dirs between launcher sessions)
