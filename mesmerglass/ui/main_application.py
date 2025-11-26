"""Main Application Window for MesmerGlass Phase 7.

Vertical tab-based interface for managing visual trance sessions.
Replaces the legacy Launcher with a cleaner, session-focused design.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QFileDialog, QInputDialog, QLabel
)

from ..session_manager import SessionManager
from .tabs.home_tab import HomeTab
from .tabs.cuelists_tab import CuelistsTab
from .tabs.playbacks_tab import PlaybacksTab
from .tabs.display_tab import DisplayTab
from ..content.simple_video_streamer import SimpleVideoStreamer
from ..content.media_scan import scan_media_directory


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
            from ..content.themebank import ThemeBank
            from ..content.theme import ThemeConfig
            from pathlib import Path
            import json
            import threading
            
            # Create EMPTY ThemeBank immediately to prevent UI blocking
            # Media will be loaded asynchronously after UI appears
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
            
            # Load media asynchronously AFTER UI appears
            def load_media_async():
                try:
                    self.logger.info("🔄 Starting background media scan...")
                    
                    # Load media bank configuration
                    media_bank_path = Path("media_bank.json")
                    media_entries = []
                    if media_bank_path.exists():
                        with open(media_bank_path, 'r', encoding='utf-8') as f:
                            media_entries = json.load(f)
                    
                    # Build themes from media bank entries
                    themes = []
                    for idx, entry in enumerate(media_entries):
                        theme_name = entry.get('name', 'Unnamed')
                        media_dir = Path(entry.get('path', ''))
                        media_type = entry.get('type', 'images')
                        
                        # SKIP NETWORK DRIVES automatically to prevent lag
                        if media_dir.drive and media_dir.drive.upper() in ['U:', 'Z:', 'Y:', 'X:', 'W:', 'V:']:
                            self.logger.warning(f"⚠️  Skipping network drive '{theme_name}': {media_dir} (use local drives for performance)")
                            continue
                        
                        if not media_dir.exists():
                            self.logger.warning(f"⚠️  Skipping '{theme_name}': {media_dir} doesn't exist")
                            continue
                        
                        all_images, all_videos = scan_media_directory(media_dir)

                        if media_type == 'images':
                            images = all_images
                            videos = []
                        elif media_type == 'videos':
                            images = []
                            videos = all_videos
                        else:  # 'both' or unexpected string → include everything
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
                    
                    # Update ThemeBank with loaded themes
                    if themes:
                        # Update root_path to empty (using absolute paths)
                        self.theme_bank._root_path = Path(".")
                        self.theme_bank._themes = [t for t in themes if t.enabled]
                        # CRITICAL: Rebuild image caches for new themes
                        self.theme_bank._preload_theme_images()
                        self.theme_bank.set_active_themes(primary_index=1)
                        self.logger.info(f"✅ Media scan complete: {len(themes)} theme(s) loaded, {sum(len(t.image_path) for t in themes)} total images")
                    else:
                        self.logger.warning("⚠️  No media found in media bank")
                
                except Exception as e:
                    self.logger.error(f"❌ Background media scan failed: {e}")
            
            # Start background thread AFTER a short delay to let UI appear first
            def delayed_load():
                import time
                time.sleep(1)  # Wait 1 second for UI to appear
                load_media_async()
            
            media_thread = threading.Thread(target=delayed_load, daemon=True, name="MediaScanner")
            media_thread.start()
            
            # 4. Create VisualDirector (manages playback loading)
            from ..mesmerloom.visual_director import VisualDirector
            self.visual_director = VisualDirector(
                theme_bank=self.theme_bank,
                compositor=self.compositor,
                text_renderer=self.text_renderer,
                video_streamer=self.video_streamer,
                text_director=self.text_director
            )
            self.logger.info("VisualDirector initialized")
            
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
        
        # Tab 5: Device Control (placeholder)
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        label = QLabel("🔗 Device tab\n\nComing soon...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.tabs.addTab(placeholder, "🔗 Device")
        
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

