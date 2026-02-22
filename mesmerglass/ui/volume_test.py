"""Live volume test panel.

Two modes:
- Attached (normal app): a small panel that controls the *real* app AudioEngine.
    Enabled via `python run.py --volume-test`.
- Standalone (dev): creates its own AudioEngine and plays test tones.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QPushButton,
    QFileDialog,
)

from mesmerglass.engine.audio import AudioEngine


@dataclass(frozen=True)
class _ToneSpec:
    channel: int
    freq_hz: float
    label: str


def _generate_sine_int16_stereo(
    *,
    duration_s: float,
    sample_rate: int,
    freq_hz: float,
    peak: float = 0.15,
) -> np.ndarray:
    n = int(max(1, round(duration_s * sample_rate)))
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    wave = np.sin(2.0 * np.pi * float(freq_hz) * t)
    amp = np.clip(float(peak), 0.0, 1.0)
    mono = (wave * (amp * 32767.0)).astype(np.int16)
    stereo = np.column_stack([mono, mono])
    return stereo


class VolumePanel(QWidget):
    """A small always-available panel to tweak AudioEngine volumes live."""

    def __init__(
        self,
        *,
        audio_engine: AudioEngine,
        title: str = "Volume Test",
        include_test_audio_controls: bool = False,
        channel_names: dict[int, str] | None = None,
        include_global_stream_slider: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setMinimumWidth(520)

        self.audio_engine = audio_engine
        self._include_test_audio_controls = include_test_audio_controls
        self._channel_names = dict(channel_names or {})
        self._include_global_stream_slider = bool(include_global_stream_slider)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self._rows: list[tuple[str, QSlider, QLabel]] = []

        # Channel sliders
        for ch in range(int(getattr(self.audio_engine, "num_channels", 0) or 0)):
            name = self._channel_names.get(ch)
            label = f"{name} (ch{ch})" if name else f"Channel {ch}"
            self._add_slider_row(root, label, on_change=lambda v, c=ch: self._set_channel_volume(c, v))

        # Legacy/global pygame.mixer.music slider (optional).
        if self._include_global_stream_slider:
            self._add_slider_row(root, "Streaming", on_change=self._set_streaming_volume)

        if include_test_audio_controls:
            controls = QHBoxLayout()
            self._btn_start = QPushButton("Start tones")
            self._btn_start.clicked.connect(self._start_tones)
            controls.addWidget(self._btn_start)

            self._btn_stop = QPushButton("Stop all")
            self._btn_stop.clicked.connect(self._stop_all)
            controls.addWidget(self._btn_stop)

            self._btn_stream = QPushButton("Play streaming file…")
            self._btn_stream.clicked.connect(self._pick_and_stream)
            controls.addWidget(self._btn_stream)

            self._btn_stop_stream = QPushButton("Stop streaming")
            self._btn_stop_stream.clicked.connect(lambda: self.audio_engine.stop_streaming_track(fade_ms=0))
            controls.addWidget(self._btn_stop_stream)

            controls.addStretch(1)
            root.addLayout(controls)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #aaa; font-size: 11px;")
        root.addWidget(self._status)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        # Defaults
        for _, slider, value_label in self._rows:
            slider.setValue(50)
            value_label.setText("50%")

        # Make channel 2 (often Shepard) quieter by default.
        if int(getattr(self.audio_engine, "num_channels", 0) or 0) >= 3:
            name = self._channel_names.get(2)
            label = f"{name} (ch2)" if name else "Channel 2"
            self._set_slider_value(label, 15)

        if include_test_audio_controls:
            self._start_tones()

    def _add_slider_row(self, parent: QVBoxLayout, name: str, *, on_change) -> None:
        row = QHBoxLayout()
        label = QLabel(f"{name}:")
        label.setMinimumWidth(95)
        row.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setSingleStep(1)
        slider.valueChanged.connect(lambda v: on_change(int(v)))
        row.addWidget(slider, 1)

        value_label = QLabel("0%")
        value_label.setMinimumWidth(50)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value_label)

        parent.addLayout(row)
        self._rows.append((name, slider, value_label))

    def _set_slider_value(self, name: str, value: int) -> None:
        for row_name, slider, value_label in self._rows:
            if row_name == name:
                slider.blockSignals(True)
                slider.setValue(int(value))
                slider.blockSignals(False)
                value_label.setText(f"{int(value)}%")
                break

    def _update_value_label(self, name: str, value: int) -> None:
        for row_name, _, value_label in self._rows:
            if row_name == name:
                value_label.setText(f"{int(value)}%")
                break

    def _set_channel_volume(self, channel: int, value_pct: int) -> None:
        vol = max(0.0, min(1.0, float(value_pct) / 100.0))
        self.audio_engine.set_volume(channel, vol)
        name = self._channel_names.get(channel)
        label = f"{name} (ch{channel})" if name else f"Channel {channel}"
        self._update_value_label(label, value_pct)

    def _set_streaming_volume(self, value_pct: int) -> None:
        vol = max(0.0, min(1.0, float(value_pct) / 100.0))
        self.audio_engine.set_streaming_volume(vol)
        self._update_value_label("Streaming", value_pct)

    def _start_tones(self) -> None:
        if not self._include_test_audio_controls:
            return
        if not self.audio_engine.init_ok:
            return

        # Load simple generated loops so sliders have something audible.
        sample_rate = 44100
        tones = [
            _ToneSpec(channel=0, freq_hz=110.0, label="low"),
            _ToneSpec(channel=1, freq_hz=220.0, label="mid"),
        ]

        for spec in tones:
            if spec.channel >= self.audio_engine.num_channels:
                continue
            pcm = _generate_sine_int16_stereo(duration_s=2.0, sample_rate=sample_rate, freq_hz=spec.freq_hz, peak=0.12)
            self.audio_engine.load_channel_pcm(spec.channel, pcm, tag=f"tone:{spec.label}:{spec.freq_hz}")
            current = self._get_slider_value(f"Channel {spec.channel}")
            self.audio_engine.fade_in_and_play(spec.channel, fade_ms=0, volume=current, loop=True)

        # If we have channel 2, use the project's Shepard generator.
        if self.audio_engine.num_channels >= 3:
            try:
                from mesmerglass.engine.shepard_tone import generate_shepard_tone_int16_stereo

                pcm = generate_shepard_tone_int16_stereo(
                    duration_s=60.0,
                    sample_rate=sample_rate,
                    direction="ascending",
                    peak=0.18,
                )
                shep_ch = 2
                self.audio_engine.load_channel_pcm(shep_ch, pcm, tag="shepard:test")
                current = self._get_slider_value(f"Channel {shep_ch}")
                self.audio_engine.fade_in_and_play(shep_ch, fade_ms=0, volume=current, loop=True)
            except Exception:
                pass

    def _get_slider_value(self, name: str) -> float:
        for row_name, slider, _ in self._rows:
            if row_name == name:
                return float(slider.value()) / 100.0
        return 0.5

    def _stop_all(self) -> None:
        try:
            self.audio_engine.stop_all()
        except Exception:
            pass

    def _pick_and_stream(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio file to stream",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.m4a *.aac);;All Files (*)",
        )
        if not file_path:
            return
        volume = self._get_slider_value("Streaming")
        self.audio_engine.play_streaming_track(file_path, volume=volume, fade_ms=0, loop=True)

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        if self._include_test_audio_controls:
            self._stop_all()
        super().closeEvent(event)

    def _refresh_status(self) -> None:
        try:
            busy: list[str] = []
            for ch in range(int(getattr(self.audio_engine, "num_channels", 0) or 0)):
                try:
                    if self.audio_engine.is_playing(ch):
                        name = self._channel_names.get(ch)
                        busy.append(f"{name or 'ch'}{ch}" if name else f"ch{ch}")
                except Exception:
                    pass
            streaming = False
            try:
                streaming = bool(self.audio_engine.is_streaming_active())
            except Exception:
                streaming = False

            stream_name = ""
            try:
                path = getattr(self.audio_engine, "_streaming_path", None)
                if path:
                    import os

                    stream_name = os.path.basename(str(path))
            except Exception:
                stream_name = ""

            msg = f"Playing: {', '.join(busy) if busy else 'none'}"
            msg += f" | Streaming: {'yes' if streaming else 'no'}"
            if streaming and stream_name:
                msg += f" ({stream_name})"
            self._status.setText(msg)
        except Exception:
            pass


def launch_volume_test(argv: list[str] | None = None) -> int:
    """Standalone dev helper."""
    _ = argv  # reserved for future flags

    app = QApplication.instance()
    owns_app = False
    if app is None:
        app = QApplication(sys.argv)
        owns_app = True

    engine = AudioEngine(num_channels=3)
    window = VolumePanel(audio_engine=engine, title="MesmerGlass - Volume Test", include_test_audio_controls=True)
    window.show()

    if owns_app:
        return int(app.exec())
    return 0


def create_attached_volume_panel(audio_engine: AudioEngine) -> VolumePanel:
    """Create a panel that controls an existing AudioEngine (no test tones)."""
    return VolumePanel(
        audio_engine=audio_engine,
        title="MesmerGlass - Live Volume Panel",
        include_test_audio_controls=False,
        channel_names={
            0: "HYPNO",
            1: "BACKGROUND",
            2: "SHEPARD",
        },
        include_global_stream_slider=False,
    )
