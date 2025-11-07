# Independent Text Control System

## Overview

The text system has been completely decoupled from Visual Programs, giving you precise control over all text overlays through a dedicated **Text** tab.

## Architecture

### Components

1. **TextDirector** (`mesmerglass/engine/text_director.py`)
   - Core text orchestration engine
   - Handles text cycling, mode transitions, and rendering
   - Runs independently from Visual Programs
   - Updates at 60 FPS via compositor integration

2. **TextTab** (`mesmerglass/ui/text_tab.py`)
   - User interface for text control
   - Real-time parameter adjustment
   - Text library management with weights
   - Mode selection and timing controls

3. **Integration Points**
   - Connected to `LoomCompositor.paintGL()` loop
   - Uses existing `TextRenderer` for rendering
   - Independent of `VisualDirector`

## Text Modes

### 1. **Off**
- Disables all text overlays
- Clears any existing text from screen

### 2. **Static**
- Displays text for a fixed duration
- Clean, simple text changes
- Best for: Clear, readable messages

**Parameters:**
- Duration per Text: How long each text appears (1-600 seconds)

### 3. **Flash**
- Rapid on/off blinking
- Strobe-like effect
- Best for: Attention-grabbing, trance induction

**Parameters:**
- Duration per Text: How long before changing text
- Flash Speed: Frames per flash cycle (1-60)
  - Lower = faster flashing
  - Default: 8 frames (~7.5 Hz at 60 FPS)

### 4. **Fade**
- Smooth fade in/out transitions
- Gentle, professional appearance
- Best for: Relaxing, non-jarring text

**Technical:**
- 0.5 second fade in
- Full visibility in middle
- 0.5 second fade out
- Total duration set by "Duration per Text"

### 5. **Pulse**
- Size and opacity variation (sine wave)
- Breathing effect
- Best for: Dynamic, hypnotic display

**Technical:**
- 1 second pulse period
- Opacity: 70%-100%
- Scale: 90%-110%
- Continuous smooth animation

### 6. **Scroll**
- Text moves left to right across screen
- Band/marquee style
- Best for: Subconscious messaging, background text

**Technical:**
- 2 second scroll period
- Starts off-screen left (-20%)
- Ends off-screen right (120%)
- Wraps seamlessly

## Display Parameters

### Scale
- Range: 10%-500%
- Default: 150%
- Controls text size multiplier
- Independent of window resolution

### Opacity
- Range: 0%-100%
- Default: 100%
- Controls text transparency
- Applied in addition to mode-specific opacity (e.g., fade, pulse)

### Position X
- Range: 0%-100%
- Default: 50% (center)
- Horizontal position
- 0% = left edge, 100% = right edge

### Position Y
- Range: 0%-100%
- Default: 50% (center)
- Vertical position
- 0% = top edge, 100% = bottom edge

## Text Library Management

### Weight System

Each text has a **weight** (0%-100%) controlling its selection probability:

- **100% weight**: Normal probability
- **50% weight**: Half as likely to appear
- **0% weight**: Never appears (but stays enabled)

**Example:**
```
"Obey" - 100% weight - Will appear often
"Submit" - 100% weight - Will appear often
"Good toy" - 50% weight - Will appear half as often
"Mindless" - 25% weight - Will appear quarter as often
```

### Weighted Random Selection

The system uses weighted random selection:

1. Calculate total weight of all enabled texts
2. Generate random number in range [0, total_weight]
3. Walk through texts, accumulating weights
4. Select text when cumulative weight exceeds random number

**Result:** Higher weight = more frequent appearance, but still random.

### Enable/Disable

- **Checkbox**: Toggle individual texts on/off
- Disabled texts are completely excluded from rotation
- Weight slider is disabled when text is disabled

### Bulk Actions

1. **Enable All**: Turn on all texts
2. **Disable All**: Turn off all texts
3. **Reset Weights**: Set all weights to 100%

## Default Text Library

Ships with 20 default texts:

**Commands:**
- "Obey"
- "Submit"
- "Comply"

**States:**
- "Good toy"
- "Mindless"
- "Empty"
- "Blank"
- "Compliant"
- "Docile"
- "Entranced"

**Deepening:**
- "Drop deeper"
- "Drift down"
- "Let go"
- "Deeper and deeper"
- "Sleep"
- "Relax"

**Focus:**
- "Watch the spiral"
- "Focus on my words"
- "You are hypnotized"
- "No thoughts"
- "Just watch"

## Usage Guide

### Basic Setup

1. **Select Mode**
   - Choose from dropdown (Off, Static, Flash, Fade, Pulse, Scroll)

