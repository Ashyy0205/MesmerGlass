import os, time, random, threading
from typing import List

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFileDialog, QTabWidget, QGroupBox, QScrollArea, QFrame,
    QListWidget, QListWidgetItem
)

from ..engine.audio import Audio2
from ..engine.pulse import PulseEngine, clamp
from .overlay import OverlayWindow
from .pages.textfx import TextFxPage
from .pages.device import DevicePage
from .pages.audio import AudioPage  # <-- NEW
from .devtools import DevToolsWindow  # <-- Dev Tools


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
        self.enable_device_sync = False
        self.enable_buzz_on_flash = True; self.buzz_intensity = 0.6
        self.enable_bursts = False; self.burst_min_s = 25; self.burst_max_s = 60; self.burst_peak = 0.9; self.burst_max_ms = 2000

        self.overlays: List[OverlayWindow] = []; self.running = False

        self._build_ui()
        self._bind_shortcuts()

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
    def _on_toggle_device_sync(self, b: bool): self.enable_device_sync = b; self._refresh_status()

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

        for i in checked_idx:
            sc = screens[i] if i < len(screens) else screens[0]
            ov = OverlayWindow(sc, self.primary_path or None, self.secondary_path or None,
                               self.primary_op, self.secondary_op, self.text, self.text_color, self.font,
                               self.text_scale_pct, self.flash_interval_ms, self.flash_width_ms,
                               self.fx_mode, self.fx_intensity)
            self._wire_flash_timer(ov); self.overlays.append(ov)

        if self.enable_device_sync and self.enable_bursts:
            self._start_burst_scheduler()

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
        for ov in self.overlays:
            try:
                if hasattr(ov, "_flash_sync_timer"): ov._flash_sync_timer.stop()
                ov.close()
            except Exception: pass
                
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
        super().closeEvent(event)
        self.overlays.clear()
        self.audio.stop()
        try: self.pulse.set_level(0.0)
        except Exception: pass
        self.pulse.stop()
