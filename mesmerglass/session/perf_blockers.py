from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Optional


_LOCK = threading.Lock()
# Keep a short history so we can attribute spikes even if the frame check
# happens slightly after the blocking operation completes.
_RECENT: deque[dict[str, Any]] = deque(maxlen=64)


def record(operation: str, duration_ms: float, **metadata: Any) -> None:
    if not operation:
        return
    try:
        dur = float(duration_ms)
    except Exception:
        return
    if dur <= 0:
        return

    rec: dict[str, Any] = {
        "operation": str(operation),
        "duration_ms": dur,
        "metadata": metadata or {},
        "timestamp": time.time(),
    }
    with _LOCK:
        _RECENT.append(rec)


def recent(ttl_s: float = 3.0) -> Optional[dict[str, Any]]:
    now = time.time()
    best: Optional[dict[str, Any]] = None
    with _LOCK:
        # Iterate newest → oldest.
        for rec in reversed(_RECENT):
            ts = float(rec.get("timestamp", 0.0) or 0.0)
            if (now - ts) > float(ttl_s):
                break
            best = rec
            break
    return best


def recent_all(ttl_s: float = 3.0) -> list[dict[str, Any]]:
    now = time.time()
    out: list[dict[str, Any]] = []
    with _LOCK:
        for rec in reversed(_RECENT):
            ts = float(rec.get("timestamp", 0.0) or 0.0)
            if (now - ts) > float(ttl_s):
                break
            out.append(rec)
    return out


def recent_max(
    ttl_s: float = 0.75,
    *,
    exclude_ops: Optional[set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Return the largest-duration record in the recent window.

    Args:
        ttl_s: Lookback window (seconds).
        exclude_ops: Optional set of operation labels to ignore.
    """
    candidates = recent_all(ttl_s=ttl_s)
    if not candidates:
        return None

    best: Optional[dict[str, Any]] = None
    best_dur = 0.0
    for rec in candidates:
        op = str(rec.get("operation") or "")
        if exclude_ops and op in exclude_ops:
            continue
        dur = float(rec.get("duration_ms", 0.0) or 0.0)
        if best is None or dur > best_dur:
            best = rec
            best_dur = dur
    return best


def recent_best(local: Optional[dict[str, Any]], ttl_s: float = 3.0) -> Optional[dict[str, Any]]:
    """Return whichever record is newer: `local` or global `recent()`."""
    global_rec = recent(ttl_s=ttl_s)
    if not global_rec:
        return local
    if not local:
        return global_rec

    try:
        local_ts = float(local.get("timestamp", 0.0) or 0.0)
    except Exception:
        local_ts = 0.0
    try:
        global_ts = float(global_rec.get("timestamp", 0.0) or 0.0)
    except Exception:
        global_ts = 0.0

    return global_rec if global_ts >= local_ts else local
