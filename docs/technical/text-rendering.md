# Text Rendering System

## Overview

MesmerGlass implements an independent text rendering system with multiple display modes, based on Trance's text overlay architecture. Text rendering is completely decoupled from Visual Programs, allowing text to display independently with various effects.

## Virtual Screen Targeting (Preview Parity)

MesmerGlass now treats text layout math and GL placement as two halves of the same pipeline. Every compositor exposes `set_virtual_screen_size()` / `get_target_screen_size()` so text can be scaled against a _live_ resolution even when rendered inside a small preview widget.

- **LoomCompositor / LoomWindowCompositor**: Convert texture quads to normalized device coordinates using the virtual size when present (defaults to widget/window dimensions, then 1920×1080 fallback).
- **TextDirector**: Queries `get_target_screen_size()` before computing centered placement, carousel spacing, and scroll offsets. When no compositor is ready it falls back to 1920×1080 to keep math deterministic.
- **Playback Editor**: Pushes the active monitor's resolution into the preview compositor on startup so the preview text exactly matches live/fullscreen output.

### Manual QA
1. Launch the Playback Editor and drag the window between monitors with different resolutions.
2. Each time, run `Tools → Reset Preview` (or close/reopen) so `_apply_preview_virtual_size()` re-samples the new monitor.
3. Confirm the preview text occupies the same relative area as the fullscreen MesmerGlass session (use a centered cue for easy comparison).
4. Toggle SUBTEXT mode; the wallpaper grid density should remain unchanged between preview and live windows because both share the same logical resolution.

## Multi-Display Mirroring (Phase 7 Refresh)

The Phase 7 text stack now mirrors overlays to every active compositor—primary window, duplicate monitors, and VR-safe mirrors—without forcing a manual refresh.

- `TextDirector.set_secondary_compositors()` immediately binds new LoomWindowCompositor instances, clears any stale textures, and **re-renders the current text payload** so carousel/SUBTEXT effects show up everywhere within a frame.
- Secondary compositors keep their own GL texture lists but never advance TextDirector state; only the primary window calls `text_director.update()` each frame, preserving deterministic timing.
- Carousel/SUBTEXT grids re-render continuously on the primary window; secondaries receive the same textures via `_render_current_text()` and remain visually in sync even if they come online mid-session.

### Manual QA (Dual Display)
1. Launch a session with two monitors selected (Display tab) and enable a cue that uses SUBTEXT / carousel text.
2. While the cue is active, toggle the secondary display on/off in the UI (or plug in a new monitor). Each secondary window should instantly show scrolling text without waiting for the next cue.
3. Watch both displays for 15+ seconds. The wallpaper grid should stay phase-matched (no drift between monitors) because only the primary compositor advances scroll offsets.
4. Stop the session and relaunch—there should be no residual textures stuck on the secondaries after cleanup.

## Text Display Modes (SplitMode)

### Core Text Modes

#### 1. NONE (Centered Text)
**Default centered display**
- Single text instance at screen center
- Large font size (typically 1/3 viewport height)
- Shadow effect (20% larger behind main text)
- Use case: Simple, impactful single-word display

**Parameters:**
- Position: `x=0.5, y=0.5` (screen center)
- Scale: `1.5` (large)
- Alpha: `1.0` (fully opaque)

---

#### 2. SUBTEXT (Scrolling Bands) ⭐ **Carousel Effect**
**Horizontal scrolling wallpaper grid**

Creates a tiled grid of repeated text that scrolls horizontally across the screen, similar to a digital marquee or scrolling wallpaper effect.

**Architecture:**
```
Screen Layout (wallpaper grid):
┌─────────────────────────────────────────┐
│ Text Text Text Text Text Text Text... →│  ← Row 1 (scrolling)
│  Text Text Text Text Text Text Text... →│ ← Row 2 (staggered + scrolling)
│ Text Text Text Text Text Text Text... →│  ← Row 3
│  Text Text Text Text Text Text Text... →│ ← Row 4 (staggered)
│ Text Text Text Text Text Text Text... →│  ← Row 5
└─────────────────────────────────────────┘

Horizontal Scrolling:
All tiles move left-to-right together
Speed: 50 pixels/second (configurable)
Seamless wrapping at screen edges
Odd rows staggered by 50% for visual variety
```

