# Cuelist System Implementation Plan

**Project:** MesmerGlass Cuelist/Session System  
**Version:** 1.0  
**Date:** November 8, 2025  
**Status:** Planning Phase

---

## 📋 Executive Summary

This document outlines the complete implementation plan for adding a **Cuelist/Session System** to MesmerGlass. The system will enable users to create complex, timed hypnosis sessions by sequencing "Cues" that dynamically select from pools of visual "Playbacks" (formerly called Modes).

**Key Innovation:** All transitions (cue changes, playback switches) are **synchronized to media cycle boundaries** for natural, rhythm-preserving flow.

---

## 🎯 Goals & Requirements

### Primary Goals
1. Enable creation of multi-segment hypnosis sessions (Cuelists)
2. Support dynamic playback variation within segments (weighted pools)
3. Ensure smooth, cycle-synchronized transitions
4. Integrate per-cue audio tracks with fade coordination
5. Maintain backward compatibility with existing Mode/Playback system

### Success Criteria
- ✅ Users can create cuelists via JSON or UI
- ✅ Session Runner executes cuelists with perfect cycle sync
- ✅ Playback selection respects weights and cycle constraints
- ✅ Audio fades align with visual transitions
- ✅ Existing playback files work without modification
- ✅ All transitions occur only at media cycle boundaries

---

## 📚 Terminology

| Term | Definition | Example |
|------|------------|---------|
| **Playback** | Visual preset (spiral + media + text settings) | "Deep Spiral Red.json" |
| **Cue** | Timed segment with playback pool + audio | "Induction" cue (5 min, 3 playbacks) |
| **Cuelist** | Ordered sequence of cues forming a session | "Full Session.cuelist.json" |
| **Playback Pool** | List of possible playbacks for a cue (weighted) | [Playback A: 60%, B: 30%, C: 10%] |
| **Cycle Boundary** | Media cycle completion point (image/video change) | Every 48 frames (0.8s) for speed=50 |
| **Session Runner** | Execution engine that orchestrates cuelist playback | Core timing/transition controller |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SESSION RUNNER                          │
│  (Orchestrates cue progression & cycle-synced transitions)  │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   CUELIST   │ │   VISUAL    │ │    AUDIO    │
│  (Timeline) │ │  DIRECTOR   │ │   ENGINE    │
└─────────────┘ └─────────────┘ └─────────────┘
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│    CUES     │ │  PLAYBACKS  │ │   TRACKS    │
│  (Segments) │ │  (Presets)  │ │  (Files)    │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## 📦 Data Models

### Playback (Renamed from Mode)
**Location:** `mesmerglass/playbacks/*.json`  
**Format:** Existing mode JSON format (no changes to structure)

```json
{
  "name": "Deep Spiral Red",
  "version": "1.0",
  "spiral": {
    "type": 3,
    "rotation_speed": 60.0,
    "reverse": false,
    "intensity": 0.8,
    "width": 60,
    "arm_color": [1.0, 0.2, 0.2],
    "gap_color": [0.0, 0.0, 0.0]
  },
  "media": {
    "mode": "images",
    "cycle_speed": 50,
    "use_theme_bank": true,
    "opacity": 0.7,
    "zoom_enabled": true,
    "zoom_duration": 300,
    "zoom_target": 1.5
  },
  "text": {
    "enabled": true,
    "cycle_frames": 240
  }
}
```

### Playback Entry
**Python Class:** `PlaybackEntry` (in `session/cue.py`)

```python
@dataclass
class PlaybackEntry:
    playback_path: Path          # Path to playback JSON file
    weight: float = 1.0          # Selection probability weight
    min_cycles: Optional[int] = None  # Min cycles before switch allowed
    max_cycles: Optional[int] = None  # Max cycles before forced switch
```

**JSON Format:**
```json
{
  "playback": "playbacks/deep_spiral_red.json",
  "weight": 2.0,
  "min_cycles": 3,
  "max_cycles": 10
}
```

### Audio Track
**Python Class:** `AudioTrack` (in `session/cue.py`)

```python
@dataclass
class AudioTrack:
    file_path: Path
    volume: float = 1.0          # 0.0 to 1.0
    loop: bool = False
    fade_in_ms: float = 500
    fade_out_ms: float = 500
```

**JSON Format:**
```json
{
  "file": "audio/binaural_theta.mp3",
  "volume": 0.8,
  "loop": true,
  "fade_in_ms": 1000,
  "fade_out_ms": 1000
}
```

### Transition
**Python Class:** `CueTransition` (in `session/cue.py`)

```python
@dataclass
class CueTransition:
    type: str = "none"           # "none", "fade", "interpolate"
    duration_ms: float = 500
    wait_for_cycle: bool = True  # Always True (enforced)
```

**JSON Format:**
```json
{
  "type": "fade",
  "duration_ms": 1000
}
```

### Cue
**Python Class:** `Cue` (in `session/cue.py`)

```python
class PlaybackSelectionMode(Enum):
    ON_CUE_START = "on_cue_start"
    ON_MEDIA_CYCLE = "on_media_cycle"
    ON_TIMED_INTERVAL = "on_timed_interval"

@dataclass
class Cue:
    name: str
    duration_seconds: float
    playback_pool: List[PlaybackEntry]
    selection_mode: PlaybackSelectionMode = PlaybackSelectionMode.ON_CUE_START
    selection_interval_seconds: Optional[float] = None
    transition_in: CueTransition = field(default_factory=CueTransition)
    transition_out: CueTransition = field(default_factory=CueTransition)
    audio_tracks: List[AudioTrack] = field(default_factory=list)
```

