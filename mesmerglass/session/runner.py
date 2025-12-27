"""
Session Runner - Execution engine for cuelist playback.

The SessionRunner orchestrates cuelist execution with:
- Cycle-synchronized transitions (waits for media cycle boundaries)
- Weighted/sequential playback selection from cue pools
- Audio/visual coordination with fade transitions
- State machine management (STOPPED, RUNNING, PAUSED)
- Event emission for UI updates and logging

Architecture:
    SessionRunner.update() called every frame (60fps)
    → Check transition triggers (duration OR cycle count)
    → When triggered: wait for cycle boundary, then execute transition
    → Load next playback from weighted pool
    → Emit events for state changes
"""

from __future__ import annotations
import random
import time
import logging
try:
    import psutil
except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
    psutil = None
    _PSUTIL_IMPORT_ERROR = exc
else:
    _PSUTIL_IMPORT_ERROR = None
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional, Any
from pathlib import Path

if TYPE_CHECKING:
    from .cuelist import Cuelist
    from .cue import Cue, PlaybackEntry
    from ..mesmerloom.visual_director import VisualDirector
    from ..engine.audio import AudioEngine
    from ..mesmerloom.compositor import LoomCompositor

from .cue import PlaybackSelectionMode, AudioRole
from .cuelist import CuelistLoopMode, CuelistTransitionMode
from .events import SessionEventEmitter, SessionEvent, SessionEventType
from .audio_prefetch_worker import AudioPrefetchWorker, PrefetchJob
from ..logging_utils import PerfTracer


class SessionState(Enum):
    """Session execution states."""
    STOPPED = auto()    # Not running, can be started
    RUNNING = auto()    # Active execution
    PAUSED = auto()     # Paused, can be resumed
    COMPLETED = auto()  # Finished successfully (ONCE mode)


@dataclass
class _AudioBufferReservation:
    """Tracks decoded buffer usage so we can honor per-role budgets."""
    role: AudioRole
    cue_index: Optional[int]
    path: str
    remaining_seconds: float
    active: bool = False


class _ReserveOutcome(Enum):
    RESERVED = auto()
    DEFER = auto()
    STREAM = auto()


