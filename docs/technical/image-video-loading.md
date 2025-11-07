# Image and Video Loading System

## Overview

The image and video loading system provides theme-based media management with async loading, weighted shuffling for anti-repetition, and GPU texture caching. This implementation matches Trance's theme/shuffler architecture.

## Architecture

### Three-Layer Design

1. **Configuration Layer** (`theme.py`)
   - Theme definitions and collections
   - Weighted shuffler for anti-repetition
   - Trance-compatible JSON format

2. **Loading Layer** (`media.py`)
   - Async image loading (disk → RAM)
   - LRU image cache
   - Future: video frame extraction

3. **Management Layer** (`themebank.py`)
   - Multi-theme management (2 active themes)
   - Last-8 image tracking
   - Theme switching with cooldown

## Components

### ThemeConfig (`mesmerglass/content/theme.py`)

Represents a single theme with associated media paths and text.

**Fields:**
- `name`: Theme identifier
- `enabled`: Whether theme is active
- `image_path`: List of image file paths
- `animation_path`: List of video file paths
- `font_path`: List of font file paths
- `text_line`: List of text messages

**Methods:**
- `validate()`: Check configuration validity
- `from_dict()` / `to_dict()`: JSON serialization
- `get_random_text()`: Select random text line

### ThemeCollection (`mesmerglass/content/theme.py`)

Container for multiple themes with loading/saving.

**Methods:**
- `load_theme_collection(path)`: Load from JSON file
- `save_theme_collection(collection, path)`: Save to JSON
- `get_enabled_themes()`: Filter active themes
- `from_dict()` / `to_dict()`: Support Trance `theme_map` or direct `themes` array

**Format Support:**
```json
{
  "theme_map": {
    "theme_name": {
      "enabled": true,
      "image_path": ["img1.jpg", "img2.png"],
      "text_line": ["Message 1", "Message 2"]
    }
  }
}
```

### Shuffler (`mesmerglass/content/theme.py`)

Weighted random selector that avoids repetition.

**Algorithm:**
1. Start with equal weights (default 1.0)
2. Select random index weighted by current weights
3. Decrease weight when image selected
4. Increase weight when image ages out of last-8

**Methods:**
- `next()`: Select next index using weighted random
- `decrease(index, amount=1.0)`: Lower selection probability
- `increase(index, amount=1.0)`: Raise selection probability
- `reset()`: Reset all weights to default

**Example:**
```python
shuffler = Shuffler(count=10)
idx = shuffler.next()  # Weighted random 0-9
shuffler.decrease(idx)  # Make less likely next time
```

### ImageData (`mesmerglass/content/media.py`)

Decoded image in RAM.

**Fields:**
- `width`, `height`: Image dimensions
- `data`: RGBA numpy array (height, width, 4) uint8
- `path`: Original file path

**Validation:**
- Must be RGBA format (4 channels)
- Must be uint8 dtype
- Dimensions must match shape

### AsyncImageLoader (`mesmerglass/content/media.py`)

Background thread for decoding images.

**Two-Phase Loading:**
1. **Phase 1 (Background Thread)**: Disk → RAM
   - PIL decodes image file
   - Convert to RGBA format
   - Store in result queue

2. **Phase 2 (Main Thread)**: RAM → GPU
   - Process result queue
   - Upload to OpenGL texture (future)
   - Move into cache

**Methods:**
- `request_load(path)`: Queue image for loading
- `get_loaded_images()`: Retrieve decoded images
- `shutdown()`: Stop background thread

**Usage:**
```python
loader = AsyncImageLoader()
loader.request_load(Path("image.jpg"))

# Later, on main thread
loaded = loader.get_loaded_images()
for path, image_data in loaded:
    # Upload to GPU here
    pass
```

### ImageCache (`mesmerglass/content/media.py`)

LRU cache for loaded images.

**Features:**
- Configurable cache size
- Automatic eviction (least recently used)
- On-demand loading via AsyncImageLoader
- Thread-safe result processing

**Methods:**
- `get_image(path)`: Get cached image or request load
- `process_loaded_images()`: Move loaded images into cache
- `clear()`: Empty cache

**Example:**
```python
cache = ImageCache(cache_size=16, loader=loader)

# Request image (loads if not cached)
image = cache.get_image(Path("image.jpg"))
if image is None:
    # Not loaded yet, try again later
    cache.process_loaded_images()
    image = cache.get_image(Path("image.jpg"))
```

