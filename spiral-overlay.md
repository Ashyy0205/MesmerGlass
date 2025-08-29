# MesmerGlass Spiral Overlay Feature

--

## 1. Full Feature Design

### Purpose
Enhance MesmerGlass by adding a **GPU-rendered, evolving spiral overlay** that sits on top of existing video visuals.  
This spiral overlay must be **dynamic, controllable, and hypnotic**, while preserving MesmerGlass’s core property:  
**a full-screen, always-on-top, click-through window** (user can still interact with underlying applications).

---

### Visual Requirements

- **Arms**
  - Default: **4 arms** (matches provided examples).
  - User-adjustable: **2–8 arms** via UI.

- **Band Ratio**
  - ~50/50 dark/light.
  - **Bar width breathes** slowly over ~90 s.

- **Rotation**
  - Base: ~**0.12 cycles/sec**.
  - Gentle wobble: ±0.015 cps, period ~25 s.
  - **No pops or jumps** (slew-limited changes only).

- **Twist (coil tightness)**
  - Base: 1.00.
  - Drift: ±0.10.
  - Cycle: ~220 s.
  - Perceived as in/out depth movement.

- **Opacity**
  - Base: ~0.75.
  - Linked to bar width (≈60% of its deviation).
  - Clamped: [0.55, 0.95].

- **Contrast**
  - Base: 1.00.
  - Drift: ±0.10.
  - Cycle: ~140 s.
  - Phase-shifted vs bar width (offset ~0.4).

- **Vignette**
  - Base: 0.30.
  - Drift: ±0.05.
  - Cycle: ~240 s.

---

### Colorization

- **Arm Color** (`uArmColor`) — default near-white.
- **Gap Color** (`uGapColor`) — default near-black (or let underlying video show).
- **Color Modes**
  1. **Flat Bi-Color** (default) — arms = Arm Color, gaps = Gap Color.
  2. **Radial Gradient** — each of Arm and Gap colors may fade inner→outer (two pickers each, plus gradient amount).
  3. **Palette Drift** — optional very slow hue drift (disabled by default; ≤ ±8° hue shift over ≥180 s).

All colors are controlled **live from the UI**.  
**No config files.**

---

### Inside-Out Direction Flip

- **Concept**
  - Rotation direction reverses via a **wavefront**.
  - Wave starts at center and propagates outward.
  - Inner coils reverse first, outer coils last.
  - Flip duration: ~30 s.

- **Implementation**
  - `uWavefrontRadius` animated from −0.2 → 1.2.
  - `uWavefrontWidth` controls softness (e.g., 0.08).
  - Blending uses `tanh/smoothstep` → **no hard edges**.
  - Temporary `uSpeedBoost` (~0.03 cps) applied inside flipped region.

- **Choreography**
  - Start: `uDirSignA = +1`, `uDirSignB = −1`, `uWavefrontRadius = −0.2`.
  - Trigger cadence: ~every 3 min ±45 s jitter.
  - Animate radius outward over ~30 s.
  - Commit: swap direction (`uDirSignA = uDirSignB`), re-arm new `uDirSignB = −uDirSignA`, reset radius.
  - Decay speed boost after ~5 s.

---

### Intensity Control (Global Slider [0..1])

- **Scaling Rules**
  - Base rotation speed: 0.09 → 0.14 cps.
  - Speed wobble amplitude: 0.006 → 0.020 cps.
  - Bar width range: 0.04 → 0.10.
  - Breathing cycle: 140 → 70 s.
  - Twist range: 0.06 → 0.14.
  - Twist cycle: 260 → 180 s.
  - Flip cadence: every 240 → 120 s.
  - Wave duration: 40 → 22 s.
  - Contrast boost: 0 → +0.18.
  - Vignette: 0.22 → 0.38.
  - Chromatic shift (optional): 0.0 → 0.3 px.

- **Auto-Intensity**
  - Toggle allows external systems (e.g., edge engine, device sync) to drive Intensity.

- **Rapid Changes**
  - Tighten slew limits for 1–2 s if Intensity changes abruptly → prevents pops.

---

### Safety (Nausea-Guard)

- **Speed Limit**: |effective phase speed(r)| ≤ 0.18 cps.
- **Bar Width Clamp**: [0.36, 0.62].
- **Contrast Clamp**: [0.85, 1.25].
- **Per-Frame Delta Caps** (@30 fps):
  - Δbar_width ≤ 0.0016.
  - Δopacity ≤ 0.003.
  - Δbase_speed ≤ 0.0015.
- **Chromatic Shift Limit**: ≤ 0.3 px.

---

### UI Requirements

Add a **Spiral Overlay Panel** in the MesmerGlass settings UI:

- **General**
  - Toggle: Enable Spiral Overlay.
  - Slider: Intensity [0..1].
  - Toggle: Auto-Intensity.
  - Dropdown: Blend Mode (Multiply / Screen / SoftLight).
  - Slider: Spiral Opacity [0.2–1.0].
  - Arm Count: [2–8], default 4.

