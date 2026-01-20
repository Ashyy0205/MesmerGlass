from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Mp4ExportSettings:
    output_path: Path
    width: int = 1920
    height: int = 1080
    fps: int = 60
    prefer_nvenc: bool = True


class _EncodeWorker(threading.Thread):
    def __init__(
        self,
        *,
        frame_queue: "queue.Queue[Optional[np.ndarray]]",
        settings: Mp4ExportSettings,
    ) -> None:
        super().__init__(daemon=True)
        self._q = frame_queue
        self._settings = settings
        self._stop = threading.Event()
        self._error: Optional[BaseException] = None

    @property
    def error(self) -> Optional[BaseException]:
        return self._error

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            import av

            out_path = str(self._settings.output_path)
            fps = int(self._settings.fps)
            width = int(self._settings.width)
            height = int(self._settings.height)

            container = av.open(out_path, mode="w")
            codec_name = None
            if self._settings.prefer_nvenc:
                codec_name = "h264_nvenc"
            else:
                codec_name = "libx264"

            # Create stream; if NVENC init fails, fall back to libx264.
            try:
                stream = container.add_stream(codec_name, rate=fps)
            except Exception:
                codec_name = "libx264"
                stream = container.add_stream(codec_name, rate=fps)

            stream.width = width
            stream.height = height
            stream.pix_fmt = "yuv420p"

            if codec_name == "libx264":
                stream.options = {
                    "preset": "veryfast",
                    "tune": "zerolatency",
                    "crf": "18",
                    "profile": "high",
                }
            else:
                # Keep options conservative; rely on defaults unless user needs tuning.
                stream.options = {
                    "preset": "p7",
                    "rc": "vbr_hq",
                    "cq": "18",
                    "bf": "0",
                    "g": str(max(1, min(fps, 60))),
                    "forced-idr": "1",
                    "repeat_headers": "1",
                }

            while not self._stop.is_set():
                frame = self._q.get()
                if frame is None:
                    break

                # Ensure RGB uint8 contiguous
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8, copy=False)
                if not frame.flags["C_CONTIGUOUS"]:
                    frame = np.ascontiguousarray(frame)

                # Resize/crop not supported in v1; assume exact output size.
                video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
                if video_frame.width != width or video_frame.height != height:
                    video_frame = video_frame.reformat(width=width, height=height, format="yuv420p")
                else:
                    video_frame = video_frame.reformat(format="yuv420p")

                for packet in stream.encode(video_frame):
                    container.mux(packet)

            # Flush encoder
            for packet in stream.encode(None):
                container.mux(packet)
            container.close()

        except BaseException as exc:
            self._error = exc
            logger.error("[export] Encode worker failed: %s", exc, exc_info=True)


