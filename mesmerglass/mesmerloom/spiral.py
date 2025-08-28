"""SpiralDirector implementation (Phase 2 core logic).

Responsibilities:
 - Intensity scaling for dynamic parameters (speeds, ranges, contrast, vignette, chromatic shift)
 - Inside-out flip wave FSM with jittered cadence
 - Safety clamps + per-frame slew caps
 - Export of uniform-ready values

The implementation aims for determinism in tests by allowing a seed and accepting dt.
"""
from __future__ import annotations
from dataclasses import dataclass
import math, random, time
from typing import Optional

@dataclass
class SpiralState:
    intensity: float = 0.0
    phase: float = 0.0
    base_speed: float = 0.09
    effective_speed: float = 0.09
    bar_width: float = 0.5
    twist: float = 0.06
    contrast: float = 1.0
    opacity: float = 0.85
    vignette: float = 0.22
    chromatic_shift: float = 0.0
    flip_state: int = 0  # 0 idle,1 active
    flip_radius: float = -0.2
    flip_width: float = 0.08
    safety_clamped: bool = False

class SpiralDirector:
    # Static configuration (ranges)
    BASE_SPEED_MIN = 0.09; BASE_SPEED_MAX = 0.14
    WOBBLE_MIN = 0.006; WOBBLE_MAX = 0.020
    TWIST_MIN = 0.06; TWIST_MAX = 0.14
    CONTRAST_BOOST_MAX = 0.18
    VIGNETTE_MIN = 0.22; VIGNETTE_MAX = 0.38
    CHROMA_MAX = 0.3
    # Flip ranges
    FLIP_PERIOD_MIN = 120.0; FLIP_PERIOD_MAX = 240.0  # intensity 0→1 maps 240→120 (invert later)
    FLIP_WAVE_MIN = 22.0; FLIP_WAVE_MAX = 40.0
    FLIP_RADIUS_START = -0.2; FLIP_RADIUS_END = 1.2
    # Safety clamps
    SPEED_CAP = 0.18
    BAR_WIDTH_MIN = 0.36; BAR_WIDTH_MAX = 0.62
    OPACITY_MIN = 0.55; OPACITY_MAX = 0.95
    CONTRAST_MIN = 0.85; CONTRAST_MAX = 1.25
    # Slew caps (per frame @60fps)
    DW_BAR_WIDTH = 0.0016
    DW_OPACITY = 0.003
    DW_CONTRAST = 0.004
    DW_BASE_SPEED = 0.0015

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.state = SpiralState()
        self._pending_intensity = 0.0
        self._last_update = time.time()
        self._flip_elapsed = 0.0
        self._next_flip_in = self._schedule_next_flip(0.0)
        self._intensity_slew_cooldown = 0.0  # while >0 use half slew caps

    # ---------------- Intensity & scaling ----------------
    def set_intensity(self, v: float):
        v = max(0.0, min(1.0, float(v)))
        if abs(v - self._pending_intensity) > 1e-6:
            # Trigger temporary tighter slew window (~1.5s)
            self._intensity_slew_cooldown = 1.5
        self._pending_intensity = v

    # --- Parameter setters for UI panel (lightweight; adjust targets indirectly) ---
    def set_bar_width(self, base: float, rng: float, cycle_s: float):
        # Adjust internal ranges indirectly via intensity-based breathing; we store overrides for future use
        self.BAR_WIDTH_MIN = max(0.05, min(0.95, base - abs(rng)))
        self.BAR_WIDTH_MAX = max(self.BAR_WIDTH_MIN + 0.01, min(0.99, base + abs(rng)))
        # Cycle not directly used in simplified model; kept for forward compatibility
    def set_twist(self, base: float, rng: float, cycle_s: float):
        self.TWIST_MIN = max(0.0, min(base - abs(rng), 5.0))
        self.TWIST_MAX = max(self.TWIST_MIN + 0.001, min(base + abs(rng), 5.0))
    def set_wobble(self, amp: float, cycle_s: float):
        self.WOBBLE_MIN = max(0.0, min(amp * 0.3, 1.0))
        self.WOBBLE_MAX = max(self.WOBBLE_MIN + 0.0001, min(amp, 1.0))
    def set_flip_cadence(self, cadence_s: float, wave_duration_s: float):
        self.FLIP_PERIOD_MIN = max(5.0, min(cadence_s * 0.6, 7200.0))
        self.FLIP_PERIOD_MAX = max(self.FLIP_PERIOD_MIN + 1.0, min(cadence_s * 1.4, 7200.0))
        self.FLIP_WAVE_MIN = max(1.0, min(wave_duration_s * 0.5, 600.0))
        self.FLIP_WAVE_MAX = max(self.FLIP_WAVE_MIN + 1.0, min(wave_duration_s * 1.5, 600.0))
    def set_vignette(self, v: float):
        self.VIGNETTE_MIN = max(0.0, min(v * 0.5, 2.0))
        self.VIGNETTE_MAX = max(self.VIGNETTE_MIN + 0.001, min(v * 1.5, 2.0))

    # ---------------- Flip scheduling ----------------
    def _schedule_next_flip(self, intensity: float) -> float:
        # intensity 0 -> long period (240s), intensity 1 -> short (120s)
        base_period = self.FLIP_PERIOD_MAX - (self.FLIP_PERIOD_MAX - self.FLIP_PERIOD_MIN) * intensity
        jitter = self.rng.uniform(-45.0, 45.0)
        return max(30.0, base_period + jitter)  # guard against too small

    def force_flip(self):
        if self.state.flip_state == 0:
            self.state.flip_state = 1
            self.state.flip_radius = self.FLIP_RADIUS_START
            self._flip_elapsed = 0.0

    # ---------------- Update loop ----------------
    def update(self, dt: float | None = None) -> SpiralState:
        now = time.time()
        if dt is None:
            dt = now - self._last_update
        if dt <= 0:
            dt = 1/60
        self._last_update = now
        intensity = self._pending_intensity
        st = self.state
        st.intensity = intensity
        # Intensity mappings
        base_speed_target = self.BASE_SPEED_MIN + (self.BASE_SPEED_MAX - self.BASE_SPEED_MIN) * intensity
        wobble_amp = self.WOBBLE_MIN + (self.WOBBLE_MAX - self.WOBBLE_MIN) * intensity
        twist_target = self.TWIST_MIN + (self.TWIST_MAX - self.TWIST_MIN) * intensity
        # Bar width breathing: amplitude 0.04→0.10 around midpoint of clamp
        bw_amp = 0.04 + (0.10 - 0.04) * intensity
        bw_mid = (self.BAR_WIDTH_MIN + self.BAR_WIDTH_MAX) * 0.5
        t_breathe_cycle = 140.0 - (140.0 - 70.0) * intensity
        breathe_phase = (now * (1.0 / t_breathe_cycle)) * math.tau
        bar_width_target = bw_mid + bw_amp * math.sin(breathe_phase) * 0.5  # reduce amplitude so always inside clamp pre-safety
        # Opacity scaling (use upper half of allowed range)
        opacity_target = self.OPACITY_MIN + (self.OPACITY_MAX - self.OPACITY_MIN) * (0.5 + 0.5 * intensity)
        contrast_target = 1.0 + self.CONTRAST_BOOST_MAX * intensity
        vignette_target = self.VIGNETTE_MIN + (self.VIGNETTE_MAX - self.VIGNETTE_MIN) * intensity
        chroma_target = self.CHROMA_MAX * intensity

        # Apply per-frame slew (with tightening if intensity cooldown active)
        tight = self._intensity_slew_cooldown > 0.0
        scale = 0.5 if tight else 1.0
        st.base_speed = self._slew(st.base_speed, base_speed_target, self.DW_BASE_SPEED * scale)
        st.bar_width = self._slew(st.bar_width, bar_width_target, self.DW_BAR_WIDTH * scale)
        st.opacity = self._slew(st.opacity, opacity_target, self.DW_OPACITY * scale)
        st.contrast = self._slew(st.contrast, contrast_target, self.DW_CONTRAST * scale)
        st.twist = self._lerp(st.twist, twist_target, min(1.0, dt * 0.5))  # slower blend
        st.vignette = self._lerp(st.vignette, vignette_target, min(1.0, dt * 0.5))
        st.chromatic_shift = self._slew(st.chromatic_shift, chroma_target, 0.01 * scale)

        # Flip FSM scheduling
        if st.flip_state == 0:
            self._next_flip_in -= dt
            if self._next_flip_in <= 0.0:
                self.force_flip()
                # Pre-schedule next period (will start counting after flip completes)
                self._next_flip_in = self._schedule_next_flip(intensity)
        if st.flip_state == 1:
            wave_duration = self.FLIP_WAVE_MAX - (self.FLIP_WAVE_MAX - self.FLIP_WAVE_MIN) * intensity
            self._flip_elapsed += dt
            prog = min(1.0, self._flip_elapsed / wave_duration)
            st.flip_radius = self.FLIP_RADIUS_START + (self.FLIP_RADIUS_END - self.FLIP_RADIUS_START) * prog
            if prog >= 1.0:
                st.flip_state = 0
                st.flip_radius = self.FLIP_RADIUS_START
                self._flip_elapsed = 0.0
        # Speed wobble + flip local boost (simplified: uniform boost while active)
        wobble = math.sin(now * 2.0 * math.pi * 0.5) * wobble_amp  # 0.5 cps wobble
        flip_boost = 0.03 if st.flip_state == 1 else 0.0
        st.effective_speed = min(self.SPEED_CAP, st.base_speed + wobble + flip_boost)
        st.phase = (st.phase + st.effective_speed * dt) % 10000.0

        # Safety clamps (applied after updates)
        safety = False
        if st.bar_width < self.BAR_WIDTH_MIN: st.bar_width = self.BAR_WIDTH_MIN; safety = True
        if st.bar_width > self.BAR_WIDTH_MAX: st.bar_width = self.BAR_WIDTH_MAX; safety = True
        if st.opacity < self.OPACITY_MIN: st.opacity = self.OPACITY_MIN; safety = True
        if st.opacity > self.OPACITY_MAX: st.opacity = self.OPACITY_MAX; safety = True
        if st.contrast < self.CONTRAST_MIN: st.contrast = self.CONTRAST_MIN; safety = True
        if st.contrast > self.CONTRAST_MAX: st.contrast = self.CONTRAST_MAX; safety = True
        if st.chromatic_shift > self.CHROMA_MAX: st.chromatic_shift = self.CHROMA_MAX; safety = True
        st.safety_clamped = safety

        if self._intensity_slew_cooldown > 0.0:
            self._intensity_slew_cooldown = max(0.0, self._intensity_slew_cooldown - dt)
        return st

    # ---------------- Helpers ----------------
    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * max(0.0, min(1.0, t))

    def _slew(self, cur: float, target: float, max_delta: float) -> float:
        delta = target - cur
        if abs(delta) <= max_delta:
            return target
        return cur + math.copysign(max_delta, delta)

    # ---------------- Export ----------------
    def export_uniforms(self) -> dict[str, float | int]:
        s = self.state
        return {
            "uPhase": s.phase,
            "uBaseSpeed": s.base_speed,
            "uEffectiveSpeed": s.effective_speed,
            "uBarWidth": s.bar_width,
            "uTwist": s.twist,
            "uSpiralOpacity": s.opacity,
            "uContrast": s.contrast,
            "uVignette": s.vignette,
            "uChromaticShift": s.chromatic_shift,
            "uFlipWaveRadius": s.flip_radius,
            "uFlipState": s.flip_state,
            "uIntensity": s.intensity,
            "uSafetyClamped": 1 if s.safety_clamped else 0,
        }
