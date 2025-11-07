# Trance Recreation Implementation Plan

**Status:** In Progress  
**Last Updated:** October 28, 2025  
**Goal:** Recreate Trance's hypnotic visual system in MesmerGlass

---

## 🎨 GUI Integration Strategy

### Current GUI Architecture
MesmerGlass uses a **tabbed main window** (`launcher.py`) with specialized control panels:

**Existing Tabs:**
- **Media** - Video/image overlay controls (legacy overlay system)
- **Text FX** - Text overlay effects
- **Audio** - Dual audio track player
- **Device** - Buttplug.io device integration
- **MesmerLoom** - Spiral overlay controls (`panel_mesmerloom.py`)
- **Performance** - FPS/metrics display
- **DevTools** - Developer utilities

**Control Panel Pattern:**
```python
# Each feature gets a QGroupBox with vertical layout
box = QGroupBox("Feature Name")
layout = QVBoxLayout(box)

# Controls follow _row() helper pattern:
def _row(label: str, widget: QWidget) -> QWidget:
    # Returns QWidget with horizontal layout:
    # [Label (160px min)] [Widget (stretch)]
```

### Integration Plan Per Phase

---

#### **Phase 1: Video Playback GUI** 🎬

**New Tab: "Background Media"**  
Location: `mesmerglass/ui/pages/background_media.py`

**Controls:**
```
┌─ Background Media ─────────────────────────┐
│                                            │
│ ┌─ Video/Image Selection ────────────┐    │
│ │ File Path: [________________________]  │
│ │            [Browse...] [Clear]       │
│ │                                       │
│ │ Content Type: [Image ▼] [GIF/WebM/MP4] │
│ │                                       │
│ │ Preview: [███████████████]            │
│ │          (240x135 thumbnail)          │
│ └───────────────────────────────────────┘ │
│                                            │
│ ┌─ Playback ──────────────────────────┐   │
│ │ Mode: [●Single ○Ping-Pong ○Loop]     │
│ │                                       │
│ │ Speed: [====|=====] 100%              │
│ │        (50% - 200%)                   │
│ │                                       │
│ │ [▶ Play] [⏸ Pause] [⏹ Stop]          │
│ └───────────────────────────────────────┘ │
│                                            │
│ ┌─ Effects ────────────────────────────┐  │
│ │ Zoom:         [=====|===] 1.0x        │
│ │ Kaleidoscope: [ ] Enable              │
│ │ Aspect Ratio: [☑] Preserve            │
│ └───────────────────────────────────────┘ │
│                                            │
│ ┌─ Status ──────────────────────────────┐ │
│ │ Resolution: 1920x1080                 │
│ │ FPS: 30.0 | Frame: 145/900            │
│ │ Buffer: A:Ready B:Loading (45%)       │
│ └───────────────────────────────────────┘ │
└────────────────────────────────────────────┘
```

**Implementation:**
- Reuse compositor's existing `set_background_texture()` API
- Add `set_background_video_frame()` for animated content
- Wire controls to `VideoStreamer` class
- Update status labels via QTimer (30 FPS)

**Code Hook:**
```python
# In launcher.py
self.bg_media_page = BackgroundMediaPage(self.compositor, self.director)
self.tabs.addTab(self.bg_media_page, "Background")

# BackgroundMediaPage connects to:
self.compositor.set_background_texture(texture_id, zoom, w, h)
self.compositor.set_background_kaleidoscope(enabled)
```

---

#### **Phase 2: Zoom & Animation GUI** 🔍

**Add to "Background Media" Tab:**

**New Group: "Animation"**
```
┌─ Animation ──────────────────────────────┐
│ Pattern: [None ▼]                        │
│          [None/Center Zoom/Drift/Random] │
│                                          │
│ ─── Center Zoom Settings ────            │
│ Start Zoom:  [====|======] 1.0x          │
│ End Zoom:    [=========|=] 1.5x          │
│ Duration:    [======|====] 8.0s          │
│ Hold Start:  [==|========] 2.0s          │
│ Hold End:    [==|========] 2.0s          │
│                                          │
│ ─── Drift Settings ───────────            │
│ X Speed:     [====|======] 0.5           │
│ Y Speed:     [======|====] 0.3           │
│ Drift Scale: [===|=======] 0.3           │
│                                          │
│ ─── Random Settings ──────────            │
│ Change Every: [====|=====] 12.0s         │
│ Max Zoom:     [=======|==] 1.8x          │
│ Max Drift:    [=====|====] 0.5           │
│                                          │
│ [☑] Loop Animation                       │
└──────────────────────────────────────────┘
```

**Implementation:**
- ComboBox selects animation pattern (0=None, 1=Center, 2=Drift, 3=Random)
- Pattern change shows/hides relevant spinboxes
- QTimer updates `compositor.set_background_zoom()` each frame
- Director stores interpolation state

**Code Hook:**
```python
# In BackgroundMediaPage
self.anim_timer = QTimer()
self.anim_timer.timeout.connect(self._update_animation)
self.anim_timer.start(16)  # 60 FPS

def _update_animation(self):
    zoom, offset = self.animator.get_current_state()
    self.compositor.set_background_zoom(zoom)
    self.compositor.set_background_offset(offset)  # NEW API
```

---

#### **Phase 3: Text Overlay GUI** 📝

**New Tab: "Text Overlay"** (Separate from legacy TextFX)  
Location: `mesmerglass/ui/pages/text_overlay.py`

**Controls:**
```
┌─ Text Overlay ───────────────────────────┐
│                                          │
│ ┌─ Content ───────────────────────────┐ │
│ │ Mode: [●Single ○Sequence]            │ │
│ │                                      │ │
│ │ ─── Single Text ─────                │ │
│ │ Text: [________________________]     │ │
│ │       (Supports newlines)            │ │
│ │                                      │ │
│ │ ─── Text Sequence ────────           │ │
│ │ [Add Line...] [Load File...]         │ │
│ │ ┌────────────────────────────────┐   │ │
│ │ │ 1. You are getting sleepy...   │   │ │
│ │ │ 2. Deeper and deeper...        │   │ │
│ │ │ 3. So relaxed...               │   │ │
│ │ └────────────────────────────────┘   │ │
│ │ [↑] [↓] [Edit] [Delete]              │ │
│ │                                      │ │
│ │ Duration/Line: [====|====] 5.0s      │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Appearance ─────────────────────────┐ │
│ │ Font:        [Segoe UI ▼] [Browse]   │ │
│ │ Size:        [======|====] 48pt      │ │
│ │ Color:       [■] [Pick...]           │ │
│ │ Outline:     [☑] Width: [==|=] 2px   │ │
│ │ Shadow:      [☑] Blur: [===|=] 4px   │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Layout ─────────────────────────────┐ │
│ │ Position:  [Center ▼]                │ │
│ │            [Top/Center/Bottom/Custom] │ │
│ │                                      │ │
│ │ Alignment: [●Center ○Left ○Right]    │ │
│ │                                      │ │
│ │ Split Mode: [None ▼]                 │ │
│ │             [None/Word/Character]    │ │
│ │ Split Gap:  [=====|===] 50px         │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Effects ────────────────────────────┐ │
│ │ Fade In:  [===|======] 1.0s          │ │
│ │ Fade Out: [===|======] 1.0s          │ │
│ │ Wobble:   [==|=======] 0.02          │ │
│ │ Drift:    [==|=======] 0.01          │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ [Preview Text Rendering]                 │
└──────────────────────────────────────────┘
```