**JSON Format:**
```json
{
  "name": "Deepener",
  "duration_seconds": 300,
  "playback_pool": [
    {
      "playback": "playbacks/spiral_deep_1.json",
      "weight": 2.0,
      "min_cycles": 2,
      "max_cycles": 8
    },
    {
      "playback": "playbacks/spiral_deep_2.json",
      "weight": 1.0,
      "min_cycles": 2,
      "max_cycles": 8
    }
  ],
  "selection_mode": "on_media_cycle",
  "transition_in": {
    "type": "fade",
    "duration_ms": 1500
  },
  "transition_out": {
    "type": "fade",
    "duration_ms": 1500
  },
  "audio_tracks": [
    {
      "file": "audio/binaural_theta.mp3",
      "volume": 0.7,
      "loop": true,
      "fade_in_ms": 2000,
      "fade_out_ms": 2000
    }
  ]
}
```

### Cuelist
**Python Class:** `Cuelist` (in `session/cuelist.py`)

```python
class CuelistLoopMode(Enum):
    ONCE = "once"
    LOOP = "loop"
    PING_PONG = "ping_pong"

@dataclass
class Cuelist:
    name: str
    description: str = ""
    version: str = "1.0"
    author: str = ""
    cues: List[Cue] = field(default_factory=list)
    loop_mode: CuelistLoopMode = CuelistLoopMode.ONCE
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**JSON Format:**
```json
{
  "name": "Full Deep Trance Session",
  "description": "45-minute complete induction and deepener sequence",
  "version": "1.0",
  "author": "Example Creator",
  "loop_mode": "once",
  "cues": [
    {
      "name": "Induction",
      "duration_seconds": 600,
      "playback_pool": [...],
      "selection_mode": "on_cue_start",
      "transition_in": {...},
      "audio_tracks": [...]
    },
    {
      "name": "Deepener",
      "duration_seconds": 900,
      "playback_pool": [...],
      "selection_mode": "on_media_cycle",
      "audio_tracks": [...]
    },
    {
      "name": "Wakener",
      "duration_seconds": 300,
      "playback_pool": [...],
      "selection_mode": "on_cue_start",
      "transition_out": {...}
    }
  ]
}
```

---

## 🔄 State Machine: Session Runner

### States

```
┌─────────────┐
│   STOPPED   │──── start() ────▶┌──────────────┐
└─────────────┘                  │  WAITING_FOR │
                                 │    CYCLE     │
                                 └───────┬──────┘
                                         │
                                   (cycle boundary)
                                         │
                                         ▼
┌─────────────┐                  ┌──────────────┐
│   PAUSED    │◀──── pause() ────│   RUNNING    │
└──────┬──────┘                  └───────┬──────┘
       │                                 │
       │                            (cue ends)
       │                                 │
       └───── resume() ────▶┌────────────▼──────┐
                            │ TRANSITIONING_OUT │
                            └────────┬───────────┘
                                     │
                               (cycle boundary)
                                     │
                                     ▼
                            ┌─────────────────┐
                            │   NEXT_CUE or   │
                            │    FINISHED     │
                            └─────────────────┘
```

### State Transitions

| From State | Event | To State | Actions |
|------------|-------|----------|---------|
| STOPPED | start() | WAITING_FOR_CYCLE | Load first cue, wait for boundary |
| WAITING_FOR_CYCLE | cycle boundary | RUNNING | Execute transition_in, start audio, select playback |
| RUNNING | cue timer expires | TRANSITIONING_OUT | Set pending transition |
| TRANSITIONING_OUT | cycle boundary | WAITING_FOR_CYCLE or FINISHED | Execute transition_out, stop audio, advance cue |
| RUNNING | pause() | PAUSED | Pause timers, keep visual state |
| PAUSED | resume() | RUNNING | Resume timers |
| RUNNING | playback switch needed | WAITING_FOR_CYCLE | Set pending switch |
| ANY | skip_to_cue(n) | TRANSITIONING_OUT | Interrupt current, transition to new cue |

---

## 🎬 Execution Flow

### Detailed Sequence Diagram

```
SESSION START
    │
    ├─▶ Load Cuelist JSON
    ├─▶ Validate cue structure
    ├─▶ Initialize SessionRunner(cuelist, visual_director, audio_engine)
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  CUE START (Index 0)                                           │
└────────────────────────────────────────────────────────────────┘
    │
    ├─▶ Mark waiting_for_cycle_boundary = True
    ├─▶ Set transition_pending = "in"
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  WAIT FOR CYCLE BOUNDARY                                       │
│  (Check every frame: visual_director.get_cycle_count())       │
└────────────────────────────────────────────────────────────────┘
    │
    └─▶ (Cycle boundary detected)
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  EXECUTE TRANSITION IN                                         │
│  1. Select playback from pool (weighted random)                │
│  2. Load playback via visual_director.load_playback()          │
│  3. Trigger compositor.fade_in(duration_ms)                    │
│  4. Start audio tracks with fade_in                            │
│  5. Reset time_in_cue = 0                                      │
│  6. Reset cycles_with_playback = 0                             │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  RUNNING LOOP (60 FPS)                                         │
│                                                                │
│  Every Frame:                                                  │
│    • time_in_cue += dt                                         │
│    • time_in_cycle += dt                                       │
│    • visual_director.update(dt)                                │
│    • Check cycle boundary:                                     │
│        if cycle_count increased:                               │
│          - time_in_cycle = 0                                   │
│          - cycles_with_playback += 1                           │
│          - Process pending transitions                         │
│          - Check playback switch conditions                    │
│                                                                │
│  Playback Switch Logic:                                        │
│    if selection_mode == ON_MEDIA_CYCLE:                        │
│      - Check min/max cycle constraints                         │
│      - If switch allowed: transition_pending = "switch"        │
│                                                                │
│    if selection_mode == ON_TIMED_INTERVAL:                     │
│      - if time_in_cue % interval == 0:                         │
│          transition_pending = "switch"                         │
│                                                                │
│  Cue End Check:                                                │
│    if time_in_cue >= cue.duration_seconds:                     │
│      - transition_pending = "out"                              │
└────────────────────────────────────────────────────────────────┘
    │
    └─▶ (transition_pending = "out")
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  WAIT FOR CYCLE BOUNDARY                                       │
└────────────────────────────────────────────────────────────────┘
    │
    └─▶ (Cycle boundary detected)
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  EXECUTE TRANSITION OUT                                        │
│  1. Trigger compositor.fade_out(duration_ms)                   │
│  2. Stop audio tracks with fade_out                            │
│  3. Advance cue index                                          │
└────────────────────────────────────────────────────────────────┘
    │
    ├─▶ If more cues: Go to CUE START
    │
    └─▶ If no more cues:
        │
        ├─▶ loop_mode == ONCE: SESSION END
        ├─▶ loop_mode == LOOP: index = 0, Go to CUE START
        └─▶ loop_mode == PING_PONG: Reverse list, Go to CUE START
