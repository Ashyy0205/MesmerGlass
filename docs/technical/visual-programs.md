# Visual Programs

## Overview

Visual programs are high-level compositions that combine multiple visual elements (images, videos, text) with synchronized spiral animations. Each visual program follows a specific timing and transition pattern.

**Status:** ✅ COMPLETE (8 visual types implemented, 3 exposed via Media Modes UI)

**Note:** Visual Programs tab has been removed from the UI. Users now access visual programs through the **Media Mode** selector in the MesmerLoom tab:
- **Images & Videos** → MixedVisual (index 7)
- **Images Only** → SimpleVisual (index 0)
- **Videos Only** → AnimationVisual (index 6)

Other visual types (SubText, Accelerate, SlowFlash, etc.) remain available programmatically but are not exposed in the default UI.

## Architecture

### Core Components

1. **Visual Base Class** (`mesmerglass/engine/visuals.py`)
   - Abstract interface for all visual programs
   - Manages cycler lifecycle (reset, complete, progress tracking)
   - Delegates timing logic to cycler system

2. **Cycler Integration** (Phase 4+5)
   - ActionCycler: Periodic callbacks
   - RepeatCycler: Loop actions N times
   - SequenceCycler: Chain actions sequentially
   - ParallelCycler: Run multiple cyclers simultaneously

3. **Shuffler System** (Phase 5)
   - Weighted random selection
   - Last-8 anti-repetition
   - Content variety guarantee

## Visual Types

### 1. SimpleVisual

**Purpose:** Basic image display with spiral overlay

**Pattern:**
- Display 16 images sequentially
- Each image shown for 48 frames (~0.8 seconds at 60 FPS)
- Spiral rotates every frame
- Images selected via shuffler (no repetition)

**Callbacks:**
- `on_change_image(index)` - Load and display image
- `on_rotate_spiral()` - Spiral rotation marker
- `on_preload_image(index)` - Optional async preloading

**Implementation:**
```python
SimpleVisual(
    image_paths=[...],
    on_change_image=lambda idx: load_image(idx),
    on_rotate_spiral=lambda: rotate_spiral(),
    on_preload_image=None
)
```

### 2. SubTextVisual

**Purpose:** Multi-layer text + image with variable timing

**Pattern:**
- Changes main text every 4/12/24/48 frames (random selection)
- Changes subtext (secondary layer) separately
- Images shown for 48 frames
- All 3 layers synchronized via ParallelCycler

**Callbacks:**
- `on_change_image(index)` - Background image
- `on_change_text(text)` - Primary text layer
- `on_change_subtext(text)` - Secondary text layer
- `on_rotate_spiral()` - Spiral rotation

**Text Periods:**
- 4 frames = ultra-fast flash (1/15 second)
- 12 frames = quick text (1/5 second)
- 24 frames = medium text (2/5 second)
- 48 frames = slow text (0.8 second)

### 3. AccelerateVisual

**Purpose:** Gradual acceleration with zoom effect

**Pattern:**
- Starts with 56 frames per image (slow)
- Decreases to 12 frames per image (fast)
- Zoom increases proportionally (1.0 → 2.0+)
- 7 images total (decreasing periods: 56, 52, 48, 28, 20, 16, 12)

**Callbacks:**
- `on_change_image(index, zoom)` - Image with zoom parameter
- `on_rotate_spiral_degrees(degrees)` - Spiral rotation with angle

**Zoom Calculation:**
```python
zoom = 1.0 + (period_decrease / max_decrease) * 1.0
# Period 56 → zoom 1.0
# Period 12 → zoom 2.0
```

### 4. SlowFlashVisual

**Purpose:** Alternating slow/fast image display

**Pattern:**
- 64 frames slow → 8 frames fast (alternating)
- 20 images total (10 slow + 10 fast)
- Creates rhythm/pulse effect
- Spiral rotates continuously

**Callbacks:**
- `on_change_image(index)` - Standard image change
- `on_rotate_spiral()` - Spiral rotation

**Timing:**
- Slow: 64 frames (~1 second)
- Fast: 8 frames (~0.13 seconds)
- Total: 720 frames (~12 seconds)

### 5. FlashTextVisual

**Purpose:** Rapid text+image flashing

**Pattern:**
- Change image every 48 frames (slow)
- Flash text every 6 frames (ultra-fast)
- 8 text flashes per image
- 16 images total
- Creates subliminal text effect

**Callbacks:**
- `on_change_image(index)` - Background image
- `on_change_text(text)` - Flash text overlay
- `on_rotate_spiral()` - Spiral rotation

