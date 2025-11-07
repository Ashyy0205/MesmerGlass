"""Tests for theme and media loading."""

import pytest
from pathlib import Path
import json
import tempfile
import numpy as np

from mesmerglass.content.theme import (
    ThemeConfig, ThemeCollection, Shuffler,
    load_theme_collection, save_theme_collection
)
from mesmerglass.content.media import ImageData


class TestThemeConfig:
    def test_create_theme(self):
        """Test creating theme config."""
        theme = ThemeConfig(
            name="test",
            enabled=True,
            image_path=["img1.jpg", "img2.png"],
            text_line=["Hello", "World"]
        )
        assert theme.name == "test"
        assert theme.enabled == True
        assert len(theme.image_path) == 2
        assert len(theme.text_line) == 2
    
    def test_validate_theme(self):
        """Test theme validation."""
        theme = ThemeConfig(name="test")
        theme.validate()  # Should not raise
        
        # Invalid name
        with pytest.raises(ValueError, match="name must be non-empty"):
            ThemeConfig(name="").validate()
    
    def test_from_dict(self):
        """Test creating theme from dictionary."""
        data = {
            "name": "my_theme",
            "enabled": True,
            "image_path": ["a.jpg", "b.png"],
            "font_path": ["font.ttf"],
            "text_line": ["Text 1", "Text 2"]
        }
        theme = ThemeConfig.from_dict(data)
        assert theme.name == "my_theme"
        assert len(theme.image_path) == 2
        assert len(theme.text_line) == 2
    
    def test_to_dict(self):
        """Test converting theme to dictionary."""
        theme = ThemeConfig(
            name="test",
            image_path=["img.jpg"],
            text_line=["Hello"]
        )
        data = theme.to_dict()
        assert data["name"] == "test"
        assert data["image_path"] == ["img.jpg"]
        assert data["text_line"] == ["Hello"]


class TestThemeCollection:
    def test_create_collection(self):
        """Test creating theme collection."""
        themes = [
            ThemeConfig(name="theme1"),
            ThemeConfig(name="theme2")
        ]
        collection = ThemeCollection(themes=themes)
        assert len(collection.themes) == 2
    
    def test_from_dict_trance_format(self):
        """Test loading Trance format (theme_map)."""
        data = {
            "theme_map": {
                "theme1": {
                    "enabled": True,
                    "image_path": ["img1.jpg"],
                    "text_line": ["Text 1"]
                },
                "theme2": {
                    "enabled": False,
                    "image_path": ["img2.jpg"],
                    "text_line": ["Text 2"]
                }
            }
        }
        collection = ThemeCollection.from_dict(data)
        assert len(collection.themes) == 2
        assert collection.themes[0].name == "theme1"
        assert collection.themes[1].name == "theme2"
    
    def test_from_dict_direct_format(self):
        """Test loading direct format (themes list)."""
        data = {
            "themes": [
                {"name": "theme1", "enabled": True},
                {"name": "theme2", "enabled": False}
            ]
        }
        collection = ThemeCollection.from_dict(data)
        assert len(collection.themes) == 2
    
    def test_get_enabled_themes(self):
        """Test filtering enabled themes."""
        themes = [
            ThemeConfig(name="theme1", enabled=True),
            ThemeConfig(name="theme2", enabled=False),
            ThemeConfig(name="theme3", enabled=True)
        ]
        collection = ThemeCollection(themes=themes)
        enabled = collection.get_enabled_themes()
        assert len(enabled) == 2
        assert enabled[0].name == "theme1"
        assert enabled[1].name == "theme3"
    
    def test_save_and_load(self):
        """Test saving and loading theme collection."""
        themes = [
            ThemeConfig(
                name="test_theme",
                enabled=True,
                image_path=["img1.jpg", "img2.png"],
                text_line=["Hello", "World"]
            )
        ]
        collection = ThemeCollection(themes=themes)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            # Save
            save_theme_collection(collection, temp_path)
            
            # Load
            loaded = load_theme_collection(temp_path)
            assert len(loaded.themes) == 1
            assert loaded.themes[0].name == "test_theme"
            assert len(loaded.themes[0].image_path) == 2
            assert len(loaded.themes[0].text_line) == 2
        finally:
            temp_path.unlink()


class TestShuffler:
    def test_create_shuffler(self):
        """Test creating shuffler."""
        shuffler = Shuffler(count=10)
        assert shuffler._count == 10
        assert len(shuffler._weights) == 10
    
    def test_next(self):
        """Test weighted random selection."""
        shuffler = Shuffler(count=5)
        
        # Should return valid index
        for _ in range(20):
            idx = shuffler.next()
            assert 0 <= idx < 5
    
    def test_increase_decrease(self):
        """Test weight adjustment."""
        shuffler = Shuffler(count=5, default_weight=1.0)
        
        # Decrease weight
        shuffler.decrease(2, amount=0.5)
        assert shuffler._weights[2] == 0.5
        
        # Increase weight  
        shuffler.increase(3, amount=2.0)
        assert shuffler._weights[3] == 3.0
        
        # Decrease to zero
        shuffler.decrease(2, amount=1.0)
        assert shuffler._weights[2] == 0.0
    
    def test_weighted_selection(self):
        """Test that higher weights increase selection probability."""
        shuffler = Shuffler(count=3, default_weight=1.0)
        
        # Make index 1 much more likely
        shuffler.increase(1, amount=100.0)
        
        # Run many selections
        counts = [0, 0, 0]
        for _ in range(1000):
            idx = shuffler.next()
            counts[idx] += 1
        
        # Index 1 should be selected most often
        assert counts[1] > counts[0]
        assert counts[1] > counts[2]
    
    def test_reset(self):
        """Test weight reset."""
        shuffler = Shuffler(count=5, default_weight=2.0)
        
        shuffler.decrease(0, amount=1.0)
        shuffler.increase(2, amount=3.0)
        
        shuffler.reset()
        
        # All weights should be back to default
        assert all(w == 2.0 for w in shuffler._weights)


class TestImageData:
    def test_create_image_data(self):
        """Test creating image data."""
        data = np.zeros((100, 200, 4), dtype=np.uint8)
        img = ImageData(
            width=200,
            height=100,
            data=data,
            path=Path("test.jpg")
        )
        assert img.width == 200
        assert img.height == 100
        assert img.data.shape == (100, 200, 4)
    
    def test_validate_dtype(self):
        """Test that non-uint8 raises error."""
        data = np.zeros((100, 200, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="must be uint8"):
            ImageData(width=200, height=100, data=data, path=Path("test.jpg"))
    
    def test_validate_shape(self):
        """Test that wrong shape raises error."""
        # Wrong number of channels
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="must be.*RGBA"):
            ImageData(width=200, height=100, data=data, path=Path("test.jpg"))
        
        # Wrong dimensions
        data = np.zeros((100, 200, 4), dtype=np.uint8)
        with pytest.raises(ValueError, match="shape mismatch"):
            ImageData(width=999, height=100, data=data, path=Path("test.jpg"))
