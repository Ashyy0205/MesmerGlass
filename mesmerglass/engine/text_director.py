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
from typing import Optional, Callable, List
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
        on_text_change: Optional[Callable[[str, Optional['SplitMode']], None]] = None
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
        
        # Text library
        self._text_entries: List[TextEntry] = []
        self._current_text = ""
        self._current_split_mode = SplitMode.CENTERED_SYNC if SplitMode else None
        self._user_text_library = False  # True if text library was set by user (Text tab)
        
        # Timing and rendering control
        self._enabled = False  # Whether to render text
        self._frame_counter = 0
        self._frames_per_text = 120  # 2 seconds at 60fps (how long to show each text)
        
        # Scrolling animation state (for SUBTEXT mode)
        self._scroll_offset = 0.0
        self._scroll_speed = 30.0  # Pixels per second (doubled from 15.0)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("[TextDirector] Initialized (independent text system)")
    
    # ===== Configuration =====
    
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
    
    def set_timing(self, frames_per_text: int) -> None:
        """Set how long to show each text.
        
        Args:
            frames_per_text: Frames to display each text (60 = 1 second)
        """
        self._frames_per_text = max(1, frames_per_text)
    
    def is_enabled(self) -> bool:
        """Check if text rendering is enabled.
        
        Returns:
            True if text will be rendered
        """
        return self._enabled
    
    # ===== Configuration =====
    
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
        self.logger.info(f"[TextDirector] Loaded {len(texts)} texts (user_set={user_set})")
    
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
        
        if self._current_split_mode and SplitMode and self._current_split_mode == SplitMode.CENTERED_SYNC:
            text, split_mode = self.get_random_text()
            if text:
                self._current_text = text
                self._current_split_mode = split_mode
                self._render_current_text()
                self._frame_counter = 0  # Reset counter
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
        
        # Update scrolling animation (pixels per frame at 60fps)
        dt = 1.0 / 60.0  # Assume 60fps
        self._scroll_offset += self._scroll_speed * dt
        # No wrapping - let it grow and wrap in rendering logic
        
        self._frame_counter += 1
        
        # Determine timing based on mode
        # SUBTEXT: 10 seconds (600 frames at 60fps)
        # CENTERED_SYNC: synced with media (handled via on_media_change), but use long default
        if self._current_split_mode and SplitMode:
            if self._current_split_mode == SplitMode.SUBTEXT:
                frames_per_text = 600  # 10 seconds
            else:
                frames_per_text = 99999999  # Effectively infinite - media change will trigger update
        else:
            frames_per_text = self._frames_per_text  # Fallback to default
        
        # Change text at interval (only for SUBTEXT mode in practice)
        if self._frame_counter >= frames_per_text:
            # Get new random text
            text, split_mode = self.get_random_text()
            if text:
                self._current_text = text
                self._current_split_mode = split_mode
                self._render_current_text()
            self._frame_counter = 0
        elif self._frame_counter == 1:
            # First frame - render initial text
            if not self._current_text:
                text, split_mode = self.get_random_text()
                if text:
                    self._current_text = text
                    self._current_split_mode = split_mode
                    self._render_current_text()
        
        # Re-render SUBTEXT mode every frame for scrolling animation
        if self._current_split_mode and SplitMode and self._current_split_mode == SplitMode.SUBTEXT:
            self._render_current_text()
    
    def _render_current_text(self) -> None:
        """Render current text to compositor using split mode."""
        if not self._current_text or not self.text_renderer or not self.compositor:
            return
        
        try:
            # Clear existing text
            self.compositor.clear_text_textures()
            
            # Render based on split mode
            if self._current_split_mode and SplitMode:
                if self._current_split_mode == SplitMode.SUBTEXT:
                    # Scrolling horizontal bands (carousel effect)
                    self._render_subtext()
                elif self._current_split_mode == SplitMode.CENTERED_SYNC:
                    # Centered text (default mode)
                    self._render_centered()
                else:
                    # Fallback: render as centered text
                    self._render_centered()
            else:
                # No split mode: render as centered text
                self._render_centered()
                
        except Exception as e:
            self.logger.error(f"[TextDirector] Failed to render text: {e}", exc_info=True)
    
    def _render_centered(self) -> None:
        """Render text as single centered element."""
        rendered = self.text_renderer.render_main_text(
            self._current_text,
            large=True,
            shadow=True
        )
        
        if rendered and hasattr(rendered, 'texture_data'):
            self.compositor.add_text_texture(
                rendered.texture_data,
                x=0.5,
                y=0.5,
                alpha=1.0,
                scale=1.5
            )
    
    
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
        rendered = self.text_renderer.render_main_text(
            self._current_text,
            large=True,  # Large text for better visibility
            shadow=False
        )
        
        if not rendered or not hasattr(rendered, 'texture_data'):
            return
        
        # Get actual screen dimensions from compositor (critical for correct spacing!)
        # Fallback to 1920x1080 if compositor not available
        if self.compositor and hasattr(self.compositor, 'width') and hasattr(self.compositor, 'height'):
            screen_width = max(1, self.compositor.width())
            screen_height = max(1, self.compositor.height())
        else:
            screen_width = 1920
            screen_height = 1080
        
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
                
                # Add text texture at this position
                # Use alpha=1.0 so the opacity slider has full control
                self.compositor.add_text_texture(
                    rendered.texture_data,
                    x=x,
                    y=y,
                    alpha=1.0,
                    scale=text_scale
                )
    
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