**Grid Characteristics:**
- **Layout**: Tiled grid filling entire screen
- **Columns**: ~8-12 (based on text width + 5% spacing)
- **Rows**: ~6-8 (based on text height + 5% spacing)
- **Scrolling**: Horizontal (left-to-right)
- **Speed**: 50 pixels/second (default)
- **Stagger**: Odd rows offset by 50% column width
- **Color**: Semi-transparent (alpha=0.7)
- **Scale**: 0.8 (smaller for wallpaper)
- **Animation**: Continuous re-positioning every frame

**Rendering Algorithm:**
```python
# Calculate grid dimensions
text_width_px = rendered.width * 0.8  # Scale
text_height_px = rendered.height * 0.8
spacing = 1.05  # 5% gap

cols = int(screen_width / (text_width_px * spacing)) + 2  # +2 for scrolling
rows = int(screen_height / (text_height_px * spacing)) + 1

# Render each tile
for row in range(rows):
    for col in range(cols):
        # Base position
        x_ndc = -1.0 + (col * text_w_ndc)
        
        # Stagger odd rows
        if row % 2 == 1:
            x_ndc += text_w_ndc * 0.5
        
        # Apply scroll offset
        scroll_ndc = (scroll_offset / screen_width) * 2.0
        x_ndc -= scroll_ndc
        
        # Wrap around edges
        while x_ndc < -1.0 - text_w_ndc:
            x_ndc += wrap_width
        
        # Add tile
        add_text_texture(texture, x, y, alpha=0.7, scale=0.8)
```

**Performance:**
- Re-renders entire grid every frame for scrolling
- ~50-80 text instances per frame (depends on text size)
- GPU texture caching recommended
- Monitor frame rate on integrated GPUs

**Use Cases:**
- Digital marquee/ticker effect
- Scrolling wallpaper background
- Ambient text atmosphere
- Subliminal messaging streams
- Cyberpunk aesthetic
- Matrix-style cascading text walls

---

#### 3. SPLIT_WORD (Scattered Words)
**Individual words distributed across screen**

- Splits text into words
- Scatters up to 10 words across screen
- 5 columns × 2 rows grid pattern
- Each word rendered separately

**Parameters:**
- Position: Grid-based (`x = 0.1 + (i % 5) * 0.2`)
- Scale: `1.2` (medium-large)
- Alpha: `1.0` (opaque)

**Example:**
```
Text: "Obey and submit to the spiral"
Result: 
  "Obey"     "and"      "submit"   "to"       "the"
           "spiral"
```

---

#### 4. SPLIT_LINE (Line-by-Line)
**Multi-line text displayed sequentially**

- Splits text by newline characters
- Shows one line at a time (sequencing handled by Visual Programs)
- Centered positioning

---

#### 5. SPLIT_WORD_GAPS / SPLIT_LINE_GAPS
**Spaced word/line display**

- Similar to SPLIT_WORD/LINE but with increased spacing
- Creates breathing room between elements
- Better for readability with longer texts

---

#### 6. FILL_SCREEN (Wallpaper Grid) ⚠️ **Deprecated for Text**
**Static grid of repeated text**

> **Note**: FILL_SCREEN is primarily an **image tiling mode** from Trance. For text, use **SUBTEXT** instead for scrolling bands.

If used for text:
- Creates 8×6 grid (48 instances)
- Static (no animation)
- Semi-transparent (alpha=0.7)
- Smaller scale (0.8)

**Migration:** Use `SUBTEXT` for dynamic scrolling text display.

---

#### 7. CHARACTER (Typewriter Effect)
**Character-by-character display**

- Individual character rendering
- Currently renders as single text (full typewriter animation TBD)
- Future: Frame-by-frame character reveal

---

#### 8. SPLIT_ONCE_ONLY
**Single display cycle**

- Shows text once then advances to next
- No looping within same text
- Used for sequential storytelling

---

## Text Concatenation (SUBTEXT Mode)

SUBTEXT mode requires special text handling to fill the screen width:

