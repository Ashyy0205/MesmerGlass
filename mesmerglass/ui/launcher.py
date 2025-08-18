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
from .pages.audio import AudioPage  # <-- NEW
from .devtools import DevToolsWindow  # <-- Dev Tools


class ScanCompleteSignaler(QObject):
    """Thread-safe signaler for scan completion."""
    scan_completed = pyqtSignal(object)  # Emits device_list


# ---- tiny helpers used by pages built in this file ----
def _card(title: str) -> QGroupBox:
    box = QGroupBox(title); box.setContentsMargins(0,0,0,0); return box

def _row(label: str, widget: QWidget, trailing: QWidget | None = None) -> QWidget:
    w = QWidget(); 
    from PyQt6.QtWidgets import QHBoxLayout
    h = QHBoxLayout(w); h.setContentsMargins(10,6,10,6); h.setSpacing(10)
    lab = QLabel(label); lab.setMinimumWidth(160)
    h.addWidget(lab, 0); h.addWidget(widget, 1)
    if trailing: h.addWidget(trailing, 0)
    return w

def _pct_label(v: float) -> QLabel:
    lab = QLabel(f"{int(round(v*100))}%")
    lab.setMinimumWidth(48)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lab


class Launcher(QMainWindow):
    def __init__(self, app_title="Mesmer Glass — 0.7.0"):
        super().__init__()
        self.setWindowTitle(app_title)
        
        # Create thread-safe signaler for scan completion
        self.scan_signaler = ScanCompleteSignaler()
        self.scan_signaler.scan_completed.connect(self._update_device_list_ui)
        self.resize(980, 620)

        # ---------- state ----------
        self.primary_path = ""; self.secondary_path = ""
        self.primary_op = 0.10; self.secondary_op = 0.0
        self.dev_mode = False
        self.dev_tools = None  # Will be created when needed

        self.text = "RELAX"; self.text_color = QColor("#FFFFFF"); self.font = QFont("Segoe UI", 64)
        
        # Dev mode shortcut (Ctrl+Shift+D)
        self.dev_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.dev_shortcut.activated.connect(self.toggle_dev_mode)
        self.text_scale_pct = 22; self.fx_mode = "Breath + Sway"; self.fx_intensity = 70
        self.flash_interval_ms = 1500; self.flash_width_ms = 200

        self.audio = Audio2(); self.audio1_path = ""; self.audio2_path = ""; self.vol1 = 0.6; self.vol2 = 0.5

        self.pulse = PulseEngine(quiet=True)
        self.enable_device_sync = True  # Enable device sync by default
        self.enable_buzz_on_flash = True; self.buzz_intensity = 0.6
        self.enable_bursts = False; self.burst_min_s = 25; self.burst_max_s = 60; self.burst_peak = 0.9; self.burst_max_ms = 2000

        # MesmerIntiface server for pure Python device control
        self.mesmer_server = None
        self.device_scan_in_progress = False

        self.overlays: List[OverlayWindow] = []; self.running = False

        self._build_ui()
        self._bind_shortcuts()
        
        # Auto-start MesmerIntiface server if device sync is enabled
        if self.enable_device_sync:
            self._start_mesmer_server()

    # ============================== UI ==============================
    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QVBoxLayout(root); main.setContentsMargins(10,10,10,10); main.setSpacing(10)

        # Tab container
        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)

        # Add pages as tabs
        scroll_media = QScrollArea()
        scroll_media.setWidgetResizable(True)
        scroll_media.setFrameShape(QFrame.Shape.NoFrame)
        scroll_media.setWidget(self._page_media())
        self.tabs.addTab(scroll_media, "Media")

        # Text & FX page
        self.page_textfx = TextFxPage(
            text=self.text, text_scale_pct=self.text_scale_pct, fx_mode=self.fx_mode, fx_intensity=self.fx_intensity,
            flash_interval_ms=self.flash_interval_ms, flash_width_ms=self.flash_width_ms
        )
        scroll_textfx = QScrollArea()
        scroll_textfx.setWidgetResizable(True)
        scroll_textfx.setFrameShape(QFrame.Shape.NoFrame)
        scroll_textfx.setWidget(self.page_textfx)
        self.tabs.addTab(scroll_textfx, "Text & FX")

        # Audio page
        self.page_audio = AudioPage(
            file1=os.path.basename(self.audio1_path),
            file2=os.path.basename(self.audio2_path),
            vol1_pct=int(self.vol1*100),
            vol2_pct=int(self.vol2*100),
        )
        scroll_audio = QScrollArea()
        scroll_audio.setWidgetResizable(True)
        scroll_audio.setFrameShape(QFrame.Shape.NoFrame)
        scroll_audio.setWidget(self.page_audio)
        self.tabs.addTab(scroll_audio, "Audio")

        # Device page
        self.page_device = DevicePage(
            enable_sync=self.enable_device_sync,
            buzz_on_flash=self.enable_buzz_on_flash,
            buzz_intensity_pct=int(self.buzz_intensity*100),
            bursts_enable=self.enable_bursts,
            min_gap_s=self.burst_min_s, max_gap_s=self.burst_max_s,
            peak_pct=int(self.burst_peak*100), max_ms=self.burst_max_ms
        )
        scroll_device = QScrollArea()
        scroll_device.setWidgetResizable(True)
        scroll_device.setFrameShape(QFrame.Shape.NoFrame)
        scroll_device.setWidget(self.page_device)
        self.tabs.addTab(scroll_device, "Device Sync")

        # Displays page
        scroll_displays = QScrollArea()
        scroll_displays.setWidgetResizable(True)
        scroll_displays.setFrameShape(QFrame.Shape.NoFrame)
        scroll_displays.setWidget(self._page_displays())
        self.tabs.addTab(scroll_displays, "Displays")

        # Wire page signals -> state
        self.page_textfx.textChanged.connect(lambda s:setattr(self, "text", s))
        self.page_textfx.fontRequested.connect(self._pick_font)
        self.page_textfx.colorRequested.connect(self._pick_color)
        self.page_textfx.textScaleChanged.connect(lambda v:setattr(self, "text_scale_pct", v))
        self.page_textfx.fxModeChanged.connect(lambda s:setattr(self, "fx_mode", s))
        self.page_textfx.fxIntensityChanged.connect(lambda v:setattr(self, "fx_intensity", v))
        self.page_textfx.flashIntervalChanged.connect(lambda v:setattr(self, "flash_interval_ms", v))
        self.page_textfx.flashWidthChanged.connect(lambda v:setattr(self, "flash_width_ms", v))

        # Audio wiring
        self.page_audio.load1Requested.connect(self._pick_a1)
        self.page_audio.load2Requested.connect(self._pick_a2)
        self.page_audio.vol1Changed.connect(lambda pct: (self._set_vols(pct/100.0, self.vol2)))
        self.page_audio.vol2Changed.connect(lambda pct: (self._set_vols(self.vol1, pct/100.0)))

        # Device wiring
        self.page_device.enableSyncChanged.connect(self._on_toggle_device_sync)
        self.page_device.scanDevicesRequested.connect(self._on_scan_devices)
        self.page_device.deviceSelected.connect(self._on_device_selected)
        self.page_device.buzzOnFlashChanged.connect(lambda b:setattr(self, "enable_buzz_on_flash", b))
        self.page_device.buzzIntensityChanged.connect(lambda v:setattr(self, "buzz_intensity", v/100.0))
        self.page_device.burstsEnableChanged.connect(lambda b:setattr(self, "enable_bursts", b))
        self.page_device.burstMinChanged.connect(lambda v:setattr(self, "burst_min_s", v))
        self.page_device.burstMaxChanged.connect(lambda v:setattr(self, "burst_max_s", v))
        self.page_device.burstPeakChanged.connect(lambda v:setattr(self, "burst_peak", v/100.0))
        self.page_device.burstMaxMsChanged.connect(lambda v:setattr(self, "burst_max_ms", v))

        # Footer
        footer = QWidget(); footer.setObjectName("footerBar")
        fl = QHBoxLayout(footer); fl.setContentsMargins(10, 6, 10, 6)
        self.btn_launch = QPushButton("Launch")
        self.btn_stop = QPushButton("Stop")
        fl.addWidget(self.btn_launch); fl.addWidget(self.btn_stop); fl.addStretch(1)
        self.chip_overlay = QLabel("Overlay: Idle"); self.chip_overlay.setObjectName("statusChip")
        self.chip_device  = QLabel("Device: Off");  self.chip_device.setObjectName("statusChip")
        self.chip_audio   = QLabel("Audio: 0/2");   self.chip_audio.setObjectName("statusChip")
        fl.addWidget(self.chip_overlay); fl.addWidget(self.chip_device); fl.addWidget(self.chip_audio)
        main.addWidget(footer, 0)

        self.btn_launch.clicked.connect(self.launch)
        self.btn_stop.clicked.connect(self.stop_all)
        self._refresh_status()

    # ---------------- Media page (unchanged bubble style) ----------------
    def _page_media(self):
        page = QWidget()
        root = QVBoxLayout(page); root.setContentsMargins(6,6,6,6); root.setSpacing(12)

        # Primary bubble
        card_primary = _card("Primary video")
        pv = QVBoxLayout(card_primary); pv.setContentsMargins(12,8,12,8); pv.setSpacing(4)

        self.lbl_primary = QLabel("(none)")
        btn_pick_primary = QPushButton("Choose file…"); btn_pick_primary.clicked.connect(self._pick_primary)
        pv.addWidget(_row("File", btn_pick_primary, self.lbl_primary))

        self.sld_primary_op = QSlider(Qt.Orientation.Horizontal); self.sld_primary_op.setRange(0,100); self.sld_primary_op.setValue(int(self.primary_op*100))
        self.lab_primary_pct = _pct_label(self.primary_op)
        self.sld_primary_op.valueChanged.connect(lambda x:(setattr(self, "primary_op", x/100.0), self.lab_primary_pct.setText(f"{x}%")))
        pv.addWidget(_row("Opacity", self.sld_primary_op, self.lab_primary_pct))

        root.addWidget(card_primary)

        # Secondary bubble
        card_secondary = _card("Secondary video")
        sv = QVBoxLayout(card_secondary); sv.setContentsMargins(12,8,12,8); sv.setSpacing(4)

        self.lbl_secondary = QLabel("(none)")
        btn_pick_secondary = QPushButton("Choose file…"); btn_pick_secondary.clicked.connect(self._pick_secondary)
        sv.addWidget(_row("File", btn_pick_secondary, self.lbl_secondary))

        self.sld_secondary_op = QSlider(Qt.Orientation.Horizontal); self.sld_secondary_op.setRange(0,100); self.sld_secondary_op.setValue(int(self.secondary_op*100))
        self.lab_secondary_pct = _pct_label(self.secondary_op)
        self.sld_secondary_op.valueChanged.connect(lambda x:(setattr(self, "secondary_op", x/100.0), self.lab_secondary_pct.setText(f"{x}%")))
        sv.addWidget(_row("Opacity", self.sld_secondary_op, self.lab_secondary_pct))

        root.addWidget(card_secondary)
        root.addStretch(1)
        return page

    def _page_displays(self):
        from PyQt6.QtWidgets import QPushButton
        card = _card("Displays"); v = QVBoxLayout(card); v.setContentsMargins(12,10,12,12); v.setSpacing(8)

        self.list_displays = QListWidget()
        for s in QGuiApplication.screens():
            it = QListWidgetItem(f"{s.name()}  {s.geometry().width()}x{s.geometry().height()}"); it.setCheckState(Qt.CheckState.Unchecked)
            self.list_displays.addItem(it)
        v.addWidget(self.list_displays, 1)

        btn_sel_all = QPushButton("Select all")
        btn_sel_pri = QPushButton("Primary only")
        v.addWidget(_row("Quick select", btn_sel_all, btn_sel_pri))
        btn_sel_all.clicked.connect(self._select_all_displays)
        btn_sel_pri.clicked.connect(self._select_primary_display)

        page = QWidget(); root = QVBoxLayout(page); root.addWidget(card); root.addStretch(1)
        return page

    # ========================== helpers / pickers ==========================
    def _bind_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.launch)
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop_all)
        for i in range(1, 6):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda idx=i-1: self.tabs.setCurrentIndex(idx))

    def _select_all_displays(self):
        for i in range(self.list_displays.count()):
            self.list_displays.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_primary_display(self):
        for i in range(self.list_displays.count()):
            self.list_displays.item(i).setCheckState(Qt.CheckState.Unchecked)
        if self.list_displays.count() > 0:
            self.list_displays.item(0).setCheckState(Qt.CheckState.Checked)

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
        font, ok = QFontDialog.getFont(self.font, self, "Pick font")
        if ok: self.font = font

    def _pick_color(self):
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self.text_color, self, "Pick text color")
        if c.isValid(): self.text_color = c

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

    def _set_vols(self, v1, v2): self.vol1, self.vol2 = v1, v2; self.audio.set_vols(v1, v2)
    
    def _start_mesmer_server(self):
        """Start MesmerIntiface server if not already running."""
        if not self.mesmer_server:
            try:
                self.mesmer_server = MesmerIntifaceServer(port=12350)
                self.mesmer_server.start()
                print("🚀 MesmerIntiface server started automatically on port 12350")
                self._refresh_status()
            except Exception as e:
                print(f"❌ Failed to start MesmerIntiface server: {e}")
                self.mesmer_server = None
    
    def _on_toggle_device_sync(self, b: bool): 
        self.enable_device_sync = b
        
        # Initialize or shutdown MesmerIntiface server
        if b and not self.mesmer_server:
            try:
                self.mesmer_server = MesmerIntifaceServer(port=12350)
                self.mesmer_server.start()
                print("🚀 MesmerIntiface server started on port 12350")
            except Exception as e:
                print(f"❌ Failed to start MesmerIntiface server: {e}")
                self.mesmer_server = None
                
        elif not b and self.mesmer_server:
            try:
                # Synchronously shutdown the server
                import asyncio
                loop = None
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, create a new one for shutdown
                        def shutdown_sync():
                            shutdown_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(shutdown_loop)
                            shutdown_loop.run_until_complete(self.mesmer_server.shutdown())
                            shutdown_loop.close()
                        
                        import threading
                        shutdown_thread = threading.Thread(target=shutdown_sync)
                        shutdown_thread.start()
                        shutdown_thread.join(timeout=5.0)  # Wait max 5 seconds
                    else:
                        loop.run_until_complete(self.mesmer_server.shutdown())
                except RuntimeError:
                    # No event loop, create new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.mesmer_server.shutdown())
                    loop.close()
                    
                self.mesmer_server = None
                print("🛑 MesmerIntiface server stopped")
            except Exception as e:
                print(f"❌ Error stopping MesmerIntiface server: {e}")
                
        self._refresh_status()
    
    def _on_scan_devices(self):
        """Handle device scan request."""
        if self.device_scan_in_progress or not self.mesmer_server:
            return
            
        self.device_scan_in_progress = True
        
        # Start scanning in background
        import asyncio
        import threading
        
        def scan_task():
            try:
                # Run async scan
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def do_scan():
                    print("🔍 Starting Bluetooth device scan...")
                    success = await self.mesmer_server.start_real_scanning()
                    if success:
                        # Scan for 8 seconds
                        await asyncio.sleep(8.0)
                        await self.mesmer_server.stop_real_scanning()
                        
                        # Get device list and update UI
                        device_list = self.mesmer_server.get_device_list()
                        
                        # Debug: Print device list info
                        print(f"🔍 Device list contains {len(device_list.devices)} devices:")
                        for i, device in enumerate(device_list.devices):
                            print(f"  {i}: {device.name} (index={device.index})")
                        
                        # Update UI using thread-safe signal
                        print("📡 Emitting scan_completed signal...")
                        self.scan_signaler.scan_completed.emit(device_list)
                        
                        print(f"✅ Scan completed - found {len(device_list.devices)} device(s)")
                    else:
                        print("❌ Failed to start Bluetooth scan")
                        QTimer.singleShot(0, lambda: self._scan_completed(None))
                
                loop.run_until_complete(do_scan())
                loop.close()
                
            except Exception as e:
                print(f"❌ Scan error: {e}")
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._scan_completed(None))
                
        def scan_wrapper():
            try:
                scan_task()
            finally:
                # Ensure scan state is reset even if there's an exception
                self.device_scan_in_progress = False
                
        threading.Thread(target=scan_wrapper, daemon=True).start()
    
    def _update_device_list_ui(self, device_list):
        """Update UI with scan results (called on main thread)."""
        # Always reset scan state first
        self.device_scan_in_progress = False
        
        print(f"🖥️ Updating UI with device list containing {len(device_list.devices)} devices")
        for device in device_list.devices:
            print(f"   - {device.name} (index: {device.index})")
        
        # Update the device page
        self.page_device.update_device_list(device_list)
        print("✅ Called update_device_list on device page")
        
        # Auto-select single device
        if len(device_list.devices) == 1:
            device = device_list.devices[0]
            print(f"🎯 Auto-selecting single device: {device.name} (index {device.index})")
            self._on_device_selected(device.index)
        
        # Also tell pulse engine about devices if sync is enabled
        if self.enable_device_sync and device_list.devices:
            # Update pulse engine's device manager
            for device in device_list.devices:
                self.pulse.device_manager.add_device({
                    "DeviceIndex": device.index,
                    "DeviceName": device.name,
                    "DeviceMessages": device.device_messages
                })
    
    def _scan_completed(self, device_list):
        """Handle scan completion."""
        self.device_scan_in_progress = False
        if device_list:
            self._update_device_list_ui(device_list)
        else:
            # Failed scan - reset button state
            self.page_device.reset_scan_button()
    
    def _on_device_selected(self, device_idx: int):
        """Handle device selection."""
        if not self.mesmer_server:
            return
            
        print(f"🎯 Selecting device with Buttplug index {device_idx}")
        
        # Update pulse engine selection
        if hasattr(self.pulse, 'select_device_by_index'):
            self.pulse.select_device_by_index(device_idx)
        elif hasattr(self.pulse, 'device_manager'):
            self.pulse.device_manager.select_device(device_idx)
            
        # Find the list index for this device
        device_list = self.mesmer_server.get_device_list()
        list_idx = None
        for i, device in enumerate(device_list.devices):
            if device.index == device_idx:
                list_idx = i
                break
                
        if list_idx is not None:
            # Update server device selection using list index
            self.mesmer_server.select_device(list_idx)
            print(f"✅ Selected device at list index {list_idx} (Buttplug index {device_idx})")
            
            # Automatically connect to the selected device
            import threading
            import asyncio
            
            def connect_device():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    async def do_connect():
                        print(f"🔗 Attempting to connect to device {device_idx}...")
                        success = await self.mesmer_server.connect_real_device(device_idx)
                        if success:
                            print(f"✅ Successfully connected to device {device_idx}")
                        else:
                            print(f"❌ Failed to connect to device {device_idx}")
                        return success
                    
                    result = loop.run_until_complete(do_connect())
                    loop.close()
                    
                except Exception as e:
                    print(f"❌ Error connecting to device {device_idx}: {e}")
                    
            # Run connection in background thread
            connect_thread = threading.Thread(target=connect_device, daemon=True)
            connect_thread.start()
            
        else:
            print(f"❌ Could not find device with Buttplug index {device_idx}")
        
        # Get updated device list and refresh UI
        device_list = self.mesmer_server.get_device_list()
        self.page_device.update_device_list(device_list)

    def _refresh_status(self):
        self.chip_overlay.setText(f"Overlay: {'Running' if self.running else 'Idle'}")
        a_count = (1 if self.audio1_path else 0) + (1 if self.audio2_path else 0)
        self.chip_audio.setText(f"Audio: {a_count}/2")
        self.chip_device.setText("Device: On" if self.enable_device_sync else "Device: Off")

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

        # Use a shared start time for all overlays to synchronize flashing
        shared_start_time = time.time()

        for i in checked_idx:
            sc = screens[i] if i < len(screens) else screens[0]
            ov = OverlayWindow(sc, self.primary_path or None, self.secondary_path or None,
                               self.primary_op, self.secondary_op, self.text, self.text_color, self.font,
                               self.text_scale_pct, self.flash_interval_ms, self.flash_width_ms,
                               self.fx_mode, self.fx_intensity)
            # Override the individual start_time with shared one for synchronization
            ov.start_time = shared_start_time
            self.overlays.append(ov)

        # Create a single synchronized flash timer for all overlays
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
                
            # Use the first overlay's settings for timing (they should all be the same)
            first_overlay = self.overlays[0]
            now_ms = int((time.time() - shared_start_time) * 1000.0)
            show = (now_ms % first_overlay.flash_interval_ms) < first_overlay.flash_width_ms
            
            # Only trigger device pulse on flash transition (not continuously)
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
        
        # Stop shared flash timer
        if hasattr(self, "_shared_flash_timer") and self._shared_flash_timer:
            self._shared_flash_timer.stop()
            self._shared_flash_timer = None
            
        # Stop burst timer
        if hasattr(self, "_burst_timer") and self._burst_timer:
            self._burst_timer.stop()
            self._burst_timer = None
            
        for ov in self.overlays:
            try:
                if hasattr(ov, "_flash_sync_timer"): ov._flash_sync_timer.stop()
                ov.close()
            except Exception: pass
            
        # Stop audio and pulse engines
        self.audio.stop()
        self.pulse.stop()
                
    def toggle_dev_mode(self):
        """Toggle development mode with virtual toy support."""
        self.dev_mode = not self.dev_mode
        if self.dev_mode:
            if not self.dev_tools:
                self.dev_tools = DevToolsWindow(self)
            self.dev_tools.show()
        else:
            if self.dev_tools:
                self.dev_tools.close()
                
    def closeEvent(self, event):
        """Handle application close."""
        if self.dev_tools:
            self.dev_tools.close()
            
        # Shutdown MesmerIntiface server
        if self.mesmer_server:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.mesmer_server.shutdown())
                loop.close()
                print("🛑 MesmerIntiface server shut down")
            except Exception as e:
                print(f"❌ Error shutting down MesmerIntiface server: {e}")
                
        super().closeEvent(event)
        self.overlays.clear()
        self.audio.stop()
        try: self.pulse.set_level(0.0)
        except Exception: pass
        self.pulse.stop()
