"""Launcher window (restored baseline).

This file was fully replaced with a previously saved, known-good version
(`launch_pre.py`) after structural corruption in earlier patches. Future
enhancements (menu bar, pack path tracking) will be re-applied as small
incremental diffs on top of this stable baseline.
"""

import os, time, random, threading, time as _time_mod, asyncio, json  # asyncio added for persistent BLE loop
from typing import List, Dict, Any, Optional
from pathlib import Path  # For theme bank initialization

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFileDialog, QTabWidget, QGroupBox, QScrollArea, QFrame,
    QListWidget, QListWidgetItem
)

import time  # needed for spiral evolution timer
from ..engine.audio import Audio2
from ..engine.pulse import PulseEngine, clamp
from mesmerglass.mesmerloom.spiral import SpiralDirector  # spiral parameter director (GL overlay)
try:
    # Visual Programs integration
    from ..mesmerloom.visual_director import VisualDirector
    from ..engine.text_director import TextDirector
    from ..content.text_renderer import TextRenderer
    from ..content.simple_video_streamer import SimpleVideoStreamer
    from ..content.themebank import ThemeBank
except Exception as e:
    logging.getLogger(__name__).warning(f"Visual Programs imports failed: {e}")
    VisualDirector = None  # type: ignore
    TextDirector = None  # type: ignore
    TextRenderer = None  # type: ignore
    SimpleVideoStreamer = None  # type: ignore
    ThemeBank = None  # type: ignore
try:
    # MesmerIntiface optional if bleak is not installed in current environment.
    from ..engine.mesmerintiface import MesmerIntifaceServer  # type: ignore
except Exception:  # pragma: no cover - fallback when bleak missing or import error
    MesmerIntifaceServer = None  # type: ignore
from .overlay import OverlayWindow
from .pages.device import DevicePage
from .pages.audio import AudioPage
from .pages.devtools import DevToolsPage  # DevTools content (now hosted in separate window)
from .pages.performance import PerformancePage  # Performance metrics page
# Visual Programs tab removed - replaced with simple media mode selector in MesmerLoom tab
from .text_tab import TextTab  # Simplified text tab (messages only)
# Note: SpiralPage removed - opacity controls moved to MesmerLoom tab
from .panel_mesmerloom import PanelMesmerLoom
from ..vr.vr_bridge import VrBridge  # VR bridge (OpenXR or mock)
try:
    import logging
    try:
        from ..mesmerloom.compositor import LoomCompositor
        logging.getLogger(__name__).info("[spiral.trace] LoomCompositor import succeeded in launcher.py")
    except Exception as e:
        logging.getLogger(__name__).error(f"[spiral.trace] LoomCompositor import failed in launcher.py: {e}")
        LoomCompositor = None  # type: ignore
    try:
        from .spiral_window import SpiralWindow
        logging.getLogger(__name__).info("[spiral.trace] SpiralWindow import succeeded in launcher.py")
    except Exception as e:
        logging.getLogger(__name__).error(f"[spiral.trace] SpiralWindow import failed in launcher.py: {e}")
        SpiralWindow = None
