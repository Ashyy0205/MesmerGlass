"""Performance metrics UI page.

Shows FPS / frame timing, I/O stall stats, and per-audio track memory usage.
If no frames have been recorded yet (e.g. video not started) we still display
0.0 for FPS and show a status hint so the user understands why averages are
blank.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout

from ...engine.perf import perf_metrics


def _group(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setContentsMargins(8, 6, 8, 6)
    return g


def _fmt_bytes(n: int | None) -> str:
    if n is None:
        return "(none)"
    if n < 1024:
        return f"{n} B"
    kb = n / 1024.0
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024.0
    return f"{mb:.2f} MB"


class PerformancePage(QWidget):
    TARGET_FPS = 30.0          # Hard-coded thresholds (per request)
    WARN_FRAME_MS = 60.0
    WARN_STALL_MS = 120.0

    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio = audio_engine
        # Apply thresholds to shared metrics backend
        perf_metrics.target_fps = self.TARGET_FPS
        perf_metrics.warn_frame_ms = self.WARN_FRAME_MS
        perf_metrics.warn_stall_ms = self.WARN_STALL_MS
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(250)  # 4 Hz refresh

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Frame statistics
        grp_stats = _group("Frame Stats")
        stats_form = QFormLayout(grp_stats)
        stats_form.setContentsMargins(10, 6, 10, 6)
        stats_form.setSpacing(4)
        self.lab_fps = QLabel("0.0")
        self.lab_avg = QLabel("0.0")
        self.lab_max = QLabel("0.0")
        self.lab_stalls = QLabel("0")
        self.lab_last_stall = QLabel("—")
        self.lab_frame_hint = QLabel("No frames yet (video idle)")
        self.lab_frame_hint.setStyleSheet("color:#888;")
        stats_form.addRow("FPS", self.lab_fps)
        stats_form.addRow("Avg frame (ms)", self.lab_avg)
        stats_form.addRow("Max frame (ms)", self.lab_max)
        stats_form.addRow("Stall count", self.lab_stalls)
        stats_form.addRow("Last stall (ms)", self.lab_last_stall)
        stats_form.addRow("Status", self.lab_frame_hint)
        layout.addWidget(grp_stats)

        # Threshold summary (fixed values)
        grp_thr = _group("Thresholds (Fixed)")
        thr_form = QFormLayout(grp_thr)
        thr_form.setContentsMargins(10, 6, 10, 6)
        thr_form.setSpacing(4)
        thr_form.addRow("Target FPS", QLabel(f"{self.TARGET_FPS:.0f}"))
        thr_form.addRow("Frame warn (ms)", QLabel(f"{self.WARN_FRAME_MS:.0f}"))
        thr_form.addRow("Stall warn (ms)", QLabel(f"{self.WARN_STALL_MS:.0f}"))
        layout.addWidget(grp_thr)

        # Audio memory section
        grp_mem = _group("Audio Memory")
        mem_form = QFormLayout(grp_mem)
        mem_form.setContentsMargins(10, 6, 10, 6)
        mem_form.setSpacing(4)
        self.lab_a1 = QLabel("(none)")
        self.lab_a2 = QLabel("(none)")
        mem_form.addRow("Primary", self.lab_a1)
        mem_form.addRow("Secondary", self.lab_a2)
        layout.addWidget(grp_mem)

        # Warnings list
        grp_warn = _group("Warnings")
        warn_form = QFormLayout(grp_warn)
        warn_form.setContentsMargins(10, 6, 10, 6)
        warn_form.setSpacing(4)
        self.lab_warn = QLabel("(none)")
        self.lab_warn.setWordWrap(True)
        warn_form.addRow("Active", self.lab_warn)
        layout.addWidget(grp_warn)

        layout.addStretch(1)

    def _refresh(self):
        snap = perf_metrics.snapshot()
        # Always show numeric values (0.0) even if no frames yet for clarity
        self.lab_fps.setText(f"{snap.fps:.1f}")
        if snap.avg_frame_ms is None:
            self.lab_avg.setText("0.0")
            self.lab_max.setText("0.0")
        else:
            self.lab_avg.setText(f"{snap.avg_frame_ms:.1f}")
            self.lab_max.setText(f"{snap.max_frame_ms:.1f}" if snap.max_frame_ms is not None else "0.0")
        self.lab_stalls.setText(str(snap.stall_count))
        self.lab_last_stall.setText("—" if snap.last_stall_ms is None else f"{snap.last_stall_ms:.0f}")
        self.lab_warn.setText("(none)" if not snap.warnings else "\n".join(snap.warnings))

        # Hide frame hint after first real frame (avg becomes non-None)
        if snap.avg_frame_ms is not None and self.lab_frame_hint.isVisible():
            self.lab_frame_hint.hide()

        # Audio memory (best-effort; handle early init gracefully)
        try:
            mem = self.audio.memory_usage_bytes()
        except Exception:
            mem = {"audio1_bytes": None, "audio2_bytes": None, "audio1_streaming": False}
        a1 = "(streaming)" if mem.get("audio1_streaming") else _fmt_bytes(mem.get("audio1_bytes"))
        a2 = _fmt_bytes(mem.get("audio2_bytes"))
        self.lab_a1.setText(a1)
        self.lab_a2.setText(a2)

__all__ = ["PerformancePage"]
