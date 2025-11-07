"""Unit tests for TextRenderer (Phase 3.1)."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from PIL import Image, ImageFont

from ..content.text_renderer import TextRenderer, TextStyle, SplitMode, RenderedText


@pytest.fixture
def text_renderer():
    """Create a TextRenderer instance for testing."""
    return TextRenderer()


@pytest.fixture
def custom_style():
    """Create a custom TextStyle for testing."""
    return TextStyle(
        font_size=100,
        color=(255, 0, 0, 200),
        outline_width=2,
        shadow_offset=(2, 2)
    )


class TestTextRendererInit:
    """Test TextRenderer initialization."""
    
    def test_init_creates_default_style(self, text_renderer):
        """Test default style initialization."""
        assert text_renderer._style is not None
        assert text_renderer._style.font_size == 48
        assert text_renderer._style.color == (255, 255, 255, 255)
    
    def test_init_loads_font(self, text_renderer):
        """Test that font is loaded on initialization."""
        assert text_renderer._current_font is not None


class TestTextStyleDataclass:
    """Test TextStyle dataclass."""
    
    def test_text_style_default_values(self):
        """Test default TextStyle values."""
        style = TextStyle()
        assert style.font_size == 48
        assert style.color == (255, 255, 255, 255)
        assert style.outline_width == 0
        assert style.shadow_offset == (0, 0)
        assert style.line_spacing == 1.2
    
    def test_text_style_custom_values(self, custom_style):
        """Test custom TextStyle values."""
        assert custom_style.font_size == 100
        assert custom_style.color == (255, 0, 0, 200)
        assert custom_style.outline_width == 2
        assert custom_style.shadow_offset == (2, 2)


class TestStyleManagement:
    """Test style setting and management."""
    
    def test_set_style(self, text_renderer, custom_style):
        """Test setting a custom style."""
        text_renderer.set_style(custom_style)
        assert text_renderer._style == custom_style
        assert text_renderer._style.font_size == 100
    
    def test_get_style(self, text_renderer):
        """Test getting current style."""
        style = text_renderer.get_style()
        assert isinstance(style, TextStyle)
        assert style.font_size == 48  # Default


class TestTextRendering:
    """Test text rendering to texture."""
    
    def test_render_simple_text(self, text_renderer):
        """Test rendering simple text."""
        result = text_renderer.render("HELLO")
        
        assert isinstance(result, RenderedText)
        assert result.text == "HELLO"
        assert result.texture_data is not None
        assert isinstance(result.texture_data, np.ndarray)
        assert result.texture_data.shape[2] == 4  # RGBA
        assert result.width > 0
        assert result.height > 0
    
    def test_render_empty_text(self, text_renderer):
        """Test rendering empty text."""
        result = text_renderer.render("")
        
        assert isinstance(result, RenderedText)
        assert result.text == ""
        assert result.texture_data is not None
    
    def test_render_multiline_text(self, text_renderer):
        """Test rendering multiline text."""
        result = text_renderer.render("LINE1\nLINE2")
        
        assert isinstance(result, RenderedText)
        assert "LINE1" in result.text or "LINE2" in result.text or result.text == "LINE1\nLINE2"


class TestSplitModes:
    """Test different split modes."""
    
    def test_split_mode_none(self, text_renderer):
        """Test NONE mode returns single element."""
        result = text_renderer.render_split("HELLO WORLD", SplitMode.NONE)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].text == "HELLO WORLD"
    
    def test_split_mode_word(self, text_renderer):
        """Test SPLIT_WORD mode splits by words."""
        result = text_renderer.render_split("HELLO WORLD TEST", SplitMode.SPLIT_WORD)
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0].text == "HELLO"
        assert result[1].text == "WORLD"
        assert result[2].text == "TEST"
    
    def test_split_mode_word_gaps(self, text_renderer):
        """Test SPLIT_WORD_GAPS mode."""
        result = text_renderer.render_split("HELLO WORLD", SplitMode.SPLIT_WORD_GAPS)
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].text == "HELLO"
        assert result[1].text == "WORLD"
    
    def test_split_mode_line(self, text_renderer):
        """Test SPLIT_LINE mode splits by newlines."""
        result = text_renderer.render_split("LINE1\nLINE2\nLINE3", SplitMode.SPLIT_LINE)
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0].text == "LINE1"
        assert result[1].text == "LINE2"
        assert result[2].text == "LINE3"
    
    def test_split_mode_line_gaps(self, text_renderer):
        """Test SPLIT_LINE_GAPS mode."""
        result = text_renderer.render_split("LINE1\nLINE2", SplitMode.SPLIT_LINE_GAPS)
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].text == "LINE1"
        assert result[1].text == "LINE2"
    
    def test_split_mode_character(self, text_renderer):
        """Test CHARACTER mode splits by characters."""
        result = text_renderer.render_split("ABC", SplitMode.CHARACTER)
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0].text == "A"
        assert result[1].text == "B"
        assert result[2].text == "C"
    
    def test_split_mode_fill_screen(self, text_renderer):
        """Test FILL_SCREEN mode returns single element."""
        result = text_renderer.render_split("REPEAT TEXT", SplitMode.FILL_SCREEN)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].text == "REPEAT TEXT"


class TestTextureGeneration:
    """Test texture data generation."""
    
    def test_texture_is_rgba(self, text_renderer):
        """Test generated texture is RGBA format."""
        result = text_renderer.render("TEST")
        
        assert result.texture_data.shape[2] == 4  # RGBA channels
        assert result.texture_data.dtype == np.uint8
    
    def test_texture_has_dimensions(self, text_renderer):
        """Test texture has width and height."""
        result = text_renderer.render("TEST")
        
        assert result.width > 0
        assert result.height > 0
        assert result.texture_data.shape[1] == result.width
        assert result.texture_data.shape[0] == result.height
    
    def test_texture_auto_cropping(self, text_renderer):
        """Test texture is auto-cropped to content bounds."""
        result = text_renderer.render("X")
        
        # Texture should be cropped to actual content
        assert result.texture_data is not None
        # Check that there are some non-transparent pixels
        alpha_channel = result.texture_data[:, :, 3]
        assert np.any(alpha_channel > 0)
    
    def test_texture_has_baseline(self, text_renderer):
        """Test texture includes baseline information."""
        result = text_renderer.render("TEST")
        assert result.baseline >= 0


class TestRenderedTextDataclass:
    """Test RenderedText dataclass."""
    
    def test_rendered_text_creation(self):
        """Test creating RenderedText instance."""
        texture_data = np.zeros((100, 200, 4), dtype=np.uint8)
        rendered = RenderedText(
            text="TEST",
            texture_data=texture_data,
            width=200,
            height=100,
            baseline=0
        )
        
        assert rendered.text == "TEST"
        assert rendered.width == 200
        assert rendered.height == 100
        assert rendered.baseline == 0
        assert rendered.texture_data.shape == (100, 200, 4)


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_render_whitespace_only(self, text_renderer):
        """Test rendering whitespace-only text."""
        result = text_renderer.render("   ")
        
        # Should handle whitespace gracefully
        assert isinstance(result, RenderedText)
        assert result.texture_data is not None
    
    def test_render_special_characters(self, text_renderer):
        """Test rendering special characters."""
        result = text_renderer.render("!@#$%^&*()")
        
        assert isinstance(result, RenderedText)
        assert result.text == "!@#$%^&*()"
    
    def test_render_very_long_text(self, text_renderer):
        """Test rendering very long text."""
        long_text = "WORD " * 100
        
        result = text_renderer.render_split(long_text, SplitMode.SPLIT_WORD)
        
        assert isinstance(result, list)
        assert len(result) == 100
    
    def test_multiple_consecutive_spaces(self, text_renderer):
        """Test handling multiple consecutive spaces in word split."""
        result = text_renderer.render_split("HELLO    WORLD", SplitMode.SPLIT_WORD)
        
        # Should filter out empty strings from split
        assert all(r.text.strip() for r in result)  # No empty strings
    
    def test_multiple_consecutive_newlines(self, text_renderer):
        """Test handling multiple consecutive newlines in line split."""
        result = text_renderer.render_split("LINE1\n\n\nLINE2", SplitMode.SPLIT_LINE)
        
        # Should filter out empty strings from split
        assert all(r.text.strip() for r in result)  # No empty strings


class TestStyleEffects:
    """Test style effects like outline and shadow."""
    
    def test_outline_effect(self, text_renderer):
        """Test rendering with outline."""
        style = TextStyle(outline_width=2, outline_color=(0, 0, 0, 255))
        text_renderer.set_style(style)
        
        result = text_renderer.render("TEST")
        assert result.texture_data is not None
    
    def test_shadow_effect(self, text_renderer):
        """Test rendering with shadow."""
        style = TextStyle(shadow_offset=(2, 2), shadow_blur=1)
        text_renderer.set_style(style)
        
        result = text_renderer.render("TEST")
        assert result.texture_data is not None
    
    def test_combined_effects(self, text_renderer):
        """Test rendering with multiple effects."""
        style = TextStyle(
            outline_width=1,
            shadow_offset=(2, 2),
            shadow_blur=1
        )
        text_renderer.set_style(style)
        
        result = text_renderer.render("TEST")
        assert result.texture_data is not None


class TestMultilineRendering:
    """Test multiline text rendering."""
    
    def test_render_multiline(self, text_renderer):
        """Test rendering multiline text."""
        lines = ["LINE1", "LINE2", "LINE3"]
        result = text_renderer.render_multiline(lines)
        
        assert isinstance(result, RenderedText)
        assert result.width > 0
        assert result.height > 0
    
    def test_render_multiline_with_max_width(self, text_renderer):
        """Test rendering multiline with max width constraint."""
        lines = ["SHORT", "MEDIUM"]
        result = text_renderer.render_multiline(lines, max_width=500)
        
        assert isinstance(result, RenderedText)
        # Should still render even if constrained
        assert result.texture_data is not None


class TestFontCaching:
    """Test font loading and caching."""
    
    def test_font_cache_exists(self, text_renderer):
        """Test that font cache is initialized."""
        assert hasattr(text_renderer, '_font_cache')
        assert isinstance(text_renderer._font_cache, dict)
    
    def test_current_font_loaded(self, text_renderer):
        """Test that a font is loaded on init."""
        assert text_renderer._current_font is not None
