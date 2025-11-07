"""Text rendering system for overlay effects.

This module provides text-to-texture rendering with support for:
- Font loading and caching
- Text split modes (word, line, character, gaps)
- Shadow and outline effects
- OpenGL texture generation
- Multi-line text layout

Based on Trance's text rendering system.
"""

import os
from pathlib import Path
from typing import Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None


class SplitMode(Enum):
    """Text split/display modes."""
    CENTERED_SYNC = 0       # Centered text that changes with media
    SUBTEXT = 1            # Scrolling horizontal bands filling screen (carousel effect)


@dataclass
class TextStyle:
    """Text appearance configuration."""
    font_path: Optional[str] = None     # Path to TTF font file
    font_size: int = 48                 # Font size in points
    color: Tuple[int, int, int, int] = (255, 255, 255, 255)  # RGBA
    outline_width: int = 0              # Outline thickness (0 = no outline)
    outline_color: Tuple[int, int, int, int] = (0, 0, 0, 255)  # Outline RGBA
    shadow_offset: Tuple[int, int] = (0, 0)  # Shadow offset (x, y)
    shadow_blur: int = 0                # Shadow blur radius
    shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 128)  # Shadow RGBA
    line_spacing: float = 1.2           # Line height multiplier


@dataclass
class RenderedText:
    """A rendered text element with texture data."""
    text: str                           # Original text
    texture_data: np.ndarray           # RGBA image data
    width: int                          # Texture width
    height: int                         # Texture height
    baseline: int                       # Baseline offset from top