**Implementation:**
- Font manager caches TTF files
- Text renderer creates texture atlas
- Sequence player advances via QTimer
- Split mode creates multiple quads with calculated offsets

**Code Hook:**
```python
# In compositor
self.text_renderer = TextRenderer()
self.compositor.set_text_sequence(lines, duration_per_line)
self.compositor.set_text_appearance(font, size, color, outline, shadow)
self.compositor.set_text_layout(position, alignment, split_mode, gap)
```

---

#### **Phase 4: Cycler System GUI** ⏱️

**New Tab: "Timeline"**  
Location: `mesmerglass/ui/pages/timeline.py`

**Controls:**
```
┌─ Timeline Editor ────────────────────────┐
│                                          │
│ [+ Action] [+ Repeat] [+ Sequence] [+ │] │
│                                          │
│ ┌─ Cycler Tree ────────────────────────┐ │
│ │ ▼ Root (Parallel)                    │ │
│ │   ├─ ▶ Sequence "Intro"              │ │
│ │   │   ├─ Action: Fade In (2s)        │ │
│ │   │   └─ Action: Show Text (5s)      │ │
│ │   ├─ ▶ Repeat x3                     │ │
│ │   │   └─ Action: Pulse (1s)          │ │
│ │   └─ ▶ Parallel "Main"               │ │
│ │       ├─ Repeat ∞                    │ │
│ │       │   └─ Action: Zoom (8s)       │ │
│ │       └─ Sequence                    │ │
│ │           ├─ Action: Text 1 (4s)     │ │
│ │           └─ Action: Text 2 (4s)     │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Selected: Action "Zoom" ────────────┐ │
│ │ Type:     [Zoom Background ▼]        │ │
│ │ Duration: [======|====] 8.0s         │ │
│ │ Start:    [====|======] 1.0x         │ │
│ │ End:      [=========|=] 2.0x         │ │
│ │ Easing:   [Ease In-Out ▼]            │ │
│ │                                      │ │
│ │ [Apply] [Cancel] [Delete]            │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Playback ───────────────────────────┐ │
│ │ [▶ Play] [⏸ Pause] [⏹ Stop]          │ │
│ │ Position: 00:12.5 / 01:45.0          │ │
│ │ [===========|===================]    │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ [Save Timeline...] [Load Timeline...]    │
└──────────────────────────────────────────┘
```

**Implementation:**
- Tree widget displays cycler hierarchy
- Drag & drop to reorder/reparent cyclers
- Right-click context menu for add/delete/copy
- Timeline scrubber updates preview
- Export to JSON for persistence

**Code Hook:**
```python
# In timeline page
self.cycler_engine = CyclerEngine()
self.tree_widget.itemClicked.connect(self._edit_cycler)

def _play_timeline(self):
    self.cycler_engine.reset()
    self.play_timer.start(16)  # 60 FPS

def _update_playback(self):
    self.cycler_engine.tick(0.016)
    # Cyclers emit commands to compositor/director
```

---

#### **Phase 5: Image Shuffler GUI** 🎲

**Add to "Background Media" Tab:**

**New Group: "Playlist"**
```
┌─ Playlist ───────────────────────────────┐
│ Mode: [●Shuffle ○Sequential ○Random]     │
│                                          │
│ [Add Files...] [Add Folder...] [Clear]   │
│                                          │
│ ┌────────────────────────────────────┐   │
│ │ ✓ sunset.jpg          (1920x1080) │   │
│ │ ✓ ocean.gif           (1280x720)  │   │
│ │ ✗ video.mp4 (too large, skipped)  │   │
│ │ ✓ spiral_bg.webm      (1080x1080) │   │
│ │ ✓ abstract.png        (2560x1440) │   │
│ └────────────────────────────────────┘   │
│ 4 valid / 5 total                        │
│                                          │
│ ┌─ Shuffle Settings ──────────────────┐  │
│ │ Avoid Repeat: [===|======] Last 8    │ │
│ │ Min Duration: [====|=====] 10.0s     │ │
│ │ Max Duration: [=======|==] 30.0s     │ │
│ │                                      │ │
│ │ Weighted by: [None ▼]                │ │
│ │              [None/Duration/Size]    │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ Current: sunset.jpg (15.2s remaining)    │
│ Next:    abstract.png                    │
│                                          │
│ [▶ Start Playlist] [⏸ Pause] [⏭ Next]   │
└──────────────────────────────────────────┘
```

**Implementation:**
- QListWidget displays playlist with icons
- Checkboxes toggle item enable/disable
- Drag & drop to reorder (for sequential mode)
- Weighted shuffle uses file metadata
- Last-N tracking prevents recent repeats

**Code Hook:**
```python
# In BackgroundMediaPage
self.shuffler = ImageShuffler()
self.shuffler.add_files(paths)
self.shuffler.set_avoid_last_n(8)

def _next_item(self):
    path, duration = self.shuffler.next()
    self._load_media(path)
    self.switch_timer.setInterval(int(duration * 1000))
```

---

#### **Phase 6: Visual Programs GUI** 🎭

**New Tab: "Visual Programs"**  
Location: `mesmerglass/ui/pages/visual_programs.py`

