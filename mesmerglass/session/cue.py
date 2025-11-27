"""
Cue Data Models - Individual segments of a cuelist session.

A Cue represents a timed segment with:
- Playback pool (multiple playbacks with weights)
- Selection mode (when to switch playbacks)
- Audio tracks (up to 2)
- Transition effects (in/out)

All transitions are synchronized to media cycle boundaries for natural flow.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
import json


class PlaybackSelectionMode(Enum):
    """When to select a new playback from the pool."""
    ON_CUE_START = "on_cue_start"  # Select once at cue start
    ON_MEDIA_CYCLE = "on_media_cycle"  # Switch at each media cycle boundary
    ON_TIMED_INTERVAL = "on_timed_interval"  # Switch at fixed time intervals


class PlaybackSelectionAlgorithm(Enum):
    """How to select a playback from the pool."""
    WEIGHTED = "weighted"  # Weighted random selection based on entry.weight
    SEQUENTIAL = "sequential"  # Round-robin through pool
    SHUFFLE = "shuffle"  # Random selection with equal probability


@dataclass
class PlaybackEntry:
    """
    Entry in a playback pool with selection weight and duration constraints.
    
    Attributes:
        playback_path: Path to playback JSON file (relative or absolute)
        weight: Selection probability weight (higher = more likely)
        min_duration_s: Minimum duration in seconds before switch allowed (optional)
        max_duration_s: Maximum duration in seconds before forced switch (optional)
        min_cycles: DEPRECATED - use min_duration_s instead
        max_cycles: DEPRECATED - use max_duration_s instead
    """
    playback_path: Path
    weight: float = 1.0
    min_duration_s: Optional[float] = None
    max_duration_s: Optional[float] = None
    # Legacy fields for backward compatibility
    min_cycles: Optional[int] = None
    max_cycles: Optional[int] = None
    text_messages: Optional[List[str]] = None
    
    def __post_init__(self):
        """Convert string path to Path object if needed."""
        if isinstance(self.playback_path, str):
            self.playback_path = Path(self.playback_path)
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate playback entry constraints.
        
        Returns:
            (is_valid, error_message)
        """
        if self.weight <= 0:
            return False, f"Weight must be positive, got {self.weight}"
        
        # Validate duration-based constraints (preferred)
        if self.min_duration_s is not None and self.min_duration_s < 0:
            return False, f"min_duration_s must be non-negative, got {self.min_duration_s}"
        
        if self.max_duration_s is not None and self.max_duration_s < 0:
            return False, f"max_duration_s must be non-negative, got {self.max_duration_s}"
        
        if (self.min_duration_s is not None and self.max_duration_s is not None 
            and self.min_duration_s > self.max_duration_s):
            return False, f"min_duration_s ({self.min_duration_s}) cannot exceed max_duration_s ({self.max_duration_s})"
        
        # Validate legacy cycle-based constraints (backward compatibility)
        if self.min_cycles is not None and self.min_cycles < 0:
            return False, f"min_cycles must be non-negative, got {self.min_cycles}"
        
        if self.max_cycles is not None and self.max_cycles < 0:
            return False, f"max_cycles must be non-negative, got {self.max_cycles}"
        
        if (self.min_cycles is not None and self.max_cycles is not None 
            and self.min_cycles > self.max_cycles):
            return False, f"min_cycles ({self.min_cycles}) cannot exceed max_cycles ({self.max_cycles})"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        data = {
            "playback": str(self.playback_path),
            "weight": self.weight
        }
        # Prefer duration-based fields
        if self.min_duration_s is not None:
            data["min_duration_s"] = self.min_duration_s
        if self.max_duration_s is not None:
            data["max_duration_s"] = self.max_duration_s
        # Include legacy cycle fields for backward compatibility
        if self.min_cycles is not None:
            data["min_cycles"] = self.min_cycles
        if self.max_cycles is not None:
            data["max_cycles"] = self.max_cycles
        if self.text_messages:
            data["text_messages"] = list(self.text_messages)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlaybackEntry:
        """Deserialize from dict."""
        return cls(
            playback_path=Path(data["playback"]),
            weight=data.get("weight", 1.0),
            min_duration_s=data.get("min_duration_s"),
            max_duration_s=data.get("max_duration_s"),
            min_cycles=data.get("min_cycles"),
            max_cycles=data.get("max_cycles"),
            text_messages=data.get("text_messages"),
        )


