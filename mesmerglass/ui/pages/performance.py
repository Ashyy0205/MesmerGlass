"""Performance monitoring page used by the Qt UI and tests.

The page is intentionally lightweight so unit tests can instantiate it with
an Audio2 stub without launching the full application window stack.
"""
from __future__ import annotations

from typing import Optional, Protocol

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mesmerglass.engine.audio import Audio2
from mesmerglass.engine.perf import PerformanceSnapshot, perf_metrics


class _AudioLike(Protocol):
    def memory_usage_bytes(self) -> dict:
        ...


class PerformancePage(QWidget):
    """Compact widget that surfaces perf + audio memory stats."""

    def __init__(
        self,
        audio: Optional[_AudioLike] = None,
        *,
        parent: Optional[QWidget] = None,
        refresh_interval_ms: int = 250,
    ) -> None:
        super().__init__(parent)
        self._audio: _AudioLike = audio or Audio2()
        self._timer = QTimer(self)
        self._timer.setInterval(refresh_interval_ms)
        self._timer.timeout.connect(self._refresh_all)
        self.destroyed.connect(lambda *_: self._timer.stop())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.lab_heading = QLabel("📊 Performance Snapshot")
        self.lab_heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.lab_heading)

        self.lab_fps = QLabel("FPS: --")
        self.lab_frame = QLabel("Frame avg: -- ms | max: -- ms")
        self.lab_stall = QLabel("I/O stalls: --")
        self.lab_warn = QLabel("Warnings: none")

        self.lab_a1 = QLabel("Audio 1: --")
        self.lab_a2 = QLabel("Audio 2: --")

        for lab in (
            self.lab_fps,
            self.lab_frame,
            self.lab_stall,
            self.lab_warn,
            self.lab_a1,
            self.lab_a2,
        ):
            lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(lab)

        self._timer.start()
        self._refresh_all()

    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        self._refresh_perf_section(perf_metrics.snapshot())
        self._refresh_audio_section()

    def _refresh_perf_section(self, snap: PerformanceSnapshot) -> None:
        self.lab_fps.setText(f"FPS: {snap.fps:.1f}" if snap.fps else "FPS: --")
        if snap.avg_frame_ms is not None and snap.max_frame_ms is not None:
            self.lab_frame.setText(
                f"Frame avg: {snap.avg_frame_ms:.1f} ms | max: {snap.max_frame_ms:.1f} ms"
            )
        else:
            self.lab_frame.setText("Frame avg: -- ms | max: -- ms")

        stall_text = "I/O stalls: --"
        if snap.stall_count:
            last = f", last {snap.last_stall_ms:.0f} ms" if snap.last_stall_ms else ""
            stall_text = f"I/O stalls: {snap.stall_count}{last}"
        self.lab_stall.setText(stall_text)

        self.lab_warn.setText(
            "Warnings: " + ("; ".join(snap.warnings) if snap.warnings else "none")
        )

    def _refresh_audio_section(self) -> None:
        stats = None
        try:
            stats = self._audio.memory_usage_bytes()
        except Exception:
            stats = None

        if not stats:
            self.lab_a1.setText("Audio 1: unavailable")
            self.lab_a2.setText("Audio 2: unavailable")
            return

        audio1 = self._format_bytes(stats.get("audio1_bytes"))
        audio2 = self._format_bytes(stats.get("audio2_bytes"))
        streaming = " (streaming)" if stats.get("audio1_streaming") else ""
        self.lab_a1.setText(f"Audio 1: {audio1}{streaming}")
        self.lab_a2.setText(f"Audio 2: {audio2}")

    @staticmethod
    def _format_bytes(value: Optional[int]) -> str:
        if value is None:
            return "--"
        kb = value / 1024.0
        if kb >= 1024.0:
            return f"{kb / 1024.0:.1f} MB"
        return f"{kb:.1f} KB"