### Algorithm
```python
def build_subtext_string(texts: List[str], viewport_width: float) -> str:
    """
    Concatenate texts from library until string fills viewport width.
    
    Original Trance implementation:
    - Loop through text library cyclically
    - Add space + text each iteration
    - Continue until text width >= viewport width
    - Max 64 iterations to prevent infinite loop
    """
    text_string = ""
    n = 0
    iterations = 0
    
    while text_width < viewport_width and iterations < 64:
        text_string += " " + texts[n]
        n = (n + 1) % len(texts)
        iterations += 1
    
    return text_string
```

### Width Calculation
- Uses font metrics to measure rendered text width
- Compares against viewport width
- Accounts for aspect ratio: `size.x * target_y / size.y < 1.0`

---

## Scrolling Animation

### Horizontal Scrolling (SUBTEXT)

**State Variables:**
```python
self._scroll_offset = 0.0      # Current scroll position (0.0 - 1.0)
self._scroll_speed = 0.002     # Position change per frame
```

**Update Loop (per frame):**
```python
def update():
    # Increment offset
    self._scroll_offset += self._scroll_speed
    
    # Wrap around at edge
    if self._scroll_offset > 1.0:
        self._scroll_offset -= 1.0
    
    # Apply to x-coordinate
    x = 0.5 + self._scroll_offset
```

**Speed Calibration:**
- `0.001` = Slow crawl
- `0.002` = **Default** - Readable scroll
- `0.005` = Fast stream
- `0.01` = Rapid blur

**Seamless Looping:**
- Text wraps around screen edges
- Offset resets at 1.0
- Continuous motion without jumps

---

## Independent Text System Architecture

### TextDirector
**Purpose:** Manages text library and rendering

**Responsibilities:**
- Text selection with weights
- Split mode routing
- Frame-based timing
- Scrolling animation state
- Rendering dispatch

**Key Methods:**
```python
set_enabled(bool)                    # Enable/disable text rendering
set_timing(frames_per_text)          # How long to show each text
set_text_split_mode(text, mode)      # Per-text split mode
set_all_split_mode(mode)             # Global split mode
update()                             # Called every frame from compositor
```

### TextRenderer
**Purpose:** Renders text to OpenGL textures

**Features:**
- Font loading and caching
- Shadow and outline effects
- Multi-line layout
- Text measurement

### Compositor Integration
**Update Loop:**
```python
def paintGL():
    # Update visual director (images/video)
    if self.visual_director:
        self.visual_director.update(dt=1/60.0)
    
    # Update text director (independent text)
    if self.text_director:
        self.text_director.update()  # Handles scrolling animation
```

---

## Configuration

### Text Tab UI

**Controls:**
1. **Enable Independent Text Rendering** - Toggle text system on/off
2. **Duration per Text** - How long to show each text (1-600 seconds)
3. **Global Split Mode** - Default mode for all texts
4. **Per-Text Split Mode** - Override for individual texts
5. **Text Weights** - Probability of selection (0-100%)
6. **Enable/Disable** - Include/exclude specific texts

### Recommended Settings

**For Carousel Effect (Scrolling Bands):**
```
Split Mode: SUBTEXT
Duration: 30-60 seconds
Alpha: 0.8 (semi-transparent)
Scale: 0.6 (smaller for bands)
Speed: 0.002 (readable scroll)
```

**For Centered Impact:**
```
Split Mode: NONE
Duration: 3-5 seconds
Alpha: 1.0 (fully opaque)
Scale: 1.5 (large)
Shadow: Enabled
```

**For Scattered Subliminals:**
```
Split Mode: SPLIT_WORD
Duration: 5-10 seconds
Alpha: 0.7 (subtle)
Scale: 1.2 (medium)
```

---

## Original Trance Implementation Notes

### From `visual/api.cpp`

