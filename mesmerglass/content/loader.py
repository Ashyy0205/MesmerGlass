"""Message pack (legacy "session pack") loader helpers.

Public function name kept for backward compatibility; user-facing strings
now reference "message pack".
"""

from __future__ import annotations

import json, time
from pathlib import Path
from typing import Union
from .models import build_session_pack, SessionPack, build_session_state, SessionState

MAX_SIZE_BYTES = 1_000_000


def load_session_pack(path: Union[str, Path]) -> SessionPack:
    start = time.perf_counter()
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"Message pack not found: {p}")
    if p.stat().st_size > MAX_SIZE_BYTES:
        raise ValueError("Message pack file too large (>1MB)")
    try:
        # Use utf-8-sig so UTF-8 files that include a BOM don't fail.
        raw = p.read_text(encoding="utf-8-sig")
        # Defensive strip of stray leading BOM if present after decode.
        if raw.startswith("\ufeff"):
            raw = raw.lstrip("\ufeff")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e.msg} (line {e.lineno})") from None
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object")
    pack = build_session_pack(data)
    # Soft timing guard (logically enforced via tests only)
    _elapsed_ms = (time.perf_counter() - start) * 1000.0
    return pack


def load_session_pack_from_json_str(raw: str) -> SessionPack:
    return build_session_pack(json.loads(raw))


# ------------------- SessionState save/load (runtime state) -------------------
def load_session_state(path: Union[str, Path]) -> SessionState:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"Session state file not found: {p}")
    if p.stat().st_size > MAX_SIZE_BYTES:
        raise ValueError("Session state file too large (>1MB)")
    try:
        raw = p.read_text(encoding="utf-8-sig")
        if raw.startswith("\ufeff"):
            raw = raw.lstrip("\ufeff")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e.msg} (line {e.lineno})") from None
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object")
    return build_session_state(data)

def save_session_state(state: SessionState, path: Union[str, Path]) -> None:
    p = Path(path)
    p.write_text(state.to_json(), encoding="utf-8")
