"""Session event system for broadcasting session state changes.

Provides event types, event data structures, and event emitter for decoupled
communication between SessionRunner and UI/logging/external systems.

Usage:
    emitter = SessionEventEmitter()
    emitter.subscribe(SessionEventType.CUE_START, lambda evt: print(f"Cue started: {evt.data}"))
    emitter.emit(SessionEvent(SessionEventType.CUE_START, data={"cue_index": 0}))
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Any, Optional
import logging


class SessionEventType(Enum):
    """Types of events that can occur during session execution."""
    
    # Session lifecycle
    SESSION_START = auto()     # Session started
    SESSION_END = auto()       # Session completed normally
    SESSION_PAUSE = auto()     # Session paused
    SESSION_RESUME = auto()    # Session resumed from pause
    SESSION_STOP = auto()      # Session stopped manually (before completion)
    
    # Cue lifecycle
    CUE_START = auto()         # Cue segment started
    CUE_END = auto()           # Cue segment completed
    
    # Transition events
    TRANSITION_START = auto()  # Transition between cues started
    TRANSITION_END = auto()    # Transition between cues completed
    
    # Progress events (for UI updates)
    CUE_PROGRESS = auto()      # Periodic progress update during cue
    
    # Error events
    ERROR = auto()             # Error occurred during session


@dataclass
class SessionEvent:
    """Represents a session event with optional payload data.
    
    Attributes:
        event_type: Type of event that occurred
        data: Optional dictionary with event-specific data
        timestamp: Optional timestamp (can be set by emitter)
    """
    event_type: SessionEventType
    data: Optional[dict[str, Any]] = None
    timestamp: Optional[float] = None
    
    def __str__(self) -> str:
        """Human-readable event representation."""
        if self.data:
            data_str = ", ".join(f"{k}={v}" for k, v in self.data.items())
            return f"SessionEvent({self.event_type.name}, {data_str})"
        return f"SessionEvent({self.event_type.name})"


class SessionEventEmitter:
    """Event bus for session state changes.
    
    Allows components to subscribe to specific event types and receive
    notifications when those events occur. Supports multiple subscribers
    per event type.
    
    Example:
        emitter = SessionEventEmitter()
        
        # Subscribe to events
        def on_cue_start(event: SessionEvent):
            print(f"Cue {event.data['cue_index']} started")
        
        emitter.subscribe(SessionEventType.CUE_START, on_cue_start)
        
        # Emit events
        emitter.emit(SessionEvent(
            SessionEventType.CUE_START,
            data={"cue_index": 0, "cue_name": "Induction"}
        ))
    """
    
    def __init__(self):
        """Initialize event emitter with empty subscriber lists."""
        self._subscribers: dict[SessionEventType, list[Callable[[SessionEvent], None]]] = {}
        self.logger = logging.getLogger(__name__)
    
    def subscribe(
        self,
        event_type: SessionEventType,
        callback: Callable[[SessionEvent], None]
    ) -> None:
        """Subscribe to a specific event type.
        
        Args:
            event_type: Type of event to listen for
            callback: Function to call when event occurs (receives SessionEvent)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            self.logger.debug(f"[events] Subscribed to {event_type.name} (total={len(self._subscribers[event_type])})")
    
    def unsubscribe(
        self,
        event_type: SessionEventType,
        callback: Callable[[SessionEvent], None]
    ) -> None:
        """Unsubscribe from a specific event type.
        
        Args:
            event_type: Type of event to stop listening for
            callback: The callback function to remove
        """
        if event_type in self._subscribers:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                self.logger.debug(f"[events] Unsubscribed from {event_type.name} (total={len(self._subscribers[event_type])})")
    
    def emit(self, event: SessionEvent) -> None:
        """Emit an event to all subscribed callbacks.
        
        Args:
            event: The event to emit
        """
        # Add timestamp if not already set
        if event.timestamp is None:
            import time
            event.timestamp = time.time()
        
        self.logger.debug(f"[events] Emitting: {event}")
        
        # Call all subscribers for this event type
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    self.logger.error(f"[events] Callback error for {event.event_type.name}: {e}", exc_info=True)
    
    def clear_all(self) -> None:
        """Remove all event subscribers (useful for testing/cleanup)."""
        self._subscribers.clear()
        self.logger.debug("[events] Cleared all subscribers")
