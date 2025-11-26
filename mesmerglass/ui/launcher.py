"""Headless-compatible Launcher shim.

Provides a very small subset of the legacy :class:`Launcher` surface area so the
CLI subcommands (``mesmerglass ui`` / ``state`` / ``cuelist`` helpers) keep
working even though the Phase 7 MainApplication replaced the original widget.
The shim intentionally focuses on deterministic, non-GL behaviors that the CLI
relies on inside automated tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class _HeadlessFont:
    def __init__(self, family: str = "Default", size: int = 24) -> None:
        self._family = family
        self._size = size

    def family(self) -> str:
        return self._family

    def pointSize(self) -> int:
        return self._size


class _Label:
    def __init__(self, text: str = "(default)") -> None:
        self._text = text

    def setText(self, value: str) -> None:
        self._text = value

    def text(self) -> str:
        return self._text


class _HeadlessTextFxPage:
    def __init__(self, launcher: "Launcher") -> None:
        self._launcher = launcher
        self.lab_font_family = _Label()

    def set_text(self, value: str) -> None:
        self._launcher.text = value

    def update_font_label(self, family: Optional[str]) -> None:
        self.lab_font_family.setText(family or "(default)")


class _HeadlessTabs:
    def __init__(self) -> None:
        self._tabs = [
            "MesmerLoom",
            "Audio",
            "Text & FX",
            "Devices",
            "VR",
            "Performance",
            "DevTools",
        ]
        self._index = 0

    def count(self) -> int:
        return len(self._tabs)

    def tabText(self, idx: int) -> str:
        return self._tabs[idx]

    def setCurrentIndex(self, idx: int) -> None:
        if 0 <= idx < len(self._tabs):
            self._index = idx

    def currentIndex(self) -> int:
        return self._index


class _HeadlessDisplayItem:
    def __init__(self, name: str, checked: bool = False) -> None:
        self.name = name
        self._state = 2 if checked else 0

    def setCheckState(self, value: int) -> None:
        self._state = value

    def checkState(self) -> int:
        return self._state


class _HeadlessDisplayList:
    def __init__(self) -> None:
        self._items = [
            _HeadlessDisplayItem("Primary", checked=True),
            _HeadlessDisplayItem("Secondary"),
        ]

    def count(self) -> int:
        return len(self._items)

    def item(self, index: int) -> _HeadlessDisplayItem:
        return self._items[index]


@dataclass
class _SessionState:
    data: Dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> Dict[str, Any]:
        return dict(self.data)


class Launcher:
    """Very small launcher stub for CLI automation."""

    is_headless_stub = True
    supports_visual_measurement = False

    def __init__(self, title: str = "MesmerGlass", enable_device_sync_default: bool = True,
                 layout_mode: str = "tabbed") -> None:
        self._title = title
        self.enable_device_sync_default = enable_device_sync_default
        self.layout_mode = layout_mode
        self.tabs = _HeadlessTabs()
        self.list_displays = _HeadlessDisplayList()
        self.page_textfx = _HeadlessTextFxPage(self)

        # Public fields touched by CLI helpers
        self.text: Optional[str] = None
        self.text_scale_pct: int = 100
        self.fx_mode: Optional[str] = None
        self.fx_intensity: int = 50
        self.current_font_path: Optional[str] = None
        self.text_font = _HeadlessFont()
        self.vol1: float = 0.5
        self.vol2: float = 0.5
        self.primary_path: Optional[str] = None
        self.buzz_intensity: float = 0.0
        self.running: bool = False
        self.visual_director = None  # not available in stub
        self.compositor = None
        self._session_state = self._build_default_state()

    # --- helpers expected by CLI -------------------------------------------------
    def show(self) -> None:  # pragma: no cover - noop for CLI
        pass

    def close(self) -> None:  # pragma: no cover - noop for CLI
        pass

    def launch(self) -> None:
        self.running = True

    def stop_all(self) -> None:
        self.running = False

    def _set_vols(self, v1: float, v2: float) -> None:
        self.vol1 = max(0.0, min(1.0, v1))
        self.vol2 = max(0.0, min(1.0, v2))

    def _select_all_displays(self) -> None:
        for i in range(self.list_displays.count()):
            self.list_displays.item(i).setCheckState(2)

    def _select_primary_display(self) -> None:
        for i in range(self.list_displays.count()):
            state = 2 if i == 0 else 0
            self.list_displays.item(i).setCheckState(state)

    # --- session capture/apply ---------------------------------------------------
    def _build_default_state(self) -> Dict[str, Any]:
        return {
            "textfx": {
                "font_path": None,
                "font_family": "(default)",
                "font_point_size": self.text_font.pointSize(),
                "scale_pct": self.text_scale_pct,
                "fx_mode": self.fx_mode,
                "fx_intensity": self.fx_intensity,
            },
            "audio": {
                "vol1": self.vol1,
                "vol2": self.vol2,
            },
        }

    def capture_session_state(self) -> _SessionState:
        data = self._build_default_state()
        data["textfx"].update({
            "font_path": self.current_font_path,
            "font_family": self.page_textfx.lab_font_family.text(),
            "scale_pct": self.text_scale_pct,
            "fx_mode": self.fx_mode,
            "fx_intensity": self.fx_intensity,
        })
        data["audio"].update({"vol1": self.vol1, "vol2": self.vol2})
        data["launcher"] = {
            "running": self.running,
            "tab": self.tabs.tabText(self.tabs.currentIndex()),
        }
        return _SessionState(data)

    def apply_session_state(self, state: Any) -> None:
        data: Dict[str, Any]
        if isinstance(state, _SessionState):
            data = state.to_json_dict()
        elif hasattr(state, "to_json_dict"):
            data = state.to_json_dict()  # type: ignore[assignment]
        elif isinstance(state, dict):
            data = state
        else:
            return

        textfx = data.get("textfx", {})
        self.current_font_path = textfx.get("font_path", self.current_font_path)
        self.text_scale_pct = int(textfx.get("scale_pct", self.text_scale_pct))
        self.fx_mode = textfx.get("fx_mode", self.fx_mode)
        self.fx_intensity = int(textfx.get("fx_intensity", self.fx_intensity))
        font_family = textfx.get("font_family")
        if font_family:
            self.page_textfx.update_font_label(font_family)
        audio = data.get("audio", {})
        self.vol1 = float(audio.get("vol1", self.vol1))
        self.vol2 = float(audio.get("vol2", self.vol2))
        launcher_meta = data.get("launcher", {})
        tab_name = launcher_meta.get("tab")
        if tab_name:
            for idx in range(self.tabs.count()):
                if self.tabs.tabText(idx) == tab_name:
                    self.tabs.setCurrentIndex(idx)
                    break

    # --- legacy hooks used by CLI session apply --------------------------------
    def apply_session_pack(self, pack: Any) -> None:
        """Best-effort headless application of a session pack for CLI tests."""
        text_value = getattr(pack, "first_text", None)
        if not text_value:
            text_section = getattr(pack, "text", None)
            items = getattr(text_section, "items", None)
            if items:
                first = items[0]
                text_value = getattr(first, "msg", None)
        if text_value:
            self.text = text_value
        pulse = getattr(pack, "pulse", None)
        stages = getattr(pulse, "stages", None)
        if stages:
            try:
                first_stage = stages[0]
                intensity = getattr(first_stage, "intensity", None)
                if intensity is not None:
                    self.buzz_intensity = float(intensity)
            except Exception:
                pass

    # --- Qt compatibility --------------------------------------------------------
    def page(self, name: str) -> Any:  # pragma: no cover - compatibility hook
        if name.lower() == "textfx":
            return self.page_textfx
        raise AttributeError(name)


__all__ = ["Launcher"]
