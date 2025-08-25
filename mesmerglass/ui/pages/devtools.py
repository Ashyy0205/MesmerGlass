"""DevTools page (opened via Ctrl+Shift+D) for development/CI utilities.

Provides a simple UI to spin up deterministic Virtual Toys that connect to the
local Buttplug-compatible server. Useful to test device flows without hardware.
"""
from __future__ import annotations

import threading
import asyncio
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QProgressBar, QGroupBox, QTabWidget
)

from ...devtools.virtual_toy import VirtualToy


class VirtualToyRunner:
    """Runs a VirtualToy in a background thread with its own asyncio loop.

    This avoids requiring a running asyncio loop in the Qt UI thread.
    """

    def __init__(self, name: str, port: int, *, latency_ms: int = 0, mapping: str = "linear",
                 gain: float = 1.0, gamma: float = 1.0, offset: float = 0.0, device_index: Optional[int] = None) -> None:
        self.name = name
        self.port = int(port)
        self.latency_ms = int(latency_ms)
        self.mapping = str(mapping)
        self.gain = float(gain)
        self.gamma = float(gamma)
        self.offset = float(offset)
        self.device_index = device_index
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._level = 0.0  # mirrored level for UI polling (thread-safe read)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"VirtualToy[{self.name}]", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None

    @property
    def level(self) -> float:
        return float(self._level)

    # ---------------- internals ----------------
    def _run(self) -> None:
        async def _main() -> None:
            toy = VirtualToy(
                name=self.name, port=self.port,
                latency_ms=self.latency_ms, mapping=self.mapping,  # type: ignore[arg-type]
                gain=self.gain, gamma=self.gamma, offset=self.offset,
                device_index=self.device_index,
            )
            ok = await toy.connect()
            if not ok:
                return
            listen_task = asyncio.create_task(toy.start_listening())
            try:
                # Poll the toy level periodically and mirror it for UI
                while not self._stop.is_set():
                    self._level = float(toy.state.level)
                    await asyncio.sleep(0.1)
            finally:
                listen_task.cancel()
                try:
                    await listen_task
                except Exception:
                    pass
                await toy.disconnect()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_main())
        finally:
            loop.close()


class DevToolsPage(QWidget):
    """Simple DevTools UI page (now tabbed).

    Each Virtual Toy appears on its own tab similar to the main application's
    feature tabs, showing a progress bar of the toy's current intensity.
    """

    def __init__(self, *, default_port: int = 12350):
        super().__init__()
        self.runners: Dict[str, VirtualToyRunner] = {}
        self._build_ui(default_port)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(100)  # 10 Hz refresh

    def _build_ui(self, default_port: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        ctrl = QGroupBox("Virtual Toy Controls")
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(6)
        self.edit_port = QLineEdit(str(default_port))
        self.edit_port.setFixedWidth(90)
        self.btn_add = QPushButton("Add Virtual Toy")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove_all = QPushButton("Remove All")
        self.btn_remove_all.clicked.connect(self._on_remove_all)
        cl.addWidget(QLabel("Server port:"))
        cl.addWidget(self.edit_port)
        cl.addStretch(1)
        cl.addWidget(self.btn_add)
        cl.addWidget(self.btn_remove_all)
        root.addWidget(ctrl)

        # Tabs host each toy
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        root.addStretch(1)

    def _on_add(self) -> None:
        try:
            port = int(self.edit_port.text().strip())
        except Exception:
            port = 12350
        toy_idx = 9000 + len(self.runners)
        toy_id = f"toy_{len(self.runners)}"
        runner = VirtualToyRunner(name=f"Virtual Toy {len(self.runners)}", port=port, device_index=toy_idx)
        self.runners[toy_id] = runner

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        lab = QLabel(runner.name)
        btn_rm = QPushButton("Remove Toy")
        btn_rm.clicked.connect(lambda: self._remove_one(toy_id, page))
        top.addWidget(lab)
        top.addStretch(1)
        top.addWidget(btn_rm)
        v.addLayout(top)
        bar = QProgressBar()
        bar.setRange(0, 100)
        v.addWidget(bar)
        # Attach for refresh
        page._dev_bar = bar  # type: ignore[attr-defined]
        page._dev_runner = runner  # type: ignore[attr-defined]
        self.tabs.addTab(page, runner.name)
        runner.start()

    def _remove_one(self, toy_id: str, page: QWidget) -> None:
        if toy_id in self.runners:
            try:
                self.runners[toy_id].stop()
            finally:
                del self.runners[toy_id]
        idx = self.tabs.indexOf(page)
        if idx >= 0:
            self.tabs.removeTab(idx)
        page.deleteLater()

    def _on_remove_all(self) -> None:
        for k in list(self.runners.keys()):
            try:
                self.runners[k].stop()
            finally:
                del self.runners[k]
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

    def _refresh(self) -> None:
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if not w:
                continue
            runner = getattr(w, "_dev_runner", None)
            bar = getattr(w, "_dev_bar", None)
            if runner and bar:
                bar.setValue(int(round(runner.level * 100)))

    def closeEvent(self, a0):  # type: ignore[override]
        self._on_remove_all()
        return super().closeEvent(a0)