class TextRenderer:
    """Renders text to OpenGL textures with various effects.
    
    This class handles:
    - Font loading and caching
    - Text rendering with PIL/Pillow
    - Shadow and outline effects
    - Text splitting (words, lines, characters)
    - Multi-line layout
    
    Usage:
        renderer = TextRenderer()
        renderer.set_style(TextStyle(font_size=64, color=(255, 255, 255, 255)))
        
        # Render single text
        result = renderer.render("Hello World")
        
        # Render with split mode
        parts = renderer.render_split("Hello World", SplitMode.SPLIT_WORD)
        # Returns: [RenderedText("Hello"), RenderedText("World")]
    """
    
    def __init__(self):
        """Initialize text renderer."""
        if Image is None:
            raise ImportError("Pillow is required for text rendering. Install with: pip install Pillow")
        
        self._style = TextStyle()
        self._font_cache = {}  # Cache loaded fonts
        self._current_font = None
        self._load_default_font()
    
    def _load_default_font(self):
        """Load default system font."""
        # Try to load a default font
        try:
            # First try MEDIA/Fonts directory
            media_fonts = Path(__file__).parent.parent.parent / "MEDIA" / "Fonts"
            if media_fonts.exists():
                font_files = list(media_fonts.glob("*.ttf")) + list(media_fonts.glob("*.otf"))
                if font_files:
                    self._style.font_path = str(font_files[0])
                    self._load_font()
                    print(f"[TextRenderer] Loaded font from MEDIA: {font_files[0].name}")
                    return
            
            # Try common system fonts
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
            
            for path in font_paths:
                if os.path.exists(path):
                    self._style.font_path = path
                    self._load_font()
                    print(f"[TextRenderer] Loaded system font: {path}")
                    return
            
            # Fallback to PIL default
            self._current_font = ImageFont.load_default()
            print("[TextRenderer] Using PIL default font (fallback)")
        except Exception as e:
            print(f"[TextRenderer] Warning: Could not load font: {e}")
            self._current_font = ImageFont.load_default()
    
    def _load_font(self):
        """Load font from current style settings."""
        if not self._style.font_path:
            self._current_font = ImageFont.load_default()
            return
        
        # Check cache
        cache_key = (self._style.font_path, self._style.font_size)
        if cache_key in self._font_cache:
            self._current_font = self._font_cache[cache_key]
            return
        
        # Load font
        try:
            font = ImageFont.truetype(self._style.font_path, self._style.font_size)
            self._font_cache[cache_key] = font
            self._current_font = font
        except Exception as e:
            print(f"[TextRenderer] Error loading font {self._style.font_path}: {e}")
            self._current_font = ImageFont.load_default()
    
    def set_style(self, style: TextStyle):
        """Update text rendering style.
        
        Args:
            style: New text style configuration
        """
        self._style = style
        self._load_font()
    
    def get_style(self) -> TextStyle:
        """Get current text style."""
        return self._style
    
    def measure_text(self, text: str) -> Tuple[int, int]:
        """Measure text dimensions.
        
        Args:
            text: Text to measure
        
        Returns:
            (width, height) in pixels
        """
        if not text:
            return (0, 0)
        
        # Create temporary image for measurement
        temp_img = Image.new('RGBA', (1, 1))
        draw = ImageDraw.Draw(temp_img)
        
        # Get bounding box
        bbox = draw.textbbox((0, 0), text, font=self._current_font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        
        # No padding - use exact text bounds for tight rendering
        # (outline and shadow will be clipped if enabled)
        
        return (width, height)
    
    def render(self, text: str) -> RenderedText:
        """Render text to texture.
        
        Args:
            text: Text to render
        
        Returns:
            RenderedText with texture data
        """
        if not text:
            # Return empty texture
            empty = np.zeros((1, 1, 4), dtype=np.uint8)
            return RenderedText(text, empty, 1, 1, 0)
        
        # Measure text (gives us initial size with font padding)
        width, height = self.measure_text(text)
        
        # Add some buffer for rendering (will crop later)
        buffer = 20
        img = Image.new('RGBA', (width + buffer * 2, height + buffer * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Calculate text position (centered in buffer)
        text_x = buffer
        text_y = buffer
        
        # Draw shadow
        if self._style.shadow_blur > 0 or self._style.shadow_offset != (0, 0):
            shadow_x = text_x + self._style.shadow_offset[0]
            shadow_y = text_y + self._style.shadow_offset[1]
            
            # Simple shadow (blur would require PIL.ImageFilter)
            draw.text((shadow_x, shadow_y), text, font=self._current_font, fill=self._style.shadow_color)
        
        # Draw outline
        if self._style.outline_width > 0:
            outline_w = self._style.outline_width
            for ox in range(-outline_w, outline_w + 1):
                for oy in range(-outline_w, outline_w + 1):
                    if ox != 0 or oy != 0:
                        draw.text((text_x + ox, text_y + oy), text, font=self._current_font, 
                                 fill=self._style.outline_color)
        
        # Draw main text
        draw.text((text_x, text_y), text, font=self._current_font, fill=self._style.color)
        
        # Convert to numpy array
        texture_data = np.array(img, dtype=np.uint8)
        
        # Find the actual bounding box of non-transparent pixels
        alpha_channel = texture_data[:, :, 3]
        rows = np.any(alpha_channel > 0, axis=1)
        cols = np.any(alpha_channel > 0, axis=0)
        
        if np.any(rows) and np.any(cols):
            # Crop to actual content
            y_min, y_max = np.where(rows)[0][[0, -1]]
            x_min, x_max = np.where(cols)[0][[0, -1]]
            
            # Add 1 pixel padding to avoid clipping
            y_min = max(0, y_min - 1)
            y_max = min(texture_data.shape[0] - 1, y_max + 1)
            x_min = max(0, x_min - 1)
            x_max = min(texture_data.shape[1] - 1, x_max + 1)
            
            # Crop the texture
            texture_data = texture_data[y_min:y_max+1, x_min:x_max+1]
            width = texture_data.shape[1]
            height = texture_data.shape[0]
        else:
            # No content found, use original
            width = img.width
            height = img.height
        
        # Calculate baseline
        bbox = draw.textbbox((text_x, text_y), text, font=self._current_font)
        baseline = bbox[1] - text_y
        
        return RenderedText(text, texture_data, width, height, baseline)
    
    def render_split(self, text: str, mode: SplitMode) -> List[RenderedText]:
        """Render text with split mode.
        
        Args:
            text: Text to render
            mode: How to split the text
        
        Returns:
            List of RenderedText, one per split element
        """
        if mode == SplitMode.CENTERED_SYNC:
            # Centered text - render as single complete text
            return [self.render(text)]
        
        elif mode == SplitMode.SUBTEXT:
            # Scrolling bands - render for wallpaper mode
            return [self.render(text)]
        
        # Default fallback
        return [self.render(text)]
    
    def render_multiline(self, lines: List[str], max_width: Optional[int] = None) -> RenderedText:
        """Render multiple lines of text.
        
        Args:
            lines: List of text lines
            max_width: Maximum width (None = no limit)
        
        Returns:
            Combined RenderedText
        """
        if not lines:
            empty = np.zeros((1, 1, 4), dtype=np.uint8)
            return RenderedText("", empty, 1, 1, 0)
        
        # Render each line
        rendered_lines = [self.render(line) for line in lines]
        
        # Calculate total size
        max_line_width = max(r.width for r in rendered_lines)
        if max_width and max_line_width > max_width:
            max_line_width = max_width
        
        line_height = int(self._style.font_size * self._style.line_spacing)
        total_height = line_height * len(lines)
        
        # Create combined image
        combined_img = np.zeros((total_height, max_line_width, 4), dtype=np.uint8)
        
        # Paste each line
        y_offset = 0
        for rendered in rendered_lines:
            # Center horizontally
            x_offset = (max_line_width - rendered.width) // 2
            
            # Paste line (with bounds checking)
            y_end = min(y_offset + rendered.height, total_height)
            x_end = min(x_offset + rendered.width, max_line_width)
            
            combined_img[y_offset:y_end, x_offset:x_end] = \
                rendered.texture_data[:y_end-y_offset, :x_end-x_offset]
            
            y_offset += line_height
        
        combined_text = '\n'.join(lines)
        return RenderedText(combined_text, combined_img, max_line_width, total_height, 0)
    
    def get_font_list(self) -> List[str]:
        """Get list of available system fonts.
        
        Returns:
            List of font file paths
        """
        font_paths = []
        
        # Windows fonts
        win_fonts = Path("C:/Windows/Fonts")
        if win_fonts.exists():
            font_paths.extend([str(f) for f in win_fonts.glob("*.ttf")])
            font_paths.extend([str(f) for f in win_fonts.glob("*.otf")])
        
        # Linux fonts
        linux_fonts = Path("/usr/share/fonts/truetype")
        if linux_fonts.exists():
            for subdir in linux_fonts.iterdir():
                if subdir.is_dir():
                    font_paths.extend([str(f) for f in subdir.glob("*.ttf")])
        
        # macOS fonts
        mac_fonts = Path("/System/Library/Fonts")
        if mac_fonts.exists():
            font_paths.extend([str(f) for f in mac_fonts.glob("*.ttf")])
            font_paths.extend([str(f) for f in mac_fonts.glob("*.ttc")])
        
        return sorted(font_paths)
    
    # ===== Trance 3-Layer Text System =====
    
    def render_main_text(
        self,
        text: str,
        large: bool = True,
        shadow: bool = True,
        max_width_pct: float = 0.625,  # 62.5% of screen width
        max_height_pct: float = 0.33    # 33% of screen height
    ) -> Optional[RenderedText]:
        """Render main text (large, centered, optional shadow).
        
        This is Trance's primary text layer - large centered text
        with optional shadow. Used by most visual programs.
        
        Args:
            text: Text string to render
            large: If True, use large font size
            shadow: If True, render shadow layer behind text
            max_width_pct: Maximum width as percentage of screen
            max_height_pct: Maximum height as percentage of screen
        
        Returns:
            RenderedText with texture data, or None if failed
        """
        if not text.strip():
            return None
        
        # Save current style
        original_style = self._style
        
        try:
            # Create style for main text
            main_style = TextStyle(
                font_path=original_style.font_path,
                font_size=72 if large else 48,
                color=original_style.color,
                shadow_offset=(4, 4) if shadow else (0, 0),
                shadow_color=(0, 0, 0, 180)
            )
            self.set_style(main_style)
            
            # Render text
            result = self.render(text)
            
            return result
            
        except Exception as e:
            print(f"Error rendering main text: {e}")
            return None
        finally:
            # Restore original style
            self.set_style(original_style)
    
    def render_subtext(
        self,
        text_list: List[str],
        band_height_pct: float = 0.0625,  # 6.25% of viewport height
        viewport_height: int = 1080,
        color: Optional[Tuple[int, int, int, int]] = None
    ) -> List[RenderedText]:
        """Render subtext as horizontal scrolling bands.
        
        This is Trance's subtext layer - horizontal bands of text
        that scroll across the screen. Used by SubTextVisual.
        
        Creates multiple horizontal bands that fill the screen vertically.
        Each band contains concatenated text from the list.
        
        Args:
            text_list: List of text strings to cycle through
            band_height_pct: Height of each band as percentage of viewport
            viewport_height: Viewport height in pixels
            color: RGBA color for text (None = use current style)
        
        Returns:
            List of RenderedText for each band
        """
        if not text_list:
            return []
        
        # Save current style
        original_style = self._style
        
        try:
            # Create style for subtext
            band_height = int(viewport_height * band_height_pct)
            subtext_style = TextStyle(
                font_path=original_style.font_path,
                font_size=max(18, band_height // 2),  # Scale font to band
                color=color if color else (128, 128, 128, 200)
            )
            self.set_style(subtext_style)
            
            # Calculate number of bands to fill screen
            num_bands = int(1.0 / band_height_pct)  # e.g., 16 bands at 6.25%
            
            rendered_bands = []
            
            for band_idx in range(num_bands):
                # Concatenate text with spacing for scrolling
                band_text = "   ".join(text_list * 3)  # Repeat 3 times for scrolling
                
                # Render band text
                result = self.render(band_text)
                
                # Ensure band has minimum width for scrolling
                if result.width < 2000:
                    # Pad with more repeats
                    band_text = "   ".join(text_list * 10)
                    result = self.render(band_text)
                
                rendered_bands.append(result)
            
            return rendered_bands
            
        except Exception as e:
            print(f"Error rendering subtext: {e}")
            return []
        finally:
            # Restore original style
            self.set_style(original_style)
    
    def render_small_subtext(
        self,
        text: str,
        color: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[RenderedText]:
        """Render small subtext for corner positioning.
        
        This is Trance's small subtext layer - small text positioned
        at screen corners/edges. Used by SubTextVisual for secondary text.
        
        Args:
            text: Text string to render
            color: RGBA color (None = use current style)
        
        Returns:
            RenderedText or None
        """
        if not text.strip():
            return None
        
        # Save current style
        original_style = self._style
        
        try:
            # Create style for small subtext
            small_style = TextStyle(
                font_path=original_style.font_path,
                font_size=18,
                color=color if color else (200, 200, 200, 180)
            )
            self.set_style(small_style)
            
            # Render text
            result = self.render(text)
            
            return result
            
        except Exception as e:
            print(f"Error rendering small subtext: {e}")
            return None
        finally:
            # Restore original style
            self.set_style(original_style)