**Controls:**
```
┌─ Visual Programs ────────────────────────┐
│                                          │
│ ┌─ Program Library ────────────────────┐ │
│ │ [New Program] [Import...] [Export]   │ │
│ │                                      │ │
│ │ ▼ My Programs                        │ │
│ │   • Hypnotic Induction (12:30)       │ │
│ │   • Deep Trance Loop (∞)             │ │
│ │   • Awakener (3:45)                  │ │
│ │                                      │ │
│ │ ▼ Trance Presets (built-in)          │ │
│ │   • Classic Spiral                   │ │
│ │   • Ocean Waves                      │ │
│ │   • Fractal Journey                  │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Program Editor: "Hypnotic Induction"┐ │
│ │ Duration: 12:30 (calculated)         │ │
│ │                                      │ │
│ │ ┌─ Visual Sequence ─────────────────┐ │ │
│ │ │ 1. [00:00] Image Set "Intro"     │ │ │
│ │ │    • 5 images, 10s each, fade    │ │ │
│ │ │                                  │ │ │
│ │ │ 2. [00:50] Video "Ocean Loop"    │ │ │
│ │ │    • ocean.webm, ping-pong, 2min │ │ │
│ │ │                                  │ │ │
│ │ │ 3. [02:50] Text Sequence         │ │ │
│ │ │    • 10 lines, 5s each, drift    │ │ │
│ │ │                                  │ │ │
│ │ │ 4. [03:40] Image Set "Deep"      │ │ │
│ │ │    • 8 images, 15s, kaleidoscope │ │ │
│ │ │                                  │ │ │
│ │ │ 5. [05:40] Blank (1min hold)     │ │ │
│ │ │                                  │ │ │
│ │ │ 6. [06:40] Return to Image Set 1 │ │ │
│ │ └──────────────────────────────────┘ │ │
│ │                                      │ │
│ │ [↑] [↓] [Add Visual] [Edit] [Delete] │ │
│ │                                      │ │
│ │ ┌─ Spiral Overlay (all visuals) ───┐ │ │
│ │ │ [☑] Enable during program        │ │ │
│ │ │ Intensity: [=====|====] 0.65     │ │ │
│ │ │ Evolution: [☑] Auto-evolve       │ │ │
│ │ └──────────────────────────────────┘ │ │
│ │                                      │ │
│ │ [Save Program] [Test Run] [Close]    │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ ┌─ Active Program Playback ────────────┐ │
│ │ Playing: "Hypnotic Induction"        │ │
│ │ Visual:  Image Set "Deep" (3/8)      │ │
│ │ Time:    04:23 / 12:30               │ │
│ │ [========|========================]  │ │
│ │                                      │ │
│ │ [⏸ Pause] [⏹ Stop] [⏭ Next Visual]  │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ [▶ Start Program...] (Dropdown selector) │
└──────────────────────────────────────────┘
```

**Implementation:**
- Programs stored as JSON (visual sequence + spiral config)
- Program player orchestrates shuffler, video streamer, text overlay
- Auto-switches between visual types based on timestamps
- Spiral overlay runs continuously with optional evolution
- Presets bundled with app, user programs saved to AppData

**Code Hook:**
```python
# In visual_programs.py
self.program_player = VisualProgramPlayer(
    self.compositor,
    self.director,
    self.shuffler,
    self.video_streamer,
    self.text_renderer
)

def _play_program(self, program_data):
    self.program_player.load(program_data)
    self.program_player.start()
    self.playback_timer.start(16)  # 60 FPS updates
```

---

### GUI Refactoring Strategy

#### Deprecate Legacy "Media" Tab
- Current overlay system (`overlay.py`) uses QPainter (slow, limited)
- Move functionality to new "Background Media" tab (GL-accelerated)
- Keep old tab for backward compatibility (show deprecation notice)

#### Consolidate Spiral Controls
- "MesmerLoom" tab already has comprehensive spiral controls
- Add "Background Interaction" group:
  ```
  ┌─ Background Interaction ─────────────┐
  │ Blend with Background: [☑] Enable   │
  │ Blend Mode: [Multiply ▼]            │
  │ Background Affects Spiral: [ ]      │
  │   (future: color sampling)          │
  └─────────────────────────────────────┘
  ```

#### Persistent Settings
- All new controls save to `~/.mesmerglass/config.json`
- Auto-restore on launch
- Export/Import profiles for sharing

#### Keyboard Shortcuts
```
Global shortcuts (work in spiral window):
- Ctrl+B: Toggle background visibility
- Ctrl+K: Toggle kaleidoscope
- Ctrl+T: Toggle text overlay
- Ctrl+Space: Play/pause program
- Ctrl+N: Next visual in program
- Ctrl+S: Toggle spiral overlay
- Ctrl+Q: Quit
```

---

### Testing Requirements Per Phase

Each phase MUST include GUI tests:

**Phase 1:**
- `test_gui_background_media.py` - Load image, play video, verify controls
- `test_gui_ping_pong.py` - Verify ping-pong mode toggle

**Phase 2:**
- `test_gui_zoom_animation.py` - Verify animation pattern switching
- `test_gui_zoom_controls.py` - Verify slider ranges and updates

**Phase 3:**
- `test_gui_text_sequence.py` - Add/edit/delete text lines
- `test_gui_font_selection.py` - Load custom fonts

**Phase 4:**
- `test_gui_cycler_tree.py` - Add/remove cyclers, drag & drop
- `test_gui_timeline_playback.py` - Play/pause/stop timeline

**Phase 5:**
- `test_gui_playlist.py` - Add files, shuffle, sequential modes
- `test_gui_shuffler_weights.py` - Verify weighted random

**Phase 6:**
- `test_gui_program_editor.py` - Create/edit/save programs
- `test_gui_program_playback.py` - Play program, verify visual switching

---

### Development Workflow

1. **Implement Backend** (e.g., VideoStreamer class)
2. **Create GUI Page** (e.g., BackgroundMediaPage)
3. **Wire Signals/Slots** (connect UI to backend)
4. **Add to Launcher** (`launcher.py` tabs)
5. **Write GUI Tests** (simulate user interactions)
6. **Update Docs** (screenshot + feature description)

This ensures GUI and backend stay synchronized throughout development.

---

## ✅ Completed Features

### Phase 0: Foundation (DONE)
- ✅ **Spiral System** - All 7 spiral types with cone intersection depth
- ✅ **Background Image Rendering** - Static images with aspect-ratio preservation
- ✅ **Kaleidoscope Effect** - 2x2 mirrored tiling for background images
- ✅ **Compositor Architecture** - Layered rendering (background → spiral overlay)

**Files Implemented:**
- `mesmerglass/mesmerloom/compositor.py` - Background rendering system
- `mesmerglass/mesmerloom/spiral.py` - 7-type spiral system
- `mesmerglass/engine/shaders/spiral.frag` - Spiral shader with cone intersection

### Phase 3: Text Overlay System (DONE)
- ✅ **TextRenderer** - Font loading, text-to-texture with PIL/Pillow, auto-cropping
- ✅ **TextAnimator** - 10 effects (FADE_IN, FLASH, PULSE, WOBBLE, DRIFT, ZOOM, TYPEWRITER, etc.)
- ✅ **Compositor Integration** - Text layer with proper alpha blending, global opacity control
- ✅ **Split Modes** - NONE, SPLIT_WORD, SPLIT_LINE, CHARACTER, FILL_SCREEN with carousel
- ✅ **Unit Tests** - 78 tests (61 passing, 78% coverage)

