import os, time, random, threading, time as _time_mod
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
from ..engine.mesmerintiface import MesmerIntifaceServer
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

        # UI / services ----------------------------------------------
        self._build_ui()
        self._bind_shortcuts()
        self._start_mesmer_server()

        # Message pack placeholder
        self.session_pack = None

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

    def _start_mesmer_server(self):
        """Start MesmerIntiface server if not already running."""
        if not self.mesmer_server:
            try:
                self.mesmer_server = MesmerIntifaceServer(port=12350)
                self.mesmer_server.start()
                # Register device list change callback to update UI for both virtual and BLE devices
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
                logging.getLogger(__name__).info("MesmerIntiface server started automatically on port 12350")
                self._refresh_status()
            except Exception as e:
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
            try:
                import asyncio
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(self.mesmer_server.shutdown()); loop.close()
                # Remove device callback
                try:
                    if getattr(self, "_mesmer_device_cb", None):
                        self.mesmer_server.remove_device_callback(self._mesmer_device_cb)
                except Exception:
                    pass
                self.mesmer_server = None
                logging.getLogger(__name__).info("MesmerIntiface server stopped")
            except Exception as e:
                logging.getLogger(__name__).error("Error stopping MesmerIntiface server: %s", e)
        self._refresh_status()

    def _on_scan_devices(self):
        """Handle device scan request."""
        if self.device_scan_in_progress or not self.mesmer_server:
            return
        self.device_scan_in_progress = True
        import asyncio
        def scan_task():
            try:
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                async def do_scan():
                    logging.getLogger(__name__).info("Starting Bluetooth device scan...")
                    success = await self.mesmer_server.start_real_scanning()
                    if success:
                        await asyncio.sleep(8.0)
                        await self.mesmer_server.stop_real_scanning()
                        device_list = self.mesmer_server.get_device_list()
                        self.scan_signaler.scan_completed.emit(device_list)
                    else:
                        logging.getLogger(__name__).error("Failed to start Bluetooth scan — showing current device list")
                        try:
                            device_list = self.mesmer_server.get_device_list()
                            self.scan_signaler.scan_completed.emit(device_list)
                        except Exception:
                            QTimer.singleShot(0, lambda: self._scan_completed(None))
                loop.run_until_complete(do_scan()); loop.close()
            except Exception:
                from PyQt6.QtCore import QTimer as _QtTimer
                _QtTimer.singleShot(0, lambda: self._scan_completed(None))
            finally:
                self.device_scan_in_progress = False
        threading.Thread(target=scan_task, daemon=True).start()

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
        # Stop any active scan immediately (on-demand scanning model)
        try:
            import asyncio as _a
            if self.mesmer_server.is_real_scanning():
                loop = _a.new_event_loop(); _a.set_event_loop(loop)
                loop.run_until_complete(self.mesmer_server.stop_real_scanning()); loop.close()
        except Exception:
            pass
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
            import asyncio
            def connect_device():
                try:
                    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                    async def do_connect():
                        if hasattr(self.mesmer_server, "is_ble_device_index") and not self.mesmer_server.is_ble_device_index(device_idx):
                            logging.getLogger(__name__).info("Selected virtual device %s (no BLE connect)", device_idx)
                            return True
                        logging.getLogger(__name__).info("Attempting to connect to real device %s...", device_idx)
                        success = await self.mesmer_server.connect_real_device(device_idx)
                        if success:
                            logging.getLogger(__name__).info("Successfully connected to device %s", device_idx)
                        else:
                            logging.getLogger(__name__).error("Failed to connect to device %s", device_idx)
                        return success
                    _ = loop.run_until_complete(do_connect()); loop.close()
                except Exception as e:
                    logging.getLogger(__name__).exception("Error connecting to device %s: %s", device_idx, e)
            threading.Thread(target=connect_device, daemon=True).start()
            # Start / ensure maintenance timer exists
            try:
                from PyQt6.QtCore import QTimer as _QTimer
                if not hasattr(self, '_ble_maint_timer'):
                    self._ble_maint_timer = _QTimer(self)
                    self._ble_maint_timer.setInterval(10000)  # 10s
                    def _maint():
                        import threading as _th, asyncio as _asyncio
                        if not self.mesmer_server:
                            return
                        def _run():
                            try:
                                loop = _asyncio.new_event_loop(); _asyncio.set_event_loop(loop)
                                async def do_maint():
                                    try:
                                        await self.mesmer_server.maintain_selected_device_connections()
                                    except Exception:
                                        pass
                                loop.run_until_complete(do_maint()); loop.close()
                            except Exception:
                                pass
                        _th.Thread(target=_run, daemon=True).start()
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
        import asyncio
        def connect_many(indices: list[int]):
            try:
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                async def do_all():
                    for idx in indices:
                        try:
                            if hasattr(self.mesmer_server, 'is_ble_device_index') and not self.mesmer_server.is_ble_device_index(idx):
                                continue
                            await self.mesmer_server.connect_real_device(idx)
                        except Exception:
                            pass
                loop.run_until_complete(do_all()); loop.close()
            except Exception:
                pass
        threading.Thread(target=connect_many, args=(sel,), daemon=True).start()

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
            if self.mesmer_server and hasattr(self.mesmer_server, 'is_real_scanning') and self.mesmer_server.is_real_scanning():
                step(8.5, "scan active - stopping")
                import asyncio
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                step(8.51, f"loop created id={id(loop)}")
                async def _stop_scan():  # inline coroutine for timeout control
                    step(8.52, "stop coroutine begin")  # inside coroutine start
                    try:
                        try:
                            await asyncio.wait_for(self.mesmer_server.stop_real_scanning(), timeout=6.0)
                        except asyncio.TimeoutError:
                            step(8.53, "scan stop timeout -> continuing")
                        else:
                            step(8.54, "scan stop coroutine returned")
                    except Exception as e:  # capture unexpected internal errors
                        step(8.55, f"scan stop error {e!r}")
                try:
                    loop.run_until_complete(_stop_scan())
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass
                step(8.56, "event loop closed")
                # Short settle delay – some native stacks need a beat after scan stop
                _ts = time.perf_counter()
                while time.perf_counter() - _ts < 0.15:
                    # tiny sleep slices to keep UI responsive while allowing BLE stack to settle
                    _time_mod.sleep(0.01)
                step(8.6, "scan stopped + settled")
                # (If crash still happens after 8.6 we know it is *after* scan tear‑down.)
        except Exception as e:
            log.error("scan stop error: %s", e)
        if self.mesmer_server:
            try:
                import asyncio
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                step(9, "mesmer server shutdown begin")
                loop.run_until_complete(self.mesmer_server.shutdown())
                loop.close(); step(9.5, "mesmer server shutdown done")
            except Exception as e:
                log.error("Mesmer shutdown error: %s", e)
        try:
            self.pulse.set_level(0.0); step(10, "pulse level zeroed")
        except Exception: pass
        try:
            super().closeEvent(event); step(11, "super closeEvent")
        except Exception: pass
        step(12, "closeEvent end")
    # ---------------- Message Pack (v1 mapping) ----------------
    def apply_session_pack(self, pack):  # duck-typed SessionPack
        try:
            self.session_pack = pack
            self._cycle_index = 0
            self._cycle_weights = []
            first = getattr(pack, 'first_text', None)
            if first:
                self.text = first
                try:
                    if hasattr(self.page_textfx, 'set_text'):
                        self.page_textfx.set_text(first)
                    if hasattr(self.page_textfx, 'set_pack_name'):
                        self.page_textfx.set_pack_name(getattr(pack, 'name', '(pack)'))
                except Exception:
                    pass
            avg = getattr(pack, 'avg_intensity', None)
            if avg is not None:
                self.buzz_intensity = max(0.0, min(1.0, float(avg)))
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