"""SpiralDirector implementation (    BASE_SPEED_MIN = 0.09; BASE_SPEED_MAX = 0.14
    WOBBLE_MIN = 0.006; WOBBLE_MAX = 0.020
    TWIST_MIN = 0.06; TWIST_MAX = 0.14
    CONTRAST_BOOST_MAX = 0.18
    VIGNETTE_MIN = 0.0; VIGNETTE_MAX = 0.0  # Disabled to prevent background darkening
    CHROMA_MAX = 0.32 core logic).

Responsibilities:
 - Intensity scaling for dynamic parameters (speeds, ranges, contrast, vignette, chromatic shift)
 - Inside-out flip wave FSM with jittered cadence
 - Safety clamps + per-frame slew caps
 - Export of uniform-ready values

The implementation aims for determinism in tests by allowing a seed and accepting dt.
"""
from __future__ import annotations
from dataclasses import dataclass
import math, os, random, time
from typing import Optional

ROTATION_TRACE_ENABLED = bool(
    os.environ.get("MESMERGLASS_SPIRAL_ROTATE_TRACE")
    or os.environ.get("MESMERGLASS_SPIRAL_TRACE")
)

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
    safety_clamped: bool = False

class SpiralDirector:
    # Static configuration (ranges)
    BASE_SPEED_MIN = 0.09; BASE_SPEED_MAX = 0.14
    WOBBLE_MIN = 0.006; WOBBLE_MAX = 0.020
    TWIST_MIN = 0.06; TWIST_MAX = 0.14
    CONTRAST_BOOST_MAX = 0.18
    VIGNETTE_MIN = 0.0; VIGNETTE_MAX = 0.0  # Disabled to prevent background darkening
    CHROMA_MAX = 0.3
    # Flip ranges
    # Safety clamps
    SPEED_CAP = 0.18
    BAR_WIDTH_MIN = 0.36; BAR_WIDTH_MAX = 0.62
    OPACITY_MIN = 0.0; OPACITY_MAX = 1.0  # Allow full range for custom modes
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
        self._intensity_slew_cooldown = 0.0  # while >0 use half slew caps
        self._lock_opacity = False  # When True, prevent automatic opacity evolution (for custom modes)
        
        # High-precision phase accumulator (prevents drift over long runtime)
        self._phase_accumulator = 0.0  # Double-precision accumulator for rotation
        self._rotation_count = 0  # Track full rotations for diagnostics
        
        # Additional spiral parameters for shader
        self.arm_count = 8
        self.arm_color = (1.0, 1.0, 1.0)  # White arms
        self.gap_color = (0.0, 0.0, 0.0)  # Black gaps (for contrast on black background)
        self.blend_mode = 1  # 0=multiply, 1=screen, 2=softlight - screen mode to avoid darkening
        self.color = (1.0, 1.0, 1.0)
        self.resolution = (1920, 1080)
        self.super_samples = 4  # Anti-aliasing samples: 1=none, 4=2x2, 9=3x3, 16=4x4
        self.precision_level = "high"  # low, medium, high
        
        # Trance spiral type and width (NEW)
        self.spiral_type = 3  # 1-7: log, quad, linear, sqrt, inverse, power, modulated (default: linear)
        self.spiral_width = 60  # Degrees per arm: 360, 180, 120, 90, 72, 60
        self.rotation_speed = 4.0  # Rotation speed multiplier (4.0 = normal, up to 40.0 = very fast)
        
        # Trance rendering parameters (NEW)
        self.near_plane = 1.0  # Distance to near plane (fixed, controls FoV)
        self.far_plane = 5.0  # Distance to far plane (1.0 + far_plane_distance, controls zoom)
        self.eye_offset = 0.0  # Eye offset for VR/stereoscopic rendering

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
    def set_vignette(self, v: float):
        self.VIGNETTE_MIN = max(0.0, min(v * 0.5, 2.0))
        self.VIGNETTE_MAX = max(self.VIGNETTE_MIN + 0.001, min(v * 1.5, 2.0))

    def set_arm_count(self, count: int):
        """Set number of spiral arms (2-16)."""
        self.arm_count = max(2, min(16, int(count)))
    
    def set_arm_color(self, r: float, g: float, b: float):
        """Set spiral arm color (RGB 0-1)."""
        self.arm_color = (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
    
    def set_gap_color(self, r: float, g: float, b: float):
        """Set spiral gap color (RGB 0-1)."""
        self.gap_color = (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
    
    def set_blend_mode(self, mode: int):
        """Set blend mode (0=multiply, 1=screen, 2=softlight)."""
        self.blend_mode = max(0, min(2, int(mode)))
    
    def set_opacity(self, opacity: float):
        """Set spiral opacity (0.0-1.0). Locks opacity to prevent automatic evolution."""
        # Clamp to safe range and update state
        self.state.opacity = max(self.OPACITY_MIN, min(self.OPACITY_MAX, opacity))
        # Lock opacity to prevent automatic intensity-based evolution
        self._lock_opacity = True
    
    def set_resolution(self, width: int, height: int):
        """Set screen resolution for aspect ratio correction."""
        self.resolution = (max(1, int(width)), max(1, int(height)))
    
    def set_supersampling(self, samples: int):
        """Set anti-aliasing samples (1=none, 4=2x2, 9=3x3, 16=4x4)."""
        valid_samples = [1, 4, 9, 16]
        self.super_samples = samples if samples in valid_samples else 4
    
    def set_precision(self, level: str):
        """Set floating-point precision level (low, medium, high)."""
        valid_levels = ["low", "medium", "high"]
        self.precision_level = level if level in valid_levels else "high"
    
    def set_spiral_type(self, spiral_type: int):
        """Set spiral type (1-7): log, quad, linear, sqrt, inverse, power, modulated."""
        self.spiral_type = max(1, min(7, int(spiral_type)))
    
    def set_spiral_width(self, width: int):
        """Set spiral width in degrees (360, 180, 120, 90, 72, 60)."""
        valid_widths = [360, 180, 120, 90, 72, 60]
        if width in valid_widths:
            self.spiral_width = width
        else:
            # Find closest valid width
            self.spiral_width = min(valid_widths, key=lambda x: abs(x - width))
    
    def set_rotation_speed(self, speed: float):
        """Set rotation speed in RPM (negative = reverse).

        Unified model: value is RPM, not a legacy multiplier. To preserve the
        legacy "feel" range from the UI (4..40x), the VMC maps x→RPM with a
        gain (default 10x). Here we allow a wider RPM range to avoid unintended
        clamping when higher perceived speeds are desired.
        """
        # Allow negative speeds for reverse rotation; clamp conservatively high
        new_speed = max(-600.0, min(600.0, float(speed)))  # Clamp to ±600 RPM
        
        # Reset phase accumulator if direction changes to prevent direction lag
        if hasattr(self, 'rotation_speed') and hasattr(self, '_phase_accumulator'):
            old_sign = 1 if self.rotation_speed >= 0 else -1
            new_sign = 1 if new_speed >= 0 else -1
            if old_sign != new_sign:
                # Direction changed - reset phase accumulator to prevent direction lag
                self._phase_accumulator = 0.0
        
        self.rotation_speed = new_speed
    
    def change_spiral(self):
        """Randomly change spiral type and width (Trance: visual_api.cpp line 91-99)."""
        # 75% chance to skip change (random_chance(4) in Trance)
        if self.rng.random() < 0.75:
            return
        
        # Change spiral type (1-7)
        self.spiral_type = self.rng.randint(1, 7)
        
        # Change spiral width (360 / (1 + random(6)))
        divisor = 1 + self.rng.randint(0, 5)
        self.spiral_width = 360 // divisor
    
    def rotate_spiral(self, amount: float, dt: float | None = None):
        """
        Rotate spiral using direct RPM calculation instead of legacy Trance formula.
        
        NEW APPROACH: rotation_speed is treated as actual RPM (rotations per minute).
        This bypasses the legacy formula and directly converts RPM to phase increment.
        
        Args:
            amount: Legacy parameter (ignored in new RPM mode)
                   To maintain compatibility with existing calls like rotate_spiral(4.0)
            dt: Delta time in seconds. If None, uses 1/30.0 as fallback (for compatibility)
        """
        # Use provided dt, or fallback to 1/30.0 for compatibility
        if dt is None:
            dt = 1/30.0
        
        # Calculate phase increment: (rotations/minute) / (60 seconds/minute) * (seconds/frame)
        phase_per_second = self.rotation_speed / 60.0
        phase_increment = phase_per_second * dt
        
        if ROTATION_TRACE_ENABLED:
            if not hasattr(self, '_rotate_call_count'):
                self._rotate_call_count = 0
            self._rotate_call_count += 1
            if self._rotate_call_count <= 10:
                import traceback

                stack_lines = traceback.format_stack()
                # Get last few relevant frames (skip this function's frame)
                relevant_stack = ''.join(stack_lines[-4:-1])
                print(
                    f"[rotate_spiral_DEBUG] Call #{self._rotate_call_count}: RPM={self.rotation_speed}, dt={dt:.6f}, phase_increment={phase_increment:.6f}",
                    flush=True,
                )
                print(f"  Caller stack:\n{relevant_stack}", flush=True)
        
        # Use high-precision accumulator to prevent drift  
        self._phase_accumulator += phase_increment
        
        # Normalize when crossing 1.0 boundary (prevents precision loss)
        if self._phase_accumulator >= 1.0:
            full_rotations = int(self._phase_accumulator)
            self._rotation_count += full_rotations
            self._phase_accumulator -= full_rotations
        elif self._phase_accumulator < 0.0:
            full_rotations = int(-self._phase_accumulator) + 1
            self._rotation_count -= full_rotations
            self._phase_accumulator += full_rotations
        
        # Note: state.phase is updated by update() method which reads from _phase_accumulator
        # This separation ensures a single source of truth for the phase value

    # ---------------- Update loop ----------------
    def update(self, dt: float | None = None) -> SpiralState:
        now = time.time()
        if dt is None:
            dt = now - self._last_update
        # CRITICAL: If dt is too small or negative, something is calling update() too frequently
        # In that case, skip the update entirely to prevent double-updates
        if dt <= 0.001:  # Less than 1ms suggests double-call
            logging.getLogger(__name__).warning(f"[spiral.update] dt={dt:.6f}s is too small - skipping update to prevent double-updates")
            return self.state  # Return current state without updating
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
        # Skip opacity evolution if locked (custom mode has direct control)
        if not self._lock_opacity:
            st.opacity = self._slew(st.opacity, opacity_target, self.DW_OPACITY * scale)
        st.contrast = self._slew(st.contrast, contrast_target, self.DW_CONTRAST * scale)
        st.twist = self._lerp(st.twist, twist_target, min(1.0, dt * 0.5))  # slower blend
        st.vignette = self._lerp(st.vignette, vignette_target, min(1.0, dt * 0.5))
        st.chromatic_shift = self._slew(st.chromatic_shift, chroma_target, 0.01 * scale)

        # Speed wobble only (legacy flip wave removed)
        wobble = math.sin(now * 2.0 * math.pi * 0.5) * wobble_amp  # 0.5 cps wobble
        st.effective_speed = min(self.SPEED_CAP, st.base_speed + wobble)
        
        # Rotate spiral using rotation_speed (RPM) and actual dt
        self.rotate_spiral(0.0, dt=dt)  # Pass dt to use measured frame time
        
        # Update state.phase from the high-precision accumulator (set by rotate_spiral)
        st.phase = float(self._phase_accumulator)

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
    def export_uniforms(self) -> dict:
        s = self.state
        now = time.time()
        
        # Calculate aspect ratio
        aspect_ratio = float(self.resolution[0]) / float(self.resolution[1]) if self.resolution[1] > 0 else 1.778
        
        return {
            # Core SpiralDirector uniforms
            "uPhase": s.phase,
            "uBaseSpeed": s.base_speed,
            "uEffectiveSpeed": s.effective_speed,
            "uBarWidth": s.bar_width,
            "uTwist": s.twist,
            "uSpiralOpacity": s.opacity,
            "uContrast": s.contrast,
            "uVignette": s.vignette,
            "uChromaticShift": s.chromatic_shift,
            "uIntensity": 1.0,  # Always 1.0 - intensity removed from system (spiral uses full color)
            "uSafetyClamped": 1 if s.safety_clamped else 0,
            
            # Time and resolution
            "uTime": now,
            # Note: uResolution is set by compositor from actual window size, don't override it
            
            # Visual parameters
            "uArms": self.arm_count,
            "uBlendMode": self.blend_mode,
            "uArmColor": self.arm_color,
            "uGapColor": self.gap_color,
            "uSuperSamples": self.super_samples,
            "uPrecisionLevel": {"low": 0, "medium": 1, "high": 2}.get(self.precision_level, 2),
            # NOTE: uWindowOpacity is NOT exported here - it's managed by LoomCompositor
            # directly via setWindowOpacity() to avoid conflicts with intensity (which is 0.0)
            
            # Trance spiral parameters (NEW)
            "near_plane": self.near_plane,
            "far_plane": self.far_plane,
            "eye_offset": self.eye_offset,
            "aspect_ratio": aspect_ratio,
            "width": float(self.spiral_width),
            "spiral_type": float(self.spiral_type),
            # Use signed phase directly so reverse direction is preserved in the shader.
            # Phase is accumulated from RPM (including sign), so the shader should not
            # multiply by rotation speed again (avoids rpm^2 scaling).
            "time": s.phase,
            "rotation_speed": self.rotation_speed,  # Kept for diagnostics/zoom; ignored by shader rotation
            "acolour": (*self.arm_color, 1.0),  # Convert RGB to RGBA
            "bcolour": (*self.gap_color, 1.0),   # Convert RGB to RGBA
            
            # Legacy compatibility
            "u_time": now,
            "u_color": self.color,
            "u_resolution": self.resolution,
        }