**Files Implemented:**
- `mesmerglass/content/text_renderer.py` (392 lines) - Text-to-texture rendering
- `mesmerglass/content/text_animator.py` (389 lines) - Animation effects
- `mesmerglass/mesmerloom/compositor.py` (updates) - Text overlay rendering
- `scripts/test_text_effects.py` (558 lines) - Interactive demo
- `mesmerglass/tests/test_text_renderer.py` (319 lines) - Unit tests
- `mesmerglass/tests/test_text_animator.py` (540 lines) - Unit tests

### Phase 4 & 5: Cycler System + Media Shuffler (DONE)
- ✅ **ActionCycler** - Execute callback every N frames (with offset support)
- ✅ **RepeatCycler** - Repeat child cycler N times with automatic reset
- ✅ **SequenceCycler** - Execute cyclers one after another sequentially
- ✅ **ParallelCycler** - Run multiple cyclers simultaneously
- ✅ **VisualDirector** - FPS-independent timing with frame accumulator pattern
- ✅ **Shuffler** - Weighted random selection with last-N anti-repetition tracking
- ✅ **Unit Tests** - 55 tests (100% passing)

**Files Implemented:**
- `mesmerglass/engine/cyclers.py` (315 lines) - Core cycler classes with composition
- `mesmerglass/engine/shuffler.py` (185 lines) - Weighted random shuffler
- `mesmerglass/engine/director.py` (176 lines) - Visual director with FPS control
- `mesmerglass/tests/test_cyclers.py` (482 lines) - Cycler unit tests
- `mesmerglass/tests/test_shuffler.py` (245 lines) - Shuffler unit tests

---

## 🎯 Implementation Roadmap

### Phase 1: Video Playback Support 🎬
**Priority:** HIGH - Foundation for all animated content  
**Estimated Complexity:** Medium-High  
**Dependencies:** OpenCV (already installed)

#### 1.1 Core Video Streaming
**Goal:** Play MP4/WebM videos as background layer behind spiral

**Requirements from Trance:**
- **Supported Formats:**
  - GIF (via giflib) - loaded entirely into memory
  - WebM (VP8/VP9 via libvpx) - streamed from disk
  - MP4 (via ffmpeg) - streamed from disk
  
- **Streaming Architecture:**
  ```
  Double-buffered system:
  - Buffer A: Currently playing video
  - Buffer B: Preloading next video in background
  - Circular buffer for frame storage
  - Async loading on separate thread
  ```

- **Playback Speed Formula:**
  ```python
  frame_advance_rate = (120 / global_fps) / 8
  # At 60 fps: 0.25 frames per update
  # Video advances every 4 screen refreshes
  ```

- **Ping-Pong Playback Mode:**
  - Video plays forward to end
  - Then plays backward to beginning
  - Creates seamless loop without pause
  - Direction tracked by boolean flag

**Implementation Steps:**

1. **Create Video Decoder** (`mesmerglass/content/video.py`):
   ```python
   class VideoDecoder:
       """Decode video files frame-by-frame."""
       def __init__(self, path: str):
           self.cap = cv2.VideoCapture(path)
           self.fps = self.cap.get(cv2.CAP_PROP_FPS)
           self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
       
       def read_frame(self) -> Optional[ImageData]:
           """Read next frame as ImageData."""
           pass
       
       def seek(self, frame_num: int):
           """Seek to specific frame."""
           pass
   ```

2. **Create Video Streamer** (`mesmerglass/content/video_streamer.py`):
   ```python
   class VideoStreamer:
       """Double-buffered async video streaming."""
       def __init__(self, buffer_size: int = 30):
           self.buffer_a = []  # Currently playing
           self.buffer_b = []  # Preloading
           self.current_frame = 0
           self.backwards = False  # Ping-pong direction
           self.update_counter = 0.0  # Fractional frame accumulator
       
       def advance_frame(self, global_fps: int = 60):
           """Advance to next frame with ping-pong logic."""
           # Accumulate fractional frames
           self.update_counter += (120.0 / global_fps) / 8.0
           
           # Only advance when counter >= 1.0
           while self.update_counter >= 1.0:
               self.update_counter -= 1.0
               
               if self.backwards:
                   self.current_frame -= 1
                   if self.current_frame <= 0:
                       self.backwards = False  # Reverse direction
               else:
                   self.current_frame += 1
                   if self.current_frame >= len(self.buffer_a) - 1:
                       self.backwards = True  # Reverse direction
       
       def get_current_frame(self) -> ImageData:
           """Get current frame for rendering."""
           pass
   ```

3. **Integrate with Compositor**:
   - Extend `set_background_texture()` to accept video frames
   - Add `set_background_video(video_path)` method
   - Update background every frame from video streamer
   - Upload new frame to GPU texture each update

4. **Add Video Controls**:
   - Play/pause toggle
   - Playback speed multiplier
   - Loop vs ping-pong mode selection

**Testing:**
- `scripts/test_video_playback.py` - Basic video rendering test
- `scripts/test_video_pingpong.py` - Verify ping-pong loop behavior
- Test with various formats: MP4, WebM, GIF
- Verify memory usage stays bounded (circular buffer)

**Success Criteria:**
- ✅ Can load and play MP4/WebM videos
- ✅ Smooth playback at 60fps
- ✅ Ping-pong mode works seamlessly (no pause at endpoints)
- ✅ Memory usage stays constant (no leaks)
- ✅ Video + spiral overlay renders correctly
- ✅ Works with kaleidoscope effect

---

### Phase 2: Image Zoom & Animation 🔍
**Priority:** HIGH - Makes content hypnotic  
**Estimated Complexity:** Medium  
**Dependencies:** Phase 1 (uses same rendering system)

#### 2.1 Zoom System
**Goal:** Smooth zoom-in/out animations over time

**Zoom Parameters from Trance:**
- **zoom_origin**: Starting depth [0.0 - 1.0]
  - 0.0 = image at far plane (distance)
  - 0.5 = halfway between far and near
  - 1.0 = image at near plane (closest)
  
- **zoom**: Ending depth [zoom_origin to 1.0]
  - Animates from zoom_origin toward viewer
  - Creates "zooming in" motion
  
- **Interpolation**: Linear blend over time
  ```
  current_zoom = zoom_origin + (zoom - zoom_origin) * progress
  where progress ∈ [0, 1]
  ```

**Zoom Patterns from Trance Visuals:**

