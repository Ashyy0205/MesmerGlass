"""
CustomVisual - User-defined visual modes loaded from JSON files.

This class replaces hardcoded Visual Programs with user-configurable modes
created in the Visual Mode Creator tool. Custom modes define:
- Spiral behavior (type, speed, opacity, reverse) - colors excluded (global setting)
- Media cycling (images/videos, speed, opacity)
- Text overlays (mode, opacity, library)
- Zoom animations (mode, rate, duration)

Custom modes are the future-proof replacement for built-in Visual classes.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..content.themebank import ThemeBank
    from ..mesmerloom.compositor import LoomCompositor
    from ..content.text_renderer import SplitMode
    from ..engine.text_director import TextDirector

from mesmerglass.mesmerloom.visuals import Visual
from mesmerglass.mesmerloom.cyclers import ActionCycler


class CustomVisual(Visual):
    """
    User-defined visual mode loaded from JSON configuration.
    
    CustomVisual reads a mode file and applies settings to compositor, spiral,
    text system, and media. Unlike hardcoded Visual Programs, CustomVisual is
    fully data-driven and supports all settings from Visual Mode Creator.
    
    Mode File Structure:
        {
            "version": "1.0",
            "name": "Mode Name",
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
    
    Note: Spiral colors (arm_color, gap_color) are NOT in mode files - they
    remain global settings controlled in launcher UI.
    
    See docs/technical/custom-mode-settings-reference.md for complete details.
    """
    
    def __init__(
        self,
        mode_path: Path,
        theme_bank: Optional[ThemeBank] = None,
        on_change_image: Optional[Callable[[int], None]] = None,
        on_change_video: Optional[Callable[[int], None]] = None,
        on_rotate_spiral: Optional[Callable[[float], None]] = None,
        compositor: Optional[LoomCompositor] = None,
        text_director: Optional[TextDirector] = None
    ):
        """
        Initialize CustomVisual from mode file.
        
        Args:
            mode_path: Path to JSON mode file
            theme_bank: ThemeBank for media/text lookup (if use_theme_bank=true)
            on_change_image: Callback for image switching
            on_change_video: Callback for video switching
            on_rotate_spiral: Callback for spiral rotation
            compositor: LoomCompositor for applying settings
            text_director: TextDirector for text system configuration
        """
        super().__init__()
        
        self.logger = logging.getLogger(__name__)
        self.mode_path = Path(mode_path)
        self.theme_bank = theme_bank
        self.compositor = compositor
        self.text_director = text_director
        
        # Callbacks
        self.on_change_image = on_change_image
        self.on_change_video = on_change_video
        self.on_rotate_spiral = on_rotate_spiral
        
        # Mode configuration (loaded from JSON)
        self.config: Dict[str, Any] = {}
        self.mode_name: str = "Unknown Mode"
        
        # Media state
        self._current_media_index = 0
        self._media_paths: List[Path] = []
        self._media_mode: str = "images"  # "images", "videos", "both", "none"
        self._use_theme_bank_media = False  # Flag to use ThemeBank.get_image() instead of paths
        
        # Frame counting for cycling
        self._frame_counter = 0
        self._frames_per_cycle = 180  # Default 3 seconds at 60fps

        # Strict mode (Launcher-enforced exact mode behavior)
        # When enabled, this visual will not schedule media changes via its
        # internal cycler. The Launcher will drive media changes using a
        # precise QTimer at the exact interval derived from the mode.
        self._strict_mode = False
        
        # Load and validate mode file
        self._load_mode_file()
        
        # Apply initial settings
        self._apply_initial_settings()
    
    # ===== Mode File Loading =====
    
    def _load_mode_file(self) -> None:
        """Load and validate JSON mode file."""
        try:
            if not self.mode_path.exists():
                raise FileNotFoundError(f"Mode file not found: {self.mode_path}")
            
            with open(self.mode_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            # Validate version
            version = self.config.get("version", "1.0")
            if version != "1.0":
                self.logger.warning(f"[CustomVisual] Unknown mode version: {version}")
            
            # Extract mode name
            self.mode_name = self.config.get("name", self.mode_path.stem)
            
            self.logger.info(f"[CustomVisual] Loaded mode: {self.mode_name} from {self.mode_path.name}")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"[CustomVisual] Invalid JSON in mode file: {e}")
            raise ValueError(f"Invalid mode file JSON: {e}")
        except Exception as e:
            self.logger.error(f"[CustomVisual] Failed to load mode file: {e}")
            raise
    
    def _apply_initial_settings(self) -> None:
        """Apply mode settings to compositor, spiral, and text systems."""
        # Apply spiral settings (excluding colors - those are global)
        self._apply_spiral_settings()
        
        # Apply media settings and build media list
        self._apply_media_settings()
        
        # Apply text settings
        self._apply_text_settings()
        
        # Apply zoom settings
        self._apply_zoom_settings()
        
        self.logger.info(f"[CustomVisual] '{self.mode_name}' initialized with {len(self._media_paths)} media items")
    
    def reapply_all_settings(self) -> None:
        """Re-apply all custom mode settings (called after compositor is ready)."""
        self.logger.info("[CustomVisual] Re-applying all settings...")
        self._apply_spiral_settings()
        self._apply_media_settings()
        self._apply_text_settings()
        self._apply_zoom_settings()
        self.logger.info("[CustomVisual] All settings re-applied")
    
    def reload_from_disk(self) -> bool:
        """
        Reload JSON file from disk and re-apply all settings.
        
        Useful for live editing mode files without restarting launcher.
        
        Returns:
            True if reload succeeded, False on error
        """
        try:
            self.logger.info(f"[CustomVisual] Reloading mode from disk: {self.mode_path.name}")
            
            # Re-load JSON file
            self._load_mode_file()
            
            # Re-apply all settings with new config
            self._apply_spiral_settings()
            self._apply_media_settings()
            self._apply_text_settings()
            self._apply_zoom_settings()
            
            self.logger.info(f"[CustomVisual] Successfully reloaded '{self.mode_name}' from disk")
            return True
            
        except Exception as e:
            self.logger.error(f"[CustomVisual] Failed to reload mode: {e}")
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
        
        # NOTE: arm_color and gap_color are NOT applied - they remain global settings
    
    def _apply_media_settings(self) -> None:
        """Apply media configuration and build media path list."""
        media_config = self.config.get("media", {})
        
        # Media mode: "images", "videos", "both", "none"
        self._media_mode = media_config.get("mode", "images")
        
        # Media cycling speed (1-100) → frames per cycle
        # Use exponential curve matching visual_mode_creator
        cycle_speed = media_config.get("cycle_speed", 50)
        cycle_speed = max(1, min(100, cycle_speed))  # Clamp to range
        
        # Formula: interval_ms = 10000 * pow(0.005, (speed-1)/99)
        # Convert to frames: frames = (interval_ms / 1000) * 60fps (launcher now runs at 60fps to match VMC)
        interval_ms = 10000 * pow(0.005, (cycle_speed - 1) / 99.0)
        self._frames_per_cycle = max(1, round((interval_ms / 1000.0) * 60.0))  # 60 FPS to match VMC
        actual_interval_ms = (self._frames_per_cycle / 60.0) * 1000.0  # Calculate actual timing at 60 FPS
        self.logger.info(f"[CustomVisual] Applied media cycle speed: {cycle_speed} → {self._frames_per_cycle} frames ({actual_interval_ms:.0f}ms at 60fps, target: {interval_ms:.0f}ms)")
        
        # Fade duration (in seconds)
        fade_duration = media_config.get("fade_duration", 0.5)
        fade_duration = max(0.0, min(5.0, fade_duration))  # Clamp 0-5 seconds
        if self.compositor and hasattr(self.compositor, 'set_fade_duration'):
            self.compositor.set_fade_duration(fade_duration)
            self.logger.info(f"[CustomVisual] Applied media fade duration: {fade_duration:.2f}s")
        
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
            
            self.text_director.set_text_library(text_lines, default_split_mode=split_mode, user_set=False)
            self.logger.info(f"[CustomVisual] Called set_text_library with {len(text_lines)} lines, split_mode={split_mode}")
        else:
            # Use explicit text library from config
            text_lines = text_config.get("library", [])
            self.text_director.set_text_library(text_lines, default_split_mode=split_mode, user_set=False)
            self.logger.info(f"[CustomVisual] Using explicit texts: {len(text_lines)} lines")
        
        self.logger.info(f"[CustomVisual] Text application complete: mode={text_mode}, enabled={enabled}, opacity={opacity}")
    
    def _restart_zoom_animation(self) -> None:
        """Restart zoom animation from 1.0 (called on each media change)."""
        zoom_config = self.config.get("zoom", {})
        zoom_mode = zoom_config.get("mode", "none")
        
        if zoom_mode == "none" or not self.compositor:
            return
        
        # Restart zoom animation from start_zoom=1.0
        zoom_rate = zoom_config.get("rate", 0.5)
        
        if hasattr(self.compositor, 'start_zoom_animation'):
            self.compositor.start_zoom_animation(
                start_zoom=1.0,
                target_zoom=1.5,
                mode=zoom_mode,
                rate=zoom_rate
            )
            self.logger.debug(f"[CustomVisual] Restarted zoom animation: mode={zoom_mode}, rate={zoom_rate}")
    
    def _apply_zoom_settings(self) -> None:
        """Apply zoom animation settings."""
        zoom_config = self.config.get("zoom", {})
        
        if not self.compositor:
            return
        
        # Zoom mode: "none", "exponential", "falling", "linear", "pulse", "in", "out"
        zoom_mode = zoom_config.get("mode", "none")
        zoom_rate = zoom_config.get("rate", 0.5)
        
        if zoom_mode == "none":
            # Disable zoom
            if hasattr(self.compositor, 'set_zoom_rate'):
                self.compositor.set_zoom_rate(0.0)
                self.logger.info("[CustomVisual] Zoom disabled (mode=none)")
            if hasattr(self.compositor, 'set_zoom_animation_enabled'):
                self.compositor.set_zoom_animation_enabled(False)
                self.logger.info("[CustomVisual] Zoom animations disabled")
        else:
            # Enable zoom animation with compositor's start_zoom_animation
            if hasattr(self.compositor, 'set_zoom_animation_enabled'):
                self.compositor.set_zoom_animation_enabled(True)
            
            # Start zoom animation with mode and rate
            # Supported modes: "exponential" (zoom in), "falling" (zoom out), "linear", "pulse"
            if hasattr(self.compositor, 'start_zoom_animation'):
                self.compositor.start_zoom_animation(
                    start_zoom=1.0,
                    target_zoom=1.5,  # End zoom level
                    mode=zoom_mode,
                    rate=zoom_rate
                )
                self.logger.info(f"[CustomVisual] Applied zoom animation: mode={zoom_mode}, rate={zoom_rate}")
            elif hasattr(self.compositor, 'set_zoom_rate'):
                # Fallback: use simple zoom rate if start_zoom_animation not available
                rate = zoom_rate if zoom_mode in ["exponential", "in"] else -zoom_rate
                self.compositor.set_zoom_rate(rate)
                self.logger.info(f"[CustomVisual] Applied zoom rate: mode={zoom_mode}, rate={rate}")
    
    # ===== Cycler Interface (Required by Visual base class) =====
    
    def build_cycler(self):
        """
        Build cycler for frame-based media cycling.
        
        CustomVisual uses a simple ActionCycler that advances media every N frames.
        Unlike complex Visual Programs with nested cyclers, CustomVisual is linear.
        """
        # If strict mode is enabled, return a no-op cycler so that the
        # Launcher can drive media changes using a precise timer. This avoids
        # double-advancement and keeps timing exact to the mode.
        if getattr(self, "_strict_mode", False):
            return ActionCycler(period=999_999_999, action=lambda: None, repeat_count=1)
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
        return ActionCycler(
            period=self._frames_per_cycle,  # Fixed: parameter name is 'period', not 'frames'
            action=cycle_media,
            offset=self._frames_per_cycle  # Wait one full cycle before first media change
        )
    
    def _load_current_media(self) -> None:
        """Load the current media item (image or video)."""
        # DON'T restart zoom here - visual director will restart zoom only when image actually changes
        # (this prevents zoom restarting every cycle even when image is still loading)
        
        if self._use_theme_bank_media:
            # Use ThemeBank.get_image() directly (no path list)
            if self._media_mode in ("images", "both"):
                # ThemeBank provides images via get_image() method
                # on_change_image callback will call theme_bank.get_image() internally
                if self.on_change_image:
                    self.on_change_image(0)  # Index ignored when using ThemeBank
                    self.logger.debug("[CustomVisual] Loaded image from ThemeBank")
            
            # TODO: ThemeBank doesn't currently support videos - only images
            # If videos are needed, would need to add get_video() method to ThemeBank
            
            # DON'T call on_media_change() here - visual director will call it when image actually uploads
            # (this prevents text changing before image is ready)
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
        elif not is_video and self.on_change_image:
            self.on_change_image(self._current_media_index)
            self.logger.debug(f"[CustomVisual] Loaded image: {media_path.name}")
        
        # Trigger text change if in CENTERED_SYNC mode
        if self.text_director:
            self.text_director.on_media_change()
    
    # ===== Visual Interface Methods =====
    
    def reset(self) -> None:
        """Reset visual to initial state."""
        self._frame_counter = 0
        self._current_media_index = 0
        
        # DON'T auto-load media - wait for Launch button
        # User expects mode to load in "preview" state without starting playback
        # Media will load when start() is called (Launch button pressed)
        
        # Reset cycler
        if self._cycler:
            if hasattr(self._cycler, 'reset'):
                self._cycler.reset()
        
        self.logger.info(f"[CustomVisual] '{self.mode_name}' reset to initial state (media NOT loaded - awaiting start())")

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
        self._frame_counter += 1
        
        # Advance cycler (handles media cycling)
        cycler = self.get_cycler()
        if cycler:
            cycler.advance()
        
        # CustomVisual never completes - loops indefinitely
        return True
    
    def get_name(self) -> str:
        """Get display name of this visual mode."""
        return self.mode_name
    
    def get_description(self) -> str:
        """Get description of this visual mode."""
        return self.config.get("description", f"Custom mode: {self.mode_name}")
    
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
