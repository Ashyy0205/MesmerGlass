"""Session / Message Pack data models (v1).

Defines small dataclasses plus validation for a versioned session pack:
 - text.items: ordered messages with durations
 - pulse.stages: ordered intensity stages
 - pulse.fallback: reserved token (future use)

No scheduling logic here; the launcher only applies initial state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Any, Dict, Optional


@dataclass(slots=True)
class TextItem:
    """Single message entry.

    Legacy format (v1 initial) required ``secs`` (positive int) and used it as
    both display duration and relative weight for random cycling.

    New format allows an explicit ``weight`` (float>0) plus optional ``mode``.
    ``secs`` becomes optional and is ignored by the new weight-based cycling
    logic if ``weight`` is provided. We keep it for backward compatibility so
    previously saved packs continue to validate & load.
    """
    msg: str
    secs: int | None = None   # legacy optional
    weight: float | None = None  # new optional explicit weight (>0)
    mode: str | None = None  # future per-message visual mode (free-form)

    def effective_weight(self) -> float:
        """Return a positive weight used for random selection.

        Priority: explicit weight > legacy secs > default 1.0
        """
        if self.weight is not None:
            try:
                w = float(self.weight)
                return w if w > 0 else 1.0
            except Exception:  # pragma: no cover - defensive
                return 1.0
        if isinstance(self.secs, int) and self.secs > 0:
            return float(self.secs)
        return 1.0

    def validate(self, idx: int) -> None:
        if not isinstance(self.msg, str) or not self.msg.strip():
            raise ValueError(f"text.items[{idx}].msg must be non-empty string")
        # Either weight or secs (or both) must be present & valid
        has_weight = self.weight is not None
        has_secs = self.secs is not None
        if not has_weight and not has_secs:
            raise ValueError(f"text.items[{idx}] must have weight or secs")
        if has_weight:
            try:
                w = float(self.weight)  # type: ignore[arg-type]
            except Exception:
                raise ValueError(f"text.items[{idx}].weight must be float >0") from None
            if not (w > 0):
                raise ValueError(f"text.items[{idx}].weight must be >0 (got {self.weight})")
        if has_secs:
            if not isinstance(self.secs, int) or self.secs <= 0:
                raise ValueError(f"text.items[{idx}].secs must be positive int if provided")
        if self.mode is not None and (not isinstance(self.mode, str) or not self.mode.strip()):
            raise ValueError(f"text.items[{idx}].mode must be non-empty string if provided")


@dataclass(slots=True)
class TextSection:
    items: List[TextItem] = field(default_factory=list)
    def validate(self) -> None:
        for i, it in enumerate(self.items):
            it.validate(i)


@dataclass(slots=True)
class PulseStage:
    mode: str
    intensity: float
    secs: int
    def validate(self, idx: int) -> None:
        if not isinstance(self.mode, str) or not self.mode.strip():
            raise ValueError(f"pulse.stages[{idx}].mode must be non-empty string")
        try:
            iv = float(self.intensity)
        except Exception:
            raise ValueError(f"pulse.stages[{idx}].intensity must be float 0..1") from None
        if not (0.0 <= iv <= 1.0):
            raise ValueError(f"pulse.stages[{idx}].intensity must be 0..1 (got {self.intensity})")
        if not isinstance(self.secs, int) or self.secs <= 0:
            raise ValueError(f"pulse.stages[{idx}].secs must be positive int")


@dataclass(slots=True)
class PulseSection:
    stages: List[PulseStage] = field(default_factory=list)
    fallback: Optional[str] = None
    def validate(self) -> None:
        for i, st in enumerate(self.stages):
            st.validate(i)
        if self.fallback is not None and (not isinstance(self.fallback, str) or not self.fallback.strip()):
            raise ValueError("pulse.fallback must be non-empty string if provided")


@dataclass(slots=True)
class SessionPack:
    version: int
    name: str
    text: TextSection = field(default_factory=TextSection)
    pulse: PulseSection = field(default_factory=PulseSection)
    raw: Dict[str, Any] = field(default_factory=dict)
    def validate(self) -> None:
        if self.version != 1:
            raise ValueError(f"Unsupported session pack version {self.version}; expected 1")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty string")
        self.text.validate()
        self.pulse.validate()
    @property
    def first_text(self) -> Optional[str]:
        return self.text.items[0].msg if self.text.items else None
    @property
    def avg_intensity(self) -> Optional[float]:
        if not self.pulse.stages:
            return None
        return sum(s.intensity for s in self.pulse.stages) / len(self.pulse.stages)
    def to_canonical_dict(self) -> Dict[str, Any]:
        """Return canonical JSON-ready dict.

        For text items we now prefer (msg, weight, mode) and only include
        ``secs`` if it existed and weight was absent (legacy preservation).
        """
        text_items = []
        for ti in self.text.items:
            entry: Dict[str, Any] = {"msg": ti.msg}
            if ti.weight is not None:
                entry["weight"] = ti.weight
            if ti.mode is not None:
                entry["mode"] = ti.mode
            # include legacy secs only if no weight supplied (avoid confusion)
            if ti.weight is None and ti.secs is not None:
                entry["secs"] = ti.secs
            text_items.append(entry)
        return {
            "version": self.version,
            "name": self.name,
            "text": {"items": text_items},
            "pulse": {
                "stages": [
                    {"mode": st.mode, "intensity": st.intensity, "secs": st.secs}
                    for st in self.pulse.stages
                ],
                **({"fallback": self.pulse.fallback} if self.pulse.fallback else {}),
            },
        }


def build_session_pack(data: Dict[str, Any]) -> SessionPack:
    version = data.get("version")
    name = data.get("name", "")
    text_raw = data.get("text", {}) or {}
    pulse_raw = data.get("pulse", {}) or {}
    text_items = []
    for i, it in enumerate(text_raw.get("items", []) or []):
        if not isinstance(it, dict):
            raise ValueError(f"text.items[{i}] must be object")
        text_items.append(TextItem(
            msg=it.get("msg", ""),
            secs=it.get("secs"),  # may be None
            weight=it.get("weight"),
            mode=it.get("mode"),
        ))
    pulse_stages = []
    for i, st in enumerate(pulse_raw.get("stages", []) or []):
        if not isinstance(st, dict):
            raise ValueError(f"pulse.stages[{i}] must be object")
        pulse_stages.append(PulseStage(mode=st.get("mode", ""), intensity=st.get("intensity", 0.0), secs=st.get("secs", 0)))
    pack = SessionPack(
        version=version,
        name=name,
        text=TextSection(items=text_items),
        pulse=PulseSection(stages=pulse_stages, fallback=pulse_raw.get("fallback")),
        raw=data,
    )
    pack.validate()
    return pack