1. **SubTextVisual Pattern:**
   ```python
   zoom_origin = 0.0
   zoom = 0.375 * progress  # Gentle zoom-in over 48 frames
   # Visual effect: Moderate approach over ~0.8 seconds
   ```

2. **AccelerateVisual Pattern:**
   ```python
   zoom_origin = 0.4 * global_progress  # Slow build over entire sequence
   zoom = zoom_origin + 0.1 * image_progress  # Quick pulse per image
   # Visual effect: Dual zoom (slow global + fast per-image)
   ```

3. **SlowFlashVisual Pattern:**
   ```python
   # Slow mode:
   zoom_origin = 0.25 * sequence_progress
   zoom = zoom_origin + 0.5 * image_progress  # Large motion per image
   
   # Fast mode:
   zoom_origin = frame_index / 48.0  # Discrete steps
   zoom = zoom_origin + 8.0 * image_progress / 48.0  # Rapid pulses
   ```

**Implementation Steps:**

1. **Update Background Fragment Shader**:
   ```glsl
   uniform float uZoomOrigin;  // Starting depth [0.0-1.0]
   uniform float uZoom;        // Ending depth [0.0-1.0]
   uniform float uZoomProgress; // Interpolation [0.0-1.0]
   
   void main() {
       // Calculate aspect ratios (already done)
       // ... existing aspect ratio code ...
       
       // Apply zoom interpolation
       float current_zoom = mix(uZoomOrigin, uZoom, uZoomProgress);
       
       // Scale UV coordinates based on zoom
       // Zoom > 1.0 = zoomed in (UVs scaled down)
       // Zoom < 1.0 = zoomed out (UVs scaled up)
       float zoom_scale = 1.0 / current_zoom;
       
       vec2 center = vec2(0.5, 0.5);
       uv = center + (uv - center) * zoom_scale;
       
       // Apply kaleidoscope AFTER zoom
       // ... existing kaleidoscope code ...
   }
   ```

2. **Add Zoom API to Compositor**:
   ```python
   def set_background_zoom_animation(
       self,
       zoom_origin: float = 1.0,
       zoom_target: float = 1.5,
       duration_seconds: float = 1.0
   ):
       """Animate zoom from origin to target over duration."""
       self._zoom_origin = max(0.1, min(5.0, zoom_origin))
       self._zoom_target = max(0.1, min(5.0, zoom_target))
       self._zoom_duration = duration_seconds
       self._zoom_start_time = time.time()
   ```

3. **Update Render Loop**:
   ```python
   def _render_background(self, w_px: float, h_px: float):
       # Calculate zoom progress
       if hasattr(self, '_zoom_start_time'):
           elapsed = time.time() - self._zoom_start_time
           progress = min(1.0, elapsed / self._zoom_duration)
           current_zoom = self._zoom_origin + (self._zoom_target - self._zoom_origin) * progress
       else:
           current_zoom = self._background_zoom
       
       # Set shader uniforms
       loc = GL.glGetUniformLocation(self._background_program, 'uZoomOrigin')
       if loc >= 0:
           GL.glUniform1f(loc, self._zoom_origin)
       
       loc = GL.glGetUniformLocation(self._background_program, 'uZoom')
       if loc >= 0:
           GL.glUniform1f(loc, self._zoom_target)
       
       loc = GL.glGetUniformLocation(self._background_program, 'uZoomProgress')
       if loc >= 0:
           GL.glUniform1f(loc, progress)
   ```

#### 2.2 Pan/Drift Animation
**Goal:** Slow panning motion across image

**Implementation:**
- Add `uPanOffset` uniform (vec2)
- Offset UV coordinates before zoom calculation
- Animate pan_x and pan_y over time
- Creates slow drift across image

**Drift Patterns:**
- Circular drift (orbit around center)
- Linear drift (left→right, top→bottom)
- Random walk drift (subtle jitter)

**Testing:**
- `scripts/test_zoom_animation.py` - Verify smooth zoom
- `scripts/test_zoom_patterns.py` - Test SubText/Accelerate patterns
- `scripts/test_pan_drift.py` - Verify drift animations

**Success Criteria:**
- ✅ Smooth zoom-in animations (no stuttering)
- ✅ Zoom works with both images and videos
- ✅ Kaleidoscope + zoom combination works
- ✅ Multiple zoom patterns available
- ✅ Pan/drift creates subtle motion

---

### Phase 3: Text Overlay System 📝
**Priority:** MEDIUM - Adds subliminal messaging  
**Estimated Complexity:** Medium-High  
**Dependencies:** Freetype2, PIL/Pillow

#### 3.1 Font Rendering
**Goal:** Render text with custom fonts over spiral

**Text Rendering in Trance:**
- **Font Support:** TTF/OTF via FreeType
- **Rendering Method:** Pre-render text to texture, blit to screen
- **Positioning:** Center-aligned with depth offset
- **Animation:** Fade in/out with alpha blending

**Text Types:**
1. **Main Text** - Large center text with fade
2. **Subtext** - Scrolling bottom text
3. **Flash Text** - Rapid alternating text

**Implementation Steps:**

1. **Create Text Renderer** (`mesmerglass/content/text_renderer.py`):
   ```python
   class TextRenderer:
       """Render text to OpenGL texture."""
       
       def __init__(self):
           from PIL import Image, ImageDraw, ImageFont
           self.font_cache = {}  # Cache loaded fonts
       
       def render_text(
           self,
           text: str,
           font_path: str,
           font_size: int = 48,
           color: tuple = (255, 255, 255, 255)
       ) -> ImageData:
           """Render text to RGBA image."""
           # Load font (cache it)
           if font_path not in self.font_cache:
               self.font_cache[font_path] = ImageFont.truetype(font_path, font_size)
           font = self.font_cache[font_path]
           
           # Calculate text size
           dummy_img = Image.new('RGBA', (1, 1))
           draw = ImageDraw.Draw(dummy_img)
           bbox = draw.textbbox((0, 0), text, font=font)
           width = bbox[2] - bbox[0] + 20  # Add padding
           height = bbox[3] - bbox[1] + 20
           
           # Create image and draw text
           img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
           draw = ImageDraw.Draw(img)
           draw.text((10, 10), text, font=font, fill=color)
           
           # Convert to ImageData
           return ImageData(
               width=width,
               height=height,
               data=np.array(img),
               path=Path(f"text_{hash(text)}.png")
           )
   ```

