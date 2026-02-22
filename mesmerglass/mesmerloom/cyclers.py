"""
Frame-accurate timing system for animation orchestration.

Based on Trance's cycler architecture - provides composable timing primitives
for building complex visual programs with precise frame-level control.
"""

from abc import ABC, abstractmethod
import os
import time
from typing import Callable, List, Optional


class Cycler(ABC):
    """
    Base class for all cycler types.
    
    Cyclers provide frame-accurate timing control for animations and visual programs.
    They can be composed into trees for complex orchestration patterns.
    """
    
    @abstractmethod
    def advance(self) -> None:
        """Advance cycler by one logical frame."""
        pass
    
    @abstractmethod
    def complete(self) -> bool:
        """Check if cycler has finished execution."""
        pass
    
    @abstractmethod
    def length(self) -> int:
        """Total number of frames this cycler will execute."""
        pass
    
    @abstractmethod
    def index(self) -> int:
        """Current frame index within this cycler."""
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset cycler to initial state."""
        pass
    
    def progress(self) -> float:
        """
        Calculate progress through cycler [0.0 - 1.0].
        
        Returns:
            Progress ratio, where 0.0 = start, 1.0 = complete
        """
        total = self.length()
        if total == 0:
            return 1.0
        return min(1.0, self.index() / total)


class ActionCycler(Cycler):
    """
    Execute a callback action every N frames, optionally with an initial offset.
    
    Example use cases:
    - Change image every 48 frames
    - Update text every 4 frames
    - Preload next asset at frame 24 (offset)
    
    Args:
        period: Number of frames between action executions
        action: Callable to execute at each period
        offset: Number of frames to wait before first execution (default: 0)
        repeat_count: Maximum number of times to execute action (default: infinite)
    """
    
    def __init__(
        self,
        period: int,
        action: Callable[[], None],
        offset: int = 0,
        repeat_count: Optional[int] = None
    ):
        if period <= 0:
            raise ValueError(f"Period must be positive, got {period}")
        if offset < 0:
            raise ValueError(f"Offset must be non-negative, got {offset}")
        
        self.period = period
        self.action = action
        self.offset = offset
        self.repeat_count = repeat_count
        self._frame = 0
        self._executions = 0

        # Best-effort perf attribution for heavy action callbacks.
        # This is intentionally lightweight and only records when an action call is slow.
        try:
            self._action_warn_ms = float(os.environ.get("MESMERGLASS_CYCLER_ACTION_WARN_MS", "6"))
        except Exception:
            self._action_warn_ms = 6.0

        self._action_name = self._resolve_action_name(action)

    @staticmethod
    def _resolve_action_name(action: Callable[[], None]) -> str:
        try:
            # functools.partial
            target = getattr(action, "func", None) or action
            name = getattr(target, "__qualname__", None) or getattr(target, "__name__", None)
            if not name:
                name = target.__class__.__qualname__
            name = str(name)
        except Exception:
            name = "action"
        # Keep it compact/stable for logs.
        if len(name) > 96:
            name = name[:96] + "…"
        return name
    
    def advance(self) -> None:
        """Advance by one frame, execute action if at period boundary."""
        # Check if we're past offset and at a period boundary
        if self._frame >= self.offset:
            frames_since_offset = self._frame - self.offset
            if frames_since_offset % self.period == 0:
                # Check repeat limit
                if self.repeat_count is None or self._executions < self.repeat_count:
                    t0 = time.perf_counter()
                    self.action()
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    if dt_ms >= float(self._action_warn_ms or 0.0):
                        try:
                            from mesmerglass.session import perf_blockers

                            perf_blockers.record(
                                "visual.cycler.action",
                                float(dt_ms),
                                name=self._action_name,
                                period=int(self.period),
                            )
                        except Exception:
                            pass
                    self._executions += 1
        
        self._frame += 1
    
    def complete(self) -> bool:
        """
        ActionCyclers with infinite repeats never complete.
        With repeat_count, completes after reaching full length.
        """
        if self.repeat_count is None:
            return False
        # Complete when we've reached our designed length
        return self._frame >= self.length()
    
    def length(self) -> int:
        """
        Total frames this cycler will run.
        
        Returns:
            offset + (period * repeat_count) if finite, else a very large number
        """
        if self.repeat_count is None:
            return 999999999  # Effectively infinite
        return self.offset + (self.period * self.repeat_count)
    
    def index(self) -> int:
        """Current frame index."""
        return self._frame
    
    def reset(self) -> None:
        """Reset to initial state."""
        self._frame = 0
        self._executions = 0


class RepeatCycler(Cycler):
    """
    Repeat a child cycler N times.
    
    After child completes, resets it and increments repetition counter.
    Useful for creating loops of complex cycler sequences.
    
    Example:
        # Flash text 5 times (each flash is 10 frames)
        flash = ActionCycler(10, flash_text)
        repeat = RepeatCycler(5, flash)
    
    Args:
        count: Number of times to repeat child cycler
        child: Child cycler to repeat
    """
    
    def __init__(self, count: int, child: Cycler):
        if count <= 0:
            raise ValueError(f"Repeat count must be positive, got {count}")
        
        self.count = count
        self.child = child
        self._repetition = 0
    
    def advance(self) -> None:
        """Advance child, reset when it completes."""
        if self.complete():
            return
        
        self.child.advance()
        
        # If child just completed, reset it and increment counter
        if self.child.complete():
            self._repetition += 1
            if not self.complete():
                self.child.reset()
    
    def complete(self) -> bool:
        """Complete after N repetitions."""
        return self._repetition >= self.count
    
    def length(self) -> int:
        """Total frames = child length * repeat count."""
        return self.child.length() * self.count
    
    def index(self) -> int:
        """Current frame = (completed reps * child length) + child index."""
        if self.complete():
            return self.length()
        return (self._repetition * self.child.length()) + self.child.index()
    
    def reset(self) -> None:
        """Reset to initial state."""
        self._repetition = 0
        self.child.reset()


class SequenceCycler(Cycler):
    """
    Execute multiple cyclers one after another in sequence.
    
    When a child completes, advances to the next child.
    Completes when all children have completed.
    
    Example:
        # Fade in, hold, fade out
        sequence = SequenceCycler([
            ActionCycler(30, fade_in),   # 0.5s fade in
            ActionCycler(60, hold),       # 1.0s hold
            ActionCycler(30, fade_out)    # 0.5s fade out
        ])
    
    Args:
        children: List of cyclers to execute in order
    """
    
    def __init__(self, children: List[Cycler]):
        if not children:
            raise ValueError("SequenceCycler requires at least one child")
        
        self.children = children
        self._current_index = 0
    
    def advance(self) -> None:
        """Advance current child, move to next when it completes."""
        if self.complete():
            return
        
        # Advance current child
        current = self.children[self._current_index]
        current.advance()
        
        # Move to next child if current completed
        if current.complete():
            self._current_index += 1
    
    def complete(self) -> bool:
        """Complete when all children have completed."""
        return self._current_index >= len(self.children)
    
    def length(self) -> int:
        """Total frames = sum of all child lengths."""
        return sum(child.length() for child in self.children)
    
    def index(self) -> int:
        """Current frame = sum of completed children + current child index."""
        if self.complete():
            return self.length()
        
        # Sum lengths of all completed children
        completed_frames = sum(
            self.children[i].length()
            for i in range(self._current_index)
        )
        
        # Add current child's index
        return completed_frames + self.children[self._current_index].index()
    
    def reset(self) -> None:
        """Reset to initial state."""
        self._current_index = 0
        for child in self.children:
            child.reset()


class ParallelCycler(Cycler):
    """
    Execute multiple cyclers simultaneously in parallel.
    
    All children advance together each frame.
    Completes when all children have completed.
    
    Example:
        # Spiral rotation + image changes + text cycling, all happening together
        parallel = ParallelCycler([
            ActionCycler(1, rotate_spiral),     # Every frame
            ActionCycler(48, change_image),     # Every 48 frames
            ActionCycler(4, cycle_text)         # Every 4 frames
        ])
    
    Args:
        children: List of cyclers to execute in parallel
    """
    
    def __init__(self, children: List[Cycler]):
        if not children:
            raise ValueError("ParallelCycler requires at least one child")
        
        self.children = children
    
    def advance(self) -> None:
        """Advance all children that haven't completed yet."""
        for child in self.children:
            if not child.complete():
                child.advance()
    
    def complete(self) -> bool:
        """Complete when all children have completed."""
        return all(child.complete() for child in self.children)
    
    def length(self) -> int:
        """Total frames = length of longest child."""
        if not self.children:
            return 0
        return max(child.length() for child in self.children)
    
    def index(self) -> int:
        """Current frame = maximum index across all children."""
        if not self.children:
            return 0
        if self.complete():
            return self.length()
        return max(child.index() for child in self.children)
    
    def reset(self) -> None:
        """Reset to initial state."""
        for child in self.children:
            child.reset()
