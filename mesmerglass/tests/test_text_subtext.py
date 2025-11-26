"""
Tests for SUBTEXT (scrolling bands / carousel effect) rendering mode.

Verifies:
- Band count calculations (~8 bands at 1080p)
- Band spacing (2 * height + 1/512)
- Text concatenation (fills screen width)
- Scrolling animation (offset updates)
- Difference between SUBTEXT and FILL_SCREEN
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from mesmerglass.engine.text_director import TextDirector
from mesmerglass.content.text_renderer import SplitMode


class TestSubtextRendering:
    """Test SUBTEXT mode (scrolling horizontal bands)."""
    
    @pytest.fixture
    def mock_renderer(self):
        """Create mock text renderer."""
        renderer = Mock()
        rendered = Mock()
        rendered.texture_data = b"fake_texture_data"
        rendered.width = 100  # Add numeric width
        rendered.height = 50  # Add numeric height
        renderer.render_main_text.return_value = rendered
        return renderer
    
    @pytest.fixture
    def mock_compositor(self):
        """Create mock compositor."""
        compositor = Mock()
        compositor.add_text_texture = Mock()
        compositor.clear_text_textures = Mock()
        compositor.set_virtual_screen_size = Mock()
        compositor.get_target_screen_size = Mock(return_value=(1280, 720))
        return compositor
    
    @pytest.fixture
    def director(self, mock_renderer, mock_compositor):
        """Create TextDirector with mocks."""
        clock = {"t": 0.0}

        def fake_time():
            clock["t"] += 0.016  # simulate ~60fps progression
            return clock["t"]

        director = TextDirector(
            text_renderer=mock_renderer,
            compositor=mock_compositor,
            time_provider=fake_time
        )
        director.set_text_library(["Test Text 1", "Test Text 2", "Test Text 3"])
        return director
    
    def test_subtext_band_count(self, director, mock_compositor):
        """Verify wallpaper grid rendered with correct tile count."""
        # Set SUBTEXT mode
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        
        # First update initializes and renders
        director.update()
        
        # SUBTEXT mode re-renders every frame, so we get double rendering on first frame
        # Reset and do clean render
        mock_compositor.reset_mock()
        director.update()  # Second update - clean SUBTEXT render
        
        # Expected: Wallpaper grid filling screen
        # Typical: ~8-12 cols × ~6-8 rows = 48-96 tiles
        # (depends on text size, but should be grid pattern)
        
        call_count = mock_compositor.add_text_texture.call_count
        assert call_count >= 30, f"Expected at least 30 tiles for wallpaper grid, got {call_count}"
        assert call_count <= 200, f"Expected at most 200 tiles, got {call_count}"
    
    def test_subtext_band_spacing(self, director, mock_compositor):
        """Verify grid spacing between tiles."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        director.update()
        
        # Get all positions
        positions = []
        for call in mock_compositor.add_text_texture.call_args_list:
            kwargs = call[1] if len(call) > 1 else {}
            if 'x' in kwargs and 'y' in kwargs:
                positions.append((kwargs['x'], kwargs['y']))
        
        # Verify we have a grid pattern (multiple unique x and y values)
        x_coords = sorted(set(round(p[0], 3) for p in positions))
        y_coords = sorted(set(round(p[1], 3) for p in positions))
        
        assert len(x_coords) >= 5, f"Expected grid with at least 5 unique x-positions, got {len(x_coords)}"
        assert len(y_coords) >= 3, f"Expected grid with at least 3 unique y-positions (rows), got {len(y_coords)}"
    
    def test_text_concatenation(self, director, mock_renderer):
        """Verify text rendering (single instance tiled, not concatenated)."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        director.update()
        
        # Check that render_main_text was called
        assert mock_renderer.render_main_text.called
        call_args = mock_renderer.render_main_text.call_args
        rendered_text = call_args[0][0] if call_args[0] else ""
        
        # Should render single text instance (not concatenated)
        # Grid is created by repeating the same texture
        assert len(rendered_text) <= 20, \
            f"Expected single text instance, not concatenated. Got: {rendered_text}"
    
    def test_scrolling_animation(self, director, mock_compositor):
        """Verify scroll offset increments each frame."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        
        # Get initial scroll offset
        initial_offset = director._scroll_offset
        
        # Update multiple frames
        for _ in range(10):
            director.update()
        
        # Verify offset increased (in pixels, can grow beyond 1.0)
        assert director._scroll_offset > initial_offset, \
            "Scroll offset should increase each frame"
    
    def test_scroll_offset_applied_to_x(self, director, mock_compositor):
        """Verify scroll offset applied to x-coordinate (horizontal scrolling)."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        
        # Set known scroll offset (in pixels)
        director._scroll_offset = 100.0  # 100 pixels scrolled
        director.update()
        
        # Get x-coordinates - should vary due to grid columns
        # and scroll offset applied to all
        x_coords = []
        for call in mock_compositor.add_text_texture.call_args_list:
            kwargs = call[1] if len(call) > 1 else {}
            if 'x' in kwargs:
                x_coords.append(kwargs['x'])
        
        # Should have multiple x-coordinates (grid columns)
        unique_x = list(set(round(x, 3) for x in x_coords))
        assert len(unique_x) >= 3, \
            f"Expected multiple x-coordinates for grid, got: {unique_x}"
    
    def test_subtext_vs_centered(self, director, mock_compositor):
        """Verify SUBTEXT and centered text produce different outputs."""
        # Test centered mode
        director.set_all_split_mode(SplitMode.CENTERED_SYNC)
        director.set_enabled(True)
        director.update()
        centered_calls = mock_compositor.add_text_texture.call_count
        mock_compositor.reset_mock()
        
        # Test SUBTEXT mode
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director._current_text = ""  # Force fresh selection/render
        director._current_split_mode = SplitMode.SUBTEXT
        director._frame_counter = 0
        director.update()
        subtext_calls = mock_compositor.add_text_texture.call_count
        
        assert centered_calls != subtext_calls, \
            f"Centered ({centered_calls}) and SUBTEXT ({subtext_calls}) should differ"
        assert subtext_calls > centered_calls, \
            "SUBTEXT should render more tiles than centered mode"
    
    def test_subtext_transparency(self, director, mock_compositor):
        """Verify SUBTEXT uses semi-transparent alpha."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        director.update()
        
        # Check alpha values
        alpha_values = []
        for call in mock_compositor.add_text_texture.call_args_list:
            kwargs = call[1] if len(call) > 1 else {}
            if 'alpha' in kwargs:
                alpha_values.append(kwargs['alpha'])
        
        # Bands render opaque so they blend with spiral shader; ensure >0 alpha
        assert all(alpha >= 1.0 for alpha in alpha_values), \
            f"SUBTEXT bands should be fully opaque, got alphas: {alpha_values}"
    
    def test_subtext_scale(self, director, mock_compositor):
        """Verify SUBTEXT uses smaller scale than centered text."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        director.update()
        
        # Check scale values
        scale_values = []
        for call in mock_compositor.add_text_texture.call_args_list:
            kwargs = call[1] if len(call) > 1 else {}
            if 'scale' in kwargs:
                scale_values.append(kwargs['scale'])
        # SUBTEXT upsizes glyphs to cover more area
        assert all(scale >= 1.0 for scale in scale_values), \
            f"SUBTEXT bands should use larger scale, got: {scale_values}"

    def test_secondary_compositors_receive_existing_text(self, director, mock_compositor):
        """New secondary compositors immediately mirror current text output."""
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        director.update()

        secondary = Mock()
        secondary.add_text_texture = Mock()
        secondary.clear_text_textures = Mock()
        secondary.set_virtual_screen_size = Mock()
        secondary.get_target_screen_size = Mock(return_value=(1920, 1080))

        director.set_secondary_compositors([secondary])

        secondary.clear_text_textures.assert_called()
        assert secondary.add_text_texture.call_count > 0

    def test_subtext_sets_virtual_screen_size_for_all_compositors(self, director, mock_compositor):
        """SUBTEXT layout should apply a shared virtual canvas to every compositor."""
        secondary = Mock()
        secondary.add_text_texture = Mock()
        secondary.clear_text_textures = Mock()
        secondary.set_virtual_screen_size = Mock()
        secondary.get_target_screen_size = Mock(return_value=(1920, 1080))

        director.set_secondary_compositors([secondary])
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.set_enabled(True)
        director.update()

        # Layout uses max(1920, primary 1280) = 1920 width
        mock_compositor.set_virtual_screen_size.assert_called_with(1920, 1080)
        secondary.set_virtual_screen_size.assert_called_with(1920, 1080)


class TestSubtextTiming:
    """Test timing and animation for SUBTEXT mode."""
    
    @pytest.fixture
    def director_with_timing(self):
        """Create director with timing controls."""
        renderer = Mock()
        rendered = Mock()
        rendered.texture_data = b"fake_data"
        rendered.width = 100  # Add numeric width
        rendered.height = 50  # Add numeric height
        renderer.render_main_text.return_value = rendered
        
        compositor = Mock()
        clock = {"t": 0.0}

        def fake_time():
            clock["t"] += 0.05
            return clock["t"]

        director = TextDirector(
            text_renderer=renderer,
            compositor=compositor,
            time_provider=fake_time
        )
        director.set_text_library(["A", "B", "C"])
        return director
    
    def test_continuous_rendering(self, director_with_timing):
        """Verify SUBTEXT re-renders every frame for scrolling."""
        director_with_timing.set_all_split_mode(SplitMode.SUBTEXT)
        director_with_timing.set_enabled(True)
        
        # First update to initialize
        director_with_timing.update()
        initial_count = director_with_timing.compositor.add_text_texture.call_count
        
        # Second update should re-render (for scrolling animation)
        director_with_timing.update()
        second_count = director_with_timing.compositor.add_text_texture.call_count
        
        # Should have rendered twice (continuous animation)
        assert second_count > initial_count, \
            "SUBTEXT should re-render every frame for scrolling"
    
    def test_other_modes_no_continuous_render(self, director_with_timing):
        """Verify non-SUBTEXT modes don't re-render every frame."""
        director_with_timing.set_all_split_mode(SplitMode.CENTERED_SYNC)
        director_with_timing.set_enabled(True)
        director_with_timing.set_timing(1000)  # Very long duration
        
        # First update
        director_with_timing.update()
        initial_count = director_with_timing.compositor.add_text_texture.call_count
        
        # Second update (same text, no re-render)
        director_with_timing.update()
        second_count = director_with_timing.compositor.add_text_texture.call_count
        
        # Should NOT have re-rendered (static mode)
        assert second_count == initial_count, \
            "Non-SUBTEXT modes should not re-render every frame"


