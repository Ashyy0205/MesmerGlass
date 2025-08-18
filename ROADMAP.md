# MesmerGlass Development Roadmap

*A comprehensive development plan for MesmerGlass - Advanced Hypnotic Display & Device Control System*

---

## 🎯 Project Vision

MesmerGlass is evolving into a comprehensive hypnotic experience platform that combines:
- **Visual Effects**: Multi-display synchronized text flashing and video overlays
- **Device Control**: Bluetooth toy integration with real-time pulse synchronization
- **Biometric Integration**: Heart rate monitoring for adaptive experiences
- **Content Management**: Save/playlist system for complex session workflows
- **User Experience**: Intuitive UI with advanced customization options

---

## 📅 Development Phases

### Phase 1: Core Stability & Quality of Life (Q3 2025)
*Focus: Polish existing features and improve user experience*

#### 🔧 **Memory & Performance Optimization**
**Priority: HIGH** | **Effort: Medium** | **Impact: Critical**

- **Audio Memory Fix** 🎵
  - Current issue: Audio engine consuming excessive memory
  - Solution: Implement streaming audio with configurable buffer sizes
  - Technical approach: Replace full-file loading with chunked streaming
  - Files to modify: `mesmerglass/engine/audio.py`
  - Expected impact: 70-90% memory reduction for large audio files

- **Video Performance Optimization** 🎬
  - Implement hardware-accelerated video decoding where available
  - Add video compression quality settings
  - Optimize frame timing for smooth playback across multiple displays

#### 🎮 **Hotkeys System**
**Priority: HIGH** | **Effort: Low** | **Impact: High**

- **Global Hotkey Support**
  - Emergency stop: `Ctrl+Shift+Esc`
  - Pause/Resume: `Ctrl+Shift+Space`
  - Intensity adjustment: `Ctrl+Shift+↑/↓`
  - Quick save: `Ctrl+Shift+S`
  - Files to create: `mesmerglass/ui/hotkeys.py`
  - Dependencies: `pynput` or `keyboard` library

#### 📊 **Log Panel & Debugging**
**Priority: MEDIUM** | **Effort: Medium** | **Impact: Medium**

- **Real-time Log Viewer**
  - Integrated log panel in main UI
  - Filterable by component (audio, video, device, bluetooth)
  - Export logs for debugging
  - Files to modify: `mesmerglass/ui/launcher.py`, create `mesmerglass/ui/log_panel.py`

### Phase 2: Content Management & Multi-Device (Q4 2025)
*Focus: Advanced content organization and device handling*

#### 💾 **Saves & Playlists System**
**Priority: HIGH** | **Effort: High** | **Impact: Very High**

- **Save System Architecture**
  ```
  saves/
  ├── sessions/           # Complete session configurations
  │   ├── basic_session.json
  │   └── advanced_edging.json
  ├── playlists/          # Ordered content sequences
  │   ├── morning_routine.json
  │   └── evening_wind_down.json
  └── presets/            # Quick-load device/audio/visual presets
      ├── gentle_pulse.json
      └── intense_flash.json
  ```

- **File Structure (JSON Schema)**
  ```json
  {
    "metadata": {
      "name": "Session Name",
      "description": "Description",
      "version": "1.0",
      "created": "2025-08-18T10:30:00Z",
      "duration_estimate": 1800
    },
    "audio": {
      "file": "path/to/audio.mp3",
      "volume": 0.7,
      "effects": ["reverb", "echo"]
    },
    "visual": {
      "text_sequences": [...],
      "flash_patterns": [...],
      "background_video": "path/to/video.mp4"
    },
    "devices": {
      "pulse_patterns": [...],
      "device_mapping": {...}
    },
    "biometric": {
      "hr_targets": {...},
      "adaptive_enabled": true
    }
  }
  ```

- **Implementation Plan**
  - Create `mesmerglass/content/` module
  - Add `mesmerglass/ui/content_manager.py` 
  - Integrate with existing UI components
  - Add import/export functionality

