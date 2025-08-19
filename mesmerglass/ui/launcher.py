import os, time, random, threading
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
        super().__init__()
        self.setWindowTitle(title)
        # Layout mode: "tabbed" (default, current tests) or "sidebar"
        self.layout_mode = layout_mode if layout_mode in ("tabbed", "sidebar") else "tabbed"

        # State
        self.primary_path = ""; self.secondary_path = ""
        self.primary_op = 1.0; self.secondary_op = 0.5
        self.text = "MESMERGLASS"; self.text_color = QColor("white"); self.text_font = QFont("Segoe UI", 28)
        self.text_scale_pct = 100; self.fx_mode = "Breath + Sway"; self.fx_intensity = 50
        self.flash_interval_ms = 1200; self.flash_width_ms = 250

        self.audio1_path = ""; self.audio2_path = ""; self.vol1 = 0.5; self.vol2 = 0.5
        self.enable_device_sync = bool(enable_device_sync_default)
        self.enable_buzz_on_flash = True; self.buzz_intensity = 0.6
        self.enable_bursts = False; self.burst_min_s = 30; self.burst_max_s = 120; self.burst_peak = 0.9; self.burst_max_ms = 1200

        self.overlays = []
        self.running = False

        # Engines
        self.audio = Audio2()
        self.pulse = PulseEngine(use_mesmer=True, allow_auto_select=False)
        self.mesmer_server = None
        self._mesmer_device_cb = None
        self.device_scan_in_progress = False
        self.scan_signaler = ScanCompleteSignaler()
        self.scan_signaler.scan_completed.connect(self._scan_completed)

        # Build UI and start optional services
        self._build_ui()
        self._bind_shortcuts()
        self._start_mesmer_server()  # opportunistic start

    # ========================== UI build ==========================
    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QVBoxLayout(root); main.setContentsMargins(10, 10, 10, 10); main.setSpacing(10)

        # Tabs container (always created, used by both layouts)
        self.tabs = QTabWidget()

        # Media tab
        scroll_media = QScrollArea(); scroll_media.setWidgetResizable(True); scroll_media.setFrameShape(QFrame.Shape.NoFrame)
        scroll_media.setWidget(self._page_media())
        self.tabs.addTab(scroll_media, "Media")

        # Text & FX tab
        self.page_textfx = TextFxPage(
            text=self.text,
            text_scale_pct=self.text_scale_pct,
            fx_mode=self.fx_mode,
            fx_intensity=self.fx_intensity,
            flash_interval_ms=self.flash_interval_ms,
            flash_width_ms=self.flash_width_ms,
        )
        scroll_textfx = QScrollArea(); scroll_textfx.setWidgetResizable(True); scroll_textfx.setFrameShape(QFrame.Shape.NoFrame)
        scroll_textfx.setWidget(self.page_textfx)
        self.tabs.addTab(scroll_textfx, "Text & FX")

        # Audio tab
        self.page_audio = AudioPage(
            file1=os.path.basename(self.audio1_path),
            file2=os.path.basename(self.audio2_path),
            vol1_pct=int(self.vol1 * 100),
            vol2_pct=int(self.vol2 * 100),
        )
        scroll_audio = QScrollArea(); scroll_audio.setWidgetResizable(True); scroll_audio.setFrameShape(QFrame.Shape.NoFrame)
        scroll_audio.setWidget(self.page_audio)
        self.tabs.addTab(scroll_audio, "Audio")

        # Device tab
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
        scroll_device.setWidget(self.page_device)
        self.tabs.addTab(scroll_device, "Device Sync")

        # Displays tab
        scroll_displays = QScrollArea(); scroll_displays.setWidgetResizable(True); scroll_displays.setFrameShape(QFrame.Shape.NoFrame)
        scroll_displays.setWidget(self._page_displays())
        self.tabs.addTab(scroll_displays, "Displays")

        # Build chrome/layout
        if self.layout_mode == "sidebar":
            # Top bar with hard-coded program name as requested
            topbar = QWidget(); topbar.setObjectName("topBar")
            tbl = QHBoxLayout(topbar); tbl.setContentsMargins(12, 8, 12, 8); tbl.setSpacing(8)
            title_lab = QLabel("MesmerGlass"); title_lab.setObjectName("topTitle")
            tbl.addWidget(title_lab, 0); tbl.addStretch(1)
            # Status chips in top bar
            self.chip_overlay = QLabel("Overlay: Idle"); self.chip_overlay.setObjectName("statusChip")
            self.chip_device = QLabel("Device: Off"); self.chip_device.setObjectName("statusChip")
            tbl.addWidget(self.chip_overlay, 0); tbl.addWidget(self.chip_device, 0)
            main.addWidget(topbar, 0)

            # Left nav + content
            center = QWidget(); ch = QHBoxLayout(center); ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(10)
            self.nav = QListWidget(); self.nav.setObjectName("sideNav")
            for name in ("Media", "Text & FX", "Audio", "Device Sync", "Displays"):
                self.nav.addItem(name)
            self.nav.setCurrentRow(0)
            # Hide the tab bar; use side nav instead
            try:
                self.tabs.tabBar().setVisible(False)
            except Exception:
                pass
            ch.addWidget(self.nav, 0)
            ch.addWidget(self.tabs, 1)
            main.addWidget(center, 1)

            # Wire nav <-> tabs
            def _on_nav_change(i: int):
                if 0 <= i < self.tabs.count():
                    self.tabs.setCurrentIndex(i)
            self.nav.currentRowChanged.connect(_on_nav_change)
            self.tabs.currentChanged.connect(lambda i: self.nav.setCurrentRow(i))
        else:
            # Default: tabbed layout with visible tabs
            try:
                self.tabs.tabBar().setVisible(True)
            except Exception:
                pass
            main.addWidget(self.tabs, 1)

        # Wire page signals -> state
        self.page_textfx.textChanged.connect(lambda s: setattr(self, "text", s))
        self.page_textfx.fontRequested.connect(self._pick_font)
        self.page_textfx.colorRequested.connect(self._pick_color)
        self.page_textfx.textScaleChanged.connect(lambda v: setattr(self, "text_scale_pct", v))
        self.page_textfx.fxModeChanged.connect(lambda s: setattr(self, "fx_mode", s))
        self.page_textfx.fxIntensityChanged.connect(lambda v: setattr(self, "fx_intensity", v))
        self.page_textfx.flashIntervalChanged.connect(lambda v: setattr(self, "flash_interval_ms", v))
        self.page_textfx.flashWidthChanged.connect(lambda v: setattr(self, "flash_width_ms", v))

        # Audio wiring
        self.page_audio.load1Requested.connect(self._pick_a1)
        self.page_audio.load2Requested.connect(self._pick_a2)
        self.page_audio.vol1Changed.connect(lambda pct: self._set_vols(pct / 100.0, self.vol2))
        self.page_audio.vol2Changed.connect(lambda pct: self._set_vols(self.vol1, pct / 100.0))

        # Device wiring
        self.page_device.enableSyncChanged.connect(self._on_toggle_device_sync)
        self.page_device.scanDevicesRequested.connect(self._on_scan_devices)
        self.page_device.deviceSelected.connect(self._on_device_selected)
        self.page_device.devicesSelected.connect(self._on_devices_selected)  # multi-select handler
        self.page_device.buzzOnFlashChanged.connect(lambda b: setattr(self, "enable_buzz_on_flash", b))
        self.page_device.buzzIntensityChanged.connect(lambda v: setattr(self, "buzz_intensity", v / 100.0))
        self.page_device.burstsEnableChanged.connect(lambda b: setattr(self, "enable_bursts", b))
        self.page_device.burstMinChanged.connect(lambda v: setattr(self, "burst_min_s", v))
        self.page_device.burstMaxChanged.connect(lambda v: setattr(self, "burst_max_s", v))
        self.page_device.burstPeakChanged.connect(lambda v: setattr(self, "burst_peak", v / 100.0))
        self.page_device.burstMaxMsChanged.connect(lambda v: setattr(self, "burst_max_ms", v))

        # Footer (kept for controls and audio status). In sidebar mode, overlay/device chips live in top bar.
        footer = QWidget(); footer.setObjectName("footerBar")
        fl = QHBoxLayout(footer); fl.setContentsMargins(10, 6, 10, 6)
        self.btn_launch = QPushButton("Launch")
        self.btn_stop = QPushButton("Stop")
        fl.addWidget(self.btn_launch); fl.addWidget(self.btn_stop); fl.addStretch(1)
        # Only create overlay/device chips in footer for tabbed mode
        if self.layout_mode != "sidebar":
            self.chip_overlay = QLabel("Overlay: Idle"); self.chip_overlay.setObjectName("statusChip")
            self.chip_device = QLabel("Device: Off"); self.chip_device.setObjectName("statusChip")
            fl.addWidget(self.chip_overlay); fl.addWidget(self.chip_device)
        self.chip_audio = QLabel("Audio: 0/2"); self.chip_audio.setObjectName("statusChip")
        fl.addWidget(self.chip_audio)
        main.addWidget(footer, 0)

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
        if self.overlays and self.enable_device_sync and self.enable_buzz_on_flash:
            self._wire_shared_flash_timer(shared_start_time)
        if self.enable_device_sync and self.enable_bursts:
            self._start_burst_scheduler()

    def _wire_shared_flash_timer(self, shared_start_time: float):
        """Create a single synchronized flash timer for all overlays to prevent double-speed flashing."""
        self._shared_flash_timer = QTimer(self)
        self._prev_flash_show = False
        def on_shared_tick():
            if not self.overlays:
                return
            first_overlay = self.overlays[0]
            now_ms = int((time.time() - shared_start_time) * 1000.0)
            show = (now_ms % first_overlay.flash_interval_ms) < first_overlay.flash_width_ms
            if self.enable_device_sync and self.enable_buzz_on_flash and show and not self._prev_flash_show:
                ms = first_overlay.flash_width_ms
                lvl = float(clamp(self.buzz_intensity, 0.0, 1.0))
                self.pulse.pulse(lvl, ms)
            self._prev_flash_show = show
        self._shared_flash_timer.timeout.connect(on_shared_tick)
        self._shared_flash_timer.start(15)  # 15ms interval for smooth detection

    def _wire_flash_timer(self, ov: OverlayWindow):
        ov._prev_show = False
        t = QTimer(self)
        def on_tick():
            now_ms = int((time.time()-ov.start_time)*1000.0)
            show = (now_ms % ov.flash_interval_ms) < ov.flash_width_ms
            if self.enable_device_sync and self.enable_buzz_on_flash and show and not getattr(ov, "_prev_show", False):
                ms = ov.flash_width_ms; lvl = float(clamp(self.buzz_intensity, 0.0, 1.0))
                self.pulse.pulse(lvl, ms)
            ov._prev_show = show
        t.timeout.connect(on_tick); t.start(15); ov._flash_sync_timer = t

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
        if not self.running: return
        self.running = False; self._refresh_status()
        if hasattr(self, "_shared_flash_timer") and self._shared_flash_timer:
            self._shared_flash_timer.stop(); self._shared_flash_timer = None
        if hasattr(self, "_burst_timer") and self._burst_timer:
            self._burst_timer.stop(); self._burst_timer = None
        for ov in self.overlays:
            try:
                if hasattr(ov, "_flash_sync_timer"): ov._flash_sync_timer.stop()
                ov.close()
            except Exception: pass
        self.overlays.clear()
        self.audio.stop(); self.pulse.stop()

    def closeEvent(self, event):
        """Handle application close."""
        if self.mesmer_server:
            try:
                import asyncio
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                loop.run_until_complete(self.mesmer_server.shutdown())
                loop.close()
                logging.getLogger(__name__).info("MesmerIntiface server shut down")
            except Exception as e:
                logging.getLogger(__name__).error("Error shutting down MesmerIntiface server: %s", e)
        super().closeEvent(event)
        self.overlays.clear()
        self.audio.stop()
        try: self.pulse.set_level(0.0)
        except Exception: pass
        self.pulse.stop()
