"""
Session Management System for MesmerGlass.

This package implements the Cuelist/Session system that enables users to create
complex, timed hypnosis sessions by sequencing "Cues" that dynamically select
from pools of visual "Playbacks".

Core Components:
- Cue: Timed segment with playback pool + audio tracks
- Cuelist: Ordered sequence of cues forming a complete session
- SessionRunner: Execution engine with cycle-synchronized transitions

See docs/technical/cuelist-system-implementation-plan.md for full architecture.
"""

from .cue import (
    Cue,
    PlaybackEntry,
    AudioTrack,
    CueTransition,
    PlaybackSelectionMode,
    AudioRole,
)

from .cuelist import (
    Cuelist,
    CuelistLoopMode
)

from .events import (
    SessionEventType,
    SessionEvent,
    SessionEventEmitter
)

from .runner import SessionRunner

__all__ = [
    # Cue components
    'Cue',
    'PlaybackEntry',
    'AudioTrack',
    'CueTransition',
    'PlaybackSelectionMode',
    'AudioRole',
    
    # Cuelist components
    'Cuelist',
    'CuelistLoopMode',
    
    # Event system
    'SessionEventType',
    'SessionEvent',
    'SessionEventEmitter',
    
    # Execution
    'SessionRunner',
]

__version__ = '0.1.0'
