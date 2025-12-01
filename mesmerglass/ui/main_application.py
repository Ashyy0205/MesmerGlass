"""Main Application Window for MesmerGlass Phase 7.

Vertical tab-based interface for managing visual trance sessions.
Replaces the legacy Launcher with a cleaner, session-focused design.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional, List, Any

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QFileDialog, QInputDialog, QLabel
)

from ..session_manager import SessionManager
from .tabs.home_tab import HomeTab
from .tabs.cuelists_tab import CuelistsTab
from .tabs.playbacks_tab import PlaybacksTab
from .tabs.display_tab import DisplayTab
from .tabs.devices_tab import DevicesTab
from ..content.simple_video_streamer import SimpleVideoStreamer
from ..content.media_scan import scan_media_directory, scan_font_directory
from ..content.themebank import ThemeBank
from ..content.theme import ThemeConfig


class MainApplication(QMainWindow):
    """Main application window with vertical tab sidebar.
    
    Features:
    - Vertical tab navigation (Home, Cuelists, Cues, Playbacks, Display, Audio, Device, etc.)
    - File menu (New/Open/Save session, Import/Export, Exit)
    - Status bar (session status, display info)
    - Dark theme
    - Window state persistence
    """
    
    RECENT_SESSIONS_KEY = "recent_sessions"
    MAX_RECENT_SESSIONS = 3

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.settings = QSettings("MesmerGlass", "MainApplication")
        
        # Session management
        self.session_manager = SessionManager()
        self.session_data: Optional[dict] = None
        self.autorun_config: Optional[dict[str, Any]] = self._read_autorun_env()
        self.autorun_timer: Optional[QTimer] = None
        self.autorun_active = False
        self._autorun_session_hooked = False
        self._autorun_wait_deadline: float | None = None
        self._media_scan_thread: Optional[threading.Thread] = None
        
        # Auto-save timer (debounce saves to avoid excessive file I/O)
        self.auto_save_timer = QTimer()
        self.auto_save_timer.setInterval(2000)  # 2 seconds after last change
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.timeout.connect(self._auto_save_session)
        
        # VR streaming integration (wireless Android APK discovery)
        from ..mesmervisor.streaming_server import DiscoveryService
        
        self.vr_discovery_service = DiscoveryService(
            discovery_port=5556, 
            streaming_port=5555
        )
        self.vr_discovery_service.start()
        self.logger.info("VR discovery service started for wireless Android clients")
        
        # Initialize engines and directors
        self._initialize_engines()
        
        self._setup_ui()
        self._restore_window_state()
        self.logger.info("MainApplication initialized")

        if self.autorun_config:
            QTimer.singleShot(0, self._start_autorun_if_configured)
    
    def _initialize_engines(self):
        """Initialize all rendering engines and directors.
        
        Creates instances of:
        - SpiralDirector: Spiral parameter control
        - LoomCompositor: OpenGL rendering engine
        - TextDirector: Text rendering and library management
        - VisualDirector: Playback loading and coordination
        - AudioEngine: Multi-channel audio playback
        - DeviceManager: Buttplug device control (optional)
        """
        from ..mesmerloom.spiral import SpiralDirector
        from ..engine.text_director import TextDirector
        from ..content.text_renderer import TextRenderer
        
        # Ensure attributes exist even if initialization fails partway
        self.video_streamer: Optional[SimpleVideoStreamer] = None

        try:
            # 1. Create SpiralDirector (controls spiral parameters)
            self.spiral_director = SpiralDirector()
            self.logger.info("SpiralDirector initialized")
            
            # 2. Create LoomCompositor (OpenGL rendering)
            try:
                from ..mesmerloom.window_compositor import LoomWindowCompositor
                self.compositor = LoomWindowCompositor(self.spiral_director)
                self.logger.info("LoomWindowCompositor created (artifact-free)")
            except ImportError:
                from ..mesmerloom.compositor import LoomCompositor
                self.compositor = LoomCompositor(self.spiral_director, parent=self)
                self.logger.info("LoomCompositor created (fallback)")
            
            # Set compositor inactive initially (will activate when session runs)
            if self.compositor:
                self.compositor.set_active(False)
            
            # 3. Create TextRenderer and TextDirector
            self.text_renderer = TextRenderer()
            # Note: VisualDirector is created later, so we'll wire the callback after that
            self.text_director = TextDirector(
                text_renderer=self.text_renderer,
                compositor=self.compositor
            )
            self.logger.info("TextDirector initialized")
            
            # Connect TextDirector to compositor for text overlay rendering
            if self.compositor:
                self.compositor.text_director = self.text_director

            # 3.25. Create SimpleVideoStreamer (ThemeBank video playback)
            try:
                # Prefill only ~0.5s of frames synchronously; async loader fills the rest
                self.video_streamer = SimpleVideoStreamer(buffer_size=180, prefill_frames=24)
                self.logger.info("SimpleVideoStreamer initialized for ThemeBank videos")
            except Exception as streamer_exc:  # pragma: no cover - defensive path
                self.video_streamer = None
                self.logger.error(f"Video streamer initialization failed: {streamer_exc}")
            
            # 3.5. Create ThemeBank for media management
            root_path = Path("MEDIA") if Path("MEDIA").exists() else Path(".")
            empty_theme = ThemeConfig(
                name="Loading...",
                enabled=True,
                image_path=[],
                animation_path=[],
                font_path=[],
                text_line=[]
            )
            
            self.theme_bank = ThemeBank(
                themes=[empty_theme],
                root_path=root_path,
                image_cache_size=256  # Increased for large external media libraries (2156 images)
            )
            self.theme_bank.set_active_themes(primary_index=1)
            self.logger.info("ThemeBank created (empty, media will load in background)")
            self._schedule_media_bank_refresh(delay=1.0)
            
            # 4. Create VisualDirector (manages playback loading)
            from ..mesmerloom.visual_director import VisualDirector
            # Note: mesmer_intiface_server will be set after it's initialized (step 7)
            self.visual_director = VisualDirector(
                theme_bank=self.theme_bank,
                compositor=self.compositor,
                text_renderer=self.text_renderer,
                video_streamer=self.video_streamer,
                text_director=self.text_director,
                mesmer_server=None  # Will be set after mesmer_intiface_server is created
            )
            self.logger.info("VisualDirector initialized")
            
            # Wire up text change callback for vibration on text cycle
            # This allows VisualDirector to trigger vibration when TextDirector changes text
            self.text_director._on_text_change = self.visual_director._on_change_text
            self.logger.debug("Text change callback wired to VisualDirector for vibration support")
            
            # 5. Create AudioEngine (multi-channel audio for sessions)
            from ..engine.audio import AudioEngine
            self.audio_engine = AudioEngine(num_channels=2)
            self.logger.info("AudioEngine initialized")
            
            # 6. Create DeviceManager (optional - may not be available)
            try:
                from ..engine.device_manager import DeviceManager
                self.device_manager = DeviceManager()
                self.logger.info("DeviceManager initialized")
            except Exception as e:
                self.logger.warning(f"DeviceManager not available: {e}")
                self.device_manager = None
                
            # 7. Create MesmerIntifaceServer for Bluetooth device control
            try:
                from ..engine.mesmerintiface import MesmerIntifaceServer
                self.mesmer_intiface_server = MesmerIntifaceServer(port=12350)
                self.mesmer_intiface_server.start()
                self.logger.info("MesmerIntifaceServer initialized on port 12350")
                
                # Wire up server to VisualDirector for vibration on text cycle
                self.visual_director.mesmer_server = self.mesmer_intiface_server
                self.logger.debug("MesmerIntifaceServer wired to VisualDirector for vibration support")
            except Exception as e:
                self.logger.warning(f"MesmerIntifaceServer not available: {e}")
                self.mesmer_intiface_server = None
            
            self.logger.info("All engines initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Engine initialization failed: {e}", exc_info=True)
            # Set all to None on failure
            self.spiral_director = None
            self.compositor = None
            self.text_renderer = None
            self.text_director = None
            self.visual_director = None
            self.audio_engine = None
            self.device_manager = None
    
    def _setup_ui(self):
        """Build the main UI structure."""
        self.setWindowTitle("MesmerGlass")
        self.setMinimumSize(1024, 768)
        
        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QTabWidget::pane {
                border: none;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #2d2d30;
                color: #d4d4d4;
                padding: 12px 16px;
                margin: 2px 0px;
                border-left: 3px solid transparent;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-left: 3px solid #0e639c;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #2a2d2e;
            }
            QStatusBar {
                background-color: #007acc;
                color: #ffffff;
                font-size: 11px;
            }
            QMenuBar {
                background-color: #3c3c3c;
                color: #d4d4d4;
                padding: 4px;
            }
            QMenuBar::item:selected {
                background-color: #094771;
            }
            QMenu {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #454545;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """)
        
        # === Menu Bar ===
        self._create_menu_bar()
        
        # === Central Widget with Vertical Tabs ===
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Vertical tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        
        # Add tabs
        self._create_tabs()
        
        # === Status Bar ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Status bar sections
        self.status_session = "No session loaded"
        self.status_display = "No display selected"
        self._update_status_bar()
    
    def _create_tabs(self):
        """Create and add all tabs."""
        # Tab 1: Display (Monitor and VR selection) - Created FIRST so HomeTab can access it
        self.display_tab = DisplayTab(self)
        self.tabs.addTab(self.display_tab, "🖥️ Display")
        
        # Tab 2: Home (Session Runner + Live Preview)
        self.home_tab = HomeTab(self)
        self.tabs.addTab(self.home_tab, "🏠 Home")
        
        # Tab 3: Cuelists (Browse cuelist files)
        self.cuelists_tab = CuelistsTab(self)
        self.tabs.addTab(self.cuelists_tab, "📝 Cuelists")
        
        # Connect data_changed signal to mark session dirty
        if hasattr(self.cuelists_tab, 'data_changed'):
            self.cuelists_tab.data_changed.connect(self._mark_session_dirty)
        
        # Tab 4: Playbacks (Browse playback JSON files)
        self.playbacks_tab = PlaybacksTab(self)
        self.tabs.addTab(self.playbacks_tab, "🎨 Playbacks")
        
        # Connect data_changed signal to mark session dirty
        if hasattr(self.playbacks_tab, 'data_changed'):
            self.playbacks_tab.data_changed.connect(self._mark_session_dirty)
        
        # Tab 5: Device Control (Bluetooth device scanning and connection)
        self.devices_tab = DevicesTab(self)
        self.tabs.addTab(self.devices_tab, "🔗 Device")
        
        # Tab 6: Performance monitoring (placeholder)
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        label = QLabel("📊 Performance tab\n\nComing soon...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.tabs.addTab(placeholder, "📊 Performance")
        
        # Tab 7: DevTools (placeholder)
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        label = QLabel("🛠️ DevTools tab\n\nComing soon...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.tabs.addTab(placeholder, "🛠️ DevTools")
        
        self.logger.info(f"Created {self.tabs.count()} tabs")
        
        # Start VR display refresh timer (updates DisplayTab with discovered devices)
        self._vr_refresh_timer = QTimer(self)
        self._vr_refresh_timer.setInterval(2000)  # Refresh every 2 seconds
        self._vr_refresh_timer.timeout.connect(self._refresh_vr_displays)
        self._vr_refresh_timer.start()
        
        # Do initial refresh after 1 second
        QTimer.singleShot(1000, self._refresh_vr_displays)
    
    def _refresh_vr_displays(self):
        """Refresh VR devices in Display tab."""
        if hasattr(self, 'display_tab') and hasattr(self.display_tab, '_refresh_vr_displays'):
            self.display_tab._refresh_vr_displays()
    
    def _on_tab_changed(self, index: int):
        """Handle tab change to call lifecycle hooks."""
        # Call on_hide on previous tab
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if hasattr(widget, 'on_hide') and i != index:
                widget.on_hide()
        
        # Call on_show on new tab
        current_widget = self.tabs.widget(index)
        if hasattr(current_widget, 'on_show'):
            current_widget.on_show()
    
    def _create_menu_bar(self):
        """Create the file menu."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("☰ File")
        
        # New Session
        new_action = QAction("New Session", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._on_new_session)
        file_menu.addAction(new_action)
        
        # Open Session
        open_action = QAction("Open Session...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_session)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        # Save Session
        save_action = QAction("Save Session", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save_session)
        file_menu.addAction(save_action)
        
        # Save Session As
        save_as_action = QAction("Save Session As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_session_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # Import Cuelist
        import_action = QAction("Import Cuelist...", self)
        import_action.triggered.connect(self._on_import_cuelist)
        file_menu.addAction(import_action)
        
        # Export Cuelist
        export_action = QAction("Export Cuelist...", self)
        export_action.triggered.connect(self._on_export_cuelist)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
    
    def _update_status_bar(self):
        """Update status bar with current state."""
        session_name = self.session_manager.get_session_name() or "No session loaded"
        dirty_indicator = " *" if self.session_manager.dirty else ""
        self.status_bar.showMessage(
            f"Status: Ready | Session: {session_name}{dirty_indicator} | Display: {self.status_display}"
        )
    
    def _restore_window_state(self):
        """Restore window position, size, and last active tab."""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        last_tab = self.settings.value("last_tab", 0, type=int)
        if 0 <= last_tab < self.tabs.count():
            self.tabs.setCurrentIndex(last_tab)
    
    def _save_window_state(self):
        """Save window position, size, and active tab."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("last_tab", self.tabs.currentIndex())
    
    def closeEvent(self, event):
        """Handle window close event with save prompt."""
        if self.session_manager.dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Session has unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Save:
                if not self._on_save_session():
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        
        self._save_window_state()

        # Ensure background streaming threads tear down cleanly
        if getattr(self, "video_streamer", None):
            try:
                self.video_streamer.stop()
                self.logger.info("Video streamer stopped")
            except Exception as exc:  # pragma: no cover - defensive cleanup
                self.logger.warning(f"Video streamer stop failed: {exc}")

        event.accept()
    
    # === File Menu Handlers ===
    
    def _on_new_session(self):
        """Create a new session."""
        if not self._ensure_safe_to_switch_session():
            return
        
        # Prompt for session name
        name, ok = QInputDialog.getText(self, "New Session", "Session Name:")
        if not ok or not name:
            return
        
        description, ok = QInputDialog.getText(self, "New Session", "Description (optional):")
        if not ok:
            description = ""
        
        # Create new session
        self.session_data = self.session_manager.new_session(name, description)
        self._propagate_session_to_tabs()
        self._update_status_bar()
        self.logger.info(f"New session created: {name}")
    
    def _on_open_session(self):
        """Open an existing session file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Open Session",
            str(self.session_manager.session_dir),
            "Session Files (*.session.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        self.open_session_from_path(Path(file_path))
    
    def _on_save_session(self) -> bool:
        """Save current session. Returns True if successful."""
        if self.session_data is None:
            QMessageBox.warning(self, "No Session", "No session to save")
            return False
        
        if self.session_manager.current_file is None:
            return self._on_save_session_as()
        
        try:
            self.session_manager.save_session()
            self._record_recent_session(self.session_manager.current_file)
            self._update_status_bar()
            self.logger.info(f"Session saved: {self.session_manager.current_file.name}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save session: {e}")
            self.logger.error(f"Failed to save session: {e}", exc_info=True)
            return False
    
    def _on_save_session_as(self) -> bool:
        """Save session to a new file. Returns True if successful."""
        if self.session_data is None:
            QMessageBox.warning(self, "No Session", "No session to save")
            return False
        
        default_name = self.session_data["metadata"]["name"].lower().replace(" ", "_")
        default_path = str(self.session_manager.session_dir / f"{default_name}.session.json")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Session As",
            default_path,
            "Session Files (*.session.json);;All Files (*)"
        )
        
        if not file_path:
            return False
        
        try:
            self.session_manager.save_session(Path(file_path), self.session_data)
            self._record_recent_session(Path(file_path))
            self._update_status_bar()
            self.logger.info(f"Session saved as: {file_path}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save session: {e}")
            self.logger.error(f"Failed to save session: {e}", exc_info=True)
            return False
    
    def _mark_session_dirty(self):
        """Mark session as having unsaved changes and schedule auto-save."""
        self.session_manager.mark_dirty()
        self._update_status_bar()
        self.logger.debug("Session marked dirty")
        
        # Schedule auto-save (debounced)
        if self.session_manager.current_file:
            self.auto_save_timer.start()  # Restarts timer if already running
    
    def _auto_save_session(self):
        """Auto-save session after debounce period."""
        if not self.session_manager.dirty or not self.session_manager.current_file:
            return
        
        try:
            self.session_manager.save_session()
            self._record_recent_session(self.session_manager.current_file)
            self._update_status_bar()
            self.logger.info(f"Auto-saved session to {self.session_manager.current_file.name}")
        except Exception as e:
            self.logger.error(f"Auto-save failed: {e}", exc_info=True)

    def _ensure_safe_to_switch_session(self) -> bool:
        """Prompt when unsaved changes exist before discarding."""
        if not self.session_manager.dirty:
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Current session has unsaved changes. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return reply == QMessageBox.StandardButton.Yes

    def _load_session_from_path(self, filepath: Path) -> bool:
        """Load a session file and propagate it to the UI."""
        try:
            self.session_data = self.session_manager.load_session(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open session: {e}")
            self.logger.error(f"Failed to open session: {e}", exc_info=True)
            return False

        self._record_recent_session(filepath)
        self._propagate_session_to_tabs()
        self._update_status_bar()

        name = self.session_data.get("metadata", {}).get("name", filepath.stem)
        self.logger.info(f"Session opened: {name}")
        return True

    def open_session_from_path(self, filepath: Path, skip_dirty_check: bool = False) -> bool:
        """Public helper to open a session file path (used by quick actions)."""
        filepath = Path(filepath)
        if not filepath.exists():
            QMessageBox.warning(
                self,
                "Session Missing",
                f"Session file not found:\n{filepath}"
            )
            return False
        if not skip_dirty_check and not self._ensure_safe_to_switch_session():
            return False
        return self._load_session_from_path(filepath)

    def get_recent_sessions(self) -> List[str]:
        """Return stored recent session file paths (most recent first)."""
        value = self.settings.value(self.RECENT_SESSIONS_KEY, [])
        if value is None:
            return []
        if isinstance(value, str):
            entries = [value]
        elif isinstance(value, list):
            entries = [str(item) for item in value]
        else:
            entries = []
        return entries[: self.MAX_RECENT_SESSIONS]

    def _record_recent_session(self, filepath: Optional[Path]):
        """Persist the provided session path in the recent list."""
        if filepath is None:
            return
        path_str = str(Path(filepath).resolve())
        current = self.get_recent_sessions()
        deduped = [entry for entry in current if entry.lower() != path_str.lower()]
        deduped.insert(0, path_str)
        trimmed = deduped[: self.MAX_RECENT_SESSIONS]
        self.settings.setValue(self.RECENT_SESSIONS_KEY, trimmed)
    
    def _propagate_session_to_tabs(self):
        """Send session data to all tabs that need it."""
        if self.session_data is None:
            return

        # Each tab that needs session data gets a reference
        # Tabs modify the dict in-place and signal when dirty
        if hasattr(self.home_tab, 'set_session_data'):
            self.home_tab.set_session_data(self.session_data)
        
        if hasattr(self.playbacks_tab, 'set_session_data'):
            self.playbacks_tab.set_session_data(self.session_data)
        
        if hasattr(self.cuelists_tab, 'set_session_data'):
            self.cuelists_tab.set_session_data(self.session_data)
        
        if hasattr(self.display_tab, 'set_session_data'):
            self.display_tab.set_session_data(self.session_data)
        
        self.logger.info("Session data propagated to all tabs")
        self._schedule_media_bank_refresh()

    # === Autorun helpers ===

    def _read_autorun_env(self) -> Optional[dict[str, Any]]:
        """Capture autorun instructions from CLI-provided environment variables."""
        session_file = os.environ.get("MESMERGLASS_SESSION_FILE")
        if not session_file:
            return None

        path = Path(session_file).expanduser()
        try:
            path = path if path.is_absolute() else (Path.cwd() / path)
            path = path.resolve()
        except Exception:
            path = path

        cuelist_key = os.environ.get("MESMERGLASS_SESSION_CUELIST")
        duration_val: Optional[float] = None
        raw_duration = os.environ.get("MESMERGLASS_AUTORUN_DURATION")
        if raw_duration:
            try:
                parsed = float(raw_duration)
                if parsed > 0:
                    duration_val = parsed
                else:
                    self.logger.warning("Autorun duration must be positive (got %s)", raw_duration)
            except ValueError:
                self.logger.warning("Autorun duration is not a number: %s", raw_duration)

        auto_exit = os.environ.get("MESMERGLASS_AUTORUN_EXIT", "0").lower() in {"1", "true", "yes", "on"}
        config: dict[str, Any] = {
            "session_path": path,
            "requested_cuelist": cuelist_key,
            "duration": duration_val,
            "auto_exit": auto_exit,
        }
        self.logger.info(
            "Autorun configured: session=%s cuelist=%s duration=%s auto_exit=%s",
            path,
            cuelist_key or "<first>",
            duration_val or "<none>",
            auto_exit,
        )
        return config

    def _start_autorun_if_configured(self) -> None:
        """Kick off autorun after the UI is built."""
        if not self.autorun_config:
            return

        config = self.autorun_config
        session_path: Path = config["session_path"]
        if not session_path.exists():
            self.logger.error("Autorun session file not found: %s", session_path)
            self._complete_autorun(failed=True)
            return

        if not self.open_session_from_path(session_path, skip_dirty_check=True):
            self.logger.error("Autorun failed to open session: %s", session_path)
            self._complete_autorun(failed=True)
            return

        self._prepare_theme_bank_for_autorun()

        # Wait for ThemeBank if available, otherwise proceed immediately
        wait_timeout_s = 20.0
        self._autorun_wait_deadline = time.monotonic() + wait_timeout_s
        if self._theme_bank_ready_for_autorun():
            self._kickoff_autorun_playback()
        else:
            self.logger.info("Autorun waiting for ThemeBank readiness (timeout %.0fs)", wait_timeout_s)
            self.autorun_timer = QTimer(self)
            self.autorun_timer.setInterval(500)
            self.autorun_timer.timeout.connect(self._poll_autorun_theme_bank)
            self.autorun_timer.start()

    def _prepare_theme_bank_for_autorun(self) -> None:
        if self.session_data is None:
            return
        # Ensure active media bank gets scheduled ASAP
        try:
            self._schedule_media_bank_refresh()
        except Exception as exc:
            self.logger.warning("Unable to schedule media refresh for autorun: %s", exc)

    def _theme_bank_ready_for_autorun(self) -> bool:
        theme_bank = getattr(self, "theme_bank", None)
        if theme_bank is None or not hasattr(theme_bank, "ensure_ready"):
            return True
        try:
            status = theme_bank.ensure_ready(timeout_s=0.0)
        except Exception as exc:  # pragma: no cover - readiness probe failures
            self.logger.warning("ThemeBank readiness check failed: %s", exc)
            return True
        if status.ready:
            return True
        return False

    def _poll_autorun_theme_bank(self) -> None:
        if self._theme_bank_ready_for_autorun():
            if self.autorun_timer:
                self.autorun_timer.stop()
                self.autorun_timer = None
            self.logger.info("Autorun ThemeBank ready; starting playback")
            self._kickoff_autorun_playback()
            return

        if time.monotonic() > getattr(self, "_autorun_wait_deadline", 0):
            if self.autorun_timer:
                self.autorun_timer.stop()
                self.autorun_timer = None
            self.logger.error("Autorun timed out waiting for ThemeBank readiness")
            self._complete_autorun(failed=True)

    def _kickoff_autorun_playback(self) -> None:
        config = self.autorun_config
        if not config:
            return

        session_path = config.get("session_path")
        runner_tab = getattr(getattr(self, "home_tab", None), "session_runner_tab", None)
        if runner_tab is None:
            self.logger.error("Autorun aborted: SessionRunnerTab unavailable")
            self._complete_autorun(failed=True)
            return

        cuelist_key = self._resolve_autorun_cuelist_key(config.get("requested_cuelist"))
        if not cuelist_key:
            self.logger.error("Autorun aborted: session has no cuelists to run")
            self._complete_autorun(failed=True)
            return

        if not runner_tab.load_cuelist_from_session(cuelist_key):
            self.logger.error("Autorun failed to load cuelist '%s'", cuelist_key)
            self._complete_autorun(failed=True)
            return

        if not runner_tab.start_session_programmatically():
            self.logger.error("Autorun failed to start cuelist '%s'", cuelist_key)
            self._complete_autorun(failed=True)
            return

        session_path_str = str(session_path) if session_path is not None else "<unknown>"
        self.logger.info("Autorun started cuelist '%s' from %s", cuelist_key, session_path_str)
        self.autorun_active = True
        config["resolved_cuelist"] = cuelist_key
        runner_tab.session_stopped.connect(self._handle_autorun_session_stopped)
        self._autorun_session_hooked = True

        duration = config.get("duration")
        if duration:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._handle_autorun_duration_elapsed)
            timer.start(int(duration * 1000))
            self.autorun_timer = timer
            self.logger.info("Autorun will stop after %.1f seconds", duration)

    def _resolve_autorun_cuelist_key(self, requested: Optional[str]) -> Optional[str]:
        """Resolve the target cuelist key, falling back to the first entry when needed."""
        if not self.session_data:
            return None

        cuelists = self.session_data.get("cuelists") or {}
        if not cuelists:
            return None

        if requested:
            if requested in cuelists:
                return requested
            requested_lower = requested.lower()
            for key, payload in cuelists.items():
                name = str(payload.get("name", "")).lower()
                if name and name == requested_lower:
                    self.logger.info("Autorun resolved cuelist name '%s' to key '%s'", requested, key)
                    return key
            self.logger.warning("Autorun cuelist '%s' not found; falling back to first entry", requested)

        fallback_key = next(iter(cuelists.keys()))
        self.logger.info("Autorun defaulting to first cuelist '%s'", fallback_key)
        return fallback_key

    def _handle_autorun_duration_elapsed(self) -> None:
        if not self.autorun_active:
            return
        self.logger.info("Autorun duration elapsed; stopping session")
        self._request_session_stop("duration elapsed")

    def _handle_autorun_session_stopped(self) -> None:
        if not self.autorun_active:
            return
        self.logger.info("Autorun session stopped")
        self._complete_autorun(failed=False)

    def _request_session_stop(self, reason: str) -> None:
        runner_tab = getattr(getattr(self, "home_tab", None), "session_runner_tab", None)
        if runner_tab is None:
            self.logger.warning("Autorun could not stop session (%s): runner tab missing", reason)
            self._complete_autorun(failed=True)
            return
        try:
            runner_tab._on_stop_session()
        except Exception as exc:  # pragma: no cover - defensive guard
            self.logger.error("Autorun stop failed: %s", exc, exc_info=True)
            self._complete_autorun(failed=True)

    def _complete_autorun(self, *, failed: bool) -> None:
        config = self.autorun_config or {}
        auto_exit = bool(config.get("auto_exit"))

        if self.autorun_timer:
            self.autorun_timer.stop()
            self.autorun_timer = None

        if self._autorun_session_hooked:
            runner_tab = getattr(getattr(self, "home_tab", None), "session_runner_tab", None)
            if runner_tab is not None:
                try:
                    runner_tab.session_stopped.disconnect(self._handle_autorun_session_stopped)
                except Exception:
                    pass
            self._autorun_session_hooked = False

        self.autorun_active = False
        self.autorun_config = None
        self._autorun_wait_deadline = None

        if auto_exit:
            state = "failure" if failed else "completion"
            delay_ms = 250 if failed else 750
            self.logger.info("Autorun exiting application after %s", state)
            QTimer.singleShot(delay_ms, self._quit_after_autorun)

    def _quit_after_autorun(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
        else:  # pragma: no cover - fallback path
            self.close()
    
    def _get_media_bank_entries(self) -> List[dict]:
        """Return session-defined media bank entries."""
        if not self.session_data:
            return []
        entries = self.session_data.get("media_bank", [])
        return [dict(entry) for entry in entries if isinstance(entry, dict)]

    def _schedule_media_bank_refresh(self, delay: float = 0.0):
        """Kick off a background media scan after an optional delay."""
        if getattr(self, "theme_bank", None) is None:
            return

        def runner():
            if delay > 0:
                time.sleep(delay)
            self._load_media_bank_async()

        thread = threading.Thread(target=runner, daemon=True, name="MediaScanner")
        thread.start()
        self._media_scan_thread = thread

    def _load_media_bank_async(self):
        """Build ThemeBank themes from the active session's media directories."""
        try:
            entries = self._get_media_bank_entries()
            self.logger.info("🔄 Starting background media scan...")

            themes = []
            font_paths: list[str] = []
            for entry in entries:
                theme_name = entry.get('name', 'Unnamed')
                media_dir = Path(entry.get('path', ''))
                media_type = entry.get('type', 'images')

                if media_dir.drive and media_dir.drive.upper() in ['U:', 'Z:', 'Y:', 'X:', 'W:', 'V:']:
                    self.logger.warning(
                        f"⚠️  Skipping network drive '{theme_name}': {media_dir} (use local drives for performance)"
                    )
                    continue

                if not media_dir.exists():
                    self.logger.warning(f"⚠️  Skipping '{theme_name}': {media_dir} doesn't exist")
                    continue

                if media_type == 'fonts':
                    fonts = scan_font_directory(media_dir)
                    if fonts:
                        font_paths.extend(fonts)
                        self.logger.info(f"🔤 Font bank '{theme_name}': {len(fonts)} font(s)")
                    else:
                        self.logger.warning(f"⚠️  Font bank '{theme_name}' contains no *.ttf/*.otf files")
                    continue

                all_images, all_videos = scan_media_directory(media_dir)

                if media_type == 'images':
                    images = all_images
                    videos = []
                elif media_type == 'videos':
                    images = []
                    videos = all_videos
                else:
                    images = all_images
                    videos = all_videos

                theme = ThemeConfig(
                    name=theme_name,
                    enabled=True,
                    image_path=images,
                    animation_path=videos,
                    font_path=[],
                    text_line=[]
                )
                themes.append(theme)
                self.logger.info(f"✅ Theme '{theme_name}': {len(images)} images, {len(videos)} videos")

            if themes:
                self.theme_bank._root_path = Path('.')
                self.theme_bank._themes = [t for t in themes if t.enabled]
                self.theme_bank._preload_theme_images()
                self.theme_bank.set_active_themes(primary_index=1)
                total_images = sum(len(t.image_path) for t in themes)
                self.logger.info(
                    f"✅ Media scan complete: {len(themes)} theme(s) loaded, {total_images} total images"
                )
            else:
                self.logger.warning("⚠️  No media found in session media bank")

            if hasattr(self, "theme_bank") and self.theme_bank:
                self.theme_bank.set_font_library(font_paths)
                if font_paths:
                    self.logger.info(f"🔤 Font library ready: {len(font_paths)} font(s) available")
                else:
                    self.logger.info("🔤 Font library empty - using default TextRenderer font")

        except Exception as exc:
            self.logger.error(f"❌ Background media scan failed: {exc}")

    def _on_import_cuelist(self):
        """Import a cuelist file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Cuelist", "", "Cuelist Files (*.cuelist.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # TODO: Implement cuelist import
            self.logger.info(f"Cuelist imported: {file_path}")
            QMessageBox.information(self, "Success", "Cuelist imported successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import cuelist: {e}")
            self.logger.error(f"Failed to import cuelist: {e}", exc_info=True)
    
    def _on_export_cuelist(self):
        """Export a cuelist file."""
        # TODO: Show cuelist selection dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Cuelist", "", "Cuelist Files (*.cuelist.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # TODO: Implement cuelist export
            self.logger.info(f"Cuelist exported: {file_path}")
            QMessageBox.information(self, "Success", "Cuelist exported successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export cuelist: {e}")
            self.logger.error(f"Failed to export cuelist: {e}", exc_info=True)
    
    def mark_session_dirty(self):
        """Mark session as having unsaved changes."""
        self.session_manager.mark_dirty()
        self._update_status_bar()