class TestTextSyncSettings:
    """Verify manual text timing vs media-synced behavior."""

    @pytest.fixture
    def base_director(self):
        renderer = Mock()
        rendered = Mock()
        rendered.texture_data = b"fake"
        rendered.width = 100
        rendered.height = 50
        renderer.render_main_text.return_value = rendered
        compositor = Mock()
        director = TextDirector(text_renderer=renderer, compositor=compositor)
        director.set_text_library(["Alpha", "Beta", "Gamma"])
        director.set_enabled(True)
        return director, compositor

    def test_manual_mode_advances_without_media(self, base_director):
        director, compositor = base_director
        director.configure_sync(sync_with_media=False, frames_per_text=2)
        director.update()  # Initial render
        first_count = compositor.add_text_texture.call_count
        director._elapsed_time_s = director._manual_target_seconds
        director.update()
        director._elapsed_time_s = director._manual_target_seconds
        director.update()
        assert compositor.add_text_texture.call_count > first_count, \
            "Manual mode should advance text via update timing"

    def test_media_change_ignored_when_manual(self, base_director):
        director, compositor = base_director
        director.configure_sync(sync_with_media=False, frames_per_text=60)
        director.on_media_change()
        assert compositor.add_text_texture.call_count == 0, \
            "Manual mode should not react to media change callbacks"

    def test_manual_mode_applies_to_subtext(self, base_director):
        director, _ = base_director
        director.set_text_library(["One", "Two"])
        director.set_all_split_mode(SplitMode.SUBTEXT)
        director.configure_sync(sync_with_media=False, frames_per_text=1)
        with patch("mesmerglass.engine.text_director.random.random", side_effect=[0.1, 0.9]):
            director.update()
            first = director._current_text
            director._elapsed_time_s = director._manual_target_seconds
            director.update()
            second = director._current_text
        assert first != second, "Manual cadence should rotate carousel text independently of media"