except Exception:  # pragma: no cover
    LoomCompositor = None  # type: ignore
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
        """Main application launcher / controller window (reconstructed cleanly)."""
        super().__init__()
        self.setWindowTitle(title)
        self.layout_mode = layout_mode if layout_mode in ("tabbed", "sidebar") else "tabbed"

        # Core state -------------------------------------------------
        self.primary_path = ""; self.secondary_path = ""
        self.primary_op = 1.0; self.secondary_op = 0.5
        self.text = ""
        self.text_color = QColor("white"); self.text_font = QFont("Segoe UI", 28)
        self.text_scale_pct = 100; self.fx_mode = "Breath + Sway"; self.fx_intensity = 50
        self.flash_interval_ms = 1200; self.flash_width_ms = 250
        self.audio1_path = ""; self.audio2_path = ""; self.vol1 = 0.5; self.vol2 = 0.5
        self.enable_device_sync = bool(enable_device_sync_default)
        # Env override to fully disable the PulseEngine/device sync for stability (e.g. VR-only sessions)
        try:
            import os as _os
            if _os.environ.get("MESMERGLASS_NO_PULSE", "0") in ("1", "true", "True", "yes"):
                self.enable_device_sync = False
                logging.getLogger(__name__).info("[device] MESMERGLASS_NO_PULSE=1 -> device sync disabled")
        except Exception:
            pass
        self.enable_buzz_on_flash = True; self.buzz_intensity = 0.6
        self.enable_bursts = False; self.burst_min_s = 30; self.burst_max_s = 120; self.burst_peak = 0.9; self.burst_max_ms = 1200
        self.overlays = []  # list of OverlayWindow instances

        # Media cycling (simple random cycler replacing Visual Programs)
        self.media_mode = 1  # 0=images&videos, 1=images only, 2=video focus (default: Images Only)
        self.image_duration_sec = 5  # Default 5 seconds per image
        self.video_duration_sec = 30  # Default 30 seconds per video

        # Spiral (phase 1 logic only + MesmerLoom compositor wiring)
        self.spiral_enabled = False
        self.spiral_director = SpiralDirector()
        self._spiral_timer = None  # legacy alias (not used here)
        self.spiral_timer = QTimer(self)
        self.spiral_timer.setInterval(33)
        self.spiral_opacity = 0.5
        try:
            if hasattr(self.spiral_director, 'cfg'):
                self.spiral_opacity = getattr(self.spiral_director.cfg, 'opacity', 0.5)
            elif hasattr(self.spiral_director, 'state'):
                self.spiral_opacity = getattr(self.spiral_director.state, 'opacity', 0.5)
        except Exception:
            pass
        self.running = False
        
        # VR streaming integration (using MesmerVisor streaming server)
        from ..mesmervisor.streaming_server import VRStreamingServer, DiscoveryService
        from ..mesmervisor.gpu_utils import EncoderType
        self.vr_streaming_server = None  # Will be created on-demand when VR client selected
        self.vr_clients = []  # List of discovered VR clients (from discovery service)
        self._vr_streaming_active = False
        
        # Start discovery service immediately to find VR devices
        # (streaming server created later on-demand)
        self.vr_discovery_service = DiscoveryService(
            discovery_port=5556, 
            streaming_port=5555
        )
        self.vr_discovery_service.start()
        
        # Auto-refresh VR clients list every 2 seconds
        self._vr_refresh_timer = QTimer(self)
        self._vr_refresh_timer.setInterval(2000)
        self._vr_refresh_timer.timeout.connect(self._refresh_vr_displays)
        self._vr_refresh_timer.start()
        
        # Also do an initial refresh after 1 second to catch early discoveries
        QTimer.singleShot(1000, self._refresh_vr_displays)
        # MesmerLoom compositor (may be None / unavailable headless)
        self.compositor = None
        try:
            # Try QOpenGLWindow compositor first (artifact-free)
            try:
                from ..mesmerloom.window_compositor import LoomWindowCompositor
                self.compositor = LoomWindowCompositor(self.spiral_director)
                logging.getLogger(__name__).info("[spiral.trace] LoomWindowCompositor created successfully (artifact-free)")
            except ImportError:
                # Fallback to QOpenGLWidget compositor (has FBO artifacts)
                if LoomCompositor is not None:
                    self.compositor = LoomCompositor(self.spiral_director, parent=self)
                    logging.getLogger(__name__).info("[spiral.trace] LoomCompositor fallback created (has FBO artifacts)")
                    
            if self.compositor:
                self.compositor.set_active(False)
        except Exception:
            self.compositor = None
        
        # Visual Programs integration (theme bank, text renderer, video streamer, director)
        self.theme_bank = None
        self.text_renderer = None
        self.video_streamer = None
        self.visual_director = None
        self.text_director = None  # Independent text control system
        
        # Media Bank: Global list of all available media directories
        # Each mode selects which bank entries to use (stored as indices in mode JSON)
        # Starts empty - user must add directories via MesmerLoom tab
        self._media_bank: List[Dict[str, Any]] = []
        
        # Load saved Media Bank from config file if it exists
        self._load_media_bank_config()
        # Allow disabling all media/text/video subsystems for VR-minimal stability
        self._no_media = False
        try:
            _env = os.environ
            self._no_media = (
                _env.get("MESMERGLASS_NO_MEDIA", "0") in ("1", "true", "True", "yes")
                or _env.get("MESMERGLASS_VR_MINIMAL", "0") in ("1", "true", "True", "yes")
            )
            if self._no_media:
                logging.getLogger(__name__).info("[media] NO_MEDIA=1/VR_MINIMAL=1 -> skipping ThemeBank/Text/Video initialization")
        except Exception:
            self._no_media = False
        try:
            if not self._no_media and ThemeBank is not None:
                # Initialize theme bank with test media for demonstration
                from ..content.theme import ThemeConfig
                
                # Get test media directory
                media_dir = Path(__file__).parent.parent.parent / "MEDIA"
                
                # Check if MediaBank has enabled entries - if so, use those instead of test theme
                enabled_bank_entries = [i for i, entry in enumerate(self._media_bank) 
                                       if entry.get('enabled', True)]
                
                if enabled_bank_entries:
                    # Use MediaBank entries to build theme
                    logging.getLogger(__name__).info(
                        f"[visual] Found {len(enabled_bank_entries)} enabled MediaBank entries - "
                        f"rebuilding theme from bank"
                    )
                    self._rebuild_media_library_from_selections(enabled_bank_entries, silent=True)
                else:
                    # No MediaBank entries - create test theme with sample content
                    logging.getLogger(__name__).info("[visual] No MediaBank entries - using default MEDIA folder")
                    
                    test_images = []
                    test_videos = []
                    test_text = [
                        "Welcome to MesmerGlass",
                        "Trance Visual Programs",
                        "Relax and Focus",
                        "Let Go",
                        "Deep and Deeper",
                        "Spiral Down",
                        "Good Subject",
                        "Obey and Enjoy"
                    ]
                    
                    # Scan for test images if MEDIA directory exists
                    if media_dir.exists():
                        images_dir = media_dir / "Images"
                        videos_dir = media_dir / "Videos"
                        
                        if images_dir.exists():
                            # Collect image paths (relative to media_dir)
                            for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                                for img_path in images_dir.glob(ext):
                                    test_images.append(str(img_path.relative_to(media_dir)))
                        
                        if videos_dir.exists():
                            # Collect video paths (relative to media_dir)
                            for ext in ['*.mp4', '*.webm', '*.mkv', '*.avi']:
                                for vid_path in videos_dir.glob(ext):
                                    test_videos.append(str(vid_path.relative_to(media_dir)))
                    
                    # Create theme config
                    default_theme = ThemeConfig(
                        name="Test Theme",
                        enabled=True,
                        image_path=test_images,  # Correct field name
                        animation_path=test_videos,  # Correct field name
                        font_path=[],
                        text_line=test_text  # Correct field name
                    )
                    
                    self.theme_bank = ThemeBank(
                        themes=[default_theme],
                        root_path=media_dir if media_dir.exists() else Path.cwd(),
                        image_cache_size=64
                    )
                    
                    # Activate the theme (set as primary)
                    if len(self.theme_bank._themes) > 0:
                        self.theme_bank.set_active_themes(primary_index=1)  # 1-indexed
                    
                    img_count = len(test_images)
                    vid_count = len(test_videos)
                    txt_count = len(test_text)
                    logging.getLogger(__name__).info(
                        f"[visual] ThemeBank initialized with test theme: "
                        f"{img_count} images, {vid_count} videos, {txt_count} text lines"
                    )
            if not self._no_media and TextRenderer is not None:
                # Initialize text renderer
                self.text_renderer = TextRenderer()
                logging.getLogger(__name__).info("[visual] TextRenderer initialized")
            
            if not self._no_media and SimpleVideoStreamer is not None:
                # Initialize video streamer (forward-only mode, no ping-pong)
                self.video_streamer = SimpleVideoStreamer(buffer_size=120)
                logging.getLogger(__name__).info("[visual] SimpleVideoStreamer initialized (forward-only)")
            
            if not self._no_media and TextDirector is not None and self.text_renderer and self.compositor:
                # Initialize text director FIRST (text library manager)
                self.text_director = TextDirector(
                    text_renderer=self.text_renderer,
                    compositor=self.compositor
                )
                logging.getLogger(__name__).info("[text] TextDirector initialized (text library manager)")
            
            if not self._no_media and VisualDirector is not None and self.theme_bank and self.compositor:
                # Initialize visual director (with text_director for text selection)
                self.visual_director = VisualDirector(
                    theme_bank=self.theme_bank,
                    compositor=self.compositor,
                    text_renderer=self.text_renderer,
                    video_streamer=self.video_streamer,
                    text_director=self.text_director  # Visual Programs request texts from here
                )
                logging.getLogger(__name__).info("[visual] VisualDirector initialized (with text_director integration)")
        except Exception as e:
            logging.getLogger(__name__).error(f"[visual] Visual Programs initialization failed: {e}")
            import traceback
            traceback.print_exc()
        
        # Runtime spiral windows (one per selected display)
        self.spiral_windows = []
        # VR bridge plumbing
        self.vr_bridge = None
        self._vr_comp = None  # currently connected compositor for VR frames

        # Auto diagnostic spiral enable/launch (no UI click) if env set
        try:
            if os.environ.get("MESMERGLASS_SPIRAL_AUTO") == '1':
                # Defer until event loop starts to avoid premature screen queries
                from PyQt6.QtCore import QTimer as _QT
                def _auto_start():
                    try:
                        if not self.spiral_enabled:
                            self._on_spiral_toggled(True)
                        # Ensure at least first display checked
                        if self.list_displays.count()>0 and all(self.list_displays.item(i).checkState()!=Qt.CheckState.Checked for i in range(self.list_displays.count())):
                            self.list_displays.item(0).setCheckState(Qt.CheckState.Checked)
                        self.launch()
                    except Exception as e:
                        logging.getLogger(__name__).error("Auto spiral launch failed: %s", e)
                _QT.singleShot(250, _auto_start)
        except Exception:
            pass

        # Engines ----------------------------------------------------
        self.audio = Audio2()
        self.pulse = PulseEngine(use_mesmer=True, allow_auto_select=False)
        self.mesmer_server = None
        self._mesmer_device_cb = None
        self.device_scan_in_progress = False
        self.scan_signaler = ScanCompleteSignaler()
        self.scan_signaler.scan_completed.connect(self._scan_completed)
        self._shutting_down = False

        # Persistent BLE loop ---------------------------------------
        # Allow disabling the dedicated BLE asyncio loop via env to avoid
        # interactions with Windows WinRT/BLE in VR-only scenarios.
        self._ble_loop = None
        self._ble_loop_alive = False
        try:
            import os as _os
            _disable_ble_loop = _os.environ.get("MESMERGLASS_NO_BLE_LOOP", "0") in ("1", "true", "True", "yes") or bool(_os.environ.get("MESMERGLASS_NO_SERVER"))
        except Exception:
            _disable_ble_loop = False
        if not _disable_ble_loop:
            self._ble_loop = asyncio.new_event_loop()
            self._ble_loop_alive = True
            def _ble_loop_runner():
                asyncio.set_event_loop(self._ble_loop)
                try:
                    self._ble_loop.run_forever()
                except Exception as e:  # pragma: no cover
                    logging.getLogger(__name__).error("BLE loop crash: %s", e)
                finally:
                    try:
                        self._ble_loop.close()
                    except Exception:
                        pass
            self._ble_loop_thread = threading.Thread(target=_ble_loop_runner, name="BLELoop", daemon=True)
            self._ble_loop_thread.start()
        else:
            logging.getLogger(__name__).info("[device] BLE loop disabled via env (MESMERGLASS_NO_BLE_LOOP or MESMERGLASS_NO_SERVER)")

        # Environment flags -----------------------------------------
        self._suppress_server = bool(os.environ.get("MESMERGLASS_NO_SERVER"))
        sim_flag = os.environ.get("MESMERGLASS_GL_SIMULATE") == "1"
        force_flag = os.environ.get("MESMERGLASS_GL_FORCE") == "1"
        test_or_ci = bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI"))
        self._gl_simulation = bool(sim_flag and not force_flag and test_or_ci)
        try:
            logging.getLogger(__name__).info(
                "Launcher env: MESMERGLASS_GL_SIMULATE=%r MESMERGLASS_GL_FORCE=%r test_or_ci=%s _gl_simulation=%s", os.environ.get("MESMERGLASS_GL_SIMULATE"), os.environ.get("MESMERGLASS_GL_FORCE"), test_or_ci, self._gl_simulation
            )
        except Exception:
            pass
        # VR flags
        try:
            self._vr_enabled = (os.environ.get("MESMERGLASS_VR") == '1')
            self._vr_force_mock = (os.environ.get("MESMERGLASS_VR_MOCK") == '1')
            if self._vr_enabled:
                self._init_vr_bridge()
        except Exception:
            self._vr_enabled = False
            self._vr_force_mock = False
        # Strict mode enforcement (force EXACT adherence to mode timing)
        try:
            self._strict_mode = (os.environ.get("MESMERGLASS_STRICT_MODE") == '1')
            logging.getLogger(__name__).info("[mode] Strict mode: %s", self._strict_mode)
        except Exception:
            self._strict_mode = False

        # UI / services ----------------------------------------------
        self._build_ui()
        self._install_menu_bar()
        self._bind_shortcuts()
        if not self._suppress_server:
            self._start_mesmer_server()

        # Session / font placeholders --------------------------------
        self.session_pack = None
        self.current_pack_path = None
        self.current_font_path = None

    # ========================== UI build ==========================
    def _build_ui(self):
        """Build primary UI (tabs or sidebar) with footer + status chips.

        Rewritten to correct prior indentation corruption. Keep logic minimal
        and defer heavy/optional wiring inside try/except so headless tests pass.
        """
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(10)

        self.tabs = QTabWidget()

        # === CONTROL TABS ===

        # Media tab removed (redundant; media is controlled by mode JSON via VisualDirector)
        # Intentionally no-op: keep legacy fields/state for session state compatibility.

        # Text tab (simplified - messages only)
        try:
            self.page_text = TextTab(text_director=getattr(self, 'text_director', None))
            scr_txt = QScrollArea(); scr_txt.setWidgetResizable(True); scr_txt.setFrameShape(QFrame.Shape.NoFrame)
            scr_txt.setWidget(self.page_text)
            idx_text = self.tabs.addTab(scr_txt, "📝 Text")
            try: self.tabs.setTabToolTip(idx_text, "Text message library (add/edit/remove messages)")
            except Exception: pass
        except Exception as e:
            logging.getLogger(__name__).error(f"Text tab creation failed: {e}", exc_info=True)
            self.page_text = None  # type: ignore

        # MesmerLoom tab (Spiral controls)
        try:
            self.page_mesmerloom = PanelMesmerLoom(self.spiral_director, self.compositor, self)
            scr_ml = QScrollArea(); scr_ml.setWidgetResizable(True); scr_ml.setFrameShape(QFrame.Shape.NoFrame)
            scr_ml.setWidget(self.page_mesmerloom)
            idx_ml = self.tabs.addTab(scr_ml, "🌀 MesmerLoom")
            try: self.tabs.setTabToolTip(idx_ml, "Spiral overlay controls - intensity, colors, type, width")
            except Exception: pass
        except Exception:
            self.page_mesmerloom = None  # type: ignore

        # Audio tab
        self.page_audio = AudioPage(
            file1=os.path.basename(self.audio1_path),
            file2=os.path.basename(self.audio2_path),
            vol1_pct=int(self.vol1 * 100),
            vol2_pct=int(self.vol2 * 100),
        )
        scr_audio = QScrollArea(); scr_audio.setWidgetResizable(True); scr_audio.setFrameShape(QFrame.Shape.NoFrame)
        scr_audio.setWidget(self.page_audio)
        idx_audio = self.tabs.addTab(scr_audio, "🎵 Audio")
        try: self.tabs.setTabToolTip(idx_audio, "Background music and audio tracks")
        except Exception: pass

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
        scr_dev = QScrollArea(); scr_dev.setWidgetResizable(True); scr_dev.setFrameShape(QFrame.Shape.NoFrame)
        scr_dev.setWidget(self.page_device)
        idx_dev = self.tabs.addTab(scr_dev, "🔗 Device Sync")
        try: self.tabs.setTabToolTip(idx_dev, "Haptic device synchronization (Buttplug.io)")
        except Exception: pass

        # Displays tab
        scr_disp = QScrollArea(); scr_disp.setWidgetResizable(True); scr_disp.setFrameShape(QFrame.Shape.NoFrame)
        scr_disp.setWidget(self._page_displays())
        idx_disp = self.tabs.addTab(scr_disp, "🖥️ Displays")
        try: self.tabs.setTabToolTip(idx_disp, "Select which monitors show the overlay")
        except Exception: pass

        if self.layout_mode == 'sidebar':
            # Simple sidebar nav replicating prior behavior
            top = QWidget(); top.setObjectName('topBar')
            tl = QHBoxLayout(top); tl.setContentsMargins(12,8,12,8); tl.setSpacing(8)
            lab_title = QLabel('MesmerGlass'); lab_title.setObjectName('topTitle')
            tl.addWidget(lab_title,0); tl.addStretch(1)
            self.chip_overlay = QLabel('Overlay: Idle'); self.chip_overlay.setObjectName('statusChip')
            self.chip_device = QLabel('Device: Off'); self.chip_device.setObjectName('statusChip')
            tl.addWidget(self.chip_overlay); tl.addWidget(self.chip_device)
            main.addWidget(top,0)
            center = QWidget(); ch = QHBoxLayout(center); ch.setContentsMargins(0,0,0,0); ch.setSpacing(10)
            self.nav = QListWidget(); self.nav.setObjectName('sideNav')
            # Simplified tab list (Visual Programs tab removed in Phase 2)
            for name in (" MesmerLoom", "🎵 Audio", "🔗 Device Sync", "🖥️ Displays"):
                self.nav.addItem(name)
            self.nav.setCurrentRow(0)  # Start on MesmerLoom
            try: self.tabs.tabBar().setVisible(False)
            except Exception: pass
            ch.addWidget(self.nav,0); ch.addWidget(self.tabs,1); main.addWidget(center,1)
            self.nav.currentRowChanged.connect(lambda i: 0 <= i < self.tabs.count() and self.tabs.setCurrentIndex(i))
            self.tabs.currentChanged.connect(lambda i: self.nav.setCurrentRow(i))
        else:
            try: self.tabs.tabBar().setVisible(True)
            except Exception: pass
            main.addWidget(self.tabs,1)

        # Signal wiring ------------------------------------------------
        # Text tab (simplified - no signals needed for message library)
        try:
            if hasattr(self, 'page_text') and self.page_text:
                # TextTab manages its own text_director, no external signals needed
                pass
        except Exception: pass
        # Audio
        try:
            self.page_audio.load1Requested.connect(self._pick_a1)
            self.page_audio.load2Requested.connect(self._pick_a2)
            self.page_audio.vol1Changed.connect(lambda pct: self._set_vols(pct/100.0, self.vol2))
            self.page_audio.vol2Changed.connect(lambda pct: self._set_vols(self.vol1, pct/100.0))
        except Exception: pass
        # Device
        try:
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
        except Exception: pass

        # Footer -------------------------------------------------------
        footer = QWidget(); footer.setObjectName('footerBar')
        fl = QHBoxLayout(footer); fl.setContentsMargins(10,6,10,6)
        self.btn_launch = QPushButton('Launch'); self.btn_stop = QPushButton('Stop')
        fl.addWidget(self.btn_launch); fl.addWidget(self.btn_stop); fl.addStretch(1)
        if self.layout_mode != 'sidebar':
            self.chip_overlay = QLabel('Overlay: Idle'); self.chip_overlay.setObjectName('statusChip')
            self.chip_device = QLabel('Device: Off'); self.chip_device.setObjectName('statusChip')
            fl.addWidget(self.chip_overlay); fl.addWidget(self.chip_device)
        self.chip_audio = QLabel('Audio: 0/2'); self.chip_audio.setObjectName('statusChip'); fl.addWidget(self.chip_audio)
        self.chip_spiral = QLabel('Spiral: Off'); self.chip_spiral.setObjectName('statusChip'); fl.addWidget(self.chip_spiral)
        main.addWidget(footer,0)
        self.btn_launch.clicked.connect(self.launch)
        self.btn_stop.clicked.connect(self.stop_all)
        self._refresh_status()
        
        # Setup keyboard shortcuts
        self._setup_shortcuts()
        # Start a lightweight frame tick so spiral rotation and visuals advance
        # consistently at ~60 FPS even without the legacy SpiralPage toggle.
        try:
            self._mode_tick = QTimer(self)
            self._mode_tick.setInterval(16)
            # Avoid duplicate connections in case of re-init
            try:
                self._mode_tick.timeout.disconnect()  # type: ignore[arg-type]
            except Exception:
                pass
            self._mode_tick.timeout.connect(self._tick_visuals)
            if not self._mode_tick.isActive():
                self._mode_tick.start()
        except Exception as e:
            logging.getLogger(__name__).warning(f"[visual] Could not start mode tick: {e}")

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts for launcher actions."""
        from PyQt6.QtGui import QShortcut, QKeySequence
        from PyQt6.QtCore import Qt
        
        # Ctrl+R: Reload custom mode
        reload_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        reload_shortcut.activated.connect(self._on_reload_custom_mode)
        logging.getLogger(__name__).info("[launcher] Keyboard shortcut registered: Ctrl+R = Reload Custom Mode")

    # ==========================
    # Mode / visuals integration
    # ==========================
    def _tick_visuals(self):
        """Advance spiral rotation and current visual once per frame.

        Keeps Launcher visuals in lockstep with VMC by using the MesmerLoom
        SpiralDirector RPM-based rotation and a fixed 60 FPS dt.
        """
        try:
            if hasattr(self, 'spiral_director') and self.spiral_director:
                # Amount parameter is ignored in RPM mode; retained for compatibility
                self.spiral_director.rotate_spiral(0.0)
                self.spiral_director.update(1/60.0)
        except Exception as e:
            logging.getLogger(__name__).debug(f"[visual] spiral tick error: {e}")

        try:
            if hasattr(self, 'visual_director') and self.visual_director:
                self.visual_director.update(dt=1/60.0)
        except Exception as e:
            logging.getLogger(__name__).debug(f"[visual] director update error: {e}")

        try:
            if self.compositor:
                if hasattr(self.compositor, 'update_zoom_animation'):
                    self.compositor.update_zoom_animation()
                self.compositor.update()
        except Exception:
            pass

    def _on_custom_mode_requested(self, mode_path: str) -> None:
        """Load a custom visual mode JSON and apply its settings.

        Called by PanelMesmerLoom when the user selects a mode; this wires through
        VisualDirector → CustomVisual so spiral/media/text/zoom are applied.
        """
        try:
            from pathlib import Path as _Path
            p = _Path(mode_path)
            if not p.exists():
                logging.getLogger(__name__).error(f"[visual] Mode not found: {p}")
                return
            if not self.visual_director:
                logging.getLogger(__name__).error("[visual] VisualDirector not initialized")
                return
            ok = self.visual_director.select_custom_visual(p)
            if not ok:
                logging.getLogger(__name__).error(f"[visual] Failed to load mode: {p}")
                return
            cv = getattr(self.visual_director, 'current_visual', None)
            # If strict mode is enabled, instruct the visual to disable its internal cycler.
            try:
                if self._strict_mode and cv and hasattr(cv, 'set_strict_mode'):
                    cv.set_strict_mode(True)
                    logging.getLogger(__name__).info("[mode] Enabled strict mode on CustomVisual")
            except Exception:
                pass
            if cv and hasattr(cv, 'reapply_all_settings'):
                try:
                    cv.reapply_all_settings()
                except Exception:
                    pass
            logging.getLogger(__name__).info(f"[visual] Custom mode loaded: {p.name}")
        except Exception as e:
            logging.getLogger(__name__).error(f"[visual] Mode load error: {e}")

    # ---------------- Spiral logic (Phase 1.1 stub) ----------------
    def _on_spiral_toggled(self, enabled: bool):  # connected by SpiralPage
        self.spiral_enabled = bool(enabled)
        try:
            logging.getLogger(__name__).info(
                "Spiral toggled -> enabled=%s running=%s sim=%s", self.spiral_enabled, self.running, getattr(self,'_gl_simulation', None)
            )
        except Exception: pass
        # Lazily create timer
        if self.spiral_enabled:
            if self.spiral_timer is None:
                self.spiral_timer = QTimer(self)
                self.spiral_timer.setInterval(16)  # ~60 FPS logic tick (matches VMC)
                # Guard against duplicate connection
                try:
                    self.spiral_timer.timeout.disconnect()  # type: ignore[arg-type]
                except Exception:
                    pass
                self.spiral_timer.timeout.connect(self._on_spiral_tick)
            if not self.spiral_timer.isActive():
                self.spiral_timer.start()
        else:
            if self.spiral_timer and self.spiral_timer.isActive():
                self.spiral_timer.stop()
        # Compositor activation gate
        try:
            if self.compositor and getattr(self.compositor, 'available', True):
                self.compositor.set_active(self.spiral_enabled)
        except Exception:
            pass
        # Status chip update
        if hasattr(self, 'chip_spiral'):
            try:
                self.chip_spiral.setText('Spiral: On' if self.spiral_enabled else 'Spiral: Off')
                self.chip_spiral.setStyleSheet('background:#2d5; color:#000; padding:2px 6px; border-radius:4px;' if self.spiral_enabled else 'background:#555; color:#ddd; padding:2px 6px; border-radius:4px;')
            except Exception:
                pass
        # Refresh global status if it reflects spiral (future extension)
        try: self._refresh_status()
        except Exception: pass
        # If user toggles spiral while overlays already running, create or
        # destroy spiral windows immediately so feedback is instant.
        try:
            if self.running:
                if self.spiral_enabled:
                    # In simulation mode we don't attempt real GL windows
                    if self._gl_simulation:
                        if hasattr(self, 'chip_spiral'):
                            try:
                                self.chip_spiral.setText('Spiral: Sim')
                                self.chip_spiral.setToolTip('GL simulation mode active – no real spiral rendering')
                            except Exception: pass
                    else:
                        self._create_spiral_windows()
                else:
                    self._destroy_spiral_windows()
        except Exception:
            pass

    def _on_spiral_tick(self):  # placeholder: evolve parameters only
        # Debug: Log first 3 calls to verify this method is being invoked
        if not hasattr(self, '_tick_count'):
            self._tick_count = 0
        self._tick_count += 1
        if self._tick_count <= 3:
            logging.getLogger(__name__).info(f"[spiral_tick] Tick #{self._tick_count}: spiral_enabled={self.spiral_enabled}")
        
        if not self.spiral_enabled:
            if self._tick_count <= 3:
                logging.getLogger(__name__).info(f"[spiral_tick] EARLY RETURN: spiral_enabled=False")
            return
        try:
            # Debug: Log first 3 ticks to verify this method is being called
            if self._tick_count <= 3:
                logging.getLogger(__name__).info(f"[spiral_tick] Tick #{self._tick_count}: using standard rotation method")
            
            # Use standard spiral rotation - the method now handles RPM calculation internally  
            self.spiral_director.rotate_spiral(4.0)  # amount is ignored in new RPM mode
            
            # Deterministic dt for tests (60 FPS matches VMC)
            self.spiral_director.update(1/60.0)
            
            # Debug: Log rotation speed to verify it's using correct RPM
            if self._tick_count <= 3:
                current_rpm = self.spiral_director.rotation_speed
                phase_acc = getattr(self.spiral_director, '_phase_accumulator', 'NO_ATTR')
                state_phase = getattr(self.spiral_director.state, 'phase', 'NO_ATTR')
                logging.getLogger(__name__).info(f"[spiral_tick] RPM={current_rpm}, _phase_accumulator={phase_acc}, state.phase={state_phase}")
            
            uniforms = self.spiral_director.export_uniforms() if hasattr(self.spiral_director, 'export_uniforms') else getattr(self.spiral_director, 'uniforms', lambda: {})()
            
            # Add rotation debug output for speed measurement (every 4th tick to match VMC frequency)
            if self._tick_count % 4 == 0:
                print(f"[Launcher rotation_debug] phase={uniforms.get('uPhase', 0):.6f}")
                print(f"[Launcher rotation_debug] time={uniforms.get('time', 0):.6f}")
                print(f"[Launcher rotation_debug] rotation_speed={uniforms.get('rotation_speed', 0)}")
                print(f"[Launcher rotation_debug] uEffectiveSpeed={uniforms.get('uEffectiveSpeed', 0)}")
                print(f"[Launcher rotation_debug] uBaseSpeed={uniforms.get('uBaseSpeed', 0)}")
                print(f"[Launcher rotation_debug] uIntensity={uniforms.get('uIntensity', 0)}")
                
                # Add zoom debug output
                current_zoom = uniforms.get('zoom_level', 1.0)
                expected_zoom_rate = 0.05 * uniforms.get('rotation_speed', 0)
                print(f"[Launcher zoom_debug] zoom_level={current_zoom:.6f}")
                print(f"[Launcher zoom_debug] expected_zoom_rate={expected_zoom_rate:.6f}")
                print(f"[Launcher zoom_debug] zoom_rate={uniforms.get('zoom_rate', 0):.6f}")
            
            # CRITICAL: Cache uniforms to prevent compositor from calling director.update() again
            # This ensures spiral rotation happens exactly once per tick at the correct rate
            if hasattr(self, 'spiral_windows') and self.spiral_windows:
                for win in self.spiral_windows:
                    if hasattr(win, 'comp') and hasattr(win.comp, '_uniforms_cache'):
                        win.comp._uniforms_cache = uniforms.copy()
                        if self._tick_count <= 3:
                            logging.getLogger(__name__).info(f"[spiral_tick] Cached uniforms to compositor (time={uniforms.get('time', 'N/A')})")
            
            # Update visual director if running (this advances the visual's cycler)
            if self.visual_director and self.visual_director.current_visual:
                try:
                    self.visual_director.update(dt=1/60.0)
                    
                    # NOTE: Built-in visual restart removed in Phase 3
                    # Custom modes handle their own looping/completion internally
                    # Check if visual completed and restart for continuous playback (once per completion)
                    # is_complete = self.visual_director.is_complete()
                    # if is_complete:
                    #     # Custom modes loop internally, no restart needed
                    pass
                    if False:  # Disabled - built-in visuals removed
                        # Use a flag to prevent restarting multiple times per completion
                        restarting = getattr(self, '_visual_restarting', False)
                        if not restarting:
                            self._visual_restarting = True
                            # current_index = self.visual_director.current_visual_index  # Removed in Phase 3
                            # logging.getLogger(__name__).info(f"[visual] Visual program completed (index={current_index}), restarting for continuous playback")
                            # if current_index is not None:
                            #     success = self.visual_director.select_visual(current_index)  # Method removed
                            #     logging.getLogger(__name__).info(f"[visual] Restart result: {success}")
                            self._visual_restarting = False
                        else:
                            # Debugging: log that we're skipping restart due to flag
                            if self.visual_director.get_frame_count() % 60 == 0:
                                logging.getLogger(__name__).debug(f"[visual] Complete but skipping restart (flag={restarting})")
                    else:
                        # Clear restart flag when visual is running normally
                        self._visual_restarting = False
                except Exception as e:
                    logging.getLogger(__name__).error(f"[visual] Update error: {e}", exc_info=True)
            elif getattr(self, '_visual_debug_logged', 0) < 3:
                # Debug: Log why visual director isn't updating (max 3 times)
                self._visual_debug_logged = getattr(self, '_visual_debug_logged', 0) + 1
                logging.getLogger(__name__).warning(
                    f"[visual] Not updating: visual_director={self.visual_director is not None} "
                    f"current_visual={getattr(self.visual_director, 'current_visual', None) is not None if self.visual_director else 'N/A'}"
                )
            
            if self.compositor and getattr(self.compositor, 'available', True):
                # Send uniforms if compositor supports it
                try:
                    if hasattr(self.compositor, 'set_uniforms_from_director'):
                        self.compositor.set_uniforms_from_director(uniforms)
                except Exception:
                    pass
                # Request draw/update independently so tests see an update() call even if uniform method is absent
                try:
                    if hasattr(self.compositor, 'request_draw'):
                        self.compositor.request_draw()
                except Exception:
                    pass
                try:
                    if hasattr(self.compositor, 'update'):
                        self.compositor.update()
                except Exception:
                    pass
            # Broadcast to any active runtime spiral windows
            for win in list(getattr(self, 'spiral_windows', [])):
                try:
                    if getattr(win, 'available', True) and getattr(win, 'set_uniforms_from_director', None):
                        win.set_uniforms_from_director(uniforms)
                        if hasattr(win, 'request_draw'):
                            win.request_draw()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_window_opacity_changed(self, opacity: float):
        """Update window-level opacity for all spiral windows"""
        try:
            # Prevent UI slider from overriding custom mode's opacity control
            if self.visual_director and self.visual_director.is_custom_mode_active():
                logging.getLogger(__name__).info(f"[CustomVisual] Ignoring window opacity change (custom mode has direct JSON control)")
                return
            
            logging.getLogger(__name__).info(f"[spiral.trace] _on_window_opacity_changed called with opacity={opacity}")
            logging.getLogger(__name__).info(f"[spiral.trace] Setting window opacity to {opacity} on {len(getattr(self, 'spiral_windows', []))} windows")
            for win in list(getattr(self, 'spiral_windows', [])):
                try:
                    # Main GL overlay (QOpenGLWindow compositor):
                    if hasattr(win, 'comp') and hasattr(win.comp, 'setWindowOpacity'):
                        logging.getLogger(__name__).info(f"[spiral.trace] Calling setWindowOpacity({opacity}) on window {win}")
                        win.comp.setWindowOpacity(opacity)
                    # Duplicate QWidget mirror window:
                    elif hasattr(win, 'set_overlay_opacity'):
                        win.set_overlay_opacity(opacity)
                    else:
                        logging.getLogger(__name__).warning(f"[spiral.trace] Window {win} missing comp or setWindowOpacity method")
                except Exception as e:
                    logging.getLogger(__name__).warning(f"[spiral.trace] Failed to set window opacity on {win}: {e}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[spiral.trace] Failed to update window opacity: {e}")

    # ---------------- Spiral compositor window management ----------------
    def _create_spiral_windows(self):
        """Create per-display spiral compositor windows if spiral enabled.

        Called from launch() and when enabling spiral mid-run. Idempotent: if
        windows already exist they are refreshed only if screen count changed.
        """
        if not self.spiral_enabled:
            try: logging.getLogger(__name__).info("_create_spiral_windows early-exit: spiral not enabled")
            except Exception: pass
            return
        # Suppress in simulation mode (no real GL); update chip if present.
        if getattr(self, '_gl_simulation', False):
            try: logging.getLogger(__name__).info("_create_spiral_windows early-exit: simulation flag true")
            except Exception: pass
            if hasattr(self, 'chip_spiral'):
                try:
                    self.chip_spiral.setText('Spiral: Sim')
                    self.chip_spiral.setToolTip('GL simulation mode – disable MESMERGLASS_GL_SIMULATE for real rendering')
                except Exception: pass
            return
        # Skip if we already have windows matching current selection
        # Diagnostic: force overlays on all screens if MESMERGLASS_SPIRAL_ALL=1
        force_all = os.environ.get('MESMERGLASS_SPIRAL_ALL') == '1'
        try:
            if force_all:
                screens = QGuiApplication.screens()
                checked_idx = list(range(len(screens)))
                logging.getLogger(__name__).warning("[spiral.trace] MESMERGLASS_SPIRAL_ALL=1: Forcing overlays on all screens: %s", checked_idx)
            else:
                checked_idx = [i for i in range(self.list_displays.count()) if self.list_displays.item(i).checkState()==Qt.CheckState.Checked]
                logging.getLogger(__name__).info(f"[spiral.trace] UI selection: checked_idx={checked_idx} (list_displays.count={self.list_displays.count()})")
                for idx in checked_idx:
                    try:
                        item = self.list_displays.item(idx)
                        logging.getLogger(__name__).info(f"[spiral.trace] UI selected display idx={idx} text={item.text()} checked={item.checkState()==Qt.CheckState.Checked}")
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"[spiral.trace] Error logging UI display idx={idx}: {e}")
        except Exception:
            checked_idx = []
        
        # Auto-select first display if none selected (same logic as launch())
        if not checked_idx and self.list_displays.count() > 0:
            try:
                self.list_displays.item(0).setCheckState(Qt.CheckState.Checked)
                checked_idx = [0]
                logging.getLogger(__name__).info("_create_spiral_windows: auto-selected display 0 (none were checked)")
            except Exception as e:
                logging.getLogger(__name__).warning(f"_create_spiral_windows: auto-select failed: {e}")
        
        if not checked_idx:
            try: logging.getLogger(__name__).info("_create_spiral_windows early-exit: no displays selected (list_displays.count=%s)", getattr(self, 'list_displays', None).count() if hasattr(self,'list_displays') else '?')
            except Exception: pass
            return
        # If we already have same count assume up-to-date
        if self.spiral_windows and len(self.spiral_windows) == len(checked_idx):
            try: logging.getLogger(__name__).info("_create_spiral_windows early-exit: existing windows count matches selection (%d)", len(self.spiral_windows))
            except Exception: pass
            
            # Before early-exit, check if custom mode needs settings applied
            logging.getLogger(__name__).info(f"[CustomVisual] Early-exit check: visual_director={self.visual_director is not None}")
            if self.visual_director:
                is_custom = self.visual_director.is_custom_mode_active()
                logging.getLogger(__name__).info(f"[CustomVisual] Early-exit check: is_custom_mode_active={is_custom}")
                if is_custom:
                    try:
                        from mesmerglass.mesmerloom.custom_visual import CustomVisual
                        current = self.visual_director.current_visual
                        logging.getLogger(__name__).info(f"[CustomVisual] Early-exit check: current_visual type={type(current).__name__}, spiral_windows={len(self.spiral_windows) if self.spiral_windows else 0}")
                        if isinstance(current, CustomVisual) and self.spiral_windows:
                            for win in self.spiral_windows:
                                has_comp = hasattr(win, 'comp')
                                # Check for spiral_director OR director (different compositor types)
                                has_spiral = (hasattr(win.comp, 'spiral_director') or hasattr(win.comp, 'director')) if has_comp else False
                                logging.getLogger(__name__).info(f"[CustomVisual] Early-exit check: win has_comp={has_comp}, has_spiral={has_spiral}")
                                if has_comp and has_spiral:
                                    current.compositor = win.comp
                                    logging.getLogger(__name__).info("[CustomVisual] About to call reapply_all_settings()...")
                                    current.reapply_all_settings()
                                    logging.getLogger(__name__).info("[CustomVisual] Re-applied all settings (early-exit path)")
                                    break
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"[CustomVisual] Failed to re-apply settings (early-exit): {e}")
                        import traceback
                        traceback.print_exc()
            
            return
        self._destroy_spiral_windows()
        if LoomCompositor is None:
            try: logging.getLogger(__name__).warning("_create_spiral_windows abort: LoomCompositor unavailable")
            except Exception: pass
            return
        try:
            screens = QGuiApplication.screens()
        except Exception:
            screens = []
        try: logging.getLogger(__name__).info("_create_spiral_windows building windows for displays=%s total_screens=%d", checked_idx, len(screens))
        except Exception: pass
        # Log all available screens and their geometries
        logging.getLogger(__name__).info("[launcher] Available screens:")
        for idx, screen in enumerate(screens):
            logging.getLogger(__name__).info(f"  Screen {idx}: name={screen.name()} geometry={screen.geometry()}")

        from .spiral_duplicate_window import SpiralDuplicateWindow
        main_win = None
        for idx, i in enumerate(checked_idx):
            sc = screens[i] if (i < len(screens) and screens) else (screens[0] if screens else None)
            if sc is None:
                continue
            if idx == 0:
                # Main spiral overlay (GL)
                try:
                    # Pass defer_timer flag to SpiralWindow so it sets flag BEFORE compositor init
                    defer_timer = getattr(self, '_defer_compositor_timer', False)
                    win = SpiralWindow(self.spiral_director, parent=None, screen_index=i, defer_timer=defer_timer)
                    win.setGeometry(sc.geometry())
                    win.set_active(True)
                    
                    # CRITICAL: Update visual director to use spiral window's compositor
                    # Visual director was initialized with launcher's preview compositor,
                    # but we need to use the spiral window's compositor for actual rendering
                    if self.visual_director and hasattr(win, 'comp'):
                        try:
                            self.visual_director.compositor = win.comp
                            logging.getLogger(__name__).info("[visual] Updated visual director to use spiral window compositor")
                            
                            # CRITICAL: Also update text director to use spiral window's compositor
                            if self.text_director:
                                # IMPORTANT: Preserve opacity setting from old compositor
                                old_opacity = 1.0
                                if self.text_director.compositor and hasattr(self.text_director.compositor, 'get_text_opacity'):
                                    old_opacity = self.text_director.compositor.get_text_opacity()
                                    logging.getLogger(__name__).info(f"[text] Preserving opacity {old_opacity:.2f} from old compositor")
                                
                                self.text_director.compositor = win.comp
                                win.comp.text_director = self.text_director  # Bidirectional link
                                logging.getLogger(__name__).info("[text] Updated text director to use spiral window compositor")
                                
                                # Apply the preserved opacity to the new compositor
                                if hasattr(win.comp, 'set_text_opacity'):
                                    win.comp.set_text_opacity(old_opacity)
                                    logging.getLogger(__name__).info(f"[text] Applied preserved opacity {old_opacity:.2f} to new compositor")
                            
                            # CRITICAL: Also attach visual director to compositor so paintGL can update it
                            win.comp.visual_director = self.visual_director
                            logging.getLogger(__name__).info("[visual] Attached visual director to compositor for auto-updates")
                            
                            # NOTE: Do NOT auto-load media here - wait for Launch button
                            # User expects mode to load in "preview" state without starting playback
                            # Media will load when Launch button is pressed
                        except Exception as e:
                            logging.getLogger(__name__).warning(f"[visual] Failed to update compositor: {e}")
                    
                    # Apply current opacity to new window
                    # For custom modes, set window opacity to 1.0 so JSON has 100% direct control
                    try:
                        if self.visual_director and self.visual_director.is_custom_mode_active():
                            current_opacity = 1.0
                            logging.getLogger(__name__).info("[CustomVisual] Setting window opacity to 1.0 for direct JSON control")
                        else:
                            current_opacity = getattr(self, 'spiral_opacity', 0.85)
                        
                        if hasattr(win, 'comp') and hasattr(win.comp, 'setWindowOpacity'):
                            win.comp.setWindowOpacity(current_opacity)
                            logging.getLogger(__name__).info(f"[spiral.trace] Applied opacity {current_opacity} to new spiral window")
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"[spiral.trace] Failed to set initial opacity: {e}")
                    
                    win.showFullScreen(); win.raise_()
                    self.spiral_windows.append(win)
                    main_win = win
                    # VR: connect frame stream to VR bridge if enabled
                    try:
                        if self.vr_bridge and hasattr(win, 'comp') and hasattr(win.comp, 'frame_drawn'):
                            self._connect_vr_to_comp(win.comp)
                    except Exception:
                        pass
                except Exception:
                    continue
            else:
                # Duplicate window for secondary screens
                try:
                    dup_win = SpiralDuplicateWindow(sc, sc.geometry())
                    if main_win:
                        if hasattr(main_win, 'comp'):
                            logging.getLogger(__name__).info(f"[launcher] main_win.comp found for duplicate window on screen {sc.name()}")
                            if hasattr(main_win.comp, 'get_framebuffer_image'):
                                logging.getLogger(__name__).info(f"[launcher] Assigning get_framebuffer_image as image source for duplicate window on screen {sc.name()}")
                                dup_win.set_image_source(main_win.comp.get_framebuffer_image)
                                if hasattr(main_win.comp, 'frame_drawn'):
                                    dup_win.connect_frame_signal(main_win.comp)
                                    logging.getLogger(__name__).info(f"[launcher] Connected frame_drawn signal for duplicate window on screen {sc.name()}")
                            else:
                                logging.getLogger(__name__).warning(f"[launcher] main_win.comp missing get_framebuffer_image for duplicate window on screen {sc.name()}")
                        else:
                            logging.getLogger(__name__).warning(f"[launcher] main_win missing 'comp' attribute for duplicate window on screen {sc.name()}")
                    else:
                        logging.getLogger(__name__).warning(f"[launcher] No main_win for duplicate window on screen {sc.name()}")
                    # Apply current opacity to duplicate mirror window so overlay effect matches main.
                    # For custom modes, set to 1.0 for direct JSON control
                    try:
                        if self.visual_director and self.visual_director.is_custom_mode_active():
                            current_opacity = 1.0
                            logging.getLogger(__name__).info("[CustomVisual] Setting duplicate window opacity to 1.0 for direct JSON control")
                        else:
                            current_opacity = getattr(self, 'spiral_opacity', 0.85)
                        
                        if hasattr(dup_win, 'set_overlay_opacity'):
                            dup_win.set_overlay_opacity(current_opacity)
                    except Exception:
                        pass
                    dup_win.showFullScreen(); dup_win.raise_()
                    self.spiral_windows.append(dup_win)
                except Exception as e:
                    logging.getLogger(__name__).error(f"[launcher] Exception creating duplicate window: {e}")
                    continue
        try:
            logging.getLogger(__name__).info("_create_spiral_windows done: created=%d", len(self.spiral_windows))
        except Exception:
            pass
        
        # If custom mode is active, re-apply all settings now that windows exist
        if self.visual_director and self.visual_director.is_custom_mode_active():
            try:
                from mesmerglass.mesmerloom.custom_visual import CustomVisual
                current = self.visual_director.current_visual
                if isinstance(current, CustomVisual) and self.spiral_windows:
                    # Re-apply all custom mode settings to newly created windows
                    for win in self.spiral_windows:
                        # Check for spiral_director OR director (different compositor types)
                        has_spiral = hasattr(win, 'comp') and (hasattr(win.comp, 'spiral_director') or hasattr(win.comp, 'director'))
                        if has_spiral:
                            current.compositor = win.comp
                            current.reapply_all_settings()
                            logging.getLogger(__name__).info("[CustomVisual] Re-applied all settings to new window")
                            break  # Only need to apply to first window (others mirror it)
            except Exception as e:
                logging.getLogger(__name__).warning(f"[CustomVisual] Failed to re-apply settings: {e}")

    def _destroy_spiral_windows(self):
        """Destroy all runtime spiral compositor windows."""
        # Disconnect VR stream first
        try:
            self._disconnect_vr()
        except Exception:
            pass
        # CRITICAL: Clear compositor references FIRST to prevent GL operations
        # on deleted compositor (causes GL_INVALID_OPERATION errors)
        # This ensures no texture uploads or rendering happens during destruction
        if hasattr(self, 'visual_director') and self.visual_director:
            try:
                self.visual_director.compositor = None
                logging.getLogger(__name__).info("[spiral.trace] Cleared visual_director.compositor before window destruction")
            except Exception:
                pass
        if hasattr(self, 'text_director') and self.text_director:
            try:
                self.text_director.compositor = None
                logging.getLogger(__name__).info("[spiral.trace] Cleared text_director.compositor before window destruction")
            except Exception:
                pass
        
        # Now safe to destroy windows (no GL operations will be attempted)
        for win in list(self.spiral_windows):
            try:
                if hasattr(win, 'set_active'):
                    try: win.set_active(False)
                    except Exception: pass
                win.close()
                if hasattr(win, 'deleteLater'):
                    try: win.deleteLater()
                    except Exception: pass
            except Exception:
                pass
        self.spiral_windows.clear()

    # ---------------- VR bridge wiring ----------------
    def _init_vr_bridge(self):
        """Initialize VrBridge according to env flags."""
        try:
            self.vr_bridge = VrBridge(enabled=True)
            if self._vr_force_mock:
                # Force mock mode regardless of OpenXR availability
                try:
                    setattr(self.vr_bridge, "_mock", True)
                except Exception:
                    pass
            self.vr_bridge.start()
            logging.getLogger(__name__).info("[vr] VrBridge initialized (mock=%s)", getattr(self.vr_bridge, "_mock", True))
        except Exception as e:
            logging.getLogger(__name__).warning("[vr] VrBridge init failed: %s", e)
            self.vr_bridge = None

    def _connect_vr_to_comp(self, comp):
        """Connect compositor frame signal to VR submit slot (idempotent)."""
        if not self.vr_bridge:
            return
        try:
            if self._vr_comp is comp:
                return
            if self._vr_comp is not None:
                self._disconnect_vr()
            self._vr_comp = comp
            # Enable compositor VR safe mode if requested via env and supported
            try:
                import os as _os
                if _os.environ.get("MESMERGLASS_VR_SAFE") in ("1", "true", "True") and hasattr(comp, "enable_vr_safe_mode"):
                    comp.enable_vr_safe_mode(True)
                    logging.getLogger(__name__).info("[vr] Enabled VR safe mode on compositor (offscreen FBO tap)")
            except Exception:
                pass
            # Bind OpenXR session to THIS compositor's current GL context before connecting
            did_make_current = False
            try:
                if hasattr(comp, 'makeCurrent'):
                    # Only make current if not already current, to avoid interfering with paintGL
                    try:
                        from PyQt6.QtGui import QOpenGLContext  # type: ignore
                    except Exception:
                        QOpenGLContext = None  # type: ignore
                    is_current = False
                    if 'QOpenGLContext' in locals() and QOpenGLContext is not None:
                        try:
                            is_current = (QOpenGLContext.currentContext() is not None)
                        except Exception:
                            is_current = False
                    if not is_current:
                        comp.makeCurrent()
                        did_make_current = True
                # Attempt deferred VR init now that a context is definitely current
                try:
                    if hasattr(self.vr_bridge, 'ensure_initialized_with_current_context'):
                        self.vr_bridge.ensure_initialized_with_current_context()
                except Exception as e:
                    logging.getLogger(__name__).debug("[vr] ensure_initialized_with_current_context failed: %s", e)
            finally:
                if did_make_current and hasattr(comp, 'doneCurrent'):
                    try: comp.doneCurrent()
                    except Exception: pass
            if hasattr(comp, 'frame_drawn'):
                comp.frame_drawn.connect(self._vr_on_frame)  # type: ignore[attr-defined]
                logging.getLogger(__name__).info("[vr] Connected frame_drawn to VR submitter")
        except Exception as e:
            logging.getLogger(__name__).warning("[vr] Failed to connect VR submit: %s", e)

    def _disconnect_vr(self):
        comp = self._vr_comp
        if comp is None:
            return
        try:
            if hasattr(comp, 'frame_drawn'):
                comp.frame_drawn.disconnect(self._vr_on_frame)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._vr_comp = None

    def _vr_on_frame(self):
        """Submit the latest compositor frame to the VR bridge."""
        if not (self.vr_bridge and self._vr_comp):
            return
        comp = self._vr_comp
        # Ensure a current GL context for VR submit, but avoid interfering
        # when we're already inside paintGL (signal emitted inline).
        did_make_current = False
        try:
            try:
                from PyQt6.QtGui import QOpenGLContext  # type: ignore
            except Exception:
                QOpenGLContext = None  # type: ignore
            current_ctx = None
            if 'QOpenGLContext' in locals() and QOpenGLContext is not None:
                try:
                    current_ctx = QOpenGLContext.currentContext()
                except Exception:
                    current_ctx = None
            if current_ctx is None and hasattr(comp, 'makeCurrent'):
                comp.makeCurrent()
                did_make_current = True
        except Exception:
            pass
        try:
            # If XR session was deferred, try to complete it now (once context is current)
            try:
                if hasattr(self.vr_bridge, 'ensure_initialized_with_current_context') and not getattr(self.vr_bridge, '_session_began', False):
                    self.vr_bridge.ensure_initialized_with_current_context()
            except Exception:
                pass
            # Determine source FBO and pixel size
            fbo = 0
            try:
                # Prefer offscreen VR-safe FBO if available
                if hasattr(comp, 'vr_fbo_info'):
                    info = comp.vr_fbo_info()
                    if info:
                        fbo, w_px, h_px = info
                        self.vr_bridge.submit_frame_from_fbo(int(fbo), int(w_px), int(h_px))
                        return
            except Exception:
                fbo = 0
            # Fallback for QOpenGLWidget: use defaultFramebufferObject() if available
            try:
                if hasattr(comp, 'defaultFramebufferObject'):
                    fbo = int(comp.defaultFramebufferObject())
            except Exception:
                pass
            try:
                dpr = getattr(comp, 'devicePixelRatioF', lambda: 1.0)()
            except Exception:
                dpr = 1.0
            try:
                w_px = int(max(1, comp.width()) * float(dpr))
                h_px = int(max(1, comp.height()) * float(dpr))
            except Exception:
                w_px, h_px = 1920, 1080
            try:
                self.vr_bridge.submit_frame_from_fbo(fbo, w_px, h_px)
            except Exception as e:
                logging.getLogger(__name__).debug("[vr] submit_frame_from_fbo failed: %s", e)
        finally:
            # Only release context if we acquired it here; if paintGL owns it,
            # leave it alone to avoid driver instability.
            if did_make_current:
                try:
                    if hasattr(comp, 'doneCurrent'):
                        comp.doneCurrent()
                except Exception:
                    pass

    # Media page removed

    def _page_displays(self):
        card = _card("Displays"); v = QVBoxLayout(card); v.setContentsMargins(12, 10, 12, 12); v.setSpacing(8)
        
        # Add label for monitors
        monitors_label = QLabel("<b>Monitors</b>")
        v.addWidget(monitors_label)
        
        self.list_displays = QListWidget()
        # Add physical monitors
        for s in QGuiApplication.screens():
            it = QListWidgetItem(f"🖥️ {s.name()}  {s.geometry().width()}x{s.geometry().height()}")
            it.setCheckState(Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, {"type": "monitor", "screen": s})
            self.list_displays.addItem(it)
            
        # Separator
        separator = QListWidgetItem("─" * 40)
        separator.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
        self.list_displays.addItem(separator)
        
        # Add label for VR devices
        vr_label_item = QListWidgetItem("<b>VR Devices (Wireless)</b>")
        vr_label_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
        self.list_displays.addItem(vr_label_item)
        
        # Add discovered VR clients
        self._refresh_vr_displays()
        
        v.addWidget(self.list_displays, 1)

        btn_sel_all = QPushButton("Select all"); btn_sel_pri = QPushButton("Primary only")
        btn_refresh_vr = QPushButton("🔄 Refresh VR")
        btn_refresh_vr.clicked.connect(self._refresh_vr_displays)
        
        quick_row = QWidget()
        quick_layout = QHBoxLayout(quick_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_label = QLabel("Quick select:")
        quick_label.setMinimumWidth(160)
        quick_layout.addWidget(quick_label)
        quick_layout.addWidget(btn_sel_all)
        quick_layout.addWidget(btn_sel_pri)
        quick_layout.addWidget(btn_refresh_vr)
        quick_layout.addStretch()
        
        v.addWidget(quick_row)
        btn_sel_all.clicked.connect(self._select_all_displays)
        btn_sel_pri.clicked.connect(self._select_primary_display)

        page = QWidget(); root = QVBoxLayout(page); root.addWidget(card); root.addStretch(1)
        return page

    def _refresh_vr_displays(self):
        """Refresh the VR devices section in the displays list."""
        logging.getLogger(__name__).debug("[VR Refresh] Starting VR display refresh")
        
        if not hasattr(self, 'list_displays'):
            return
            
        # Save the checked state of existing VR items (by client IP)
        checked_ips = set()
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict) and data.get("type") == "vr":
                if item.checkState() == Qt.CheckState.Checked:
                    client_info = data.get("client")
                    if client_info:
                        checked_ips.add(client_info.get("ip"))
        
        # Find indices of monitors, separator, label, and VR devices
        last_monitor_idx = -1
        separator_idx = -1
        vr_label_idx = -1
        vr_device_indices = []
        
        for i in range(self.list_displays.count()):
            item = self.list_displays.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            text = item.text()
            
            # Track last monitor
            if data and isinstance(data, dict) and data.get("type") == "monitor":
                last_monitor_idx = i
            # Track separator
            elif "─" in text and separator_idx == -1:
                separator_idx = i
            # Track VR label
            elif "VR Devices" in text and vr_label_idx == -1:
                vr_label_idx = i
            # Track VR devices
            elif data and isinstance(data, dict) and data.get("type") == "vr":
                vr_device_indices.append(i)
        
        # Remove existing VR devices (in reverse order to preserve indices)
        for idx in reversed(vr_device_indices):
            self.list_displays.takeItem(idx)
        
        # Ensure separator exists in correct position (after monitors)
        if separator_idx == -1:
            separator = QListWidgetItem("─" * 40)
            separator.setFlags(Qt.ItemFlag.NoItemFlags)
            insert_pos = last_monitor_idx + 1
            self.list_displays.insertItem(insert_pos, separator)
            separator_idx = insert_pos
            # Adjust vr_label_idx if it exists and is after insertion
            if vr_label_idx >= insert_pos:
                vr_label_idx += 1
        
        # Ensure VR label exists in correct position (after separator)
        if vr_label_idx == -1:
            vr_label_item = QListWidgetItem("<b>VR Devices (Wireless)</b>")
            vr_label_item.setFlags(Qt.ItemFlag.NoItemFlags)
            insert_pos = separator_idx + 1
            self.list_displays.insertItem(insert_pos, vr_label_item)
            vr_label_idx = insert_pos
            
        # Get discovered VR clients from discovery service (if running)
        discovered_clients = []
        if self.vr_discovery_service:
            try:
                # Discovery service tracks clients that have broadcast "VR_HEADSET_HELLO"
                discovered_clients = getattr(self.vr_discovery_service, 'discovered_clients', [])
                logging.getLogger(__name__).info(f"[VR Refresh] Discovery service returned {len(discovered_clients)} clients")
                if discovered_clients:
                    for client in discovered_clients:
                        logging.getLogger(__name__).info(f"  → {client.get('name')} at {client.get('ip')}")
            except Exception as e:
                logging.getLogger(__name__).error(f"Error getting VR clients from discovery: {e}")
        
        if discovered_clients:
            # Add VR client items after the VR label (make them checkable and selectable)
            insert_pos = vr_label_idx + 1
            for client_info in discovered_clients:
                name = client_info.get("name", "Unknown VR Device")
                ip = client_info.get("ip", "0.0.0.0")
                it = QListWidgetItem(f"📱 {name} ({ip})")
                # Restore checked state if this client was previously checked
                if ip in checked_ips:
                    it.setCheckState(Qt.CheckState.Checked)
                else:
                    it.setCheckState(Qt.CheckState.Unchecked)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                it.setData(Qt.ItemDataRole.UserRole, {"type": "vr", "client": client_info})
                self.list_displays.insertItem(insert_pos, it)
                insert_pos += 1  # Increment for next VR device

    # ========================== helpers / pickers ==========================
    def _bind_shortcuts(self):
        sc_launch = QShortcut(QKeySequence("Ctrl+L"), self); sc_launch.activated.connect(self.launch)
        sc_stop = QShortcut(QKeySequence("Ctrl+."), self); sc_stop.activated.connect(self.stop_all)
        for i in range(1, 6):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda idx=i - 1: self.tabs.setCurrentIndex(idx))
        sc_dev = QShortcut(QKeySequence("Ctrl+Shift+D"), self); sc_dev.activated.connect(self._open_devtools)

    def _open_devtools(self, focus_performance: bool = False):
        """Open (or focus) DevTools in a separate window.

        Replaces prior behavior of adding a tab. A 'DevTools' menu is created on first open
        with actions to focus or close the window. Shortcut (Ctrl+Shift+D) reuses the same window.
        """
        try:
            # If already open, just raise/focus
            if getattr(self, '_devtools_win', None):
                try:
                    self._devtools_win.show(); self._devtools_win.raise_(); self._devtools_win.activateWindow()
                    if focus_performance and hasattr(self, '_devtools_tabs'):
                        # Switch to performance tab if it exists
                        tabs = getattr(self, '_devtools_tabs', None)
                        if tabs:
                            for i in range(tabs.count()):
                                if tabs.tabText(i).lower().startswith('performance'):
                                    tabs.setCurrentIndex(i); break
                except Exception:
                    pass
                return
            # Determine default port (reuse active MesmerIntiface server if available)
            default_port = 12350
            if getattr(self, 'mesmer_server', None):
                try: default_port = int(self.mesmer_server.selected_port)
                except Exception: pass
            dev_page = DevToolsPage(default_port=default_port)
            # Host pages in a tab widget inside its own window
            from PyQt6.QtWidgets import QMainWindow
            # Create as top-level (no parent) so it does not stay always-on-top of main window
            win = QMainWindow(None)
            win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            win.setWindowTitle("DevTools")
            from PyQt6.QtWidgets import QTabWidget
            tabs = QTabWidget(); self._devtools_tabs = tabs
            # DevTools (Virtual Toys) tab
            scroll1 = QScrollArea(); scroll1.setWidgetResizable(True); scroll1.setFrameShape(QFrame.Shape.NoFrame)
            scroll1.setWidget(dev_page)
            tabs.addTab(scroll1, "DevTools")
            # Performance tab (lazy optional add below)
            perf_page = PerformancePage(self.audio)
            scroll2 = QScrollArea(); scroll2.setWidgetResizable(True); scroll2.setFrameShape(QFrame.Shape.NoFrame)
            scroll2.setWidget(perf_page)
            tabs.addTab(scroll2, "Performance")
            if focus_performance:
                tabs.setCurrentIndex(1)
            win.setCentralWidget(tabs)
            self._devtools_win = win  # hold reference
            # Inject menu on first open
            self._ensure_devtools_menu()
            win.destroyed.connect(lambda *_: setattr(self, '_devtools_win', None))  # clear ref on close
            win.resize(640, 480)
            win.show()
        except Exception as e:
            logging.getLogger(__name__).error("Failed to open DevTools window: %s", e)

    def _ensure_devtools_menu(self):
        """Create a DevTools menu lazily (only when first opened)."""
        try:
            if getattr(self, '_devtools_menu_created', False):
                return
            mb = self.menuBar() if hasattr(self, 'menuBar') else None
            if not mb:
                return
            m = mb.addMenu("DevTools")
            act_focus = m.addAction("Open / Focus DevTools")
            act_focus.triggered.connect(lambda: self._open_devtools(False))
            act_perf = m.addAction("Open Performance Metrics")
            act_perf.triggered.connect(lambda: self._open_devtools(True))
            act_close = m.addAction("Close DevTools")
            def _close():
                w = getattr(self, '_devtools_win', None)
                if w:
                    try: w.close()
                    except Exception: pass
            act_close.triggered.connect(_close)
            self._devtools_menu_created = True
        except Exception:
            pass

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

    # Media pickers removed

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
            "font_path": getattr(self, "current_font_path", None),  # added: persist font file path
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
            # Load raw font file first (if provided) so its family becomes available
            fpath = textfx.get("font_path")
            if fpath and os.path.isfile(fpath):
                try:
                    from PyQt6.QtGui import QFontDatabase
                    fid = QFontDatabase.addApplicationFont(fpath)
                    self.current_font_path = fpath
                    if fid != -1 and (not fam):
                        fams = QFontDatabase.applicationFontFamilies(fid)
                        if fams:
                            fam = fams[0]
                except Exception as e:
                    logging.getLogger(__name__).warning("Font load failed (%s): %s", fpath, e)
                    self.current_font_path = fpath  # remember even if invalid
            if fam and sz:
                try:
                    self.text_font = QFont(fam, int(sz))
                except Exception:
                    pass
            # Ensure current_font_path retained even if load failed
            if fpath and not getattr(self, 'current_font_path', None):
                self.current_font_path = fpath
            # Update UI font label if page exists (ensures user sees restored font)
            # Note: TextTab doesn't need font label updates (fonts controlled by modes)
            try:
                pass  # No font UI updates needed for simplified text tab
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
            # --- Text Tab (simplified - no UI updates needed) ---
            # TextTab manages its own message library, no external updates needed
            
            # --- Video Opacity Controls (Primary / Secondary) ---
            # Reflect restored opacity values in sliders & percentage labels; block signals to avoid feedback loops.
            if hasattr(self, 'sld_primary_op'):
                try:
                    self.sld_primary_op.blockSignals(True)
                    self.sld_primary_op.setValue(int(self.primary_op * 100))
                    if hasattr(self, 'lab_primary_pct'):
                        self.lab_primary_pct.setText(f"{int(self.primary_op * 100)}%")
                finally:
                    try: self.sld_primary_op.blockSignals(False)
                    except Exception: pass
            if hasattr(self, 'sld_secondary_op'):
                try:
                    self.sld_secondary_op.blockSignals(True)
                    self.sld_secondary_op.setValue(int(self.secondary_op * 100))
                    if hasattr(self, 'lab_secondary_pct'):
                        self.lab_secondary_pct.setText(f"{int(self.secondary_op * 100)}%")
                finally:
                    try: self.sld_secondary_op.blockSignals(False)
                    except Exception: pass
            # Propagate to existing overlays if any (headless tests usually have none)
            try:
                for ov in getattr(self, 'overlays', []) or []:
                    if hasattr(ov, 'primary_op'): ov.primary_op = self.primary_op
                    if hasattr(ov, 'secondary_op'): ov.secondary_op = self.secondary_op
            except Exception:
                pass
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
        if hasattr(self, 'chip_spiral'):
            self.chip_spiral.setText(f"Spiral: {'On' if self.spiral_enabled else 'Off'}")

    # (Removed legacy spiral integration block in favor of minimal Phase 1.1 handlers earlier)

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
        
        # Get checked displays (monitors and VR clients)
        checked_items = [self.list_displays.item(i) for i in range(self.list_displays.count())
                        if self.list_displays.item(i).checkState()==Qt.CheckState.Checked]
        
        logging.getLogger(__name__).info(f"[VR] Found {len(checked_items)} checked items in display list")
        
        # Separate monitors and VR clients
        monitor_indices = []
        vr_clients = []
        for item in checked_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            logging.getLogger(__name__).info(f"[VR] Checked item: text='{item.text()}' data={data}")
            if data and isinstance(data, dict):
                if data.get("type") == "monitor":
                    # Find monitor index
                    for i, s in enumerate(screens):
                        if s == data.get("screen"):
                            monitor_indices.append(i)
                            break
                elif data.get("type") == "vr":
                    client_info = data.get("client")
                    logging.getLogger(__name__).info(f"[VR] Found VR item! client_info={client_info}")
                    if client_info:
                        vr_clients.append(client_info)
                        logging.getLogger(__name__).info(f"[VR] Added VR client: {client_info}")
            else:
                logging.getLogger(__name__).warning(f"[VR] Checked item has no data or invalid data: text='{item.text()}'")
        
        logging.getLogger(__name__).info(f"[VR] After processing: monitor_indices={monitor_indices}, vr_clients={vr_clients}")
        
        # Auto-select first monitor if none selected
        # For VR streaming, we still need a monitor selected to create the compositor
        if not monitor_indices and not vr_clients and len(screens) > 0:
            monitor_indices = [0]
            # Also check the first monitor item in the list
            for i in range(self.list_displays.count()):
                item = self.list_displays.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and data.get("type") == "monitor":
                    item.setCheckState(Qt.CheckState.Checked)
                    break
        elif not monitor_indices and vr_clients:
            # VR only selected - still create compositor but minimize window
            monitor_indices = [0]
            logging.getLogger(__name__).info("VR-only mode: using minimized compositor on monitor 0")
        
        # Create overlays for physical monitors
        shared_start_time = time.time()
        for i in monitor_indices:
            sc = screens[i] if i < len(screens) else screens[0]
            ov = OverlayWindow(sc, self.primary_path or None, self.secondary_path or None,
                               self.primary_op, self.secondary_op, self.text, self.text_color, self.text_font,
                               self.text_scale_pct, self.flash_interval_ms, self.flash_width_ms,
                               self.fx_mode, self.fx_intensity)
            ov.start_time = shared_start_time
            self.overlays.append(ov)
            
        # VR streaming setup happens later after spiral windows are created
        # (need compositor to capture frames from)
            
        # Always use a single shared flash timer so message changes align exactly
        # with flash boundaries (prevents mid-flash text changes). Buzz logic
        # inside the timer remains conditional on enable_device_sync.
        if self.overlays:
            self._wire_shared_flash_timer(shared_start_time)
        if self.enable_device_sync and self.enable_bursts:
            self._start_burst_scheduler()
        
        # Auto-enable spiral if not already enabled
        if not self.spiral_enabled:
            try:
                self._on_spiral_toggled(True)  # Enable spiral and start timer
                logging.getLogger(__name__).info("[launch] Auto-enabled MesmerLoom spiral")
            except Exception as e:
                logging.getLogger(__name__).warning(f"[launch] Failed to auto-enable spiral: {e}")
        
        # Auto-set default intensity if currently zero (make spiral visible)
        # Skip this for custom modes - they control intensity directly
        try:
            if self.visual_director and self.visual_director.is_custom_mode_active():
                logging.getLogger(__name__).info("[CustomVisual] Skipping auto-intensity (custom mode controls intensity)")
                
                # CRITICAL: Start spiral timer NOW (was deferred during mode load for silence)
                if getattr(self, '_needs_spiral_timer_init', False) or self.spiral_timer is None or not self.spiral_timer.isActive():
                    logging.getLogger(__name__).info("[CustomVisual] Starting spiral timer on Launch...")
                    # Create timer if needed
                    if self.spiral_timer is None:
                        self.spiral_timer = QTimer(self)
                        self.spiral_timer.setInterval(16)  # ~60 FPS logic tick
                        logging.getLogger(__name__).info("[CustomVisual] Created new QTimer")
                    
                    # ALWAYS ensure signal is connected (even if timer already existed)
                    try:
                        self.spiral_timer.timeout.disconnect()  # type: ignore[arg-type]
                        logging.getLogger(__name__).info("[CustomVisual] Disconnected existing timer signal")
                    except Exception:
                        pass
                    self.spiral_timer.timeout.connect(self._on_spiral_tick)
                    logging.getLogger(__name__).info("[CustomVisual] Connected timer to _on_spiral_tick()")
                    
                    # Start timer
                    if not self.spiral_timer.isActive():
                        self.spiral_timer.start()
                        logging.getLogger(__name__).info("[CustomVisual] Started spiral timer on Launch")
                    
                    # Clear flag
                    self._needs_spiral_timer_init = False
                
                # CRITICAL: Resume visual director to start playback
                # Visual director was paused during mode load (silent state)
                self.visual_director.resume()
                logging.getLogger(__name__).info("[CustomVisual] Resumed visual director (started playback)")
                
                # CRITICAL: Start compositor timers NOW (were deferred for complete silence)
                if getattr(self, '_defer_compositor_timer', False):
                    for win in self.spiral_windows:
                        if hasattr(win, 'comp') and hasattr(win.comp, '_start_timer'):
                            win.comp._start_timer()
                            logging.getLogger(__name__).info("[CustomVisual] Started compositor timer on Launch")
                    # Clear flag so future creates use normal behavior
                    self._defer_compositor_timer = False
                
                # DON'T load media here - compositor might be deleted!
                # Will load after _create_spiral_windows() ensures valid GL context
                
            elif hasattr(self, 'spiral_director') and self.spiral_director:
                current_intensity = getattr(self.spiral_director.state, 'intensity', 0.0)
                if current_intensity == 0.0:
                    # Set to 70% intensity (comfortable default for hypnotic spiral)
                    self.spiral_director.set_intensity(0.7)
                    logging.getLogger(__name__).info("[launch] Set default spiral intensity: 0.7")
                    # Update UI slider if panel exists
                    if hasattr(self, 'page_mesmerloom') and hasattr(self.page_mesmerloom, 'sld_intensity'):
                        self.page_mesmerloom.sld_intensity.setValue(70)  # 0-100 range
        except Exception as e:
            logging.getLogger(__name__).warning(f"[launch] Failed to set default intensity: {e}")
        
        # Create spiral windows first to establish valid GL context
        try:
            self._create_spiral_windows()
        except Exception as e:
            logging.getLogger(__name__).error(f"[launch] Failed to create spiral windows: {e}")
            import traceback
            traceback.print_exc()
        
        # Start VR streaming if we have VR clients selected
        # Create and start the streaming server on-demand
        logging.getLogger(__name__).info(f"[VR] Checking VR clients: count={len(vr_clients)}, clients={vr_clients}")
        if vr_clients and len(vr_clients) > 0:
            logging.getLogger(__name__).info(f"[VR] Starting VR streaming for {len(vr_clients)} clients")
            try:
                # Get compositor from spiral window (fullscreen) instead of preview
                streaming_compositor = None
                if self.spiral_windows and len(self.spiral_windows) > 0:
                    if hasattr(self.spiral_windows[0], 'comp'):
                        streaming_compositor = self.spiral_windows[0].comp
                        logging.getLogger(__name__).info("VR streaming: using spiral window compositor")
                elif self.compositor:
                    streaming_compositor = self.compositor
                    logging.getLogger(__name__).info("VR streaming: using preview compositor (fallback)")
                
                if streaming_compositor:
                    # Import streaming server
                    from ..mesmervisor.streaming_server import VRStreamingServer
                    from ..mesmervisor.gpu_utils import EncoderType
                    import OpenGL.GL as GL
                    import numpy as np
                    
                    # Create frame cache (populated by Qt signal, consumed by streaming thread)
                    self._vr_streaming_active = True
                    self._vr_last_frame = None
                    self._vr_frame_lock = threading.Lock()
                    
                    def capture_frame():
                        """Return cached frame for VR streaming (called from streaming thread)"""
                        if not self._vr_streaming_active:
                            return None
                        
                        # Return cached frame (NEVER call GL functions from streaming thread)
                        with self._vr_frame_lock:
                            if self._vr_last_frame is not None:
                                frame = self._vr_last_frame.copy()  # Copy to avoid race conditions
                                return frame
                        
                        return None  # No frame available yet
                    
                    # Create streaming server with frame callback (2048x1024 @ 30 FPS, JPEG encoding, quality=25 optimized for Oculus Go)
                    self.vr_streaming_server = VRStreamingServer(
                        width=1920,
                        height=1080,
                        fps=30,
                        encoder_type=EncoderType.JPEG,
                        quality=25,  # Optimized for Oculus Go: stable 20 FPS, 60 Mbps, good visual quality
                        frame_callback=capture_frame
                    )
                    
                    # Discovery service already running from __init__, just ensure it's started
                    if self.vr_discovery_service and not hasattr(self.vr_discovery_service, '_running'):
                        self.vr_discovery_service.start()
                        logging.getLogger(__name__).info("VR discovery service started on UDP port 5556")
                    
                    # Start streaming server (TCP 5555)
                    self.vr_streaming_server.start_server()
                    logging.getLogger(__name__).info("VR streaming server started on TCP port 5555")
                    
                    # Connect compositor's frame_drawn signal to cache frames
                    if hasattr(streaming_compositor, 'frame_drawn'):
                        # Cache frame when compositor renders
                        def on_frame_ready():
                            """Cache frame from compositor (called from Qt main thread)"""
                            if self._vr_streaming_active:
                                try:
                                    # Capture frame from compositor (GL calls safe here - main thread)
                                    w_px = streaming_compositor.width()
                                    h_px = streaming_compositor.height()
                                    
                                    # Read pixels from GL framebuffer
                                    pixels = GL.glReadPixels(0, 0, w_px, h_px, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                                    frame = np.frombuffer(pixels, dtype=np.uint8).reshape(h_px, w_px, 3)
                                    frame = np.flipud(frame)  # Flip vertically (GL origin is bottom-left)
                                    
                                    # Cache frame for streaming thread (thread-safe)
                                    if frame is not None and frame.size > 0:
                                        with self._vr_frame_lock:
                                            self._vr_last_frame = frame
                                except Exception as e:
                                    logging.getLogger(__name__).error(f"VR frame cache error: {e}")
                                    import traceback
                                    traceback.print_exc()
                        
                        # Connect the signal
                        streaming_compositor.frame_drawn.connect(on_frame_ready)
                        logging.getLogger(__name__).info("VR streaming connected to compositor frame signal")
                        logging.getLogger(__name__).info(f"VR streaming: compositor size={streaming_compositor.width()}x{streaming_compositor.height()}")
                        
                        # If VR-only mode (no monitors selected), minimize the spiral window
                        if vr_clients and not any(data.get("type") == "monitor" 
                                                  for item in checked_items 
                                                  if (data := item.data(Qt.ItemDataRole.UserRole))):
                            if self.spiral_windows and len(self.spiral_windows) > 0:
                                self.spiral_windows[0].showMinimized()
                                logging.getLogger(__name__).info("VR-only mode: minimized spiral window")
                    else:
                        logging.getLogger(__name__).warning("Compositor missing frame_drawn signal for VR streaming")
                else:
                    logging.getLogger(__name__).warning("Cannot start VR streaming: no compositor available")
            except Exception as e:
                logging.getLogger(__name__).error(f"Failed to start VR streaming: {e}")
                import traceback
                traceback.print_exc()
        
        # NOW load media AFTER compositor is created and references updated
        try:
            if self.visual_director and self.visual_director.is_custom_mode_active():
                current_visual = self.visual_director.current_visual
                if current_visual and hasattr(current_visual, '_load_current_media'):
                    # Ensure compositor reference is valid before uploading textures
                    if self.visual_director.compositor is None:
                        logging.getLogger(__name__).error("[CustomVisual] Cannot load media: compositor is None!")
                    else:
                        current_visual._load_current_media()
                        logging.getLogger(__name__).info("[CustomVisual] Loaded initial media on Launch")
                
                # CRITICAL: Re-assert spiral opacity to make it visible
                # Fixes issue where spiral doesn't show until opacity slider is moved
                if hasattr(self, 'spiral_director') and self.spiral_director:
                    spiral_config = current_visual.config.get('spiral', {})
                    opacity = spiral_config.get('opacity', 0.5)
                    self.spiral_director.set_opacity(opacity)
                    logging.getLogger(__name__).info(f"[CustomVisual] Re-asserted spiral opacity: {opacity}")
        except Exception as e:
            logging.getLogger(__name__).error(f"[CustomVisual] Failed to load media: {e}")
            import traceback
            traceback.print_exc()
        
        # Start media cycling (using SimpleVisual from visuals.py - proven working)
        # In strict mode with a custom visual, drive media changes with a precise QTimer
        # at the exact interval derived from the mode. Otherwise, use default behavior
        # (note: built-in visuals are disabled in Phase 3).
        try:
            if self.visual_director and self.visual_director.is_custom_mode_active() and getattr(self, '_strict_mode', False):
                current_visual = self.visual_director.current_visual
                # Compute expected interval from mode's cycle_speed using shared formula
                speed = 50
                try:
                    speed = int(current_visual.config.get('media', {}).get('cycle_speed', 50)) if current_visual and hasattr(current_visual, 'config') else 50
                except Exception:
                    speed = 50
                s = max(1, min(100, speed))
                # interval_ms = 10000 * 0.005^((s-1)/99)
                import math as _m
                interval_ms = int(10000.0 * _m.pow(0.005, (s - 1) / 99.0))
                # Create precise timer
                from PyQt6.QtCore import QTimer as _QTimer
                self._strict_media_timer = getattr(self, '_strict_media_timer', None)
                if self._strict_media_timer is None:
                    self._strict_media_timer = _QTimer(self)
                    try:
                        self._strict_media_timer.setTimerType(_QTimer.TimerType.PreciseTimer)
                    except Exception:
                        pass
                    self._strict_media_timer.timeout.connect(self._on_strict_media_tick)
                self._strict_media_timer.setInterval(max(1, int(interval_ms)))
                if not self._strict_media_timer.isActive():
                    self._strict_media_timer.start()
                logging.getLogger(__name__).info(f"[mode] Strict media timer started @ {interval_ms} ms (speed={s})")
            else:
                self._start_media_cycling()
        except Exception as e:
            logging.getLogger(__name__).warning(f"[mode] Strict media timer setup failed: {e}")
            # Fallback to default behavior
            try:
                self._start_media_cycling()
            except Exception:
                pass

    def _on_strict_media_tick(self):
        """Strict-mode media tick: advance media exactly per mode interval."""
        try:
            if getattr(self, "_no_media", False):
                return
            if not (self.visual_director and self.visual_director.is_custom_mode_active()):
                return
            cv = self.visual_director.current_visual
            if not cv:
                return
            # Manually advance media; ThemeBank selection handled inside
            if hasattr(cv, '_media_paths') and isinstance(getattr(cv, '_media_paths', None), list) and cv._media_paths:
                cv._current_media_index = (cv._current_media_index + 1) % len(cv._media_paths)
            cv._load_current_media()
        except Exception as e:
            logging.getLogger(__name__).warning(f"[mode] Strict media tick error: {e}")

    def _start_media_cycling(self):
        """Start media cycling using appropriate visual based on media mode."""
        try:
            if getattr(self, "_no_media", False):
                logging.getLogger(__name__).info("[media] NO_MEDIA active -> skipping media cycling")
                return
            logging.getLogger(__name__).info(f"[media] _start_media_cycling called, mode={self.media_mode}")
            
            if not self.visual_director:
                logging.getLogger(__name__).warning("[media] Visual director not available")
                return
            
            # Skip if custom mode is active - it manages its own visuals
            if self.visual_director.is_custom_mode_active():
                logging.getLogger(__name__).info("[media] Custom mode active, skipping built-in visual selection")
                return
            
            # Log compositor status
            if self.visual_director.compositor:
                logging.getLogger(__name__).info("[media] Visual director has compositor ready")
            else:
                logging.getLogger(__name__).error("[media] Visual director compositor is None!")
                return
            
            # Log video streamer status for video modes
            if self.media_mode in [0, 2]:  # Images & Videos or Video Focus
                if self.visual_director.video_streamer:
                    logging.getLogger(__name__).info("[media] Video streamer available")
                else:
                    logging.getLogger(__name__).warning("[media] Video streamer not available for video mode")
            
            # Choose visual based on media mode:
            # 0=Images & Videos → SimpleVisual (index 0) - images only
            # 1=Images Only → SimpleVisual (index 0)
            # 2=Video Focus → Show warning that videos aren't supported yet
            
            # NOTE: Background rendering (images/videos) requires full implementation
            # in LoomWindowCompositor - currently only available in LoomCompositor
            
            if self.media_mode == 0:
                # Images & Videos: Use MixedVisual (index 7) - alternates between images and videos
                visual_index = 7  # MixedVisual (3 images, 2 videos per cycle)
                mode_name = "Images & Videos"
                # Enable zoom for mixed mode
                if self.compositor:
                    self.compositor.set_zoom_animation_enabled(True)
            elif self.media_mode == 1:
                # Images Only: Use SimpleVisual
                visual_index = 0  # SimpleVisual
                mode_name = "Images Only"
                # Enable zoom for image mode
                if self.compositor:
                    self.compositor.set_zoom_animation_enabled(True)
            else:  # media_mode == 2
                # Video Focus: Use AnimationVisual
                visual_index = 6  # AnimationVisual
                mode_name = "Video Focus"
                # Disable zoom for video focus mode
                if self.compositor:
                    self.compositor.set_zoom_animation_enabled(False)
                    
                # Warn if using LoomWindowCompositor (doesn't support background rendering yet)
                if hasattr(self.compositor, '__class__') and 'Window' in self.compositor.__class__.__name__:
                    logging.getLogger(__name__).warning(
                        "[media] Video playback requires background rendering which is not yet "
                        "implemented in LoomWindowCompositor. Videos will not display. "
                        "Use 'Images Only' mode for now."
                    )
            
            # NOTE: Built-in visual selection removed in Phase 3
            # Media cycling now requires custom mode with media settings
            logging.getLogger(__name__).warning(f"[media] Built-in visual selection removed - use custom JSON modes instead")
            # logging.getLogger(__name__).info(f"[media] Selecting visual {visual_index} ({mode_name})")
            # success = self.visual_director.select_visual(visual_index)  # Method removed in Phase 3
            success = False  # Always fail - no built-in visuals
            
            if success:
                logging.getLogger(__name__).info(f"[media] Started visual {visual_index} ({mode_name})")
            else:
                logging.getLogger(__name__).info(f"[media] Skipped built-in visual - load custom mode via MesmerLoom panel")
                
        except Exception as e:
            logging.getLogger(__name__).error(f"[media] Failed to start media cycling: {e}")
            import traceback
            traceback.print_exc()

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
        # Stop media cycler
        self._media_cycler = None
        step(3.5, "media cycler stopped")
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
        # Stop strict media timer if running
        if hasattr(self, "_strict_media_timer") and getattr(self, "_strict_media_timer") is not None:
            try:
                self._strict_media_timer.stop()
            except Exception:
                pass
            self._strict_media_timer = None; step(5.5, "strict media timer stopped")
        try: self.audio.stop(); step(6, "audio stopped")
        except Exception: pass
        try: self.pulse.stop(); step(7, "pulse stopped")
        except Exception: pass
        # Destroy spiral windows after other teardown to ensure GL contexts
        # release cleanly without referencing shutting-down director.
        try:
            self._destroy_spiral_windows(); step(8, "spiral windows destroyed")
        except Exception:
            pass
        # Stop VR streaming (but keep discovery service running for next session)
        try:
            self._vr_streaming_active = False
            if hasattr(self, 'vr_streaming_server') and self.vr_streaming_server:
                self.vr_streaming_server.stop_server()
                self.vr_streaming_server = None
                step(8.3, "vr streaming server stopped")
            # Note: vr_discovery_service continues running to discover devices
        except Exception as e:
            log.warning(f"Error stopping VR streaming: {e}")
        # Shutdown VR bridge last
        try:
            if getattr(self, 'vr_bridge', None):
                self.vr_bridge.shutdown()  # type: ignore[union-attr]
                step(8.5, "vr bridge shutdown")
        except Exception:
            pass

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
        # Stop VR discovery early
        try:
            if hasattr(self, 'vr_discovery') and self.vr_discovery:
                self.vr_discovery.stop()
                step(0.7, "vr discovery stopped")
        except Exception:
            pass
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
                # TextTab doesn't need UI updates for pack loading (messages controlled by mode files)
                pass
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
            # TextTab doesn't need pack name updates (controlled by mode files)
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
                # TextTab doesn't need pack name updates (controlled by mode files)
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
            # Font load action removed (moved into Text & FX tab button)
            file_menu.addSeparator()
            act_vmc = file_menu.addAction("Visual Mode Creator..."); act_vmc.triggered.connect(self._action_open_vmc)  # type: ignore[attr-defined]
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

    def _action_open_vmc(self):
        """Launch Visual Mode Creator in a separate process."""
        try:
            import subprocess
            import sys
            from pathlib import Path
            
            # Get path to VMC script
            vmc_script = Path(__file__).parent.parent.parent / "scripts" / "visual_mode_creator.py"
            
            if not vmc_script.exists():
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Visual Mode Creator", f"Could not find Visual Mode Creator script at:\n{vmc_script}")
                return
            
            # Launch VMC in separate process (non-blocking)
            # Use same Python interpreter that's running the launcher
            subprocess.Popen([sys.executable, str(vmc_script)], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
            
            logging.getLogger(__name__).info(f"[launcher] Launched Visual Mode Creator: {vmc_script}")
            
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to launch VMC: {e}")
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Visual Mode Creator", f"Failed to launch:\n{e}")
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
                # TextTab doesn't need UI text updates (controlled by mode files)
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

    # ---------------- Font import support ----------------
    def _on_load_font(self):
        """Prompt user to select a font file and apply it (stores path for session state)."""
        try:
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            from PyQt6.QtGui import QFontDatabase, QFont
        except Exception:
            return
        try:
            fn, _ = QFileDialog.getOpenFileName(self, "Load Font", "", "Fonts (*.ttf *.otf);;All Files (*.*)")
            if not fn:
                return
            fam = None
            try:
                fid = QFontDatabase.addApplicationFont(fn)
                if fid != -1:
                    fams = QFontDatabase.applicationFontFamilies(fid)
                    if fams:
                        fam = fams[0]
            except Exception as e:
                logging.getLogger(__name__).warning("Font add failed: %s", e)
            self.current_font_path = fn
            if fam:
                size = self.text_font.pointSize() if getattr(self, 'text_font', None) else 24
                try:
                    self.text_font = QFont(fam, size)
                except Exception:
                    pass
            try:
                # TextTab doesn't need font label updates (fonts controlled by mode files)
                pass
            except Exception:
                pass
            try:
                QMessageBox.information(self, "Font", f"Loaded font: {fam or os.path.basename(fn)}")
            except Exception:
                pass
        except Exception as e:
            logging.getLogger(__name__).error("Font load error: %s", e)
            try:
                QMessageBox.critical(self, "Font", f"Failed to load font: {e}")
            except Exception:
                pass
    
    def _on_custom_mode_requested(self, mode_path: str):
        """Custom mode load requested - load and start CustomVisual."""
        try:
            if not self.visual_director:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Visual Director Not Available",
                    "Visual Director system failed to initialize.\n\n"
                    "Check console for errors or contact support."
                )
                logging.getLogger(__name__).warning("[CustomVisual] VisualDirector not initialized")
                return
            
            # CRITICAL: Ensure spiral windows are created before loading mode
            # CustomVisual needs compositor to apply settings during initialization
            needs_timer_start = False  # Track if we need to start timer after mode loads
            if not self.spiral_windows:
                logging.getLogger(__name__).info("[CustomVisual] Auto-enabling spiral for mode load")
                # Auto-enable spiral if not already active
                if not self.spiral_enabled:
                    # Set flag but DON'T start timer yet - mode needs to load first to set opacity
                    self.spiral_enabled = True
                    needs_timer_start = True
                    try:
                        # Update UI checkbox to reflect auto-enable
                        if hasattr(self, 'panel_mesmerloom') and hasattr(self.panel_mesmerloom, 'check_spiral_enable'):
                            self.panel_mesmerloom.check_spiral_enable.setChecked(True)
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"[CustomVisual] Failed to update spiral checkbox: {e}")
                
                # CRITICAL: Set flag to defer compositor timer (complete silence until Launch)
                self._defer_compositor_timer = True
                logging.getLogger(__name__).info("[CustomVisual] Set flag to defer compositor timer start")
                
                # Create spiral windows
                self._create_spiral_windows()
                
                # CRITICAL: Stop compositor timers immediately after creation (complete silence until Launch)
                if self.spiral_windows:
                    for win in self.spiral_windows:
                        if hasattr(win, 'comp') and hasattr(win.comp, '_stop_timer'):
                            win.comp._stop_timer()
                            logging.getLogger(__name__).info("[CustomVisual] Stopped compositor timer (will restart on Launch)")
                
                # Wait a moment for windows to initialize (ensure compositor is ready)
                if not self.spiral_windows:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self,
                        "Spiral Initialization Failed",
                        "Failed to automatically create spiral overlay.\n\n"
                        "Try manually enabling the spiral checkbox before loading modes."
                    )
                    logging.getLogger(__name__).error("[CustomVisual] Failed to auto-create spiral windows")
                    return
            
            from pathlib import Path
            mode_file = Path(mode_path)
            
            logging.getLogger(__name__).info(f"[CustomVisual] Loading mode: {mode_file.name}")
            
            # CRITICAL: If already running (from Launch), stop completely before reloading
            # This prevents race conditions where update() advances frames during mode transition
            if self.running:
                logging.getLogger(__name__).info("[CustomVisual] Already running - stopping before reload")
                self.stop_all()
            
            # CRITICAL: Pause BEFORE loading mode to prevent any frames from advancing
            # This prevents cycler from triggering during mode load transition
            if hasattr(self, 'visual_director') and self.visual_director:
                self.visual_director.pause()
                logging.getLogger(__name__).info("[CustomVisual] Paused visual director BEFORE mode load (prevents auto-advance)")
            
            # Load custom visual
            if self.visual_director.select_custom_visual(mode_file):
                # Note: MesmerLoom controls are now always locked (simplified UI)
                # Custom modes define all settings in JSON
                logging.getLogger(__name__).info(f"[CustomVisual] Started custom mode: {mode_file.name}")
                
                # Keep paused - user expects mode to load in "silent" state
                # Spiral timer will start when Launch button is pressed
                logging.getLogger(__name__).info("[CustomVisual] Visual director remains paused (silent state - awaiting Launch)")
                
                # DON'T start spiral timer here - nothing should render until Launch
                # Timer will be started in Launch button handler
                logging.getLogger(__name__).info("[CustomVisual] Spiral timer will start on Launch (complete silence until then)")
                
                # Store needs_timer_start flag for Launch handler
                self._needs_spiral_timer_init = needs_timer_start
                
                # Continue to next iteration (skip timer start logic)
                if True:  # Skip the timer start block
                    pass
                else:
                    # OLD CODE (disabled): This block started timer immediately
                    # NOW: Timer starts only on Launch press
                    pass
                
                if False:  # Disable old timer start logic
                        logging.getLogger(__name__).info("[CustomVisual] Timer already active, skipping start()")
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Custom Mode Load Failed",
                    f"Failed to load custom mode:\n{mode_file.name}\n\n"
                    "Possible issues:\n"
                    "- Invalid JSON format\n"
                    "- Missing required fields\n"
                    "- Incompatible version\n\n"
                    "Check console for detailed error messages."
                )
                logging.getLogger(__name__).error(f"[CustomVisual] Failed to load mode: {mode_file.name}")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Custom Mode Error",
                f"Error loading custom mode:\n\n{e}\n\n"
                "Check console for full traceback."
            )
            logging.getLogger(__name__).error(f"[CustomVisual] Load error: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_reload_custom_mode(self):
        """Reload current custom mode from disk (for live editing)."""
        try:
            if not self.visual_director:
                logging.getLogger(__name__).warning("[CustomVisual] VisualDirector not initialized")
                return
            
            # Check if custom mode is active
            if not self.visual_director.is_custom_mode_active():
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    "No Custom Mode Active",
                    "Please load a custom mode first before reloading."
                )
                return
            
            from ..mesmerloom.custom_visual import CustomVisual
            if isinstance(self.visual_director.current_visual, CustomVisual):
                mode_name = self.visual_director.current_visual.mode_name
                logging.getLogger(__name__).info(f"[CustomVisual] Reloading mode '{mode_name}' from disk...")
                
                # Reload from disk
                if self.visual_director.current_visual.reload_from_disk():
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.information(
                        self,
                        "Mode Reloaded",
                        f"Successfully reloaded '{mode_name}' from disk.\n\n"
                        "All settings have been refreshed."
                    )
                    logging.getLogger(__name__).info(f"[CustomVisual] Reload successful: {mode_name}")
                else:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self,
                        "Reload Failed",
                        f"Failed to reload '{mode_name}'.\n\n"
                        "Check console for error details."
                    )
                    logging.getLogger(__name__).error(f"[CustomVisual] Reload failed: {mode_name}")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Reload Error",
                f"Error reloading custom mode:\n\n{e}"
            )
            logging.getLogger(__name__).error(f"[CustomVisual] Reload error: {e}")
            import traceback
            traceback.print_exc()
    
    def _rebuild_media_library(self, images_dir: Optional[Path] = None, videos_dir: Optional[Path] = None, silent: bool = False):
        """Rebuild ThemeBank with custom or default media directories.
        
        Args:
            images_dir: Custom images directory (None = use default MEDIA/Images)
            videos_dir: Custom videos directory (None = use default MEDIA/Videos)
            silent: If True, suppress success notification popup (for mode loading)
        """
        try:
            from ..content.theme import ThemeConfig
            
            # Store custom directories so they persist across mode loads
            self._custom_images_dir = images_dir
            self._custom_videos_dir = videos_dir
            
            # Get base media directory
            media_dir = Path(__file__).parent.parent.parent / "MEDIA"
            
            # Use custom directories or defaults
            images_path = images_dir if images_dir else (media_dir / "Images")
            videos_path = videos_dir if videos_dir else (media_dir / "Videos")
            
            logging.getLogger(__name__).info(
                f"[MesmerLoom] Rebuilding media library:\n"
                f"  Images: {images_path}\n"
                f"  Videos: {videos_path}"
            )
            logging.getLogger(__name__).info(f"[MesmerLoom] Stored custom dirs: images={self._custom_images_dir}, videos={self._custom_videos_dir}")
            
            # Build media lists
            test_images = []
            test_videos = []
            test_text = [
                "Welcome to MesmerGlass",
                "Trance Visual Programs",
                "Relax and Focus",
                "Let Go",
                "Deep and Deeper",
                "Spiral Down",
                "Good Subject",
                "Obey and Enjoy"
            ]
            
            # Determine root_path FIRST (needed for relative path calculation)
            root_path_for_scanning = images_dir.parent if images_dir else media_dir
            logging.getLogger(__name__).info(f"[MesmerLoom] root_path for scanning: {root_path_for_scanning}")
            
            # Scan images directory
            if images_path.exists() and images_path.is_dir():
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                    for img_path in images_path.glob(ext):
                        # Store relative path from root_path
                        try:
                            relative_path = img_path.relative_to(root_path_for_scanning)
                            test_images.append(str(relative_path))
                        except ValueError:
                            # If relative_to fails, store as absolute (shouldn't happen)
                            logging.getLogger(__name__).warning(f"[MesmerLoom] Could not make path relative, using absolute: {img_path}")
                            test_images.append(str(img_path))
                
                # Show first few images as sample
                if test_images:
                    sample = test_images[:3] if len(test_images) > 3 else test_images
                    logging.getLogger(__name__).info(f"[MesmerLoom] Sample image paths (relative to root): {sample}")
            else:
                logging.getLogger(__name__).warning(f"[MesmerLoom] Images directory does not exist: {images_path}")
            
            # Scan videos directory
            if videos_path.exists() and videos_path.is_dir():
                for ext in ['*.mp4', '*.webm', '*.mkv', '*.avi']:
                    for vid_path in videos_path.glob(ext):
                        # Store relative path from root_path
                        try:
                            relative_path = vid_path.relative_to(root_path_for_scanning)
                            test_videos.append(str(relative_path))
                        except ValueError:
                            # If relative_to fails, store as absolute (shouldn't happen)
                            logging.getLogger(__name__).warning(f"[MesmerLoom] Could not make path relative, using absolute: {vid_path}")
                            test_videos.append(str(vid_path))
            else:
                logging.getLogger(__name__).warning(f"[MesmerLoom] Videos directory does not exist: {videos_path}")
            
            # Create new theme config
            default_theme = ThemeConfig(
                name="Media Library",
                enabled=True,
                image_path=test_images,
                animation_path=test_videos,
                font_path=[],
                text_line=test_text
            )
            
            # Use root_path calculated earlier (consistent with path scanning)
            root_path = root_path_for_scanning
            if not root_path.exists():
                root_path = media_dir
                logging.getLogger(__name__).warning(f"[MesmerLoom] root_path does not exist, falling back to media_dir: {media_dir}")
            
            self.theme_bank = ThemeBank(
                themes=[default_theme],
                root_path=root_path,
                image_cache_size=64
            )
            
            # Activate the theme
            if len(self.theme_bank._themes) > 0:
                self.theme_bank.set_active_themes(primary_index=1)
            
            img_count = len(test_images)
            vid_count = len(test_videos)
            txt_count = len(test_text)
            logging.getLogger(__name__).info(
                f"[MesmerLoom] Media library rebuilt: "
                f"{img_count} images, {vid_count} videos, {txt_count} text lines"
            )
            
            # Update VisualDirector's theme_bank reference if it exists
            if self.visual_director and hasattr(self.visual_director, 'theme_bank'):
                self.visual_director.theme_bank = self.theme_bank
                logging.getLogger(__name__).info("[MesmerLoom] Updated VisualDirector's theme_bank reference")
                
                # If a custom mode is active, reload its media with the new ThemeBank
                if hasattr(self.visual_director, 'current_visual') and self.visual_director.current_visual:
                    from ..mesmerloom.custom_visual import CustomVisual
                    if isinstance(self.visual_director.current_visual, CustomVisual):
                        logging.getLogger(__name__).info("[MesmerLoom] Reloading custom mode media with new ThemeBank...")
                        # Re-apply media settings to pick up new ThemeBank
                        self.visual_director.current_visual._apply_media_settings()
                        logging.getLogger(__name__).info("[MesmerLoom] Custom mode media reloaded")
            
            # Show success notification (unless silent mode for mode loading)
            if not silent:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    "Media Library Updated",
                    f"Successfully loaded media from:\n\n"
                    f"Images: {images_path.name if not images_dir else images_path}\n"
                    f"Videos: {videos_path.name if not videos_dir else videos_path}\n\n"
                    f"Found: {img_count} images, {vid_count} videos"
                )
            
        except Exception as e:
            logging.getLogger(__name__).error(f"[MesmerLoom] Media library rebuild failed: {e}")
            import traceback
            traceback.print_exc()
            
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Media Library Error",
                f"Failed to rebuild media library:\n\n{e}"
            )
    
    def _load_media_bank_config(self):
        """Load Media Bank configuration from file."""
        config_path = Path(__file__).parent.parent.parent / "media_bank.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._media_bank = json.load(f)
                logging.getLogger(__name__).info(f"[MediaBank] Loaded {len(self._media_bank)} entries from config")
            except Exception as e:
                logging.getLogger(__name__).error(f"[MediaBank] Failed to load config: {e}")
                self._media_bank = []
        else:
            logging.getLogger(__name__).info("[MediaBank] No saved config found - starting with empty bank")
    
    def _save_media_bank_config(self):
        """Save Media Bank configuration to file."""
        config_path = Path(__file__).parent.parent.parent / "media_bank.json"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._media_bank, f, indent=2, ensure_ascii=False)
            logging.getLogger(__name__).info(f"[MediaBank] Saved {len(self._media_bank)} entries to config")
        except Exception as e:
            logging.getLogger(__name__).error(f"[MediaBank] Failed to save config: {e}")
    
    def _rebuild_media_library_from_selections(self, bank_indices: List[int], silent: bool = True):
        """Rebuild ThemeBank using only selected Media Bank indices.
        
        This is called when loading a custom mode that specifies which
        Media Bank entries to use via bank_selections in the JSON.
        
        Args:
            bank_indices: List of indices into self._media_bank array
            silent: If True, suppress notifications (default for mode loading)
        """
        try:
            from ..content.theme import ThemeConfig
            
            logging.getLogger(__name__).info(f"[MediaBank] Rebuilding from bank selections: {bank_indices}")
            
            # Validate indices
            valid_indices = [i for i in bank_indices if 0 <= i < len(self._media_bank)]
            if len(valid_indices) != len(bank_indices):
                logging.getLogger(__name__).warning(
                    f"[MediaBank] Some indices out of range. Using valid indices only: {valid_indices}"
                )
            
            if not valid_indices:
                logging.getLogger(__name__).error("[MediaBank] No valid bank indices provided")
                return
            
            # Collect paths from selected bank entries
            images_dirs = []
            videos_dirs = []
            
            for idx in valid_indices:
                entry = self._media_bank[idx]
                if not entry.get('enabled', True):
                    logging.getLogger(__name__).info(f"[MediaBank] Skipping disabled entry: {entry['name']}")
                    continue
                
                entry_type = entry.get('type', 'images')
                entry_path = Path(entry['path'])
                
                if entry_type in ('images', 'both') and entry_path.exists():
                    images_dirs.append(entry_path)
                if entry_type in ('videos', 'both') and entry_path.exists():
                    videos_dirs.append(entry_path)
            
            logging.getLogger(__name__).info(
                f"[MediaBank] Selected directories:\n"
                f"  Images: {len(images_dirs)} directories\n"
                f"  Videos: {len(videos_dirs)} directories"
            )
            
            # Build media lists
            test_images = []
            test_videos = []
            test_text = [
                "Welcome to MesmerGlass",
                "Trance Visual Programs",
                "Relax and Focus",
                "Let Go",
                "Deep and Deeper",
                "Spiral Down",
                "Good Subject",
                "Obey and Enjoy"
            ]
            
            # Determine root_path (use first image directory's parent, or default MEDIA)
            media_dir = Path(__file__).parent.parent.parent / "MEDIA"
            root_path_for_scanning = images_dirs[0].parent if images_dirs else media_dir
            logging.getLogger(__name__).info(f"[MediaBank] root_path for scanning: {root_path_for_scanning}")
            
            # Scan all selected image directories
            for img_dir in images_dirs:
                if img_dir.is_dir():
                    for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
                        for img_path in img_dir.glob(ext):
                            try:
                                relative_path = img_path.relative_to(root_path_for_scanning)
                                test_images.append(str(relative_path))
                            except ValueError:
                                logging.getLogger(__name__).warning(
                                    f"[MediaBank] Could not make path relative, using absolute: {img_path}"
                                )
                                test_images.append(str(img_path))
            
            # Scan all selected video directories
            for vid_dir in videos_dirs:
                if vid_dir.is_dir():
                    for ext in ['*.mp4', '*.webm', '*.mkv', '*.avi']:
                        for vid_path in vid_dir.glob(ext):
                            try:
                                relative_path = vid_path.relative_to(root_path_for_scanning)
                                test_videos.append(str(relative_path))
                            except ValueError:
                                logging.getLogger(__name__).warning(
                                    f"[MediaBank] Could not make path relative, using absolute: {vid_path}"
                                )
                                test_videos.append(str(vid_path))
            
            # Create new theme config
            default_theme = ThemeConfig(
                name="Media Bank Selection",
                enabled=True,
                image_path=test_images,
                animation_path=test_videos,
                font_path=[],
                text_line=test_text
            )
            
            # Use calculated root_path
            root_path = root_path_for_scanning
            if not root_path.exists():
                root_path = media_dir
                logging.getLogger(__name__).warning(
                    f"[MediaBank] root_path does not exist, falling back to media_dir: {media_dir}"
                )
            
            self.theme_bank = ThemeBank(
                themes=[default_theme],
                root_path=root_path,
                image_cache_size=64
            )
            
            # Activate the theme
            if len(self.theme_bank._themes) > 0:
                self.theme_bank.set_active_themes(primary_index=1)
            
            img_count = len(test_images)
            vid_count = len(test_videos)
            txt_count = len(test_text)
            logging.getLogger(__name__).info(
                f"[MediaBank] Media library rebuilt from bank selections: "
                f"{img_count} images, {vid_count} videos, {txt_count} text lines"
            )
            
            # Update VisualDirector's theme_bank reference
            if self.visual_director and hasattr(self.visual_director, 'theme_bank'):
                self.visual_director.theme_bank = self.theme_bank
                logging.getLogger(__name__).info("[MediaBank] Updated VisualDirector's theme_bank reference")
            
        except Exception as e:
            logging.getLogger(__name__).error(f"[MediaBank] Rebuild from selections failed: {e}")
            import traceback
            traceback.print_exc()
    