2. **Add Text Layer to Compositor**:
   ```python
   def set_text_overlay(
       self,
       text: str,
       font_path: str,
       position: tuple = (0.5, 0.5),  # Normalized [0-1]
       alpha: float = 1.0,
       depth: float = 0.0  # Zoom depth like images
   ):
       """Set text overlay with positioning."""
       # Render text to texture
       text_image = self.text_renderer.render_text(text, font_path)
       text_texture = upload_image_to_gpu(text_image)
       
       # Store text state
       self._text_texture = text_texture
       self._text_position = position
       self._text_alpha = alpha
       self._text_depth = depth
   ```

3. **Render Text Layer**:
   ```python
   def _render_text(self, w_px: float, h_px: float):
       """Render text overlay after spiral."""
       if not hasattr(self, '_text_texture'):
           return
       
       # Use separate text shader program
       # Renders quad at specified position with alpha blend
       # Apply depth offset for zoom consistency
   ```

#### 3.2 Text Sequences
**Goal:** Cycle through multiple text strings with timing

**Text Cycling from Trance:**
```python
# SubTextVisual text pattern
# Resets every 4 frames, cycles through words
text_reset = ActionCycler(4, lambda: change_text(SPLIT_WORD))
text = ActionCycler(4, lambda: change_text(SPLIT_ONCE_ONLY))
text_loop = SequenceCycler([text_reset, RepeatCycler(23, text)])
```

**Text Splitting Modes:**
- `SPLIT_WORD` - Split text by whitespace, show one word
- `SPLIT_ONCE_ONLY` - Show entire string at once
- `SPLIT_CHARACTER` - Show one character at a time

**Implementation:**
```python
class TextSequence:
    """Manage cycling text sequences."""
    
    def __init__(self, text_lines: list[str], mode: str = 'word'):
        self.lines = text_lines
        self.mode = mode
        self.current_index = 0
        self.words = self._split_text()
    
    def _split_text(self) -> list[str]:
        """Split text based on mode."""
        if self.mode == 'word':
            return ' '.join(self.lines).split()
        elif self.mode == 'line':
            return self.lines
        elif self.mode == 'character':
            return list(''.join(self.lines))
    
    def next(self) -> str:
        """Get next text in sequence."""
        text = self.words[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.words)
        return text
```

**Testing:**
- `scripts/test_text_rendering.py` - Basic font rendering
- `scripts/test_text_fade.py` - Alpha fade animations
- `scripts/test_text_sequence.py` - Cycling text

**Success Criteria:**
- ✅ Can render custom TTF/OTF fonts
- ✅ Text appears over spiral with proper alpha blend
- ✅ Text sequences cycle correctly
- ✅ Different split modes work (word/line/character)
- ✅ Text + image + spiral all render together

---

### Phase 4 & 5: Cycler System + Media Shuffler ⏱️🎲
**Priority:** HIGH - Foundation for playlist + anti-repetition  
**Estimated Complexity:** Medium  
**Dependencies:** None (pure timing logic + weighted random)

#### 4.1 Core Cycler Classes
**Goal:** Frame-accurate timing system for all animations

**Cycler Architecture from Trance:**

```cpp
// Base cycler interface
class Cycler {
public:
    virtual void advance() = 0;      // Advance by 1 frame
    virtual bool complete() = 0;     // Is cycler finished?
    virtual uint32_t length() = 0;   // Total frames
    virtual float progress() = 0;    // Progress [0.0-1.0]
    virtual uint32_t index() = 0;    // Current frame index
};
```

**Implementation:**

1. **ActionCycler** - Execute callback every N frames:
   ```python
   class ActionCycler:
       """Execute action every N frames, optionally at offset."""
       
       def __init__(self, period: int, action: callable, offset: int = 0):
           self.period = period
           self.action = action
           self.offset = offset
           self.frame = 0
       
       def advance(self):
           """Advance by 1 frame."""
           if self.frame >= self.offset and (self.frame - self.offset) % self.period == 0:
               self.action()
           self.frame += 1
       
       def complete(self) -> bool:
           """Action cyclers never complete."""
           return False
       
       def progress(self) -> float:
           """Progress within current period."""
           return ((self.frame - self.offset) % self.period) / self.period
   ```

2. **RepeatCycler** - Repeat child cycler N times:
   ```python
   class RepeatCycler:
       """Repeat a child cycler N times."""
       
       def __init__(self, count: int, child: Cycler):
           self.count = count
           self.child = child
           self.repetition = 0
       
       def advance(self):
           self.child.advance()
           if self.child.complete():
               self.repetition += 1
               self.child.reset()
       
       def complete(self) -> bool:
           return self.repetition >= self.count
       
       def length(self) -> int:
           return self.child.length() * self.count
   ```

3. **SequenceCycler** - Run cyclers one after another:
   ```python
   class SequenceCycler:
       """Execute cyclers in sequence."""
       
       def __init__(self, children: list[Cycler]):
           self.children = children
           self.current_index = 0
       
       def advance(self):
           if self.current_index < len(self.children):
               self.children[self.current_index].advance()
               if self.children[self.current_index].complete():
                   self.current_index += 1
       
       def complete(self) -> bool:
           return self.current_index >= len(self.children)
   ```

4. **ParallelCycler** - Run multiple cyclers simultaneously:
   ```python
   class ParallelCycler:
       """Execute multiple cyclers in parallel."""
       
       def __init__(self, children: list[Cycler]):
           self.children = children
       
       def advance(self):
           for child in self.children:
               if not child.complete():
                   child.advance()
       
       def complete(self) -> bool:
           return all(c.complete() for c in self.children)
   ```

#### 4.2 Global FPS System
**Goal:** Control animation speed independent of screen refresh

**FPS Control from Trance:**
```python
# Global FPS determines cycler speed, not render speed
global_fps = 60  # Typical value

# Update loop (called every screen refresh ~60Hz)
def update():
    visual.cycler().advance()  # Advance by 1 logical frame
    if visual.cycler().complete():
        switch_to_next_visual()
```

**Implementation:**
```python
class VisualDirector:
    """Manages visual program execution with FPS control."""
    
    def __init__(self, global_fps: int = 60):
        self.global_fps = global_fps
        self.current_visual = None
        self.frame_accumulator = 0.0
        self.last_update = time.time()
    
    def update(self):
        """Update visual state (called every render frame)."""
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        
        # Accumulate frames based on FPS
        self.frame_accumulator += dt * self.global_fps
        
        # Advance logical frames
        while self.frame_accumulator >= 1.0:
            self.frame_accumulator -= 1.0
            
            if self.current_visual:
                self.current_visual.cycler.advance()
                
                if self.current_visual.cycler.complete():
                    self.switch_visual()
```