class AudioRole(str, Enum):
    """Enumerated purpose for a cue-level audio track."""
    HYPNO = "hypno"
    BACKGROUND = "background"
    GENERIC = "generic"


@dataclass
class AudioTrack:
    """
    Audio track configuration for a cue.
    
    Attributes:
        file_path: Path to audio file (MP3, WAV, OGG, etc.)
        volume: Volume level (0.0 to 1.0)
        loop: Whether to loop the track during the cue
        fade_in_ms: Fade-in duration in milliseconds
        fade_out_ms: Fade-out duration in milliseconds
    """
    file_path: Path
    volume: float = 1.0
    loop: bool = False
    fade_in_ms: float = 500
    fade_out_ms: float = 500
    role: AudioRole = AudioRole.GENERIC
    
    def __post_init__(self):
        """Convert string path to Path object if needed."""
        if isinstance(self.file_path, str):
            self.file_path = Path(self.file_path)
        if isinstance(self.role, str):
            try:
                self.role = AudioRole(self.role)
            except ValueError:
                self.role = AudioRole.GENERIC
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate audio track settings.
        
        Returns:
            (is_valid, error_message)
        """
        if not (0.0 <= self.volume <= 1.0):
            return False, f"Volume must be 0.0-1.0, got {self.volume}"
        
        if self.fade_in_ms < 0:
            return False, f"fade_in_ms must be non-negative, got {self.fade_in_ms}"
        
        if self.fade_out_ms < 0:
            return False, f"fade_out_ms must be non-negative, got {self.fade_out_ms}"

        # Role must be a known enum value
        if isinstance(self.role, str):
            try:
                self.role = AudioRole(self.role)
            except Exception as exc:
                return False, f"Invalid audio role '{self.role}': {exc}"
        elif not isinstance(self.role, AudioRole):
            return False, f"Invalid audio role type: {type(self.role)}"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "file": str(self.file_path),
            "volume": self.volume,
            "loop": self.loop,
            "fade_in_ms": self.fade_in_ms,
            "fade_out_ms": self.fade_out_ms,
            "role": self.role.value if isinstance(self.role, AudioRole) else str(self.role)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AudioTrack:
        """Deserialize from dict."""
        role_value = data.get("role")
        role = AudioRole.GENERIC
        if role_value:
            try:
                role = AudioRole(role_value)
            except ValueError:
                role = AudioRole.GENERIC

        return cls(
            file_path=Path(data["file"]),
            volume=data.get("volume", 1.0),
            loop=data.get("loop", False),
            fade_in_ms=data.get("fade_in_ms", 500),
            fade_out_ms=data.get("fade_out_ms", 500),
            role=role
        )


@dataclass
class CueTransition:
    """
    Transition effect configuration for cue boundaries.
    
    Note: wait_for_cycle is always True and enforced by SessionRunner.
    All transitions are synchronized to media cycle boundaries.
    
    Attributes:
        type: Transition type ("none", "fade", "interpolate")
        duration_ms: Transition duration in milliseconds
        wait_for_cycle: Always True (cycle synchronization enforced)
    """
    type: str = "none"
    duration_ms: float = 500
    wait_for_cycle: bool = True  # Always True, enforced
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate transition settings.
        
        Returns:
            (is_valid, error_message)
        """
        valid_types = ["none", "fade", "interpolate"]
        if self.type not in valid_types:
            return False, f"Invalid transition type '{self.type}', must be one of {valid_types}"
        
        if self.duration_ms < 0:
            return False, f"duration_ms must be non-negative, got {self.duration_ms}"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "type": self.type,
            "duration_ms": self.duration_ms
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CueTransition:
        """Deserialize from dict."""
        return cls(
            type=data.get("type", "none"),
            duration_ms=data.get("duration_ms", 500),
            wait_for_cycle=True  # Always enforce cycle sync
        )


