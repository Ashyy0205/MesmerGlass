"""Launcher window (restored baseline).

This file was fully replaced with a previously saved, known-good version
(`launch_pre.py`) after structural corruption in earlier patches. Future
enhancements (menu bar, pack path tracking) will be re-applied as small
incremental diffs on top of this stable baseline.
"""

import os, time, random, threading, time as _time_mod, asyncio  # asyncio added for persistent BLE loop
from typing import List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFileDialog, QTabWidget, QGroupBox, QScrollArea, QFrame,
    QListWidget, QListWidgetItem
)

from ..engine.audio import Audio2
from ..engine.pulse import PulseEngine, clamp
try:
    # MesmerIntiface optional if bleak is not installed in current environment.
    from ..engine.mesmerintiface import MesmerIntifaceServer  # type: ignore
except Exception:  # pragma: no cover - fallback when bleak missing or import error
    MesmerIntifaceServer = None  # type: ignore
from .overlay import OverlayWindow
from .pages.textfx import TextFxPage
from .pages.device import DevicePage
from .pages.audio import AudioPage
from .pages.devtools import DevToolsPage
import logging


class ScanCompleteSignaler(QObject):
    """Thread-safe signaler for scan completion."""
    scan_completed = pyqtSignal(object)  # Emits device_list


# ---- tiny helpers used by pages built in this file ----

