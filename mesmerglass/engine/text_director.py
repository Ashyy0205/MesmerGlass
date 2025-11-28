"""
Text Director - Independent text library management.

Manages text selection with weights - Visual Programs handle display/animation.
This provides:
- Text library with enable/disable
- Weighted random selection
- Text callbacks to Visual Programs
"""

from __future__ import annotations

import logging
import random
import math
import time
from collections import OrderedDict
from typing import Optional, Callable, List, Any, Tuple
from dataclasses import dataclass

try:
    from ..content.text_renderer import SplitMode
except ImportError:
    SplitMode = None  # type: ignore


@dataclass
class TextEntry:
    """Single text entry with weight and split mode."""
    text: str
    weight: float = 1.0
    enabled: bool = True
    split_mode: Optional['SplitMode'] = None


class TextDirector:
    """
    Manages text library with weighted selection AND independent text rendering.
    
    Completely independent from Visual Programs - handles both text selection
    and rendering with split modes.
    
    Features:
    - Text enable/disable
    - Weighted random selection
    - Per-text split modes (FILL_SCREEN, SPLIT_WORD, etc.)
    - Independent text cycling and rendering
    - Frame-based timing control
    """
    
    def __init__(
        self,
        text_renderer=None,
        compositor=None,
        on_text_change: Optional[Callable[[str, Optional['SplitMode']], None]] = None,
        time_provider: Optional[Callable[[], float]] = None,
    ):
        """Initialize text director.
        
        Args:
            text_renderer: TextRenderer instance for rendering
            compositor: Compositor instance for display
            on_text_change: Callback(text, split_mode) when text changes
        """
        self.text_renderer = text_renderer
        self.compositor = compositor
        self._on_text_change = on_text_change
        
        # Multi-display support: Track secondary compositors for text broadcasting
        self._secondary_compositors: List[Any] = []
        
        # Text library
        self._text_entries: List[TextEntry] = []
        self._current_text = ""
        self._current_split_mode = SplitMode.CENTERED_SYNC if SplitMode else None
        self._user_text_library = False  # True if text library was set by user (Text tab)
        
        # Timing and rendering control
        self._enabled = False  # Whether to render text
        self._frame_counter = 0
        self._frames_per_text = 120  # 2 seconds at 60fps (how long to show each text)
        self._manual_frames_per_text = self._frames_per_text
        self._sync_with_media = True
        self._default_target_seconds = self._frames_per_text / 60.0
        self._manual_target_seconds = self._manual_frames_per_text / 60.0
        
        # Scrolling animation state (for SUBTEXT mode)
        self._scroll_offset = 0.0
        self._scroll_speed = 30.0  # Pixels per second (doubled from 15.0)
        self._subtext_render_min_interval = 1.0 / 30.0  # ~33ms guard between heavy renders
        self._subtext_render_min_delta_px = 8.0  # ignore micro scroll adjustments
        self._last_subtext_render_time: Optional[float] = None
        self._last_subtext_render_offset: float = 0.0

        # Cache rendered textures (keyed by text, mode, size, font, and color)
        self._text_render_cache_capacity = 24
        self._text_render_cache: 'OrderedDict[Tuple[str, Optional[SplitMode], bool, bool, str, Tuple[int, int, int, int]], Any]' = OrderedDict()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("[TextDirector] Initialized (independent text system)")

        # Global opacity multiplier (matches compositor default)
        self._text_opacity = 1.0
        self._text_color = (1.0, 1.0, 1.0, 1.0)
        if self.compositor:
            self._apply_opacity_to_compositor(self.compositor)
        self._apply_text_color_to_renderer()

        # Font override tracking (Text tab vs ThemeBank)
        self._font_override_user = False
        self._active_font_path: Optional[str] = None

        # Timing helpers use a monotonic clock so slider timing is framerate independent
        self._time_provider: Callable[[], float] = time_provider or time.monotonic
        self._last_update_time: Optional[float] = None
        self._elapsed_time_s: float = 0.0
        self._recompute_target_seconds()
        self._render_log_interval = 5.0
        self._last_render_log_ts = 0.0
        self._last_render_log_mode: Optional['SplitMode'] = None
    
    # ===== Multi-Display Support =====
    
    def set_secondary_compositors(self, compositors: List[Any]) -> None:
        """Set secondary compositors and immediately mirror current text state."""
        self._secondary_compositors = [comp for comp in (compositors or []) if comp]

        for comp in self._secondary_compositors:
            try:
                if hasattr(comp, "text_director"):
                    comp.text_director = self
                if hasattr(comp, "clear_text_textures"):
                    comp.clear_text_textures()
                # Ensure opacity matches when mirroring text to new outputs
                self._apply_opacity_to_compositor(comp)
            except Exception as exc:
                self.logger.warning(f"[TextDirector] Failed to prime secondary compositor: {exc}")

        self.logger.debug(f"[TextDirector] Set {len(self._secondary_compositors)} secondary compositors")

        # Re-render current text so secondaries immediately mirror the primary output
        if self._enabled and self._current_text:
            self._render_current_text()
    
    def _get_all_compositors(self) -> List[Any]:
        """Get list of all compositors (primary + secondaries)."""
        compositors = []
        if self.compositor:
            compositors.append(self.compositor)
        compositors.extend(self._secondary_compositors)
        return compositors

    def _invalidate_text_cache(self) -> None:
        """Drop cached rendered text so future draws regenerate with new style/state."""
        if self._text_render_cache:
            self._text_render_cache.clear()

    def _build_render_cache_key(
        self,
        text: str,
        mode: Optional['SplitMode'],
        *,
        large: bool,
        shadow: bool,
    ) -> Tuple[str, Optional['SplitMode'], bool, bool, str, Tuple[int, int, int, int]]:
        """Return a cache key that encapsulates text, sizing, font, and color state."""
        font_key = self._active_font_path or "__default__"
        color_key = tuple(int(round(max(0.0, min(1.0, comp)) * 255)) for comp in self._text_color)
        return (text, mode, large, shadow, font_key, color_key)

    def _get_cached_rendered_text(
        self,
        text: str,
        mode: Optional['SplitMode'],
        *,
        large: bool,
        shadow: bool
    ):
        """Render text or reuse a cached texture when possible."""
        if not self.text_renderer:
            return None

        key = self._build_render_cache_key(text, mode, large=large, shadow=shadow)
        cached = self._text_render_cache.get(key)
        if cached is not None:
            self._text_render_cache.move_to_end(key)
            return cached

        rendered = self.text_renderer.render_main_text(text, large=large, shadow=shadow)
        if rendered and hasattr(rendered, 'texture_data'):
            self._text_render_cache[key] = rendered
            if len(self._text_render_cache) > self._text_render_cache_capacity:
                self._text_render_cache.popitem(last=False)
        return rendered

    def _apply_opacity_to_compositor(self, compositor: Any) -> None:
        """Apply stored opacity to a compositor when capability exists."""
        if compositor and hasattr(compositor, "set_text_opacity"):
            try:
                compositor.set_text_opacity(self._text_opacity)
            except Exception as exc:
                self.logger.debug(f"[TextDirector] Failed to apply text opacity to compositor: {exc}")

    def _get_layout_dimensions(self, comp: Optional[Any] = None) -> tuple[int, int]:
        """Determine the logical resolution to use for text layout math."""

        def _measure(candidate: Any) -> tuple[int, int]:
            width = height = 0
            if not candidate:
                return (0, 0)
            if hasattr(candidate, "get_target_screen_size"):
                try:
                    width, height = candidate.get_target_screen_size()
                except Exception:
                    width = height = 0
            if (width <= 0 or height <= 0) and hasattr(candidate, "width") and hasattr(candidate, "height"):
                try:
                    width = int(candidate.width())
                    height = int(candidate.height())
                except Exception:
                    width = height = 0
            return (width, height)

        # When an explicit compositor is provided, only read from that source
        if comp is not None:
            width, height = _measure(comp)
            if width <= 0 or height <= 0:
                width, height = 1920, 1080
            return (int(width), int(height))

        # Aggregate across all compositors so multi-display layouts stay in sync
        aggregate_width = 0
        aggregate_height = 0
        for candidate in self._get_all_compositors():
            width, height = _measure(candidate)
            aggregate_width = max(aggregate_width, width)
            aggregate_height = max(aggregate_height, height)

        if aggregate_width <= 0 or aggregate_height <= 0:
            aggregate_width, aggregate_height = 1920, 1080

        # Always enforce a minimum canvas so small preview windows still emulate live spacing
        min_width, min_height = 1920, 1080
        aggregate_width = max(aggregate_width, min_width)
        aggregate_height = max(aggregate_height, min_height)

        return (int(aggregate_width), int(aggregate_height))

    def _recompute_target_seconds(self) -> None:
        """Cache frame-based timings as seconds for stable comparisons."""
        self._default_target_seconds = max(1, self._frames_per_text) / 60.0
        self._manual_target_seconds = max(1, self._manual_frames_per_text) / 60.0

    def _reset_elapsed_time(self) -> None:
        """Reset accumulated time so next update measures from scratch."""
        self._elapsed_time_s = 0.0
        self._last_update_time = None

    def _should_log_render(self, mode: Optional['SplitMode']) -> bool:
        """Return True if we should emit an INFO render log (mode change or interval)."""

        now = self._time_provider()
        mode_changed = mode != self._last_render_log_mode
        if mode_changed:
            self._last_render_log_mode = mode
            self._last_render_log_ts = now
            return True
        if now - self._last_render_log_ts >= self._render_log_interval:
            self._last_render_log_ts = now
            return True
        return False
    
    # ===== Configuration =====
    
    def reset(self) -> None:
        """Reset text director state (clear scroll offset and frame counter).
        
        Should be called when starting a new playback/cue to prevent state carryover.
        """
        old_offset = self._scroll_offset
        old_mode = self._current_split_mode
        
        self._scroll_offset = 0.0
        self._frame_counter = 0
        self._reset_elapsed_time()
        self._last_subtext_render_time = None
        self._last_subtext_render_offset = 0.0
        self._invalidate_text_cache()
        
        self.logger.info(f"[TextDirector] RESET: offset {old_offset:.2f}→0.0, mode={old_mode} (preserved)")
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable text rendering.
        
        Args:
            enabled: True to render text, False to clear
        """
        self._enabled = enabled
        if not enabled and self.compositor:
            try:
                self.compositor.clear_text_textures()
            except Exception:
                pass
        self.logger.info(f"[TextDirector] Text rendering: {'enabled' if enabled else 'disabled'}")
        if enabled:
            self._reset_elapsed_time()

    def set_opacity(self, opacity: float) -> None:
        """Set global text opacity (0.0-1.0) for all compositors."""
        clamped = max(0.0, min(1.0, float(opacity)))
        if math.isclose(clamped, self._text_opacity, rel_tol=1e-4, abs_tol=1e-4):
            return
        self._text_opacity = clamped
        for comp in self._get_all_compositors():
            self._apply_opacity_to_compositor(comp)
        self.logger.info(f"[TextDirector] Text opacity set to {self._text_opacity:.2f}")

    def get_opacity(self) -> float:
        """Return current text opacity multiplier."""
        return self._text_opacity

    def set_text_color(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        """Set the RGBA color applied to rendered text."""
        components = []
        for value in (r, g, b, a):
            try:
                components.append(max(0.0, min(1.0, float(value))))
            except Exception:
                components.append(1.0)
        new_color = tuple(components)
        if all(math.isclose(new_color[i], self._text_color[i], rel_tol=1e-4, abs_tol=1e-4) for i in range(4)):
            return
        self._text_color = new_color
        self._apply_text_color_to_renderer()
        if self._enabled and self._current_text:
            self._render_current_text()
        self.logger.info(
            "[TextDirector] Text color set to RGB=(%.2f, %.2f, %.2f)"
            % (self._text_color[0], self._text_color[1], self._text_color[2])
        )

    def _apply_text_color_to_renderer(self) -> None:
        """Push stored color into the text renderer style."""
        if not self.text_renderer:
            return
        try:
            style = self.text_renderer.get_style()
            rgba = tuple(int(round(max(0.0, min(1.0, comp)) * 255)) for comp in self._text_color)
            style.color = rgba
            self.text_renderer.set_style(style)
        except Exception as exc:
            self.logger.debug(f"[TextDirector] Failed to apply text color: {exc}")
    
    def set_timing(self, frames_per_text: int) -> None:
        """Set how long to show each text.
        
        Args:
            frames_per_text: Frames to display each text (60 = 1 second)
        """
        self._frames_per_text = max(1, frames_per_text)
        if not self._sync_with_media:
            self._manual_frames_per_text = self._frames_per_text
        self._recompute_target_seconds()
    
    def is_enabled(self) -> bool:
        """Check if text rendering is enabled.
        
        Returns:
            True if text will be rendered
        """
        return self._enabled

    def configure_sync(self, sync_with_media: bool, frames_per_text: Optional[int] = None) -> None:
        """Configure whether text follows media changes or independent timing.

        Args:
            sync_with_media: True to trigger on media events, False for manual cadence.
            frames_per_text: Optional manual duration in frames (60fps basis).
        """
        self._sync_with_media = bool(sync_with_media)
        if frames_per_text is not None:
            self._manual_frames_per_text = max(1, int(frames_per_text))
        else:
            self._manual_frames_per_text = self._frames_per_text
        self._recompute_target_seconds()
        self._reset_elapsed_time()
        if not self._sync_with_media:
            self._frame_counter = 0

    def is_sync_with_media(self) -> bool:
        return self._sync_with_media
    
    # ===== Configuration =====
    
    def has_user_font_override(self) -> bool:
        """Return True when the Text tab selected an explicit font."""
        return self._font_override_user

    def set_font_path(self, font_path: Optional[str], *, user_set: bool = False) -> None:
        """Apply a custom font path to the renderer.

        Args:
            font_path: Absolute font file path (or None to revert to default)
            user_set: True when coming from UI (locks future auto overrides)
        """

        if user_set:
            self._font_override_user = bool(font_path)
        elif self._font_override_user:
            self.logger.debug("[TextDirector] Skipping auto font because user override is active")
            return

        if font_path == self._active_font_path:
            return

        self._active_font_path = font_path

        if not self.text_renderer:
            return

        try:
            style = self.text_renderer.get_style()
            style.font_path = font_path
            self.text_renderer.set_style(style)
            self.logger.info(
                "[TextDirector] Applied %s font", font_path if font_path else "default"
            )
        except Exception as exc:
            self.logger.warning(f"[TextDirector] Failed to apply font '{font_path}': {exc}")

    def set_text_library(self, texts: List[str], default_split_mode=None, user_set: bool = False) -> None:
        """Set available texts.
        
        Args:
            texts: List of text strings
            default_split_mode: Default SplitMode for all texts (or None to use default)
            user_set: True if this is user-customized text (from Text tab), False for automatic (modes/themes)
        """
        # Use CENTERED_SYNC as default if none specified
        if default_split_mode is None and SplitMode:
            default_split_mode = SplitMode.CENTERED_SYNC
            
        self._text_entries = [
            TextEntry(text=t, weight=1.0, enabled=True, split_mode=default_split_mode)
            for t in texts
        ]
        self._user_text_library = user_set
        self._invalidate_text_cache()
        
        # CRITICAL: Set current split mode immediately when library is loaded
        # This ensures reset() (called after set_text_library) preserves the CORRECT mode
        # Previously, _current_split_mode was only updated on first render, causing
        # reset to preserve the OLD mode from the previous playback
        self._current_split_mode = default_split_mode
        
        self.logger.info(f"[TextDirector] Loaded {len(texts)} texts (user_set={user_set}), mode={default_split_mode}")
        self._reset_elapsed_time()
    
    def has_user_text_library(self) -> bool:
        """Check if text library was set by user (Text tab).
        
        Returns:
            True if user has customized the text library via Text tab
        """
        return self._user_text_library
    
    def set_text_weights(self, weights: dict[str, float]) -> None:
        """Set weights for specific texts.
        
        Args:
            weights: Dict mapping text -> weight (0.0-1.0)
        """
        for entry in self._text_entries:
            if entry.text in weights:
                entry.weight = max(0.0, min(1.0, weights[entry.text]))
    
    def set_text_enabled(self, text: str, enabled: bool) -> None:
        """Enable/disable specific text.
        
        Args:
            text: Text string to modify
            enabled: Whether to include in rotation
        """
        for entry in self._text_entries:
            if entry.text == text:
                entry.enabled = enabled
                break
    
    def set_text_split_mode(self, text: str, split_mode: 'SplitMode') -> None:
        """Set split mode for specific text.
        
        Args:
            text: Text string to modify
            split_mode: SplitMode enum value
        """
        for entry in self._text_entries:
            if entry.text == text:
                entry.split_mode = split_mode
                break
    
    def set_all_split_mode(self, split_mode: 'SplitMode') -> None:
        """Set split mode for all texts.
        
        Args:
            split_mode: SplitMode enum value
        """
        for entry in self._text_entries:
            entry.split_mode = split_mode
        self.logger.info(f"[TextDirector] Set all texts to split mode: {split_mode}")
    
    # ===== Selection =====
    
    def get_random_text(self) -> tuple[str, Optional['SplitMode']]:
        """Get random text using weighted selection.
        
        Returns:
            Tuple of (text, split_mode)
        """
        # Filter enabled texts
        enabled = [e for e in self._text_entries if e.enabled and e.weight > 0]
        
        if not enabled:
            return ("", None)
        
        # Weighted random selection
        total_weight = sum(e.weight for e in enabled)
        r = random.random() * total_weight
        
        cumulative = 0.0
        for entry in enabled:
            cumulative += entry.weight
            if r <= cumulative:
                self._current_text = entry.text
                self._current_split_mode = entry.split_mode
                
                # Log text selection with user_set status
                user_status = "(USER SET)" if self._user_text_library else "(AUTO)"
                self.logger.info(f"[TextDirector] Selected text {user_status}: '{entry.text}'")
                
                # Trigger callback
                if self._on_text_change:
                    try:
                        self._on_text_change(entry.text, entry.split_mode)
                    except Exception as e:
                        self.logger.error(f"Text change callback error: {e}")
                
                return (entry.text, entry.split_mode)
        
        # Fallback (shouldn't happen)
        return (enabled[0].text, enabled[0].split_mode)
    
    def get_current_text(self) -> tuple[str, Optional['SplitMode']]:
        """Get current text and split mode.
        
        Returns:
            Tuple of (text, split_mode)
        """
        return (self._current_text, self._current_split_mode)
    
    def on_media_change(self) -> None:
        """Force text change when media changes (for CENTERED_SYNC mode).
        
        Call this when visual programs change their media (image/video)
        to sync text changes with media changes.
        """
        # Only change text if enabled and in CENTERED_SYNC mode
        if not self._enabled:
            return
        if not self._sync_with_media:
            return
        
        if self._current_split_mode and SplitMode and self._current_split_mode == SplitMode.CENTERED_SYNC:
            text, split_mode = self.get_random_text()
            if text:
                self._current_text = text
                self._current_split_mode = split_mode
                self._render_current_text()
                self._frame_counter = 0  # Reset counter
                self._reset_elapsed_time()
                self.logger.debug(f"[TextDirector] Text synced with media change: {text[:30]}...")
    
    # ===== Update Loop =====
    
    def update(self) -> None:
        """Update text display (call every frame from compositor).
        
        This handles:
        - Text cycling based on timing
        - Rendering text with split modes
        - Clearing text when disabled
        - Scrolling animation (for SUBTEXT mode)
        """
        if not self._enabled:
            return

        if not self.text_renderer or not self.compositor:
            return

        if not self._text_entries:
            return

        now = self._time_provider()
        if self._last_update_time is None:
            self._last_update_time = now
        dt = max(0.0, now - self._last_update_time)
        self._last_update_time = now
        self._elapsed_time_s += dt

        # Update scrolling animation (pixels per frame at 60fps equivalent)
        self._scroll_offset += self._scroll_speed * dt
        # No wrapping - let it grow and wrap in rendering logic

        self._frame_counter += 1
        
        # Determine timing based on mode
        # SUBTEXT: 10 seconds (hard-coded)
        # CENTERED_SYNC: synced with media (handled via on_media_change)
        if self._sync_with_media:
            if self._current_split_mode and SplitMode:
                if self._current_split_mode == SplitMode.SUBTEXT:
                    target_seconds = 10.0  # 10 seconds regardless of FPS
                elif self._current_split_mode == SplitMode.CENTERED_SYNC:
                    target_seconds = float("inf")  # Media change drives update
                else:
                    target_seconds = self._default_target_seconds
            else:
                target_seconds = self._default_target_seconds
        else:
            target_seconds = self._manual_target_seconds
        
        # Change text at interval (only for SUBTEXT mode in practice)
        if not math.isinf(target_seconds) and self._elapsed_time_s >= target_seconds:
            # Get new random text
            text, split_mode = self.get_random_text()
            if text:
                self._current_text = text
                self._current_split_mode = split_mode
                self._render_current_text()
            self._frame_counter = 0
            self._elapsed_time_s = 0.0
        elif self._frame_counter == 1:
            # First frame - render initial text
            if not self._current_text:
                text, split_mode = self.get_random_text()
                if text:
                    self._current_text = text
                    self._current_split_mode = split_mode
                    self._render_current_text()

        # If a long target is infinite (media sync) keep elapsed time bounded so floats do not grow unbounded
        if math.isinf(target_seconds):
            self._elapsed_time_s = min(self._elapsed_time_s, 60.0)
        
        # Re-render SUBTEXT mode every frame for scrolling animation
        if self._current_split_mode and SplitMode and self._current_split_mode == SplitMode.SUBTEXT:
            self._render_current_text(force=False)
    
    def _render_current_text(self, *, force: bool = True) -> None:
        """Render current text to compositor using split mode."""
        if not self._current_text or not self.text_renderer:
            return
        
        # Get all compositors (primary + secondaries)
        all_compositors = self._get_all_compositors()
        if not all_compositors:
            return
        
        now = self._time_provider()
        if (not force and self._current_split_mode and SplitMode
                and self._current_split_mode == SplitMode.SUBTEXT):
            if self._last_subtext_render_time is not None:
                since_last = now - self._last_subtext_render_time
                delta = abs(self._scroll_offset - self._last_subtext_render_offset)
                if (since_last < self._subtext_render_min_interval
                        and delta < self._subtext_render_min_delta_px):
                    return

        try:
            # Clear existing text on ALL compositors
            for comp in all_compositors:
                try:
                    comp.clear_text_textures()
                except Exception as e:
                    self.logger.error(f"[TextDirector] Failed to clear text on compositor: {e}")
            
            # Render based on split mode
            log_at_info = self._should_log_render(self._current_split_mode)
            log_fn = self.logger.info if log_at_info else self.logger.debug
            log_fn(
                f"[TextDirector] RENDER: mode={self._current_split_mode}, scroll_offset={self._scroll_offset:.2f}"
            )
            
            if self._current_split_mode and SplitMode:
                if self._current_split_mode == SplitMode.SUBTEXT:
                    # Scrolling horizontal bands (carousel effect)
                    if log_at_info:
                        self.logger.info("[TextDirector] Rendering CAROUSEL (subtext)")
                    else:
                        self.logger.debug("[TextDirector] Rendering CAROUSEL (subtext)")
                    self._render_subtext()
                elif self._current_split_mode == SplitMode.CENTERED_SYNC:
                    # Centered text (default mode)
                    if log_at_info:
                        self.logger.info("[TextDirector] Rendering CENTERED")
                    else:
                        self.logger.debug("[TextDirector] Rendering CENTERED")
                    self._render_centered()
                else:
                    # Fallback: render as centered text
                    if log_at_info:
                        self.logger.info(
                            f"[TextDirector] Rendering FALLBACK (unknown mode: {self._current_split_mode})"
                        )
                    else:
                        self.logger.debug(
                            f"[TextDirector] Rendering FALLBACK (unknown mode: {self._current_split_mode})"
                        )
                    self._render_centered()
            else:
                # No split mode: render as centered text
                if log_at_info:
                    self.logger.info("[TextDirector] Rendering DEFAULT CENTERED (no mode set)")
                else:
                    self.logger.debug("[TextDirector] Rendering DEFAULT CENTERED (no mode set)")
                self._render_centered()
                
            if self._current_split_mode and SplitMode and self._current_split_mode == SplitMode.SUBTEXT:
                self._last_subtext_render_time = now
                self._last_subtext_render_offset = self._scroll_offset

        except Exception as e:
            self.logger.error(f"[TextDirector] Failed to render text: {e}", exc_info=True)
    
    def _render_centered(self) -> None:
        """Render text as single centered element on all compositors."""
        rendered = self._get_cached_rendered_text(
            self._current_text,
            self._current_split_mode,
            large=True,
            shadow=True
        )
        
        if rendered and hasattr(rendered, 'texture_data'):
            # Add text to ALL compositors (primary + secondaries)
            for comp in self._get_all_compositors():
                try:
                    comp.add_text_texture(
                        rendered.texture_data,
                        x=0.5,
                        y=0.5,
                        alpha=1.0,
                        scale=1.5
                    )
                except Exception as e:
                    self.logger.error(f"[TextDirector] Failed to add text to compositor: {e}")
    
    
    def _render_subtext(self) -> None:
        """Render scrolling wallpaper grid (carousel effect).
        
        Creates a tiled grid of text that scrolls horizontally,
        matching the behavior of mode 7 in test_text_effects.py.
        
        Key features:
        - Grid of repeated text filling screen
        - Horizontal scrolling (left-to-right)
        - Odd rows staggered for visual variety
        - Seamless wrapping at edges
        """
        if not self._current_text:
            return
        
        # Render single text instance (will be tiled)
        rendered = self._get_cached_rendered_text(
            self._current_text,
            self._current_split_mode,
            large=True,
            shadow=False
        )
        
        if not rendered or not hasattr(rendered, 'texture_data'):
            return
        
        # Get logical layout dimensions (respects virtual overrides for preview/live parity)
        screen_width, screen_height = self._get_layout_dimensions()

        # Ensure every compositor renders using the same virtual canvas so spacing stays identical
        for comp in self._get_all_compositors():
            if hasattr(comp, "set_virtual_screen_size"):
                try:
                    comp.set_virtual_screen_size(screen_width, screen_height)
                except Exception:
                    self.logger.debug("[TextDirector] Failed to set virtual screen size on compositor", exc_info=True)
        
        # Text dimensions with scale
        text_scale = 1.5  # Larger for better coverage
        text_width_px = rendered.width * text_scale
        text_height_px = rendered.height * text_scale
        
        # Dynamic spacing based on message length (matches launcher behavior)
        # Shorter messages get wider spacing, longer messages get tighter spacing
        # This ensures consistent visual density across different text lengths
        # Formula: spacing scales inversely with SCALED text width
        # - Short messages ("Yes", ~180px scaled): spacing ~1.50 (50% gap)
        # - Medium messages ("AND DEEPER", ~600px scaled): spacing ~1.15 (15% gap)
        # - Long messages (>1200px scaled): spacing ~1.05 (5% gap)
        base_width = 700.0  # Reference width for balanced spacing (scaled)
        min_spacing = 1.05  # Minimum gap for very long messages (5%)
        max_spacing = 1.50  # Maximum gap for very short messages (50%)
        spacing = base_width / max(text_width_px, 50)  # Use SCALED width for calculation
        spacing = max(min_spacing, min(max_spacing, spacing))  # Clamp to range
        
        # Calculate NDC units (normalized device coordinates: -1 to 1)
        text_w_ndc = (text_width_px * spacing / screen_width) * 2.0
        text_h_ndc = (text_height_px * spacing / screen_height) * 2.0
        
        # Calculate grid dimensions (add extra columns for seamless scrolling)
        cols_needed = int(screen_width / (text_width_px * spacing)) + 2
        rows_needed = int(screen_height / (text_height_px * spacing)) + 1
        
        # Limit to reasonable numbers
        cols_needed = min(cols_needed, 15)
        rows_needed = min(rows_needed, 10)
        
        # Convert scroll offset (pixels) to NDC units (-1 to 1)
        # Divide by screen_width to normalize, then scale to NDC range
        scroll_ndc = (self._scroll_offset / screen_width) * 2.0
        
        # Render each tile in the grid
        for row in range(rows_needed):
            for col in range(cols_needed):
                # Base position in NDC (-1 to 1)
                x_ndc = -1.0 + (col * text_w_ndc)
                
                # Stagger odd rows for visual variety
                if row % 2 == 1:
                    x_ndc += text_w_ndc * 0.5
                
                # Add carousel scrolling
                x_ndc -= scroll_ndc
                
                # Wrap around when scrolling off screen
                wrap_width = text_w_ndc * cols_needed
                while x_ndc < -1.0 - text_w_ndc:
                    x_ndc += wrap_width
                while x_ndc > 1.0 + text_w_ndc:
                    x_ndc -= wrap_width
                
                # Vertical position in NDC (top to bottom)
                y_ndc = 1.0 - (row * text_h_ndc) - text_h_ndc * 0.5
                
                # Convert NDC (-1 to 1) to compositor coordinates (0 to 1)
                x = (x_ndc + 1.0) / 2.0
                y = (y_ndc + 1.0) / 2.0
                
                # Add text texture at this position on ALL compositors
                for comp in self._get_all_compositors():
                    try:
                        comp.add_text_texture(
                            rendered.texture_data,
                            x=x,
                            y=y,
                            alpha=1.0,
                            scale=text_scale
                        )
                    except Exception as e:
                        self.logger.error(f"[TextDirector] Failed to add subtext to compositor: {e}")
    
    # ===== Status =====
    
    def get_enabled_count(self) -> int:
        """Get count of enabled texts.
        
        Returns:
            Number of texts that can be shown
        """
        return sum(1 for e in self._text_entries if e.enabled and e.weight > 0)
    
    def get_text_entries(self) -> List[TextEntry]:
        """Get all text entries.
        
        Returns:
            List of TextEntry objects
        """
        return self._text_entries.copy()
