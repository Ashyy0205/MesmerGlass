"""Performance monitoring page used by the Qt UI and tests.

This widget is intentionally lightweight: it can be instantiated in unit
tests without launching the full window stack.

GPU/VRAM values are sourced from the compositor (OpenGL) via `perf_metrics`
instead of OS/NVML tooling, since per-process GPU attribution is unreliable
on some Windows setups.
"""

from __future__ import annotations

import os
import subprocess
import time
import zlib
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QMessageBox,
    QStyle,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap

try:  # optional dependency
    import pyqtgraph as pg
except Exception:  # pragma: no cover
    pg = None

try:  # optional dependency
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from mesmerglass.engine.perf import PerformanceSnapshot, perf_metrics
from mesmerglass.engine.streaming_telemetry import StreamingClientSnapshot, StreamingSnapshot, streaming_telemetry


class _AudioLike(Protocol):
    def memory_usage_bytes(self) -> dict:
        ...


class _SessionRunnerLike(Protocol):
    def is_running(self) -> bool:
        ...

    def get_current_cue_index(self) -> int:
        ...

    def get_current_cue_name(self) -> Optional[str]:
        ...

    def get_current_playback_label(self) -> Optional[str]:
        ...

    def get_current_playback_path(self) -> Optional[str]:
        ...


class _SessionRunnerTabLike(Protocol):
    session_started: Any
    session_stopped: Any
    session_paused: Any
    session_resumed: Any

    @property
    def cuelist(self) -> Any:
        ...

    @property
    def session_runner(self) -> Any:
        ...


