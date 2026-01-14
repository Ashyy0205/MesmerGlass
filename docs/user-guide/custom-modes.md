# Custom “Modes” (Playbacks)

MesmerGlass no longer uses the old “Visual Mode Creator / Visual Programs” workflow. The equivalent concept in the current UI is a **Playback**.

## What is a Playback?

A playback is a reusable “render recipe” stored inside a session:

- Spiral parameters (type/speed/opacity/colors)
- Media behavior (images/videos/both, cycle speed)
- Text behavior (mode, sync cadence, opacity/color)
- Zoom / acceleration parameters

Playbacks live under `session_data["playbacks"]` inside a `.session.json` file.

## Creating a playback

1. Create or open a session (**File → New Session** / **Open Session…**)
2. Go to the **Playbacks** tab
3. Click **New Playback**
4. Configure the settings, then save

## Using a playback

Playbacks are typically referenced by cues/cuelists. A common workflow is:

1. Create a playback
2. Create a cuelist and add a cue with a duration
3. Choose which playback is active for that cue
4. Run via **Home → Session Runner**

## File format note

Sessions are plain JSON. If you want to version-control your configurations, check `.session.json` files into git and edit them via the UI.

```json
{
  "version": "1.0",
  "name": "My Custom Mode",
  "description": "Optional description",
  
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": 4.0,
    "opacity": 1.0,
    "reverse": false
  },
  
  "media": {
    "mode": "images",
    "cycle_speed": 50,
    "opacity": 1.0,
    "use_theme_bank": true,
    "paths": [],
    "shuffle": false
  },
  
  "text": {
    "enabled": true,
    "mode": "centered_sync",
    "opacity": 1.0,
    "use_theme_bank": true,
    "library": [],
    "sync_with_media": true,
    "manual_cycle_speed": 50
  },
  
  "zoom": {
    "mode": "none",
    "rate": 0.5,
    "duration_frames": 180
  }
}
```

### Field Reference

**`version`** (string): Schema version, currently `"1.0"`

**`name`** (string): Display name for the mode

**`description`** (string, optional): Human-readable description

**`spiral`** (object):
- `type` (string): `"logarithmic"`, `"quadratic"`, `"linear"`, `"sqrt"`, `"inverse"`, `"power"`, `"sawtooth"`
- `rotation_speed` (number): -40.0 to +40.0 (negative = reverse)
- `opacity` (number): 0.0 to 1.0
- `reverse` (boolean): Quick reverse flag

**`media`** (object):
- `mode` (string): `"images"`, `"videos"`, `"both"`, `"none"`
- `cycle_speed` (integer): 1 to 100 (maps to frame interval via exponential curve)
- `opacity` (number): 0.0 to 1.0
- `use_theme_bank` (boolean): If true, uses launcher's media library; if false, uses `paths`
- `paths` (array of strings): Explicit file paths (only used if `use_theme_bank` is false)
- `shuffle` (boolean): Randomize media order

**`text`** (object):
- `enabled` (boolean): Enable/disable text rendering
- `mode` (string): `"centered_sync"` (changes with media), `"subtext"` (scrolling carousel)
- `opacity` (number): 0.0 to 1.0
- `use_theme_bank` (boolean): If true, uses launcher's text library; if false, uses `library`
- `library` (array of strings): Custom text phrases (only used if `use_theme_bank` is false)
- `sync_with_media` (boolean): For `centered_sync` mode, triggers text change with media
- `manual_cycle_speed` (integer): 1-100 slider that controls manual cadence when sync is disabled (matches media speed curve)

**`zoom`** (object):
- `mode` (string): `"none"`, `"in"`, `"out"`, `"pulse"`
- `rate` (number): 0.0 to 2.0 (zoom speed)
- ~~`duration_frames`~~ ❌ **REMOVED** (zoom duration controlled by media cycle speed)

## Design Philosophy

### Why Spiral Colors Are Excluded

Spiral colors (arm_color, gap_color) are **global settings** controlled in the launcher's MesmerLoom tab. This allows:

- Users to apply their preferred color scheme to **any mode**
- Quick color changes without recreating modes
- Separation of "visual pattern" (mode) from "visual theme" (colors)

### ThemeBank Integration

Custom modes can use two sources for media/text:

1. **ThemeBank** (`use_theme_bank: true`): Uses launcher's configured media/text libraries
   - **Advantage**: Easy to update content without changing mode files
   - **Use case**: Modes designed to work with your personal library

2. **Explicit paths** (`use_theme_bank: false`): Embeds specific file references
   - **Advantage**: Self-contained, portable modes
   - **Use case**: Sharing modes with specific content

## Examples

### Example 1: Fast Spiral with Centered Text

