"""
CustomVisual - User-defined visual playbacks loaded from JSON files.

This class replaces hardcoded Visual Programs with user-configurable playbacks
created in the Visual Playback Creator tool. Custom playbacks define:
- Spiral behavior (type, speed, opacity, reverse) - colors excluded (global setting)
- Media cycling (images/videos, speed, opacity)
- Text overlays (mode, opacity, library)
- Zoom animations (mode, rate, duration)

Custom playbacks are the future-proof replacement for built-in Visual classes.
"""

from __future__ import annotations
import json
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..content.themebank import ThemeBank
    from ..mesmerloom.compositor import LoomCompositor
    from ..content.text_renderer import SplitMode
    from ..engine.text_director import TextDirector

from mesmerglass.mesmerloom.visuals import Visual
from mesmerglass.mesmerloom.cyclers import ActionCycler, ParallelCycler


class CustomVisual(Visual):
    """
    User-defined visual playback loaded from JSON configuration.
    
    CustomVisual reads a playback file and applies settings to compositor, spiral,
    text system, and media. Unlike hardcoded Visual Programs, CustomVisual is
    fully data-driven and supports all settings from Visual Playback Creator.
    
    Playback File Structure:
        {
            "version": "1.0",
            "name": "Playback Name",
            "description": "Optional description",
            "spiral": {
                "type": "logarithmic|quadratic|linear|sqrt|inverse|power|sawtooth",
                "rotation_speed": 4.0,
                "opacity": 0.8,
                "intensity": 0.8,
                "reverse": false
            },
            "media": {
                "mode": "images|videos|both|none",
                "cycle_speed": 50,
                "opacity": 1.0,
                "fade_duration": 0.5,
                "use_theme_bank": true,
                "paths": [],
                "shuffle": false
            },
            "text": {
                "enabled": true,
                "mode": "centered_sync|subtext",
                "opacity": 0.8,
                "use_theme_bank": true,
                "library": [],
                "sync_with_media": true
            },
            "zoom": {
                "mode": "exponential|pulse|linear|none",
                "rate": 0.2
            }
        }
    
    Spiral color fields (arm_color, gap_color) can now be stored per playback
    and are applied when present. Legacy playbacks that omit them continue to
    use the launcher's global color selection.
    
    See docs/technical/custom-mode-settings-reference.md for complete details.
    """

    ACCEL_ROTATION_START_X = 4.0
    ACCEL_ROTATION_END_X = 24.0
    ACCEL_MEDIA_START_SPEED = 50.0
    ACCEL_MEDIA_END_SPEED = 100.0
    ACCEL_ZOOM_START_RATE = 0.4
    ACCEL_ZOOM_END_RATE = 3.0
    ACCEL_RPM_GAIN = 10.0  # Matches PlaybackEditor.SPEED_GAIN for parity
    ACCEL_MIN_DURATION = 0.1
    ACCEL_MEDIA_UPDATE_COOLDOWN = 0.15
    ACCEL_MEDIA_SMOOTH_DELTA = 1.0
    ACCEL_MEDIA_APPLY_EPSILON = 0.25
    
    def __init__(
        self,
        playback_path: Path,
        theme_bank: Optional[ThemeBank] = None,
        on_change_image: Optional[Callable[[int], None]] = None,
        on_change_video: Optional[Callable[[Any], None]] = None,
        on_rotate_spiral: Optional[Callable[[float], None]] = None,
        compositor: Optional[LoomCompositor] = None,
        text_director: Optional[TextDirector] = None
    ):
        """
        Initialize CustomVisual from playback file.
        
        Args:
            playback_path: Path to JSON playback file
            theme_bank: ThemeBank for media/text lookup (if use_theme_bank=true)
            on_change_image: Callback for image switching
            on_change_video: Callback for video switching
            on_rotate_spiral: Callback for spiral rotation
            compositor: LoomCompositor for applying settings
            text_director: TextDirector for text system configuration
        """
        super().__init__()
        
        self.logger = logging.getLogger(__name__)
        self.playback_path = Path(playback_path)
        self.theme_bank = theme_bank
        self.compositor = compositor
        self.text_director = text_director
        
        # Multi-display support: Track secondary compositors for zoom sync
        self._secondary_compositors: List[Any] = []
        
        # Callbacks
        self.on_change_image = on_change_image
        self.on_change_video = on_change_video
        self.on_rotate_spiral = on_rotate_spiral
        
        # Playback configuration (loaded from JSON)
        self.config: Dict[str, Any] = {}
        self.playback_name: str = "Unknown Playback"
        
        # Media state
        self._current_media_index = 0
        self._media_paths: List[Path] = []
        self._media_mode: str = "images"  # "images", "videos", "both", "none"
        self._use_theme_bank_media = False  # Flag to use ThemeBank.get_image() instead of paths
        self._theme_bank_media_cycle: str = "image"
        self._showing_video = False  # Tracks whether the current media is a video
        
        # Frame counting for cycling
        self._frame_counter = 0
        self._frames_per_cycle = 180  # Default 3 seconds at 60fps
        
        # Cycle tracking (Phase 2 - for session synchronization)
        self._cycle_marker = 0  # Increments each time media changes

        # Strict mode (Launcher-enforced exact playback behavior)
        # When enabled, this visual will not schedule media changes via its
        # internal cycler. The Launcher will drive media changes using a
        # precise QTimer at the exact interval derived from the playback.
        self._strict_mode = False

        # Accelerate runtime state
        self._accelerate_enabled = False
        self._accelerate_duration = 30.0
        self._accelerate_rotation_start_x: Optional[float] = None
        self._accelerate_media_start_speed: Optional[float] = None
        self._accelerate_zoom_start_rate: Optional[float] = None
        self._accelerate_start_time: Optional[float] = None
        self._accelerate_progress = 0.0
        self._accelerate_media_interval_s: Optional[float] = None
        self._accelerate_media_speed_current: Optional[float] = None
        self._accelerate_next_media_time: Optional[float] = None
        self._accelerate_media_speed_smoothed: Optional[float] = None
        self._accelerate_last_interval_update_ts: Optional[float] = None
        self._accelerate_last_applied_speed: Optional[float] = None
        self._accelerate_last_log_time: Optional[float] = None
        
        # Load and validate playback file
        self._load_playback_file()
        
        # Apply initial settings
        self._apply_initial_settings()
        self._load_accelerate_settings()
    
    # ===== Multi-Display Support =====
    
    def set_secondary_compositors(self, compositors: List[Any]) -> None:
        """Set secondary compositors for multi-display zoom synchronization.
        
        Args:
            compositors: List of secondary LoomWindowCompositor instances
        """
        self._secondary_compositors = compositors.copy() if compositors else []
        self.logger.debug(f"[CustomVisual] Set {len(self._secondary_compositors)} secondary compositors")
    
    def _get_all_compositors(self) -> List[Any]:
        """Get list of all compositors (primary + secondaries)."""
        compositors = []
        if self.compositor:
            compositors.append(self.compositor)
        compositors.extend(self._secondary_compositors)
        return compositors
    
    # ===== Playback File Loading =====
    
    def _load_playback_file(self) -> None:
        """Load and validate JSON playback file."""
        try:
            if not self.playback_path.exists():
                raise FileNotFoundError(f"Playback file not found: {self.playback_path}")
            
            with open(self.playback_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            # Validate version
            version = self.config.get("version", "1.0")
            if version != "1.0":
                self.logger.warning(f"[CustomVisual] Unknown playback version: {version}")
            
            # Extract playback name
            self.playback_name = self.config.get("name", self.playback_path.stem)
            
            self.logger.info(f"[CustomVisual] Loaded playback: {self.playback_name} from {self.playback_path.name}")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"[CustomVisual] Invalid JSON in playback file: {e}")
            raise ValueError(f"Invalid playback file JSON: {e}")
        except Exception as e:
            self.logger.error(f"[CustomVisual] Failed to load playback file: {e}")
            raise
    
    def _apply_initial_settings(self) -> None:
        """Apply playback settings to compositor, spiral, and text systems."""
        # Apply spiral settings (excluding colors - those are global)
        self._apply_spiral_settings()
        
        # Apply media settings and build media list
        self._apply_media_settings()
        
        # Apply text settings
        self._apply_text_settings()
        
        # Apply zoom settings
        self._apply_zoom_settings()
        
        self.logger.info(f"[CustomVisual] '{self.playback_name}' initialized with {len(self._media_paths)} media items")
    
    def reapply_all_settings(self) -> None:
        """Re-apply all custom playback settings (called after compositor is ready)."""
        self.logger.info("[CustomVisual] Re-applying all settings...")
        self._apply_spiral_settings()
        self._apply_media_settings()
        self._apply_text_settings()
        self._apply_zoom_settings()
        self._load_accelerate_settings()
        self.logger.info("[CustomVisual] All settings re-applied")
    
    def reload_from_disk(self) -> bool:
        """
        Reload JSON file from disk and re-apply all settings.
        
        Useful for live editing playback files without restarting launcher.
        
        Returns:
            True if reload succeeded, False on error
        """
        try:
            self.logger.info(f"[CustomVisual] Reloading playback from disk: {self.playback_path.name}")
            
            # Re-load JSON file
            self._load_playback_file()
            
            # Re-apply all settings with new config
            self._apply_spiral_settings()
            self._apply_media_settings()
            self._apply_text_settings()
            self._apply_zoom_settings()
            self._load_accelerate_settings()
            
            self.logger.info(f"[CustomVisual] Successfully reloaded '{self.playback_name}' from disk")
            return True
            
        except Exception as e:
            self.logger.error(f"[CustomVisual] Failed to reload playback: {e}")
            return False
    
    # ===== Settings Application =====
    
    def _apply_spiral_settings(self) -> None:
        """Apply spiral configuration (type, speed, opacity, reverse)."""
        spiral_config = self.config.get("spiral", {})
        
        if not self.compositor:
            self.logger.warning("[CustomVisual] No compositor available")
            return
        
        # Guard against deleted/invalid compositor (C++ object wrapped by Python)
        try:
            # Test if compositor is still valid by checking a basic attribute
            if hasattr(self.compositor, 'spiral_director'):
                pass  # Compositor is valid
        except RuntimeError as e:
            self.logger.error(f"[CustomVisual] Compositor has been deleted: {e}")
            return
        
        # Support both LoomCompositor (director) and LoomWindowCompositor (spiral_director)
        spiral = None
        if hasattr(self.compositor, 'spiral_director'):
            spiral = self.compositor.spiral_director
        elif hasattr(self.compositor, 'director'):
            spiral = self.compositor.director
        
        if not spiral:
            self.logger.warning("[CustomVisual] No spiral director available")
            return
        
        # Spiral type (logarithmic, quadratic, linear, etc.)
        # Convert string name to numeric ID (1-7)
        spiral_type_str = spiral_config.get("type", "logarithmic")
        spiral_type_map = {
            "logarithmic": 1,
            "quadratic": 2,
            "linear": 3,
            "sqrt": 4,
            "inverse": 5,  # Fixed: was "cubic" - matches visual_mode_creator.py
            "power": 6,
            "sawtooth": 7  # Fixed: was "hyperbolic" - matches visual_mode_creator.py
        }
        
        # If it's already an int, use it; otherwise map the string
        if isinstance(spiral_type_str, int):
            spiral_type = spiral_type_str
        else:
            spiral_type = spiral_type_map.get(spiral_type_str.lower(), 1)  # Default to logarithmic
        
        if hasattr(spiral, 'set_spiral_type'):
            spiral.set_spiral_type(spiral_type)
            self.logger.info(f"[CustomVisual] Applied spiral type: {spiral_type_str} (ID={spiral_type})")
        
        # Rotation speed (negative = reverse)
        rotation_speed = spiral_config.get("rotation_speed", 4.0)
        reverse = spiral_config.get("reverse", False)
        self.logger.info(f"[CustomVisual] DEBUG: Read rotation_speed={rotation_speed} (type={type(rotation_speed).__name__}), reverse={reverse}")
        if reverse:
            rotation_speed = -abs(rotation_speed)  # Ensure negative
        self.logger.info(f"[CustomVisual] DEBUG: After reverse processing: rotation_speed={rotation_speed}")
        if hasattr(spiral, 'set_rotation_speed'):
            spiral.set_rotation_speed(rotation_speed)
            # Verify it was actually set
            actual_speed = spiral.rotation_speed
            self.logger.info(f"[CustomVisual] Applied rotation_speed={rotation_speed}x → Actual spiral.rotation_speed={actual_speed} (reverse={reverse})")
        
        # Spiral opacity
        opacity = spiral_config.get("opacity", 1.0)
        if hasattr(spiral, 'set_opacity'):
            spiral.set_opacity(opacity)
            self.logger.info(f"[CustomVisual] Applied spiral opacity: {opacity}")
        
        # NOTE: Intensity removed - reserved for future use
        # Spiral will use its default intensity (0.0) or whatever is set globally
        
        def _color_tuple(value):
            """Validate and clamp RGB triples stored in playback JSON."""
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                return None
            try:
                clamped = tuple(max(0.0, min(1.0, float(c))) for c in value)
            except Exception:
                return None
            return clamped

        arm_color = _color_tuple(spiral_config.get("arm_color"))
        gap_color = _color_tuple(spiral_config.get("gap_color"))
        if arm_color and hasattr(spiral, 'set_arm_color'):
            spiral.set_arm_color(*arm_color)
            self.logger.info(f"[CustomVisual] Applied arm color: {arm_color}")
        if gap_color and hasattr(spiral, 'set_gap_color'):
            spiral.set_gap_color(*gap_color)
            self.logger.info(f"[CustomVisual] Applied gap color: {gap_color}")
    
    @staticmethod
    def _cycle_speed_to_frames(speed: int) -> tuple[int, float]:
        """Convert 1-100 cycle speed into (frames, target_ms) at 60 FPS."""
        import math
        speed = max(1, min(100, int(speed)))
        normalized = (speed - 1) / 99.0
        interval_ms = 10000 * math.pow(0.005, normalized)
        frames = max(1, round((interval_ms / 1000.0) * 60.0))
        return frames, interval_ms

    def _apply_media_settings(self) -> None:
        """Apply media configuration and build media path list."""
        media_config = self.config.get("media", {})
        
        # Media mode: "images", "videos", "both", "none"
        self._media_mode = media_config.get("mode", "images")
        
        # Media cycling speed (1-100) → frames per cycle
        # Use exponential curve matching visual_mode_creator
        cycle_speed = max(1, min(100, media_config.get("cycle_speed", 50)))
        self._frames_per_cycle, target_interval_ms = self._cycle_speed_to_frames(cycle_speed)
        actual_interval_ms = (self._frames_per_cycle / 60.0) * 1000.0  # Calculate actual timing at 60 FPS
        self.logger.info(f"[CustomVisual] Applied media cycle speed: {cycle_speed} → {self._frames_per_cycle} frames ({actual_interval_ms:.0f}ms at 60fps, target: {target_interval_ms:.0f}ms)")
        
        # CRITICAL: Clear old cycler so new one will be built with updated _frames_per_cycle
        # Without this, the old cycler continues running with the previous playback's period
        self._cycler = None
        self.logger.debug(f"[CustomVisual] Cleared cycler to force rebuild with new period={self._frames_per_cycle}")
        
        # Fade duration (disabled)
        if self.compositor and hasattr(self.compositor, 'set_fade_duration'):
            self.compositor.set_fade_duration(0.0)
            self.logger.info("[CustomVisual] Media fades disabled; using instant cuts")
        
        # Build media path list or configure ThemeBank usage
        use_theme_bank = media_config.get("use_theme_bank", True)
        
        if use_theme_bank and self.theme_bank:
            # Media Bank: Check for bank_selections (indices into launcher's media_bank)
            bank_selections = media_config.get("bank_selections", [0, 1])  # Default to first two (MEDIA folders)
            
            # Notify launcher to rebuild ThemeBank with selected banks only
            # The launcher has the _media_bank array and will filter it
            if self.compositor and hasattr(self.compositor, 'parent') and self.compositor.parent():
                parent = self.compositor.parent()
                # Try to find the launcher window
                while parent and not hasattr(parent, '_rebuild_media_library_from_selections'):
                    parent = parent.parent() if hasattr(parent, 'parent') and callable(parent.parent) else None
                
                if parent and hasattr(parent, '_rebuild_media_library_from_selections'):
                    self.logger.info(f"[CustomVisual] Applying Media Bank selections: {bank_selections}")
                    parent._rebuild_media_library_from_selections(bank_selections)
                else:
                    self.logger.warning("[CustomVisual] Could not find launcher to apply bank selections")
            
            # Use ThemeBank.get_image() directly instead of building path list
            # ThemeBank provides images dynamically with internal shuffling/weighting
            self._use_theme_bank_media = True
            self._media_paths = []  # Empty - not used when ThemeBank active
            self.logger.debug(f"[CustomVisual] Using ThemeBank dynamic media ({self._media_mode}) with bank selections: {bank_selections}")
        else:
            # Use explicit paths from config (legacy mode)
            self._use_theme_bank_media = False
            paths = media_config.get("paths", [])
            self._media_paths = [Path(p) for p in paths]
            self.logger.debug(f"[CustomVisual] Using explicit paths: {len(self._media_paths)} items")
            
            # Optional: shuffle explicit paths
            shuffle = media_config.get("shuffle", False)
            if shuffle and self._media_paths:
                import random
                random.shuffle(self._media_paths)
                self.logger.debug("[CustomVisual] Media paths shuffled")

    def _load_theme_bank_media(self) -> None:
        """Request the next ThemeBank media item based on mode preferences."""
        if not self.theme_bank:
            self.logger.warning("[CustomVisual] ThemeBank requested but not available")
            return

        if self._media_mode == "images":
            self._request_theme_bank_image()
            return

        if self._media_mode == "videos":
            if not self._request_theme_bank_video():
                self.logger.warning("[CustomVisual] ThemeBank has no videos; falling back to images")
                self._request_theme_bank_image()
            return

        if self._media_mode == "both":
            # Alternate image/video preference, but gracefully fall back if one type unavailable
            for _ in range(2):
                target = self._theme_bank_media_cycle
                loader = self._request_theme_bank_video if target == "video" else self._request_theme_bank_image
                if loader():
                    # Flip preference for next call
                    self._theme_bank_media_cycle = "video" if target == "image" else "image"
                    return
                # Try the other media type next
                self._theme_bank_media_cycle = "video" if target == "image" else "image"

            self.logger.warning("[CustomVisual] ThemeBank 'both' mode could not load image or video")
            return

        # media_mode == "none" or unexpected value
        self.logger.debug(f"[CustomVisual] ThemeBank media skipped (mode={self._media_mode})")

    def _request_theme_bank_image(self) -> bool:
        """Trigger ThemeBank image callback. Returns True on success."""
        if not self.on_change_image:
            self.logger.error("[CustomVisual] on_change_image callback missing for ThemeBank image request")
            return False
        try:
            # ThemeBank explicitly wants an image; ensure downstream render paths know it
            self._showing_video = False
            self.logger.info("[CustomVisual] Calling on_change_image(0) for ThemeBank")
            self.on_change_image(0)
            self.logger.debug("[CustomVisual] ThemeBank image request dispatched")
            return True
        except Exception as exc:
            self.logger.error(f"[CustomVisual] ThemeBank image callback failed: {exc}")
            return False

    def _request_theme_bank_video(self) -> bool:
        """Request a ThemeBank video path and forward to the video callback."""
        if not self.theme_bank or not hasattr(self.theme_bank, "get_video"):
            self.logger.debug("[CustomVisual] ThemeBank video support unavailable")
            return False

        try:
            video_path = self.theme_bank.get_video()
        except Exception as exc:
            self.logger.error(f"[CustomVisual] ThemeBank get_video failed: {exc}")
            return False

        if not video_path:
            self.logger.debug("[CustomVisual] ThemeBank returned no video path")
            return False

        if not self.on_change_video:
            self.logger.error("[CustomVisual] on_change_video callback missing; cannot play ThemeBank video")
            return False

        try:
            # Mark upcoming media as video so VisualDirector pushes frames to compositor
            self._showing_video = True
            self.logger.info(f"[CustomVisual] Requesting ThemeBank video: {video_path}")
            self.on_change_video(video_path)
            return True
        except Exception as exc:
            self.logger.error(f"[CustomVisual] ThemeBank video callback failed: {exc}")
            return False

    def is_showing_video(self) -> bool:
        """Expose whether the visual is currently showing a video to callers like VisualDirector."""
        return bool(getattr(self, "_showing_video", False))
    
    def _apply_text_settings(self) -> None:
        """Apply text configuration to TextDirector."""
        text_config = self.config.get("text", {})
        
        if not self.text_director:
            self.logger.warning("[CustomVisual] No TextDirector available")
            return
        
        # Text enabled
        enabled = text_config.get("enabled", True)
        self.text_director.set_enabled(enabled)
        
        if not enabled:
            self.logger.debug("[CustomVisual] Text rendering disabled")
            return
        
        # Text mode: "centered_sync", "subtext", "none"
        from mesmerglass.content.text_renderer import SplitMode
        text_mode = text_config.get("mode", "centered_sync")
        
        if text_mode == "centered_sync":
            split_mode = SplitMode.CENTERED_SYNC
        elif text_mode == "subtext":
            split_mode = SplitMode.SUBTEXT
        else:
            split_mode = SplitMode.CENTERED_SYNC  # Default
        
        # Text opacity
        opacity = text_config.get("opacity", 1.0)
        if hasattr(self.text_director, 'set_opacity'):
            self.text_director.set_opacity(opacity)
        
        # Text color (defaults to white for backward compatibility)
        target_color = text_config.get("color")
        if not isinstance(target_color, (list, tuple)) or len(target_color) < 3:
            target_color = (1.0, 1.0, 1.0)
        try:
            r, g, b = (
                max(0.0, min(1.0, float(target_color[i] if i < len(target_color) else 1.0)))
                for i in range(3)
            )
        except Exception:
            r, g, b = (1.0, 1.0, 1.0)
        if hasattr(self.text_director, 'set_text_color'):
            self.text_director.set_text_color(r, g, b)

        # Font selection priority: explicit font → ThemeBank font → default renderer font
        explicit_font = text_config.get("font_path")
        use_font_bank = text_config.get("use_font_bank", True)
        applied_font: Optional[str] = None
        font_locked = (
            hasattr(self.text_director, "has_user_font_override")
            and self.text_director.has_user_font_override()
        )
        if hasattr(self.text_director, "set_font_path") and not font_locked:
            if explicit_font:
                applied_font = explicit_font
                self.text_director.set_font_path(explicit_font, user_set=False)
            elif use_font_bank and self.theme_bank and hasattr(self.theme_bank, "pick_font_for_playback"):
                bank_font = self.theme_bank.pick_font_for_playback()
                applied_font = bank_font
                self.text_director.set_font_path(bank_font, user_set=False)
            else:
                self.text_director.set_font_path(None, user_set=False)

        if font_locked:
            self.logger.info("[CustomVisual] Text font locked by user override")
        elif applied_font:
            try:
                font_name = Path(applied_font).name
            except Exception:
                font_name = applied_font
            self.logger.info(f"[CustomVisual] Text font set to {font_name}")
        else:
            self.logger.info("[CustomVisual] Text font using renderer default")

        # Text library
        use_theme_bank = text_config.get("use_theme_bank", True)
        
        # Check if user has set custom text library via Text tab
        user_has_custom_texts = self.text_director and self.text_director.has_user_text_library()
        
        # DEBUG: Comprehensive text loading trace
        self.logger.info(f"[CustomVisual] Text loading: use_theme_bank={use_theme_bank}, theme_bank={self.theme_bank is not None}, user_has_custom_texts={user_has_custom_texts}")
        
        if user_has_custom_texts:
            # User has customized text library in Text tab - respect their choice
            self.logger.info(f"[CustomVisual] Preserving user's custom text library from Text tab")
        if user_has_custom_texts:
            # User has customized text library in Text tab - respect their choice
            self.logger.info(f"[CustomVisual] Preserving user's custom text library from Text tab")
        elif use_theme_bank and self.theme_bank:
            # Get text from ThemeBank
            has_text_lines = hasattr(self.theme_bank, 'text_lines')
            self.logger.info(f"[CustomVisual] ThemeBank has text_lines attribute: {has_text_lines}")
            
            if has_text_lines:
                text_lines = list(self.theme_bank.text_lines)
                self.logger.info(f"[CustomVisual] ThemeBank text_lines content: {text_lines[:3] if len(text_lines) > 0 else '[]'} (showing first 3)")
            else:
                text_lines = []
                self.logger.warning(f"[CustomVisual] ThemeBank missing text_lines attribute!")
            
            # Fallback to sample texts if ThemeBank is empty
            if not text_lines:
                text_lines = [
                    "Focus on my words",
                    "Let your mind relax",
                    "Deeper and deeper",
                    "Feel the spiral pull you in",
                    "Your thoughts are fading",
                    "Obey and submit",
                    "You are falling deeper",
                    "Let go of control",
                    "My words guide you",
                    "Deeper with every breath"
                ]
                self.logger.info(f"[CustomVisual] ThemeBank text is empty - using {len(text_lines)} sample texts")
            
            self.text_director.set_text_library(text_lines, default_split_mode=split_mode, user_set=False)
            self.logger.info(f"[CustomVisual] Called set_text_library with {len(text_lines)} lines, split_mode={split_mode}")
        else:
            # Use explicit text library from config
            text_lines = text_config.get("library", [])
            self.text_director.set_text_library(text_lines, default_split_mode=split_mode, user_set=False)
            self.logger.info(f"[CustomVisual] Using explicit texts: {len(text_lines)} lines")
        
        # Configure sync/manual timing (default to sync unless explicit override)
        sync_with_media = text_config.get("sync_with_media", True)
        manual_cycle_speed = int(text_config.get(
            "manual_cycle_speed",
            self.config.get("media", {}).get("cycle_speed", 50)
        ))
        frames_per_text, _ = self._cycle_speed_to_frames(manual_cycle_speed)
        if hasattr(self.text_director, "configure_sync"):
            self.text_director.configure_sync(sync_with_media=sync_with_media, frames_per_text=frames_per_text)
        self.logger.info(
            f"[CustomVisual] Text sync={'media' if sync_with_media else 'manual'} "
            f"manual_speed={manual_cycle_speed} ({frames_per_text} frames)"
        )
        
        self.logger.info(f"[CustomVisual] Text application complete: mode={text_mode}, enabled={enabled}, opacity={opacity}")
    
    def _restart_zoom_animation(self, duration_override: Optional[int] = None) -> None:
        """Restart zoom animation from 1.0 (called on each media change)."""
        zoom_config = self.config.get("zoom", {})
        zoom_mode = zoom_config.get("mode", "none")
        
        if zoom_mode == "none":
            return
        
        # Get all compositors (primary + secondaries)
        all_compositors = self._get_all_compositors()
        if not all_compositors:
            return
        
        # Get media cycle duration for zoom animation (matches cycle speed exactly)
        duration_frames = duration_override or getattr(self, '_frames_per_cycle', 127)
        duration_frames = max(1, int(duration_frames))
        duration_seconds = duration_frames / 60.0  # Convert to seconds at 60fps
        
        # For exponential/falling modes, calculate rate from duration
        # Formula: zoom_current = zoom_start * exp(rate * time)
        # At end of duration: zoom_target = zoom_start * exp(rate * duration)
        # Therefore: rate = ln(zoom_target / zoom_start) / duration
        zoom_start = 1.0
        zoom_target = 1.5
        
        if zoom_mode in ("exponential", "falling"):
            import math
            zoom_rate = math.log(zoom_target / zoom_start) / duration_seconds
            # For falling mode, use negative rate
            if zoom_mode == "falling":
                zoom_rate = -zoom_rate
        else:
            # For linear/pulse modes, use config rate (or default)
            zoom_rate = zoom_config.get("rate", 0.5)
        
        # Restart zoom on ALL compositors (primary + secondaries)
        for comp in all_compositors:
            if hasattr(comp, 'start_zoom_animation'):
                comp.start_zoom_animation(
                    start_zoom=zoom_start,
                    target_zoom=zoom_target,
                    duration_frames=duration_frames,
                    mode=zoom_mode,
                    rate=zoom_rate
                )
        
        self.logger.debug(
            "[CustomVisual] Restarted zoom animation on %d compositor(s): mode=%s, rate=%.4f, duration=%d frames (%.2fs)",
            len(all_compositors),
            zoom_mode,
            zoom_rate,
            duration_frames,
            duration_seconds,
        )
    
    def _apply_zoom_settings(self) -> None:
        """Apply zoom animation settings to all compositors."""
        zoom_config = self.config.get("zoom", {})
        
        # Get all compositors (primary + secondaries)
        all_compositors = self._get_all_compositors()
        if not all_compositors:
            return
        
        # Zoom mode: "none", "exponential", "falling", "linear", "pulse", "in", "out"
        zoom_mode = zoom_config.get("mode", "none")
        zoom_rate = zoom_config.get("rate", 0.5)
        
        if zoom_mode == "none":
            # Disable zoom on all compositors
            for comp in all_compositors:
                if hasattr(comp, 'set_zoom_rate'):
                    comp.set_zoom_rate(0.0)
                if hasattr(comp, 'set_zoom_animation_enabled'):
                    comp.set_zoom_animation_enabled(False)
            self.logger.info(f"[CustomVisual] Zoom disabled on {len(all_compositors)} compositor(s)")
        else:
            # Enable zoom animation on all compositors
            for comp in all_compositors:
                if hasattr(comp, 'set_zoom_animation_enabled'):
                    comp.set_zoom_animation_enabled(True)
                
                # Start zoom animation with mode and rate
                if hasattr(comp, 'start_zoom_animation'):
                    comp.start_zoom_animation(
                        start_zoom=1.0,
                        target_zoom=1.5,  # End zoom level
                        mode=zoom_mode,
                        rate=zoom_rate
                    )
                elif hasattr(comp, 'set_zoom_rate'):
                    # Fallback: use simple zoom rate if start_zoom_animation not available
                    rate = zoom_rate if zoom_mode in ["exponential", "in"] else -zoom_rate
                    comp.set_zoom_rate(rate)
            
            self.logger.info(f"[CustomVisual] Applied zoom animation on {len(all_compositors)} compositor(s): mode={zoom_mode}, rate={zoom_rate}")

    # ===== Accelerate Handling =====

    def _load_accelerate_settings(self) -> None:
        """Load accelerate configuration from playback JSON and reset runtime state."""
        self.logger.info(f"[CustomVisual][ACCEL-LOAD] _load_accelerate_settings() called")
        accel_config = self.config.get("accelerate") or {}
        self.logger.info(f"[CustomVisual][ACCEL-LOAD] accel_config: {accel_config}")
        spiral_config = self.config.get("spiral", {})
        media_config = self.config.get("media", {})
        zoom_config = self.config.get("zoom", {})

        self._accelerate_enabled = bool(accel_config.get("enabled", False))
        self.logger.info(f"[CustomVisual][ACCEL-LOAD] _accelerate_enabled set to: {self._accelerate_enabled}")
        duration = float(accel_config.get("duration", 30.0))
        self._accelerate_duration = max(self.ACCEL_MIN_DURATION, duration)

        default_rotation_x = abs(float(spiral_config.get("rotation_speed", 40.0))) / self.ACCEL_RPM_GAIN
        default_media_speed = float(media_config.get("cycle_speed", 50.0))
        default_zoom_rate = float(zoom_config.get("rate", 0.2))

        self._accelerate_rotation_start_x = self._coerce_float(
            accel_config.get("start_rotation_x"),
            default_rotation_x,
        )
        self._accelerate_media_start_speed = max(
            self.ACCEL_MEDIA_START_SPEED,
            self._coerce_float(
                accel_config.get("start_media_speed"),
                default_media_speed,
            )
        )
        self._accelerate_zoom_start_rate = self._coerce_float(
            accel_config.get("start_zoom_rate"),
            default_zoom_rate,
        )

        self._reset_accelerate_runtime_state()
        self.set_strict_mode(self._accelerate_enabled)

    @staticmethod
    def _coerce_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(fallback)

    def _reset_accelerate_runtime_state(self) -> None:
        self._accelerate_start_time = None
        self._accelerate_progress = 0.0
        self._accelerate_media_interval_s = None
        self._accelerate_media_speed_current = None
        self._accelerate_next_media_time = None
        self._accelerate_media_speed_smoothed = None
        self._accelerate_last_interval_update_ts = None
        self._accelerate_last_applied_speed = None
        self._accelerate_last_log_time = None

    def _runtime_frame_tick(self) -> None:
        """Run per-frame maintenance (accelerate + diagnostics)."""
        self._frame_counter += 1

        if not self._accelerate_enabled:
            return

        self._update_accelerate_effects()
        self._tick_strict_media_cycle()

        if not self.logger.isEnabledFor(logging.DEBUG):
            return

        now = time.perf_counter()
        last_log = self._accelerate_last_log_time or 0.0
        if (now - last_log) < 1.0:
            return

        self._accelerate_last_log_time = now
        next_media_in = (self._accelerate_next_media_time or now) - now
        self.logger.debug(
            "[CustomVisual][strict] frame=%d accel_progress=%.3f media_speed=%.1f interval=%.3fs next_in=%.3fs",
            self._frame_counter,
            self._accelerate_progress,
            self._accelerate_media_speed_smoothed or 0.0,
            self._accelerate_media_interval_s or 0.0,
            max(0.0, next_media_in),
        )

    def _update_accelerate_effects(self, *, force: bool = False) -> None:
        """Apply accelerate overrides when enabled."""
        if not self._accelerate_enabled:
            return

        now = time.perf_counter()
        if force or self._accelerate_start_time is None:
            self._accelerate_start_time = now
            elapsed = 0.0
            self.logger.info(f"[CustomVisual][ACCEL] Starting acceleration at time {now:.6f}")
        else:
            elapsed = now - self._accelerate_start_time

        duration = max(self.ACCEL_MIN_DURATION, self._accelerate_duration)
        progress = max(0.0, min(1.0, elapsed / duration))
        self._accelerate_progress = progress

        rotation_start = self._accelerate_rotation_start_x or 4.0
        media_start = self._accelerate_media_start_speed or 50.0
        zoom_start = self._accelerate_zoom_start_rate or 0.2

        rotation_target = max(rotation_start, self.ACCEL_ROTATION_END_X)
        media_target = max(media_start, self.ACCEL_MEDIA_END_SPEED)
        zoom_target = max(zoom_start, self.ACCEL_ZOOM_END_RATE)

        rotation_x = rotation_start + (rotation_target - rotation_start) * progress
        media_speed = media_start + (media_target - media_start) * progress
        zoom_rate = zoom_start + (zoom_target - zoom_start) * progress

        if force or elapsed < 1.0:  # Log first second
            self.logger.info(f"[CustomVisual][ACCEL] Progress: {progress:.3f}, media_speed: {media_speed:.1f}, rotation: {rotation_x:.1f}, zoom: {zoom_rate:.2f}")

        self._apply_accelerate_rotation(rotation_x)
        self._apply_accelerate_media_speed(media_speed)
        self._apply_accelerate_zoom_rate(zoom_rate)

    def _apply_accelerate_rotation(self, x_value: float) -> None:
        spiral = None
        if hasattr(self.compositor, 'spiral_director'):
            spiral = self.compositor.spiral_director
        elif hasattr(self.compositor, 'director'):
            spiral = self.compositor.director

        if not spiral:
            return

        rpm = float(x_value) * self.ACCEL_RPM_GAIN
        if self.config.get("spiral", {}).get("reverse", False):
            rpm = -abs(rpm)
        spiral.set_rotation_speed(rpm)

    def _apply_accelerate_media_speed(self, speed_value: float) -> None:
        speed_target = max(1.0, min(100.0, float(speed_value)))
        self._accelerate_media_speed_current = speed_target

        smoothed = self._accelerate_media_speed_smoothed
        delta_cap = self.ACCEL_MEDIA_SMOOTH_DELTA
        if smoothed is None:
            smoothed = speed_target
        else:
            delta = speed_target - smoothed
            if abs(delta) > delta_cap:
                smoothed += delta_cap if delta > 0 else -delta_cap
            else:
                smoothed = speed_target
        smoothed = max(1.0, min(100.0, smoothed))
        self._accelerate_media_speed_smoothed = smoothed

        last_speed = self._accelerate_last_applied_speed
        if last_speed is not None and abs(last_speed - smoothed) < self.ACCEL_MEDIA_APPLY_EPSILON:
            return

        now = time.perf_counter()
        if (
            self._accelerate_last_interval_update_ts is not None
            and (now - self._accelerate_last_interval_update_ts) < self.ACCEL_MEDIA_UPDATE_COOLDOWN
        ):
            return

        self._accelerate_last_interval_update_ts = now
        self._accelerate_last_applied_speed = smoothed

        frames, _interval_ms = self._cycle_speed_to_frames(int(round(smoothed)))
        base_frames = max(1, int(getattr(self, '_frames_per_cycle', 300)))
        if frames > base_frames:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(
                    "[CustomVisual][accelerate] clamped interval: requested=%d frames base=%d",
                    frames,
                    base_frames,
                )
            frames = base_frames
        interval_s = frames / 60.0  # Remove ACCEL_MIN_DURATION clamp to allow true high speeds
        self._accelerate_media_interval_s = interval_s
        
        # Only set next media time if not already scheduled (first initialization)
        # Otherwise, let the existing schedule continue - new interval applies to NEXT cycle
        if self._accelerate_next_media_time is None:
            self._accelerate_next_media_time = now + interval_s

    def _apply_accelerate_zoom_rate(self, rate: float) -> None:
        all_compositors = self._get_all_compositors()
        if not all_compositors:
            return

        for comp in all_compositors:
            if hasattr(comp, 'set_zoom_rate'):
                comp.set_zoom_rate(rate)
            elif hasattr(comp, '_zoom_rate'):
                comp._zoom_rate = rate

    def _tick_strict_media_cycle(self) -> None:
        if not self._accelerate_enabled:
            return

        interval = self._accelerate_media_interval_s
        if interval is None:
            interval = self._frames_per_cycle / 60.0
            self.logger.info(f"[CustomVisual][DEBUG] _tick: interval was None, using default {interval:.3f}s (_frames_per_cycle={self._frames_per_cycle})")
        # Remove ACCEL_MIN_DURATION clamp to allow true high speeds

        now = time.perf_counter()
        if self._accelerate_next_media_time is None:
            self._accelerate_next_media_time = now + interval
            self.logger.info(f"[CustomVisual][DEBUG] _tick: First media advance scheduled at {self._accelerate_next_media_time:.6f} (now={now:.6f}, interval={interval:.3f}s)")
            return

        time_until = self._accelerate_next_media_time - now
        if now < self._accelerate_next_media_time:
            return

        self.logger.info(f"[CustomVisual][DEBUG] _tick: Media advancing NOW (was due {-time_until:.3f}s ago, interval={interval:.3f}s)")
        self._advance_media_cycle()
        self._accelerate_next_media_time = now + interval
        self.logger.info(f"[CustomVisual][DEBUG] _tick: Next media scheduled at {self._accelerate_next_media_time:.6f} (now={now:.6f}, interval={interval:.3f}s)")

    def _advance_media_cycle(self) -> None:
        if not self._use_theme_bank_media and not self._media_paths:
            return

        if not self._use_theme_bank_media and self._media_paths:
            self._current_media_index = (self._current_media_index + 1) % len(self._media_paths)

        self._load_current_media()

    def _schedule_next_accelerate_media_tick(self) -> None:
        if not self._accelerate_enabled:
            return

        interval = self._accelerate_media_interval_s
        if interval is None:
            interval = self._frames_per_cycle / 60.0
        # Remove ACCEL_MIN_DURATION clamp to allow true high speeds
        self._accelerate_next_media_time = time.perf_counter() + interval

    def get_expected_media_cycle_frames(self) -> int:
        """Expose the current media interval as frames for zoom alignment."""
        base_frames = max(1, int(getattr(self, '_frames_per_cycle', 300)))
        source = "base"
        frames_result = base_frames
        if self._accelerate_enabled:
            interval_s = self._accelerate_media_interval_s
            if interval_s is not None:
                frames_result = max(1, int(round(interval_s * 60.0)))
                source = "interval"
            else:
                # Fall back to current accelerate speed hints when interval is not set yet
                speed_hint = self._accelerate_media_speed_smoothed or self._accelerate_media_speed_current
                if speed_hint is not None:
                    frames_hint, _ = self._cycle_speed_to_frames(int(round(speed_hint)))
                    frames_result = max(1, frames_hint)
                    source = "speed_hint"
                else:
                    frames_result = base_frames
                    source = "fallback"
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "[CustomVisual][accelerate] expected frames (%s): %d",
                source,
                frames_result,
            )
        return frames_result
        # Default to the configured frames-per-cycle for non-accelerate modes
    
    # ===== Cycler Interface (Required by Visual base class) =====
    
    def build_cycler(self):
        """
        Build cycler for frame-based media cycling.

        CustomVisual uses a simple ActionCycler that advances media every N frames.
        Unlike complex Visual Programs with nested cyclers, CustomVisual is linear.
        """
        frame_tick_cycler = ActionCycler(period=1, action=self._runtime_frame_tick)

        # In strict mode the launcher drives media changes; keep per-frame ticks for accelerate.
        if getattr(self, "_strict_mode", False):
            return frame_tick_cycler

        def cycle_media():
            """Advance to next media item."""
            if self._use_theme_bank_media:
                # ThemeBank mode - just load next image (ThemeBank handles selection)
                self._load_current_media()
            elif self._media_paths:
                # Explicit path list mode - cycle through indices
                self._current_media_index = (self._current_media_index + 1) % len(self._media_paths)
                self._load_current_media()

        # Create ActionCycler that runs every _frames_per_cycle frames
        # CRITICAL: offset=period to prevent immediate execution on frame 0
        # User expects mode to load without auto-starting media (preview state)
        # Media will load when Launch button is pressed
        media_cycler = ActionCycler(
            period=self._frames_per_cycle,  # Fixed: parameter name is 'period', not 'frames'
            action=cycle_media,
            offset=self._frames_per_cycle  # Wait one full cycle before first media change
        )
        return ParallelCycler([frame_tick_cycler, media_cycler])


    def _load_current_media(self) -> None:
        """Load the current media item (image or video)."""
        self.logger.info(f"[CustomVisual] _load_current_media() called - _use_theme_bank_media={self._use_theme_bank_media}, _media_mode={self._media_mode}")
        
        # DON'T restart zoom here - visual director will restart zoom only when image actually changes
        # (this prevents zoom restarting every cycle even when image is still loading)
        
        if self._use_theme_bank_media:
            self._load_theme_bank_media()
            # DON'T call on_media_change() here - visual director will call it when image/video actually uploads
            return
        
        # Explicit path list mode (for custom handpicked media)
        if not self._media_paths:
            return
        
        media_path = self._media_paths[self._current_media_index]
        
        # Determine if image or video based on extension
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        is_video = media_path.suffix.lower() in video_exts
        
        if is_video and self.on_change_video:
            self.on_change_video(self._current_media_index)
            self.logger.debug(f"[CustomVisual] Loaded video: {media_path.name}")
            
            # NOTE: Cycle marker increment moved to visual_director._on_change_video()
            # Ensures cycle advances only after successful video load
            
        elif not is_video and self.on_change_image:
            self.on_change_image(self._current_media_index)
            self.logger.debug(f"[CustomVisual] Loaded image: {media_path.name}")
            
            # NOTE: Cycle marker increment moved to visual_director._on_change_image()
            # Ensures cycle advances only after successful image upload
        
        # Trigger text change only when syncing with media
        if self.text_director:
            if (not hasattr(self.text_director, "is_sync_with_media")) or self.text_director.is_sync_with_media():
                self.text_director.on_media_change()
    
    # ===== Visual Interface Methods =====
    
    def reset(self) -> None:
        """Reset visual to initial state."""
        self._frame_counter = 0
        self._current_media_index = 0
        
        # Reset cycle marker (Phase 2)
        self._cycle_marker = 0

        # Reset ThemeBank alternating preference
        self._theme_bank_media_cycle = "image"

        # Reset accelerate runtime state
        self._reset_accelerate_runtime_state()
        
        # DON'T auto-load media - wait for start() call
        # User expects mode to load in "preview" state without starting playback
        # Media will load when start() is called (Launch button pressed or session starts)
        
        # Reset cycler
        if self._cycler:
            if hasattr(self._cycler, 'reset'):
                self._cycler.reset()
        
        self.logger.info(f"[CustomVisual] '{self.playback_name}' reset to initial state (media NOT loaded - awaiting start())")
    
    def start(self) -> None:
        """Start visual playback - loads first media item and begins cycling."""
        self.logger.info(f"[CustomVisual] start() called - media_items={len(getattr(self, '_media_paths', [])) if hasattr(self, '_media_paths') else 'NO _media_paths'}, _use_theme_bank_media={self._use_theme_bank_media}")
        self.logger.info(f"[CustomVisual][ACCEL] Acceleration enabled: {self._accelerate_enabled}, duration: {self._accelerate_duration}s")
        if self._accelerate_enabled:
            self.logger.info(f"[CustomVisual][ACCEL] Start values: rotation_x={self._accelerate_rotation_start_x}, media_speed={self._accelerate_media_start_speed}, zoom_rate={self._accelerate_zoom_start_rate}")

        self._reset_accelerate_runtime_state()
        self.logger.info(f"[CustomVisual][DEBUG] After reset: _accelerate_media_interval_s={self._accelerate_media_interval_s}")
        
        if self._accelerate_enabled:
            self._update_accelerate_effects(force=True)
            self.logger.info(f"[CustomVisual][DEBUG] After _update_accelerate_effects: _accelerate_media_interval_s={self._accelerate_media_interval_s}")
            
            # CRITICAL: Ensure interval is calculated immediately for first cycle
            # This prevents fallback to 3-second default interval
            if self._accelerate_media_interval_s is None:
                start_speed = self._accelerate_media_start_speed or 50.0
                frames, _ = self._cycle_speed_to_frames(int(round(start_speed)))
                self._accelerate_media_interval_s = frames / 60.0  # Remove ACCEL_MIN_DURATION clamp
                self.logger.info(f"[CustomVisual][DEBUG] FALLBACK: Calculated initial interval: {self._accelerate_media_interval_s:.3f}s for speed {start_speed}")
            else:
                self.logger.info(f"[CustomVisual][DEBUG] Interval already set: {self._accelerate_media_interval_s:.3f}s")
            
            self.logger.info(f"[CustomVisual] Acceleration enabled - starting immediately")
        
        # Check if we have explicit media paths
        if hasattr(self, '_media_paths') and self._media_paths:
            self._load_current_media()
            self.logger.info(f"[CustomVisual] '{self.playback_name}' started - media loaded and playing")
        elif self._use_theme_bank_media:
            # No media_paths list when using ThemeBank, but still need to load
            self._load_current_media()
            self.logger.info(f"[CustomVisual] '{self.playback_name}' started - ThemeBank media loading")
        else:
            self.logger.warning(f"[CustomVisual] '{self.playback_name}' has no media to start")

        if self._accelerate_enabled:
            # CRITICAL: Schedule next media cycle NOW so it happens immediately on next frame tick
            # Don't add interval - that causes 3s stall. Frame tick will detect time has passed and load media.
            now = time.perf_counter()
            self._accelerate_next_media_time = now
            self.logger.info(f"[CustomVisual][DEBUG] Next media scheduled at {self._accelerate_next_media_time:.6f} (now={now:.6f}, diff=0.0s)")
            self.logger.info(f"[CustomVisual] Next media cycle scheduled for immediate execution")

    # ===== Strict mode toggles =====

    def set_strict_mode(self, enabled: bool) -> None:
        """Enable/disable strict mode (Launcher-driven exact timing).

        When enabled, this visual's cycler becomes a no-op and the Launcher
        is expected to call _load_current_media() at the precise interval
        derived from the mode configuration.
        """
        self._strict_mode = bool(enabled)
        # Rebuild/clear cycler so subsequent get_cycler() returns correct behavior
        self._cycler = None

    def is_strict_mode(self) -> bool:
        return bool(self._strict_mode)
    
    def advance(self) -> bool:
        """
        Advance visual by one frame.

        Returns:
            True if visual should continue, False if complete
        """
        # Advance cycler (handles runtime ticks + media cycling)
        cycler = self.get_cycler()
        if cycler:
            cycler.advance()

        # CustomVisual never completes - loops indefinitely
        return True


    def get_name(self) -> str:
        """Get display name of this visual mode."""
        return self.playback_name
    
    def get_description(self) -> str:
        """Get description of this visual mode."""
        return self.config.get("description", f"Custom playback: {self.playback_name}")
    
    def get_current_cycle(self) -> int:
        """Get current cycle marker (Phase 2 - session synchronization).
        
        The cycle marker increments each time media changes (new image or video).
        Used by VisualDirector to detect cycle boundaries for synchronized transitions.
        
        Returns:
            Number of media cycles completed since reset
        """
        return self._cycle_marker
    
    # ===== Utility Methods =====
    
    @staticmethod
    def validate_mode_file(mode_path: Path) -> tuple[bool, str]:
        """
        Validate mode file structure without loading.
        
        Args:
            mode_path: Path to mode JSON file
        
        Returns:
            (is_valid, error_message) - error_message is empty string if valid
        """
        try:
            if not mode_path.exists():
                return False, f"File not found: {mode_path}"
            
            with open(mode_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Check required top-level keys
            required_keys = ["version", "name", "spiral", "media", "text", "zoom"]
            missing = [k for k in required_keys if k not in config]
            if missing:
                return False, f"Missing required keys: {missing}"
            
            # Validate version
            if config["version"] != "1.0":
                return False, f"Unsupported version: {config['version']}"
            
            # Basic type checks
            if not isinstance(config["name"], str):
                return False, "Field 'name' must be string"
            
            if not isinstance(config["spiral"], dict):
                return False, "Field 'spiral' must be object"
            
            if not isinstance(config["media"], dict):
                return False, "Field 'media' must be object"
            
            if not isinstance(config["text"], dict):
                return False, "Field 'text' must be object"
            
            if not isinstance(config["zoom"], dict):
                return False, "Field 'zoom' must be object"
            
            return True, ""
            
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"
