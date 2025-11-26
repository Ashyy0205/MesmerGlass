"""
Cuelist Data Model - Complete session definition.

A Cuelist is an ordered sequence of Cues that defines a complete hypnosis session.
Supports various playback modes (once, loop, ping-pong) and provides methods for
loading/saving JSON files and managing cue sequences.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
import json

from .cue import Cue


class CuelistLoopMode(Enum):
    """Playback mode for cuelist completion."""
    ONCE = "once"  # Play through once and stop
    LOOP = "loop"  # Loop back to first cue
    PING_PONG = "ping_pong"  # Reverse cue order and play back


class CuelistTransitionMode(Enum):
    """How to transition between cues in a cuelist."""
    SNAP = "snap"  # Instant change at next media cycle boundary
    FADE = "fade"  # Smooth fade over specified duration


@dataclass
class Cuelist:
    """
    Complete session definition with ordered sequence of cues.
    
    A Cuelist defines a full hypnosis session by sequencing multiple Cues.
    Each Cue can have different playback pools, audio tracks, and durations.
    
    Attributes:
        name: Display name for the cuelist
        description: Optional description of the session
        version: Cuelist format version (for future compatibility)
        author: Creator name (optional)
        cues: Ordered list of Cue objects
        loop_mode: How to handle cuelist completion
        metadata: Additional custom metadata (tags, difficulty, etc.)
    """
    name: str
    description: str = ""
    version: str = "1.0"
    author: str = ""
    cues: List[Cue] = field(default_factory=list)
    loop_mode: CuelistLoopMode = CuelistLoopMode.ONCE
    transition_mode: CuelistTransitionMode = CuelistTransitionMode.SNAP
    transition_duration_ms: float = 2000.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def total_duration(self) -> float:
        """
        Calculate total duration of cuelist in seconds.
        
        Returns:
            Total duration (sum of all cue durations)
        """
        return sum(cue.duration_seconds for cue in self.cues)
    
    def get_cue(self, index: int) -> Optional[Cue]:
        """
        Get cue by index.
        
        Args:
            index: Cue index (0-based)
        
        Returns:
            Cue object or None if index out of range
        """
        if 0 <= index < len(self.cues):
            return self.cues[index]
        return None
    
    def add_cue(self, cue: Cue, position: Optional[int] = None) -> None:
        """
        Add a cue to the cuelist.
        
        Args:
            cue: Cue object to add
            position: Insert position (None = append to end)
        """
        if position is None:
            self.cues.append(cue)
        else:
            self.cues.insert(position, cue)
    
    def remove_cue(self, index: int) -> Optional[Cue]:
        """
        Remove cue by index.
        
        Args:
            index: Cue index to remove
        
        Returns:
            Removed Cue object or None if index invalid
        """
        if 0 <= index < len(self.cues):
            return self.cues.pop(index)
        return None
    
    def reorder_cues(self, new_order: List[int]) -> bool:
        """
        Reorder cues according to index list.
        
        Args:
            new_order: List of indices in desired order
        
        Returns:
            True if successful, False if invalid order
        """
        if len(new_order) != len(self.cues):
            return False
        
        if set(new_order) != set(range(len(self.cues))):
            return False
        
        self.cues = [self.cues[i] for i in new_order]
        return True
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate cuelist configuration.
        
        Returns:
            (is_valid, error_message)
        """
        # Validate name
        if not self.name or not self.name.strip():
            return False, "Cuelist name cannot be empty"
        
        # Validate cues list
        if not self.cues:
            return False, "Cuelist must contain at least one cue"
        
        # Validate each cue
        for i, cue in enumerate(self.cues):
            is_valid, msg = cue.validate()
            if not is_valid:
                return False, f"Cue {i} ('{cue.name}'): {msg}"
        
        # Check for duplicate cue names
        cue_names = [cue.name for cue in self.cues]
        if len(cue_names) != len(set(cue_names)):
            duplicates = [name for name in cue_names if cue_names.count(name) > 1]
            return False, f"Duplicate cue names found: {duplicates}"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize cuelist to JSON-compatible dict."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "loop_mode": self.loop_mode.value,
            "transition_mode": self.transition_mode.value,
            "transition_duration_ms": self.transition_duration_ms,
            "cues": [cue.to_dict() for cue in self.cues],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Cuelist:
        """Deserialize from dict."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            author=data.get("author", ""),
            cues=[Cue.from_dict(cue_data) for cue_data in data.get("cues", [])],
            loop_mode=CuelistLoopMode(data.get("loop_mode", "once")),
            transition_mode=CuelistTransitionMode(data.get("transition_mode", "snap")),
            transition_duration_ms=data.get("transition_duration_ms", 2000.0),
            metadata=data.get("metadata", {})
        )
    
    def save(self, path: Path) -> None:
        """
        Save cuelist to JSON file.
        
        Args:
            path: Output file path (typically .cuelist.json)
        
        Raises:
            ValueError: If cuelist validation fails
            IOError: If file cannot be written
        """
        # Validate before saving
        is_valid, msg = self.validate()
        if not is_valid:
            raise ValueError(f"Cannot save invalid cuelist: {msg}")
        
        # Ensure path is Path object
        path = Path(path)
        
        # Create parent directory if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON with pretty formatting
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> Cuelist:
        """
        Load cuelist from JSON file.
        
        Args:
            path: Path to cuelist JSON file
        
        Returns:
            Cuelist object
        
        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file contains invalid JSON
            ValueError: If cuelist validation fails
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Cuelist file not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cuelist = cls.from_dict(data)
        
        # Validate after loading
        is_valid, msg = cuelist.validate()
        if not is_valid:
            raise ValueError(f"Invalid cuelist in {path}: {msg}")
        
        return cuelist