class SessionRunner:
    """
    Execution engine for cuelist playback with cycle-synchronized transitions.
    
    Responsibilities:
    - Load cues sequentially from cuelist
    - Select playbacks from cue's pool (weighted/sequential/shuffle)
    - Detect transition triggers (duration elapsed OR cycle count reached)
    - Wait for cycle boundaries before executing transitions
    - Emit session events for UI updates
    - Handle pause/resume/stop and manual cue skipping
    
    Usage:
        runner = SessionRunner(cuelist, visual_director, event_emitter)
        runner.start()  # Starts session, loads first cue
        
        # In main loop (60fps):
        runner.update(dt)  # Check for transitions, advance state
    """
    
    def __init__(
        self,
        cuelist: Cuelist,
        visual_director: VisualDirector,
        event_emitter: Optional[SessionEventEmitter] = None,
        audio_engine: Optional[AudioEngine] = None,
        compositor: Optional[LoomCompositor] = None,
        display_tab = None,  # DisplayTab for monitor selection
        session_data: Optional[dict] = None  # Session data for accessing playback configs
    ):
        """
        Initialize session runner.
        
        Args:
            cuelist: Cuelist to execute
            visual_director: Visual system controller (for loading playbacks and cycle tracking)
            event_emitter: Event emitter for broadcasting state changes (optional)
            audio_engine: Audio playback engine (optional, for Phase 4)
            compositor: OpenGL compositor (primary compositor, used as template for multi-display)
            display_tab: DisplayTab widget for monitor selection (optional)
            session_data: Full session data dict for accessing playback configs (optional)
        """
        self.cuelist = cuelist
        self.visual_director = visual_director
        self.event_emitter = event_emitter or SessionEventEmitter()
        self.audio_engine = audio_engine
        self.compositor = compositor  # Primary compositor (template)
        self.display_tab = display_tab
        self.session_data = session_data
        
        self.logger = logging.getLogger(__name__)
        
        # State machine
        self._state = SessionState.STOPPED
        
        # Cue tracking
        self._current_cue_index = -1  # -1 = no cue loaded
        self._cue_start_time: Optional[float] = None
        self._cue_start_cycle: int = 0  # Cycle count when cue started
        
        # Playback pool tracking (time-based switching with cycle synchronization)
        self._current_playback_entry: Optional[PlaybackEntry] = None  # Current playback from pool
        self._playback_start_time: float = 0.0  # Time when current playback started
        self._playback_target_duration: float = 0.0  # Target duration in seconds before switch
        self._playback_switch_pending: bool = False  # Waiting for next cycle to switch
        self._active_selection_mode = PlaybackSelectionMode.ON_CUE_START  # Effective mode after overrides
        self._selection_mode_override_active = False  # True when legacy cues force cycle switching
        
        # Playback history (to avoid repeats within cue)
        self._playback_history: list[str] = []  # List of recently used playback names
        self._history_limit = 3  # Remember last N playbacks to avoid
        
        # Transition state
        self._pending_transition = False  # Waiting for cycle boundary
        self._transition_target_cue: Optional[int] = None  # Next cue to load
        self._transition_in_progress = False  # Currently fading between cues
        self._transition_start_time: Optional[float] = None  # When fade started
        self._transition_fade_alpha: float = 1.0  # Fade alpha (1.0 = old cue, 0.0 = new cue)

        # Transition safety: if cycle boundaries never arrive (e.g., media disabled
        # or a visual doesn't emit cycle events), we must still respect cue durations.
        self._pending_transition_since_ts: Optional[float] = None
        self._last_cycle_boundary_ts: Optional[float] = None
        self._cycle_boundary_interval_ema_s: float = 1.0
        
        # Session timing
        self._session_start_time: Optional[float] = None
        self._pause_start_time: Optional[float] = None
        self._total_paused_time: float = 0.0
        
        # Loop tracking (for PING_PONG mode)
        self._loop_direction = 1  # 1 = forward, -1 = backward
        
        # Frame timing tracking (for performance monitoring)
        self._frame_times: list[float] = []  # Frame delta times in ms
        self._last_frame_time: Optional[float] = None  # Time of last update() call
        self._frame_budget_ms = 16.67  # 60 FPS = 16.67ms per frame
        self._frame_spike_warn_ms = 100.0  # Warn if frame exceeds ~6x budget
        self._worst_frame_spike: Optional[dict[str, Any]] = None
        self._last_blocking_operation: Optional[dict[str, Any]] = None
        
        # Memory usage tracking
        if psutil is None:
            raise RuntimeError(
                "psutil is required for SessionRunner. Install it via 'pip install psutil' "
                "or add it to your environment requirements."
            ) from _PSUTIL_IMPORT_ERROR
        self._process = psutil.Process()
        self._memory_samples: list[float] = []  # MB samples
        self._memory_sample_interval = 100  # Sample every 100 frames
        self._frame_count = 0
        
        # Cycle callback registration (separate flags for cue transitions vs playback switching)
        self._cue_callback_registered = False  # For cue transitions
        self._playback_callback_registered = False  # For playback switching
        
        # Multi-display support: Additional compositors for secondary displays
        self._secondary_compositors: list[LoomCompositor] = []
        
        # VR streaming support
        self.vr_streaming_server = None
        self._vr_streaming_active = False
        self._vr_last_frame = None
        self._vr_frame_lock = None
        self._vr_frame_handler = None

        # Audio runtime tracking
        self._audio_role_channels: dict[AudioRole, int] = {}
        self._active_hypno_duration: Optional[float] = None
        self._audio_prefetch_lead_seconds = self._resolve_audio_prefetch_lead(session_data)
        self._prefetched_cues: set[int] = set()
        self._audio_stream_threshold_mb = self._resolve_audio_stream_threshold(session_data)
        self._active_stream_role: Optional[AudioRole] = None
        self._audio_buffer_limits = self._resolve_audio_buffer_limits(session_data)
        self._audio_buffer_usage: dict[AudioRole, float] = {role: 0.0 for role in AudioRole}
        self._audio_buffer_reservations: dict[str, _AudioBufferReservation] = {}
        self._prefetch_backlog: set[int] = set()
        self._prefetch_worker = AudioPrefetchWorker(audio_engine) if audio_engine else None
        self._prefetch_jobs: dict[int, set[str]] = {}
        self._audio_prefetch_wait_ms = self._resolve_audio_prefetch_wait_limit(session_data)
        self._slow_decode_stream_ms = self._resolve_slow_decode_stream_threshold(session_data)
        self._pending_streams: dict[AudioRole, dict[str, Any]] = {}

        if self.audio_engine:
            self.audio_engine.set_stream_threshold_mb(self._audio_stream_threshold_mb)
            self.audio_engine.set_slow_decode_threshold_ms(self._slow_decode_stream_ms)

        self._perf_tracer = PerfTracer(f"cuelist:{cuelist.name}")
        if self._perf_tracer.enabled:
            loop_mode = (cuelist.loop_mode.value if getattr(cuelist, "loop_mode", None) else "once")
            self._perf_tracer.set_context(
                cuelist=cuelist.name,
                cue_count=len(cuelist.cues),
                loop_mode=loop_mode,
            )
    
    # ===== State Properties =====

    def _perf_span(self, name: str, *, category: str = "misc", **metadata: Any):
        tracer = getattr(self, "_perf_tracer", None)
        if not tracer or not tracer.enabled:
            return PerfTracer.noop_span()
        return tracer.span(name, category=category, metadata=metadata)

    def _record_blocking_operation(self, operation: str, duration_ms: float, **metadata: Any) -> None:
        """Track work that held up the frame thread so we can attribute spikes."""
        if duration_ms <= 0:
            return

        record = {
            "operation": operation,
            "duration_ms": duration_ms,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._last_blocking_operation = record

        if duration_ms >= 1000.0:
            meta_str = ", ".join(f"{k}={v}" for k, v in record["metadata"].items()) or "no-metadata"
            self.logger.warning(
                "[perf] Blocking %s took %.1fms (%s)",
                operation,
                duration_ms,
                meta_str,
            )

    def _recent_blocking_operation(self, ttl_s: float = 3.0) -> Optional[dict[str, Any]]:
        ctx = self._last_blocking_operation
        if not ctx:
            return None
        if (time.time() - ctx.get("timestamp", 0.0)) > ttl_s:
            return None
        return ctx

    def _record_frame_spike(self, frame_delta_ms: float) -> None:
        """Remember the worst frame spike so we can summarize later."""
        blocker = self._recent_blocking_operation()
        record = {
            "delta_ms": frame_delta_ms,
            "timestamp": time.time(),
            "blocker": blocker,
        }
        if not self._worst_frame_spike or frame_delta_ms > self._worst_frame_spike.get("delta_ms", 0.0):
            self._worst_frame_spike = record

    def _ensure_theme_bank_ready(self, *, require_videos: bool = False, wait_s: float = 0.5) -> bool:
        """Check that ThemeBank has accessible media before starting playback."""

        bank = getattr(self.visual_director, "theme_bank", None)
        if bank is None or not hasattr(bank, "ensure_ready"):
            return True
        scan_in_progress = bool(getattr(bank, "media_scan_in_progress", False))
        is_network = bool(getattr(bank, "network_sources_detected", False))
        # Allow a longer readiness grace period for network media / warmup.
        effective_wait_s = max(0.0, float(wait_s))
        if is_network:
            effective_wait_s = max(effective_wait_s, 3.0)
        elif scan_in_progress:
            effective_wait_s = max(effective_wait_s, 1.5)
        try:
            status = bank.ensure_ready(require_videos=require_videos, timeout_s=effective_wait_s)
        except Exception as exc:
            self.logger.warning("[session] ThemeBank readiness check failed: %s", exc)
            return True
        ready = status.ready and (not require_videos or status.total_videos > 0)
        if ready:
            self.logger.info(
                "[session] ThemeBank ready: images=%d videos=%d cached=%d last=%s",
                status.total_images,
                status.total_videos,
                status.cached_images,
                status.last_image_path,
            )
            return True
        # SMB shares can report empty/partial contents for a while after reboot.
        # Don't abort the session: keep running and visuals will start once media loads.
        if scan_in_progress:
            self.logger.warning(
                "[session] ThemeBank not ready (scan in progress) - continuing: %s",
                status.ready_reason,
            )
            return True
        if is_network and (status.total_images > 0 or status.total_videos > 0 or status.themes_total > 0):
            self.logger.warning(
                "[session] ThemeBank not ready (network media) - continuing: %s",
                status.ready_reason,
            )
            return True
        self.logger.error("[session] ThemeBank not ready: %s", status.ready_reason)
        return False

    def _format_blocking_summary(self, record: dict[str, Any]) -> str:
        metadata = record.get("metadata") or {}
        preferred_keys = ("cue_index", "track", "role", "reason")
        details = [f"{key}={metadata[key]}" for key in preferred_keys if key in metadata]
        extras = [f"{key}={value}" for key, value in metadata.items() if key not in preferred_keys]
        details.extend(extras)
        duration = record.get("duration_ms")
        if duration is not None:
            details.append(f"duration={duration:.1f}ms")
        detail_str = ", ".join(details) if details else "no metadata"
        return f"{record.get('operation', 'unknown')} ({detail_str})"

    def get_perf_snapshot(self, *, reset: bool = False) -> Optional[dict[str, Any]]:
        tracer = getattr(self, "_perf_tracer", None)
        if not tracer or not tracer.enabled:
            return None
        if reset:
            return tracer.consume()
        return tracer.snapshot()

    def _resolve_audio_prefetch_lead(self, session_data: Optional[dict]) -> float:
        """Determine how many seconds before a cue ends we should prefetch audio."""
        try:
            settings = (session_data or {}).get("settings", {})
            audio_settings = settings.get("audio", {})
            value = float(audio_settings.get("prefetch_lead_seconds", 8.0))
            return max(1.0, min(30.0, value))
        except Exception:
            return 8.0

    def _resolve_audio_prefetch_wait_limit(self, session_data: Optional[dict]) -> float:
        """Return max milliseconds we'll wait for async audio to finish when cue starts."""
        try:
            settings = (session_data or {}).get("settings", {})
            audio_settings = settings.get("audio", {})
            value = float(audio_settings.get("prefetch_block_limit_ms", 150.0))
            return max(20.0, min(500.0, value))
        except Exception:
            return 150.0

    def _resolve_audio_stream_threshold(self, session_data: Optional[dict]) -> float:
        """Read session-configured streaming threshold in megabytes (0 disables)."""
        try:
            settings = (session_data or {}).get("settings", {})
            audio_settings = settings.get("audio", {})
            value = float(audio_settings.get("stream_threshold_mb", 64.0))
            return max(0.0, value)
        except Exception:
            return 64.0

    def _resolve_slow_decode_stream_threshold(self, session_data: Optional[dict]) -> float:
        """Return decode time (ms) after which we permanently stream the asset."""
        try:
            settings = (session_data or {}).get("settings", {})
            audio_settings = settings.get("audio", {})
            value = float(audio_settings.get("slow_decode_stream_ms", 350.0))
            return max(0.0, min(2000.0, value))
        except Exception:
            return 350.0

    def _resolve_audio_buffer_limits(self, session_data: Optional[dict]) -> dict[AudioRole, float]:
        """Return max decoded seconds per role (default hypno/background = 10s)."""
        defaults = {
            AudioRole.HYPNO: 10.0,
            AudioRole.BACKGROUND: 10.0,
            AudioRole.GENERIC: 5.0,
        }
        try:
            settings = (session_data or {}).get("settings", {})
            audio_settings = settings.get("audio", {})
            buffer_config = audio_settings.get("max_buffer_seconds", {})
            role_map: dict[AudioRole, float] = defaults.copy()

            def _read_value(primary_key: str, fallback_key: str, role: AudioRole) -> None:
                src_value = audio_settings.get(primary_key)
                if src_value is None and isinstance(buffer_config, dict):
                    src_value = buffer_config.get(fallback_key)
                if src_value is None:
                    return
                try:
                    role_map[role] = max(0.0, float(src_value))
                except Exception:
                    pass

            _read_value("max_buffer_seconds_hypno", "hypno", AudioRole.HYPNO)
            _read_value("max_buffer_seconds_background", "background", AudioRole.BACKGROUND)
            _read_value("max_buffer_seconds_generic", "generic", AudioRole.GENERIC)
            return role_map
        except Exception:
            return defaults

    def _normalize_audio_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve())
        except Exception:
            return str(file_path)

    def _estimate_track_duration(self, file_path: str, cue_duration: Optional[float]) -> Optional[float]:
        if not self.audio_engine:
            return cue_duration
        try:
            duration = self.audio_engine.estimate_track_duration(str(file_path))
        except AttributeError:
            duration = None
        if duration is not None:
            return duration
        return cue_duration

    def _reserve_audio_buffer(
        self,
        *,
        cue_index: Optional[int],
        role: AudioRole,
        file_path: str,
        cue_duration: Optional[float],
        active: bool,
        allow_eviction: bool,
    ) -> _ReserveOutcome:
        limit = self._audio_buffer_limits.get(role, self._audio_buffer_limits.get(AudioRole.GENERIC, 0.0))
        if limit <= 0.0:
            return _ReserveOutcome.STREAM

        normalized = self._normalize_audio_path(file_path)
        reservation = self._audio_buffer_reservations.get(normalized)
        if reservation:
            if cue_index is not None:
                reservation.cue_index = cue_index
            if active and not reservation.active:
                reservation.active = True
            return _ReserveOutcome.RESERVED

        duration = self._estimate_track_duration(file_path, cue_duration)
        if duration is None:
            return _ReserveOutcome.STREAM
        if duration > limit:
            return _ReserveOutcome.STREAM
        required = min(limit, max(0.0, float(duration)))
        if required <= 0.0:
            return _ReserveOutcome.STREAM

        available = limit - self._audio_buffer_usage.get(role, 0.0)
        if required > available:
            if allow_eviction:
                self._evict_prefetched_buffers(role, required - available)
                available = limit - self._audio_buffer_usage.get(role, 0.0)
            if required > available:
                return _ReserveOutcome.STREAM if active else _ReserveOutcome.DEFER

        reservation = _AudioBufferReservation(
            role=role,
            cue_index=cue_index,
            path=normalized,
            remaining_seconds=required,
            active=active,
        )
        self._audio_buffer_reservations[normalized] = reservation
        self._audio_buffer_usage[role] = self._audio_buffer_usage.get(role, 0.0) + required
        return _ReserveOutcome.RESERVED

    def _evict_prefetched_buffers(self, role: AudioRole, needed_seconds: float) -> None:
        if needed_seconds <= 0:
            return
        for path, reservation in list(self._audio_buffer_reservations.items()):
            if reservation.role != role or reservation.active:
                continue
            self._audio_buffer_usage[role] = max(0.0, self._audio_buffer_usage[role] - reservation.remaining_seconds)
            self._audio_buffer_reservations.pop(path, None)
            if self.audio_engine:
                try:
                    self.audio_engine.drop_cached_sound(path)
                except AttributeError:
                    pass
            needed_seconds -= reservation.remaining_seconds
            if needed_seconds <= 0:
                break

    def _release_audio_buffer_for_path(self, file_path: str) -> None:
        normalized = self._normalize_audio_path(file_path)
        reservation = self._audio_buffer_reservations.pop(normalized, None)
        if not reservation:
            return
        self._audio_buffer_usage[reservation.role] = max(0.0, self._audio_buffer_usage[reservation.role] - reservation.remaining_seconds)
        if self.audio_engine and not reservation.active:
            try:
                self.audio_engine.drop_cached_sound(normalized)
            except AttributeError:
                pass

    def _release_audio_buffers_for_cue(self, cue_index: int) -> None:
        for path, reservation in list(self._audio_buffer_reservations.items()):
            if reservation.cue_index == cue_index:
                self._audio_buffer_usage[reservation.role] = max(0.0, self._audio_buffer_usage[reservation.role] - reservation.remaining_seconds)
                self._audio_buffer_reservations.pop(path, None)
                if self.audio_engine:
                    try:
                        self.audio_engine.drop_cached_sound(path)
                    except AttributeError:
                        pass

    def _decay_active_audio_buffers(self, elapsed_seconds: float) -> None:
        if elapsed_seconds <= 0:
            return
        for reservation in self._audio_buffer_reservations.values():
            if not reservation.active or reservation.remaining_seconds <= 0:
                continue
            reduction = min(reservation.remaining_seconds, elapsed_seconds)
            reservation.remaining_seconds -= reduction
            self._audio_buffer_usage[reservation.role] = max(0.0, self._audio_buffer_usage[reservation.role] - reduction)

    def _mark_prefetch_pending(self, cue_index: int) -> None:
        if cue_index >= 0:
            self._prefetch_backlog.add(cue_index)

    def _retry_prefetch_backlog(self) -> None:
        if not self._prefetch_backlog:
            return
        for cue_index in list(self._prefetch_backlog):
            if cue_index in self._prefetched_cues:
                self._prefetch_backlog.discard(cue_index)
                continue
            self._prefetch_cue_audio(cue_index, force=True)
            if cue_index in self._prefetched_cues:
                self._prefetch_backlog.discard(cue_index)

    def _track_prefetch_job(self, cue_index: int, normalized_path: str) -> None:
        pending = self._prefetch_jobs.setdefault(cue_index, set())
        pending.add(normalized_path)

    def _complete_prefetch_job(self, cue_index: int, normalized_path: str) -> None:
        pending = self._prefetch_jobs.get(cue_index)
        if not pending:
            return
        pending.discard(normalized_path)
        if not pending:
            self._prefetch_jobs.pop(cue_index, None)

    def _maybe_finalize_cue_prefetch(self, cue_index: int) -> None:
        if cue_index < 0 or cue_index in self._prefetched_cues:
            return
        if cue_index in self._prefetch_backlog:
            return
        if self._prefetch_jobs.get(cue_index):
            return
        self._prefetched_cues.add(cue_index)
        self._prefetch_backlog.discard(cue_index)

    def _process_completed_prefetch_jobs(self) -> None:
        if not self._prefetch_worker:
            return
        for job, success, exc in self._prefetch_worker.drain_completed():
            elapsed_ms = (time.perf_counter() - job.submitted_at) * 1000.0
            normalized = job.path
            self._complete_prefetch_job(job.cue_index, normalized)
            if not success:
                if exc:
                    self.logger.warning(
                        "[session] Async audio prefetch failed for cue %d (%s): %s",
                        job.cue_index,
                        Path(normalized).name,
                        exc,
                    )
                self._release_audio_buffer_for_path(normalized)
                self._mark_prefetch_pending(job.cue_index)
                continue
            if elapsed_ms > 40.0:
                self.logger.warning(
                    "[perf] Audio prefetch of %s took %.1fms (cue %d)",
                    Path(normalized).name,
                    elapsed_ms,
                    job.cue_index,
                )
            if (
                self._slow_decode_stream_ms > 0.0
                and elapsed_ms >= self._slow_decode_stream_ms
            ):
                self.logger.warning(
                    "[session] Prefetch latency for %s hit slow-decode threshold (%.0f >= %.0f ms); enforcing streaming",
                    Path(normalized).name,
                    elapsed_ms,
                    self._slow_decode_stream_ms,
                )
            self._maybe_finalize_cue_prefetch(job.cue_index)

    def _reset_audio_buffer_tracking(self) -> None:
        self._audio_buffer_reservations.clear()
        for role in self._audio_buffer_usage:
            self._audio_buffer_usage[role] = 0.0
        self._prefetch_backlog.clear()
    
    def is_running(self) -> bool:
        """Check if session is actively running."""
        return self._state == SessionState.RUNNING
    
    def is_paused(self) -> bool:
        """Check if session is paused."""
        return self._state == SessionState.PAUSED
    
    def is_stopped(self) -> bool:
        """Check if session is stopped."""
        return self._state == SessionState.STOPPED
    
    def is_completed(self) -> bool:
        """Check if session completed successfully."""
        return self._state == SessionState.COMPLETED
    
    @property
    def state(self) -> SessionState:
        """Get current session state."""
        return self._state
    
    def get_current_cue_index(self) -> int:
        """Get index of current cue (-1 if none)."""
        return self._current_cue_index
    
    # ===== Lifecycle Methods =====
    
    def start(self) -> bool:
        """Start cuelist execution from first cue.
        
        Returns:
            True if started successfully, False on error
        """
        if self._state != SessionState.STOPPED:
            self.logger.warning(f"[session] Cannot start: already {self._state.name}")
            return False
        
        # Validate cuelist
        is_valid, error = self.cuelist.validate()
        if not is_valid:
            self.logger.error(f"[session] Cannot start: invalid cuelist - {error}")
            return False
        
        if not self.cuelist.cues:
            self.logger.error("[session] Cannot start: cuelist has no cues")
            return False
        
        self.logger.info(f"[session] Starting session: {self.cuelist.name}")

        if not self._ensure_theme_bank_ready(wait_s=0.5):
            self._state = SessionState.STOPPED
            return False
        
        # Initialize session state
        self._state = SessionState.RUNNING
        self._session_start_time = time.time()
        self._total_paused_time = 0.0
        self._loop_direction = 1
        self._worst_frame_spike = None
        self._last_blocking_operation = None
        
        # Activate compositor(s) on selected display(s)
        if self.compositor:
            from PyQt6.QtGui import QGuiApplication
            
            # Get selected displays from DisplayTab
            selected_displays = []
            if self.display_tab:
                selected_displays = self.display_tab.get_selected_displays()
                self.logger.info(f"[session] DisplayTab returned {len(selected_displays)} selected displays")
                for i, display in enumerate(selected_displays):
                    self.logger.info(f"[session]   Display {i}: type={display.get('type')}, data_keys={list(display.keys())}")
            else:
                self.logger.warning("[session] No display_tab available!")
            
            # Separate monitors and VR clients
            monitor_displays = [d for d in selected_displays if d.get("type") == "monitor"]
            vr_clients = [d for d in selected_displays if d.get("type") == "vr"]
            
            # Fallback to primary screen if nothing selected
            if not monitor_displays:
                primary_screen = QGuiApplication.primaryScreen()
                self.logger.info("[session] No monitors selected, using primary screen")
                monitor_displays = [{"type": "monitor", "screen": primary_screen}]
            
            self.logger.info(f"[session] Activating compositor on {len(monitor_displays)} monitor(s)")
            
            # First monitor: Use primary compositor
            first_screen = monitor_displays[0].get("screen")
            if first_screen:
                applied_geometry = self.compositor.fit_to_screen(first_screen)
                if applied_geometry is None:
                    applied_geometry = first_screen.geometry()
                self.logger.info(
                    f"[session] [Display 1/{len(monitor_displays)}] Primary compositor on '{first_screen.name()}': "
                    f"{applied_geometry.width()}x{applied_geometry.height()}"
                )
            else:
                self.compositor.fit_to_screen(None)
            
            self.compositor.set_active(True)
            self.compositor.showFullScreen()
            
            # Force window to be fully opaque
            try:
                import ctypes
                hwnd = int(self.compositor.winId())
                ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x00000002)
            except Exception:
                pass
            
            # Additional monitors: Create secondary compositors
            if len(monitor_displays) > 1:
                from ..mesmerloom.window_compositor import LoomWindowCompositor
                
                # Get the spiral director from the primary compositor
                spiral_director = self.compositor.director
                
                for i, display in enumerate(monitor_displays[1:], start=2):
                    screen = display.get("screen")
                    if not screen:
                        continue
                    
                    try:
                        # Create new compositor instance sharing the same directors
                        # NOTE: text_director is shared for text rendering, but only primary calls update()
                        secondary_compositor = LoomWindowCompositor(
                            director=spiral_director,
                            text_director=self.visual_director.text_director,
                            is_primary=False  # Don't advance text_director state on secondaries
                        )
                        
                        # Position on target screen
                        applied_geometry = secondary_compositor.fit_to_screen(screen)
                        if applied_geometry is None:
                            applied_geometry = screen.geometry()
                        self.logger.info(
                            f"[session] [Display {i}/{len(monitor_displays)}] Secondary compositor on '{screen.name()}': "
                            f"{applied_geometry.width()}x{applied_geometry.height()}"
                        )
                        
                        # Activate and show
                        secondary_compositor.set_active(True)
                        secondary_compositor.showFullScreen()
                        
                        # Force fully opaque
                        try:
                            import ctypes
                            hwnd = int(secondary_compositor.winId())
                            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x00000002)
                        except Exception:
                            pass
                        
                        # Track secondary compositor
                        self._secondary_compositors.append(secondary_compositor)
                        
                        # Register with VisualDirector for content mirroring
                        self.visual_director.register_secondary_compositor(secondary_compositor)
                        
                        self.logger.info(f"[session] Secondary compositor {i-1} created and activated")
                        
                    except Exception as e:
                        self.logger.error(f"[session] Failed to create secondary compositor for display {i}: {e}")
            
            # Register all secondary compositors with TextDirector (after loop completes)
            if self.visual_director.text_director and self._secondary_compositors:
                self.visual_director.text_director.set_secondary_compositors(self._secondary_compositors)
                self.logger.info(f"[session] Registered {len(self._secondary_compositors)} secondary compositor(s) with TextDirector")
            
            self.logger.info(f"[session] Total active compositors: {1 + len(self._secondary_compositors)}")
            
            # Start VR streaming if we have VR clients selected
            if vr_clients and len(vr_clients) > 0:
                self.logger.info(f"[session] Starting VR streaming for {len(vr_clients)} VR client(s)")
                try:
                    from ..mesmervisor.streaming_server import VRStreamingServer
                    from ..mesmervisor.gpu_utils import EncoderType
                    import OpenGL.GL as GL
                    import numpy as np
                    import threading
                    
                    # Use primary compositor for VR streaming
                    streaming_compositor = self.compositor
                    
                    # Create frame cache (populated by Qt signal, consumed by streaming thread)
                    self._vr_streaming_active = True
                    self._vr_last_frame = None
                    self._vr_frame_lock = threading.Lock()
                    
                    def capture_frame():
                        """Return cached frame for VR streaming (called from streaming thread)"""
                        if not self._vr_streaming_active:
                            return None
                        
                        # Return cached frame (NEVER call GL functions from streaming thread)
                        with self._vr_frame_lock:
                            if self._vr_last_frame is not None:
                                frame = self._vr_last_frame.copy()  # Copy to avoid race conditions
                                return frame
                        
                        return None  # No frame available yet
                    
                    # Create streaming server with frame callback
                    self.vr_streaming_server = VRStreamingServer(
                        width=1920,
                        height=1080,
                        fps=30,
                        encoder_type=EncoderType.JPEG,
                        quality=25,  # Optimized for Oculus Go
                        frame_callback=capture_frame
                    )
                    
                    # Start streaming server (TCP 5555)
                    self.vr_streaming_server.start_server()
                    self.logger.info("[session] VR streaming server started on TCP port 5555")
                    
                    # Connect compositor's frame_ready signal to cache frames
                    if hasattr(streaming_compositor, 'frame_ready'):
                        if self._vr_frame_handler is None:
                            def on_frame_ready(frame):
                                """Cache frame from compositor (called from Qt main thread with GL context active)"""
                                if self._vr_streaming_active and frame is not None and frame.size > 0:
                                    try:
                                        with self._vr_frame_lock:
                                            self._vr_last_frame = frame.copy()
                                    except Exception as e:  # pragma: no cover - defensive
                                        self.logger.error(f"[session] VR frame cache error: {e}")

                            self._vr_frame_handler = on_frame_ready

                        if hasattr(streaming_compositor, 'set_vr_capture_enabled'):
                            try:
                                streaming_compositor.set_vr_capture_enabled(True, max_fps=30)
                            except Exception:
                                pass
                        else:
                            streaming_compositor._vr_capture_enabled = True
                        try:
                            streaming_compositor.frame_ready.connect(self._vr_frame_handler)
                        except Exception:
                            pass
                        self.logger.info("[session] VR streaming connected to compositor frame_ready signal")
                        self.logger.info(f"[session] VR streaming: compositor size={streaming_compositor.width()}x{streaming_compositor.height()}")
                        
                        # If VR-only mode (no monitors selected), minimize the compositor window
                        if not monitor_displays:
                            streaming_compositor.showMinimized()
                            self.logger.info("[session] VR-only mode: minimized compositor window")
                    else:
                        self.logger.warning("[session] Compositor missing frame_ready signal for VR streaming")
                        
                except Exception as e:
                    self.logger.error(f"[session] Failed to start VR streaming: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Register cycle callback for cue transitions
        if not self._cue_callback_registered:
            self.visual_director.register_cycle_callback(self._on_cycle_boundary)
            self._cue_callback_registered = True
        
        # Emit session start event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.SESSION_START,
            data={"cuelist_name": self.cuelist.name, "total_cues": len(self.cuelist.cues)}
        ))
        
        # Warm the streaming worker before the first cue to avoid stalls
        if self.audio_engine:
            warmup = getattr(self.audio_engine, "ensure_stream_worker_ready", None)
            if callable(warmup):
                try:
                    warmup()
                except Exception as exc:  # pragma: no cover - defensive logging only
                    self.logger.warning("[session] Stream worker warmup failed: %s", exc)

        # Start first cue
        self._reset_audio_buffer_tracking()
        # Prefetch only the active cue up front; keep synchronous to avoid jitter
        # before the opening cue starts. Runtime transitions leverage async prefetch.
        self._prefetch_cue_audio(0, async_allowed=False)
        return self._start_cue(0)
    
    def stop(self) -> None:
        """Stop session execution and cleanup."""
        if self._state == SessionState.STOPPED:
            return
        
        prev_state = self._state
        self._state = SessionState.STOPPED
        
        self.logger.info("[session] Stopping session")
        
        # If paused, resume first to ensure clean state transition
        if prev_state == SessionState.PAUSED:
            self.logger.debug("[session] Resuming from pause before stop")
            if self.audio_engine:
                try:
                    self.audio_engine.resume_all()
                except Exception as exc:
                    self.logger.warning(f"[session] Audio resume before stop failed: {exc}")
            self.visual_director.resume()
        
        # End current cue if running
        if self._current_cue_index >= 0:
            self._end_cue()
        
        # === AUDIO INTEGRATION: Stop all audio channels ===
        if self.audio_engine:
            self.audio_engine.stop_all()
            self.logger.debug("[session] Stopped all audio channels")
            self._audio_role_channels.clear()
            self._active_hypno_duration = None
            self._active_stream_role = None
            canceler = getattr(self.audio_engine, "cancel_stream_handle", None)
            if callable(canceler):
                for ctx in self._pending_streams.values():
                    handle = ctx.get("handle")
                    if handle:
                        canceler(handle)
        self._prefetched_cues.clear()
        self._reset_audio_buffer_tracking()
        self._prefetch_jobs.clear()
        if self._prefetch_worker:
            self._prefetch_worker.cancel_pending(drop_completed=True)
        self._pending_streams.clear()
        
        # Unregister cycle callbacks
        if self._cue_callback_registered:
            self.visual_director.unregister_cycle_callback(self._on_cycle_boundary)
            self._cue_callback_registered = False
        if self._playback_callback_registered:
            self.visual_director.unregister_cycle_callback(self._on_playback_cycle_boundary)
            self._playback_callback_registered = False
        
        # Stop VR streaming
        if self.vr_streaming_server:
            try:
                self._vr_streaming_active = False
                with self._vr_frame_lock:
                    self._vr_last_frame = None
                if self.compositor and hasattr(self.compositor, 'frame_ready') and self._vr_frame_handler:
                    try:
                        self.compositor.frame_ready.disconnect(self._vr_frame_handler)
                    except Exception:
                        pass
                    self._vr_frame_handler = None
                if self.compositor and hasattr(self.compositor, 'set_vr_capture_enabled'):
                    try:
                        self.compositor.set_vr_capture_enabled(False)
                    except Exception:
                        pass
                elif self.compositor and hasattr(self.compositor, '_vr_capture_enabled'):
                    self.compositor._vr_capture_enabled = False
                self.vr_streaming_server.stop_server()
                self.vr_streaming_server = None
                self.logger.info("[session] VR streaming server stopped")
            except Exception as e:
                self.logger.error(f"[session] Failed to stop VR streaming: {e}")
        
        # Deactivate and cleanup compositors (fast path - no blocking operations)
        if self.compositor:
            # Deactivate primary compositor immediately
            self.compositor.set_active(False)
            # Hide asynchronously to avoid blocking
            try:
                self.compositor.hide()
            except Exception as e:
                self.logger.debug(f"[session] Compositor hide error (non-critical): {e}")
            self.logger.info("[session] Primary compositor deactivated and hidden")
            
            # Cleanup secondary compositors quickly
            count = len(self._secondary_compositors)
            for i, secondary in enumerate(self._secondary_compositors, start=1):
                try:
                    # Unregister from VisualDirector
                    self.visual_director.unregister_secondary_compositor(secondary)
                    
                    # Deactivate and schedule cleanup (non-blocking)
                    secondary.set_active(False)
                    try:
                        secondary.hide()
                    except:
                        pass  # Ignore hide errors
                    secondary.deleteLater()  # Schedule for Qt deletion
                except Exception as e:
                    self.logger.debug(f"[session] Secondary compositor {i} cleanup error (non-critical): {e}")
            
            self._secondary_compositors.clear()
            self.logger.info(f"[session] All compositors deactivated ({1 + count} total)")
        
        # Emit stop event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.SESSION_STOP if prev_state == SessionState.RUNNING else SessionEventType.SESSION_END,
            data={"total_time": self._get_elapsed_time()}
        ))
        
        # Reset state
        self._current_cue_index = -1
        self._cue_start_time = None
        self._session_start_time = None
        self._pending_transition = False
        self._pending_transition_since_ts = None
        self._transition_target_cue = None
    
    def pause(self) -> bool:
        """Pause session execution.
        
        Returns:
            True if paused, False if not running
        """
        if self._state != SessionState.RUNNING:
            self.logger.warning(f"[session] Cannot pause: state is {self._state.name}")
            return False
        
        self._state = SessionState.PAUSED
        self._pause_start_time = time.time()
        
        self.logger.info("[session] Session paused")
        
        # Pause visual director
        self.visual_director.pause()
        if self.audio_engine:
            try:
                self.audio_engine.pause_all()
            except Exception as exc:
                self.logger.warning(f"[session] Audio pause failed: {exc}")
        
        # Emit pause event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.SESSION_PAUSE,
            data={"cue_index": self._current_cue_index}
        ))
        
        return True
    
    def resume(self) -> bool:
        """Resume session execution from pause.
        
        Returns:
            True if resumed, False if not paused
        """
        if self._state != SessionState.PAUSED:
            self.logger.warning(f"[session] Cannot resume: state is {self._state.name}")
            return False
        
        # Calculate pause duration
        if self._pause_start_time:
            pause_duration = time.time() - self._pause_start_time
            self._total_paused_time += pause_duration
            self._pause_start_time = None
        
        self._state = SessionState.RUNNING
        
        self.logger.info("[session] Session resumed")
        
        if self.audio_engine:
            try:
                self.audio_engine.resume_all()
            except Exception as exc:
                self.logger.warning(f"[session] Audio resume failed: {exc}")
        
        # Resume visual director
        self.visual_director.resume()
        
        # Emit resume event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.SESSION_RESUME,
            data={"cue_index": self._current_cue_index}
        ))
        
        return True
    
    # ===== Cue Lifecycle =====

    def _prefetch_cue_audio(
        self,
        cue_index: Optional[int],
        *,
        force: bool = False,
        async_allowed: bool = True,
    ) -> None:
        """Ensure upcoming cue audio is cached before transitions fire."""
        if (
            cue_index is None
            or self.audio_engine is None
            or cue_index < 0
            or cue_index >= len(self.cuelist.cues)
        ):
            return

        span = self._perf_span(
            "prefetch_cue",
            category="audio",
            cue_index=cue_index,
            force=bool(force),
            async_allowed=bool(async_allowed),
        )
        with span:
            if force:
                self._prefetched_cues.discard(cue_index)
                self._prefetch_backlog.discard(cue_index)
                self._prefetch_jobs.pop(cue_index, None)

            if cue_index in self._prefetched_cues and not force:
                span.annotate(result="cached")
                return

            cue = self.cuelist.cues[cue_index]
            if not cue.audio_tracks:
                self._prefetched_cues.add(cue_index)
                self._prefetch_backlog.discard(cue_index)
                span.annotate(result="no-tracks")
                return

            needs_retry = False
            async_jobs = False

            for track in cue.audio_tracks:
                file_path = str(track.file_path)
                role = track.role if isinstance(track.role, AudioRole) else AudioRole.GENERIC

                outcome = self._reserve_audio_buffer(
                    cue_index=cue_index,
                    role=role,
                    file_path=file_path,
                    cue_duration=cue.duration_seconds,
                    active=False,
                    allow_eviction=False,
                )

                if outcome == _ReserveOutcome.DEFER:
                    needs_retry = True
                    continue
                if outcome == _ReserveOutcome.STREAM:
                    continue  # Streaming paths do not require preload work

                normalized = str(file_path)
                normalizer = getattr(self.audio_engine, "normalize_track_path", None)
                if callable(normalizer):
                    try:
                        candidate = normalizer(file_path)
                    except Exception as exc:  # pragma: no cover - defensive logging
                        self.logger.debug("[session] normalize_track_path failed for %s: %s", file_path, exc)
                    else:
                        if isinstance(candidate, str) and candidate:
                            normalized = candidate
                if normalized in self._prefetch_jobs.get(cue_index, set()):
                    async_jobs = True
                    continue

                submitted = False
                if async_allowed and self._prefetch_worker:
                    job = PrefetchJob(cue_index=cue_index, role=role, path=normalized)
                    submitted = self._prefetch_worker.submit(job)
                    if submitted:
                        self._track_prefetch_job(cue_index, normalized)
                        async_jobs = True

                if submitted:
                    continue

                # Fallback to synchronous preload (rare: worker disabled/unavailable)
                try:
                    start = time.perf_counter()
                    ok = self.audio_engine.preload_sound(file_path)
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    if elapsed_ms > 40.0:
                        self.logger.warning(
                            "[perf] Sync audio preload of %s took %.1fms (cue %d)",
                            Path(file_path).name,
                            elapsed_ms,
                            cue_index,
                        )
                    self._record_blocking_operation(
                        "audio_prefetch_sync",
                        elapsed_ms,
                        cue_index=cue_index,
                        track=Path(file_path).name,
                        role=role.value,
                        reason="worker-disabled" if not async_allowed else "fallback",
                    )
                    if not ok:
                        needs_retry = True
                        self._release_audio_buffer_for_path(file_path)
                except Exception as exc:
                    needs_retry = True
                    self._release_audio_buffer_for_path(file_path)
                    self.logger.warning(
                        "[session] Audio prefetch failed for cue %d track %s: %s",
                        cue_index,
                        track.file_path,
                        exc,
                    )

            if needs_retry:
                self._mark_prefetch_pending(cue_index)
                span.annotate(result="retry", async_jobs=async_jobs)
                return

            if async_jobs:
                span.annotate(result="async", jobs=len(self._prefetch_jobs.get(cue_index, [])))
                return  # Completion handler will finalize cue readiness

            self._prefetched_cues.add(cue_index)
            self._prefetch_backlog.discard(cue_index)
            span.annotate(result="ready", async_jobs=False)

    
    def _ensure_audio_prefetch_window(self) -> None:
        """Keep at least one upcoming cue's audio decoded as we near cue end."""
        if (
            self._current_cue_index < 0
            or not self.audio_engine
            or not self.cuelist.cues
        ):
            return

        cue = self.cuelist.cues[self._current_cue_index]
        remaining = cue.duration_seconds - self._get_cue_elapsed_time()
        if remaining <= self._audio_prefetch_lead_seconds:
            self._prefetch_cue_audio(self._peek_next_cue_index())
        self._retry_prefetch_backlog()

    def _update_pending_streaming_tracks(self) -> None:
        """Poll async streaming handles so they can finish without blocking update."""
        if not self.audio_engine or not self._pending_streams:
            return
        for role, ctx in list(self._pending_streams.items()):
            handle = ctx.get("handle")
            if not handle:
                self._pending_streams.pop(role, None)
                continue
            outcome = self.audio_engine.poll_stream_handle(handle)
            if outcome is None:
                continue
            success, elapsed_ms, error = outcome
            track_name = ctx.get("track", "unknown")
            reason = ctx.get("reason", "async")
            if success:
                self._active_stream_role = role
                self.logger.info(
                    "[session] Streaming %s audio ready: %s (%s, %.1fms)",
                    role.value,
                    track_name,
                    reason,
                    elapsed_ms,
                )
            else:
                if error:
                    self.logger.warning(
                        "[session] Streaming async failed for %s (%s): %s",
                        track_name,
                        role.value,
                        error,
                    )
                else:
                    self.logger.info(
                        "[session] Streaming %s audio cancelled: %s",
                        role.value,
                        track_name,
                    )
            self._pending_streams.pop(role, None)

    def _await_cue_audio_ready(self, cue_index: int) -> bool:
        """Wait briefly for async decode jobs to finish for the active cue."""
        if (
            not self._prefetch_worker
            or cue_index < 0
            or cue_index not in self._prefetch_jobs
        ):
            return True

        timeout_s = self._audio_prefetch_wait_ms / 1000.0
        if timeout_s <= 0:
            return False

        with self._perf_span("await_prefetch", category="audio", cue_index=cue_index, timeout_ms=self._audio_prefetch_wait_ms) as span:
            deadline = time.perf_counter() + timeout_s
            while time.perf_counter() < deadline:
                if cue_index not in self._prefetch_jobs:
                    span.annotate(result="ready")
                    return True
                self._prefetch_worker.wait_for_cues({cue_index}, timeout=0.02)
                self._process_completed_prefetch_jobs()

            if cue_index in self._prefetch_jobs:
                self.logger.warning(
                    "[session] Audio prefetch timeout after %.0fms for cue %d",
                    self._audio_prefetch_wait_ms,
                    cue_index,
                )
                span.annotate(result="timeout")
                return False
            span.annotate(result="ready-late")
            return True

    def _determine_selection_mode(self, cue: 'Cue') -> tuple[PlaybackSelectionMode, bool]:
        """Resolve the effective playback selection mode for a cue.

        Legacy cues created before selection modes defaulted to cycle-based switching
        often configured min/max durations on pool entries while leaving the mode at
        ON_CUE_START. To preserve that behavior, detect this scenario and promote the
        cue to ON_MEDIA_CYCLE so duration constraints take effect.

        Returns:
            Tuple of (resolved_mode, override_applied)
        """
        mode = cue.selection_mode
        override = False

        if mode == PlaybackSelectionMode.ON_CUE_START and len(cue.playback_pool) > 1:
            has_duration_constraints = any(
                (entry.min_duration_s is not None)
                or (entry.max_duration_s is not None)
                or (entry.min_cycles is not None)
                or (entry.max_cycles is not None)
                for entry in cue.playback_pool
            )
            if has_duration_constraints:
                mode = PlaybackSelectionMode.ON_MEDIA_CYCLE
                override = True

        return mode, override

    def _start_cue(self, cue_index: int) -> bool:
        """Start a specific cue.
        
        Args:
            cue_index: Index of cue to start
        
        Returns:
            True if started successfully, False on error
        """
        if cue_index < 0 or cue_index >= len(self.cuelist.cues):
            self.logger.error(f"[session] Invalid cue index: {cue_index}")
            return False
        
        cue = self.cuelist.cues[cue_index]
        resolved_mode, override = self._determine_selection_mode(cue)
        self._active_selection_mode = resolved_mode
        self._selection_mode_override_active = override
        if override:
            self.logger.warning(
                "[session] Cue '%s' configured playback durations but selection_mode=%s; "
                "enabling cycle-based switching so min/max durations take effect.",
                cue.name,
                cue.selection_mode.value,
            )
        self._prefetched_cues.discard(cue_index)
        self._prefetch_backlog.discard(cue_index)
        self._current_cue_index = cue_index
        self._cue_start_time = time.time()
        self._cue_start_cycle = self.visual_director.get_cycle_count()
        self._playback_history.clear()  # Reset history for new cue
        
        # Update visual director with current cue settings (for vibration on text cycle)
        cue_settings = {
            'vibrate_on_text_cycle': cue.vibrate_on_text_cycle,
            'vibration_intensity': cue.vibration_intensity,
            'video_audio': {
                'enabled': cue.enable_video_audio,
                'volume': cue.video_audio_volume,
            },
        }
        self.visual_director.set_current_cue_settings(cue_settings)
        
        self.logger.info(f"[session] Starting cue {cue_index}: '{cue.name}' (duration={cue.duration_seconds}s)")
        
        # Select and load first playback from cue's pool
        select_span = self._perf_span(
            "select_playback",
            category="cue",
            cue_index=cue_index,
            cue_name=cue.name,
        )
        with select_span:
            playback_entry, playback_path = self._select_playback_from_pool(cue)
            if not playback_path or not playback_entry:
                select_span.annotate(result="failed")
                self.logger.error(f"[session] Failed to select playback for cue '{cue.name}'")
                return False
            select_span.annotate(
                result="ok",
                playback=getattr(playback_path, "name", str(playback_path)),
            )
        
        # Track current playback for time-based switching
        self._current_playback_entry = playback_entry
        self._playback_start_time = time.time()
        
        # Determine target duration (random between min and max in seconds)
        import random
        
        # Use duration-based fields if available, otherwise fall back to legacy cycle-based
        if playback_entry.min_duration_s is not None or playback_entry.max_duration_s is not None:
            min_duration = playback_entry.min_duration_s or 5.0
            max_duration = playback_entry.max_duration_s or 30.0
        else:
            # Legacy: convert cycles to approximate duration (assume ~10s per cycle as baseline)
            min_cycles = playback_entry.min_cycles or 1
            max_cycles = playback_entry.max_cycles or 3
            min_duration = min_cycles * 10.0
            max_duration = max_cycles * 10.0
        
        self._playback_target_duration = random.uniform(min_duration, max_duration)
        self._playback_switch_pending = False
        self.logger.debug(f"[session] Playback will run for {self._playback_target_duration:.1f}s (range: {min_duration:.1f}-{max_duration:.1f}s)")
        
        with self._perf_span(
            "load_playback",
            category="visual",
            cue_index=cue_index,
            playback=getattr(playback_path, "name", str(playback_path)),
        ) as load_span:
            success = self.visual_director.load_playback(playback_path)
            load_span.annotate(result="ok" if success else "failed")
        if not success:
            self.logger.error(f"[session] Failed to load playback: {playback_path}")
            return False
        
        # CRITICAL: Reset text scroll state BEFORE applying custom text
        # This prevents carousel scroll offset from carrying over between cues
        # Must be done AFTER load_playback (which sets split mode from JSON)
        # but BEFORE _apply_custom_text (which preserves the split mode)
        if self.visual_director.text_director and hasattr(self.visual_director.text_director, 'reset'):
            self.visual_director.text_director.reset()
            self.logger.debug("[session] Reset text director scroll state before applying custom text")
        
        # Apply custom text messages if specified in the cue
        if cue.text_messages:
            self._apply_custom_text(cue.text_messages)
            self.logger.info(f"[session] Applied {len(cue.text_messages)} custom text messages for cue '{cue.name}'")
        
        # Start playback (load media and begin cycling)
        self.visual_director.start_playback()
        self.logger.info(f"[session] Playback started: {playback_path.name}")
        
        # === AUDIO INTEGRATION: Start audio tracks for this cue ===
        if self.audio_engine and cue.audio_tracks:
            with self._perf_span(
                "cue_audio_start",
                category="audio",
                cue_index=cue_index,
                track_count=len(cue.audio_tracks),
            ) as audio_span:
                audio_start = time.perf_counter()
                self._audio_role_channels.clear()
                self._active_hypno_duration = None
                if self.audio_engine.is_streaming_active():
                    self.audio_engine.stop_streaming_track(fade_ms=0)
                self._active_stream_role = None
                prefetch_ready = self._await_cue_audio_ready(cue_index)

                ordered_tracks: list[tuple[AudioRole, Any]] = []
                hypno_track = cue.get_audio_track(AudioRole.HYPNO)
                if hypno_track:
                    ordered_tracks.append((AudioRole.HYPNO, hypno_track))
                background_track = cue.get_audio_track(AudioRole.BACKGROUND)
                if background_track:
                    ordered_tracks.append((AudioRole.BACKGROUND, background_track))
                # Append any legacy/generic roles after the explicit ones
                for track in cue.audio_tracks:
                    if track.role not in (AudioRole.HYPNO, AudioRole.BACKGROUND):
                        ordered_tracks.append((track.role, track))

                channel_index = 0
                max_channels = self.audio_engine.num_channels

                def _start_stream_track(role: AudioRole, track: Any, loop_flag: bool, reason: str) -> bool:
                    if self._active_stream_role is not None:
                        self.audio_engine.stop_streaming_track(fade_ms=0)
                        self._active_stream_role = None
                    pending = self._pending_streams.pop(role, None)
                    if pending:
                        canceler = getattr(self.audio_engine, "cancel_stream_handle", None)
                        if callable(canceler):
                            handle = pending.get("handle")
                            if handle:
                                canceler(handle)
                    async_start = getattr(self.audio_engine, "play_streaming_track_async", None)
                    if callable(async_start):
                        handle = async_start(
                            str(track.file_path),
                            volume=track.volume,
                            fade_ms=track.fade_in_ms,
                            loop=loop_flag,
                        )
                        if handle:
                            self._pending_streams[role] = {
                                "handle": handle,
                                "track": Path(track.file_path).name,
                                "reason": reason,
                            }
                            self.logger.info(
                                "[session] Streaming %s audio pending: %s (%s)",
                                role.value,
                                track.file_path.name,
                                reason,
                            )
                            return True
                    stream_start = time.perf_counter()
                    started = self.audio_engine.play_streaming_track(
                        str(track.file_path),
                        volume=track.volume,
                        fade_ms=track.fade_in_ms,
                        loop=loop_flag,
                    )
                    elapsed_ms = (time.perf_counter() - stream_start) * 1000.0
                    if elapsed_ms > 40.0:
                        self.logger.warning(
                            "[perf] Streaming start for %s took %.1fms",
                            Path(track.file_path).name,
                            elapsed_ms,
                        )
                    if started:
                        self._active_stream_role = role
                        self.logger.info(
                            "[session] Streaming %s audio: %s (%s)",
                            role.value,
                            track.file_path.name,
                            reason,
                        )
                    else:
                        self.logger.warning(
                            "[session] Streaming fallback failed for %s (%s)",
                            track.file_path,
                            reason,
                        )
                    return started

                for role, track in ordered_tracks:
                    if not track.file_path:
                        continue
                    file_path = str(track.file_path)
                    loop_flag = track.loop
                    if role == AudioRole.BACKGROUND:
                        loop_flag = True  # Background bed always loops to cover hypno duration

                    # Prefer streaming for oversized assets so we don't exhaust RAM
                    buffer_outcome = self._reserve_audio_buffer(
                        cue_index=cue_index,
                        role=role,
                        file_path=file_path,
                        cue_duration=cue.duration_seconds,
                        active=True,
                        allow_eviction=True,
                    )
                    budget_forces_stream = buffer_outcome != _ReserveOutcome.RESERVED
                    preferred_stream = budget_forces_stream or self.audio_engine.should_stream(file_path)
                    if not prefetch_ready and buffer_outcome == _ReserveOutcome.RESERVED:
                        preferred_stream = True
                        reason_hint = "prefetch pending"
                    else:
                        reason_hint = "threshold or forced" if preferred_stream else ""

                    if preferred_stream:
                        if budget_forces_stream:
                            reason = "buffer limit"
                        elif not prefetch_ready and buffer_outcome == _ReserveOutcome.RESERVED:
                            reason = reason_hint
                        else:
                            reason = "threshold or forced"
                        if _start_stream_track(role, track, loop_flag, reason):
                            if buffer_outcome == _ReserveOutcome.RESERVED:
                                self._release_audio_buffer_for_path(file_path)
                            continue
                        if budget_forces_stream:
                            self._release_audio_buffer_for_path(file_path)
                            self.logger.warning(
                                "[session] Streaming fallback failed for %s (buffer cap prevents decode)",
                                track.file_path,
                            )
                            continue
                        self.logger.warning(
                            "[session] Streaming failed for %s; attempting in-memory load",
                            track.file_path,
                        )

                    if budget_forces_stream:
                        # Could not reserve buffer and streaming failed, nothing else to try
                        continue

                    if channel_index >= max_channels:
                        self.logger.warning(
                            "[session] No free audio channels remain for %s track (max=%d)",
                            role.value,
                            max_channels,
                        )
                        self._release_audio_buffer_for_path(file_path)
                        continue

                    if not self.audio_engine.load_channel(channel_index, file_path):
                        self._release_audio_buffer_for_path(file_path)
                        if (self.audio_engine.should_stream(file_path) or budget_forces_stream) and _start_stream_track(
                            role,
                            track,
                            loop_flag,
                            "load failure fallback",
                        ):
                            continue
                        self.logger.warning(
                            f"[session] Failed to load {role.value} audio track: {track.file_path}"
                        )
                        continue

                    if not self.audio_engine.fade_in_and_play(
                        channel=channel_index,
                        fade_ms=track.fade_in_ms,
                        volume=track.volume,
                        loop=loop_flag
                    ):
                        self._release_audio_buffer_for_path(file_path)
                        self.logger.warning(
                            "[session] Failed to start playback on channel %d for %s",
                            channel_index,
                            track.file_path,
                        )
                        continue

                    self._audio_role_channels[role] = channel_index
                    length = self.audio_engine.get_channel_length(channel_index)
                    if role == AudioRole.HYPNO and length:
                        self._active_hypno_duration = length
                        self.logger.info(
                            f"[session] Hypno track duration ~{length:.1f}s, cue='{cue.name}', file='{track.file_path.name}'"
                        )

                    self.logger.debug(
                        "[session] Started %s audio (ch=%d): %s (fade=%dms, vol=%.2f, loop=%s)",
                        role.value,
                        channel_index,
                        track.file_path.name,
                        int(track.fade_in_ms),
                        track.volume,
                        loop_flag,
                    )

                    channel_index += 1

                total_audio_ms = (time.perf_counter() - audio_start) * 1000.0
                if total_audio_ms > 40.0:
                    self.logger.warning(
                        "[perf] Cue '%s' audio start took %.1fms",
                        cue.name,
                        total_audio_ms,
                    )
                audio_span.annotate(
                    duration_ms=round(total_audio_ms, 2),
                    prefetch_ready=prefetch_ready,
                    channels=len(self._audio_role_channels),
                    stream_role=self._active_stream_role.value if self._active_stream_role else None,
                )
        
        # Emit cue start event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.CUE_START,
            data={
                "cue_index": cue_index,
                "cue_name": cue.name,
                "duration": cue.duration_seconds,
                "playback_count": len(cue.playback_pool)
            }
        ))

        return True

    
    def _end_cue(self) -> None:
        """End the current cue."""
        if self._current_cue_index < 0:
            return
        
        cue = self.cuelist.cues[self._current_cue_index]
        cue_duration = self._get_cue_elapsed_time()
        
        self.logger.info(f"[session] Ending cue {self._current_cue_index}: '{cue.name}' (duration={cue_duration:.1f}s)")
        
        # === AUDIO INTEGRATION: Stop audio tracks with fade-out ===
        fade_ms_audio = cue.transition_out.duration_ms if cue.transition_out else 500
        if self.audio_engine:
            # Use transition_out fade duration if specified
            for i in range(self.audio_engine.num_channels):
                if self.audio_engine.is_playing(i):
                    self.audio_engine.fade_out_and_stop(i, fade_ms=fade_ms_audio)
                    self.logger.debug(f"[session] Fading out audio channel {i} ({fade_ms_audio}ms)")
            if self._active_stream_role is not None:
                self.audio_engine.stop_streaming_track(fade_ms=fade_ms_audio)
                self.logger.debug(
                    "[session] Fading out streaming %s audio", self._active_stream_role.value
                )
                self._active_stream_role = None
            self._audio_role_channels.clear()
            self._active_hypno_duration = None
            self._release_audio_buffers_for_cue(self._current_cue_index)

        if self.visual_director and hasattr(self.visual_director, "stop_video_audio"):
            try:
                self.visual_director.stop_video_audio(fade_ms=fade_ms_audio if self.audio_engine else 200)
            except Exception as exc:
                self.logger.debug("[session] Failed to stop video audio cleanly: %s", exc)
        
        # Emit cue end event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.CUE_END,
            data={
                "cue_index": self._current_cue_index,
                "cue_name": cue.name,
                "actual_duration": cue_duration
            }
        ))
    
    # ===== Playback Selection =====
    
    def _select_playback_from_pool(self, cue) -> tuple[Optional['PlaybackEntry'], Optional[Path]]:
        """Select a playback from cue's pool using weighted random selection.
        
        Uses entry.weight for probability. Higher weight = more likely.
        Avoids recently used playbacks when pool is large enough.
        
        Args:
            cue: The cue to select playback from
        
        Returns:
            Tuple of (PlaybackEntry, Path to playback file), or (None, None) on error
        """
        if not cue.playback_pool:
            self.logger.error(f"[session] Cue '{cue.name}' has empty playback pool")
            return None, None
        
        # Filter out recently used playbacks (if pool is large enough)
        available = [
            entry for entry in cue.playback_pool
            if Path(entry.playback_path).stem not in self._playback_history
        ]
        
        # If all playbacks were recently used, use full pool
        if not available:
            available = cue.playback_pool
        
        # Calculate total weight
        total_weight = sum(entry.weight for entry in available)
        if total_weight <= 0:
            self.logger.warning("[session] All weights are zero, using equal probability")
            selected = random.choice(available)
        else:
            # Weighted random selection
            rand_value = random.uniform(0, total_weight)
            cumulative = 0.0
            selected = available[-1]  # Fallback
            
            for entry in available:
                cumulative += entry.weight
                if rand_value <= cumulative:
                    selected = entry
                    break
        
        # Add to history
        self._playback_history.append(Path(selected.playback_path).stem)
        if len(self._playback_history) > self._history_limit:
            self._playback_history.pop(0)
        
        playback_path = Path(selected.playback_path)
        self.logger.info(f"[session] Selected playback (weighted): {playback_path.name}")
        return selected, playback_path
    
    # ===== Update Loop and Transition Detection =====
    
    def update(self, dt: float = 0.0) -> None:
        """Update session state (called every frame at 60fps).
        
        Args:
            dt: Delta time in seconds (for future use, currently unused)
        """
        if self._state != SessionState.RUNNING:
            return

        self._process_completed_prefetch_jobs()
        
        # Track frame timing
        import time
        current_time = time.perf_counter()
        frame_delta_ms = 0.0
        if self._last_frame_time is not None:
            frame_delta_ms = (current_time - self._last_frame_time) * 1000.0
            self._frame_times.append(frame_delta_ms)
            
            # Log severe spikes (>100ms = 6x budget) and capture latest blocker
            if frame_delta_ms > self._frame_spike_warn_ms:
                blocker = self._recent_blocking_operation()
                if blocker:
                    cause = blocker.get("operation", "unknown")
                    track = blocker.get("metadata", {}).get("track")
                    if track:
                        cause = f"{cause}:{track}"
                else:
                    cause = "unknown"
                self.logger.warning(
                    "[perf] SEVERE frame spike: %.2fms (blocker=%s)",
                    frame_delta_ms,
                    cause,
                )
                self._record_frame_spike(frame_delta_ms)
            
            # Keep only last 10000 frames to avoid memory growth
            if len(self._frame_times) > 10000:
                self._frame_times = self._frame_times[-10000:]
        self._last_frame_time = current_time
        
        # Track memory usage periodically
        self._frame_count += 1
        if self._frame_count % self._memory_sample_interval == 0:
            mem_mb = self._process.memory_info().rss / 1024 / 1024
            self._memory_samples.append(mem_mb)
            if len(self._memory_samples) > 200:  # Keep last 200 samples
                self._memory_samples = self._memory_samples[-200:]
            
            # Warn if memory is growing excessively
            if len(self._memory_samples) >= 10:
                recent_avg = sum(self._memory_samples[-10:]) / 10
                if recent_avg > 5000:  # >5GB
                    self.logger.warning(f"[memory] HIGH: {mem_mb:.0f}MB (avg last 1000 frames: {recent_avg:.0f}MB)")
        
        # Track operation times for spike diagnosis
        visual_start = time.perf_counter()
        
        # === VISUAL DIRECTOR: Advance media cycler and process async image loading ===
        if self.visual_director:
            self.visual_director.update(dt)
        
        visual_duration = (time.perf_counter() - visual_start) * 1000.0
        if visual_duration > 20.0:  # Log if visual update takes >20ms
            self.logger.warning(f"[perf] Visual director update took {visual_duration:.2f}ms")
        
        # === TRANSITION FADE: Update fade alpha if transition in progress ===
        if self._transition_in_progress:
            self._update_transition_fade()
        
        # === AUDIO INTEGRATION: Update audio engine state ===
        if self.audio_engine:
            self.audio_engine.update()
            self._decay_active_audio_buffers(frame_delta_ms / 1000.0)
            self._ensure_audio_prefetch_window()
            self._update_pending_streaming_tracks()
        
        # === PLAYBACK POOL SWITCHING: Check if we should switch playbacks ===
        self._check_playback_switch()
        
        # Check for transition triggers
        if self._check_transition_trigger():
            self._request_transition()

        # Safety net: if we are waiting for a cycle boundary that never arrives,
        # force the transition so cue durations are respected.
        if self._pending_transition:
            self._force_transition_if_stuck()

    def _force_transition_if_stuck(self) -> None:
        """Force a pending cue transition when cycle boundaries do not arrive.

        Transitions are designed to be cycle-synchronized, but some visuals/media
        modes may not emit cycle boundaries (or may emit them extremely rarely).
        Without a fallback, cues (and ONCE-mode sessions) can run indefinitely.
        """
        if not self._pending_transition or self._transition_target_cue is None:
            return

        # If we're ending the session (next cue < 0), do not wait for a cycle boundary.
        if self._transition_target_cue < 0:
            cue_elapsed = self._get_cue_elapsed_time()
            cue = None
            if 0 <= self._current_cue_index < len(self.cuelist.cues):
                cue = self.cuelist.cues[self._current_cue_index]

            if cue is None or cue_elapsed >= cue.duration_seconds:
                self.logger.info("[session] Forcing session end (no cycle boundary required)")
                target = self._transition_target_cue
                self._pending_transition = False
                self._pending_transition_since_ts = None
                self._transition_target_cue = None
                self._execute_transition(target)
            return

        if self._pending_transition_since_ts is None:
            self._pending_transition_since_ts = time.perf_counter()
            return

        waited_s = time.perf_counter() - self._pending_transition_since_ts

        # Timeout scales with observed cycle interval; if we've never observed a
        # cycle boundary, fall back to a small constant.
        base_interval_s = float(self._cycle_boundary_interval_ema_s or 1.0)
        timeout_s = max(0.75, min(10.0, 2.5 * base_interval_s))

        if waited_s < timeout_s:
            return

        self.logger.warning(
            "[session] Forcing cue transition after %.2fs waiting for cycle boundary (timeout=%.2fs)",
            waited_s,
            timeout_s,
        )

        target = self._transition_target_cue
        self._pending_transition = False
        self._pending_transition_since_ts = None
        self._transition_target_cue = None
        self._execute_transition(target)
    
    def _check_playback_switch(self) -> None:
        """Check if we should switch to a new playback from the pool (time-based with cycle sync)."""
        if self._current_cue_index < 0:
            return
        
        cue = self.cuelist.cues[self._current_cue_index]
        
        # Only switch if the effective selection mode wants cycle-based swapping
        if self._active_selection_mode != PlaybackSelectionMode.ON_MEDIA_CYCLE:
            return
        
        # Check if target duration has elapsed
        elapsed = time.time() - self._playback_start_time
        
        if elapsed >= self._playback_target_duration and not self._playback_switch_pending:
            # Duration reached - mark switch as pending and wait for next cycle boundary
            self._playback_switch_pending = True
            self.logger.info(f"[session] Playback duration reached ({elapsed:.1f}s >= {self._playback_target_duration:.1f}s), waiting for cycle boundary...")
            
            # Register playback cycle callback if not already registered
            if not self._playback_callback_registered:
                self.visual_director.register_cycle_callback(self._on_playback_cycle_boundary)
                self._playback_callback_registered = True
                self.logger.debug(f"[session] Registered playback cycle callback")
    
    def _process_playback_switch(self, *, force: bool = False) -> bool:
        """Execute a pending playback switch if conditions allow.

        Args:
            force: When True, perform the switch even if a cue transition
                is currently pending. This is used to honor duration
                guarantees before the runner advances to the next cue.

        Returns:
            True when a switch occurred, False otherwise.
        """
        if not self._playback_switch_pending or self._current_cue_index < 0:
            return False

        if self._pending_transition and not force:
            # Leave the pending switch intact so the transition callback can
            # execute it on the next boundary without dropping the request.
            self.logger.debug(
                "[session] Playback switch waiting on transition handler; keeping pending flag set"
            )
            return False

        cue = self.cuelist.cues[self._current_cue_index]

        if not force:
            self.logger.info(f"[session] Cycle boundary reached, switching playback now...")
        else:
            self.logger.info(
                "[session] Forcing playback switch before cue transition to honor duration constraints"
            )

        self._playback_switch_pending = False

        if self._playback_callback_registered:
            self.visual_director.unregister_cycle_callback(self._on_playback_cycle_boundary)
            self._playback_callback_registered = False
            self.logger.debug("[session] Unregistered playback cycle callback after switch")

        self._switch_playback(cue)
        return True

    def _on_playback_cycle_boundary(self) -> None:
        """Callback when cycle boundary reached during playback switching."""
        self._process_playback_switch(force=False)
    
    def _switch_playback(self, cue) -> None:
        """Switch to a new playback from the pool."""
        # Select new playback
        playback_entry, playback_path = self._select_playback_from_pool(cue)
        if not playback_path or not playback_entry:
            self.logger.error(f"[session] Failed to select new playback for cue '{cue.name}'")
            return
        
        # Load and start new playback
        # Note: load_playback() internally calls reset() on the visual
        success = self.visual_director.load_playback(playback_path)
        if not success:
            self.logger.error(f"[session] Failed to load playback: {playback_path}")
            return
        
        # Apply custom text messages if specified in the cue
        if cue.text_messages:
            self._apply_custom_text(cue.text_messages)
            self.logger.info(f"[session] Applied {len(cue.text_messages)} custom text messages for cue '{cue.name}'")
        
        self.visual_director.start_playback()
        self.logger.info(f"[session] Switched to playback: {playback_path.name}")
        
        # Update tracking and set new target duration
        self._current_playback_entry = playback_entry
        self._playback_start_time = time.time()
        
        import random
        
        # Use duration-based fields if available, otherwise fall back to legacy cycle-based
        if playback_entry.min_duration_s is not None or playback_entry.max_duration_s is not None:
            min_duration = playback_entry.min_duration_s or 5.0
            max_duration = playback_entry.max_duration_s or 30.0
        else:
            # Legacy: convert cycles to approximate duration
            min_cycles = playback_entry.min_cycles or 1
            max_cycles = playback_entry.max_cycles or 3
            min_duration = min_cycles * 10.0
            max_duration = max_cycles * 10.0
        
        self._playback_target_duration = random.uniform(min_duration, max_duration)
        self.logger.debug(f"[session] New playback will run for {self._playback_target_duration:.1f}s (range: {min_duration:.1f}-{max_duration:.1f}s)")
    
    def _apply_custom_text(self, text_messages: list[str]) -> None:
        """Apply custom text messages to the text director.
        
        Args:
            text_messages: List of text strings to display
        """
        if not self.visual_director or not hasattr(self.visual_director, 'text_director'):
            return
        
        text_director = self.visual_director.text_director
        if not text_director:
            return
        
        # Get current split mode from text director
        from ..content.text_renderer import SplitMode
        current_split_mode = getattr(text_director, '_current_split_mode', SplitMode.CENTERED_SYNC)
        
        # Set custom text library (user_set=False means it can be overridden by next playback)
        text_director.set_text_library(text_messages, default_split_mode=current_split_mode, user_set=False)
        self.logger.info(f"[session] Applied custom text library: {len(text_messages)} messages")
    
    def _check_transition_trigger(self) -> bool:
        """Check if current cue should transition to next playback or cue."""
        if self._current_cue_index < 0:
            return False
        
        cue = self.cuelist.cues[self._current_cue_index]
        
        # Check duration-based trigger
        cue_elapsed = self._get_cue_elapsed_time()
        if cue_elapsed >= cue.duration_seconds:
            # Only log if not already pending (avoid spam at 60fps)
            if not self._pending_transition:
                self.logger.info(f"[session] Duration trigger: {cue_elapsed:.1f}s >= {cue.duration_seconds}s")
            return True
        
        # TODO Phase 4: Add cycle-based triggers via PlaybackEntry.max_cycles
        # Would require tracking current playback entry and its cycle constraints
        
        return False
    
    def _request_transition(self) -> None:
        """Request transition to next cue (will wait for cycle boundary)."""
        if self._pending_transition:
            return  # Already pending
        
        self.logger.info("[session] Transition requested, waiting for cycle boundary...")
        self._pending_transition = True
        self._pending_transition_since_ts = time.perf_counter()

        # Determine next cue index
        self._transition_target_cue = self._calculate_next_cue_index()
        self._prefetch_cue_audio(self._transition_target_cue, force=True, async_allowed=True)
    
    def _on_cycle_boundary(self) -> None:
        """Callback fired when visual director crosses a cycle boundary."""
        now = time.perf_counter()
        if self._last_cycle_boundary_ts is not None:
            interval = now - self._last_cycle_boundary_ts
            interval = max(0.05, min(60.0, float(interval)))
            alpha = 0.25
            self._cycle_boundary_interval_ema_s = (
                (1.0 - alpha) * self._cycle_boundary_interval_ema_s + alpha * interval
            )
        self._last_cycle_boundary_ts = now

        if self._playback_switch_pending and self._pending_transition:
            if self._process_playback_switch(force=True):
                self.logger.debug(
                    "[session] Deferred cue transition until next cycle (playback switch just executed)"
                )
                return

        if not self._pending_transition:
            return

        if self._transition_target_cue is None:
            self.logger.error("[session] Pending transition but no target cue!")
            self._pending_transition = False
            return

        self.logger.info(f"[session] Cycle boundary reached, executing transition to cue {self._transition_target_cue}")
        
        # Execute the transition
        self._execute_transition(self._transition_target_cue)
        
        # Clear pending state
        self._pending_transition = False
        self._pending_transition_since_ts = None
        self._transition_target_cue = None
    
    def _log_frame_timing_stats(self) -> None:
        """Log frame timing statistics for the completed session."""
        if not self._frame_times:
            return
        
        total_frames = len(self._frame_times)
        avg_frame_time = sum(self._frame_times) / total_frames
        min_frame_time = min(self._frame_times)
        max_frame_time = max(self._frame_times)
        
        # Count on-time vs late frames
        on_time_frames = sum(1 for ft in self._frame_times if ft <= self._frame_budget_ms)
        late_frames = total_frames - on_time_frames
        on_time_percent = (on_time_frames / total_frames * 100) if total_frames > 0 else 0
        
        # Frame distribution
        bins = [0, 10, 15, 20, 30, 50, float('inf')]
        labels = ["0-10ms", "10-15ms", "15-20ms (BUDGET)", "20-30ms", "30-50ms", "50ms+"]
        counts = [0] * len(labels)
        
        # Use the entire session's frame samples for distribution
        for ft in self._frame_times:
            for i, (low, high) in enumerate(zip(bins[:-1], bins[1:])):
                if low <= ft < high:
                    counts[i] += 1
                    break
        
        self.logger.warning("")
        self.logger.warning("=" * 70)
        self.logger.warning("📊 FRAME TIMING STATISTICS")
        self.logger.warning("=" * 70)
        self.logger.warning(f"Total Frames: {total_frames}")
        self.logger.warning(f"Average: {avg_frame_time:.2f}ms")
        self.logger.warning(f"Min: {min_frame_time:.2f}ms")
        self.logger.warning(f"Max: {max_frame_time:.2f}ms")
        self.logger.warning(f"Budget: {self._frame_budget_ms:.2f}ms (60fps)")
        self.logger.warning(f"On-time: {on_time_frames}/{total_frames} ({on_time_percent:.1f}%)")
        self.logger.warning(f"Late: {late_frames}")
        self.logger.warning("")
        
        # Memory usage statistics
        if self._memory_samples:
            min_mem = min(self._memory_samples)
            max_mem = max(self._memory_samples)
            avg_mem = sum(self._memory_samples) / len(self._memory_samples)
            final_mem = self._memory_samples[-1]
            self.logger.warning("💾 MEMORY USAGE:")
            self.logger.warning(f"  Start: {self._memory_samples[0]:.0f}MB")
            self.logger.warning(f"  Peak: {max_mem:.0f}MB")
            self.logger.warning(f"  Final: {final_mem:.0f}MB")
            self.logger.warning(f"  Average: {avg_mem:.0f}MB")
            self.logger.warning(f"  Growth: {final_mem - self._memory_samples[0]:.0f}MB ({((final_mem / self._memory_samples[0]) - 1) * 100:.1f}%)")
            if final_mem > 10000:
                self.logger.warning(f"  ⚠️  MEMORY LEAK DETECTED: {final_mem:.0f}MB is excessive!")
            self.logger.warning("")

        if self._worst_frame_spike:
            blocker = self._worst_frame_spike.get("blocker")
            if blocker:
                summary = self._format_blocking_summary(blocker)
                self.logger.warning(
                    "⚡ Worst Frame Spike: %.1fms (blocked by %s)",
                    self._worst_frame_spike.get("delta_ms", 0.0),
                    summary,
                )
            else:
                self.logger.warning(
                    "⚡ Worst Frame Spike: %.1fms (cause unknown)",
                    self._worst_frame_spike.get("delta_ms", 0.0),
                )
        else:
            self.logger.warning(
                "⚡ Worst Frame Spike: none above %.0fms threshold",
                self._frame_spike_warn_ms,
            )
        
        self.logger.warning("📈 Frame Delay Distribution (all frames):")
        total_sampled = sum(counts)
        for label, count in zip(labels, counts):
            percent = (count / total_sampled * 100) if total_sampled > 0 else 0
            self.logger.warning(f"  {label}: {count} ({percent:.1f}%)")
        self.logger.warning("=" * 70)
        self.logger.warning("")
    
    def _execute_transition(self, next_cue_index: int) -> None:
        """Execute transition to next cue (with SNAP or FADE based on cuelist settings)."""
        # Emit transition start event
        self.event_emitter.emit(SessionEvent(
            SessionEventType.TRANSITION_START,
            data={
                "from_cue": self._current_cue_index,
                "to_cue": next_cue_index
            }
        ))
        with self._perf_span(
            "execute_transition",
            category="cue",
            from_cue=self._current_cue_index,
            to_cue=next_cue_index,
        ) as span:
            # Check for session completion
            if next_cue_index < 0:
                self.logger.info("[session] Session completed")
                self._log_frame_timing_stats()  # Log performance statistics
                self._end_cue()
                self._state = SessionState.COMPLETED
                self.event_emitter.emit(SessionEvent(
                    SessionEventType.SESSION_END,
                    data={"total_time": self._get_elapsed_time()}
                ))
                self.stop()
                span.annotate(result="completed")
                return
            
            # Get transition mode from cuelist
            transition_mode = self.cuelist.transition_mode or CuelistTransitionMode.SNAP
            span.annotate(mode=transition_mode.value)
            
            if transition_mode == CuelistTransitionMode.SNAP:
                # SNAP mode: instant transition at cycle boundary
                self.logger.info(f"[session] SNAP transition to cue {next_cue_index}")
                
                # End current cue
                self._end_cue()
                
                # Start next cue immediately
                success = self._start_cue(next_cue_index)
                span.annotate(success=success)
                
                # Emit transition end event
                self.event_emitter.emit(SessionEvent(
                    SessionEventType.TRANSITION_END,
                    data={
                        "from_cue": self._current_cue_index - 1 if success else -1,
                        "to_cue": next_cue_index,
                        "success": success,
                        "mode": "snap"
                    }
                ))
                
            else:  # FADE mode
                # FADE mode: start fade transition over specified duration
                fade_duration_s = (self.cuelist.transition_duration_ms or 2000.0) / 1000.0
                self.logger.info(f"[session] Starting FADE transition to cue {next_cue_index} (duration: {fade_duration_s:.2f}s)")
                span.annotate(fade_duration_s=fade_duration_s)
                
                # Start next cue (but keep old cue's visuals visible during fade)
                # Note: We don't call _end_cue() yet - we'll fade out the old cue
                success = self._start_cue(next_cue_index)
                span.annotate(success=success)
                
                if success:
                    # Initialize fade state
                    self._transition_in_progress = True
                    self._transition_start_time = time.time()
                    self._transition_fade_alpha = 1.0  # Start fully showing old cue
                    
                    # Note: The fade will be updated in update() method
                    # When fade completes (alpha reaches 0.0), we'll emit TRANSITION_END
                else:
                    # Failed to start new cue, abort fade
                    self.logger.error(f"[session] Failed to start cue {next_cue_index}, aborting fade")
                    self._end_cue()
                    self.event_emitter.emit(SessionEvent(
                        SessionEventType.TRANSITION_END,
                        data={
                            "from_cue": self._current_cue_index,
                            "to_cue": next_cue_index,
                            "success": False,
                            "mode": "fade"
                        }
                    ))
    
    def _update_transition_fade(self) -> None:
        """Update fade alpha during cue transition (FADE mode only)."""
        if not self._transition_in_progress or self._transition_start_time is None:
            return
        
        # Calculate fade progress
        elapsed = time.time() - self._transition_start_time
        fade_duration_s = (self.cuelist.transition_duration_ms or 2000.0) / 1000.0
        
        # Calculate alpha (1.0 = old cue visible, 0.0 = new cue visible)
        self._transition_fade_alpha = max(0.0, 1.0 - (elapsed / fade_duration_s))
        
        # Apply fade to visual director (if supported)
        # Note: This requires the visual director to support a master alpha/opacity control
        # For now, we'll just track the fade state and let it complete naturally
        # TODO: Implement visual_director.set_master_alpha() if needed
        
        # Check if fade is complete
        if self._transition_fade_alpha <= 0.0:
            self.logger.info(f"[session] Fade transition complete")
            
            # Finish transition
            self._transition_in_progress = False
            self._transition_start_time = None
            self._transition_fade_alpha = 1.0
            
            # Emit transition end event
            self.event_emitter.emit(SessionEvent(
                SessionEventType.TRANSITION_END,
                data={
                    "from_cue": self._current_cue_index - 1,
                    "to_cue": self._current_cue_index,
                    "success": True,
                    "mode": "fade"
                }
            ))
    
    def _peek_next_cue_index(self) -> Optional[int]:
        """Return the next cue index without mutating loop direction."""
        next_index = self._calculate_next_cue_index(mutate_state=False)
        return next_index if next_index >= 0 else None

    def _calculate_next_cue_index(self, mutate_state: bool = True) -> int:
        """Calculate the next cue index based on loop mode."""
        if self._current_cue_index < 0:
            return 0
        
        loop_mode = self.cuelist.loop_mode or CuelistLoopMode.ONCE
        total_cues = len(self.cuelist.cues)
        
        if loop_mode == CuelistLoopMode.ONCE:
            # Simple progression: 0 â†’ 1 â†’ 2 â†’ END
            next_index = self._current_cue_index + 1
            if next_index >= total_cues:
                return -1  # Session ends
            return next_index
        
        elif loop_mode == CuelistLoopMode.LOOP:
            # Loop back to start: 0 â†’ 1 â†’ 2 â†’ 0 â†’ 1 â†’ ...
            next_index = (self._current_cue_index + 1) % total_cues
            return next_index
        
        elif loop_mode == CuelistLoopMode.PING_PONG:
            # Bounce: 0 â†’ 1 â†’ 2 â†’ 1 â†’ 0 â†’ 1 â†’ ...
            loop_direction = self._loop_direction
            next_index = self._current_cue_index + loop_direction

            new_direction = loop_direction
            if next_index >= total_cues:
                new_direction = -1
                next_index = total_cues - 2  # Go back one
            elif next_index < 0:
                new_direction = 1
                next_index = 1  # Go forward one

            if mutate_state:
                self._loop_direction = new_direction
            return max(0, min(next_index, total_cues - 1))
        
        # Fallback
        return -1
    
    def _get_cycle_multiplier(self, playback_path) -> float:
        """
        Calculate cycle multiplier based on playback's cycle_speed.
        Higher cycle_speed = faster changes = need more cycles to maintain reasonable duration.
        
        Args:
            playback_path: Path to playback file or playback name/key
        
        Returns:
            Multiplier to apply to min/max cycles (1.0 = no scaling)
        """
        if not self.session_data or "playbacks" not in self.session_data:
            return 1.0
        
        # Extract playback name (could be Path object or string)
        if isinstance(playback_path, Path):
            # If it's a path, extract the stem (filename without extension)
            playback_name = playback_path.stem
        else:
            playback_name = str(playback_path)
        
        playback_data = self.session_data.get("playbacks", {}).get(playback_name)
        if not playback_data:
            return 1.0
        
        media_config = playback_data.get("media", {})
        cycle_speed = media_config.get("cycle_speed", 50)
        
        # Scale exponentially: speed 1-10 → 1x, speed 50 → 2x, speed 90-100 → 5-10x
        # Formula: multiplier = 1 + (cycle_speed / 50)^2
        # This gives: speed 10 → 1.04x, speed 50 → 2x, speed 75 → 3.25x, speed 100 → 5x
        multiplier = 1.0 + pow(cycle_speed / 50.0, 2.0)
        
        return multiplier
    
    # ===== Manual Control =====
    
    def skip_to_next_cue(self) -> bool:
        """Manually skip to next cue (cycle-synchronized)."""
        if self._state != SessionState.RUNNING:
            return False
        
        if self._pending_transition:
            return False  # Already transitioning
        
        self.logger.info("[session] Manual skip to next cue requested")
        self._request_transition()
        return True
    
    def skip_to_previous_cue(self) -> bool:
        """Manually skip to previous cue (cycle-synchronized)."""
        if self._state != SessionState.RUNNING:
            return False
        
        if self._pending_transition:
            return False
        
        # Calculate previous cue (respecting loop direction)
        prev_index = self._current_cue_index - 1
        if prev_index < 0:
            prev_index = len(self.cuelist.cues) - 1  # Wrap to last cue
        
        self.logger.info(f"[session] Manual skip to previous cue {prev_index} requested")
        self._pending_transition = True
        self._transition_target_cue = prev_index
        self._prefetch_cue_audio(prev_index)
        return True
    
    def skip_to_cue(self, cue_index: int) -> bool:
        """Manually skip to specific cue (cycle-synchronized)."""
        if self._state != SessionState.RUNNING:
            return False
        
        if cue_index < 0 or cue_index >= len(self.cuelist.cues):
            self.logger.error(f"[session] Invalid cue index: {cue_index}")
            return False
        
        if self._pending_transition:
            return False
        
        self.logger.info(f"[session] Manual skip to cue {cue_index} requested")
        self._pending_transition = True
        self._transition_target_cue = cue_index
        self._prefetch_cue_audio(cue_index)
        return True
    
    # ===== Helper Methods =====
    
    def _get_elapsed_time(self) -> float:
        """Get total session elapsed time (excluding pauses)."""
        if not self._session_start_time:
            return 0.0
        
        elapsed = time.time() - self._session_start_time - self._total_paused_time
        
        # If currently paused, don't count current pause duration
        if self._state == SessionState.PAUSED and self._pause_start_time:
            elapsed -= (time.time() - self._pause_start_time)
        
        return elapsed
    
    def _get_cue_elapsed_time(self) -> float:
        """Get time elapsed in current cue."""
        if not self._cue_start_time:
            return 0.0
        
        return time.time() - self._cue_start_time