#### 🎭 **Multiple Flash Messages**
**Priority: MEDIUM** | **Effort: Medium** | **Impact: High**

- **Advanced Text Sequencing**
  - Multiple text tracks with independent timing
  - Crossfade between messages
  - Conditional text based on session progress
  - Text randomization and variation
  - Files to enhance: `mesmerglass/ui/pages/textfx.py`

#### 🔗 **Multiple Toy Selection & Management**
**Priority: HIGH** | **Effort: High** | **Impact: Very High**

- **Multi-Device Architecture**
  - Support for 2-4 simultaneous devices
  - Independent or synchronized control modes
  - Device-specific intensity curves
  - Fallback handling when devices disconnect
  - Files to enhance: `mesmerglass/engine/device_manager.py`

- **Device Grouping & Profiles**
  - Save device combinations as "rigs"
  - Per-device calibration settings
  - Network device support (Wi-Fi toys)

#### 🤖 **Virtual Toys for Testing**
**Priority: MEDIUM** | **Effort: Low** | **Impact: Medium**

- **Enhanced Virtual Device Simulator**
  - Multiple virtual device types (vibrators, strokers, plugs)
  - Realistic response simulation with latency
  - Visual feedback in UI showing virtual device state
  - Integration with save/load system
  - Files to enhance: `mesmerglass/tests/virtual_toy.py`

### Phase 3: Biometric Integration & Advanced Features (Q1 2026)
*Focus: Heart rate monitoring and adaptive experiences*

#### ❤️ **Samsung Galaxy Watch Integration**
**Priority: HIGH** | **Effort: High** | **Impact: Revolutionary**

Based on your detailed implementation guide:

- **Heart Rate Monitoring Module**
  - Implement BLE heart rate service (`0x180D`)
  - Real-time BPM and RR-interval capture
  - Files to create: `mesmerglass/biometric/heart_rate.py`
  
- **Adaptive Experience Engine**
  ```python
  class AdaptiveEngine:
      def __init__(self):
          self.baseline_hr = None
          self.target_zones = {
              'relaxed': (60, 80),
              'engaged': (80, 110),
              'intense': (110, 140),
              'peak': (140, 180)
          }
      
      def adjust_intensity(self, current_hr: int, target_zone: str):
          # Dynamic intensity adjustment based on HR
          pass
  ```

- **Implementation Phases**
  1. **Basic HR Capture** (Week 1-2)
     - Implement BLE scanner for Galaxy Watch
     - Basic HR data parsing and logging
     - Simple console output for testing
  
  2. **UI Integration** (Week 3-4)
     - Add HR monitoring panel to main UI
     - Real-time HR graph with zones
     - Manual zone targeting controls
  
  3. **Adaptive Control** (Week 5-8)
     - Automatic device intensity based on HR
     - Target zone maintenance algorithms
     - Safety limits and emergency stops

- **Technical Implementation**
  ```python
  # New files to create:
  mesmerglass/biometric/
  ├── __init__.py
  ├── heart_rate.py          # BLE HR service implementation
  ├── adaptive_engine.py     # HR-based control logic
  └── safety_monitor.py      # Safety limits and alerts
  
  mesmerglass/ui/biometric/
  ├── __init__.py
  ├── hr_monitor.py          # Real-time HR display
  └── adaptive_controls.py   # Zone targeting UI
  ```

#### 🧠 **Advanced Adaptive Features**
**Priority: MEDIUM** | **Effort: Very High** | **Impact: Very High**

- **Multi-Modal Biometric Fusion**
  - Combine HR, HRV, and motion data
  - Respiration rate estimation from HR variability
  - Stress/arousal level classification
  - Machine learning for personalized responses

---

#### 🎨 **Advanced Visual Effects**
**Priority: LOW** | **Effort: High** | **Impact: Medium**

- **Shader-Based Effects**
  - Custom visual filters
  - Procedural pattern generation
  - GPU-accelerated rendering
  - VR/AR compatibility preparation