### ThemeBank (`mesmerglass/content/themebank.py`)

High-level manager for multiple themes.

**Theme Slots:**
- **Slot 0**: Old theme (being phased out)
- **Slot 1**: Primary theme
- **Slot 2**: Alternate theme
- **Slot 3**: Next theme (not yet active)

**Anti-Repetition:**
- Tracks last 8 images globally (across all themes)
- Decreases shuffler weight when image selected
- Increases shuffler weight when image ages out

**Theme Switching:**
- 500 async-update cooldown (~8-10 seconds)
- Maintains last-8 tracking across switches

**Methods:**
- `get_image(alternate=False)`: Get next image from primary or alternate theme
- `get_text_line(alternate=False)`: Get random text from theme
- `async_update()`: Process background loading, handle theme switches
- `switch_themes()`: Manually trigger theme change

**Example:**
```python
bank = ThemeBank(
    themes=[theme1, theme2, theme3],
    cache_size_per_theme=16
)

# Get next image
image_data = bank.get_image()

# Get text
text = bank.get_text_line()

# Process background loads (call frequently)
bank.async_update()
```

## CLI Commands

### Theme Inspection

```bash
# Show summary
python -m mesmerglass theme --load themes/default.json

# List all themes
python -m mesmerglass theme --load themes/default.json --list

# Show full config
python -m mesmerglass theme --load themes/default.json --show-config
```

### Testing

```bash
# Test weighted shuffler
python -m mesmerglass theme --load themes/default.json --test-shuffler 100

# Test image cache
python -m mesmerglass theme --test-cache
```

## Integration Status

### ✅ Completed
- Theme configuration loading (Trance format)
- Weighted shuffler with anti-repetition
- Async image loading (disk → RAM)
- LRU image cache
- Theme bank manager
- Last-8 image tracking
- CLI commands for testing
- 24 comprehensive tests

### ⏳ Pending
- GPU texture upload (RAM → GPU)
- Integration with LoomCompositor
- Video frame extraction (opencv)
- Image tiling/kaleidoscope effect
- Zoom interpolation
- Video ping-pong playback

## Testing

### Unit Tests (`test_theme_media.py`)
- ThemeConfig creation and validation
- ThemeCollection loading (Trance and direct formats)
- Shuffler weighted selection
- ImageData validation
- 17 tests total

### CLI Tests (`test_cli_theme.py`)
- Theme loading and summary
- Theme listing
- JSON output
- Shuffler testing
- Error handling
- 7 tests total

Run tests:
```bash
python -m pytest mesmerglass/tests/test_theme_media.py -v
python -m pytest mesmerglass/tests/test_cli_theme.py -v
```

## Next Steps

1. **GPU Texture Upload**
   - Create `texture.py` with `upload_image_to_gpu()`
   - Generate OpenGL texture from ImageData
   - Return texture ID for rendering

2. **Compositor Integration**
   - Add background texture to LoomCompositor
   - Render image layer before spiral
   - Implement tiling/kaleidoscope

3. **Video Support**
   - Create `video.py` with VideoStreamer
   - Extract frames using opencv
   - Ping-pong playback (forward→backward)

4. **Performance Testing**
   - Cache hit rates
   - Load times
   - Memory usage

## Configuration Example

```json
{
  "theme_map": {
    "hypnotic": {
      "enabled": true,
      "image_path": [
        "themes/hypnotic/img1.jpg",
        "themes/hypnotic/img2.png",
        "themes/hypnotic/img3.jpg"
      ],
      "animation_path": [
        "themes/hypnotic/video1.mp4"
      ],
      "font_path": [
        "fonts/custom.ttf"
      ],
      "text_line": [
        "Sink deeper",
        "Let go",
        "Focus on the spiral"
      ]
    },
    "trance": {
      "enabled": true,
      "image_path": [
        "themes/trance/bg1.jpg",
        "themes/trance/bg2.jpg"
      ],
      "text_line": [
        "Relax",
        "Drift",
        "Float"
      ]
    }
  }
}
```

## Dependencies

**Existing (in requirements.txt):**
- `Pillow`: Image loading and conversion
- `opencv-python`: Video frame extraction (ready for use)
- `numpy`: Image data arrays

**No new dependencies required** — all infrastructure uses existing packages.
