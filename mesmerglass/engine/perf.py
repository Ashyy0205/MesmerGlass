"""Lightweight performance metrics collection.

Provides a thread-safe singleton `perf_metrics` used by video/audio/UI code
to record frame timings and I/O stalls. The PerformancePage queries a
snapshot periodically to display rolling statistics and warnings.
"""
from __future__ import annotations

from collections import deque
from threading import Lock
from dataclasses import dataclass
from typing import Deque, Dict, List
import time


@dataclass
class PerformanceSnapshot:
    fps: float
    avg_frame_ms: float | None
    max_frame_ms: float | None
    stall_count: int
    last_stall_ms: float | None
    warnings: List[str]


class PerformanceMetrics:
    """Collects rolling performance statistics.

    Only extremely cheap operations occur in hot paths (single append & math).
    Aggregations and string building happen in `snapshot` which is UI-driven.
    """

    def __init__(self, *, max_frames: int = 240):
        self._frame_times: Deque[float] = deque(maxlen=max_frames)  # seconds
        self._stall_durations: Deque[float] = deque(maxlen=100)  # ms
        self._last_stall_ms: float | None = None
        self._lock = Lock()
        # Thresholds (mutable)
        self.target_fps: float = 30.0
        self.warn_frame_ms: float = 60.0
        self.warn_stall_ms: float = 120.0

    # ---------------- Recording APIs -----------------
    def record_frame(self, dt_seconds: float) -> None:
        if dt_seconds <= 0:  # guard (zero or negative intervals not meaningful)
            return
        with self._lock:
            self._frame_times.append(dt_seconds)

    def record_io_stall(self, duration_ms: float) -> None:
        if duration_ms <= 0:
            return
        with self._lock:
            self._stall_durations.append(duration_ms)
            self._last_stall_ms = duration_ms

    # ---------------- Query -----------------
    def snapshot(self) -> PerformanceSnapshot:
        with self._lock:
            frames = list(self._frame_times)
            stalls = list(self._stall_durations)
            last_stall = self._last_stall_ms
            target_fps = self.target_fps
            warn_frame_ms = self.warn_frame_ms
            warn_stall_ms = self.warn_stall_ms

        fps = 0.0
        avg_ms = None
        max_ms = None
        if frames:
            # FPS: based on mean dt (stable vs instantaneous)
            mean_dt = sum(frames) / len(frames)
            if mean_dt > 0:
                fps = 1.0 / mean_dt
            avg_ms = mean_dt * 1000.0
            max_ms = max(frames) * 1000.0

        warnings: List[str] = []
        if target_fps > 0 and fps and fps + 1e-6 < target_fps * 0.9:  # allow 10% slack
            warnings.append(f"Low FPS: {fps:.1f} < {target_fps:.0f}")
        if max_ms is not None and max_ms > warn_frame_ms:
            warnings.append(f"Frame spike: {max_ms:.0f} ms > {warn_frame_ms:.0f} ms")
        if last_stall is not None and last_stall > warn_stall_ms:
            warnings.append(f"I/O stall: {last_stall:.0f} ms > {warn_stall_ms:.0f} ms")

        return PerformanceSnapshot(
            fps=fps,
            avg_frame_ms=avg_ms,
            max_frame_ms=max_ms,
            stall_count=len(stalls),
            last_stall_ms=last_stall,
            warnings=warnings,
        )


# Singleton instance used across the app
perf_metrics = PerformanceMetrics()

__all__ = ["PerformanceMetrics", "PerformanceSnapshot", "perf_metrics"]
