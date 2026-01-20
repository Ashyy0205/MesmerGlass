"""Home tab - Session Runner mission control.

Main features:
- Session information display
- SessionRunner controls (Start/Pause/Stop/Skip) from Phase 6
- Live preview area (LoomCompositor)
- Quick actions (one-click features)
- Media Bank shortcuts
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QWidget, QFileDialog,
    QMessageBox, QInputDialog, QProgressDialog
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QImage, QPixmap
import time

from .base_tab import BaseTab
from ..session_runner_tab import SessionRunnerTab
from ..editors import CuelistEditor, PlaybackEditor


class HomeTab(BaseTab):
    """Home tab with session info, SessionRunner controls, live preview, and quick actions."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.session_data: Optional[Dict[str, Any]] = None
        self._preview_compositor = None
        self._preview_registered = False
        self._preview_sync_connected = False
        self._preview_frame_connected = False
        self._preview_last_frame_t = 0.0
        self._setup_ui()
    
    def set_session_data(self, session_data: Dict[str, Any]):
        """Set session data reference and update display."""
        self.session_data = session_data
        self._update_session_display()
        self._refresh_media_bank_list()
        
        # Pass session data to SessionRunnerTab for session mode
        if hasattr(self, 'session_runner_tab'):
            self.session_runner_tab.set_session_data(session_data)
        
        self.logger.info("HomeTab session data set")
    
    def _setup_ui(self):
        """Build the home tab UI with SessionRunner and preview."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Use splitter for resizable sections
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        
        # === LEFT: Session Info + Session Runner Controls ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(12)
        
        # Session Information
        session_info_group = self._create_session_info_section()
        left_layout.addWidget(session_info_group)
        
        # Embed SessionRunnerTab from Phase 6
        # Pass engines from main window
        self.session_runner_tab = SessionRunnerTab(
            parent=self.main_window,
            visual_director=getattr(self.main_window, 'visual_director', None),
            audio_engine=getattr(self.main_window, 'audio_engine', None),
            compositor=getattr(self.main_window, 'compositor', None),
            display_tab=getattr(self.main_window, 'display_tab', None)
        )
        left_layout.addWidget(self.session_runner_tab, 1)
        
        # Quick Actions
        quick_actions_group = self._create_quick_actions()
        left_layout.addWidget(quick_actions_group)
        
        self._splitter.addWidget(left_panel)
        
        # === RIGHT: Live Preview + Media Bank ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)
        
        # Live Preview (placeholder for LoomCompositor)
        preview_group = self._create_preview_section()
        right_layout.addWidget(preview_group, 1)
        
        # Media Bank
        media_bank_group = self._create_media_bank_section()
        right_layout.addWidget(media_bank_group)
        
        self._splitter.addWidget(right_panel)
        
        # Set initial sizes (60% session runner, 40% preview)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([600, 400])
        
        layout.addWidget(self._splitter)
        self._update_splitter_orientation()
        
        self.logger.info("HomeTab initialized with SessionRunner integration")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_splitter_orientation()

    def _update_splitter_orientation(self):
        """Flip splitter orientation when width is constrained."""
        if not hasattr(self, "_splitter") or self._splitter is None:
            return
        width = self.width()
        threshold = 1300
        desired_orientation = Qt.Orientation.Horizontal if width >= threshold else Qt.Orientation.Vertical
        if self._splitter.orientation() != desired_orientation:
            logger = getattr(self, "logger", None)
            if logger:
                logger.info(
                    "[home] Switching splitter orientation: %s -> %s (width=%d)",
                    "horizontal" if self._splitter.orientation() == Qt.Orientation.Horizontal else "vertical",
                    "horizontal" if desired_orientation == Qt.Orientation.Horizontal else "vertical",
                    width,
                )
            # Preserve ratios when toggling orientation
            sizes = self._splitter.sizes()
            self._splitter.setOrientation(desired_orientation)
            if sizes and len(sizes) == 2:
                self._splitter.setSizes(sizes)
    
    def _create_session_info_section(self) -> QGroupBox:
        """Create session information display section."""
        group = QGroupBox("📋 Session Information")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Session name
        self.session_name_label = QLabel("No session loaded")
        self.session_name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(self.session_name_label)
        
        # Session metadata
        self.session_meta_label = QLabel("")
        self.session_meta_label.setStyleSheet("color: #888;")
        self.session_meta_label.setWordWrap(True)
        layout.addWidget(self.session_meta_label)
        
        # Session stats
        self.session_stats_label = QLabel("")
        layout.addWidget(self.session_stats_label)
        
        return group
    
    def _update_session_display(self):
        """Update session information display."""
        if not self.session_data:
            self.session_name_label.setText("No session loaded")
            self.session_meta_label.setText("")
            self.session_stats_label.setText("")
            return
        
        # Display session name
        metadata = self.session_data.get("metadata", {})
        name = metadata.get("name", "Unnamed Session")
        self.session_name_label.setText(name)
        
        # Display metadata
        description = metadata.get("description", "")
        author = metadata.get("author", "")
        meta_parts = []
        if description:
            meta_parts.append(f"📝 {description}")
        if author:
            meta_parts.append(f"👤 {author}")
        self.session_meta_label.setText("\n".join(meta_parts))
        
        # Display stats
        num_playbacks = len(self.session_data.get("playbacks", {}))
        num_cuelists = len(self.session_data.get("cuelists", {}))
        num_cues = sum(len(cl.get("cues", [])) for cl in self.session_data.get("cuelists", {}).values())
        
        stats_text = f"📊 {num_playbacks} playbacks • {num_cuelists} cuelists • {num_cues} cues"
        self.session_stats_label.setText(stats_text)
    
    def _create_quick_actions(self) -> QGroupBox:
        """Create quick actions section."""
        group = QGroupBox("⚡ Quick Actions")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Recent sessions
        btn_recent = QPushButton("📜 Recent Sessions")
        btn_recent.clicked.connect(self._on_recent_sessions)
        layout.addWidget(btn_recent)
        
        # New playback
        btn_playback = QPushButton("🎨 New Playback")
        btn_playback.clicked.connect(self._on_new_playback)
        layout.addWidget(btn_playback)
        
        # New cuelist
        btn_new = QPushButton("➕ New Cuelist")
        btn_new.clicked.connect(self._on_new_cuelist)
        layout.addWidget(btn_new)

        # Export cuelist to MP4
        btn_export = QPushButton("📼 Export Cuelist → MP4…")
        btn_export.clicked.connect(self._on_export_cuelist_mp4)
        btn_export.setToolTip("Render the currently loaded cuelist to an MP4 (60fps, 1920×1080).")
        layout.addWidget(btn_export)
        
        return group

    def _on_export_cuelist_mp4(self) -> None:
        """Export the currently loaded cuelist to MP4 (video-only)."""
        try:
            runner_tab = getattr(self, "session_runner_tab", None)
            cuelist = getattr(runner_tab, "cuelist", None)
            if cuelist is None:
                QMessageBox.warning(self, "Export MP4", "Load a cuelist first (Session Runner → Load Cuelist).")
                return

            # Don't export while an interactive session is running.
            session_runner = getattr(runner_tab, "session_runner", None)
            if session_runner is not None and getattr(session_runner, "is_running", lambda: False)():
                QMessageBox.warning(self, "Export MP4", "Stop the current session before exporting.")
                return

            loop_mode = getattr(cuelist, "loop_mode", None)
            loop_mode_value = getattr(loop_mode, "value", loop_mode)
            if str(loop_mode_value).lower() in ("loop", "ping_pong"):
                QMessageBox.warning(
                    self,
                    "Export MP4",
                    "Looping cuelists are not supported for MP4 export yet (v1).\n\nSet Loop Mode to 'once' and try again.",
                )
                return

            default_name = f"{getattr(cuelist, 'name', 'cuelist')}.mp4".replace("/", "-").replace("\\", "-")
            out_path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Export Cuelist to MP4",
                default_name,
                "MP4 Video (*.mp4);;All Files (*)",
            )
            if not out_path_str:
                return
            out_path = Path(out_path_str)
            if out_path.suffix.lower() != ".mp4":
                out_path = out_path.with_suffix(".mp4")

            from mesmerglass.export.cuelist_mp4_exporter import CuelistMp4Exporter, Mp4ExportSettings

            settings = Mp4ExportSettings(
                output_path=out_path,
                width=1920,
                height=1080,
                fps=60,
                prefer_nvenc=True,
            )

            progress = QProgressDialog("Preparing export…", "Cancel", 0, 100, self)
            progress.setWindowTitle("Export MP4")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)

            exporter = CuelistMp4Exporter(
                cuelist=cuelist,
                visual_director=getattr(self.main_window, "visual_director", None),
                text_director=getattr(self.main_window, "text_director", None),
                spiral_director=getattr(self.main_window, "spiral_director", None),
                session_data=getattr(self, "session_data", None),
                settings=settings,
                parent=self,
            )

            if exporter._visual_director is None or exporter._text_director is None or exporter._spiral_director is None:
                QMessageBox.critical(self, "Export MP4", "Missing engines (visual/text/spiral). Cannot export.")
                return

            self._active_exporter = exporter

            def _on_progress(cur: int, total: int, label: str) -> None:
                try:
                    progress.setMaximum(max(1, int(total)))
                    progress.setValue(int(cur))
                    progress.setLabelText(f"{label}\n\n{cur}/{total} frames")
                except Exception:
                    pass

            def _on_finished(success: bool, message: str) -> None:
                try:
                    progress.reset()
                    progress.close()
                except Exception:
                    pass
                try:
                    self._active_exporter = None
                except Exception:
                    pass
                if success:
                    QMessageBox.information(self, "Export MP4", message)
                else:
                    QMessageBox.critical(self, "Export MP4", message)

            exporter.progress_changed.connect(_on_progress)
            exporter.finished.connect(_on_finished)
            progress.canceled.connect(exporter.cancel)

            exporter.start()
            progress.show()

        except Exception as exc:
            self.logger.error("[home] Export MP4 failed: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Export MP4", f"Export failed: {exc}")

    def _create_preview_section(self) -> QGroupBox:
        """Create live preview section."""
        group = QGroupBox("🎥 Live Preview")
        layout = QVBoxLayout(group)

        # Mirror the actual output via framebuffer capture (avoids GL-widget corruption).
        self._preview_image_label = QLabel()
        self._preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image_label.setStyleSheet("background-color: #000; color: #bbb;")
        self._preview_image_label.setText("Preview waiting for output…\n\nStart a session to activate rendering.")
        self._preview_image_label.setMinimumHeight(120)

        self._preview_aspect = _AspectRatioContainer(16, 9, parent=group)
        self._preview_aspect.set_child(self._preview_image_label)
        layout.addWidget(self._preview_aspect, 1)
        
        return group

    def _register_preview_compositor(self) -> None:
        if self._preview_registered:
            return
        self._preview_registered = True

        primary = getattr(self.main_window, "compositor", None)
        if primary is None:
            return

        # If the compositor is inactive (common when no session is running), we won't
        # receive frames yet. Show a friendly placeholder rather than a black box.
        try:
            is_active = bool(getattr(primary, "_active", False))
        except Exception:
            is_active = False
        if not is_active and hasattr(self, "_preview_image_label"):
            self._preview_image_label.setText("Preview waiting for output…\n\nStart a session to activate rendering.")

        if hasattr(primary, "set_preview_capture_enabled"):
            try:
                primary.set_preview_capture_enabled(True, max_fps=15)
            except Exception:
                pass
        elif hasattr(primary, "set_capture_enabled"):
            try:
                primary.set_capture_enabled(True, max_fps=15)
            except Exception:
                pass

        if not self._preview_frame_connected and hasattr(primary, "frame_ready"):
            try:
                primary.frame_ready.connect(self._on_preview_frame)
                self._preview_frame_connected = True
            except Exception:
                pass

    def _unregister_preview_compositor(self) -> None:
        if not self._preview_registered:
            return

        primary = getattr(self.main_window, "compositor", None)
        if primary is not None:
            if self._preview_frame_connected and hasattr(primary, "frame_ready"):
                try:
                    primary.frame_ready.disconnect(self._on_preview_frame)
                except Exception:
                    pass
                self._preview_frame_connected = False

            if hasattr(primary, "set_preview_capture_enabled"):
                try:
                    primary.set_preview_capture_enabled(False)
                except Exception:
                    pass
            # Intentionally do NOT call set_capture_enabled(False) as a fallback,
            # because older implementations may share the VR capture flag.

        self._preview_registered = False

    def _on_preview_frame(self, frame) -> None:
        # Throttle UI updates (even if capture emits faster)
        now = time.time()
        if (now - self._preview_last_frame_t) < (1.0 / 15.0):
            return
        self._preview_last_frame_t = now

        try:
            if frame is None:
                return
            # Defensive: ignore empty frames
            try:
                if getattr(frame, "size", 0) == 0:
                    return
            except Exception:
                pass

            # Ensure contiguous memory for QImage.
            try:
                import numpy as np
                if isinstance(frame, np.ndarray) and not frame.flags["C_CONTIGUOUS"]:
                    frame = np.ascontiguousarray(frame)
            except Exception:
                pass
            h, w, _c = frame.shape
            img = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
            pix = QPixmap.fromImage(img)
            try:
                self._preview_image_label.setText("")
            except Exception:
                pass
            self._preview_image_label.setPixmap(
                pix.scaled(
                    self._preview_image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except Exception:
            return
    
    def _create_media_bank_section(self) -> QGroupBox:
        """Create media bank shortcuts section."""
        group = QGroupBox("🏦 Media Bank")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Media bank info
        info_label = QLabel("Quick access to media directories")
        info_label.setStyleSheet("color: #888; font-style: italic; font-size: 10pt;")
        layout.addWidget(info_label)
        
        # Media bank list (session-scoped entries)
        self.media_bank_list = QListWidget()
        self.media_bank_list.setMaximumHeight(150)
        layout.addWidget(self.media_bank_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        btn_add = QPushButton("➕ Add Directory")
        btn_add.clicked.connect(self._on_add_media_directory)
        btn_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("🗑️ Remove")
        btn_remove.clicked.connect(self._on_remove_media_directory)
        btn_layout.addWidget(btn_remove)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._on_refresh_media_bank)
        btn_layout.addWidget(btn_refresh)
        
        layout.addLayout(btn_layout)
        
        # Load media bank on init
        self._refresh_media_bank_list()
        
        return group
    
    def _refresh_media_bank_list(self, trigger_scan: bool = False):
        """Refresh media bank list from the active session."""
        entries = self.session_data.get("media_bank", []) if self.session_data else []
        
        self.media_bank_list.clear()
        for entry in entries:
            name = entry.get("name", "Unnamed")
            path = entry.get("path", "")
            media_type = entry.get("type", "images")
            if media_type == "images":
                type_icon = "🖼️"
            elif media_type == "videos":
                type_icon = "🎬"
            elif media_type == "fonts":
                type_icon = "🔤"
            else:
                type_icon = "🌀"
            item = QListWidgetItem(f"{type_icon} {name} ({path})")
            self.media_bank_list.addItem(item)

        if trigger_scan:
            self._trigger_media_bank_reload()

        self.logger.info(f"Loaded {len(entries)} media bank entries")

    def _trigger_media_bank_reload(self):
        """Ask the main window to rebuild ThemeBank from the latest media bank entries."""
        scheduler = getattr(self.main_window, "_schedule_media_bank_refresh", None)
        if callable(scheduler):
            scheduler()
        else:
            self.logger.debug("Main window missing media bank scheduler; skipping reload")
    
    def _on_refresh_media_bank(self):
        """Refresh media bank list."""
        self._refresh_media_bank_list(trigger_scan=True)
    
    def _on_add_media_directory(self):
        """Add a new media directory to the bank."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Media Directory"
        )
        
        if not directory:
            return
        
        if self.session_data is None:
            self.logger.warning("Cannot add media directory without an active session")
            return

        media_bank = self.session_data.setdefault("media_bank", [])
        dir_path = Path(directory)

        # Prompt for friendly name
        default_name = dir_path.name
        name, ok = QInputDialog.getText(
            self,
            "Media Bank Name",
            "Enter a label for this directory:",
            text=default_name
        )
        if not ok:
            return
        name = name.strip() or default_name

        # Prompt for media type
        type_options = ["images", "videos", "both", "fonts"]
        type_labels = ["🖼️ Images", "🎬 Videos", "🌀 Both (Images+Videos)", "🔤 Fonts"]
        selection, ok = QInputDialog.getItem(
            self,
            "Media Bank Type",
            "What media does this directory contain?",
            type_labels,
            0,
            False
        )
        if not ok or not selection:
            return
        selected_index = type_labels.index(selection)
        selected_type = type_options[selected_index]

        media_bank.append({
            "name": name,
            "path": str(dir_path),
            "type": selected_type
        })

        self._refresh_media_bank_list(trigger_scan=True)
        self.mark_dirty()
        self.logger.info(f"Added media directory: {directory}")
    
    def _on_remove_media_directory(self):
        """Remove selected media directory from the bank."""
        current_item = self.media_bank_list.currentRow()
        if current_item < 0:
            self.logger.warning("No media bank entry selected")
            return
        
        if self.session_data is None:
            self.logger.warning("Cannot remove media directory without an active session")
            return

        media_bank = self.session_data.get("media_bank", [])
        if current_item >= len(media_bank):
            self.logger.warning("Selected media bank entry out of range")
            return

        removed = media_bank.pop(current_item)
        self._refresh_media_bank_list(trigger_scan=True)
        self.mark_dirty()
        self.logger.info(f"Removed media directory: {removed.get('name', 'Unnamed')}")
    
    def _on_recent_sessions(self):
        """Show recent sessions dialog."""
        recent_entries = self.main_window.get_recent_sessions()
        valid_entries: list[Path] = []
        labels: list[str] = []

        for entry in recent_entries:
            path = Path(entry)
            if path.exists():
                valid_entries.append(path)
                labels.append(f"{path.name} — {path}")

        if not valid_entries:
            QMessageBox.information(self, "Recent Sessions", "No recent sessions found.")
            return

        selection, ok = QInputDialog.getItem(
            self,
            "Recent Sessions",
            "Select a session to open:",
            labels,
            0,
            False
        )
        if not ok or not selection:
            return

        selected_index = labels.index(selection)
        chosen_path = valid_entries[selected_index]
        if self.main_window.open_session_from_path(chosen_path):
            self.session_data = self.main_window.session_data
            self._update_session_display()
            self._refresh_media_bank_list()
    
    def _on_new_cuelist(self):
        """Create a new cuelist."""
        if not self.session_data:
            QMessageBox.warning(
                self,
                "No Session Loaded",
                "Load or start a session before creating a cuelist."
            )
            return

        editor = CuelistEditor(session_data=self.session_data, cuelist_key=None, parent=self)
        editor.saved.connect(lambda *_: self._handle_cuelist_saved())
        editor.exec()
        self.logger.info("Cuelist editor closed from Home tab")

    def _handle_cuelist_saved(self):
        """Refresh UI after a cuelist is saved via the quick action."""
        self.mark_dirty()
        self._update_session_display()
        if hasattr(self.main_window, "cuelists_tab"):
            self.main_window.cuelists_tab.set_session_data(self.session_data)

    def _on_new_playback(self):
        """Create a new playback via the quick action."""
        if not self.session_data:
            QMessageBox.warning(
                self,
                "No Session Loaded",
                "Load or start a session before creating a playback."
            )
            return

        editor = PlaybackEditor(session_data=self.session_data, playback_key=None, parent=self)
        editor.saved.connect(lambda *_: self._handle_playback_saved())
        editor.exec()
        self.logger.info("Playback editor closed from Home tab")

    def _handle_playback_saved(self):
        """Refresh UI after a playback is saved via the quick action."""
        self.mark_dirty()
        self._update_session_display()
        if hasattr(self.main_window, "playbacks_tab"):
            self.main_window.playbacks_tab.set_session_data(self.session_data)
    
    def on_show(self):
        """Called when tab becomes visible."""
        self.logger.debug("HomeTab shown")
        # Refresh media bank when tab is shown
        self._refresh_media_bank_list()
        
        # Update SessionRunner dependencies if available
        if self.visual_director:
            self.session_runner_tab.visual_director = self.visual_director
        if self.audio_engine:
            self.session_runner_tab.audio_engine = self.audio_engine
        if self.compositor:
            self.session_runner_tab.compositor = self.compositor

        self._register_preview_compositor()
    
    def on_hide(self):
        """Called when tab becomes hidden."""
        self.logger.debug("HomeTab hidden")

        self._unregister_preview_compositor()


class _AspectRatioContainer(QWidget):
    """A simple letterboxing container that keeps its single child at a fixed aspect ratio."""

    def __init__(self, aspect_w: int, aspect_h: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._aspect = float(aspect_w) / float(aspect_h)
        self._child: QWidget | None = None

    def set_child(self, child: QWidget) -> None:
        self._child = child
        child.setParent(self)
        child.show()
        self._layout_child()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_child()

    def _layout_child(self) -> None:
        if self._child is None:
            return

        w = max(1, self.width())
        h = max(1, self.height())
        container_aspect = w / h

        if container_aspect > self._aspect:
            # Too wide -> pillarbox
            target_h = h
            target_w = int(round(target_h * self._aspect))
        else:
            # Too tall -> letterbox
            target_w = w
            target_h = int(round(target_w / self._aspect))

        x = int((w - target_w) / 2)
        y = int((h - target_h) / 2)
        self._child.setGeometry(QRect(x, y, target_w, target_h))
