"""Background audio prefetch worker so cue transitions stay responsive."""
from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional, TYPE_CHECKING, Deque, Tuple

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .cue import AudioRole
    from ..engine.audio import AudioEngine


@dataclass(frozen=True)
class PrefetchJob:
    """Represents a single audio decode request for a cue/role/path tuple."""

    cue_index: int
    role: "AudioRole"
    path: str
    submitted_at: float = field(default_factory=time.perf_counter)


class AudioPrefetchWorker:
    """Serializes pygame decode work onto a background thread pool."""

    def __init__(
        self,
        audio_engine: Optional["AudioEngine"],
        *,
        max_workers: int = 1,
        thread_name_prefix: str = "audio-prefetch",
    ) -> None:
        self._audio_engine = audio_engine
        self._lock = Lock()
        self._pending: dict[Future, PrefetchJob] = {}
        self._completed: Deque[Tuple[PrefetchJob, bool, Optional[BaseException]]] = deque()
        self._shutdown = False
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )

    def submit(self, job: PrefetchJob) -> bool:
        """Queue an audio decode job if the worker is active."""
        if self._shutdown or not self._audio_engine:
            return False

        def _task(path: str) -> bool:
            return bool(self._audio_engine.preload_sound(path))

        future = self._executor.submit(_task, job.path)
        with self._lock:
            self._pending[future] = job
        future.add_done_callback(self._on_future_done)
        return True

    def _on_future_done(self, future: Future) -> None:
        job = None
        with self._lock:
            job = self._pending.pop(future, None)
        if not job:
            return

        success = False
        exc: Optional[BaseException] = None
        try:
            success = bool(future.result())
        except BaseException as err:  # pragma: no cover - defensive
            exc = err

        with self._lock:
            self._completed.append((job, success, exc))

    def drain_completed(self) -> list[Tuple[PrefetchJob, bool, Optional[BaseException]]]:
        """Return and clear all completed job results."""
        with self._lock:
            return list(self._completed.popleft() for _ in range(len(self._completed)))

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def pending_for_cue(self, cue_index: int) -> int:
        """Return number of in-flight jobs for a specific cue."""
        with self._lock:
            return sum(1 for job in self._pending.values() if job.cue_index == cue_index)

    def wait_for_cues(self, cue_indices: set[int] | list[int], *, timeout: float = 0.2) -> None:
        """Spin until the provided cues have no pending jobs or timeout expires."""
        if timeout <= 0:
            return
        deadline = time.perf_counter() + timeout
        cues = set(cue_indices)
        while cues and time.perf_counter() < deadline:
            outstanding = {cue for cue in cues if self.pending_for_cue(cue) > 0}
            if not outstanding:
                break
            time.sleep(0.005)
            cues = outstanding

    def cancel_pending(self, *, drop_completed: bool = False) -> None:
        """Cancel outstanding futures and optionally drop recorded results."""
        with self._lock:
            for future in list(self._pending.keys()):
                future.cancel()
            self._pending.clear()
            if drop_completed:
                self._completed.clear()

    def shutdown(self, *, wait: bool = False, cancel_futures: bool = True) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        if cancel_futures:
            self.cancel_pending(drop_completed=False)
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.shutdown(wait=False)
        except Exception:
            pass