**Flash Rate:**
- 6 frames = 1/10 second at 60 FPS
- Too fast for conscious reading
- Subliminal messaging effect

### 6. ParallelImagesVisual

**Purpose:** Multiple simultaneous image slots

**Pattern:**
- 3 independent image slots (default)
- Each slot has its own period (32, 48, 64 frames)
- All slots run in parallel
- Creates layered visual complexity

**Callbacks:**
- `on_change_image(slot, index)` - Change specific slot

**Slot Configuration:**
```python
slot_count = 3
slot_periods = [32, 48, 64]  # Different timing per slot
total_cycles = 8  # Repeat 8 times
```

**Note:** Current demo uses single-slot mode for simplicity. Multi-slot rendering requires compositor layer support.

### 7. AnimationVisual

**Purpose:** Video playback with spiral overlay

**Pattern:**
- Play 6 videos sequentially
- Each video plays for 300 frames (~5 seconds)
- Videos streamed via VideoStreamer (Phase 1)
- Ping-pong playback (forward → backward → repeat)
- Spiral rotates every frame

**Callbacks:**
- `on_change_video(index)` - Load and start video
- `on_rotate_spiral()` - Spiral rotation

**Integration:**
```python
# Callback loads video
def on_change_video(index):
    video_streamer.load_video(video_paths[index])

# Update loop (60 FPS)
def update():
    cycler.advance()  # Triggers on_change_video when needed
    video_streamer.advance_frame(global_fps=60)  # Update playback
    frame = video_streamer.get_current_frame()
    compositor.set_background_video_frame(frame.data, ...)
```

**VideoStreamer Features:**
- Double-buffered async loading
- Ping-pong playback mode
- Frame-accurate seeking
- Automatic direction reversal

### 7. MixedVisual ⭐ NEW

**Purpose:** Alternates between static images and playing videos

**Pattern:**
- **Image Phase**: Display 3 images sequentially (48 frames each = ~2.4s total)
- **Video Phase**: Play 2 videos sequentially (300 frames each = ~10s total)
- Repeats for 3 complete cycles (images → videos → images → videos...)
- Separate shufflers for images and videos (no cross-contamination)

**Callbacks:**
- `on_change_image(index)` - Load and display static image
- `on_change_video(index)` - Start video playback
- `on_rotate_spiral()` - Spiral rotates every frame

**State Tracking:**
- `is_showing_video()` method returns `True` during video phase, `False` during image phase
- Visual director uses this to conditionally update video frames (prevents videos from overwriting images)

**Implementation:**
```python
MixedVisual(
    image_paths=[...],
    video_paths=[...],
    on_change_image=lambda idx: load_image(idx),
    on_change_video=lambda idx: load_video(idx),
    on_rotate_spiral=lambda: rotate_spiral(),
    image_duration=48,      # frames per image
    video_duration=300,     # frames per video
    images_per_cycle=3,     # images before switching to videos
    videos_per_cycle=2,     # videos before switching to images
    cycles=3                # total repetitions
)
```

**Usage:**
- Default for **"Images & Videos"** media mode in UI
- Provides balanced mix of static and dynamic content
- Ideal for general hypnosis/trance sessions

## Testing

### Unit Tests (`mesmerglass/tests/test_cli_spiral.py`)

**Coverage:** 18 tests, 100% passing

**Test Categories:**
1. **Cycler Construction** - Verify correct cycler types created
2. **Timing Validation** - Check frame counts, periods, total duration
3. **Callback Execution** - Verify callbacks fire at correct times
4. **Completion Logic** - Test reset, complete, progress tracking
5. **Shuffler Integration** - Verify anti-repetition for image/video selection

**Example Tests:**
```python
def test_simple_visual_timing():
    """SimpleVisual: 16 images × 48 frames = 768 total frames"""
    visual = SimpleVisual(...)
    cycler = visual.get_cycler()
    
    # Run full cycle
    for _ in range(768):
        cycler.advance()
    
    assert cycler.complete()
    assert len(callbacks) == 16  # Changed 16 images

def test_accelerate_visual_zoom():
    """AccelerateVisual: Zoom increases with speed"""
    visual = AccelerateVisual(...)
    
    # Verify zoom increases
    assert callbacks[0][1] < callbacks[-1][1]  # First zoom < last zoom
```

### Integration Demo (`scripts/demo_all_visual_programs.py`)

**Purpose:** Visual demonstration of all 7 programs with real media