def _card(title: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setContentsMargins(0, 0, 0, 0)
    return box


def _row(label: str, widget: QWidget, trailing: QWidget | None = None) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(10, 6, 10, 6)
    h.setSpacing(10)
    lab = QLabel(label)
    lab.setMinimumWidth(160)
    h.addWidget(lab, 0)
    h.addWidget(widget, 1)
    if trailing:
        h.addWidget(trailing, 0)
    return w


from .. import __app_name__


class Launcher(QMainWindow):
    def __init__(self, title: str, enable_device_sync_default: bool = True, layout_mode: str = "tabbed"):
        """Main application launcher / controller window.

        Rebuilt cleanly after earlier indentation damage; all state lives inside
        this method. Initial display text left blank so message packs fully drive
        content (was previously hard-coded 'MESMERGLASS').
        """
        super().__init__()
        self.setWindowTitle(title)
        self.layout_mode = layout_mode if layout_mode in ("tabbed", "sidebar") else "tabbed"

        # Core state -------------------------------------------------
        self.primary_path = ""; self.secondary_path = ""
        self.primary_op = 1.0; self.secondary_op = 0.5
        self.text = ""  # blank initial message
        self.text_color = QColor("white"); self.text_font = QFont("Segoe UI", 28)
        self.text_scale_pct = 100; self.fx_mode = "Breath + Sway"; self.fx_intensity = 50
        self.flash_interval_ms = 1200; self.flash_width_ms = 250
        self.audio1_path = ""; self.audio2_path = ""; self.vol1 = 0.5; self.vol2 = 0.5
        self.enable_device_sync = bool(enable_device_sync_default)
        self.enable_buzz_on_flash = True; self.buzz_intensity = 0.6
        self.enable_bursts = False; self.burst_min_s = 30; self.burst_max_s = 120; self.burst_peak = 0.9; self.burst_max_ms = 1200
        self.overlays: list = []
        self.running = False

        # Engines ----------------------------------------------------
        self.audio = Audio2()
        self.pulse = PulseEngine(use_mesmer=True, allow_auto_select=False)
        self.mesmer_server = None
        self._mesmer_device_cb = None
        self.device_scan_in_progress = False
        self.scan_signaler = ScanCompleteSignaler()
        self.scan_signaler.scan_completed.connect(self._scan_completed)
        # Global shutdown flag (guards async callbacks during close)
        self._shutting_down = False

        # --- Persistent BLE event loop (fixes 'Event loop is closed' RuntimeError) ---
        # Bleak (WinRT backend) captures the current asyncio loop when a device connects
        # and later uses loop.call_soon_threadsafe from native notification threads.
        # Previous implementation created short-lived event loops (new_event_loop + close)
        # for scan/connect operations; once closed, Bleak callbacks attempted to schedule
        # work on a dead loop, raising RuntimeError: Event loop is closed.
        # We allocate ONE long‑lived loop in a daemon thread for all BLE tasks and shut it
        # down only during Launcher.closeEvent after devices & server are cleanly stopped.
        self._ble_loop: asyncio.AbstractEventLoop | None = asyncio.new_event_loop()
        self._ble_loop_alive = True
        def _ble_loop_runner():  # runs forever until stop requested
            asyncio.set_event_loop(self._ble_loop)
            try:
                self._ble_loop.run_forever()
            except Exception as e:  # pragma: no cover - defensive
                logging.getLogger(__name__).error("BLE loop crash: %s", e)
            finally:
                # Close loop so pending handles are released
                try:
                    self._ble_loop.close()
                except Exception:
                    pass
        self._ble_loop_thread = threading.Thread(target=_ble_loop_runner, name="BLELoop", daemon=True)
        self._ble_loop_thread.start()

        # Environment flag to suppress starting MesmerIntiface server in headless/CI
        self._suppress_server = bool(os.environ.get("MESMERGLASS_NO_SERVER"))

        # UI / services ----------------------------------------------
        self._build_ui()
        self._install_menu_bar()  # add menus (idempotent)
        self._bind_shortcuts()
        if not self._suppress_server:
            self._start_mesmer_server()

        # Message pack placeholder (proper indentation inside __init__)
        self.session_pack = None
        self.current_pack_path = None  # path of last loaded session pack (not auto-loaded on state apply)

    # ========================== UI build ==========================
    def _build_ui(self):
        # Clean reimplementation to fix prior indentation issues
        root = QWidget(); self.setCentralWidget(root)
        main = QVBoxLayout(root); main.setContentsMargins(10, 10, 10, 10); main.setSpacing(10)

        self.tabs = QTabWidget()

        # Media
        scroll_media = QScrollArea(); scroll_media.setWidgetResizable(True); scroll_media.setFrameShape(QFrame.Shape.NoFrame)
        scroll_media.setWidget(self._page_media()); self.tabs.addTab(scroll_media, "Media")

        # Text & FX
        self.page_textfx = TextFxPage(
            text=self.text,
            text_scale_pct=self.text_scale_pct,
            fx_mode=self.fx_mode,
            fx_intensity=self.fx_intensity,
            flash_interval_ms=self.flash_interval_ms,
            flash_width_ms=self.flash_width_ms,
        )
        try: self.page_textfx.loadPackRequested.connect(self._on_load_session_pack)
        except Exception: pass
        try:
            self.page_textfx.createPackRequested.connect(self._on_create_message_pack)
            # removed cycle interval feature
        except Exception: pass
        scroll_textfx = QScrollArea(); scroll_textfx.setWidgetResizable(True); scroll_textfx.setFrameShape(QFrame.Shape.NoFrame)
        scroll_textfx.setWidget(self.page_textfx); self.tabs.addTab(scroll_textfx, "Text & FX")

        # Audio
        self.page_audio = AudioPage(
            file1=os.path.basename(self.audio1_path),
            file2=os.path.basename(self.audio2_path),
            vol1_pct=int(self.vol1 * 100),
            vol2_pct=int(self.vol2 * 100),
        )
        scroll_audio = QScrollArea(); scroll_audio.setWidgetResizable(True); scroll_audio.setFrameShape(QFrame.Shape.NoFrame)
        scroll_audio.setWidget(self.page_audio); self.tabs.addTab(scroll_audio, "Audio")

        # Device
        self.page_device = DevicePage(
            enable_sync=self.enable_device_sync,
            buzz_on_flash=self.enable_buzz_on_flash,
            buzz_intensity_pct=int(self.buzz_intensity * 100),
            bursts_enable=self.enable_bursts,
            min_gap_s=self.burst_min_s,
            max_gap_s=self.burst_max_s,
            peak_pct=int(self.burst_peak * 100),
            max_ms=self.burst_max_ms,
        )
        scroll_device = QScrollArea(); scroll_device.setWidgetResizable(True); scroll_device.setFrameShape(QFrame.Shape.NoFrame)
        scroll_device.setWidget(self.page_device); self.tabs.addTab(scroll_device, "Device Sync")

        # Displays
        scroll_displays = QScrollArea(); scroll_displays.setWidgetResizable(True); scroll_displays.setFrameShape(QFrame.Shape.NoFrame)
        scroll_displays.setWidget(self._page_displays()); self.tabs.addTab(scroll_displays, "Displays")

        if self.layout_mode == "sidebar":
            topbar = QWidget(); topbar.setObjectName("topBar")
            tbl = QHBoxLayout(topbar); tbl.setContentsMargins(12,8,12,8); tbl.setSpacing(8)
            title_lab = QLabel("MesmerGlass"); title_lab.setObjectName("topTitle")
            tbl.addWidget(title_lab,0); tbl.addStretch(1)
            self.chip_overlay = QLabel("Overlay: Idle"); self.chip_overlay.setObjectName("statusChip")
            self.chip_device = QLabel("Device: Off"); self.chip_device.setObjectName("statusChip")
            tbl.addWidget(self.chip_overlay,0); tbl.addWidget(self.chip_device,0)
            main.addWidget(topbar,0)
            center = QWidget(); ch = QHBoxLayout(center); ch.setContentsMargins(0,0,0,0); ch.setSpacing(10)
            self.nav = QListWidget(); self.nav.setObjectName("sideNav")
            for name in ("Media","Text & FX","Audio","Device Sync","Displays"): self.nav.addItem(name)
            self.nav.setCurrentRow(0)
            try: self.tabs.tabBar().setVisible(False)
            except Exception: pass
            ch.addWidget(self.nav,0); ch.addWidget(self.tabs,1); main.addWidget(center,1)
            def _on_nav(i:int):
                if 0 <= i < self.tabs.count(): self.tabs.setCurrentIndex(i)
            self.nav.currentRowChanged.connect(_on_nav)
            self.tabs.currentChanged.connect(lambda i: self.nav.setCurrentRow(i))
        else:
            try: self.tabs.tabBar().setVisible(True)
            except Exception: pass
            main.addWidget(self.tabs,1)

        # Wire signals
        self.page_textfx.textChanged.connect(lambda s: setattr(self, 'text', s))
        self.page_textfx.textScaleChanged.connect(lambda v: setattr(self, 'text_scale_pct', v))
        self.page_textfx.fxModeChanged.connect(lambda s: setattr(self, 'fx_mode', s))
        self.page_textfx.fxIntensityChanged.connect(lambda v: setattr(self, 'fx_intensity', v))
        self.page_textfx.flashIntervalChanged.connect(lambda v: setattr(self, 'flash_interval_ms', v))
        self.page_textfx.flashWidthChanged.connect(lambda v: setattr(self, 'flash_width_ms', v))
        # Apply chosen text colour live
        if hasattr(self.page_textfx, 'colorChanged'):
            self.page_textfx.colorChanged.connect(self._on_text_color_changed)

        self.page_audio.load1Requested.connect(self._pick_a1)
        self.page_audio.load2Requested.connect(self._pick_a2)
        self.page_audio.vol1Changed.connect(lambda pct: self._set_vols(pct/100.0, self.vol2))
        self.page_audio.vol2Changed.connect(lambda pct: self._set_vols(self.vol1, pct/100.0))

        self.page_device.enableSyncChanged.connect(self._on_toggle_device_sync)
        self.page_device.scanDevicesRequested.connect(self._on_scan_devices)
        self.page_device.deviceSelected.connect(self._on_device_selected)
        self.page_device.devicesSelected.connect(self._on_devices_selected)
        self.page_device.buzzOnFlashChanged.connect(lambda b: setattr(self,'enable_buzz_on_flash', b))
        self.page_device.buzzIntensityChanged.connect(lambda v: setattr(self,'buzz_intensity', v/100.0))
        self.page_device.burstsEnableChanged.connect(lambda b: setattr(self,'enable_bursts', b))
        self.page_device.burstMinChanged.connect(lambda v: setattr(self,'burst_min_s', v))
        self.page_device.burstMaxChanged.connect(lambda v: setattr(self,'burst_max_s', v))
        self.page_device.burstPeakChanged.connect(lambda v: setattr(self,'burst_peak', v/100.0))
        self.page_device.burstMaxMsChanged.connect(lambda v: setattr(self,'burst_max_ms', v))

        footer = QWidget(); footer.setObjectName('footerBar')
        fl = QHBoxLayout(footer); fl.setContentsMargins(10,6,10,6)
        self.btn_launch = QPushButton('Launch'); self.btn_stop = QPushButton('Stop')
        fl.addWidget(self.btn_launch); fl.addWidget(self.btn_stop); fl.addStretch(1)
        if self.layout_mode != 'sidebar':
            self.chip_overlay = QLabel('Overlay: Idle'); self.chip_overlay.setObjectName('statusChip')
            self.chip_device = QLabel('Device: Off'); self.chip_device.setObjectName('statusChip')
            fl.addWidget(self.chip_overlay); fl.addWidget(self.chip_device)
        self.chip_audio = QLabel('Audio: 0/2'); self.chip_audio.setObjectName('statusChip')
        fl.addWidget(self.chip_audio); main.addWidget(footer,0)
        # Footer buttons (correct indentation within _build_ui)
        self.btn_launch.clicked.connect(self.launch)
        self.btn_stop.clicked.connect(self.stop_all)
        self._refresh_status()

    def _page_media(self):
        def _pct_label(v: float) -> QLabel:
            lab = QLabel(f"{int(v*100)}%")
            lab.setMinimumWidth(48)
            lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return lab

        page = QWidget()
        root = QVBoxLayout(page); root.setContentsMargins(6, 6, 6, 6); root.setSpacing(12)

        # Primary bubble
        card_primary = _card("Primary video"); pv = QVBoxLayout(card_primary); pv.setContentsMargins(12, 8, 12, 8); pv.setSpacing(4)
        self.lbl_primary = QLabel("(none)")
        btn_pick_primary = QPushButton("Choose file…"); btn_pick_primary.clicked.connect(self._pick_primary)
        pv.addWidget(_row("File", btn_pick_primary, self.lbl_primary))

        self.sld_primary_op = QSlider(Qt.Orientation.Horizontal); self.sld_primary_op.setRange(0, 100); self.sld_primary_op.setValue(int(self.primary_op * 100))
        self.lab_primary_pct = _pct_label(self.primary_op)
        self.sld_primary_op.valueChanged.connect(lambda x: (setattr(self, "primary_op", x / 100.0), self.lab_primary_pct.setText(f"{x}%")))
        pv.addWidget(_row("Opacity", self.sld_primary_op, self.lab_primary_pct))

        root.addWidget(card_primary)

        # Secondary bubble
        card_secondary = _card("Secondary video"); sv = QVBoxLayout(card_secondary); sv.setContentsMargins(12, 8, 12, 8); sv.setSpacing(4)
        self.lbl_secondary = QLabel("(none)")
        btn_pick_secondary = QPushButton("Choose file…"); btn_pick_secondary.clicked.connect(self._pick_secondary)
        sv.addWidget(_row("File", btn_pick_secondary, self.lbl_secondary))

        self.sld_secondary_op = QSlider(Qt.Orientation.Horizontal); self.sld_secondary_op.setRange(0, 100); self.sld_secondary_op.setValue(int(self.secondary_op * 100))
        self.lab_secondary_pct = _pct_label(self.secondary_op)
        self.sld_secondary_op.valueChanged.connect(lambda x: (setattr(self, "secondary_op", x / 100.0), self.lab_secondary_pct.setText(f"{x}%")))
        sv.addWidget(_row("Opacity", self.sld_secondary_op, self.lab_secondary_pct))

        root.addWidget(card_secondary)
        root.addStretch(1)
        return page

    def _page_displays(self):
        card = _card("Displays"); v = QVBoxLayout(card); v.setContentsMargins(12, 10, 12, 12); v.setSpacing(8)
        self.list_displays = QListWidget()
        for s in QGuiApplication.screens():
            it = QListWidgetItem(f"{s.name()}  {s.geometry().width()}x{s.geometry().height()}"); it.setCheckState(Qt.CheckState.Unchecked)
            self.list_displays.addItem(it)
        v.addWidget(self.list_displays, 1)

        btn_sel_all = QPushButton("Select all"); btn_sel_pri = QPushButton("Primary only")
        v.addWidget(_row("Quick select", btn_sel_all, btn_sel_pri))
        btn_sel_all.clicked.connect(self._select_all_displays)
        btn_sel_pri.clicked.connect(self._select_primary_display)

        page = QWidget(); root = QVBoxLayout(page); root.addWidget(card); root.addStretch(1)
        return page

    # ========================== helpers / pickers ==========================
    def _bind_shortcuts(self):
        sc_launch = QShortcut(QKeySequence("Ctrl+L"), self); sc_launch.activated.connect(self.launch)
        sc_stop = QShortcut(QKeySequence("Ctrl+."), self); sc_stop.activated.connect(self.stop_all)
        for i in range(1, 6):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda idx=i - 1: self.tabs.setCurrentIndex(idx))
        sc_dev = QShortcut(QKeySequence("Ctrl+Shift+D"), self); sc_dev.activated.connect(self._open_devtools)

    def _open_devtools(self):
        try:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == "DevTools":
                    self.tabs.setCurrentIndex(i)
                    return
            default_port = 12350
            if getattr(self, "mesmer_server", None):
                try:
                    default_port = int(self.mesmer_server.selected_port)
                except Exception:
                    pass
            page = DevToolsPage(default_port=default_port)
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, "DevTools")
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
            # In sidebar mode, append to nav
            if getattr(self, "layout_mode", "tabbed") == "sidebar" and hasattr(self, "nav"):
                try:
                    self.nav.addItem("DevTools")
                    self.nav.setCurrentRow(self.tabs.count() - 1)
                except Exception:
                    pass
        except Exception as e:
            logging.getLogger(__name__).error("Failed to open DevTools page: %s", e)

    def _select_all_displays(self):
        for i in range(self.list_displays.count()):
            it = self.list_displays.item(i)
            if it is not None:
                it.setCheckState(Qt.CheckState.Checked)

    def _select_primary_display(self):
        for i in range(self.list_displays.count()):
            it = self.list_displays.item(i)
            if it is not None:
                it.setCheckState(Qt.CheckState.Unchecked)
        if self.list_displays.count() > 0:
            it0 = self.list_displays.item(0)
            if it0 is not None:
                it0.setCheckState(Qt.CheckState.Checked)

    def _pick_primary(self):
        f, _ = QFileDialog.getOpenFileName(self, "Pick primary video", "", "Videos (*.mp4 *.mov *.mkv *.avi);;All (*.*)")
        if f:
            self.primary_path = f
            self.lbl_primary.setText(os.path.basename(f))

    def _pick_secondary(self):
        f, _ = QFileDialog.getOpenFileName(self, "Pick secondary video", "", "Videos (*.mp4 *.mov *.mkv *.avi);;All (*.*)")
        if f:
            self.secondary_path = f
            self.lbl_secondary.setText(os.path.basename(f))

    def _pick_font(self):
        from PyQt6.QtWidgets import QFontDialog
        # Use a dedicated text_font attribute to avoid QWidget.font() collisions
        font, ok = QFontDialog.getFont(self.text_font, self, "Pick font")
        if ok:
            self.text_font = font

    def _pick_color(self):
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self.text_color, self, "Pick text color")
        if c.isValid():
            self.text_color = c

    def _pick_a1(self):
        f, _ = QFileDialog.getOpenFileName(self, "Load Audio 1", "", "Audio (*.mp3 *.ogg *.wav);;All (*.*)")
        if f:
            self.audio1_path = f
            self.page_audio.set_file1_label(os.path.basename(f))
            self.audio.load1(f); self._set_vols(self.vol1, self.vol2); self._refresh_status()

    def _pick_a2(self):
        f, _ = QFileDialog.getOpenFileName(self, "Load Audio 2", "", "Audio (*.mp3 *.ogg *.wav);;All (*.*)")
        if f:
            self.audio2_path = f
            self.page_audio.set_file2_label(os.path.basename(f))
            self.audio.load2(f); self._set_vols(self.vol1, self.vol2); self._refresh_status()

    def _set_vols(self, v1, v2):
        self.vol1, self.vol2 = v1, v2
        self.audio.set_vols(v1, v2)

    # ---------------- Session State Capture / Apply ----------------
    def capture_session_state(self):
        """Build and return a SessionState snapshot (or None on failure).

        Deferred import keeps launcher usable if content models evolve.
        """
        try:
            from ..content.models import SessionState  # local import
        except Exception:
            return None
        # Dynamic app version (if available); fall back to None silently.
        try:
            from .. import __version__ as _app_ver
        except Exception:
            _app_ver = None
        # Video
        video = {
            "primary": {"path": getattr(self, "primary_path", None) or None, "opacity": float(getattr(self, "primary_op", 1.0))},
            "secondary": {"path": getattr(self, "secondary_path", None) or None, "opacity": float(getattr(self, "secondary_op", 0.5))},
        }
        # Audio
        audio = {
            "a1": {"path": getattr(self, "audio1_path", None) or None, "volume": float(getattr(self, "vol1", 0.0))},
            "a2": {"path": getattr(self, "audio2_path", None) or None, "volume": float(getattr(self, "vol2", 0.0))},
        }
        # Text / FX
        col = getattr(self, "text_color", None)
        if col is not None:
            try:
                color_hex = f"#{col.red():02X}{col.green():02X}{col.blue():02X}"
            except Exception:
                color_hex = "#FFFFFF"
        else:
            color_hex = "#FFFFFF"
        font = getattr(self, "text_font", None)
        font_family = None; font_size = None
        if font is not None:
            try:
                font_family = font.family(); font_size = font.pointSize()
            except Exception:
                pass
        textfx = {
            "pack_path": getattr(self, "current_pack_path", None),
            "text_color": color_hex,
            "font_family": font_family,
            "font_point_size": font_size,
            "scale_pct": int(getattr(self, "text_scale_pct", 100)),
            "fx_mode": getattr(self, "fx_mode", None),
            "fx_intensity": int(getattr(self, "fx_intensity", 0)),
            "flash_interval_ms": int(getattr(self, "flash_interval_ms", 0)),
            "flash_width_ms": int(getattr(self, "flash_width_ms", 0)),
        }
        # Device sync
        device_sync = {
            "buzz_on_flash": bool(getattr(self, "enable_buzz_on_flash", False)),
            "buzz_intensity": float(getattr(self, "buzz_intensity", 0.0)),
            "enable_bursts": bool(getattr(self, "enable_bursts", False)),
            "burst_min_s": int(getattr(self, "burst_min_s", 0)),
            "burst_max_s": int(getattr(self, "burst_max_s", 0)),
            "burst_peak": float(getattr(self, "burst_peak", 0.0)),
            "burst_max_ms": int(getattr(self, "burst_max_ms", 0)),
        }
        try:
            return SessionState(video=video, audio=audio, textfx=textfx, device_sync=device_sync, app_version=_app_ver)
        except Exception:
            return None

    def apply_session_state(self, state):
        """Apply a previously captured SessionState (or raw dict).

        Ignores unknown/missing keys; clamps via existing setters where possible.
        """
        if state is None:
            return
        if isinstance(state, dict):
            data = state
        else:
            try:
                data = state.to_json_dict()  # type: ignore[attr-defined]
            except Exception:
                return
        # Video
        try:
            video = data.get("video", {}) or {}
            prim = video.get("primary", {})
            old_primary = getattr(self, 'primary_path', '')
            self.primary_path = prim.get("path") or ""; self.primary_op = float(prim.get("opacity", self.primary_op))
            sec = video.get("secondary", {})
            old_secondary = getattr(self, 'secondary_path', '')
            self.secondary_path = sec.get("path") or ""; self.secondary_op = float(sec.get("opacity", self.secondary_op))
            # Update labels if paths changed
            import os as _os
            if hasattr(self, 'lbl_primary') and self.primary_path and self.primary_path != old_primary:
                try: self.lbl_primary.setText(_os.path.basename(self.primary_path))
                except Exception: pass
            if hasattr(self, 'lbl_secondary') and self.secondary_path and self.secondary_path != old_secondary:
                try: self.lbl_secondary.setText(_os.path.basename(self.secondary_path))
                except Exception: pass
        except Exception:
            pass
        # Audio
        try:
            audio = data.get("audio", {}) or {}
            a1 = audio.get("a1", {}); new_a1 = a1.get("path") or self.audio1_path; self.vol1 = float(a1.get("volume", self.vol1))
            a2 = audio.get("a2", {}); new_a2 = a2.get("path") or self.audio2_path; self.vol2 = float(a2.get("volume", self.vol2))
            # If file paths changed, (re)load them via audio engine
            if new_a1 != getattr(self, 'audio1_path', None) and new_a1:
                try:
                    self.audio1_path = new_a1; self.audio.load1(new_a1)
                    if getattr(self, 'page_audio', None):
                        try: self.page_audio.set_file1_label(os.path.basename(new_a1))
                        except Exception: pass
                except Exception: pass
            if new_a2 != getattr(self, 'audio2_path', None) and new_a2:
                try:
                    self.audio2_path = new_a2; self.audio.load2(new_a2)
                    if getattr(self, 'page_audio', None):
                        try: self.page_audio.set_file2_label(os.path.basename(new_a2))
                        except Exception: pass
                except Exception: pass
            # Always update volumes after (re)loads
            self._set_vols(self.vol1, self.vol2)
        except Exception:
            pass
        # Text / FX
        textfx = data.get("textfx", {}) or {}
        try:
            from PyQt6.QtGui import QColor
            color_hex = textfx.get("text_color") or None
            if color_hex:
                self.text_color = QColor(color_hex)
        except Exception:
            pass
        try:
            self.text_scale_pct = int(textfx.get("scale_pct", self.text_scale_pct))
            self.fx_mode = textfx.get("fx_mode", self.fx_mode)
            self.fx_intensity = int(textfx.get("fx_intensity", self.fx_intensity))
            self.flash_interval_ms = int(textfx.get("flash_interval_ms", self.flash_interval_ms))
            self.flash_width_ms = int(textfx.get("flash_width_ms", self.flash_width_ms))
            # Font (optional restoration)
            fam = textfx.get("font_family")
            sz = textfx.get("font_point_size")
            if fam and sz:
                try:
                    self.text_font = QFont(fam, int(sz))
                except Exception:
                    pass
            # Message pack path (if provided) — now we attempt to load automatically for user convenience.
            pack_path = textfx.get("pack_path")
            if pack_path and os.path.isfile(pack_path):
                try:
                    from ..content.loader import load_session_pack
                    pack = load_session_pack(pack_path)
                    # IMPORTANT: remember path BEFORE apply so fallback inside apply_session_pack
                    # (which checks raw['_source_path'] or existing current_pack_path) retains it.
                    # Loader does not currently inject '_source_path', so without this the path
                    # would be lost and tests expecting persistence would fail.
                    self.current_pack_path = pack_path  # preserve for state restore
                    self.apply_session_pack(pack)
                except Exception as e:
                    logging.getLogger(__name__).warning("Auto-load of pack failed: %s", e)
                    self.current_pack_path = pack_path  # remember even if load failed
            else:
                # Just store path even if missing (user can resolve later)
                if pack_path:
                    self.current_pack_path = pack_path
        except Exception:
            pass
        # Device sync (apply AFTER possible pack auto-load so state values win)
        try:
            device_sync = data.get("device_sync", {}) or {}
            self.enable_buzz_on_flash = bool(device_sync.get("buzz_on_flash", self.enable_buzz_on_flash))
            self.buzz_intensity = float(device_sync.get("buzz_intensity", self.buzz_intensity))
            self.enable_bursts = bool(device_sync.get("enable_bursts", self.enable_bursts))
            self.burst_min_s = int(device_sync.get("burst_min_s", self.burst_min_s))
            self.burst_max_s = int(device_sync.get("burst_max_s", self.burst_max_s))
            self.burst_peak = float(device_sync.get("burst_peak", self.burst_peak))
            self.burst_max_ms = int(device_sync.get("burst_max_ms", self.burst_max_ms))
        except Exception:
            pass
        # Propagate changes to UI widgets where safe (best-effort; guard for headless tests)
        try:
            import os as _os
            # --- Text/FX Page ---
            if getattr(self, 'page_textfx', None):
                pt = self.page_textfx
                # Update text scale slider
                if hasattr(pt, 'sld_txt_scale'):
                    try:
                        pt.sld_txt_scale.blockSignals(True)
                        pt.sld_txt_scale.setValue(int(self.text_scale_pct))
                    finally:
                        try: pt.sld_txt_scale.blockSignals(False)
                        except Exception: pass
                # FX mode combobox
                if hasattr(pt, 'cmb_fx') and self.fx_mode:
                    try: pt.cmb_fx.setCurrentText(self.fx_mode)
                    except Exception: pass
                # FX intensity slider
                if hasattr(pt, 'sld_fx_int'):
                    try:
                        pt.sld_fx_int.blockSignals(True)
                        pt.sld_fx_int.setValue(int(self.fx_intensity))
                    finally:
                        try: pt.sld_fx_int.blockSignals(False)
                        except Exception: pass
                # Flash interval/width
                if hasattr(pt, 'spin_interval'):
                    try: pt.spin_interval.setValue(int(self.flash_interval_ms))
                    except Exception: pass
                if hasattr(pt, 'spin_width'):
                    try: pt.spin_width.setValue(int(self.flash_width_ms))
                    except Exception: pass
                # Pack name label (derive from path if available)
                if getattr(self, 'current_pack_path', None) and hasattr(pt, 'lab_pack_name'):
                    try: pt.lab_pack_name.setText(_os.path.basename(self.current_pack_path) or '(none)')
                    except Exception: pass
                # Text colour preview
                if hasattr(pt, 'lab_color_preview') and getattr(self, 'text_color', None) is not None:
                    try:
                        col = self.text_color
                        hexv = f"#{col.red():02X}{col.green():02X}{col.blue():02X}"
                        pt.lab_color_preview.setText(hexv)
                        pt.lab_color_preview.setStyleSheet(f"background:{hexv}; border:1px solid #555; padding:2px;")
                    except Exception: pass
            # --- Audio Page ---
            if getattr(self, 'page_audio', None):
                pa = self.page_audio
                # Update volume sliders using provided helper
                if hasattr(pa, 'set_vols'):
                    try: pa.set_vols(int(self.vol1 * 100), int(self.vol2 * 100))
                    except Exception: pass
                # Update file labels if paths present
                if getattr(self, 'audio1_path', None) and hasattr(pa, 'set_file1_label'):
                    try: pa.set_file1_label(_os.path.basename(self.audio1_path))
                    except Exception: pass
                if getattr(self, 'audio2_path', None) and hasattr(pa, 'set_file2_label'):
                    try: pa.set_file2_label(_os.path.basename(self.audio2_path))
                    except Exception: pass
            # --- Device Page ---
            if getattr(self, 'page_device', None):
                pd = self.page_device
                # Buzz on flash toggle & intensity
                if hasattr(pd, 'sw_buzz'):
                    try: pd.sw_buzz.blockSignals(True); pd.sw_buzz.setChecked(bool(self.enable_buzz_on_flash))
                    finally:
                        try: pd.sw_buzz.blockSignals(False)
                        except Exception: pass
                if hasattr(pd, 'sld_buzz'):
                    try:
                        pd.sld_buzz.blockSignals(True)
                        pd.sld_buzz.setValue(int(self.buzz_intensity * 100))
                        pd.lab_buzz.setText(f"{int(self.buzz_intensity*100)}%")
                    finally:
                        try: pd.sld_buzz.blockSignals(False)
                        except Exception: pass
                # Bursts enable & parameters
                if hasattr(pd, 'sw_bursts'):
                    try: pd.sw_bursts.blockSignals(True); pd.sw_bursts.setChecked(bool(self.enable_bursts))
                    finally:
                        try: pd.sw_bursts.blockSignals(False)
                        except Exception: pass
                if hasattr(pd, 'spin_min'):
                    try: pd.spin_min.blockSignals(True); pd.spin_min.setValue(int(self.burst_min_s))
                    finally:
                        try: pd.spin_min.blockSignals(False)
                        except Exception: pass
                if hasattr(pd, 'spin_max'):
                    try: pd.spin_max.blockSignals(True); pd.spin_max.setValue(int(self.burst_max_s))
                    finally:
                        try: pd.spin_max.blockSignals(False)
                        except Exception: pass
                if hasattr(pd, 'sld_peak'):
                    try:
                        pd.sld_peak.blockSignals(True)
                        pd.sld_peak.setValue(int(self.burst_peak * 100))
                        pd.lab_peak.setText(f"{int(self.burst_peak*100)}%")
                    finally:
                        try: pd.sld_peak.blockSignals(False)
                        except Exception: pass
                if hasattr(pd, 'spin_max_ms'):
                    try: pd.spin_max_ms.blockSignals(True); pd.spin_max_ms.setValue(int(self.burst_max_ms))
                    finally:
                        try: pd.spin_max_ms.blockSignals(False)
                        except Exception: pass
        except Exception:
            pass
        try:
            self._refresh_status()
        except Exception:
            pass

    def _start_mesmer_server(self):
        """Start MesmerIntiface server if not already running."""
        # NOTE: Previous patch accidentally dedented the body leading to a class-level
        # 'if not self.mesmer_server' which executed at class creation and raised NameError.
        # This restores correct indentation so the logic runs only when method is invoked.
        if self._suppress_server:
            return
        if not self.mesmer_server and MesmerIntifaceServer is not None:  # type: ignore[truthy-bool]
            try:
                self.mesmer_server = MesmerIntifaceServer(port=12350)
                self.mesmer_server.start()
                # Register device list change callback to update UI for both virtual and BLE devices
                def _cb(dev_list):  # inline small callback; resilient to exceptions
                    try:
                        self.scan_signaler.scan_completed.emit(dev_list)
                    except Exception:
                        pass  # swallow; UI closed or signal disconnected
                self._mesmer_device_cb = _cb
                try:
                    self.mesmer_server.add_device_callback(_cb)
                except Exception:
                    self._mesmer_device_cb = None  # fallback if API differs / not available
                logging.getLogger(__name__).info("MesmerIntiface server started automatically on port 12350")
                self._refresh_status()
            except Exception as e:  # pragma: no cover - defensive runtime path
                logging.getLogger(__name__).error("Failed to start MesmerIntiface server: %s", e)
                self.mesmer_server = None

    def _on_toggle_device_sync(self, b: bool): 
        self.enable_device_sync = b
        if b and not self.mesmer_server:
            try:
                self.mesmer_server = MesmerIntifaceServer(port=12350)
                self.mesmer_server.start()
                # Register device list change callback
                def _cb(dev_list):
                    try:
                        self.scan_signaler.scan_completed.emit(dev_list)
                    except Exception:
                        pass
                self._mesmer_device_cb = _cb
                try:
                    self.mesmer_server.add_device_callback(_cb)
                except Exception:
                    self._mesmer_device_cb = None
                logging.getLogger(__name__).info("MesmerIntiface server started on port 12350")
            except Exception as e:
                logging.getLogger(__name__).error("Failed to start MesmerIntiface server: %s", e)
                self.mesmer_server = None
        elif not b and self.mesmer_server:
            # Schedule async shutdown on persistent BLE loop instead of creating a short-lived loop
            async def _shutdown_server():
                try:
                    await self.mesmer_server.shutdown()  # type: ignore[func-returns-value]
                except Exception as e:
                    logging.getLogger(__name__).error("Error stopping MesmerIntiface server: %s", e)
            self._run_ble_coro(_shutdown_server())
            # Detach callback & clear ref synchronously (actual async cleanup continues in background)
            try:
                if getattr(self, "_mesmer_device_cb", None):
                    self.mesmer_server.remove_device_callback(self._mesmer_device_cb)
            except Exception:
                pass
            self.mesmer_server = None
            logging.getLogger(__name__).info("MesmerIntiface server stop requested")
        self._refresh_status()

    def _on_scan_devices(self):
        """Handle device scan request."""
        if self.device_scan_in_progress or not self.mesmer_server:
            return
        self.device_scan_in_progress = True
        # Run scan entirely inside persistent BLE loop; emit Qt signal back on completion.
        async def _scan():
            try:
                logging.getLogger(__name__).info("Starting Bluetooth device scan...")
                success = await self.mesmer_server.start_real_scanning()  # type: ignore[func-returns-value]
                if success:
                    await asyncio.sleep(8.0)
                    await self.mesmer_server.stop_real_scanning()  # type: ignore[func-returns-value]
                    device_list = self.mesmer_server.get_device_list()
                    self.scan_signaler.scan_completed.emit(device_list)
                else:
                    logging.getLogger(__name__).error("Failed to start Bluetooth scan — showing current device list")
                    try:
                        device_list = self.mesmer_server.get_device_list()
                        self.scan_signaler.scan_completed.emit(device_list)
                    except Exception:
                        QTimer.singleShot(0, lambda: self._scan_completed(None))
            except Exception:
                from PyQt6.QtCore import QTimer as _QtTimer
                _QtTimer.singleShot(0, lambda: self._scan_completed(None))
            finally:
                self.device_scan_in_progress = False
        self._run_ble_coro(_scan())

    def _update_device_list_ui(self, device_list):
        """Update UI with scan results (called on main thread)."""
        self.device_scan_in_progress = False
        logging.getLogger(__name__).info("Updating UI with %d devices", len(device_list.devices))
        for device in device_list.devices:
            logging.getLogger(__name__).debug(" - %s (index: %s)", device.name, device.index)
        self.page_device.update_device_list(device_list)
        if self.enable_device_sync and device_list.devices:
            for device in device_list.devices:
                try:
                    self.pulse.device_manager.add_device({
                        "DeviceIndex": device.index,
                        "DeviceName": device.name,
                        "DeviceMessages": device.device_messages
                    })
                except Exception:
                    pass

    def _scan_completed(self, device_list):
        """Handle scan completion."""
        if self._shutting_down:
            return
        self.device_scan_in_progress = False
        if device_list:
            self._update_device_list_ui(device_list)
        else:
            self.page_device.reset_scan_button()

    def _on_device_selected(self, device_idx: int):
        """Handle device selection."""
        if not self.mesmer_server:
            return
        logging.getLogger(__name__).info("Selecting device with Buttplug index %s", device_idx)
        # Stop any active scan immediately using persistent loop
        async def _stop_scan_if_running():
            try:
                if self.mesmer_server and self.mesmer_server.is_real_scanning():
                    await self.mesmer_server.stop_real_scanning()  # type: ignore[func-returns-value]
            except Exception:
                pass
        self._run_ble_coro(_stop_scan_if_running())
        if hasattr(self.pulse, 'select_device_by_index'):
            self.pulse.select_device_by_index(device_idx)
        elif hasattr(self.pulse, 'device_manager'):
            self.pulse.device_manager.select_device(device_idx)
        device_list = self.mesmer_server.get_device_list(); list_idx = None
        for i, device in enumerate(device_list.devices):
            if device.index == device_idx:
                list_idx = i; break
        if list_idx is not None:
            self.mesmer_server.select_device(list_idx)
            logging.getLogger(__name__).info("Selected device at list index %s (Buttplug index %s)", list_idx, device_idx)
            async def _connect_real():
                try:
                    if hasattr(self.mesmer_server, "is_ble_device_index") and not self.mesmer_server.is_ble_device_index(device_idx):
                        logging.getLogger(__name__).info("Selected virtual device %s (no BLE connect)", device_idx)
                        return True
                    logging.getLogger(__name__).info("Attempting to connect to real device %s...", device_idx)
                    success = await self.mesmer_server.connect_real_device(device_idx)  # type: ignore[func-returns-value]
                    if success:
                        logging.getLogger(__name__).info("Successfully connected to device %s", device_idx)
                    else:
                        logging.getLogger(__name__).error("Failed to connect to device %s", device_idx)
                except Exception as e:
                    logging.getLogger(__name__).exception("Error connecting to device %s: %s", device_idx, e)
            self._run_ble_coro(_connect_real())
            # Start / ensure maintenance timer exists
            try:
                from PyQt6.QtCore import QTimer as _QTimer
                if not hasattr(self, '_ble_maint_timer'):
                    self._ble_maint_timer = _QTimer(self)
                    self._ble_maint_timer.setInterval(10000)  # 10s
                    def _maint():
                        if not self.mesmer_server:
                            return
                        async def _maint_coro():
                            try:
                                await self.mesmer_server.maintain_selected_device_connections()  # type: ignore[func-returns-value]
                            except Exception:
                                pass
                        self._run_ble_coro(_maint_coro())
                    self._ble_maint_timer.timeout.connect(_maint)
                    self._ble_maint_timer.start()
            except Exception:
                pass
        else:
            logging.getLogger(__name__).error("Could not find device with Buttplug index %s", device_idx)
        device_list = self.mesmer_server.get_device_list(); self.page_device.update_device_list(device_list)

    def _refresh_status(self):
        self.chip_overlay.setText(f"Overlay: {'Running' if self.running else 'Idle'}")
        a_count = (1 if self.audio1_path else 0) + (1 if self.audio2_path else 0)
        self.chip_audio.setText(f"Audio: {a_count}/2")
        self.chip_device.setText("Device: On" if self.enable_device_sync else "Device: Off")

    def _on_devices_selected(self, indices: object):
        """Handle multi-device selection: connect BLE ones and mirror UI label."""
        try:
            sel: list[int] = list(indices) if isinstance(indices, (list, tuple, set)) else []
        except Exception:
            sel = []
        if not sel or not self.mesmer_server:
            return
        try:
            if hasattr(self.pulse, 'device_manager') and hasattr(self.pulse.device_manager, 'select_devices'):
                self.pulse.device_manager.select_devices(sel)
        except Exception:
            pass
        try:
            dev_list = self.mesmer_server.get_device_list()
            name_map = {d.index: d.name for d in dev_list.devices}
            names = [name_map.get(i, str(i)) for i in sel]
            if hasattr(self.page_device, 'set_selected_devices'):
                self.page_device.set_selected_devices(names)
        except Exception:
            pass
        async def _connect_many(indices: list[int]):
            for idx in indices:
                try:
                    if hasattr(self.mesmer_server, 'is_ble_device_index') and not self.mesmer_server.is_ble_device_index(idx):
                        continue
                    await self.mesmer_server.connect_real_device(idx)  # type: ignore[func-returns-value]
                except Exception:
                    pass
        self._run_ble_coro(_connect_many(sel))

    # ====================== launch / stop (unchanged) ======================
    def launch(self):
        if self.running: return
        self.running = True; self._refresh_status()
        self.audio.play(self.vol1, self.vol2)
        if self.enable_device_sync: self.pulse.start()
        else:                        self.pulse.stop()
        self.overlays.clear()
        screens = QGuiApplication.screens()
        checked_idx = [i for i in range(self.list_displays.count())
                       if self.list_displays.item(i).checkState()==Qt.CheckState.Checked]
        if not checked_idx and self.list_displays.count()>0:
            self.list_displays.item(0).setCheckState(Qt.CheckState.Checked)
            checked_idx = [0]
        shared_start_time = time.time()
        for i in checked_idx:
            sc = screens[i] if i < len(screens) else screens[0]
            ov = OverlayWindow(sc, self.primary_path or None, self.secondary_path or None,
                               self.primary_op, self.secondary_op, self.text, self.text_color, self.text_font,
                               self.text_scale_pct, self.flash_interval_ms, self.flash_width_ms,
                               self.fx_mode, self.fx_intensity)
            ov.start_time = shared_start_time
            self.overlays.append(ov)
        # Always use a single shared flash timer so message changes align exactly
        # with flash boundaries (prevents mid-flash text changes). Buzz logic
        # inside the timer remains conditional on enable_device_sync.
        if self.overlays:
            self._wire_shared_flash_timer(shared_start_time)
        if self.enable_device_sync and self.enable_bursts:
            self._start_burst_scheduler()

    def _wire_shared_flash_timer(self, shared_start_time: float):
        """Single synchronized flash timer (always used).

        We pick a new random message only on the rising edge of a flash (show
        transitions False->True). This guarantees the text does not change mid
        flash and keeps all overlays in sync. (Revised: we now pre-pick the
        next flash's message shortly *before* the visible phase begins so the
        very first illuminated frame already shows the new text. This removes
        the user's observed mid-illumination text switch caused by picking a
        few milliseconds after the flash started.)
        """
        self._shared_flash_timer = QTimer(self)
        self._prev_flash_show = False
        # Track which cycle (integer division of elapsed_ms / interval) we have
        # already prepared/picked a message for. We prepare the *upcoming* cycle
        # shortly before it becomes visible (during the dark phase) so that the
        # first bright frame already has the new message.
        self._prepared_cycle = -1  # last cycle index for which message was set
        lead_ms = 40  # how many ms before flash start we pre-pick (tunable)
        def on_shared_tick():
            if not self.overlays:
                return
            # Use current global flash settings (self.flash_interval_ms / self.flash_width_ms)
            # so changes via UI take effect immediately without recreating timer.
            now_ms = int((time.time() - shared_start_time) * 1000.0)
            interval = max(50, int(getattr(self, 'flash_interval_ms', 1200)))
            width = max(10, min(interval, int(getattr(self, 'flash_width_ms', 250))))
            phase = now_ms % interval
            cycle = now_ms // interval  # integer cycle index
            show = phase < width

            if not show:
                # We're in dark phase. If close to next flash boundary (within lead_ms)
                # prepare upcoming cycle's message (cycle+1) once.
                remaining = interval - phase
                if remaining <= lead_ms:
                    upcoming_cycle = cycle + 1
                    if self._prepared_cycle != upcoming_cycle:
                        self._pick_random_message()  # pre-pick for next flash
                        self._prepared_cycle = upcoming_cycle
            else:
                # Visible phase. On the very first tick of visibility ensure a
                # message exists for this cycle (fallback if pre-pick missed boundary).
                if not self._prev_flash_show:
                    if self._prepared_cycle != cycle:
                        self._pick_random_message()
                        self._prepared_cycle = cycle
                    if self.enable_device_sync and self.enable_buzz_on_flash:
                        ms = width
                        lvl = float(clamp(self.buzz_intensity, 0.0, 1.0))
                        self.pulse.pulse(lvl, ms)

            self._prev_flash_show = show
        self._shared_flash_timer.timeout.connect(on_shared_tick)
        self._shared_flash_timer.start(15)  # 15ms interval for smooth detection

    # per-overlay timer removed; shared timer always used

    def _start_burst_scheduler(self):
        self._burst_next_at = time.time() + random.uniform(self.burst_min_s, self.burst_max_s)
        self._burst_timer = QTimer(self)
        def tick():
            if not (self.running and self.enable_device_sync and self.enable_bursts): return
            now = time.time()
            if now >= self._burst_next_at:
                peak = float(clamp(self.burst_peak, 0.0, 1.0)); max_ms = max(200, int(self.burst_max_ms))
                seq = [(peak*0.3, int(max_ms*0.25)), (peak*0.7, int(max_ms*0.30)), (peak*1.0, int(max_ms*0.35))]
                def run_seq():
                    for lvl, ms in seq:
                        self.pulse.pulse(lvl, ms); time.sleep(ms/1000.0 + 0.05)
                    self.pulse.set_level(0.0)
                threading.Thread(target=run_seq, daemon=True).start()
                self._burst_next_at = now + random.uniform(self.burst_min_s, self.burst_max_s)
        self._burst_timer.timeout.connect(tick); self._burst_timer.start(200)

    def stop_all(self):
        if not self.running:
            return
        log = logging.getLogger(__name__)
        t0 = time.perf_counter()
        def step(n, msg):
            log.info("[SHUTDOWN launcher] step=%s dt=%.3f %s", n, time.perf_counter()-t0, msg)
        self.running = False; self._refresh_status(); step(1, "running flag cleared")
        if hasattr(self, "_shared_flash_timer") and self._shared_flash_timer:
            try: self._shared_flash_timer.stop()
            except Exception: pass
            self._shared_flash_timer = None; step(2, "shared flash timer stopped")
        if hasattr(self, "_burst_timer") and self._burst_timer:
            try: self._burst_timer.stop()
            except Exception: pass
            self._burst_timer = None; step(3, "burst timer stopped")
        for ov in list(self.overlays):
            try:
                if hasattr(ov, 'shutdown'):
                    ov.shutdown()
                if hasattr(ov, "_flash_sync_timer"):
                    try: ov._flash_sync_timer.stop()
                    except Exception: pass
                ov.close(); step(4, "overlay closed")
            except Exception:
                pass
        self.overlays.clear(); step(5, "overlays cleared")
        try: self.audio.stop(); step(6, "audio stopped")
        except Exception: pass
        try: self.pulse.stop(); step(7, "pulse stopped")
        except Exception: pass

    def closeEvent(self, event):  # type: ignore[override]
        log = logging.getLogger(__name__)
        t0 = time.perf_counter()
        def step(n, msg):
            """Structured shutdown step logger with immediate flush.

            We flush handlers so if a native crash occurs *after* the call we
            still have the most recent breadcrumb in the log file/console.
            """
            log.info("[SHUTDOWN close] step=%s dt=%.3f %s", n, time.perf_counter()-t0, msg)
            for h in getattr(log, 'handlers', []):  # best‑effort flush
                try:
                    if hasattr(h, 'flush'):
                        h.flush()
                except Exception:
                    pass
        step(0, "closeEvent begin")
        self._shutting_down = True
        step(0.5, f"shutdown flag set scan_in_progress={self.device_scan_in_progress}")
        try:
            self.stop_all()
        except Exception:
            log.exception("stop_all failure")
        step(8, "stop_all done")
        # If a real scan is running, stop it cleanly before shutting server
        try:
            async def _graceful_stop_scan():
                if self.mesmer_server and hasattr(self.mesmer_server, 'is_real_scanning') and self.mesmer_server.is_real_scanning():
                    step(8.5, "scan active - stopping (async)")
                    try:
                        await asyncio.wait_for(self.mesmer_server.stop_real_scanning(), timeout=6.0)  # type: ignore[arg-type]
                    except asyncio.TimeoutError:
                        step(8.53, "scan stop timeout -> continuing")
                    except Exception as e:
                        step(8.55, f"scan stop error {e!r}")
            self._run_ble_coro(_graceful_stop_scan())
        except Exception as e:
            log.error("scan stop scheduling error: %s", e)
        if self.mesmer_server:
            async def _shutdown_server_async():
                try:
                    step(9, "mesmer server shutdown begin (async)")
                    await self.mesmer_server.shutdown()  # type: ignore[func-returns-value]
                    step(9.5, "mesmer server shutdown done (async)")
                except Exception as e:
                    log.error("Mesmer shutdown error: %s", e)
            self._run_ble_coro(_shutdown_server_async())
        # After scheduling async teardown, give a tiny grace period for queued tasks
        _ts2 = time.perf_counter()
        while time.perf_counter() - _ts2 < 0.15:
            _time_mod.sleep(0.01)
        # Stop persistent BLE loop last
        self._stop_ble_loop()
        step(9.9, "BLE loop stopped")
        try:
            self.pulse.set_level(0.0); step(10, "pulse level zeroed")
        except Exception: pass
        try:
            super().closeEvent(event); step(11, "super closeEvent")
        except Exception: pass
        step(12, "closeEvent end")

    # ====================== BLE loop helpers =======================
    def _run_ble_coro(self, coro: asyncio.coroutines, timeout: float | None = None):  # type: ignore[type-arg]
        """Submit a coroutine to the persistent BLE loop safely.

        - Returns future.result() if timeout provided & completes, else Future.
        - Swallows scheduling if loop already shutting down.
        """
        loop = self._ble_loop
        if not loop or not self._ble_loop_alive:
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            return None
        if timeout is not None:
            try:
                return fut.result(timeout)
            except Exception:
                return None
        return fut

    def _stop_ble_loop(self):
        """Stop and join the persistent BLE event loop thread."""
        if not self._ble_loop_alive:
            return
        self._ble_loop_alive = False
        loop = self._ble_loop
        try:
            if loop and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
        except Exception:
            pass
        try:
            if hasattr(self, '_ble_loop_thread') and self._ble_loop_thread.is_alive():
                self._ble_loop_thread.join(timeout=1.5)
        except Exception:
            pass
    # ---------------- Message Pack (v1 mapping) ----------------
    def apply_session_pack(self, pack):  # duck-typed SessionPack
        try:
            self.session_pack = pack
            self._cycle_index = 0
            self._cycle_weights = []
            first = getattr(pack, 'first_text', None)
            # Always show first message if current text empty OR we're reloading from state
            if first and (not getattr(self, 'text', None)):
                self.text = first
            try:
                if first and hasattr(self, 'page_textfx') and self.page_textfx and hasattr(self.page_textfx, 'set_text'):
                    self.page_textfx.set_text(self.text)
                if hasattr(self, 'page_textfx') and self.page_textfx and hasattr(self.page_textfx, 'set_pack_name'):
                    self.page_textfx.set_pack_name(getattr(pack, 'name', '(pack)'))
            except Exception:
                pass
            avg = getattr(pack, 'avg_intensity', None)
            if avg is not None:
                self.buzz_intensity = max(0.0, min(1.0, float(avg)))
            # Track source path (loader injects _source_path into raw dict)
            try:
                raw = getattr(pack, 'raw', {}) or {}
                self.current_pack_path = raw.get('_source_path', self.current_pack_path)
            except Exception:
                pass
            logging.getLogger(__name__).info("Applied message pack '%s' (text_set=%s avg_intensity=%s)", getattr(pack, 'name', '?'), bool(first), avg)
            # Precompute weights for per-flash random selection
            self._prepare_pack_weights()
        except Exception as e:
            logging.getLogger(__name__).error("Failed to apply message pack: %s", e)
            raise

    # ---- message pack UI handlers ----
    def _on_load_session_pack(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        try:
            fn, _ = QFileDialog.getOpenFileName(self, "Load message pack", "", "Message Packs (*.json);;All Files (*.*)")
            if not fn:
                return
            from ..content.loader import load_session_pack
            pack = load_session_pack(fn)
            self.apply_session_pack(pack)
            self.current_pack_path = fn  # remember explicit user load path
            QMessageBox.information(self, "Message Pack", f"Loaded pack '{pack.name}'")
        except Exception as e:
            logging.getLogger(__name__).error("Error loading message pack: %s", e)
            try:
                QMessageBox.critical(self, "Message Pack", f"Failed to load pack: {e}")
            except Exception:
                pass

    def _on_save_session_pack(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        try:
            fn, _ = QFileDialog.getSaveFileName(self, "Save message pack", "message_pack.json", "Message Packs (*.json);;All Files (*.*)")
            if not fn:
                return
            # Build a minimal pack dictionary reflecting current text + a single pulse stage heuristic
            data = {
                "version": 1,
                "name": "Saved Pack",
                "text": {"items": [{"msg": getattr(self, 'text', ''), "secs": 5}]},
                "pulse": {"stages": [{"mode": "wave", "intensity": float(getattr(self, 'buzz_intensity', 0.5)), "secs": 10}], "fallback": "idle"}
            }
            import json
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if hasattr(self.page_textfx, 'set_pack_name'):
                self.page_textfx.set_pack_name(data.get('name'))
            QMessageBox.information(self, "Message Pack", f"Saved pack to {fn}")
        except Exception as e:
            logging.getLogger(__name__).error("Error saving message pack: %s", e)
            try:
                QMessageBox.critical(self, "Message Pack", f"Failed to save pack: {e}")
            except Exception:
                pass
    # New editor dialog
    def _on_create_message_pack(self):
        try:
            from .dialogs.message_pack_editor import MessagePackEditor
            from PyQt6.QtWidgets import QDialog
            dlg = MessagePackEditor(self)
            if dlg.exec() == QDialog.DialogCode.Accepted and hasattr(dlg, 'result_pack'):
                pack = dlg.result_pack
                self.apply_session_pack(pack)
                try:
                    self.page_textfx.set_pack_name(getattr(pack, 'name', '(pack)'))
                except Exception:
                    pass
        except Exception as e:
            logging.getLogger(__name__).error("Editor failed: %s", e)

    # ---------------- Menu Bar Integration ----------------
    def _install_menu_bar(self):  # idempotent; safe to call multiple times
        # Guard so repeated calls do not rebuild menus (tests may invoke)
        if getattr(self, "_menu_installed", False):  # inline quick check
            return
        try:
            from PyQt6.QtWidgets import QMenuBar, QMessageBox
        except Exception:
            return  # headless tests without full Qt
        mb = self.menuBar() if hasattr(self, 'menuBar') else None
        if mb is None:
            try:
                mb = QMenuBar(self)
                self.setMenuBar(mb)
            except Exception:
                return
        # Remove existing actions to ensure a clean slate the FIRST time we install.
        try:
            while mb.actions():
                mb.removeAction(mb.actions()[0])
        except Exception:
            pass
        file_menu = mb.addMenu("File")  # top-level File menu
        # Only state actions remain (pack management moved/removed per user request)
        try:
            act_save = file_menu.addAction("Save State…"); act_save.triggered.connect(self._action_save_state)  # type: ignore[attr-defined]
            act_load = file_menu.addAction("Load State…"); act_load.triggered.connect(self._action_load_state)  # type: ignore[attr-defined]
            file_menu.addSeparator()
        except Exception:
            pass
        try:
            exit_act = file_menu.addAction("Exit")
            exit_act.triggered.connect(self.close)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Mark as installed so subsequent calls are cheap no-ops.
        self._menu_installed = True

    def _action_save_state(self):
        """Interactive save of current runtime state."""
        try:
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            fn, _ = QFileDialog.getSaveFileName(self, "Save Session State", "session_state.json", "State (*.json);;All Files (*.*)")
            if not fn:
                return
            st = self.capture_session_state()
            if not st:
                QMessageBox.critical(self, "Save State", "Failed to capture state")
                return
            from ..content.loader import save_session_state
            save_session_state(st, fn)
            QMessageBox.information(self, "Save State", f"Saved to {os.path.basename(fn)}")
        except Exception as e:
            logging.getLogger(__name__).error("State save failed: %s", e)
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Save State", f"Failed: {e}")
            except Exception:
                pass

    def _action_load_state(self):
        """Interactive load of a previously saved runtime state."""
        try:
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            fn, _ = QFileDialog.getOpenFileName(self, "Load Session State", "", "State (*.json);;All Files (*.*)")
            if not fn:
                return
            from ..content.loader import load_session_state
            st = load_session_state(fn)
            self.apply_session_state(st)
            QMessageBox.information(self, "Load State", f"Loaded {os.path.basename(fn)}")
        except Exception as e:
            logging.getLogger(__name__).error("State load failed: %s", e)
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Load State", f"Failed: {e}")
            except Exception:
                pass

    # Legacy cycle timer methods removed (replaced by per-flash pre-pick logic above)

    def _prepare_pack_weights(self):  # Per-flash random message selection helper
        """Build weight list from current session_pack for random selection each flash."""
        try:
            pack = getattr(self, 'session_pack', None)
            self._cycle_weights = []
            if not pack or not getattr(pack, 'text', None) or not pack.text.items:
                return
            for it in pack.text.items:
                try:
                    w = float(getattr(it, 'effective_weight', lambda: 1.0)())
                except Exception:
                    w = float(getattr(it, 'secs', 1) or 1)
                if w <= 0: w = 1.0
                self._cycle_weights.append(w)
        except Exception:
            self._cycle_weights = []

    def _pick_random_message(self):
        try:
            import random
            pack = getattr(self, 'session_pack', None)
            if not pack or not getattr(pack, 'text', None) or not pack.text.items:
                return
            items = pack.text.items
            if not items: return
            weights = getattr(self, '_cycle_weights', None)
            if not weights or len(weights) != len(items):
                self._prepare_pack_weights(); weights = getattr(self, '_cycle_weights', [1]*len(items))
            idx = random.choices(range(len(items)), weights=weights, k=1)[0]
            msg = items[idx].msg
            self.text = msg
            try:
                if hasattr(self.page_textfx, 'set_text'): self.page_textfx.set_text(msg)
                # Update overlay texts live
                for ov in getattr(self, 'overlays', []):
                    ov.text = msg
            except Exception:
                pass
        except Exception as e:
            logging.getLogger(__name__).error("Random message pick failed: %s", e)

    def _on_text_color_changed(self, hex_str: str):
        """Update text colour and propagate to overlays."""
        try:
            from PyQt6.QtGui import QColor
            c = QColor(hex_str)
            if c.isValid():
                self.text_color = c
                for ov in getattr(self, 'overlays', []):
                    ov.text_color = c
        except Exception:
            pass
    # Legacy cycle timer removed: no action needed on color change beyond overlay propagation.