2. **Adjust Timing**
   - Set "Duration per Text" (how long each text appears)
   - For Flash mode: Adjust "Flash Speed"

3. **Configure Display**
   - Scale: Text size
   - Opacity: Text transparency
   - Position X/Y: Screen location

4. **Select Texts**
   - Enable/disable specific texts
   - Adjust weights for frequency control

5. **Launch**
   - Go to Displays tab
   - Check desired monitors
   - Click Launch

### Advanced Techniques

#### Subliminal Messaging
- Mode: **Flash** (8 frames = ~133ms per flash)
- Opacity: **30%-50%**
- Duration: **0.5-1 second**
- Scale: **100%-120%**

#### Hypnotic Deepening
- Mode: **Pulse** or **Fade**
- Opacity: **80%-100%**
- Duration: **3-5 seconds**
- Scale: **150%-200%**
- Texts: Select only deepening phrases

#### Background Reinforcement
- Mode: **Scroll**
- Opacity: **40%-60%**
- Duration: **1-2 seconds**
- Position Y: **10%** or **90%** (top/bottom edge)
- Scale: **80%-100%**

#### Command Emphasis
- Mode: **Static** or **Flash**
- Opacity: **100%**
- Duration: **2-3 seconds**
- Scale: **200%-250%**
- Texts: Only command words ("Obey", "Submit", "Comply")

## Integration with Visual Programs

### Independent Operation

Text Director runs **completely independently** from Visual Programs:

- Visual Programs controls background images/videos
- Text Director controls text overlays
- Both can run simultaneously
- No conflicts or interference

### Recommended Combinations

**1. Video + Text Scroll**
- Visual Programs: Video Playback
- Text Mode: Scroll (opacity 50%)
- Creates layered effect with background reinforcement

**2. Images + Text Flash**
- Visual Programs: Simple Visual
- Text Mode: Flash (8 frames)
- Synchronized subliminal messaging

**3. Text Only**
- Visual Programs: Off (or minimal background)
- Text Mode: Static/Pulse (large, centered)
- Pure text-based trance

## Performance

### Update Frequency
- Text Director updates at 60 FPS (connected to compositor paintGL loop)
- Mode transitions are frame-perfect
- No stuttering or dropped frames

### Rendering
- Uses existing TextRenderer (shared with Visual Programs)
- Efficient texture caching
- Minimal GPU overhead

### Memory
- Text library stored in memory (negligible size)
- Rendered textures cached per-frame
- No leaks or accumulation

## Troubleshooting

### Text Not Appearing

**Check:**
1. Mode is not set to "Off"
2. At least one text is enabled (checkbox checked)
3. Enabled texts have weight > 0
4. Opacity is not 0%
5. Spiral window is launched (not just preview)

### Text Flickering

**Cause:** Flash mode with very low frame count
**Solution:** Increase "Flash Speed" value (higher = slower)

### Text Too Small/Large

**Adjust:** Scale slider (10%-500%)
**Note:** Position may need adjustment after scale changes

### Text Not Changing

**Check:**
1. Duration per Text is not extremely high
2. Multiple texts are enabled
3. Application is not paused/frozen

### Text Position Wrong

**Remember:** 
- Position is **center** of text, not top-left corner
- Large text (high scale) may exceed screen boundaries
- Adjust X/Y to compensate for scale

## Technical Details

### Frame Timing

At 60 FPS:
- 1 frame = ~16.67ms
- 60 frames = 1 second
- Flash (8 frames) = ~133ms per cycle = 7.5 Hz
- Fade transition (30 frames) = 0.5 seconds

### Mode State Machines

Each mode maintains internal state:
- `_frame_counter`: Frames elapsed since text change
- `_frames_per_text`: Duration converted to frames
- `_state.visible`: Whether to render text this frame
- `_state.opacity`: Current opacity (0.0-1.0)
- `_state.scale`: Current scale multiplier
- `_state.x`, `_state.y`: Current position

### Weighted Selection Algorithm

```python
enabled = [e for e in texts if e.enabled and e.weight > 0]
total_weight = sum(e.weight for e in enabled)
r = random.random() * total_weight

cumulative = 0.0
for entry in enabled:
    cumulative += entry.weight
    if r <= cumulative:
        select(entry.text)
        break
```

## Future Enhancements

Potential additions:
- Custom text import (CSV, TXT files)
- Text grouping/categories
- Per-text timing overrides
- Color variation per text
- Font selection per text
- Multi-line text support
- Animation presets
- Text effects (shadow, outline, glow)

## See Also

- [Visual Programs Documentation](visual-programs.md)
- [Spiral Overlay Documentation](spiral-overlay.md)
- [Text Rendering Technical Details](../technical/text-rendering.md)
