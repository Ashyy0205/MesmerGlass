"""Theme configuration and media management.

Implements Trance-style theme system:
- Multiple themes with images, videos, fonts, text
- Weighted shuffler to avoid repetition
- Async image/video loading
- GPU texture caching
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import random


@dataclass(slots=True)
class ThemeConfig:
    """Single theme configuration matching Trance format.
    
    Corresponds to trance_pb::Theme proto:
    - image_path: List of relative paths to images
    - animation_path: List of relative paths to videos/animations
    - font_path: List of relative paths to fonts
    - text_line: List of text strings to display
    """
    name: str
    enabled: bool = True
    image_path: List[str] = field(default_factory=list)
    animation_path: List[str] = field(default_factory=list) 
    font_path: List[str] = field(default_factory=list)
    text_line: List[str] = field(default_factory=list)
    
    def validate(self) -> None:
        """Validate theme configuration."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Theme name must be non-empty string")
        if not isinstance(self.enabled, bool):
            raise ValueError("Theme enabled must be boolean")
        if not isinstance(self.image_path, list):
            raise ValueError("Theme image_path must be list")
        if not isinstance(self.animation_path, list):
            raise ValueError("Theme animation_path must be list")
        if not isinstance(self.font_path, list):
            raise ValueError("Theme font_path must be list")
        if not isinstance(self.text_line, list):
            raise ValueError("Theme text_line must be list")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ThemeConfig:
        """Build ThemeConfig from dictionary."""
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            image_path=data.get("image_path", []),
            animation_path=data.get("animation_path", []),
            font_path=data.get("font_path", []),
            text_line=data.get("text_line", [])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "image_path": self.image_path,
            "animation_path": self.animation_path,
            "font_path": self.font_path,
            "text_line": self.text_line
        }


@dataclass(slots=True)
class ThemeCollection:
    """Collection of themes matching Trance session format."""
    themes: List[ThemeConfig] = field(default_factory=list)
    root_path: Path = field(default_factory=Path)
    
    def validate(self) -> None:
        """Validate all themes."""
        for theme in self.themes:
            theme.validate()
    
    def get_enabled_themes(self) -> List[ThemeConfig]:
        """Get list of enabled themes."""
        return [t for t in self.themes if t.enabled]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], root_path: Optional[Path] = None) -> ThemeCollection:
        """Build ThemeCollection from dictionary.
        
        Supports two formats:
        1. Trance format: {"theme_map": {"name1": {...}, "name2": {...}}}
        2. Direct format: {"themes": [{...}, {...}]}
        """
        root = root_path or Path(".")
        
        # Try Trance format first
        if "theme_map" in data:
            theme_map = data["theme_map"]
            if not isinstance(theme_map, dict):
                raise ValueError("theme_map must be a dictionary")
            themes = []
            for name, theme_data in theme_map.items():
                if not isinstance(theme_data, dict):
                    raise ValueError(f"Theme '{name}' data must be dictionary")
                # Add name to theme data
                theme_data["name"] = name
                themes.append(ThemeConfig.from_dict(theme_data))
            return cls(themes=themes, root_path=root)
        
        # Try direct format
        if "themes" in data:
            theme_list = data["themes"]
            if not isinstance(theme_list, list):
                raise ValueError("themes must be a list")
            themes = [ThemeConfig.from_dict(t) for t in theme_list]
            return cls(themes=themes, root_path=root)
        
        raise ValueError("Theme data must have 'theme_map' or 'themes' key")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary in Trance format."""
        theme_map = {t.name: t.to_dict() for t in self.themes}
        return {"theme_map": theme_map}


class Shuffler:
    """Weighted random shuffler that avoids repetition.
    
    Implements Trance Shuffler algorithm:
    - Each item has a weight (default 1.0)
    - increase(index) raises weight
    - decrease(index) lowers weight  
    - next() returns weighted random index
    
    Used to avoid selecting same images repeatedly.
    """
    
    def __init__(self, count: int, default_weight: float = 1.0):
        """Initialize shuffler with count items.
        
        Args:
            count: Number of items to shuffle
            default_weight: Initial weight for all items
        """
        self._count = count
        self._weights = [default_weight] * count
        self._default_weight = default_weight
    
    def next(self) -> int:
        """Return weighted random index.
        
        Returns:
            Random index in [0, count) based on weights
        """
        if self._count == 0:
            raise ValueError("Shuffler is empty")
        
        # If all weights are 0, reset to defaults
        if all(w == 0 for w in self._weights):
            self._weights = [self._default_weight] * self._count
        
        # Weighted random selection
        total = sum(self._weights)
        if total <= 0:
            # Fallback to uniform
            return random.randrange(self._count)
        
        r = random.uniform(0, total)
        cumulative = 0.0
        for i, weight in enumerate(self._weights):
            cumulative += weight
            if r < cumulative:
                return i
        
        # Should never reach here, but return last as fallback
        return self._count - 1
    
    def increase(self, index: int, amount: float = 1.0) -> None:
        """Increase weight of item at index.
        
        Args:
            index: Item index to increase
            amount: Amount to add to weight
        """
        if 0 <= index < self._count:
            self._weights[index] += amount
    
    def decrease(self, index: int, amount: float = 1.0) -> None:
        """Decrease weight of item at index.
        
        Args:
            index: Item index to decrease
            amount: Amount to subtract from weight (clamped to 0)
        """
        if 0 <= index < self._count:
            self._weights[index] = max(0.0, self._weights[index] - amount)
    
    def reset(self) -> None:
        """Reset all weights to default."""
        self._weights = [self._default_weight] * self._count


def load_theme_collection(path: Path, root_path: Optional[Path] = None) -> ThemeCollection:
    """Load theme collection from JSON file.
    
    Args:
        path: Path to theme JSON file
        root_path: Root directory for resolving relative paths
    
    Returns:
        ThemeCollection instance
    
    Raises:
        ValueError: If file not found or invalid format
    """
    if not path.is_file():
        raise ValueError(f"Theme file not found: {path}")
    
    try:
        raw = path.read_text(encoding="utf-8-sig")
        if raw.startswith("\ufeff"):
            raw = raw.lstrip("\ufeff")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e.msg} (line {e.lineno})") from None
    
    if not isinstance(data, dict):
        raise ValueError("Theme file must contain JSON object")
    
    collection = ThemeCollection.from_dict(data, root_path or path.parent)
    collection.validate()
    return collection


def save_theme_collection(collection: ThemeCollection, path: Path) -> None:
    """Save theme collection to JSON file.
    
    Args:
        collection: ThemeCollection to save
        path: Output file path
    """
    collection.validate()
    data = collection.to_dict()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