**Features:**
- Uses actual LoomCompositor (spiral rendering)
- Loads real images from `MEDIA/Images/` (61 files)
- Loads real videos from `MEDIA/Videos/` (23 files)
- Uses real font from `MEDIA/Fonts/FONTL___.TTF`
- Interactive controls (1-7 select visual, SPACE pause, etc.)

**Controls:**
- `1-7` - Switch to specific visual program
- `SPACE` - Pause/Resume
- `R` - Reset current visual
- `N` - Next visual (auto-cycle)
- `K` - Toggle kaleidoscope effect
- `I/O` - Spiral intensity +/-
- `Q/ESC` - Quit

**Run Demo:**
```bash
.\.venv\Scripts\python.exe .\scripts\demo_all_visual_programs.py
```

## Implementation Details

### Cycler Composition Examples

**SimpleVisual:**
```python
# Parallel: spiral rotation + image changes
ParallelCycler([
    ActionCycler(period=1, action=rotate_spiral, repeat=768),
    RepeatCycler(count=16, child=
        ActionCycler(period=48, action=change_image)
    )
])
```

**SubTextVisual:**
```python
# 3-way parallel: spiral + image + text layers
ParallelCycler([
    spiral_cycler,
    image_loop,
    SequenceCycler([text_actions])  # Variable periods
])
```

**AccelerateVisual:**
```python
# Sequential acceleration
SequenceCycler([
    ActionCycler(period=56, action=change_zoom_1),
    ActionCycler(period=52, action=change_zoom_2),
    # ... decreasing periods
    ActionCycler(period=12, action=change_zoom_7)
])
```

### Callback Signatures

**Standard Callbacks:**
- `on_change_image(index: int)` - Most visuals
- `on_change_text(text: str)` - Text-based visuals
- `on_rotate_spiral()` - All visuals

**Special Callbacks:**
- `on_change_image(index: int, zoom: float)` - AccelerateVisual only
- `on_rotate_spiral_degrees(degrees: float)` - AccelerateVisual only
- `on_change_video(index: int)` - AnimationVisual only
- `on_change_parallel_image(slot: int, index: int)` - ParallelImagesVisual only

## Dependencies

**Required Phases:**
- ✅ Phase 0: Spiral System + LoomCompositor
- ✅ Phase 1: Video Playback (VideoStreamer, ping-pong)
- ✅ Phase 3: Text Rendering (TextRenderer, fonts)
- ✅ Phase 4+5: Cycler System + Shuffler

**Python Packages:**
- `PyQt6` - Window management, event loop
- `OpenGL` - GPU rendering
- `opencv-python` - Video decoding
- `Pillow` - Image loading, text rendering
- `numpy` - Frame buffer manipulation

## Performance Considerations

### Frame Rate
- Target: 60 FPS (16ms per frame)
- Cycler overhead: <1ms per advance()
- Image loading: Async recommended (use `on_preload_image`)
- Video decoding: Double-buffered (90 frame buffer)

### Memory
- Image cache: LRU eviction (Phase 2 infrastructure)
- Video buffer: 90 frames × resolution × 3 bytes (RGB)
- Texture upload: Reuse texture IDs (avoid allocation churn)

### GPU Upload
- Static images: One-time upload, reuse texture
- Video frames: Update texture data each frame (glTexSubImage2D)
- Text: Render to RGBA texture, composite with alpha blending

## Future Enhancements

### Potential Improvements
1. **Multi-slot rendering** - ParallelImagesVisual with actual layering
2. **Animation effects** - Fade in/out, crossfade between images
3. **Audio sync** - Match visual changes to audio beats (Phase 2)
4. **Custom patterns** - User-defined visual programs via JSON
5. **Performance profiling** - Per-visual frame time tracking

### Compatibility Notes
- AnimationVisual now fully integrated with VideoStreamer (no longer a placeholder)
- All 7 visual types production-ready
- Demo uses actual compositor infrastructure (not pygame mockup)
- Real media files from MEDIA/ folder

## References

- `mesmerglass/engine/visuals.py` - All 7 visual classes
- `mesmerglass/engine/cyclers.py` - Timing system (Phase 4)
- `mesmerglass/engine/shuffler.py` - Content selection (Phase 5)
- `mesmerglass/content/video.py` - Video streaming (Phase 1)
- `mesmerglass/content/text_renderer.py` - Text rendering (Phase 3)
- `RECREATION_FILES/SPIRAL_AND_MEDIA_DOCUMENTATION.md` - Original Trance patterns
- `docs/ROADMAP.md` - Phase progression and completion status