**Testing:**
- `tests/test_cyclers.py` - Unit tests for all cycler types
- `tests/test_shuffler.py` - Verify weighted random distribution
- `scripts/test_cycler_timing.py` - Verify frame-accurate timing
- `scripts/test_fps_control.py` - Test FPS independence
- `scripts/test_anti_repetition.py` - Ensure no repeats within last 8

**Success Criteria:**
- ✅ Cyclers execute frame-accurately
- ✅ Nested cyclers work (Repeat(Sequence(Parallel(...))))
- ✅ FPS can be changed without breaking timing
- ✅ Progress calculations are correct
- ✅ Shuffler random distribution matches weights
- ✅ Recently shown images have lower probability
- ✅ Oldest images (>8 ago) restore to normal probability

#### 4.2 Weighted Random Media Selection
**Goal:** Select images/videos randomly while avoiding recent repeats

**Shuffler Algorithm from Trance:**

```cpp
// From src/trance/util/shuffler.h
class Shuffler {
    std::vector<uint32_t> _weights;  // Weight per item
    std::size_t _total_weight;
    
    uint32_t next() {
        // Weighted random selection
        uint32_t value = random(_total_weight);
        for (uint32_t i = 0; i < _weights.size(); ++i) {
            if (value < _weights[i]) {
                return i;
            }
            value -= _weights[i];
        }
    }
    
    void increase(uint32_t index) {
        _weights[index] += 1;
        _total_weight += 1;
    }
    
    void decrease(uint32_t index) {
        if (_weights[index] > 0) {
            _weights[index] -= 1;
            _total_weight -= 1;
        }
    }
};
```

**Last-8 Tracking from ThemeBank:**
```cpp
std::deque<std::size_t> _last_images;  // Last 8 image indices
const std::size_t last_image_count = 8;

Image get_image() {
    // Select image using shuffler
    index = shuffler.next();
    
    // Decrease weight of selected image
    _last_images.push_back(index);
    for (auto& theme : _themes) {
        theme->image_shuffler.decrease(_last_images.back());
        
        // Restore weight of image that fell off the list
        if (_last_images.size() > last_image_count) {
            theme->image_shuffler.increase(_last_images.front());
        }
    }
    
    // Keep only last 8
    if (_last_images.size() > last_image_count) {
        _last_images.erase(_last_images.begin());
    }
    
    return image;
}
```

**Implementation:**

```python
class ImageShuffler:
    """Weighted random image selection with anti-repetition."""
    
    def __init__(self, image_count: int, initial_weight: int = 10):
        self.weights = [initial_weight] * image_count
        self.total_weight = initial_weight * image_count
        self.last_indices = []  # Last 8 images shown
        self.max_history = 8
    
    def next(self) -> int:
        """Select next image index using weighted random."""
        import random
        
        value = random.randint(0, self.total_weight - 1)
        for i, weight in enumerate(self.weights):
            if value < weight:
                # Decrease weight of selected image
                self._track_selection(i)
                return i
            value -= weight
        
        return 0  # Fallback
    
    def _track_selection(self, index: int):
        """Track selected image and adjust weights."""
        # Add to history
        self.last_indices.append(index)
        
        # Decrease weight of selected image
        self.decrease(index)
        
        # Restore weight of oldest image if needed
        if len(self.last_indices) > self.max_history:
            oldest = self.last_indices.pop(0)
            self.increase(oldest)
    
    def increase(self, index: int):
        """Increase selection probability."""
        self.weights[index] += 1
        self.total_weight += 1
    
    def decrease(self, index: int):
        """Decrease selection probability."""
        if self.weights[index] > 0:
            self.weights[index] -= 1
            self.total_weight -= 1
```

---

### Phase 6: Visual Programs (Playlist Engine) 🎬
**Priority:** HIGH - The actual playlist system!  
**Estimated Complexity:** High  
**Dependencies:** Phases 1-3, Phase 4+5 (cycler + shuffler)

#### 6.1 Visual Program Types
**Goal:** Implement Trance's 7 visual program types

**Visual Types to Implement:**

1. **SimpleVisual** - Basic slideshow:
   ```python
   class SimpleVisual:
       """Basic image slideshow with zoom."""
       
       def __init__(self, compositor, shuffler, global_fps=60):
           # Change image every 48 frames (~0.8s at 60fps)
           image_cycler = ActionCycler(48, lambda: self._next_image())
           
           # Preload next image at frame 24
           preload_cycler = ActionCycler(48, lambda: self._preload_next(), offset=24)
           
           # Rotate spiral every frame
           spiral_cycler = ActionCycler(1, lambda: compositor.rotate_spiral(2.0))
           
           # Run in parallel, repeat 16 times
           main_loop = RepeatCycler(16, ParallelCycler([
               image_cycler,
               preload_cycler
           ]))
           
           self.cycler = ParallelCycler([spiral_cycler, main_loop])
       
       def _next_image(self):
           """Load next image from shuffler."""
           index = self.shuffler.next()
           # Load and display image
       
       def _preload_next(self):
           """Preload next image in background."""
           # Async load to GPU
   ```

2. **SubTextVisual** - Images with scrolling text:
   ```python
   class SubTextVisual:
       """Images with cycling text overlay."""
       
       def __init__(self, compositor, shuffler, text_lines, global_fps=60):
           # Image every 48 frames
           image_cycler = ActionCycler(48, lambda: self._next_image())
           
           # Text resets every 4 frames, cycles through words
           text_reset = ActionCycler(4, lambda: self._reset_text())
           text_cycle = ActionCycler(4, lambda: self._next_text())
           text_loop = SequenceCycler([
               text_reset,
               RepeatCycler(23, text_cycle)
           ])
           
           # Subtext at different speeds (12/24/48 frames)
           subtext_slow = ActionCycler(12, lambda: self._next_subtext())
           subtext_med = ActionCycler(24, lambda: self._next_subtext())
           subtext_fast = ActionCycler(48, lambda: self._next_subtext())
           
           # Everything in parallel, repeat 16 times
           main = RepeatCycler(16, ParallelCycler([
               image_cycler,
               text_loop,
               subtext_slow,
               subtext_med,
               subtext_fast
           ]))
           
           spiral = ActionCycler(1, lambda: compositor.rotate_spiral(4.0))
           self.cycler = ParallelCycler([spiral, main])
   ```

3. **AccelerateVisual** - Accelerating slideshow:
   ```python
   class AccelerateVisual:
       """Images that accelerate in display speed."""
       
       def __init__(self, compositor, shuffler, global_fps=60):
           self.image_length = 56  # Start at 56 frames
           self.min_length = 12    # Accelerate to 12 frames
           
           # Dynamic cycler that changes period
           def create_image_cycler():
               return ActionCycler(self.image_length, lambda: self._next_image())
           
           # After each image, reduce length
           def on_image_complete():
               self.image_length = max(self.min_length, self.image_length - 1)
               # Zoom origin increases: 0.4 * progress
               # Rotation speed increases: 1.0 + (56-length)/16
           
           # ... build cycler structure
   ```

