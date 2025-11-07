"""Theme bank - manages multiple themes with media selection.

Implements Trance ThemeBank algorithm:
- Keeps 2 active themes loaded
- Loads 3rd theme asynchronously in background
- Weighted shuffler avoids last 8 selected images
- Theme switching with cooldown
"""

from __future__ import annotations
from typing import Optional, List
from pathlib import Path
from collections import deque
import time

from .theme import ThemeConfig, Shuffler
from .media import ImageCache, ImageData


class ThemeBank:
    """Manages multiple themes and media selection.
    
    Implements Trance ThemeBank strategy:
    - Theme 0: Previous theme (being unloaded)
    - Theme 1: Primary active theme  
    - Theme 2: Alternate active theme
    - Theme 3: Next theme (loading in background)
    """
    
    # Number of recent images to track
    LAST_IMAGE_COUNT = 8
    
    # Cooldown between theme switches (in async updates, ~8-10 seconds)
    THEME_SWITCH_COOLDOWN = 500
    
    def __init__(
        self,
        themes: List[ThemeConfig],
        root_path: Path,
        image_cache_size: int = 64
    ):
        """Initialize theme bank.
        
        Args:
            themes: List of theme configurations
            root_path: Root directory for resolving paths
            image_cache_size: Total images to cache across all themes
        """
        self._themes = [t for t in themes if t.enabled]
        self._root_path = root_path
        self._image_cache_size = image_cache_size
        
        # Active theme indices (None = not loaded)
        self._active_theme_indices = [None, None, None, None]  # 0=old, 1=primary, 2=alt, 3=next
        
        # Image caches per theme
        self._image_caches: dict[int, ImageCache] = {}
        
        # Shufflers per theme to avoid repetition
        self._shufflers: dict[int, Shuffler] = {}
        
        # Track last selected images globally (avoid repetition)
        self._last_images: deque[tuple[int, int]] = deque(maxlen=self.LAST_IMAGE_COUNT)
        
        # Theme switch cooldown
        self._last_theme_switch = 0
        self._async_update_count = 0
        
        # Preload images for theme paths
        self._preload_theme_images()
    
    def _preload_theme_images(self) -> None:
        """Build image path lists for each theme."""
        for i, theme in enumerate(self._themes):
            # Count total images
            image_count = len(theme.image_path)
            if image_count == 0:
                continue
            
            # Create shuffler
            self._shufflers[i] = Shuffler(image_count)
            
            # Create image cache
            cache_size = self._cache_per_theme()
            self._image_caches[i] = ImageCache(cache_size)
            
            # Resolve full paths
            full_paths = [
                self._root_path / path
                for path in theme.image_path
            ]
            
            # Preload some images
            self._image_caches[i].preload_images(full_paths, max_count=cache_size)
    
    def _cache_per_theme(self) -> int:
        """Calculate cache size per theme.
        
        Returns:
            Images to cache per theme
        """
        enabled_count = len(self._themes)
        if enabled_count == 0:
            return 0
        # Distribute total cache among max 3 active themes
        return self._image_cache_size // min(3, enabled_count)
    
    def set_active_themes(self, primary_index: int, alt_index: Optional[int] = None) -> None:
        """Set active themes.
        
        Args:
            primary_index: Index of primary theme (1-indexed like Trance)
            alt_index: Optional index of alternate theme
        """
        # Convert from 1-indexed to 0-indexed
        primary_idx = primary_index - 1
        alt_idx = (alt_index - 1) if alt_index is not None else None
        
        if primary_idx < 0 or primary_idx >= len(self._themes):
            raise ValueError(f"Invalid primary theme index: {primary_index}")
        if alt_idx is not None and (alt_idx < 0 or alt_idx >= len(self._themes)):
            raise ValueError(f"Invalid alternate theme index: {alt_index}")
        
        self._active_theme_indices[1] = primary_idx
        self._active_theme_indices[2] = alt_idx
    
    def get_image(self, alternate: bool = False) -> Optional[ImageData]:
        """Get next image from active theme.
        
        Args:
            alternate: If True, use alternate theme; otherwise primary
        
        Returns:
            ImageData if available, None if no images
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Select theme
        theme_slot = 2 if alternate else 1
        theme_idx = self._active_theme_indices[theme_slot]
        
        logger.info(f"[ThemeBank] get_image: alternate={alternate}, theme_slot={theme_slot}, theme_idx={theme_idx}")
        logger.info(f"[ThemeBank] _active_theme_indices={self._active_theme_indices}")
        
        if theme_idx is None:
            logger.warning(f"[ThemeBank] No active theme at slot {theme_slot}")
            return None
        
        theme = self._themes[theme_idx]
        if not theme.image_path:
            logger.warning(f"[ThemeBank] Theme {theme_idx} has no image paths")
            return None
        
        logger.info(f"[ThemeBank] Theme {theme_idx} has {len(theme.image_path)} images")
        
        # Get cache for this theme
        cache = self._image_caches.get(theme_idx)
        if cache is None:
            logger.warning(f"[ThemeBank] No image cache for theme {theme_idx}")
            return None
        
        # Process any newly loaded images
        cache.process_loaded_images()
        
        # Get shuffler
        shuffler = self._shufflers.get(theme_idx)
        if shuffler is None:
            logger.warning(f"[ThemeBank] No shuffler for theme {theme_idx}")
            return None
        
        # Select next image using weighted shuffler
        # BUT don't advance if last attempt failed (image still loading)
        if not hasattr(self, '_last_failed_index'):
            self._last_failed_index = {}
        
        if not hasattr(self, '_preload_index'):
            self._preload_index = {}
        
        # Check if we're retrying the same image
        last_failed = self._last_failed_index.get(theme_idx)
        if last_failed is not None:
            image_index = last_failed
            logger.info(f"[ThemeBank] Retrying previously failed image index: {image_index}")
        else:
            image_index = shuffler.next()
            logger.info(f"[ThemeBank] Shuffler selected image index: {image_index}")
        
        # Get image path
        if image_index >= len(theme.image_path):
            logger.warning(f"[ThemeBank] Image index {image_index} >= {len(theme.image_path)}")
            return None
        
        image_path = self._root_path / theme.image_path[image_index]
        
        logger.info(f"[ThemeBank] Loading image: {image_path}")
        
        # Try to get from cache
        image_data = cache.get_image(image_path)
        if image_data is None:
            # Mark this index as failed so we retry it next time
            self._last_failed_index[theme_idx] = image_index
            logger.info(f"[ThemeBank] Image still loading - will retry index {image_index} on next request")
            return None
        
        # Success! Clear the failed index
        if theme_idx in self._last_failed_index:
            del self._last_failed_index[theme_idx]
        
        logger.info(f"[ThemeBank] Successfully loaded image: {image_data.width}x{image_data.height}")
        
        # Update last images list
        self._last_images.append((theme_idx, image_index))
        
        # Decrease weight of selected image
        shuffler.decrease(image_index)
        
        # If list is full, increase weight of oldest image
        if len(self._last_images) >= self.LAST_IMAGE_COUNT:
            old_theme_idx, old_image_idx = self._last_images[0]
            old_shuffler = self._shufflers.get(old_theme_idx)
            if old_shuffler:
                old_shuffler.increase(old_image_idx)
        
        return image_data
    
    def get_text_line(self, alternate: bool = False) -> Optional[str]:
        """Get random text line from active theme.
        
        Args:
            alternate: If True, use alternate theme; otherwise primary
        
        Returns:
            Random text line or None
        """
        import random
        
        theme_slot = 2 if alternate else 1
        theme_idx = self._active_theme_indices[theme_slot]
        
        if theme_idx is None:
            return None
        
        theme = self._themes[theme_idx]
        if not theme.text_line:
            return None
        
        return random.choice(theme.text_line)
    
    def async_update(self) -> None:
        """Async update - process background loading.
        
        Should be called regularly (e.g. every frame).
        """
        self._async_update_count += 1
        
        # Process loaded images for all active caches
        for cache in self._image_caches.values():
            cache.process_loaded_images()
    
    def can_switch_themes(self) -> bool:
        """Check if theme switching is allowed (cooldown expired).
        
        Returns:
            True if can switch themes
        """
        return self._async_update_count - self._last_theme_switch >= self.THEME_SWITCH_COOLDOWN
    
    def switch_themes(self) -> bool:
        """Attempt to switch to next theme set.
        
        Returns:
            True if switched, False if cooldown active
        """
        if not self.can_switch_themes():
            return False
        
        import random
        
        # Select new random themes
        if len(self._themes) >= 2:
            indices = list(range(len(self._themes)))
            random.shuffle(indices)
            self._active_theme_indices[1] = indices[0]
            self._active_theme_indices[2] = indices[1] if len(indices) > 1 else None
        elif len(self._themes) == 1:
            self._active_theme_indices[1] = 0
            self._active_theme_indices[2] = None
        
        self._last_theme_switch = self._async_update_count
        return True
    
    def shutdown(self) -> None:
        """Shutdown all caches."""
        for cache in self._image_caches.values():
            cache.shutdown()
    
    def get_theme_count(self) -> int:
        """Get number of enabled themes."""
        return len(self._themes)
    
    def get_active_theme_names(self) -> tuple[Optional[str], Optional[str]]:
        """Get names of active themes.
        
        Returns:
            (primary_name, alternate_name) tuple
        """
        primary_idx = self._active_theme_indices[1]
        alt_idx = self._active_theme_indices[2]
        
        primary_name = self._themes[primary_idx].name if primary_idx is not None else None
        alt_name = self._themes[alt_idx].name if alt_idx is not None else None
        
        return (primary_name, alt_name)
    
    @property
    def text_lines(self) -> List[str]:
        """Get all text lines from all enabled themes.
        
        Returns:
            Combined list of text lines from all themes
        """
        all_texts = []
        for theme in self._themes:
            if hasattr(theme, 'text_line') and theme.text_line:
                all_texts.extend(theme.text_line)
        return all_texts
