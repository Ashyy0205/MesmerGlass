# Testing Custom Media Directories

## Test Flow

### 1. Create Test Directories
```powershell
# Create test folders with media
mkdir C:\TestMedia\Images
mkdir C:\TestMedia\Videos

# Copy some test images/videos there
# (or use existing folders with media)
```

### 2. Launcher Test - Primary Interface

**Step 1: Set Custom Directories (Global)**
1. Run launcher: `.\.venv\Scripts\python.exe run.py`
2. Go to **MesmerLoom** tab
3. In **Media Directories** section:
   - Click **Browse...** for Images → select `C:\TestMedia\Images`
   - Click **Browse...** for Videos → select `C:\TestMedia\Videos`
4. Click **Apply**
5. ✅ **Verify console logs**:
```
[MesmerLoom] Rebuilding media library:
  Images: C:\TestMedia\Images
  Videos: C:\TestMedia\Videos
[MesmerLoom] Media library rebuilt: X images, Y videos, Z text lines
```
6. ✅ **Verify popup**: "Media Library Updated" with file counts

**Step 2: Test with Different Modes**
1. Load any mode (e.g., `default.json`)
2. Click **Launch** button
3. ✅ **Verify**: Spiral shows media from `C:\TestMedia\` directories
4. Load a different mode
5. ✅ **Verify**: Still uses same `C:\TestMedia\` directories (global setting)

**Step 3: Revert to Defaults**
1. Click **Clear** on both directories
2. Click **Apply**
3. ✅ **Verify**: Labels show "MEDIA/Images" and "MEDIA/Videos" in gray
4. ✅ **Verify**: Media switches back to default MEDIA folders
5. ✅ **Verify console**: `[MesmerLoom] Using default images directory: ...MEDIA/Images`

### 3. Visual Mode Creator Test - Preview Only

**Step 1: Select Custom Directories for Preview**
1. Run VMC: `.\.venv\Scripts\python.exe scripts\visual_mode_creator.py`
2. In **Media Settings**, scroll to **Custom Media Directories**
3. Click **Browse...** for Images → select `C:\TestMedia\Images`
4. Click **Browse...** for Videos → select `C:\TestMedia\Videos`
5. Click **Apply Directories**
6. ✅ **Verify console logs**:
```
[visual_mode] Using custom images directory: C:\TestMedia\Images
[visual_mode] Using custom videos directory: C:\TestMedia\Videos
[visual_mode] media scan: images=X videos=Y
```
7. ✅ **Verify**: Preview shows media from custom directories

**Step 2: Verify NOT Saved to Mode**
1. Enter mode name: "Test Mode"
2. Click **Export Mode (JSON)**
3. Open the saved JSON file
4. ✅ **Verify**: NO `custom_images_dir` or `custom_videos_dir` fields present
5. ✅ **Verify**: Only standard fields: `mode`, `cycle_speed`, `fade_duration`, etc.

**Step 3: VMC Settings Don't Affect Launcher**
1. Keep VMC open with custom directories
2. In launcher, verify media is still from launcher's configured directories
3. ✅ **Verify**: VMC and launcher have independent directory settings

### 4. Persistence Test (Future Feature)

**Note:** Settings persistence not yet implemented. Custom directories reset when launcher closes.

**Future Test Steps:**
1. Set custom directories in launcher
2. Close launcher completely
3. Reopen launcher
4. ✅ **Verify**: Custom directories remembered (labels show custom paths)
5. ✅ **Verify**: ThemeBank automatically uses saved directories

## Expected Results

### ✅ Success Criteria
- [ ] Launcher shows custom directories in blue text when selected
- [ ] Launcher rebuilds ThemeBank when Apply is clicked
- [ ] All modes use the same global media directories
- [ ] VMC shows custom directories in blue text when selected
- [ ] VMC preview uses media from custom directories
- [ ] VMC does NOT export custom directories to JSON
- [ ] Clear buttons revert to default MEDIA folders
- [ ] Spiral overlay shows media from custom directories
- [ ] No crashes or errors during any step

### 🐛 Known Limitations
- Subdirectories are not scanned recursively
- Only one directory per media type (can't combine multiple folders)
- Settings are **not persistent** - custom directories reset when launcher closes (future enhancement)
- Custom directories are **global** - all modes share the same media library

## Troubleshooting

### Custom directories not working in launcher?
1. Check console for: `[MesmerLoom] Rebuilding media library:`
2. Verify directories exist and contain supported media files
3. Check file extensions match supported types
4. Ensure you clicked **Apply** after selecting directories

### Media not updating after Apply?
1. Check console for: `[MesmerLoom] Media library rebuilt:`
2. Verify file count matches expected (check if files were found)
3. Check if directory is empty or has unsupported file types

### VMC preview not showing custom media?
1. Check console for: `[visual_mode] Using custom images directory:`
2. Ensure you clicked **Apply Directories** (not just Browse)
3. VMC settings are independent from launcher settings

### Settings not persisting between sessions?
- Expected behavior: Settings reset when launcher closes
- Future enhancement: Settings persistence will be added