```json
{
  "version": "1.0",
  "name": "Fast Spiral",
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": 12.0,
    "opacity": 0.9,
    "reverse": false
  },
  "media": {
    "mode": "images",
    "cycle_speed": 80,
    "opacity": 0.7,
    "use_theme_bank": true,
    "paths": [],
    "shuffle": true
  },
  "text": {
    "enabled": true,
    "mode": "centered_sync",
    "opacity": 1.0,
    "use_theme_bank": true,
    "library": [],
    "sync_with_media": true
  },
  "zoom": {
    "mode": "in",
    "rate": 0.4
  }
}
```

**Use case**: High-energy mode with rapid media cycling and synchronized text changes.

### Example 2: Slow Reverse Spiral with Subtext

```json
{
  "version": "1.0",
  "name": "Slow Reverse",
  "spiral": {
    "type": "logarithmic",
    "rotation_speed": -2.0,
    "opacity": 0.6,
    "reverse": true
  },
  "media": {
    "mode": "videos",
    "cycle_speed": 20,
    "opacity": 0.9,
    "use_theme_bank": true,
    "paths": [],
    "shuffle": false
  },
  "text": {
    "enabled": true,
    "mode": "subtext",
    "opacity": 0.8,
    "use_theme_bank": true,
    "library": [],
    "sync_with_media": false
  },
  "zoom": {
    "mode": "out",
    "rate": 0.2
  }
}
```

**Use case**: Calming mode with slow reverse spiral, long video durations, and scrolling text.

## Validation

Custom mode files are validated on load:

```python
from mesmerglass.engine.custom_visual import CustomVisual

is_valid, error_msg = CustomVisual.validate_mode_file(Path("mode.json"))
if is_valid:
    print("✅ Mode file is valid")
else:
    print(f"❌ Validation error: {error_msg}")
```

**Common validation errors:**
- Missing required keys (`version`, `name`, `spiral`, `media`, `text`, `zoom`)
- Invalid JSON syntax
- Incorrect field types (e.g., string instead of number)
- Unsupported version number

## CLI Commands

### Validate Mode File

```powershell
./.venv/bin/python -c "from pathlib import Path; from mesmerglass.engine.custom_visual import CustomVisual; print(CustomVisual.validate_mode_file(Path('mesmerglass/modes/example_mode.json')))"
```

### Run Mode Directly (Future Enhancement)

```powershell
# Future: Direct mode execution
./.venv/bin/python -m mesmerglass visual-mode --file mesmerglass/modes/my_mode.json
```

## Migration Path

### Phase 1 (Current)
- CustomVisual works alongside built-in Visual Programs
- Users can create and load custom modes
- Built-in programs remain available

### Phase 2 (Future)
- Convert built-in Visual Programs to JSON mode files
- Ship with curated mode library
- Deprecation warnings for hardcoded programs

### Phase 3 (Future)
- Remove hardcoded Visual classes (SimpleVisual, SubTextVisual, etc.)
- CustomVisual becomes the only Visual implementation
- Complete user customization

## Troubleshooting

### Mode Won't Load

**Symptoms**: Error dialog on load, or no response

**Solutions**:
1. Validate JSON syntax with online validator
2. Check all required keys are present
3. Verify field types match schema
4. Check console for detailed error messages

### Media Not Showing

**Symptoms**: Spiral works but no background images/videos

**Solutions**:
1. If `use_theme_bank: true`, ensure media is loaded in launcher's media tabs
2. If `use_theme_bank: false`, verify file paths in `paths` array are absolute and exist
3. Check `media.mode` matches your content type

### Text Not Appearing

**Symptoms**: Media works but no text overlay

**Solutions**:
1. Verify `text.enabled: true`
2. If `use_theme_bank: true`, ensure text is loaded in launcher's text tab
3. If `use_theme_bank: false`, check `library` array has text phrases
4. Try increasing `text.opacity` to 1.0

### Spiral Colors Wrong

**Reminder**: Spiral colors are NOT in mode files. Adjust them in:
- Launcher → 🌀 MesmerLoom tab → Spiral Arm Color / Gap Color

## Best Practices

1. **Start simple**: Create basic modes first, then add complexity
2. **Use descriptive names**: Makes modes easier to find and share
3. **Test in creator**: Always preview before exporting
4. **Version control**: Keep mode files in git for history tracking
5. **Document settings**: Use `description` field to explain mode intent
6. **Share with community**: Export and share modes with other users

## See Also

- [Visual Mode Creator Usage](../development/visual-mode-creator.md)
- [Spiral Overlay Technical Reference](../technical/spiral-overlay.md)
- [Text System Documentation](../technical/text-director.md)
- [CLI Interface Guide](../technical/cli-interface.md)