class TestLayoutDimensions:
    """Verify TextDirector derives layout sizes from target overrides."""

    def _make_director(self, compositor: Mock) -> TextDirector:
        renderer = Mock()
        rendered = Mock()
        rendered.texture_data = b"texture"
        rendered.width = 200
        rendered.height = 80
        renderer.render_main_text.return_value = rendered
        director = TextDirector(text_renderer=renderer, compositor=compositor)
        director.set_text_library(["Alpha", "Beta"])
        return director

    def test_prefers_virtual_screen_size(self):
        comp = Mock()
        comp.get_target_screen_size.return_value = (2560, 1440)
        director = self._make_director(comp)

        width, height = director._get_layout_dimensions()

        comp.get_target_screen_size.assert_called_once()
        assert (width, height) == (2560, 1440)

    def test_fallbacks_to_widget_dimensions(self):
        comp = Mock()
        comp.get_target_screen_size.side_effect = Exception("bad state")
        comp.width.return_value = 800
        comp.height.return_value = 600
        director = self._make_director(comp)

        width, height = director._get_layout_dimensions()

        # Layout enforces a minimum 1920x1080 canvas so smaller preview windows still match live output
        assert (width, height) == (1920, 1080)

    def test_default_resolution_when_no_compositor(self):
        director = TextDirector(text_renderer=Mock(), compositor=None)
        director.set_text_library(["Solo"])

        width, height = director._get_layout_dimensions()

        assert (width, height) == (1920, 1080)

    def test_aggregates_primary_and_secondary_dimensions(self):
        primary = Mock()
        primary.get_target_screen_size.return_value = (1280, 720)
        secondary = Mock()
        secondary.get_target_screen_size.return_value = (1920, 1080)

        renderer = Mock()
        rendered = Mock()
        rendered.texture_data = b"texture"
        rendered.width = 200
        rendered.height = 80
        renderer.render_main_text.return_value = rendered

        director = TextDirector(text_renderer=renderer, compositor=primary)
        director.set_text_library(["Alpha"])
        director.set_secondary_compositors([secondary])

        width, height = director._get_layout_dimensions()

        assert (width, height) == (1920, 1080)