**Subtext Rendering (lines 232-272):**
```cpp
void VisualApiImpl::render_subtext(float alpha, float zoom_origin) const {
  const auto& font = _font_cache.get_font(_current_subfont);
  auto target_y = _director.vr_enabled() ? 1.f / 32.f : 1.f / 16.f;  // 6.25% height
  
  // Build text string by concatenating until it fills screen width
  std::string text;
  size_t n = 0;
  do {
    text += " " + _subtext[n];
    n = (n + 1) % _subtext.size();
    size = _director.text_size(font, text, false);
  } while (size.x * target_y / size.y < 1.f && iterations < 64);
  
  auto scale = target_y / size.y;
  auto colour = colour2sf(_director.program().shadow_text_colour());
  colour.a = uint8_t(colour.a * alpha);
  
  // Render center band
  _director.render_text(font, text, false, colour, scale, {}, 0, 0);
  
  // Render bands above and below center
  auto offset = 2 * target_y + 1.f / 512;
  for (int i = 1; (i - 1) * 2 * target_y < 1.f; ++i) {
    // Above center
    _director.render_text(font, text, false, colour, scale, 
                         sf::Vector2f{0, i * offset}, zoom_origin, zoom_origin);
    // Below center
    _director.render_text(font, text, false, colour, scale, 
                         -sf::Vector2f{0, i * offset}, zoom_origin, zoom_origin);
  }
}
```

**Key Observations:**
- VR mode reduces band height to 3.125% (half of normal)
- Alpha parameter allows fade in/out
- Zoom origin creates depth parallax effect
- Symmetric rendering (above/below center)
- Loop condition: `(i - 1) * 2 * target_y < 1.f` fills screen

---

## Performance Considerations

### SUBTEXT Mode
- **Re-renders every frame** for scrolling animation
- ~9 texture uploads per frame at 1080p
- Consider GPU texture cache optimization
- Monitor frame rate on integrated GPUs

### Other Modes
- Static after initial render
- Only re-render on text change
- Lower GPU overhead

### Optimization Strategies
1. **Texture Caching**: Reuse rendered text textures
2. **Dirty Flags**: Only re-render when state changes
3. **LOD**: Reduce band count at lower resolutions
4. **Batch Rendering**: Combine multiple bands into single draw call

---

## Testing

### Test Coverage
- `test_text_subtext.py` - SUBTEXT mode verification
  - Band count calculations
  - Spacing formula accuracy
  - Text concatenation logic
  - Scrolling animation state
  - SUBTEXT vs FILL_SCREEN differences

### Manual QA
1. **Enable SUBTEXT mode** in Text Tab
2. **Verify ~8-9 horizontal bands** fill screen vertically
3. **Confirm horizontal scrolling** (left-to-right motion)
4. **Check spacing** between bands (~12.7% viewport)
5. **Verify transparency** (semi-transparent bands)
6. **Test text cycling** (changes after duration expires)

---

## Migration from FILL_SCREEN

If you previously used `FILL_SCREEN` for text and expected scrolling bands:

**Old Configuration:**
```python
split_mode = SplitMode.FILL_SCREEN  # Static 8×6 grid
```

**New Configuration:**
```python
split_mode = SplitMode.SUBTEXT  # Scrolling horizontal bands
```

**Differences:**
| Aspect | FILL_SCREEN | SUBTEXT |
|--------|-------------|---------|
| Purpose | Image tiling | Text scrolling |
| Layout | 8×6 grid (48 instances) | ~9 horizontal bands |
| Animation | Static | Scrolling (horizontal) |
| Spacing | Even grid | 12.7% vertical spacing |
| Use Case | Wallpaper pattern | Carousel/marquee |

---

## Future Enhancements

### Planned Features
1. **Vertical Scrolling** - Support for top-to-bottom scroll direction
2. **Variable Speed** - UI control for scroll speed
3. **Color Cycling** - Animate text colors per band
4. **Depth Parallax** - Different scroll speeds per band (3D effect)
5. **Wave Deformation** - Sine wave distortion of bands
6. **Typewriter Animation** - Full CHARACTER mode implementation

### Advanced Parameters (Future)
```python
SubtextConfig:
    band_count: int = 8           # Number of bands
    band_height: float = 0.0625   # Height ratio
    spacing: float = 0.127        # Spacing ratio
    scroll_speed: float = 0.002   # Horizontal speed
    scroll_direction: str = "right"  # "left" or "right"
    alpha: float = 0.8            # Transparency
    color_cycle: bool = False     # Animate colors
    parallax: bool = False        # Depth effect
```

---

## See Also
- [Spiral Overlay](spiral-overlay.md) - Spiral rendering system
- [Visual Programs](../user-guide/visual-programs.md) - Image/video display
- [Sessions](sessions.md) - Session configuration
- [CLI Interface](cli-interface.md) - Command-line controls