---

## 🛠️ Technical Architecture Evolution

### Current Architecture
```
MesmerGlass/
├── mesmerglass/
│   ├── engine/           # Core functionality
│   ├── ui/              # User interface
│   └── tests/           # Testing framework
├── docs/                # Documentation
└── run.py              # CLI entry point
```

### Target Architecture (Phase 3)
```
MesmerGlass/
├── mesmerglass/
│   ├── engine/           # Core functionality
│   │   ├── audio.py     # Enhanced audio streaming
│   │   ├── video.py     # Optimized video processing
│   │   ├── device_manager.py  # Multi-device support
│   │   └── adaptive.py  # HR-based control
│   ├── biometric/       # NEW: Biometric integration
│   │   ├── heart_rate.py
│   │   ├── adaptive_engine.py
│   │   └── safety_monitor.py
│   ├── content/         # NEW: Content management
│   │   ├── saves.py
│   │   ├── playlists.py
│   │   └── presets.py
│   ├── ui/              # Enhanced user interface
│   │   ├── biometric/   # NEW: Biometric UI
│   │   ├── content_manager.py  # NEW: Content UI
│   │   └── hotkeys.py   # NEW: Global hotkeys
│   └── cli.py           # NEW: Comprehensive CLI
├── saves/               # NEW: User content storage
├── community/           # NEW: Shared content
└── config/              # NEW: Configuration management
```

---

## 📊 Implementation Priorities

### **Must Have (Phase 1)**
1. 🔥 **Audio memory optimization** - Critical for user experience
2. 🤖 **Enhanced virtual toys** - Nice to have for testing
3. 📋 **Basic logging panel** - Debugging and troubleshooting

### **Should Have (Phase 2)**
1. 💾 **Save/Load system** - Core feature for practical usage
2. 🎮 **Multiple device support** - Major value proposition
3. 📝 **Multiple flash messages** - Enhanced experience variety

### **Could Have (Phase 3)**
1. ❤️ **Heart rate integration** - Revolutionary but complex
2. ⌨️ **Hotkeys system** - Essential safety and usability feature
3. 🎯 **Adaptive experiences** - Advanced feature

---

## 🚀 Getting Started

### Phase 1 Immediate Actions

1. **Set up development environment for Phase 1**
   ```bash
   # Install additional dependencies
   pip install pynput memory-profiler pyqtgraph
   ```

2. **Create initial file structure**
   ```bash
   mkdir -p mesmerglass/ui/biometric
   mkdir -p mesmerglass/biometric
   mkdir -p mesmerglass/content
   mkdir -p saves/{sessions,playlists,presets}
   ```

3. **Start with audio memory optimization**
   - Profile current memory usage
   - Implement streaming audio loader
   - Test with large audio files

### Development Guidelines

- **Backwards Compatibility**: Maintain existing API compatibility
- **Testing**: Add tests for each new feature
- **Documentation**: Update docs with each phase
- **Performance**: Profile memory and CPU usage regularly
- **Safety**: Always include emergency stops and safety limits

---

## 📈 Success Metrics

### Phase 1 Success Criteria
- [ ] 70%+ reduction in audio memory usage
- [ ] All hotkeys functional across OS platforms
- [ ] Log panel showing real-time system status
- [ ] Zero regression in existing functionality

### Phase 2 Success Criteria
- [ ] Save/load system with <2 second load times
- [ ] Support for 2+ simultaneous devices
- [ ] Text sequences with 10+ independent tracks
- [ ] Virtual toy simulator matching real device behavior

### Phase 3 Success Criteria
- [ ] Real-time HR monitoring with <1 second latency
- [ ] Adaptive intensity with smooth transitions
- [ ] Safety monitoring with automatic shutoffs
- [ ] Personalized experience learning

---

**Next Steps**: Begin Phase 1 implementation starting with audio memory optimization. Each phase builds upon the previous, creating a robust and feature-rich hypnotic experience platform.

*Last Updated: August 18, 2025*