```

---

## 📋 PHASE 1: Terminology & Data Structures

**Duration:** 2-3 days  
**Dependencies:** None  
**Status:** Not Started

### Tasks

#### 1.1 Rename "Mode" → "Playback" Throughout Codebase
- [ ] **Files to rename:**
  - `mesmerglass/modes/` → `mesmerglass/playbacks/`
  - Update all JSON files in directory
- [ ] **Code updates:**
  - `custom_visual.py`: All references to "mode" → "playback"
  - `visual_director.py`: `select_custom_visual()` → `load_playback()`
  - `launcher.py`: Mode loading logic
  - All test files referencing modes
- [ ] **Documentation:**
  - Update README.md
  - Update all technical docs
  - Update user guides
- [ ] **Git:**
  - Create branch `feature/rename-mode-to-playback`
  - Commit with message: "Rename Mode → Playback (terminology update)"

**Estimated Time:** 3-4 hours  
**Test Strategy:** Run full test suite, ensure no regressions

---

#### 1.2 Create `mesmerglass/session/` Package
- [ ] Create directory: `mesmerglass/session/`
- [ ] Create `__init__.py` with exports:
  ```python
  from .cue import Cue, PlaybackEntry, AudioTrack, CueTransition, PlaybackSelectionMode
  from .cuelist import Cuelist, CuelistLoopMode
  from .runner import SessionRunner
  
  __all__ = [
      'Cue', 'PlaybackEntry', 'AudioTrack', 'CueTransition',
      'PlaybackSelectionMode', 'Cuelist', 'CuelistLoopMode',
      'SessionRunner'
  ]
  ```

**Estimated Time:** 30 minutes

---

#### 1.3 Implement `session/cue.py`
- [ ] Create enums:
  - `PlaybackSelectionMode` (ON_CUE_START, ON_MEDIA_CYCLE, ON_TIMED_INTERVAL)
- [ ] Create dataclasses:
  - `PlaybackEntry` (playback_path, weight, min_cycles, max_cycles)
  - `AudioTrack` (file_path, volume, loop, fade_in_ms, fade_out_ms)
  - `CueTransition` (type, duration_ms, wait_for_cycle)
  - `Cue` (name, duration_seconds, playback_pool, selection_mode, etc.)
- [ ] Implement methods:
  - `Cue.to_dict()` - Serialize to JSON-compatible dict
  - `Cue.from_dict(data)` - Deserialize from dict
  - `Cue.validate()` - Validate structure and values
- [ ] Add validation rules:
  - duration_seconds > 0
  - playback_pool not empty
  - weights > 0
  - min_cycles <= max_cycles
  - audio_tracks <= 2

**Estimated Time:** 4-6 hours  
**Test File:** `tests/test_cue.py`

---

#### 1.4 Implement `session/cuelist.py`
- [ ] Create enum:
  - `CuelistLoopMode` (ONCE, LOOP, PING_PONG)
- [ ] Create dataclass:
  - `Cuelist` (name, description, version, author, cues, loop_mode, metadata)
- [ ] Implement methods:
  - `total_duration()` - Sum of all cue durations
  - `get_cue(index)` - Get cue by index
  - `add_cue(cue, position)` - Insert cue
  - `remove_cue(index)` - Remove cue
  - `reorder_cues(new_order)` - Rearrange cues
  - `to_dict()` - Serialize
  - `from_dict(data)` - Deserialize
  - `validate()` - Validate structure
  - `save(path)` - Save to JSON file
  - `load(path)` - Load from JSON file
- [ ] Add validation rules:
  - name not empty
  - cues list not empty
  - all cues valid
  - no duplicate cue names

**Estimated Time:** 4-6 hours  
**Test File:** `tests/test_cuelist.py`

---

#### 1.5 Create Example Files
- [ ] Create `playbacks/example_deep_1.json`
- [ ] Create `playbacks/example_deep_2.json`
- [ ] Create `playbacks/example_wakener.json`
- [ ] Create `cuelists/example_short_session.cuelist.json`
- [ ] Add to `MEDIA/` or `examples/` directory

**Estimated Time:** 2 hours

---

### Phase 1 Deliverables
- ✅ All "Mode" references renamed to "Playback"
- ✅ `session/` package created with data models
- ✅ Full JSON serialization/deserialization
- ✅ Validation for all data structures
- ✅ Example files for testing
- ✅ Unit tests passing

---

## 📋 PHASE 2: Cycle Detection & Tracking

**Duration:** 2-3 days  
**Dependencies:** Phase 1 complete  
**Status:** Not Started

### Tasks

#### 2.1 Add Cycle Tracking to VisualDirector
- [ ] **Modify:** `mesmerglass/mesmerloom/visual_director.py`
- [ ] Add instance variables:
  ```python
  self._cycle_count = 0        # Total cycles completed
  self._last_cycle_marker = 0  # Last known cycle position
  self._cycle_callbacks = []   # Callbacks to fire on boundary
  ```
- [ ] Add methods:
  ```python
  def get_cycle_count(self) -> int:
      """Get number of completed media cycles since start"""
      
  def register_cycle_callback(self, callback: Callable[[], None]):
      """Register callback to fire on cycle boundaries"""
      
  def _check_cycle_boundary(self) -> bool:
      """Internal: Detect if cycle just completed"""
  ```
- [ ] **Integration in update():**
  ```python
  def update(self, dt: Optional[float] = None) -> None:
      # ... existing logic ...
      
      # NEW: Detect cycle completion
      if self.current_visual and hasattr(self.current_visual, 'get_current_cycle'):
          current_marker = self.current_visual.get_current_cycle()
          if current_marker > self._last_cycle_marker:
              self._cycle_count += 1
              self._last_cycle_marker = current_marker
              # Fire callbacks
              for cb in self._cycle_callbacks:
                  try:
                      cb()
                  except Exception as e:
                      self.logger.error(f"Cycle callback error: {e}")
  ```

**Estimated Time:** 3-4 hours  
**Test File:** `tests/test_cycle_tracking.py`

---

#### 2.2 Add Cycle Marker to CustomVisual
- [ ] **Modify:** `mesmerglass/mesmerloom/custom_visual.py`
- [ ] Add instance variable:
  ```python
  self._cycle_marker = 0  # Increments on each media change
  ```
- [ ] Add method:
  ```python
  def get_current_cycle(self) -> int:
      """Return current cycle number (increments on media change)"""
      return self._cycle_marker
  ```
- [ ] **Update media change callback:**
  ```python
  def _on_change_image(self, index: int):
      # ... existing logic ...
      self._cycle_marker += 1  # NEW: Increment on change
  
  def _on_change_video(self, index: int):
      # ... existing logic ...
      self._cycle_marker += 1  # NEW: Increment on change
  ```

**Estimated Time:** 2 hours  
**Test File:** `tests/test_custom_visual_cycles.py`

---

#### 2.3 Create Cycle Boundary Event System
- [ ] **New file:** `mesmerglass/session/events.py`
- [ ] Implement event system:
  ```python
  from typing import Callable, List
  from dataclasses import dataclass, field
  from enum import Enum
  
  class SessionEventType(Enum):
      CYCLE_BOUNDARY = "cycle_boundary"
      CUE_STARTED = "cue_started"
      CUE_ENDED = "cue_ended"
      PLAYBACK_SWITCHED = "playback_switched"
      SESSION_STARTED = "session_started"
      SESSION_ENDED = "session_ended"
      SESSION_PAUSED = "session_paused"
      SESSION_RESUMED = "session_resumed"
  
  @dataclass
  class SessionEvent:
      type: SessionEventType
      timestamp: float
      data: dict = field(default_factory=dict)
  
  class SessionEventEmitter:
      def __init__(self):
          self._listeners: Dict[SessionEventType, List[Callable]] = {}
      
      def on(self, event_type: SessionEventType, callback: Callable):
          """Register event listener"""
          
      def emit(self, event: SessionEvent):
          """Emit event to all listeners"""
          
      def remove(self, event_type: SessionEventType, callback: Callable):
          """Unregister event listener"""
  ```

**Estimated Time:** 2-3 hours  
**Test File:** `tests/test_session_events.py`

---

### Phase 2 Deliverables
- ✅ Reliable cycle boundary detection
- ✅ Cycle count tracking in VisualDirector
- ✅ Event system for session coordination
- ✅ Tests proving cycle detection accuracy

---

## 📋 PHASE 3: Session Runner Core

**Duration:** 4-5 days  
**Dependencies:** Phase 2 complete  
**Status:** Not Started

### Tasks

#### 3.1 Implement SessionRunner State Machine
- [ ] **New file:** `mesmerglass/session/runner.py`
- [ ] Create runner class structure:
  ```python
  from enum import Enum
  from typing import Optional
  import time
  import random
  
  class SessionState(Enum):
      STOPPED = "stopped"
      WAITING_FOR_CYCLE = "waiting_for_cycle"
      RUNNING = "running"
      TRANSITIONING_OUT = "transitioning_out"
      PAUSED = "paused"
      FINISHED = "finished"
  
  class SessionRunner:
      def __init__(
          self,
          cuelist: Cuelist,
          visual_director: VisualDirector,
          audio_engine: AudioEngine,
          compositor: LoomCompositor
      ):
          # Core references
          self.cuelist = cuelist
          self.visual_director = visual_director
          self.audio_engine = audio_engine
          self.compositor = compositor
          
          # State tracking
          self.state = SessionState.STOPPED
          self.current_cue_index = -1
          self.current_cue: Optional[Cue] = None
          self.current_playback_entry: Optional[PlaybackEntry] = None
          
          # Timing
          self.time_in_cue = 0.0
          self.time_in_cycle = 0.0
          self.cycles_with_playback = 0
          self.session_start_time = 0.0
          
          # Transition control
          self.waiting_for_cycle_boundary = False
          self.transition_pending: Optional[str] = None  # "in", "out", "switch"
          
          # Event system
          self.event_emitter = SessionEventEmitter()
          
          # Register cycle callback
          self.visual_director.register_cycle_callback(self._on_cycle_boundary)
  ```

**Estimated Time:** 6-8 hours

---

#### 3.2 Implement Playback Selection Logic
- [ ] Add weighted selection method:
  ```python
  def _select_playback(self, cue: Cue) -> PlaybackEntry:
      """Select playback from pool using weights and constraints"""
      # Filter by min_cycles constraint
      available = [
          entry for entry in cue.playback_pool
          if not entry.min_cycles or self.cycles_with_playback >= entry.min_cycles
      ]
      
      # If current playback hit max_cycles, exclude it
      if self.current_playback_entry and self.current_playback_entry.max_cycles:
          if self.cycles_with_playback >= self.current_playback_entry.max_cycles:
              available = [e for e in available if e != self.current_playback_entry]
      
      # Weighted random selection
      total_weight = sum(entry.weight for entry in available)
      r = random.random() * total_weight
      cumulative = 0.0
      for entry in available:
          cumulative += entry.weight
          if r <= cumulative:
              return entry
      
      # Fallback: return first available
      return available[0]
  ```

**Estimated Time:** 2-3 hours  
**Test File:** `tests/test_playback_selection.py`

---

#### 3.3 Implement State Transitions
- [ ] Add state transition methods:
  ```python
  def start(self):
      """Start session from first cue"""
      
  def pause(self):
      """Pause session (preserves state)"""
      
  def resume(self):
      """Resume paused session"""
      
  def stop(self):
      """Stop session and cleanup"""
      
  def skip_to_cue(self, index: int):
      """Skip to specific cue (waits for cycle boundary)"""
  ```
- [ ] Implement each with proper state validation

**Estimated Time:** 4-5 hours

---

#### 3.4 Implement Transition Execution
- [ ] Add transition methods:
  ```python
  def _execute_transition_in(self):
      """Execute cue transition in (at cycle boundary)"""
      cue = self.current_cue
      
      # 1. Select playback
      entry = self._select_playback(cue)
      self.current_playback_entry = entry
      
      # 2. Load playback
      self.visual_director.load_playback(entry.playback_path)
      
      # 3. Trigger visual fade in
      if cue.transition_in.type == "fade":
          self.compositor.trigger_fade_in(cue.transition_in.duration_ms)
      
      # 4. Start audio tracks
      for i, track in enumerate(cue.audio_tracks[:2]):
          self.audio_engine.load_channel(i, track.file_path)
          self.audio_engine.set_volume(i, track.volume)
          self.audio_engine.fade_in_and_play(i, track.fade_in_ms, loop=track.loop)
      
      # 5. Reset timers
      self.time_in_cue = 0.0
      self.cycles_with_playback = 0
      
      # 6. Update state
      self.state = SessionState.RUNNING
      self.transition_pending = None
      
      # 7. Emit event
      self.event_emitter.emit(SessionEvent(
          type=SessionEventType.CUE_STARTED,
          timestamp=time.time(),
          data={"cue_index": self.current_cue_index, "cue_name": cue.name}
      ))
  
  def _execute_transition_out(self):
      """Execute cue transition out (at cycle boundary)"""
      
  def _execute_playback_switch(self):
      """Switch playback within cue (at cycle boundary)"""
  ```

**Estimated Time:** 6-8 hours

---

#### 3.5 Implement Update Loop
- [ ] Add main update method:
  ```python
  def update(self, dt: float):
      """Update session state (call at 60 FPS)"""
      if self.state in (SessionState.STOPPED, SessionState.FINISHED):
          return
      
      if self.state == SessionState.PAUSED:
          return
      
      # Update timers
      self.time_in_cue += dt
      self.time_in_cycle += dt
      
      # Check for cue end
      if self.state == SessionState.RUNNING:
          if self.time_in_cue >= self.current_cue.duration_seconds:
              self.transition_pending = "out"
              self.state = SessionState.WAITING_FOR_CYCLE
      
      # Check for playback switch conditions
      if self.state == SessionState.RUNNING:
          if self._should_switch_playback():
              self.transition_pending = "switch"
              self.state = SessionState.WAITING_FOR_CYCLE
  
  def _on_cycle_boundary(self):
      """Callback fired by VisualDirector on cycle completion"""
      # Reset cycle timer
      self.time_in_cycle = 0.0
      self.cycles_with_playback += 1
      
      # Emit event
      self.event_emitter.emit(SessionEvent(
          type=SessionEventType.CYCLE_BOUNDARY,
          timestamp=time.time(),
          data={"cycle_count": self.cycles_with_playback}
      ))
      
      # Process pending transitions
      if self.state == SessionState.WAITING_FOR_CYCLE:
          if self.transition_pending == "in":
              self._execute_transition_in()
          elif self.transition_pending == "out":
              self._execute_transition_out()
          elif self.transition_pending == "switch":
              self._execute_playback_switch()
  ```

**Estimated Time:** 6-8 hours

---

#### 3.6 Implement Loop Logic
- [ ] Add loop handling:
  ```python
  def _advance_cue(self):
      """Move to next cue or handle loop behavior"""
      self.current_cue_index += 1
      
      if self.current_cue_index >= len(self.cuelist.cues):
          # Reached end of cuelist
          if self.cuelist.loop_mode == CuelistLoopMode.ONCE:
              self.state = SessionState.FINISHED
              self.event_emitter.emit(SessionEvent(
                  type=SessionEventType.SESSION_ENDED,
                  timestamp=time.time()
              ))
          
          elif self.cuelist.loop_mode == CuelistLoopMode.LOOP:
              self.current_cue_index = 0
              self._start_cue(self.cuelist.cues[0])
          
          elif self.cuelist.loop_mode == CuelistLoopMode.PING_PONG:
              # Reverse cue list
              self.cuelist.cues = list(reversed(self.cuelist.cues))
              self.current_cue_index = 0
              self._start_cue(self.cuelist.cues[0])
      else:
          # Start next cue
          self._start_cue(self.cuelist.cues[self.current_cue_index])
  ```

**Estimated Time:** 3-4 hours

---

### Phase 3 Deliverables
- ✅ Complete SessionRunner implementation
- ✅ All state transitions working
- ✅ Cycle-synchronized transitions
- ✅ Weighted playback selection
- ✅ Loop modes functional
- ✅ Unit tests passing

---

## 📋 PHASE 4: Audio Integration

**Duration:** 2-3 days  
**Dependencies:** Phase 3 complete  
**Status:** Not Started

### Tasks

#### 4.1 Extend AudioEngine with Fade Support
- [ ] **Modify:** `mesmerglass/engine/audio.py`
- [ ] Add fade methods:
  ```python
  def fade_in_and_play(self, channel: int, duration_ms: float, loop: bool = False):
      """Start playback with fade-in effect"""
      
  def fade_out_and_stop(self, channel: int, duration_ms: float):
      """Fade out and stop playback"""
      
  def set_fade_volume(self, channel: int, volume: float, duration_ms: float):
      """Smoothly transition to new volume"""
  ```
- [ ] Implementation using pygame.mixer fade functions
- [ ] Handle edge cases (channel already fading, etc.)

**Estimated Time:** 4-5 hours  
**Test File:** `tests/test_audio_fades.py`

---

#### 4.2 Add Per-Track Loop Control
- [ ] Track loop state per channel
- [ ] Ensure loops continue during cue (until transition out)
- [ ] Handle loop interruption gracefully

**Estimated Time:** 2 hours

---

#### 4.3 Test Audio/Visual Sync
- [ ] Create test cuelist with audio
- [ ] Verify fade timing matches visual transitions
- [ ] Ensure no audio pops/clicks at boundaries

**Estimated Time:** 3-4 hours  
**Test File:** `tests/test_audio_visual_sync.py`

---

### Phase 4 Deliverables
- ✅ AudioEngine supports fades
- ✅ Per-cue audio control
- ✅ Synchronized audio/visual transitions
- ✅ No audio artifacts

---

## 📋 PHASE 5: CLI Integration

**Duration:** 2 days  
**Dependencies:** Phase 4 complete  
**Status:** ✅ **COMPLETE** (November 9, 2025)

### Tasks

#### 5.1 Add `cuelist` CLI Command
- [x] **Modify:** `mesmerglass/cli.py`
- [x] Add subcommand:
  ```python
  p_cuelist = sub.add_parser("cuelist", help="Run a cuelist session")
  p_cuelist.add_argument("--load", required=True, help="Path to cuelist JSON")
  p_cuelist.add_argument("--headless", action="store_true", help="Run without UI")
  p_cuelist.add_argument("--validate", action="store_true", help="Validate and exit")
  p_cuelist.add_argument("--print", action="store_true", help="Print cuelist structure")
  p_cuelist.add_argument("--duration", type=float, help="Override total duration")
  ```

**Estimated Time:** 3-4 hours

---

#### 5.2 Implement Command Handler
- [x] Load cuelist from JSON
- [x] Validate structure
- [x] Initialize SessionRunner
- [x] Run session to completion (headless mode)
- [x] Print progress/status

**Estimated Time:** 4-5 hours

---

#### 5.3 Add Cuelist Validation Tool
- [x] Standalone validation:
  ```bash
  python -m mesmerglass cuelist --load session.cuelist.json --validate
  ```
- [x] Check:
  - All playback files exist
  - All audio files exist
  - Duration sanity checks
  - Weight constraints valid

**Estimated Time:** 2-3 hours  
**Test File:** `tests/test_cli_cuelist.py` ✅

---

### Phase 5 Deliverables
- ✅ CLI can run cuelists
- ✅ Validation tool working
- ✅ Headless execution supported
- ✅ 10/10 tests passing
- ✅ Documentation: `docs/technical/phase-5-cli-integration-complete.md`

---

## 📋 PHASE 6: UI Integration

**Duration:** 6-8 days  
**Dependencies:** Phase 5 complete  
**Status:** ✅ **COMPLETE** (November 10, 2025)

### Completed Tasks

#### 6.1 Create Session Tab in Launcher ✅
- [x] Session Runner tab added to launcher
- [x] Tab layout with all sections (header, info, timeline, controls, cue list)
- [x] Integrated into sidebar navigation
- [x] Set as default tab on launch

#### 6.2 Wire SessionRunner to UI ✅
- [x] Pass visual_director, audio_engine, compositor to tab
- [x] Initialize SessionRunner on Start button
- [x] Connect runner.start() / pause() / stop() / skip_to_cue() methods
- [x] Wire SessionRunner events (CUE_STARTED, CYCLE_BOUNDARY, etc.) to UI
- [x] Implement real-time UI updates (progress, cue, cycles)

#### 6.3 Example Cuelist ✅
- [x] Created `examples/short_test_session.cuelist.json`
- [x] 5-minute test session with 3 cues
- [x] Ready for manual testing

### Phase 6 Deliverables
- ✅ Session Runner tab fully functional
- ✅ Start/Pause/Stop/Skip controls working
- ✅ Real-time progress tracking
- ✅ Event-driven UI updates
- ✅ Example cuelist for testing
- ✅ Documentation: `docs/technical/phase-6-ui-integration-progress.md`

### Known Limitations
- Timeline is basic progress bar (enhanced timeline deferred to Phase 7)
- No visual cuelist editor yet (planned for Phase 7)
- No playback pool editor yet (planned for Phase 7)
- Preview is in main overlay window (integrated preview planned for Phase 7)

---

## 📋 PHASE 7: Complete GUI Redesign

**Duration:** 5 weeks (8-12 days full-time)  
**Dependencies:** Phase 6 complete  
**Status:** 📋 **PLANNED**

### Vision
Transform MesmerGlass into a **landscape-oriented, fullscreen programming environment** with:
- Large preview canvas for real-time visual feedback
- Visual cuelist builder with drag-drop timeline
- Integrated VMC (Visual Mode Creator) for playback design
- Professional layout inspired by video editing software
- Side-by-side edit-and-preview workflow

### Major Components
1. **New Main Window** (`programming_studio.py`)
   - Landscape layout (1280x720 minimum)
   - Icon sidebar navigation (60px)
   - Large preview canvas
   - Bottom timeline/controls

2. **Preview Canvas**
   - Live visual preview (centered, large)
   - Fullscreen toggle
   - VR mirror mode
   - Recording indicator

3. **Visual Cuelist Builder**
   - Horizontal timeline with proportional cue blocks
   - Drag-drop reordering
   - Visual cue editor panel
   - Playback pool management

4. **VMC Panel**
   - Playback library browser
   - Live preview while editing
   - Real-time parameter updates

5. **Additional Panels**
   - Session Runner (migrated from Phase 6)
   - Settings (consolidated)
   - Audio library & mixing
   - Real-time logs & debug tools

### See Full Plan
- 📄 `docs/technical/phase-7-gui-redesign-plan.md`

### Tasks

#### 6.1 Create Session Tab in Launcher
- [ ] **Modify:** `mesmerglass/ui/launcher.py`
- [ ] Add new tab: "Session Runner"
- [ ] Tab layout:
  ```
  ┌─────────────────────────────────────────┐
  │  Session Runner                         │
  ├─────────────────────────────────────────┤
  │  [Load Cuelist] [Save Cuelist]         │
  │                                         │
  │  Cuelist: example_session.cuelist.json │
  │  Total Duration: 45:00                  │
  │                                         │
  │  ┌───────────────────────────────────┐ │
  │  │ Cue Timeline                      │ │
  │  │ [=====>                    ]      │ │
  │  │ Current: Deepener (12:34/15:00)  │ │
  │  └───────────────────────────────────┘ │
  │                                         │
  │  [▶ Start] [⏸ Pause] [⏹ Stop]         │
  │  [⏭ Skip to Next Cue]                  │
  │                                         │
  │  ┌───────────────────────────────────┐ │
  │  │ Cue List                          │ │
  │  │ 1. Induction      [10:00]         │ │
  │  │ 2. Deepener       [15:00] ◀ Active│ │
  │  │ 3. Suggestions    [15:00]         │ │
  │  │ 4. Wakener        [05:00]         │ │
  │  └───────────────────────────────────┘ │
  │                                         │
  │  [Edit Cuelist in Editor...]           │
  └─────────────────────────────────────────┘
  ```

**Estimated Time:** 6-8 hours

---

#### 6.2 Create Cuelist Editor Panel
- [ ] **New file:** `mesmerglass/ui/panel_cuelist_editor.py`
- [ ] Features:
  - Create new cuelist
  - Add/remove/reorder cues
  - Edit cue properties
  - Playback pool editor (drag-drop, weights)
  - Audio track assignment
  - Transition configuration
  - Preview playback
  - Save/load JSON
- [ ] Use QTreeWidget for cue hierarchy
- [ ] Drag-drop reordering
- [ ] Weight sliders for playback pool

**Estimated Time:** 20-24 hours (complex UI)

---

#### 6.3 Create Playback Pool Editor Widget
- [ ] **New file:** `mesmerglass/ui/widget_playback_pool.py`
- [ ] Table view:
  ```
  ┌─────────────────────────────────────────────────┐
  │ Playback Pool                                   │
  ├──────────────────┬────────┬─────────┬──────────┤
  │ Playback         │ Weight │ Min Cyc │ Max Cyc  │
  ├──────────────────┼────────┼─────────┼──────────┤
  │ deep_spiral_1    │ [2.0]  │ [2]     │ [8]      │
  │ deep_spiral_2    │ [1.0]  │ [2]     │ [8]      │
  │ deep_spiral_3    │ [0.5]  │ [3]     │ [10]     │
  └──────────────────┴────────┴─────────┴──────────┘
  [+ Add Playback] [- Remove] [Browse...]
  ```
- [ ] Spinboxes for weights
- [ ] Optional min/max cycle inputs
- [ ] Preview button per playback

**Estimated Time:** 6-8 hours

---

#### 6.4 Create Cue Timeline Visualization
- [ ] Custom QWidget for timeline:
  ```
  Session Timeline (45:00 total)
  ┌─────────────────────────────────────────────────┐
  │ Induction │   Deepener    │ Suggestions│Wakener│
  │   10:00   │     15:00     │   15:00    │ 5:00  │
  │           │      ▼ 12:34                        │
  └─────────────────────────────────────────────────┘
         ▲ Current position with cycle pulse
  ```
- [ ] Proportional cue widths
- [ ] Current position indicator
- [ ] Cycle boundary pulse animation
- [ ] Click to skip to cue

**Estimated Time:** 8-10 hours

---

#### 6.5 Wire SessionRunner to UI
- [ ] Connect runner events to UI updates:
  - CUE_STARTED → Update timeline, highlight current
  - CYCLE_BOUNDARY → Pulse animation
  - PLAYBACK_SWITCHED → Show notification
  - SESSION_ENDED → Enable restart button
- [ ] Connect UI controls to runner:
  - Start button → runner.start()
  - Pause button → runner.pause() / resume()
  - Stop button → runner.stop()
  - Skip button → runner.skip_to_cue(next_index)

**Estimated Time:** 4-6 hours

---

### Phase 6 Deliverables
- ✅ Session Runner tab in UI
- ✅ Cuelist editor fully functional
- ✅ Timeline visualization
- ✅ Real-time progress tracking
- ✅ All controls working

---

## 📋 PHASE 7: Testing & Polish

**Duration:** 3-4 days  
**Dependencies:** Phase 6 complete  
**Status:** Not Started

### Tasks

#### 7.1 Unit Tests
- [ ] `tests/test_cue.py` - Cue data model
- [ ] `tests/test_cuelist.py` - Cuelist operations
- [ ] `tests/test_playback_selection.py` - Weighted selection
- [ ] `tests/test_session_runner.py` - Runner state machine
- [ ] `tests/test_cycle_sync.py` - Boundary synchronization
- [ ] `tests/test_audio_fades.py` - Audio transitions

**Estimated Time:** 8-10 hours

---

#### 7.2 Integration Tests
- [ ] `tests/integration/test_full_session.py` - Complete session execution
- [ ] `tests/integration/test_loop_modes.py` - All loop types
- [ ] `tests/integration/test_cue_transitions.py` - Visual transitions
- [ ] `tests/integration/test_playback_switching.py` - Mid-cue switches

**Estimated Time:** 6-8 hours

---

#### 7.3 Performance Testing
- [ ] Test with long cuelists (10+ cues)
- [ ] Test with large playback pools (20+ playbacks)
- [ ] Verify no memory leaks
- [ ] Profile update loop performance

**Estimated Time:** 4-5 hours

---

#### 7.4 User Testing
- [ ] Create 3 example cuelists:
  - Short (5 min, 3 cues)
  - Medium (20 min, 6 cues)
  - Long (45 min, 10+ cues)
- [ ] Test all selection modes
- [ ] Test all loop modes
- [ ] Verify audio sync
- [ ] Check edge cases (pause/resume, skip)

**Estimated Time:** 4-6 hours

---

#### 7.5 Documentation
- [ ] **User Guide:** `docs/user-guide/cuelist-system.md`
  - How to create cuelists
  - Playback pool configuration
  - Selection mode explanations
  - Best practices
- [ ] **Technical:** `docs/technical/cuelist-architecture.md`
  - System architecture
  - State machine details
  - Cycle synchronization algorithm
- [ ] **API Reference:** Docstrings for all classes
- [ ] **Examples:** Annotated cuelist JSON files

**Estimated Time:** 6-8 hours

---

### Phase 7 Deliverables
- ✅ Full test coverage (>85%)
- ✅ Performance validated
- ✅ User documentation complete
- ✅ Example files provided

---

## 📋 PHASE 8: Migration & Backward Compatibility

**Duration:** 1-2 days  
**Dependencies:** Phase 7 complete  
**Status:** Not Started

### Tasks

#### 8.1 Ensure Existing Playbacks Work
- [ ] Test all existing mode JSON files load as playbacks
- [ ] Verify no breaking changes to CustomVisual
- [ ] Test single-playback workflow still functions

**Estimated Time:** 2-3 hours

---

#### 8.2 Create Migration Script
- [ ] Script to convert old sessions to cuelists
- [ ] Handle edge cases
- [ ] Provide warnings for manual review

**Estimated Time:** 3-4 hours

---

#### 8.3 Update All Documentation
- [ ] Update README.md
- [ ] Update getting started guides
- [ ] Add cuelist tutorials
- [ ] Update CLI help text

**Estimated Time:** 2-3 hours

---

### Phase 8 Deliverables
- ✅ No regressions in existing features
- ✅ Migration path documented
- ✅ All docs updated

---

## 🎯 Success Metrics

### Functional Requirements
- [ ] Can create cuelists via JSON
- [ ] Can create cuelists via UI
- [ ] All transitions wait for cycle boundaries
- [ ] Playback selection respects weights
- [ ] Min/max cycle constraints enforced
- [ ] Audio fades sync with visuals
- [ ] All loop modes work correctly

### Performance Requirements
- [ ] Session Runner update() < 1ms per frame
- [ ] No frame drops during transitions
- [ ] Memory usage stable over long sessions

### User Experience
- [ ] Intuitive UI for cuelist creation
- [ ] Clear visual feedback for session progress
- [ ] No confusing state transitions
- [ ] Helpful error messages

---

## 📊 Risk Assessment

### High Risk
- **Cycle boundary synchronization** - Most critical, must be 100% reliable
  - Mitigation: Extensive testing, fallback mechanisms
- **Audio/visual sync** - Timing precision required
  - Mitigation: Use system clock, not frame count

### Medium Risk
- **UI complexity** - Cuelist editor is complex
  - Mitigation: Incremental development, user testing
- **Backward compatibility** - Must not break existing workflows
  - Mitigation: Thorough regression testing

### Low Risk
- **JSON serialization** - Standard pattern
- **Weighted selection** - Simple algorithm
- **Loop modes** - Straightforward logic

---

## 📅 Overall Timeline

| Phase | Duration | Start After |
|-------|----------|-------------|
| Phase 1: Data Structures | 2-3 days | - |
| Phase 2: Cycle Detection | 2-3 days | Phase 1 |
| Phase 3: Session Runner | 4-5 days | Phase 2 |
| Phase 4: Audio Integration | 2-3 days | Phase 3 |
| Phase 5: CLI Integration | 2 days | Phase 4 |
| Phase 6: UI Integration | 6-8 days | Phase 5 |
| Phase 7: Testing & Polish | 3-4 days | Phase 6 |
| Phase 8: Migration | 1-2 days | Phase 7 |

**Total Duration:** 22-30 days (full-time equivalent)  
**Realistic with interruptions:** 4-6 weeks

---

## 🚀 Getting Started

### Recommended First Steps
1. Create branch: `feature/cuelist-system`
2. Start with Phase 1.1: Rename Mode → Playback
3. Run tests to ensure no regressions
4. Commit and push regularly
5. Move to Phase 1.2-1.5 systematically

### Development Workflow
1. Read phase tasks carefully
2. Create sub-branch for each major feature
3. Write tests first (TDD where possible)
4. Implement feature
5. Run full test suite
6. Merge to feature branch
7. Update this document with progress

---

## 📝 Notes & Decisions

### Design Decisions
- **Why cycle boundaries?** Natural rhythm, prevents jarring cuts mid-image
- **Why weighted pools?** Variety while maintaining visual coherence
- **Why min/max cycles?** Control over variation frequency
- **Why per-cue audio?** Each segment needs different audio mood

### Alternative Approaches Considered
- **Time-based transitions without cycle sync** - Rejected (jarring)
- **Continuous parameter interpolation** - Future enhancement
- **More than 2 audio tracks** - Rejected (complexity vs utility)

### Future Enhancements
- Parameter interpolation (blend between playbacks)
- Conditional branching (user interaction)
- Real-time parameter control
- Recording/replay of live sessions
- Cuelist templates library

---

**END OF PLAN**