class CuelistMp4Exporter(QObject):
    """Offline (hidden) MP4 exporter.

    Drives SessionRunner at a fixed 60fps dt and captures frames from a hidden compositor.
    """

    progress_changed = pyqtSignal(int, int, str)  # current, total, label
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(
        self,
        *,
        cuelist,
        visual_director,
        text_director,
        spiral_director,
        session_data: Optional[dict] = None,
        settings: Mp4ExportSettings,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._cuelist = cuelist
        self._visual_director = visual_director
        self._text_director = text_director
        self._spiral_director = spiral_director
        self._session_data = session_data
        self._settings = settings

        self._timer: Optional[QTimer] = None
        self._session_runner = None
        self._hidden_compositor = None

        self._prev_visual_compositor = None
        self._prev_text_compositor = None

        self._frames_total = 0
        self._steps_done = 0
        self._frames_written = 0
        self._last_frame: Optional[np.ndarray] = None
        self._last_status = ""

        # Offline exports should use a simulated timebase so cue durations are
        # based on rendered frames rather than wall-clock.
        self._time_base = 0.0
        self._sim_time = 0.0

        self._frame_q: "queue.Queue[Optional[np.ndarray]]" = queue.Queue(maxsize=240)
        self._encoder: Optional[_EncodeWorker] = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def start(self) -> None:
        try:
            from mesmerglass.mesmerloom.window_compositor import LoomWindowCompositor
            from mesmerglass.session.runner import SessionRunner

            fps = int(self._settings.fps)
            dt = 1.0 / float(max(1, fps))

            self._time_base = time.time()
            self._sim_time = 0.0

            def _time_provider() -> float:
                return float(self._time_base + self._sim_time)

            total_seconds = float(getattr(self._cuelist, "total_duration")())
            self._frames_total = max(1, int(round(total_seconds * fps)))

            # Session-mode cuelists often reference playbacks by name; resolve those
            # to actual JSON files (same approach as SessionRunnerTab).
            if self._session_data and isinstance(self._session_data.get("playbacks"), dict):
                try:
                    import json
                    from mesmerglass.platform_paths import ensure_dir, get_user_data_dir

                    playbacks_dict = self._session_data["playbacks"]
                    temp_dir = ensure_dir(get_user_data_dir() / "runtime" / "playbacks")

                    for cue in getattr(self._cuelist, "cues", []) or []:
                        for entry in getattr(cue, "playback_pool", []) or []:
                            playback_name = str(getattr(entry, "playback_path", ""))
                            if playback_name in playbacks_dict:
                                playback_data = playbacks_dict[playback_name]
                                if isinstance(playback_data, dict) and "version" not in playback_data:
                                    playback_data["version"] = "1.0"
                                playback_file = temp_dir / f"{playback_name}.json"
                                playback_file.write_text(json.dumps(playback_data, indent=2))
                                entry.playback_path = playback_file
                except Exception as exc:
                    logger.warning("[export] Playback resolve failed (continuing): %s", exc)

            self._hidden_compositor = LoomWindowCompositor(
                director=self._spiral_director,
                text_director=self._text_director,
                is_primary=True,
            )

            # Configure hidden/offscreen compositor
            try:
                self._hidden_compositor.resize(self._settings.width, self._settings.height)
                self._hidden_compositor.setGeometry(-10000, -10000, self._settings.width, self._settings.height)
                self._hidden_compositor.setOpacity(0.0)
                if hasattr(self._hidden_compositor, "set_virtual_screen_size"):
                    try:
                        self._hidden_compositor.set_virtual_screen_size(self._settings.width, self._settings.height)
                    except Exception:
                        pass
                self._hidden_compositor.set_active(True)
                self._hidden_compositor.show()
            except Exception:
                pass

            # Enable capture at 60fps
            try:
                if hasattr(self._hidden_compositor, "set_preview_capture_enabled"):
                    self._hidden_compositor.set_preview_capture_enabled(True, max_fps=fps)
                elif hasattr(self._hidden_compositor, "set_capture_enabled"):
                    self._hidden_compositor.set_capture_enabled(True, max_fps=fps)
            except Exception:
                pass

            self._hidden_compositor.frame_ready.connect(self._on_frame_ready)

            # Swap visual/text compositor targets so *all uploads* go to the hidden compositor.
            self._prev_visual_compositor = getattr(self._visual_director, "compositor", None)
            self._prev_text_compositor = getattr(self._text_director, "compositor", None)
            try:
                self._visual_director.compositor = self._hidden_compositor
            except Exception:
                pass
            try:
                self._text_director.compositor = self._hidden_compositor
            except Exception:
                pass

            # Encoder thread
            self._encoder = _EncodeWorker(frame_queue=self._frame_q, settings=self._settings)
            self._encoder.start()

            # Session runner (headless mode so it never shows fullscreen anywhere)
            self._session_runner = SessionRunner(
                cuelist=self._cuelist,
                visual_director=self._visual_director,
                audio_engine=None,
                compositor=self._hidden_compositor,
                display_tab=None,
                session_data=self._session_data,
                headless=True,
                time_provider=_time_provider,
            )
            ok = self._session_runner.start()
            if not ok:
                raise RuntimeError("SessionRunner failed to start")

            # Tick loop: only advance after previous step was captured.
            self._timer = QTimer(self)
            self._timer.setInterval(0)

            def _tick() -> None:
                if self._cancelled:
                    self._finish(False, "Cancelled")
                    return

                if self._encoder and self._encoder.error:
                    self._finish(False, f"Encoder error: {self._encoder.error}")
                    return

                runner = self._session_runner
                if runner is None:
                    self._finish(False, "Internal error: no runner")
                    return

                # If the session has ended, but we still need frames, pad by repeating
                # the last captured frame to guarantee the export completes.
                if (not runner.is_running()) and (self._frames_written < self._frames_total):
                    if self._frame_q.full():
                        self._emit_progress("Finalizing…")
                        return
                    if self._last_frame is not None:
                        try:
                            self._frame_q.put_nowait(self._last_frame)
                            self._frames_written += 1
                            self._emit_progress("Finalizing…")
                            return
                        except queue.Full:
                            self._emit_progress("Finalizing…")
                            return
                    # No frame ever captured; fail fast.
                    self._finish(False, "Export failed: no frames captured")
                    return

                # Stop once the runner finishes and we've written everything we stepped.
                if (not runner.is_running()) and (self._frames_written >= self._steps_done):
                    self._finish(True, f"Export complete: {self._settings.output_path}")
                    return

                # Don’t advance simulation faster than we can capture/enqueue.
                if self._steps_done > self._frames_written:
                    self._emit_progress()
                    return

                # Avoid queue blowups: if encoding lags, wait.
                if self._frame_q.full():
                    self._emit_progress("Encoding…")
                    return

                # Step one frame.
                self._sim_time += dt
                runner.update(dt=dt)
                self._steps_done += 1
                self._emit_progress()

            self._timer.timeout.connect(_tick)
            self._timer.start()
            self._emit_progress("Starting…")

        except Exception as exc:
            logger.error("[export] Failed to start exporter: %s", exc, exc_info=True)
            self._finish(False, f"Export failed: {exc}")

    def _elapsed_seconds(self) -> float:
        runner = self._session_runner
        if runner is None:
            return 0.0
        try:
            current_cue_idx = runner.get_current_cue_index()
            elapsed = sum(
                cue.duration_seconds
                for i, cue in enumerate(self._cuelist.cues)
                if i < current_cue_idx
            )
            elapsed += runner._get_cue_elapsed_time()  # used in UI too
            return max(0.0, float(elapsed))
        except Exception:
            return 0.0

    def _emit_progress(self, status: Optional[str] = None) -> None:
        if status is None:
            # Use frame-derived time (deterministic under backpressure).
            elapsed = float(self._frames_written) / float(max(1, self._settings.fps))
            total = float(self._frames_total) / float(max(1, self._settings.fps))
            status = f"{elapsed:0.1f}s / {total:0.1f}s"
        if status == self._last_status and self._frames_written % 10 != 0:
            return
        self._last_status = status
        self.progress_changed.emit(self._frames_written, self._frames_total, status)

    def _on_frame_ready(self, frame: np.ndarray) -> None:
        try:
            self._last_frame = frame
        except Exception:
            self._last_frame = None
        # Enforce 1:1 capture with simulation steps.
        if self._frames_written >= self._steps_done:
            return
        try:
            self._frame_q.put_nowait(frame)
            self._frames_written += 1
        except queue.Full:
            # If full, we’ll pause stepping in the timer.
            return

    def _finish(self, success: bool, message: str) -> None:
        try:
            if self._timer:
                self._timer.stop()
        except Exception:
            pass

        try:
            if self._session_runner and self._session_runner.is_running():
                try:
                    self._session_runner.stop()
                except Exception:
                    pass
        except Exception:
            pass

        # Stop encoder
        try:
            if self._encoder:
                try:
                    self._frame_q.put_nowait(None)
                except Exception:
                    pass
                self._encoder.stop()
                self._encoder.join(timeout=5.0)
        except Exception:
            pass

        # Restore compositor targets
        try:
            if self._prev_visual_compositor is not None:
                self._visual_director.compositor = self._prev_visual_compositor
        except Exception:
            pass
        try:
            if self._prev_text_compositor is not None:
                self._text_director.compositor = self._prev_text_compositor
        except Exception:
            pass

        # Cleanup hidden compositor
        try:
            if self._hidden_compositor is not None:
                try:
                    if hasattr(self._hidden_compositor, "set_preview_capture_enabled"):
                        self._hidden_compositor.set_preview_capture_enabled(False)
                except Exception:
                    pass
                try:
                    self._hidden_compositor.set_active(False)
                    self._hidden_compositor.hide()
                except Exception:
                    pass
                try:
                    self._hidden_compositor.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass

        self.finished.emit(bool(success), str(message))