- **Colors**
  - Arm Color picker.
  - Gap Color picker.
  - Color Mode selector (Flat / Radial Gradient / Palette Drift).
  - If Radial Gradient:
    - Arm Inner, Arm Outer color pickers.
    - Gap Inner, Gap Outer color pickers.
    - Gradient amount slider.
  - If Palette Drift:
    - Drift enable toggle.
    - Drift amount slider [0..1] (very slow).

- **Advanced**
  - Bar Width base / range / cycle.
  - Twist base / range / cycle.
  - Speed wobble amp / cycle.
  - Flip cadence & wave duration.
  - Nausea-Guard (read-only: shows clamps/deltas).

- **Live Updates**
  - All changes apply **immediately**.
  - **No spiral.json** file — UI only.

---

### Performance Requirements

- **Target:** 30 fps at 1080p on a mid-tier GPU.
- **Render Scale Option:** Spiral pass may render at 0.75–1.0× resolution and upscale.
- **No shader recompilation** during runtime; update via uniforms only.
- **Stable texture uploads** (consistent format, no stalls).

---

## 2. Step-by-Step Implementation Plan

---

### A. File & Module Setup
1. Create `mesmerglass/engine/shaders/` with:
   - `fullscreen_quad.vert`
   - `spiral.frag`
2. Create `mesmerglass/engine/spiral.py`:
   - Class `SpiralDirector`.
   - Public method: `get_uniforms(dt: float) -> dict`.

---

### B. Rendering Integration
1. Modify `mesmerglass/engine/video.py`:
   - Compile shaders at init.
   - Create full-screen quad VAO.
   - Bind video texture to `uVideo`.
2. Per frame:
   - Call `SpiralDirector.get_uniforms(dt)`.
   - Set uniforms (including Arm Color, Gap Color, blend mode, opacity).
   - Draw quad → spiral composited over video.
3. Keep window **full-screen**, **always-on-top**, **click-through**.

---

### C. Shader Responsibilities (`spiral.frag`)
- Generate spiral pattern (arm count, twist, bar width).
- Apply **radius-dependent phase speed** for inside-out flips.
- Colorize arms/gaps using:
  - `uArmColor`, `uGapColor`.
  - Gradient/Drift modes if enabled.
- Apply vignette, contrast, gamma.
- Composite with `uVideo` using blend mode & opacity.

---

### D. SpiralDirector Responsibilities
- Define param schema: base, range, cycle, phase offset.
- Drive slow evolution (LFO + smoothed noise).
- Apply slew-limits to all params.
- Handle inside-out flip scheduling (wavefront animation).
- Scale ranges with Intensity.
- Enforce nausea-guard clamps.
- Return uniform dict each frame.

---

### E. Inside-Out Flip Logic
- Start: `uDirSignA=+1`, `uDirSignB=−1`, `uWavefrontRadius=−0.2`.
- Trigger every ~3 min ± jitter.
- Animate wavefront to 1.2 over ~30 s.
- Apply temporary speed boost.
- Commit new direction; re-arm; reset radius; decay boost.

---

### F. Intensity System
- UI slider [0..1], Auto-Intensity toggle.
- Scale all ranges and cycles as described.
- Apply slew-limit tightening on rapid changes.

---

### G. UI Implementation
- Add Spiral Overlay panel with all controls (General, Colors, Advanced).
- All controls update uniforms live.
- Color pickers use Qt standard dialogs.
- No config files written.

---

### H. Validation Checklist
- [ ] Overlay is full-screen, always-on-top, click-through.
- [ ] Default spiral: 4 arms, ~0.12 cps, ~0.75 opacity, Multiply blend.
- [ ] Over 5 min: breathing bands, contrast shimmer, twist drift.
- [ ] Every ~3 min: inside-out reversal completes in ~30 s.
- [ ] Intensity 0→1 increases presence safely.
- [ ] Arm/Gap colors update immediately.
- [ ] Performance: 60 fps at 1080p.

---

### I. Testing
- **Unit Tests**
  - SpiralDirector clamps outputs within guardrails.
  - Slew-limit logic caps per-frame changes.
  - Flip scheduler toggles correctly.
- **Integration Tests**
  - Shader compiles; uniforms applied correctly.
  - Overlay renders without breaking video playback.
- **Manual Tests**
  - Visual confirmation of breathing, wobble, flip.
  - Color changes apply instantly.
  - Intensity behaves as mapped.
  - Overlay click-through works.

---

## 3. Rules for Implementation (Do’s and Don’ts)

- ✅ **Do**: Apply all opacity, blend, and color effects **in-shader**.  
- ✅ **Do**: Preserve existing window flags for full-screen, always-on-top, click-through.  
- ✅ **Do**: Use slow, smoothed evolution; never hard jumps.  
- ✅ **Do**: Clamp all parameters to safety ranges.  
- ✅ **Do**: Update everything live from UI.  

- ❌ **Don’t**: Write or read a `spiral.json` file.  
- ❌ **Don’t**: Perform a global instant flip of direction; must propagate inside-out.  
- ❌ **Don’t**: Adjust OS-level window opacity to achieve blending.  
- ❌ **Don’t**: Let Intensity bypass nausea-guards.  

---
