"""Utilities for warming audio caches ahead of cue playback."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Callable, Iterable, Any

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .cuelist import Cuelist
    from ..engine.audio import AudioEngine
    from ..logging_utils import PerfTracer

from ..logging_utils import PerfTracer

ProgressCallback = Callable[[int, int, str, bool], None]

logger = logging.getLogger(__name__)


def _normalize(path: Path | str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return str(path)


def gather_audio_paths_for_cuelist(
    cuelist: Optional["Cuelist"],
    *,
    max_cues: Optional[int] = None,
) -> list[str]:
    """Collect unique audio file paths for the first N cues in the cuelist."""
    if not cuelist or not cuelist.cues:
        return []

    limit = len(cuelist.cues) if max_cues is None else max(0, min(len(cuelist.cues), max_cues))
    if limit == 0:
        return []

    seen: set[str] = set()
    ordered: list[str] = []
    for cue in cuelist.cues[:limit]:
        if not getattr(cue, "audio_tracks", None):
            continue
        for track in cue.audio_tracks:
            if not track or not getattr(track, "file_path", None):
                continue
            normalized = _normalize(track.file_path)
            if normalized not in seen:
                seen.add(normalized)
                ordered.append(normalized)
    return ordered


def _perf_span(tracer: Optional["PerfTracer"], name: str, **metadata: Any):
    if tracer and tracer.enabled:
        return tracer.span(name, category="audio", metadata=metadata)
    return PerfTracer.noop_span()


def prefetch_audio_for_cuelist(
    audio_engine: Optional["AudioEngine"],
    cuelist: Optional["Cuelist"],
    *,
    max_cues: Optional[int] = None,
    file_paths: Optional[Iterable[str]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    perf_tracer: Optional["PerfTracer"] = None,
) -> dict[str, bool]:
    """Warm the AudioEngine cache for the cuelist's audio assets."""
    if not audio_engine:
        return {}

    tracer = perf_tracer if perf_tracer and perf_tracer.enabled else None

    paths = list(file_paths or gather_audio_paths_for_cuelist(cuelist, max_cues=max_cues))
    if not paths:
        return {}

    # Fast-path: if no UI needs incremental updates, use the batch helper.
    if progress_callback is None and hasattr(audio_engine, "prefetch_tracks"):
        with _perf_span(tracer, "audio_prefetch_batch", paths=len(paths)) as span:
            try:
                result = audio_engine.prefetch_tracks(paths) or {}  # type: ignore[attr-defined]
                span.annotate(result_count=len(result))
                return result
            except Exception as exc:  # pragma: no cover - defensive logging
                span.annotate(error=str(exc))
                logger.warning("Audio prefetch failed: %s", exc)
                return {}

    results: dict[str, bool] = {}
    total = len(paths)
    preload = getattr(audio_engine, "preload_sound", None)
    batch_prefetch = getattr(audio_engine, "prefetch_tracks", None)

    for idx, path in enumerate(paths, start=1):
        ok = False
        track_start = time.perf_counter()
        with _perf_span(
            tracer,
            "audio_prefetch_track",
            idx=idx,
            total=total,
            path=Path(path).name,
        ) as span:
            try:
                if callable(preload):
                    ok = bool(preload(path))
                elif callable(batch_prefetch):
                    batch_result = batch_prefetch([path]) or {}
                    ok = any(batch_result.values())
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Audio prefetch failed for %s: %s", path, exc)
                span.annotate(error=str(exc))
                ok = False
            span.annotate(result="ok" if ok else "fail")
            elapsed_ms = (time.perf_counter() - track_start) * 1000.0
            span.annotate(duration_ms=elapsed_ms)
            if elapsed_ms >= 750.0:
                logger.warning(
                    "[audio.prefetch] Track %s took %.1fms (idx=%d/%d)",
                    Path(path).name,
                    elapsed_ms,
                    idx,
                    total,
                )

        results[path] = ok

        if progress_callback:
            progress_callback(idx, total, path, ok)

    return results