class PerformancePage(QWidget):
    """Performance dashboard widget."""

    def __init__(
        self,
        audio: Optional[_AudioLike] = None,
        parent: Optional[QWidget] = None,
        refresh_interval_ms: int = 250,
    ) -> None:
        super().__init__(parent)
        # Audio is accepted for backward compatibility, but we no longer
        # surface per-audio RAM stats here (process RAM already covers it).
        self._audio: _AudioLike | None = audio

        self._t0 = time.perf_counter()
        self._series_t = deque(maxlen=600)
        self._series_fps = deque(maxlen=600)
        self._series_avg_ms = deque(maxlen=600)
        self._series_max_ms = deque(maxlen=600)
        self._series_cpu_pct = deque(maxlen=600)
        self._series_gpu_pct = deque(maxlen=600)
        self._series_ram_mb = deque(maxlen=600)

        # Streaming telemetry series (only populated when a client is connected)
        self._stream_series: dict[str, dict[str, deque]] = {}

        self._proc = None
        self._cpu_count = 1
        self._last_cpu_t: float | None = None
        self._last_cpu_total_s: float | None = None
        self._last_proc_cpu_pct: float | None = None
        self._last_proc_rss_bytes: int | None = None
        if psutil is not None:
            try:
                self._proc = psutil.Process(os.getpid())
                self._cpu_count = int(psutil.cpu_count(logical=True) or 1)
                self._last_cpu_t = time.perf_counter()
                ct = self._proc.cpu_times()
                self._last_cpu_total_s = float(getattr(ct, "user", 0.0) + getattr(ct, "system", 0.0))
            except Exception:
                self._proc = None
                self._cpu_count = 1
                self._last_cpu_t = None
                self._last_cpu_total_s = None
                self._last_proc_cpu_pct = None
                self._last_proc_rss_bytes = None

        self._timer = QTimer(self)
        self._timer.setInterval(int(refresh_interval_ms))
        self._timer.timeout.connect(self._refresh_all)
        self.destroyed.connect(lambda *_: self._timer.stop())

        # Session-run export capture.
        self._runner_tab: _SessionRunnerTabLike | None = None
        self._capture_active = False
        self._capture_started_wall: float | None = None
        self._capture_ended_wall: float | None = None
        self._capture_samples: list[dict[str, Any]] = []
        self._last_run_samples: list[dict[str, Any]] = []
        self._last_run_meta: dict[str, Any] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.lab_heading = QLabel("Performance")
        self.lab_heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lab_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(self.lab_heading)

        # Split the page into Local vs Streaming.
        self._tabs = QTabWidget()
        self._tab_local = QWidget()
        self._tab_streaming = QWidget()
        self._tabs.addTab(self._tab_local, "Local")
        self._tabs.addTab(self._tab_streaming, "Streaming")
        layout.addWidget(self._tabs, 1)

        local_layout = QVBoxLayout(self._tab_local)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(6)

        streaming_layout = QVBoxLayout(self._tab_streaming)
        streaming_layout.setContentsMargins(0, 0, 0, 0)
        streaming_layout.setSpacing(6)

        # Summary metrics (compact)
        metrics_box = QGroupBox("Local (App / Compositor) — Live Metrics")
        metrics_layout = QGridLayout(metrics_box)
        metrics_layout.setContentsMargins(8, 8, 8, 8)
        metrics_layout.setHorizontalSpacing(12)
        metrics_layout.setVerticalSpacing(4)

        # Keep the summary block readable on wide windows.
        # Let the right column absorb extra space instead of spreading out.
        metrics_layout.setColumnStretch(0, 0)
        metrics_layout.setColumnStretch(1, 1)

        self.lab_fps = QLabel("FPS: --")
        self.lab_frame = QLabel("Frame avg/max: -- / -- ms")
        self.lab_stall = QLabel("I/O stalls: --")
        self.lab_warn = QLabel("Warnings: none")
        self.lab_proc = QLabel("Process: --")
        self.lab_gpu = QLabel("GPU: --")

        for lab in (
            self.lab_fps,
            self.lab_frame,
            self.lab_stall,
            self.lab_warn,
            self.lab_proc,
            self.lab_gpu,
        ):
            lab.setAlignment(Qt.AlignmentFlag.AlignLeft)

        metrics_layout.addWidget(self.lab_fps, 0, 0)
        metrics_layout.addWidget(self.lab_frame, 0, 1)
        metrics_layout.addWidget(self.lab_proc, 1, 0)
        metrics_layout.addWidget(self.lab_gpu, 1, 1)
        metrics_layout.addWidget(self.lab_stall, 2, 0)
        metrics_layout.addWidget(self.lab_warn, 2, 1)

        local_layout.addWidget(metrics_box)

        export_box = QGroupBox("Cuelist Run — Export")
        export_layout = QHBoxLayout(export_box)
        export_layout.setContentsMargins(8, 8, 8, 8)
        export_layout.setSpacing(8)
        self._lab_run_export = QLabel("No completed run captured yet.")
        self._lab_run_export.setAlignment(Qt.AlignmentFlag.AlignLeft)
        export_layout.addWidget(self._lab_run_export, 1)
        self._btn_export_run = QToolButton()
        self._btn_export_run.setText("Export Run Stats…")
        self._btn_export_run.setToolTip(
            "Write a text report for the most recently completed cuelist run,\n"
            "including FPS/CPU/GPU/RAM/stalls/latency and active playback per sample."
        )
        self._btn_export_run.clicked.connect(self._on_export_run_stats)
        self._btn_export_run.setEnabled(False)
        export_layout.addWidget(self._btn_export_run, 0)
        local_layout.addWidget(export_box)

        # Local charts focus state: one plot can be maximized at a time.
        self._local_focus: str | None = None
        self._local_panels: dict[str, QWidget] = {}
        self._local_focus_buttons: dict[str, QToolButton] = {}
        self._local_charts_layout: QGridLayout | None = None

        self._charts_enabled = False
        self._plot_fps = None
        self._plot_ms = None
        self._plot_usage = None
        self._plot_ram = None
        self._curve_fps = None
        self._curve_avg = None
        self._curve_max = None
        self._curve_cpu = None
        self._curve_gpu = None
        self._curve_ram = None

        if pg is None:
            lab = QLabel("Charts: unavailable (install pyqtgraph)")
            lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
            local_layout.addWidget(lab)
        else:
            try:
                self._charts_enabled = True
                charts_box = QGroupBox("Local (App / Compositor) — Charts")
                charts_layout = QGridLayout(charts_box)
                self._local_charts_layout = charts_layout
                charts_layout.setContentsMargins(8, 8, 8, 8)
                charts_layout.setHorizontalSpacing(10)
                charts_layout.setVerticalSpacing(10)

                # Palette-derived colors (avoid inventing new theme colors)
                pal = self.palette()
                c_base = pal.color(QPalette.ColorRole.Highlight)
                c_alt = pal.color(QPalette.ColorRole.Link)
                c_text = pal.color(QPalette.ColorRole.WindowText)

                # Create distinct, theme-derived line colors.
                c_cpu = c_base
                c_gpu = self._distinct_color(c_alt if c_alt.isValid() else c_base, hue_shift_deg=120)
                c_avg = c_base
                c_max = self._distinct_color(c_base, hue_shift_deg=240)

                self._plot_usage = pg.PlotWidget()
                self._plot_usage.setLabel("left", "%")
                self._plot_usage.setLabel("bottom", "Time", units="s")
                self._plot_usage.showGrid(x=True, y=True, alpha=0.25)
                try:
                    self._plot_usage.addLegend()
                except Exception:
                    pass
                self._curve_cpu = self._plot_usage.plot(pen=self._mk_pen(c_cpu, width=2), name="CPU")
                self._curve_gpu = self._plot_usage.plot(pen=self._mk_pen(c_gpu, width=2), name="GPU")
                self._plot_usage.setMinimumHeight(130)
                self._lock_plot(self._plot_usage)
                self._local_panels["usage"] = self._make_plot_panel(
                    title="CPU / GPU Usage",
                    plot=self._plot_usage,
                    key="usage",
                    on_toggle=self._set_local_focus,
                )

                self._plot_ram = pg.PlotWidget()
                self._plot_ram.setLabel("left", "MB")
                self._plot_ram.setLabel("bottom", "Time", units="s")
                self._plot_ram.showGrid(x=True, y=True, alpha=0.25)
                self._curve_ram = self._plot_ram.plot(pen=self._mk_pen(c_text, width=2))
                self._plot_ram.setMinimumHeight(130)
                self._lock_plot(self._plot_ram)
                self._local_panels["ram"] = self._make_plot_panel(
                    title="RAM Usage",
                    plot=self._plot_ram,
                    key="ram",
                    on_toggle=self._set_local_focus,
                )

                self._plot_fps = pg.PlotWidget()
                self._plot_fps.setLabel("left", "FPS")
                self._plot_fps.setLabel("bottom", "Time", units="s")
                self._plot_fps.showGrid(x=True, y=True, alpha=0.25)
                self._curve_fps = self._plot_fps.plot(pen=self._mk_pen(c_avg, width=2))
                self._plot_fps.setMinimumHeight(130)
                self._lock_plot(self._plot_fps)
                self._local_panels["fps"] = self._make_plot_panel(
                    title="Compositor FPS",
                    plot=self._plot_fps,
                    key="fps",
                    on_toggle=self._set_local_focus,
                )

                self._plot_ms = pg.PlotWidget()
                self._plot_ms.setLabel("left", "ms")
                self._plot_ms.setLabel("bottom", "Time", units="s")
                self._plot_ms.showGrid(x=True, y=True, alpha=0.25)
                try:
                    self._plot_ms.addLegend()
                except Exception:
                    pass
                self._curve_avg = self._plot_ms.plot(pen=self._mk_pen(c_avg, width=2), name="Avg")
                self._curve_max = self._plot_ms.plot(pen=self._mk_pen(c_max, width=2), name="Max")
                self._plot_ms.setMinimumHeight(130)
                self._lock_plot(self._plot_ms)
                self._local_panels["ms"] = self._make_plot_panel(
                    title="Frame Time",
                    plot=self._plot_ms,
                    key="ms",
                    on_toggle=self._set_local_focus,
                )

                # Default: start with Frame Time focused (maximized).
                self._set_local_focus("ms")

                local_layout.addWidget(charts_box)
            except Exception:
                self._charts_enabled = False
                lab = QLabel("Charts: unavailable (pyqtgraph init failed)")
                lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
                local_layout.addWidget(lab)

            self._gpu_sys_last_poll_t = 0.0
            self._gpu_sys_cache = None

        # Streaming tab state
        self._stream_focus: str | None = None
        self._stream_panels: dict[str, QWidget] = {}
        self._stream_focus_buttons: dict[str, QToolButton] = {}
        self._stream_charts_layout: QGridLayout | None = None

        # --- Streaming (VR) tab UI ---
        stream_metrics_box = QGroupBox("Streaming (VR) — Live Metrics")
        stream_metrics_v = QVBoxLayout(stream_metrics_box)
        stream_metrics_v.setContentsMargins(8, 8, 8, 8)
        stream_metrics_v.setSpacing(6)

        self._lab_stream_status = QLabel("Status: not connected")
        self._lab_stream_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        stream_metrics_v.addWidget(self._lab_stream_status)

        # Per-client table
        self._stream_clients_grid = QGridLayout()
        self._stream_clients_grid.setContentsMargins(0, 0, 0, 0)
        self._stream_clients_grid.setHorizontalSpacing(10)
        self._stream_clients_grid.setVerticalSpacing(3)

        # Avoid the table feeling "spread out" on wide windows.
        # Device column takes the slack; numeric columns stay compact.
        self._stream_clients_grid.setColumnStretch(0, 1)
        self._stream_clients_grid.setColumnStretch(1, 0)
        self._stream_clients_grid.setColumnStretch(2, 0)
        self._stream_clients_grid.setColumnStretch(3, 0)
        self._stream_clients_grid.setColumnStretch(4, 0)

        self._stream_clients_grid.setColumnMinimumWidth(1, 90)
        self._stream_clients_grid.setColumnMinimumWidth(2, 90)
        self._stream_clients_grid.setColumnMinimumWidth(3, 70)
        self._stream_clients_grid.setColumnMinimumWidth(4, 70)

        hdr_name = QLabel("Device")
        hdr_buf = QLabel("Buffer (ms)")
        hdr_fps = QLabel("Client FPS")
        hdr_bitrate = QLabel("Bitrate")
        hdr_proto = QLabel("Proto")
        for h in (hdr_name, hdr_buf, hdr_fps, hdr_bitrate, hdr_proto):
            h.setStyleSheet("font-weight: 600;")
            h.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._stream_clients_grid.addWidget(hdr_name, 0, 0)
        self._stream_clients_grid.addWidget(hdr_buf, 0, 1)
        self._stream_clients_grid.addWidget(hdr_fps, 0, 2)
        self._stream_clients_grid.addWidget(hdr_bitrate, 0, 3)
        self._stream_clients_grid.addWidget(hdr_proto, 0, 4)

        stream_metrics_v.addLayout(self._stream_clients_grid)
        self._stream_row_cells: dict[str, tuple[QLabel, QLabel, QLabel, QLabel, QLabel]] = {}

        streaming_layout.addWidget(stream_metrics_box)

        self._stream_charts_enabled = False
        self._plot_stream_buf = None
        self._plot_stream_fps = None
        self._plot_stream_enc = None
        self._plot_stream_dec = None
        self._stream_curves_buf: dict[str, object] = {}
        self._stream_curves_fps: dict[str, object] = {}
        self._stream_curves_enc: dict[str, object] = {}
        self._stream_curves_dec: dict[str, object] = {}
        self._legend_stream_buf = None
        self._legend_stream_fps = None
        self._legend_stream_enc = None
        self._legend_stream_dec = None

        if pg is None:
            lab = QLabel("Charts: unavailable (install pyqtgraph)")
            lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
            streaming_layout.addWidget(lab)
        else:
            try:
                stream_charts_box = QGroupBox("Streaming (VR) — Charts")
                charts_layout = QGridLayout(stream_charts_box)
                self._stream_charts_layout = charts_layout
                charts_layout.setContentsMargins(8, 8, 8, 8)
                charts_layout.setHorizontalSpacing(10)
                charts_layout.setVerticalSpacing(10)

                self._plot_stream_fps = pg.PlotWidget()
                self._plot_stream_fps.setLabel("left", "FPS")
                self._plot_stream_fps.setLabel("bottom", "Time", units="s")
                self._plot_stream_fps.showGrid(x=True, y=True, alpha=0.25)
                try:
                    self._legend_stream_fps = self._plot_stream_fps.addLegend(offset=(10, 10))
                    if hasattr(self._legend_stream_fps, "setLabelTextSize"):
                        self._legend_stream_fps.setLabelTextSize("8pt")
                except Exception:
                    pass
                self._plot_stream_fps.setMinimumHeight(130)
                self._lock_plot(self._plot_stream_fps)
                self._stream_panels["fps"] = self._make_plot_panel(
                    title="Client FPS",
                    plot=self._plot_stream_fps,
                    key="fps",
                    on_toggle=self._set_stream_focus,
                    target="stream",
                )

                self._plot_stream_buf = pg.PlotWidget()
                self._plot_stream_buf.setLabel("left", "ms")
                self._plot_stream_buf.setLabel("bottom", "Time", units="s")
                self._plot_stream_buf.showGrid(x=True, y=True, alpha=0.25)
                try:
                    self._legend_stream_buf = self._plot_stream_buf.addLegend(offset=(10, 10))
                    if hasattr(self._legend_stream_buf, "setLabelTextSize"):
                        self._legend_stream_buf.setLabelTextSize("8pt")
                except Exception:
                    pass
                self._plot_stream_buf.setMinimumHeight(130)
                self._lock_plot(self._plot_stream_buf)
                self._stream_panels["buf"] = self._make_plot_panel(
                    title="Client Buffer",
                    plot=self._plot_stream_buf,
                    key="buf",
                    on_toggle=self._set_stream_focus,
                    target="stream",
                )

                self._plot_stream_enc = pg.PlotWidget()
                self._plot_stream_enc.setLabel("left", "ms")
                self._plot_stream_enc.setLabel("bottom", "Time", units="s")
                self._plot_stream_enc.showGrid(x=True, y=True, alpha=0.25)
                try:
                    self._legend_stream_enc = self._plot_stream_enc.addLegend(offset=(10, 10))
                    if hasattr(self._legend_stream_enc, "setLabelTextSize"):
                        self._legend_stream_enc.setLabelTextSize("8pt")
                except Exception:
                    pass
                self._plot_stream_enc.setMinimumHeight(130)
                self._lock_plot(self._plot_stream_enc)
                self._stream_panels["enc"] = self._make_plot_panel(
                    title="Encode Time",
                    plot=self._plot_stream_enc,
                    key="enc",
                    on_toggle=self._set_stream_focus,
                    target="stream",
                )

                self._plot_stream_dec = pg.PlotWidget()
                self._plot_stream_dec.setLabel("left", "ms")
                self._plot_stream_dec.setLabel("bottom", "Time", units="s")
                self._plot_stream_dec.showGrid(x=True, y=True, alpha=0.25)
                try:
                    self._legend_stream_dec = self._plot_stream_dec.addLegend(offset=(10, 10))
                    if hasattr(self._legend_stream_dec, "setLabelTextSize"):
                        self._legend_stream_dec.setLabelTextSize("8pt")
                except Exception:
                    pass
                self._plot_stream_dec.setMinimumHeight(130)
                self._lock_plot(self._plot_stream_dec)
                self._stream_panels["dec"] = self._make_plot_panel(
                    title="Decode Time",
                    plot=self._plot_stream_dec,
                    key="dec",
                    on_toggle=self._set_stream_focus,
                    target="stream",
                )

                # Default: start with Client Buffer focused (maximized).
                self._set_stream_focus("buf")
                streaming_layout.addWidget(stream_charts_box)
                self._stream_charts_enabled = True
            except Exception:
                lab = QLabel("Charts: unavailable (pyqtgraph init failed)")
                lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
                streaming_layout.addWidget(lab)
                self._stream_charts_enabled = False

        self._timer.start()
        self._refresh_all()

    def bind_session_runner_tab(self, runner_tab: _SessionRunnerTabLike) -> None:
        """Bind to SessionRunnerTab lifecycle so we can capture per-run logs."""
        self._runner_tab = runner_tab
        try:
            runner_tab.session_started.connect(self._on_session_started)
            runner_tab.session_stopped.connect(self._on_session_stopped)
        except Exception:
            # Best-effort binding.
            self._runner_tab = None

    def _on_session_started(self) -> None:
        self._capture_active = True
        self._capture_started_wall = time.time()
        self._capture_ended_wall = None
        self._capture_samples = []
        try:
            cuelist = getattr(self._runner_tab, "cuelist", None) if self._runner_tab else None
            cuelist_name = str(getattr(cuelist, "name", "")) if cuelist else ""
        except Exception:
            cuelist_name = ""
        self._lab_run_export.setText(f"Capturing run… {cuelist_name}" if cuelist_name else "Capturing run…")
        self._btn_export_run.setEnabled(False)

    def _on_session_stopped(self) -> None:
        if self._capture_active:
            self._capture_active = False
            self._capture_ended_wall = time.time()
            self._last_run_samples = list(self._capture_samples)

            cuelist = getattr(self._runner_tab, "cuelist", None) if self._runner_tab else None
            cuelist_name = str(getattr(cuelist, "name", "")) if cuelist else ""
            duration_s = None
            if self._capture_started_wall is not None and self._capture_ended_wall is not None:
                duration_s = max(0.0, float(self._capture_ended_wall - self._capture_started_wall))
            self._last_run_meta = {
                "cuelist": cuelist_name,
                "started_wall": self._capture_started_wall,
                "ended_wall": self._capture_ended_wall,
                "duration_wall_s": duration_s,
                "sample_count": len(self._last_run_samples),
                "sample_interval_ms": int(self._timer.interval()),
            }

            if self._last_run_samples:
                self._lab_run_export.setText(
                    f"Last run captured: {cuelist_name} ({len(self._last_run_samples)} samples)"
                    if cuelist_name
                    else f"Last run captured ({len(self._last_run_samples)} samples)"
                )
                self._btn_export_run.setEnabled(True)
            else:
                self._lab_run_export.setText("Run ended, but no samples were captured.")
                self._btn_export_run.setEnabled(False)

    def _capture_run_sample(self, snap: PerformanceSnapshot) -> None:
        if not self._capture_active:
            return

        runner: _SessionRunnerLike | None = None
        cuelist = None
        try:
            if self._runner_tab is not None:
                runner = getattr(self._runner_tab, "session_runner", None)
                cuelist = getattr(self._runner_tab, "cuelist", None)
        except Exception:
            runner = None
            cuelist = None

        # Only capture while the runner exists.
        if runner is None:
            return

        # Create a stable wall-clock timestamp string for the report.
        wall = time.time()
        try:
            wall_iso = datetime.fromtimestamp(wall).isoformat(timespec="seconds")
        except Exception:
            wall_iso = ""

        t_run_s = None
        if self._capture_started_wall is not None:
            try:
                t_run_s = max(0.0, float(wall - self._capture_started_wall))
            except Exception:
                t_run_s = None

        cue_idx = None
        cue_name = None
        playback_label = None
        playback_path = None
        try:
            cue_idx = int(runner.get_current_cue_index())
        except Exception:
            cue_idx = None
        try:
            cue_name = runner.get_current_cue_name()
        except Exception:
            cue_name = None
        try:
            playback_label = runner.get_current_playback_label()
        except Exception:
            playback_label = None
        try:
            playback_path = runner.get_current_playback_path()
        except Exception:
            playback_path = None

        cuelist_name = None
        try:
            cuelist_name = str(getattr(cuelist, "name", "")) if cuelist else None
        except Exception:
            cuelist_name = None

        rss_mb = None
        if self._last_proc_rss_bytes is not None:
            rss_mb = float(self._last_proc_rss_bytes) / (1024.0 * 1024.0)

        sample = {
            "wall_iso": wall_iso,
            "t_rel_s": float(time.perf_counter() - self._t0),
            "t_run_s": float(t_run_s) if t_run_s is not None else None,
            "cuelist": cuelist_name,
            "cue_index": cue_idx,
            "cue_name": cue_name,
            "playback": playback_label,
            "playback_path": playback_path,
            "fps": float(snap.fps or 0.0),
            "avg_frame_ms": float(snap.avg_frame_ms or 0.0),
            "max_frame_ms": float(snap.max_frame_ms or 0.0),
            "gpu_avg_ms": float(snap.gpu_avg_ms or 0.0),
            "gpu_max_ms": float(snap.gpu_max_ms or 0.0),
            "gpu_busy_pct": float(snap.gpu_busy_pct or 0.0),
            "gpu_vram_used_mb": float(snap.gpu_vram_used_mb or 0.0),
            "gpu_vram_total_mb": float(snap.gpu_vram_total_mb or 0.0),
            "gpu_util_pct_sys": float(self._get_system_gpu_util_pct() or 0.0),
            "cpu_pct_proc": float(self._last_proc_cpu_pct or 0.0),
            "ram_mb_proc": float(rss_mb or 0.0),
            "stall_count": int(snap.stall_count or 0),
            "last_stall_ms": float(snap.last_stall_ms or 0.0),
            "warnings": "; ".join(list(snap.warnings or [])),
        }
        self._capture_samples.append(sample)

    def _on_export_run_stats(self) -> None:
        if not self._last_run_samples:
            QMessageBox.information(self, "Export Run Stats", "No completed run data to export yet.")
            return

        cuelist_name = str(self._last_run_meta.get("cuelist") or "cuelist")
        default_name = f"{cuelist_name}_perf_{time.strftime('%Y%m%d_%H%M%S')}.txt".replace("/", "-").replace("\\\\", "-")
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Cuelist Run Stats",
            default_name,
            "Text File (*.txt);;All Files (*)",
        )
        if not out_path:
            return

        try:
            lines: list[str] = []
            lines.append("MesmerGlass — Cuelist Run Performance Report")
            lines.append(f"Cuelist: {self._last_run_meta.get('cuelist') or ''}")
            lines.append(f"Samples: {self._last_run_meta.get('sample_count', 0)}")
            lines.append(f"Sample interval: {self._last_run_meta.get('sample_interval_ms', 0)} ms")
            dur = self._last_run_meta.get("duration_wall_s")
            if dur is not None:
                lines.append(f"Wall duration: {float(dur):.1f} s")
            lines.append("")
            lines.append(
                "\t".join(
                    [
                        "wall_time",
                        "t_rel_s",
                        "t_run_s",
                        "cue_index",
                        "cue_name",
                        "playback",
                        "fps",
                        "avg_frame_ms",
                        "max_frame_ms",
                        "cpu_pct_proc",
                        "ram_mb_proc",
                        "gpu_util_pct_sys",
                        "gpu_avg_ms",
                        "gpu_max_ms",
                        "gpu_busy_pct",
                        "gpu_vram_used_mb",
                        "gpu_vram_total_mb",
                        "stall_count",
                        "last_stall_ms",
                        "warnings",
                        "playback_path",
                    ]
                )
            )

            for s in self._last_run_samples:
                t_run_s_val = s.get("t_run_s")
                lines.append(
                    "\t".join(
                        [
                            str(s.get("wall_iso") or ""),
                            f"{float(s.get('t_rel_s') or 0.0):.3f}",
                            (f"{float(t_run_s_val):.3f}" if t_run_s_val is not None else ""),
                            str(s.get("cue_index") if s.get("cue_index") is not None else ""),
                            str(s.get("cue_name") or ""),
                            str(s.get("playback") or ""),
                            f"{float(s.get('fps') or 0.0):.2f}",
                            f"{float(s.get('avg_frame_ms') or 0.0):.2f}",
                            f"{float(s.get('max_frame_ms') or 0.0):.2f}",
                            f"{float(s.get('cpu_pct_proc') or 0.0):.1f}",
                            f"{float(s.get('ram_mb_proc') or 0.0):.1f}",
                            f"{float(s.get('gpu_util_pct_sys') or 0.0):.1f}",
                            f"{float(s.get('gpu_avg_ms') or 0.0):.2f}",
                            f"{float(s.get('gpu_max_ms') or 0.0):.2f}",
                            f"{float(s.get('gpu_busy_pct') or 0.0):.1f}",
                            f"{float(s.get('gpu_vram_used_mb') or 0.0):.1f}",
                            f"{float(s.get('gpu_vram_total_mb') or 0.0):.1f}",
                            str(int(s.get("stall_count") or 0)),
                            f"{float(s.get('last_stall_ms') or 0.0):.1f}",
                            str(s.get("warnings") or ""),
                            str(s.get("playback_path") or ""),
                        ]
                    )
                )

            Path(out_path).write_text("\n".join(lines), encoding="utf-8")
            QMessageBox.information(self, "Export Run Stats", f"Wrote report:\n{out_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Run Stats", f"Export failed: {exc}")

    def _refresh_all(self) -> None:
        snap = perf_metrics.snapshot()
        self._refresh_perf_section(snap)
        self._refresh_proc_section()
        self._refresh_gpu_section(snap)
        self._refresh_streaming_section()
        self._append_series(snap)
        self._capture_run_sample(snap)
        self._refresh_charts()

    def _refresh_perf_section(self, snap: PerformanceSnapshot) -> None:
        self.lab_fps.setText(f"FPS: {snap.fps:.1f}" if snap.fps else "FPS: --")
        if snap.avg_frame_ms is not None and snap.max_frame_ms is not None:
            self.lab_frame.setText(
                f"Frame avg/max: {snap.avg_frame_ms:.1f} / {snap.max_frame_ms:.1f} ms"
            )
        else:
            self.lab_frame.setText("Frame avg/max: -- / -- ms")

        stall_text = "I/O stalls: --"
        if snap.stall_count:
            last = f", last {snap.last_stall_ms:.0f} ms" if snap.last_stall_ms else ""
            stall_text = f"I/O stalls: {snap.stall_count}{last}"
        self.lab_stall.setText(stall_text)

        self.lab_warn.setText(
            "Warnings: " + ("; ".join(snap.warnings) if snap.warnings else "none")
        )

    def _append_series(self, snap: PerformanceSnapshot) -> None:
        t = time.perf_counter() - self._t0
        self._series_t.append(t)
        self._series_fps.append(float(snap.fps or 0.0))
        self._series_avg_ms.append(float(snap.avg_frame_ms or 0.0))
        self._series_max_ms.append(float(snap.max_frame_ms or 0.0))
        self._series_cpu_pct.append(float(self._last_proc_cpu_pct or 0.0))
        self._series_gpu_pct.append(float(self._get_system_gpu_util_pct() or 0.0))
        rss_mb = 0.0
        if self._last_proc_rss_bytes is not None:
            rss_mb = float(self._last_proc_rss_bytes) / (1024.0 * 1024.0)
        self._series_ram_mb.append(rss_mb)

        # Streaming series: append per connected client.
        try:
            s = streaming_telemetry.snapshot()
            connected_clients = [c for c in (s.clients or []) if c.connected]
            for c in connected_clients:
                st = self._stream_series.get(c.client_id)
                if st is None:
                    st = {
                        "t": deque(maxlen=600),
                        "buf_ms": deque(maxlen=600),
                        "fps": deque(maxlen=600),
                        "enc_ms": deque(maxlen=600),
                        "dec_ms": deque(maxlen=600),
                    }
                    self._stream_series[c.client_id] = st

                st["t"].append(t)
                st["buf_ms"].append(float(c.client_buffer_ms or 0.0))
                fps_val = 0.0
                if c.client_fps_milli is not None and c.client_fps_milli > 0:
                    fps_val = float(c.client_fps_milli) / 1000.0
                st["fps"].append(float(fps_val))

                # Encode/decode latency (carry-forward last value if missing).
                if c.encode_avg_ms is not None:
                    enc_val = float(c.encode_avg_ms)
                else:
                    enc_val = float(st["enc_ms"][-1]) if len(st["enc_ms"]) else 0.0
                st["enc_ms"].append(enc_val)

                dec_field = getattr(c, "client_decode_avg_ms", None)
                if dec_field is not None:
                    dec_val = float(dec_field)
                else:
                    dec_val = float(st["dec_ms"][-1]) if len(st["dec_ms"]) else 0.0
                st["dec_ms"].append(dec_val)
        except Exception:
            pass

    def _refresh_streaming_section(self) -> None:
        try:
            ss: StreamingSnapshot = streaming_telemetry.snapshot()
            clients: list[StreamingClientSnapshot] = list(ss.clients or [])
        except Exception:
            clients = []

        connected_clients = [c for c in clients if c.connected]
        connected = bool(connected_clients)

        if not connected:
            self._lab_stream_status.setText("Status: not connected")
        else:
            n = len(connected_clients)
            label = "client" if n == 1 else "clients"
            self._lab_stream_status.setText(f"Status: connected ({n} {label})")

        self._refresh_stream_client_rows(connected_clients)

        if self._stream_charts_enabled:
            self._refresh_streaming_charts(connected_clients)

    def _refresh_stream_client_rows(self, clients: list[StreamingClientSnapshot]) -> None:
        # Remove stale rows
        want = {c.client_id for c in clients}
        stale = [cid for cid in list(self._stream_row_cells.keys()) if cid not in want]
        for cid in stale:
            cells = self._stream_row_cells.pop(cid)
            for w in cells:
                try:
                    self._stream_clients_grid.removeWidget(w)
                    w.deleteLater()
                except Exception:
                    pass

        # Add/update rows
        for row_index, c in enumerate(clients, start=1):
            name = c.device_name or c.address or c.client_id
            proto = c.protocol or "--"

            bitrate = "--"
            if c.bitrate_bps is not None and c.bitrate_bps > 0:
                bitrate = f"{(float(c.bitrate_bps) / 1_000_000.0):.1f}"

            buf = "--"
            if c.client_buffer_ms is not None:
                buf = f"{int(c.client_buffer_ms)}"

            fps = "--"
            if c.client_fps_milli is not None and c.client_fps_milli > 0:
                fps = f"{(float(c.client_fps_milli) / 1000.0):.2f}"

            cells = self._stream_row_cells.get(c.client_id)
            if cells is None:
                lab_name = QLabel()
                lab_buf = QLabel()
                lab_fps = QLabel()
                lab_bitrate = QLabel()
                lab_proto = QLabel()
                for w in (lab_name, lab_buf, lab_fps, lab_bitrate, lab_proto):
                    w.setAlignment(Qt.AlignmentFlag.AlignLeft)
                cells = (lab_name, lab_buf, lab_fps, lab_bitrate, lab_proto)
                self._stream_row_cells[c.client_id] = cells

            cells[0].setText(name)
            cells[1].setText(buf)
            cells[2].setText(fps)
            cells[3].setText(bitrate)
            cells[4].setText(proto)

            self._stream_clients_grid.addWidget(cells[0], row_index, 0)
            self._stream_clients_grid.addWidget(cells[1], row_index, 1)
            self._stream_clients_grid.addWidget(cells[2], row_index, 2)
            self._stream_clients_grid.addWidget(cells[3], row_index, 3)
            self._stream_clients_grid.addWidget(cells[4], row_index, 4)

    def _client_color(self, client_id: str, base_color) -> "QColor":
        # Deterministic hue shift based on client_id.
        try:
            shift = int(zlib.crc32(client_id.encode("utf-8")) % 300) + 30
            return self._distinct_color(base_color, hue_shift_deg=shift)
        except Exception:
            return base_color

    def _refresh_streaming_charts(self, clients: list[StreamingClientSnapshot]) -> None:
        # Remove stale curves
        want = {c.client_id for c in clients}
        stale = [cid for cid in list(self._stream_curves_buf.keys()) if cid not in want]
        for cid in stale:
            try:
                self._plot_stream_buf.removeItem(self._stream_curves_buf[cid])
            except Exception:
                pass
            try:
                self._plot_stream_fps.removeItem(self._stream_curves_fps[cid])
            except Exception:
                pass
            try:
                self._plot_stream_enc.removeItem(self._stream_curves_enc[cid])
            except Exception:
                pass
            try:
                self._plot_stream_dec.removeItem(self._stream_curves_dec[cid])
            except Exception:
                pass
            self._stream_curves_buf.pop(cid, None)
            self._stream_curves_fps.pop(cid, None)
            self._stream_curves_enc.pop(cid, None)
            self._stream_curves_dec.pop(cid, None)

        pal = self.palette()
        c_base = pal.color(QPalette.ColorRole.Highlight)
        c_alt = pal.color(QPalette.ColorRole.Link)
        base = c_alt if c_alt.isValid() else c_base

        # Ensure curves exist for each client
        for c in clients:
            name = c.device_name or c.address or c.client_id
            if c.client_id not in self._stream_curves_buf:
                col = self._client_color(c.client_id, base)
                self._stream_curves_buf[c.client_id] = self._plot_stream_buf.plot(
                    pen=self._mk_pen(col, width=2),
                    name=name,
                )
                self._stream_curves_fps[c.client_id] = self._plot_stream_fps.plot(
                    pen=self._mk_pen(col, width=2),
                    name=name,
                )
                self._stream_curves_enc[c.client_id] = self._plot_stream_enc.plot(
                    pen=self._mk_pen(col, width=2),
                    name=name,
                )
                self._stream_curves_dec[c.client_id] = self._plot_stream_dec.plot(
                    pen=self._mk_pen(col, width=2),
                    name=name,
                )

        # Make legends fit multiple clients.
        try:
            n = max(1, len(clients))
            cols = min(3, n)
            for legend in (
                self._legend_stream_buf,
                self._legend_stream_fps,
                self._legend_stream_enc,
                self._legend_stream_dec,
            ):
                if legend is None:
                    continue
                if hasattr(legend, "setColumnCount"):
                    legend.setColumnCount(int(cols))
        except Exception:
            pass

        # Update data
        x_max = None
        for c in clients:
            st = self._stream_series.get(c.client_id)
            if not st:
                continue
            xs = list(st["t"])
            if xs:
                x_max = xs[-1] if x_max is None else max(x_max, xs[-1])
            self._stream_curves_buf[c.client_id].setData(xs, list(st["buf_ms"]))
            self._stream_curves_fps[c.client_id].setData(xs, list(st["fps"]))
            self._stream_curves_enc[c.client_id].setData(xs, list(st["enc_ms"]))
            self._stream_curves_dec[c.client_id].setData(xs, list(st["dec_ms"]))

        if x_max is None:
            return

        x_min = max(0.0, float(x_max) - 60.0)
        for plot in (
            self._plot_stream_buf,
            self._plot_stream_fps,
            self._plot_stream_enc,
            self._plot_stream_dec,
        ):
            if plot is None:
                continue
            plot.setXRange(x_min, float(x_max), padding=0.0)

    def _make_plot_panel(
        self,
        title: str,
        plot: "pg.PlotWidget",
        key: str,
        on_toggle: Callable[[str | None], None],
        target: str = "local",
    ) -> QWidget:
        """Wrap a PlotWidget in a small header + Max/Restore button panel."""

        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(2, 0, 2, 0)
        hl.setSpacing(8)

        lab = QLabel(title)
        lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lab.setStyleSheet("font-weight: 600;")

        btn = QToolButton()
        self._set_titlebar_icon(btn, QStyle.StandardPixmap.SP_TitleBarMaxButton)
        btn.setToolTip("Maximize")
        btn.setCheckable(True)
        btn.setChecked(False)
        # Icon-only but with a visible button chrome (auto-raise makes it too subtle).
        btn.setAutoRaise(False)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(QSize(26, 22))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_icon_button(btn)

        def _handle(checked: bool) -> None:
            # If checked, this becomes the focused plot. If unchecked and it
            # was focused, restore default layout.
            if checked:
                on_toggle(key)
            else:
                on_toggle(None)

        btn.toggled.connect(_handle)

        hl.addWidget(lab, 1)
        hl.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)
        v.addWidget(header)
        v.addWidget(plot)

        if target == "local":
            self._local_focus_buttons[key] = btn
        else:
            self._stream_focus_buttons[key] = btn

        return panel

    def _set_titlebar_icon(self, btn: QToolButton, which: QStyle.StandardPixmap) -> None:
        # Windows titlebar standard icons can be low-contrast on dark themes.
        # Render then tint to white for maximum contrast (user preference).
        base_icon: QIcon = self.style().standardIcon(which)
        size = btn.iconSize()
        if size.isEmpty():
            size = QSize(16, 16)

        try:
            pm = base_icon.pixmap(size)
            if pm.isNull():
                btn.setIcon(base_icon)
                return

            tinted = QPixmap(pm.size())
            tinted.fill(Qt.GlobalColor.transparent)
            p = QPainter(tinted)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawPixmap(0, 0, pm)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(tinted.rect(), QColor(255, 255, 255))
            p.end()
            btn.setIcon(QIcon(tinted))
        except Exception:
            btn.setIcon(base_icon)

    def _style_icon_button(self, btn: QToolButton) -> None:
        # Use palette-derived colors to stay consistent with the app theme.
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        alt = pal.color(QPalette.ColorRole.AlternateBase)
        mid = pal.color(QPalette.ColorRole.Mid)
        hi = pal.color(QPalette.ColorRole.Highlight)
        if not alt.isValid():
            alt = base.lighter(110)

        def _hex(c: QColor) -> str:
            return c.name(QColor.NameFormat.HexArgb)

        btn.setStyleSheet(
            "QToolButton {"
            f"background: {_hex(base)};"
            f"border: 1px solid {_hex(mid)};"
            "border-radius: 4px;"
            "padding: 0px;"
            "}"
            "QToolButton:hover {"
            f"background: {_hex(alt)};"
            f"border-color: {_hex(hi)};"
            "}"
            "QToolButton:checked {"
            f"border-color: {_hex(hi)};"
            "}"
        )

    def _set_local_focus(self, key: str | None) -> None:
        if key == self._local_focus:
            key = None
        self._local_focus = key
        for k, btn in self._local_focus_buttons.items():
            want = (k == key)
            if btn.isChecked() != want:
                btn.blockSignals(True)
                btn.setChecked(want)
                btn.blockSignals(False)
            if want:
                self._set_titlebar_icon(btn, QStyle.StandardPixmap.SP_TitleBarNormalButton)
                btn.setToolTip("Restore")
            else:
                self._set_titlebar_icon(btn, QStyle.StandardPixmap.SP_TitleBarMaxButton)
                btn.setToolTip("Maximize")
        self._apply_local_chart_layout()

    def _apply_local_chart_layout(self) -> None:
        if self._local_charts_layout is None:
            return

        gl = self._local_charts_layout
        for p in self._local_panels.values():
            try:
                gl.removeWidget(p)
            except Exception:
                pass

        if self._local_focus is None:
            # Default 2x2
            gl.setRowStretch(0, 1)
            gl.setRowStretch(1, 1)
            gl.setRowStretch(2, 0)
            gl.setColumnStretch(0, 1)
            gl.setColumnStretch(1, 1)
            gl.addWidget(self._local_panels["usage"], 0, 0)
            gl.addWidget(self._local_panels["ram"], 0, 1)
            gl.addWidget(self._local_panels["fps"], 1, 0)
            gl.addWidget(self._local_panels["ms"], 1, 1)
            return

        # Focused: big plot on left, three small stacked on right.
        focus = self._local_focus
        others = [k for k in ("usage", "ram", "fps", "ms") if k != focus]

        gl.setColumnStretch(0, 3)
        gl.setColumnStretch(1, 1)
        gl.setRowStretch(0, 1)
        gl.setRowStretch(1, 1)
        gl.setRowStretch(2, 1)

        gl.addWidget(self._local_panels[focus], 0, 0, 3, 1)
        gl.addWidget(self._local_panels[others[0]], 0, 1)
        gl.addWidget(self._local_panels[others[1]], 1, 1)
        gl.addWidget(self._local_panels[others[2]], 2, 1)

    def _set_stream_focus(self, key: str | None) -> None:
        if key == self._stream_focus:
            key = None
        self._stream_focus = key
        for k, btn in self._stream_focus_buttons.items():
            want = (k == key)
            if btn.isChecked() != want:
                btn.blockSignals(True)
                btn.setChecked(want)
                btn.blockSignals(False)
            if want:
                self._set_titlebar_icon(btn, QStyle.StandardPixmap.SP_TitleBarNormalButton)
                btn.setToolTip("Restore")
            else:
                self._set_titlebar_icon(btn, QStyle.StandardPixmap.SP_TitleBarMaxButton)
                btn.setToolTip("Maximize")
        self._apply_stream_chart_layout()

    def _apply_stream_chart_layout(self) -> None:
        if self._stream_charts_layout is None:
            return
        if not self._stream_panels:
            return

        gl = self._stream_charts_layout
        for p in self._stream_panels.values():
            try:
                gl.removeWidget(p)
            except Exception:
                pass

        order = [k for k in ("buf", "fps", "enc", "dec") if k in self._stream_panels]

        if self._stream_focus is None or self._stream_focus not in self._stream_panels:
            # Default 2x2
            gl.setRowStretch(0, 1)
            gl.setRowStretch(1, 1)
            gl.setRowStretch(2, 0)
            gl.setColumnStretch(0, 1)
            gl.setColumnStretch(1, 1)

            if len(order) >= 1:
                gl.addWidget(self._stream_panels[order[0]], 0, 0)
            if len(order) >= 2:
                gl.addWidget(self._stream_panels[order[1]], 0, 1)
            if len(order) >= 3:
                gl.addWidget(self._stream_panels[order[2]], 1, 0)
            if len(order) >= 4:
                gl.addWidget(self._stream_panels[order[3]], 1, 1)
            return

        focus = self._stream_focus
        others = [k for k in order if k != focus]

        gl.setColumnStretch(0, 3)
        gl.setColumnStretch(1, 1)
        gl.setRowStretch(0, 1)
        gl.setRowStretch(1, 1)
        gl.setRowStretch(2, 1)

        gl.addWidget(self._stream_panels[focus], 0, 0, 3, 1)
        if len(others) >= 1:
            gl.addWidget(self._stream_panels[others[0]], 0, 1)
        if len(others) >= 2:
            gl.addWidget(self._stream_panels[others[1]], 1, 1)
        if len(others) >= 3:
            gl.addWidget(self._stream_panels[others[2]], 2, 1)

    def _refresh_proc_section(self) -> None:
        if psutil is None or self._proc is None:
            self.lab_proc.setText("Process: unavailable")
            self._last_proc_cpu_pct = None
            self._last_proc_rss_bytes = None
            return

        try:
            # Task Manager-style per-process CPU (0..100) based on CPU time deltas.
            now = time.perf_counter()
            proc_cpu = 0.0
            if self._last_cpu_t is not None and self._last_cpu_total_s is not None:
                dt = now - self._last_cpu_t
                ct = self._proc.cpu_times()
                total_s = float(getattr(ct, "user", 0.0) + getattr(ct, "system", 0.0))
                dcpu = total_s - self._last_cpu_total_s
                if dt > 1e-6 and dcpu >= 0.0:
                    proc_cpu = (dcpu / dt) / max(1, int(self._cpu_count)) * 100.0
                self._last_cpu_t = now
                self._last_cpu_total_s = total_s

            mem = self._proc.memory_info()
            rss = int(getattr(mem, "rss", 0) or 0)
            vms = int(getattr(mem, "vms", 0) or 0)
            self._last_proc_cpu_pct = float(proc_cpu)
            self._last_proc_rss_bytes = rss
            self.lab_proc.setText(
                f"Process: CPU {proc_cpu:.0f}% | RAM {self._format_bytes(rss)} | VMS {self._format_bytes(vms)}"
            )
        except Exception:
            self.lab_proc.setText("Process: unavailable")
            self._last_proc_cpu_pct = None
            self._last_proc_rss_bytes = None

    def _refresh_gpu_section(self, snap: PerformanceSnapshot) -> None:
        parts: list[str] = ["GPU:"]

        # Prefer a reliable system-level utilization percent for now.
        # (Per-app GPU attribution is not consistently available on Windows.)
        sys_pct = self._get_system_gpu_util_pct()
        if sys_pct is not None:
            parts.append(f"System {sys_pct:.0f}%")
        elif snap.gpu_busy_pct is not None:
            parts.append(f"Busy {snap.gpu_busy_pct:.0f}%")

        if snap.gpu_avg_ms is not None:
            parts.append(f"GPU {snap.gpu_avg_ms:.1f} ms")
        if snap.gpu_vram_used_mb is not None and snap.gpu_vram_total_mb is not None:
            parts.append(f"VRAM {snap.gpu_vram_used_mb:.0f}/{snap.gpu_vram_total_mb:.0f} MB")
        elif snap.gpu_vram_total_mb is not None:
            parts.append(f"VRAM {snap.gpu_vram_total_mb:.0f} MB")

        self.lab_gpu.setText("GPU: --" if len(parts) == 1 else " ".join(parts))

    def _get_system_gpu_util_pct(self) -> float | None:
        # Cache to avoid subprocess overhead at UI refresh rate.
        now = time.perf_counter()
        if now - self._gpu_sys_last_poll_t < 1.0:
            return float(self._gpu_sys_cache) if self._gpu_sys_cache is not None else None

        self._gpu_sys_last_poll_t = now
        self._gpu_sys_cache = None

        if os.name != "nt":
            return None

        # NVIDIA only: nvidia-smi provides reliable system-wide utilization.
        try:
            r = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=0.5,
            )
            if r.returncode != 0:
                return None
            line = (r.stdout or "").strip().splitlines()[0].strip()
            pct = float(line)
            self._gpu_sys_cache = str(pct)
            return pct
        except Exception:
            return None

    def _refresh_charts(self) -> None:
        if not self._charts_enabled:
            return
        if not (self._curve_fps and self._curve_avg and self._curve_max):
            return

        try:
            xs = list(self._series_t)
            # Keep a fixed visible window (last ~60 seconds) for all plots.
            if xs:
                x_max = xs[-1]
                x_min = max(0.0, x_max - 60.0)
            else:
                x_min, x_max = 0.0, 60.0

            self._curve_fps.setData(xs, list(self._series_fps))
            self._curve_avg.setData(xs, list(self._series_avg_ms))
            self._curve_max.setData(xs, list(self._series_max_ms))
            if self._curve_cpu is not None:
                self._curve_cpu.setData(xs, list(self._series_cpu_pct))
            if self._curve_gpu is not None:
                self._curve_gpu.setData(xs, list(self._series_gpu_pct))
            if self._curve_ram is not None:
                self._curve_ram.setData(xs, list(self._series_ram_mb))

            for plot in (self._plot_usage, self._plot_ram, self._plot_fps, self._plot_ms):
                if plot is None:
                    continue
                plot.setXRange(x_min, x_max, padding=0.0)
        except Exception:
            # Best-effort: ignore transient plot issues.
            pass

    @staticmethod
    def _lock_plot(plot) -> None:
        """Disable interactions to keep plots fixed (no pan/zoom/scroll/menu)."""
        try:
            pi = plot.getPlotItem()
            try:
                pi.setMenuEnabled(False)
            except Exception:
                pass
            try:
                pi.hideButtons()
            except Exception:
                pass
            try:
                vb = pi.vb
                vb.setMouseEnabled(x=False, y=False)
                if hasattr(vb, "setWheelEnabled"):
                    vb.setWheelEnabled(False)
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def _mk_pen(color, *, width: int = 2, style: Qt.PenStyle = Qt.PenStyle.SolidLine):
        try:
            return pg.mkPen(color=color, width=width, style=style)
        except Exception:
            return pg.mkPen(width=width, style=style)

    @staticmethod
    def _distinct_color(color, *, hue_shift_deg: int) -> "QColor":
        """Return a theme-derived color shifted in hue to be more distinct.

        Avoids hard-coded hex colors while ensuring we don't end up with two
        nearly identical shades (e.g., red vs darker red).
        """
        try:
            from PyQt6.QtGui import QColor

            if not isinstance(color, QColor):
                return color
            if not color.isValid():
                return color

            h, s, v, a = color.getHsv()
            if h < 0:
                # grayscale; pick a mid saturation derived from value
                h = 200
                s = max(80, min(200, int(v * 0.6)))

            h2 = (int(h) + int(hue_shift_deg)) % 360

            # Avoid red-ish hues (roughly 345..15)
            if h2 >= 345 or h2 <= 15:
                h2 = (h2 + 40) % 360

            s2 = max(90, min(255, int(s) if s > 0 else 160))
            v2 = max(140, min(255, int(v) if v > 0 else 220))
            out = QColor.fromHsv(h2, s2, v2, a)
            return out
        except Exception:
            return color

    @staticmethod
    def _format_bytes(n: int) -> str:
        n = int(n or 0)
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024.0:.1f} KB"
        if n < 1024 * 1024 * 1024:
            return f"{n / (1024.0 * 1024.0):.1f} MB"
        return f"{n / (1024.0 * 1024.0 * 1024.0):.2f} GB"