4. **SlowFlashVisual** - Alternating slow/fast cycles:
   - Slow mode: 64 frames per image, 16 repetitions
   - Fast mode: 8 frames per image, 32 repetitions
   - Alternates between modes

5. **FlashTextVisual** - Rapid text flashing
6. **ParallelVisual** - Multiple images simultaneously
7. **AnimationVisual** - Focus on video/animation

#### 6.2 Visual Director
**Goal:** Manage switching between visual programs

```python
class VisualDirector:
    """Manages execution of visual programs."""
    
    def __init__(self, compositor, shuffler, global_fps=60):
        self.compositor = compositor
        self.shuffler = shuffler
        self.global_fps = global_fps
        self.current_visual = None
        self.visual_types = [
            SimpleVisual,
            SubTextVisual,
            AccelerateVisual,
            SlowFlashVisual,
            # ... etc
        ]
    
    def start(self):
        """Start first visual program."""
        self.switch_visual()
    
    def update(self):
        """Update current visual (called every frame)."""
        if not self.current_visual:
            return
        
        # Advance cycler
        self.current_visual.cycler.advance()
        
        # Switch when complete
        if self.current_visual.cycler.complete():
            self.switch_visual()
    
    def switch_visual(self):
        """Switch to random visual type."""
        import random
        VisualClass = random.choice(self.visual_types)
        self.current_visual = VisualClass(
            self.compositor,
            self.shuffler,
            self.global_fps
        )
```

**Testing:**
- `scripts/test_simple_visual.py` - Basic slideshow
- `scripts/test_subtext_visual.py` - Text + images
- `scripts/test_accelerate_visual.py` - Verify acceleration
- `scripts/test_visual_switching.py` - Auto-switch between types

**Success Criteria:**
- ✅ SimpleVisual runs full cycle (16 images)
- ✅ SubTextVisual shows text + images correctly
- ✅ AccelerateVisual speeds up over time
- ✅ Visual programs auto-switch when complete
- ✅ No memory leaks during long runs
- ✅ All timing is frame-accurate

---

## 📊 Implementation Timeline

### Week 1-2: Video Playback (Phase 1)
- Day 1-3: Video decoder + basic playback
- Day 4-5: Double-buffered streaming
- Day 6-7: Ping-pong mode + integration
- Testing: MP4/WebM playback with spiral overlay

### Week 3: Zoom & Animation (Phase 2)
- Day 1-2: Shader updates for zoom
- Day 3-4: Zoom API + interpolation
- Day 5: Pan/drift animations
- Testing: Various zoom patterns

### Week 4: Text Overlay (Phase 3)
- Day 1-2: Text renderer with fonts
- Day 3-4: Text sequences + cycling
- Day 5: Integration with compositor
- Testing: Text + image + spiral rendering

### Week 5: Cycler System + Shuffler (Phase 4+5)
- Day 1-2: Core cycler classes (Action, Repeat, Sequence, Parallel)
- Day 3-4: Nested cycler composition + FPS control system
- Day 5: Weighted shuffler + last-8 tracking
- Testing: Frame-accurate timing + anti-repetition verification

### Week 6-7: Visual Programs (Phase 6)
- Week 6: SimpleVisual, SubTextVisual, AccelerateVisual
- Week 7: Remaining visual types + director
- Testing: Full playlist system end-to-end

---

## 📚 Key Trance Documentation References

### Video Playback Details
**Source:** `SPIRAL_AND_MEDIA_DOCUMENTATION.md` lines 403-536

- **AsyncStreamer architecture** (double-buffered)
- **Ping-pong playback mode** (forward then backward)
- **Frame advancement formula:** `(120 / global_fps) / 8`
- **Buffer management:** Circular buffer, async loading

### Zoom Mathematics
**Source:** `SPIRAL_AND_MEDIA_DOCUMENTATION.md` lines 704-829

- **Zoom parameters:** zoom_origin, zoom, interpolation
- **SubTextVisual pattern:** `zoom = 0.375 * progress`
- **AccelerateVisual pattern:** Dual zoom (global + per-image)
- **SlowFlashVisual pattern:** Large motion (0.5 zoom range)

### Cycler System
**Source:** `SPIRAL_AND_MEDIA_DOCUMENTATION.md` lines 537-703

- **ActionCycler:** Execute every N frames
- **RepeatCycler:** Repeat child N times
- **SequenceCycler:** One after another
- **ParallelCycler:** Simultaneous execution
- **Frame timing examples:** SubTextVisual timeline table

### Shuffler Algorithm
**Source:** `SPIRAL_AND_MEDIA_DOCUMENTATION.md` lines 343-401

- **Weighted random selection**
- **Last-8 image tracking**
- **Weight adjustment:** decrease on select, increase on age-out
- **Theme management:** Multiple active themes

### Visual Program Examples
**Source:** `SPIRAL_AND_MEDIA_DOCUMENTATION.md` lines 600-703

- **SubTextVisual:** Complete implementation with timeline
- **AccelerateVisual:** Acceleration formula
- **SlowFlashVisual:** Slow/fast mode switching

---

## 🔧 Technical Notes

### Memory Management
- **Video buffers:** Keep 30 frames max (~7.2MB at 1080p)
- **Texture cache:** Reuse GPU textures when possible
- **Font cache:** Load fonts once, reuse for all text
- **Image preloading:** Background thread for next image

### Performance Targets
- **Target FPS:** 60fps rock-solid
- **Video playback:** Smooth at 30fps source material
- **Texture upload:** < 5ms for 1080p image
- **Cycler overhead:** < 0.1ms per frame

### Platform Considerations
- **Windows:** Use OpenCV VideoCapture with DirectShow backend
- **OpenGL:** Requires 3.3 core profile minimum
- **Threading:** QThread for async image/video loading

---

## ✅ Testing Strategy

### Unit Tests
- Cycler timing accuracy
- Shuffler distribution
- Text rendering output
- Video frame extraction

### Integration Tests
- Video + spiral rendering
- Text + image + spiral layering
- Visual program execution
- Memory leak detection

### Visual Tests
- Interactive test scripts for each feature
- Side-by-side with Trance for comparison
- User acceptance testing

---

## 📝 Documentation Tasks

After each phase:
1. Update this plan with completion status
2. Document API in `docs/technical/`
3. Add usage examples to `docs/user-guide/`
4. Update ROADMAP.md with progress

---