@dataclass
class Cue:
    """
    Individual segment in a cuelist session.
    
    A Cue defines a timed period with:
    - One or more playbacks (weighted pool)
    - Selection mode determining when playbacks switch
    - Optional audio tracks
    - Transition effects for entry/exit
    
    All playback switches occur at media cycle boundaries.
    
    Attributes:
        name: Display name for the cue
        duration_seconds: Duration of this cue in seconds
        playback_pool: List of possible playbacks with weights
        selection_mode: When to select new playbacks from pool
        selection_interval_seconds: Interval for TIMED_INTERVAL mode
        transition_in: Transition effect when entering cue
        transition_out: Transition effect when leaving cue
        audio_tracks: Audio tracks to play during cue (max 2)
        text_messages: Custom text messages for this cue (optional, overrides playback text)
    """
    name: str
    duration_seconds: float
    playback_pool: List[PlaybackEntry]
    selection_mode: PlaybackSelectionMode = PlaybackSelectionMode.ON_CUE_START
    selection_interval_seconds: Optional[float] = None
    transition_in: CueTransition = field(default_factory=CueTransition)
    transition_out: CueTransition = field(default_factory=CueTransition)
    audio_tracks: List[AudioTrack] = field(default_factory=list)
    text_messages: Optional[List[str]] = None
    vibrate_on_text_cycle: bool = False
    vibration_intensity: float = 0.5  # 0.0 to 1.0
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate cue configuration.
        
        Returns:
            (is_valid, error_message)
        """
        # Validate duration
        if self.duration_seconds <= 0:
            return False, f"duration_seconds must be positive, got {self.duration_seconds}"
        
        # Validate name
        if not self.name or not self.name.strip():
            return False, "Cue name cannot be empty"
        
        # Validate playback pool
        if not self.playback_pool:
            return False, "playback_pool cannot be empty"
        
        for i, entry in enumerate(self.playback_pool):
            is_valid, msg = entry.validate()
            if not is_valid:
                return False, f"Playback entry {i}: {msg}"
        
        # Validate selection interval
        if self.selection_mode == PlaybackSelectionMode.ON_TIMED_INTERVAL:
            if self.selection_interval_seconds is None:
                return False, "selection_interval_seconds required for ON_TIMED_INTERVAL mode"
            if self.selection_interval_seconds <= 0:
                return False, f"selection_interval_seconds must be positive, got {self.selection_interval_seconds}"
        
        # Validate transitions
        is_valid, msg = self.transition_in.validate()
        if not is_valid:
            return False, f"transition_in: {msg}"
        
        is_valid, msg = self.transition_out.validate()
        if not is_valid:
            return False, f"transition_out: {msg}"
        
        # Validate audio tracks (max 2) and enforce role uniqueness
        if len(self.audio_tracks) > 2:
            return False, f"Maximum 2 audio tracks allowed, got {len(self.audio_tracks)}"

        role_counts: Dict[AudioRole, int] = {}
        for i, track in enumerate(self.audio_tracks):
            is_valid, msg = track.validate()
            if not is_valid:
                return False, f"Audio track {i}: {msg}"

            role = track.role if isinstance(track.role, AudioRole) else AudioRole.GENERIC
            role_counts[role] = role_counts.get(role, 0) + 1
            if role != AudioRole.GENERIC and role_counts[role] > 1:
                return False, f"Only one '{role.value}' track allowed per cue"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        data = {
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "playback_pool": [entry.to_dict() for entry in self.playback_pool],
            "selection_mode": self.selection_mode.value,
            "transition_in": self.transition_in.to_dict(),
            "transition_out": self.transition_out.to_dict()
        }
        
        if self.selection_interval_seconds is not None:
            data["selection_interval_seconds"] = self.selection_interval_seconds
        
        if self.audio_tracks:
            serialized = [track.to_dict() for track in self.audio_tracks]
            data["audio_tracks"] = serialized

            audio_layer: Dict[str, Any] = {}
            for track in self.audio_tracks:
                if track.role == AudioRole.HYPNO:
                    audio_layer["hypno"] = track.to_dict()
                elif track.role == AudioRole.BACKGROUND:
                    audio_layer["background"] = track.to_dict()
            if audio_layer:
                data["audio"] = audio_layer
        
        if self.text_messages is not None:
            data["text_messages"] = self.text_messages
        
        if self.vibrate_on_text_cycle:
            data["vibrate_on_text_cycle"] = self.vibrate_on_text_cycle
        
        if self.vibration_intensity != 0.5:  # Only save if non-default
            data["vibration_intensity"] = self.vibration_intensity
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Cue:
        """Deserialize from dict.
        
        Supports both legacy format (duration) and new format (duration_seconds).
        """
        # Handle legacy "duration" field (convert to duration_seconds)
        if "duration_seconds" in data:
            duration = data["duration_seconds"]
        elif "duration" in data:
            duration = data["duration"]  # Legacy format
        else:
            raise KeyError("Missing 'duration_seconds' or 'duration' field in cue data")
        
        # Migrate old selection mode names
        selection_mode_str = data.get("selection_mode", "on_cue_start")
        if selection_mode_str == "random_each_cycle":
            selection_mode_str = "on_media_cycle"  # Old name → new name
        
        # Preferred new schema: "audio" with explicit roles
        tracks: List[AudioTrack] = []
        audio_block = data.get("audio")
        if isinstance(audio_block, dict):
            if audio_block.get("hypno"):
                hypno_track = AudioTrack.from_dict(audio_block["hypno"])
                hypno_track.role = AudioRole.HYPNO
                tracks.append(hypno_track)
            if audio_block.get("background"):
                bg_track = AudioTrack.from_dict(audio_block["background"])
                bg_track.role = AudioRole.BACKGROUND
                tracks.append(bg_track)

        # Legacy schema: "audio_tracks" list
        if not tracks:
            legacy_tracks = [
                AudioTrack.from_dict(track)
                for track in data.get("audio_tracks", [])
            ]
            # Assign default roles to legacy entries for deterministic behavior
            if legacy_tracks:
                if len(legacy_tracks) >= 1 and legacy_tracks[0].role == AudioRole.GENERIC:
                    legacy_tracks[0].role = AudioRole.HYPNO
                if len(legacy_tracks) >= 2 and legacy_tracks[1].role == AudioRole.GENERIC:
                    legacy_tracks[1].role = AudioRole.BACKGROUND
            tracks = legacy_tracks

        return cls(
            name=data["name"],
            duration_seconds=duration,
            playback_pool=[
                PlaybackEntry.from_dict(entry) 
                for entry in data["playback_pool"]
            ],
            selection_mode=PlaybackSelectionMode(selection_mode_str),
            selection_interval_seconds=data.get("selection_interval_seconds"),
            transition_in=CueTransition.from_dict(data.get("transition_in", {})),
            transition_out=CueTransition.from_dict(data.get("transition_out", {})),
            audio_tracks=tracks,
            text_messages=data.get("text_messages"),
            vibrate_on_text_cycle=data.get("vibrate_on_text_cycle", False),
            vibration_intensity=data.get("vibration_intensity", 0.5)
        )

    # Convenience helpers -------------------------------------------------

    def get_audio_track(self, role: AudioRole) -> Optional[AudioTrack]:
        """Return the audio track for the requested role."""
        for track in self.audio_tracks:
            if track.role == role:
                return track
        return None

    def get_audio_layers(self) -> Dict[AudioRole, AudioTrack]:
        """Return mapping of configured audio roles to their tracks."""
        result: Dict[AudioRole, AudioTrack] = {}
        for track in self.audio_tracks:
            result[track.role] = track
        return result
