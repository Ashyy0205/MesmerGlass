"""Visual Director - orchestrates visual programs with theme bank integration.

Manages:
- Current active visual program
- Callbacks connecting visuals → theme bank → compositor
- Cycler advancement and completion detection
- Image/text/video switching coordination
- Spiral rotation synchronization
"""

from __future__ import annotations
from typing import Optional, Callable, Any, TYPE_CHECKING
from pathlib import Path
import logging
from time import perf_counter
from contextlib import contextmanager

from ..logging_utils import BurstSampler

if TYPE_CHECKING:
    from ..content.themebank import ThemeBank
    from ..mesmerloom.compositor import LoomCompositor
    from .visuals import Visual


class VisualDirector:
    """Orchestrates visual programs with theme bank and compositor integration.
    
    Note: Built-in visual programs (VISUAL_PROGRAMS) removed in Phase 3.
    All visuals now loaded from JSON mode files via select_custom_visual().
    """
    
    def __init__(
        self,
        theme_bank: Optional[ThemeBank] = None,
        compositor: Optional[Any] = None,
        text_renderer: Optional[Any] = None,
        video_streamer: Optional[Any] = None,
        text_director: Optional[Any] = None,
        mesmer_server: Optional[Any] = None
    ):
        """Initialize visual director.
        
        Args:
            theme_bank: ThemeBank instance for image/text selection
            compositor: LoomCompositor instance for rendering
            text_renderer: TextRenderer instance for text overlays
            video_streamer: VideoStreamer instance for video playback
            text_director: TextDirector instance for text library management
            mesmer_server: MesmerIntifaceServer instance for device vibration control
        """
        self.theme_bank = theme_bank
        self.compositor = compositor  # Primary compositor
        self.text_renderer = text_renderer
        self.video_streamer = video_streamer
        self.text_director = text_director
        self.mesmer_server = mesmer_server
        
        self.current_visual: Optional[Visual] = None
        self._paused = False
        self._pause_saved_rotation_speed: Optional[float] = None
        self._frame_count = 0
        self._video_first_frame = False  # Track first frame of new video for fade
        self._pending_image_path = None  # Path of image we're waiting to load
        
        # Cycle tracking for session synchronization (Phase 2)
        self._cycle_count = 0  # Total media cycles completed
        self._last_cycle_marker = 0  # Last known cycle position from visual
        self._cycle_callbacks: list[Callable[[], None]] = []  # Callbacks fired on cycle boundary
        
        # Multi-display support: Additional compositors for secondary displays
        self._secondary_compositors: list[Any] = []  # Additional compositors to mirror content to
        
        # Current cue settings (for vibration on text cycle)
        self._current_cue_settings: Optional[dict] = None
        
        self.logger = logging.getLogger(__name__)
        self._image_upload_sampler = BurstSampler(interval_s=2.0)
        self._image_upload_counts = {"success": 0, "retry": 0}
        self._last_uploaded_image_path: Optional[str] = None
        self._image_retry_pending = 0
        self._last_image_still_loading = False
        self._image_retry_sampler = BurstSampler(interval_s=5.0)
        self._has_logged_first_media = False
        self._video_frame_miss_count = 0
        self._video_frame_miss_logged = False
        self._video_first_upload_logged = False
        self._perf_sampler = BurstSampler(interval_s=2.0)
    
    # ===== Multi-Display Support =====
    
    def register_secondary_compositor(self, compositor: Any) -> None:
        """Register an additional compositor for multi-display mirroring.
        
        Args:
            compositor: LoomCompositor instance to mirror content to
        """
        if compositor not in self._secondary_compositors:
            self._secondary_compositors.append(compositor)
            self.logger.debug(f"[visual] Registered secondary compositor (total: {len(self._secondary_compositors)})")
    
    def unregister_secondary_compositor(self, compositor: Any) -> None:
        """Unregister a secondary compositor.
        
        Args:
            compositor: LoomCompositor instance to remove
        """
        if compositor in self._secondary_compositors:
            self._secondary_compositors.remove(compositor)
            self.logger.debug(f"[visual] Unregistered secondary compositor (remaining: {len(self._secondary_compositors)})")
    
    def clear_secondary_compositors(self) -> None:
        """Remove all secondary compositors."""
        count = len(self._secondary_compositors)
        self._secondary_compositors.clear()
        if count > 0:
            self.logger.debug(f"[visual] Cleared {count} secondary compositor(s)")
    
    def _get_all_compositors(self) -> list[Any]:
        """Get list of all compositors (primary + secondaries).
        
        Returns:
            List of all active compositors
        """
        compositors = []
        if self.compositor:
            compositors.append(self.compositor)
        compositors.extend(self._secondary_compositors)
        return compositors

    def _record_perf_event(
        self,
        label: str,
        duration_s: float,
        warn_ms: float = 20.0,
        info_ms: float = 10.0,
    ) -> None:
        """Emit throttled perf logs for expensive operations."""

        duration_ms = duration_s * 1000.0
        if duration_ms >= warn_ms:
            self.logger.warning("[visual.perf] %s took %.1fms", label, duration_ms)
            return
        if duration_ms >= info_ms and self._perf_sampler.record():
            self.logger.warning("[visual.perf] %s took %.1fms", label, duration_ms)

    @contextmanager
    def _perf_section(
        self,
        label: str,
        warn_ms: float = 20.0,
        info_ms: float = 10.0,
    ) -> Any:
        """Context manager for timing blocks without cluttering code."""

        start = perf_counter()
        try:
            yield
        finally:
            self._record_perf_event(label, perf_counter() - start, warn_ms, info_ms)

    def _emit_image_upload_stats(self) -> None:
        """Summarize recent image uploads to avoid per-call INFO noise."""

        success = self._image_upload_counts.get("success", 0)
        if success <= 0:
            return
        retries = self._image_upload_counts.get("retry", 0)
        self.logger.info(
            "[visual] Applied %d images (pending retries=%d)",
            success,
            retries,
        )
        self._image_upload_counts = {"success": 0, "retry": 0}

    def _log_themebank_media_snapshot(self, image_path: Optional[str] = None) -> None:
        if self._has_logged_first_media:
            return
        if not self.theme_bank or not hasattr(self.theme_bank, "get_status"):
            self.logger.info("[visual] First ThemeBank media uploaded: %s", image_path or "unknown")
            self._has_logged_first_media = True
            return
        try:
            status = self.theme_bank.get_status()
            self.logger.info(
                "[visual] ThemeBank ready: images=%d cached=%d pending=%d last=%s",
                status.total_images,
                status.cached_images,
                status.pending_loads,
                image_path or status.last_image_path,
            )
        except Exception as exc:
            self.logger.info(
                "[visual] First ThemeBank media uploaded: %s (status unavailable: %s)",
                image_path or "unknown",
                exc,
            )
        self._has_logged_first_media = True

    def get_media_pipeline_stats(self) -> dict:
        """Expose lightweight stats for CLI/tests without touching OpenGL."""

        return {
            "last_image_path": self._last_uploaded_image_path,
            "pending_retries": self._image_retry_pending,
            "last_image_still_loading": self._last_image_still_loading,
            "compositor_ready": self.compositor is not None,
            "secondary_count": len(self._secondary_compositors),
        }
    
    # ===== Visual Selection =====
    
    def is_custom_mode_active(self) -> bool:
        """Check if the current visual is a CustomVisual (user-created mode).
        
        Returns:
            True if current visual is CustomVisual, False otherwise
        """
        if self.current_visual is None:
            return False
        
        # Check if instance is CustomVisual
        from .custom_visual import CustomVisual
        return isinstance(self.current_visual, CustomVisual)
    
    def load_playback(self, playback_path: Path) -> bool:
        """
        Select and initialize a CustomVisual from playback file.
        
        Args:
            playback_path: Path to JSON playback file
        
        Returns:
            True if successfully loaded, False on error
        """
        try:
            from .custom_visual import CustomVisual
            
            # Validate playback file first
            is_valid, error_msg = CustomVisual.validate_mode_file(playback_path)
            if not is_valid:
                self.logger.error(f"[CustomVisual] Invalid playback file: {error_msg}")
                return False
            
            self.logger.info(f"[CustomVisual] Loading playback from: {playback_path.name}")
            
            # Create CustomVisual instance
            custom_visual = CustomVisual(
                playback_path=playback_path,
                theme_bank=self.theme_bank,
                on_change_image=self._on_change_image,
                on_change_video=self._on_change_video,
                on_rotate_spiral=self._on_rotate_spiral,
                compositor=self.compositor,
                text_director=self.text_director
            )
            
            # CRITICAL: Ensure CustomVisual has the latest ThemeBank reference
            # (in case ThemeBank was rebuilt after VisualDirector initialization)
            custom_visual.theme_bank = self.theme_bank
            self.logger.info(f"[CustomVisual] Ensured CustomVisual has current ThemeBank reference")
            
            # Multi-display support: Pass secondary compositors to CustomVisual for zoom sync
            if self._secondary_compositors:
                custom_visual.set_secondary_compositors(self._secondary_compositors)
                self.logger.info(f"[CustomVisual] Set {len(self._secondary_compositors)} secondary compositor(s) for zoom synchronization")
            
            # Store as current visual
            self.current_visual = custom_visual
            self._paused = False
            self._pause_saved_rotation_speed = None  # Clear saved rotation speed on new visual
            self._frame_count = 0
            
            # CRITICAL FIX: Do NOT reset _last_cycle_marker during playback switches
            # The old code reset cycle tracking here, which prevented cycle boundaries
            # from being detected across playback switches in Playback Pool mode.
            # Now we only reset _cycle_count (total cycles), but preserve _last_cycle_marker
            # so the next cycle boundary can be detected immediately.
            # Reset cycle count (Phase 2) - but preserve last marker for boundary detection
            self._cycle_count = 0
            # NOTE: _last_cycle_marker is NOT reset here - preserves cycle boundary detection
            # across playback switches (critical for session transitions)
            
            # CRITICAL: Reset compositor zoom animation to prevent carryover from previous playback
            # When switching playbacks, the old zoom animation would continue until first image loads
            # This ensures zoom starts fresh at 1.0 with no animation
            if self.compositor and hasattr(self.compositor, 'reset_zoom'):
                self.compositor.reset_zoom()
                self.logger.debug("[CustomVisual] Reset compositor zoom animation")
            
            # CRITICAL: Reset text director scroll state to prevent carousel offset carryover
            # This must happen AFTER CustomVisual creation (so text_director exists)
            # but BEFORE any text rendering occurs. This handles both:
            # - Direct mode loading (no cuelist - reset happens here)
            # - Cuelist mode (reset happens here AND in _start_cue for safety)
            self.logger.debug(f"[CustomVisual] About to reset text director: self.text_director={self.text_director}, has reset={hasattr(self.text_director, 'reset') if self.text_director else 'N/A'}")
            if self.text_director and hasattr(self.text_director, 'reset'):
                self.text_director.reset()
                self.logger.info("[CustomVisual] *** RESET TEXT DIRECTOR SCROLL STATE ***")
            else:
                self.logger.warning(f"[CustomVisual] Cannot reset text director: director={self.text_director}")
            
            # Reset visual to initial state
            self.current_visual.reset()
            
            self.logger.info(f"[CustomVisual] Playback '{custom_visual.playback_name}' loaded successfully")
            self._has_logged_first_media = False
            return True
            
        except ImportError:
            self.logger.error("[CustomVisual] CustomVisual class not available")
            return False
        except Exception as e:
            self.logger.error(f"[CustomVisual] Failed to load playback: {e}", exc_info=True)
            return False
    
    def start_playback(self) -> None:
        """Start the currently loaded playback (load first media and begin cycling)."""
        if self.current_visual and hasattr(self.current_visual, 'start'):
            self.current_visual.start()
            self.logger.info("[visual] Playback started")
            # Note: If first image is still loading, update() loop will retry automatically
        else:
            self.logger.warning("[visual] No visual loaded or visual doesn't support start()")
    
    # Backward compatibility alias
    def select_custom_visual(self, mode_path: Path) -> bool:
        """Legacy method name - use load_playback() instead."""
        return self.load_playback(mode_path)
    
    # ===== Update Loop =====
    
    def update(self, dt: Optional[float] = None) -> None:
        """Update current visual (advance cycler).
        
        Args:
            dt: Delta time in seconds (unused, cyclers are frame-based)
        """
        update_start = perf_counter()
        did_process_frame = False
        try:
            # CRITICAL: Process async image loading in ThemeBank
            if self.theme_bank and hasattr(self.theme_bank, 'async_update'):
                with self._perf_section("theme_bank.async_update", warn_ms=8.0, info_ms=5.0):
                    self.theme_bank.async_update()
            
            # If last image load returned "still loading", retry now (after async_update processed loaded images)
            if hasattr(self, '_last_image_still_loading') and self._last_image_still_loading:
                self.logger.debug(f"[visual] ★ RETRY: Attempting to load pending image (frame={self._frame_count})")
                # Call _on_change_image directly to try uploading the now-loaded image
                self._on_change_image(0)  # Index doesn't matter for ThemeBank mode
                if not self._last_image_still_loading:
                    self.logger.debug(f"[visual] ★ RETRY SUCCESS!")
            
            if self.current_visual is None:
                if not hasattr(self, '_debug_no_visual'):
                    self.logger.warning("[visual] Update early-return: current_visual is None")
                    self._debug_no_visual = True
                return
            
            if self._paused:
                if not hasattr(self, '_debug_paused'):
                    self.logger.warning("[visual] Update early-return: paused")
                    self._debug_paused = True
                return
            
            # Get cycler
            cycler = self.current_visual.get_cycler()
            if cycler is None:
                if not hasattr(self, '_debug_no_cycler'):
                    self.logger.warning("[visual] Update early-return: cycler is None")
                    self._debug_no_cycler = True
                return
            
            # Advance by one frame
            with self._perf_section("visual.cycler.advance", warn_ms=12.0, info_ms=8.0):
                cycler.advance()
            self._frame_count += 1
            did_process_frame = True
            
            # Update video playback if this visual supports videos
            # CustomVisual handles its own video state via is_showing_video() method
            should_update_video = (
                self.video_streamer and self.compositor and 
                hasattr(self.current_visual, 'is_showing_video') and 
                self.current_visual.is_showing_video()
            )

            # Only dump debug once every 120 frames to avoid log spam
            video_debug_window = should_update_video and (self._frame_count % 120 == 0)
            if video_debug_window:
                cached_frames = None
                if hasattr(self.video_streamer, "get_frame_count"):
                    try:
                        cached_frames = self.video_streamer.get_frame_count()
                    except Exception:
                        cached_frames = "error"
                self.logger.debug(
                    "[visual.video] should_update_video=%s loaded=%s frame_buffer=%s",
                    should_update_video,
                    getattr(self.video_streamer, "is_loaded", lambda: "?")(),
                    cached_frames,
                )
            
            if should_update_video:
                try:
                    with self._perf_section("visual.video.tick", warn_ms=18.0, info_ms=12.0):
                        video_tick_start = perf_counter()
                        slow_threshold = 0.05  # 50ms per stage

                        update_start = perf_counter()
                        # Advance video playback
                        self.video_streamer.update(global_fps=60.0)
                        update_duration = perf_counter() - update_start
                    
                        if update_duration > slow_threshold:
                            self.logger.warning(
                                "[visual.perf] Video streamer update took %.1fms",
                                update_duration * 1000.0,
                            )

                        fetch_start = perf_counter()
                        # Get current frame and upload to compositor
                        frame = self.video_streamer.get_current_frame()
                        fetch_duration = perf_counter() - fetch_start

                        if fetch_duration > slow_threshold:
                            self.logger.warning(
                                "[visual.perf] Video frame fetch took %.1fms",
                                fetch_duration * 1000.0,
                            )

                        if video_debug_window:
                            if frame is None:
                                self.logger.debug("[visual.video] No frame retrieved this tick")
                            else:
                                self.logger.debug(
                                    "[visual.video] Uploading frame %dx%d new_video=%s",
                                    frame.width,
                                    frame.height,
                                    self._video_first_frame,
                                )
                        if frame:
                            upload_start = perf_counter()
                            # Reset miss diagnostics once a frame arrives
                            if self._video_frame_miss_logged and self._video_frame_miss_count > 0:
                                self.logger.info(
                                    "[visual.video] Video frames restored after %.1fs gap",
                                    self._video_frame_miss_count / 60.0,
                                )
                            self._video_frame_miss_count = 0
                            self._video_frame_miss_logged = False

                            if not self._video_first_upload_logged:
                                state = self._get_video_streamer_state()
                                self.logger.info(
                                    "[visual.video] First frame ready for compositor (state=%s)",
                                    state,
                                )
                                self._video_first_upload_logged = True

                            # Upload video frame as background
                            # This will overwrite any static image background
                            # Use current background zoom (respects zoom animation state)
                            current_zoom = getattr(self.compositor, '_background_zoom', 1.0)
                            self.compositor.set_background_video_frame(
                                frame.data,
                                width=frame.width,
                                height=frame.height,
                                zoom=current_zoom,
                                new_video=self._video_first_frame  # Trigger fade on first frame
                            )
                            # Clear first frame flag after upload
                            self._video_first_frame = False

                            upload_duration = perf_counter() - upload_start
                            total_duration = perf_counter() - video_tick_start

                            if upload_duration > slow_threshold:
                                self.logger.warning(
                                    "[visual.perf] Video frame upload took %.1fms",
                                    upload_duration * 1000.0,
                                )

                            if total_duration > 0.1:
                                self.logger.warning(
                                    "[visual.perf] Entire video tick took %.1fms (update=%.1fms fetch=%.1fms upload=%.1fms)",
                                    total_duration * 1000.0,
                                    update_duration * 1000.0,
                                    fetch_duration * 1000.0,
                                    upload_duration * 1000.0,
                                )
                        else:
                            self._video_frame_miss_count += 1
                            if (
                                not self._video_frame_miss_logged
                                and self._video_frame_miss_count >= 120
                            ):
                                state = self._get_video_streamer_state()
                                self.logger.warning(
                                    "[visual.video] No frame from video streamer for %.1fs (state=%s)",
                                    self._video_frame_miss_count / 60.0,
                                    state,
                                )
                                self._video_frame_miss_logged = True
                except Exception as ve:
                    # Only log video errors occasionally to avoid spam
                    if self._frame_count % 300 == 0:
                        self.logger.warning(f"[visual] Video update error: {ve}")
            
            # Check for cycle boundary crossing (Phase 2)
            self._check_cycle_boundary()
            
            # Debug: Log every 60 frames to verify update is being called
            if self._frame_count % 60 == 0:
                is_complete = self.current_visual.complete()
                self.logger.debug(
                    "[visual] Update: frame=%d progress=%.2f complete=%s",
                    self._frame_count,
                    self.current_visual.progress(),
                    is_complete,
                )
        except Exception as e:
            self.logger.error(f"Error advancing cycler: {e}", exc_info=True)
        finally:
            if did_process_frame:
                self._record_perf_event(
                    "visual.update",
                    perf_counter() - update_start,
                    warn_ms=22.0,
                    info_ms=15.0,
                )
    
    def is_complete(self) -> bool:
        """Check if current visual has finished."""
        if self.current_visual is None:
            return True
        return self.current_visual.complete()
    
    def get_progress(self) -> float:
        """Get progress through current visual [0.0 - 1.0]."""
        if self.current_visual is None:
            return 0.0
        return self.current_visual.progress()
    
    def get_frame_count(self) -> int:
        """Get number of frames processed."""
        return self._frame_count
    
    # ===== Cycle Tracking (Phase 2 - Session Synchronization) =====
    
    def get_cycle_count(self) -> int:
        """Get total number of media cycles completed.
        
        A cycle is one complete display of an image or video loop.
        Used by SessionRunner to synchronize transitions to cycle boundaries.
        
        Returns:
            Number of cycles completed since visual started
        """
        return self._cycle_count
    
    def set_current_cue_settings(self, cue_data: Optional[dict]) -> None:
        """Set current cue settings for features like vibration on text cycle.
        
        Args:
            cue_data: Dictionary containing cue settings (vibrate_on_text_cycle, vibration_intensity, etc.)
        """
        self._current_cue_settings = cue_data
        if cue_data:
            vibrate = cue_data.get('vibrate_on_text_cycle', False)
            intensity = cue_data.get('vibration_intensity', 0.5)
            self.logger.debug(f"[visual] Cue settings updated: vibrate={vibrate}, intensity={intensity:.0%}")
    
    def register_cycle_callback(self, callback: Callable[[], None]) -> None:
        """Register callback to fire when a media cycle completes.
        
        Args:
            callback: Function to call when cycle boundary is crossed (no arguments)
        """
        if callback not in self._cycle_callbacks:
            self._cycle_callbacks.append(callback)
            self.logger.debug(f"[visual] Registered cycle callback (total={len(self._cycle_callbacks)})")
    
    def unregister_cycle_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a previously registered cycle callback.
        
        Args:
            callback: The callback function to remove
        """
        if callback in self._cycle_callbacks:
            self._cycle_callbacks.remove(callback)
            self.logger.debug(f"[visual] Unregistered cycle callback (total={len(self._cycle_callbacks)})")
    
    def _check_cycle_boundary(self) -> None:
        """Check if current visual crossed a cycle boundary and fire callbacks.
        
        Called every frame from update(). Detects when the visual's cycle marker
        increments (indicating a new image or video loop started) and fires all
        registered callbacks.
        
        Handles two cases:
        1. Normal progression: marker increases (e.g., 5 → 6)
        2. Playback switch: marker resets to lower value (e.g., 5 → 1)
           - Happens when load_playback() creates new CustomVisual instance
           - Treat this as a cycle boundary to allow immediate transitions
        """
        # Only CustomVisual supports cycle tracking (has get_current_cycle method)
        if not hasattr(self.current_visual, 'get_current_cycle'):
            return
        
        try:
            current_marker = self.current_visual.get_current_cycle()
            
            # Detect boundary: marker increased OR decreased (playback switch)
            if current_marker > self._last_cycle_marker:
                # Normal case: marker advanced
                cycles_crossed = current_marker - self._last_cycle_marker
                self._cycle_count += cycles_crossed
                
                self.logger.info(f"[visual] Cycle boundary crossed: count={self._cycle_count} marker={current_marker}")
                
                # Fire all registered callbacks
                for callback in self._cycle_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        self.logger.error(f"[visual] Cycle callback error: {e}", exc_info=True)
                
                # Update marker for next check
                self._last_cycle_marker = current_marker
            
            elif current_marker < self._last_cycle_marker and current_marker > 0:
                # Playback switch detected: marker went backwards (e.g., 5 → 1)
                # This happens when load_playback() creates new CustomVisual with marker=0
                # Treat this as a cycle boundary for session transition purposes
                self.logger.info(f"[visual] Playback switch detected (marker: {self._last_cycle_marker} → {current_marker}), firing cycle boundary")
                
                # Fire all registered callbacks
                for callback in self._cycle_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        self.logger.error(f"[visual] Cycle callback error: {e}", exc_info=True)
                
                # Update marker for next check
                self._last_cycle_marker = current_marker
        except Exception as e:
            self.logger.error(f"[visual] Cycle boundary check error: {e}", exc_info=True)
    
    # ===== Playback Control =====
    
    def pause(self) -> None:
        """Pause current visual."""
        self._paused = True
        
        # Pause spiral rotation by setting speed to 0
        spiral = None
        if self.compositor and hasattr(self.compositor, 'spiral_director'):
            spiral = self.compositor.spiral_director
        elif self.compositor and hasattr(self.compositor, 'director'):
            spiral = self.compositor.director
        
        if spiral and hasattr(spiral, 'rotation_speed'):
            self._pause_saved_rotation_speed = spiral.rotation_speed
            spiral.set_rotation_speed(0.0)
    
    def resume(self) -> None:
        """Resume current visual."""
        self._paused = False
        
        # Restore spiral rotation speed (only if we have a saved value)
        if self._pause_saved_rotation_speed is not None:
            spiral = None
            if self.compositor and hasattr(self.compositor, 'spiral_director'):
                spiral = self.compositor.spiral_director
            elif self.compositor and hasattr(self.compositor, 'director'):
                spiral = self.compositor.director
            
            if spiral and hasattr(spiral, 'set_rotation_speed'):
                try:
                    spiral.set_rotation_speed(self._pause_saved_rotation_speed)
                except Exception as e:
                    self.logger.warning(f"[visual] Failed to restore rotation speed: {e}")
            self._pause_saved_rotation_speed = None
    
    def toggle_pause(self) -> bool:
        """Toggle pause state.
        
        Returns:
            New paused state (True = paused)
        """
        self._paused = not self._paused
        return self._paused
    
    def is_paused(self) -> bool:
        """Check if paused."""
        return self._paused
    
    def reset_current(self) -> None:
        """Reset current visual to start."""
        if self.current_visual:
            self.current_visual.reset()
            self._frame_count = 0
    
    # ===== Callbacks (connect visual programs → theme bank → compositor) =====
    
    def _on_change_image(self, index: int) -> None:
        """Load and display image from theme bank.
        
        Args:
            index: Image index (ignored - theme bank uses shuffler)
        """
        self.logger.debug(f"[visual] _on_change_image index={index} frame={self._frame_count}")
        
        # CRITICAL: Don't attempt image loading if compositor doesn't exist yet
        # Compositor is created when Launch is clicked, not during UI init
        if self.compositor is None:
            self.logger.warning(f"[visual] Compositor not ready - deferring image load")
            self._last_image_still_loading = True
            return
        
        with self._perf_section("image.apply", warn_ms=30.0, info_ms=18.0):
            try:
                # Use ThemeBank to get next image
                if not self.theme_bank:
                    self.logger.warning(f"[visual] ThemeBank not available")
                    self._last_image_still_loading = False
                    return
                
                image_data = self.theme_bank.get_image()
                
                if not image_data:
                    # Image not ready yet (async loading) - just continue, next change will load it
                    self._image_upload_counts["retry"] += 1
                    self._image_retry_pending += 1
                    self.logger.debug("[visual] Image still loading - retry queued")
                    if self._image_retry_sampler.record():
                        self.logger.info(
                            "[visual] Waiting for ThemeBank image (queued retries=%d)",
                            self._image_retry_pending,
                        )
                    self._last_image_still_loading = True
                    return
                
                # Image is ready - clear the loading flag
                self._last_image_still_loading = False
                queued_retries = self._image_retry_pending
                self._image_retry_pending = 0
                
                # Log the image path to verify correct directory
                image_path_str = str(image_data.path) if hasattr(image_data, 'path') else 'unknown'
                
                # Check if we ALREADY uploaded this image (retry after first successful load)
                # This prevents re-uploading the same image multiple times when retries succeed
                if hasattr(self, '_last_uploaded_image_path') and self._last_uploaded_image_path == image_path_str:
                    self.logger.debug(f"[visual] Image already uploaded; ignoring retry: {image_path_str}")
                    return  # Don't re-upload or restart zoom for same image
                
                # This is a NEW image (or first successful load of a retry)
                if hasattr(self, '_last_uploaded_image_path'):
                    self.logger.debug(f"[visual] Loading NEW image from ThemeBank: {image_path_str}")
                else:
                    self.logger.debug(f"[visual] Loading FIRST image from ThemeBank: {image_path_str}")
                
                # ImageData has width, height, and data (numpy array) - ready for GPU upload
                self.logger.debug(f"[visual] Image loaded: {image_data.width}x{image_data.height}")
                
                # Upload to ALL compositors and store each texture_id with its compositor
                compositor_texture_map = {}  # Map compositor -> texture_id
                
                # Upload to PRIMARY compositor
                texture_id = self.compositor.upload_image_to_gpu(image_data, generate_mipmaps=False)
                self.logger.debug(f"[visual] Uploaded to GPU (primary): texture_id={texture_id}")
                compositor_texture_map[self.compositor] = texture_id
                
                # Upload to all SECONDARY compositors (each gets its own texture_id)
                for i, secondary in enumerate(self._secondary_compositors, start=1):
                    try:
                        secondary_texture_id = secondary.upload_image_to_gpu(image_data, generate_mipmaps=False)
                        self.logger.debug(f"[visual] Uploaded to GPU (secondary {i}): texture_id={secondary_texture_id}")
                        compositor_texture_map[secondary] = secondary_texture_id
                    except Exception as e:
                        self.logger.error(f"[visual] Failed to upload to secondary compositor {i}: {e}")
                
                # Mark this image as uploaded to prevent re-uploading on retries
                self._last_uploaded_image_path = image_path_str
                
                # Set background texture on ALL compositors using EACH compositor's own texture_id
                for comp in compositor_texture_map.keys():
                    try:
                        comp_texture_id = compositor_texture_map[comp]
                        comp.set_background_texture(
                            comp_texture_id,  # Use THIS compositor's texture_id
                            zoom=1.0,
                            image_width=image_data.width,
                            image_height=image_data.height
                        )
                    except Exception as e:
                        self.logger.error(f"[visual] Failed to set background on compositor: {e}")
                
                # Start zoom-in animation (48 frames for images) - BUT skip if custom mode handles its own zoom
                should_start_zoom = True
                if self.is_custom_mode_active():
                    # Custom modes manage their own zoom settings - let them restart zoom animation
                    should_start_zoom = False
                    # Notify custom visual that new image was uploaded so it can restart zoom
                    if self.current_visual and hasattr(self.current_visual, '_restart_zoom_animation'):
                        self.current_visual._restart_zoom_animation()
                        self.logger.debug("[visual] Background texture applied (custom visual restarted zoom)")
                    else:
                        self.logger.debug("[visual] Background texture applied (custom mode manages zoom)")
                elif hasattr(self.compositor, '_zoom_animation_enabled') and not self.compositor._zoom_animation_enabled:
                    # Zoom disabled by user
                    should_start_zoom = False
                    self.logger.debug("[visual] Background texture applied (zoom disabled)")
                
                if should_start_zoom and hasattr(self.compositor, 'start_zoom_animation'):
                    self.compositor.start_zoom_animation(target_zoom=1.5, start_zoom=1.0, duration_frames=48)
                    self.logger.debug("[visual] Background texture applied with zoom animation")
                
                # Notify text director of media change (for CENTERED_SYNC mode)
                # Call this when image is actually uploaded (not before)
                if self.text_director and hasattr(self.text_director, 'on_media_change'):
                    self.text_director.on_media_change()
                
                # CRITICAL: Increment cycle marker ONLY after successful upload
                # This ensures cycle boundaries fire only when visual actually changes
                # Prevents desync during async image loading (no more "jumpy" cycles)
                if self.current_visual and hasattr(self.current_visual, '_cycle_marker'):
                    self.current_visual._cycle_marker += 1
                    self.logger.debug(f"[visual] Cycle marker incremented: {self.current_visual._cycle_marker}")

                zoom_state = "custom" if self.is_custom_mode_active() else ("animation" if should_start_zoom else "static")
                self.logger.debug(
                    "[visual] Image applied %s %dx%d secondaries=%d zoom=%s",
                    image_path_str,
                    image_data.width,
                    image_data.height,
                    len(self._secondary_compositors),
                    zoom_state,
                )
                self._image_upload_counts["success"] += 1
                self._log_themebank_media_snapshot(image_path=image_path_str)
                if queued_retries:
                    self.logger.info(
                        "[visual] Image applied after %d queued retry attempts", queued_retries
                    )
                if self._image_upload_sampler.record():
                    self._emit_image_upload_stats()
                
            except Exception as e:
                self.logger.error(f"Failed to change image: {e}", exc_info=True)
    
    def _on_change_image_zoom(self, index: int, zoom: float) -> None:
        """Load image with zoom effect (for AccelerateVisual).
        
        Args:
            index: Image index (ignored)
            zoom: Zoom factor [0.0 - 1.0]
        """
        if self.theme_bank is None or self.compositor is None:
            return
        
        try:
            image_data = self.theme_bank.get_image(alternate=False)
            
            if image_data is None:
                return
            
            from ..content.texture import upload_image_to_gpu
            texture_id = upload_image_to_gpu(image_data, generate_mipmaps=False)
            
            # Apply zoom: 1.0 to 1.5x based on zoom parameter
            actual_zoom = 1.0 + (zoom * 0.5)
            
            self.compositor.set_background_texture(
                texture_id,
                zoom=actual_zoom,
                image_width=image_data.width,
                image_height=image_data.height
            )
            
        except Exception as e:
            self.logger.error(f"Failed to change image with zoom: {e}", exc_info=True)
    
    def _on_change_text(self, text: str, split_mode: Optional[Any] = None) -> None:
        """Update main text overlay.
        
        Called by TextDirector when text changes. This triggers vibration if enabled.
        
        Args:
            text: Text string from TextDirector (already selected)
            split_mode: Split mode from TextDirector
        """
        if self.text_renderer is None or self.compositor is None:
            return
        
        # Check if we should vibrate on text cycle
        if self._current_cue_settings:
            vibrate = self._current_cue_settings.get('vibrate_on_text_cycle', False)
            if vibrate:
                intensity = self._current_cue_settings.get('vibration_intensity', 0.5)
                self.logger.info(f"[visual] Text changed, triggering vibration (intensity={intensity:.0%})")
                self._trigger_vibration(intensity)
            else:
                self.logger.debug(f"[visual] Text changed but vibration disabled in cue")
        else:
            self.logger.debug(f"[visual] Text changed but no cue settings available")
        
        # Text is already provided by TextDirector - no need to call get_random_text()
        # (calling get_random_text() here would cause infinite recursion)
        if not text:
            # No text provided, clear display
            self.compositor.clear_text_textures()
            return
        
        self.logger.debug(f"[visual] Text from callback: '{text}' (split: {split_mode})")
        
        with self._perf_section("text.main.render", warn_ms=18.0, info_ms=12.0):
            try:
                # Render text to texture
                rendered = self.text_renderer.render_main_text(text, large=True, shadow=True)
                
                if rendered and hasattr(rendered, 'texture_data'):
                    # Clear existing text on ALL compositors
                    for comp in self._get_all_compositors():
                        try:
                            comp.clear_text_textures()
                        except Exception as e:
                            self.logger.error(f"[visual] Failed to clear text on compositor: {e}")
                    
                    # Add new text to ALL compositors
                    for comp in self._get_all_compositors():
                        try:
                            comp.add_text_texture(
                                rendered.texture_data,
                                x=0.5,
                                y=0.5,
                                alpha=1.0,
                                scale=1.5
                            )
                        except Exception as e:
                            self.logger.error(f"[visual] Failed to add text on compositor: {e}")
            except Exception as e:
                self.logger.error(f"Failed to change text: {e}", exc_info=True)
    
    def _trigger_vibration(self, intensity: float) -> None:
        """Trigger vibration on connected devices.
        
        Args:
            intensity: Vibration intensity (0.0 to 1.0)
        """
        self.logger.info(f"[vibration] Triggering vibration at {intensity:.0%} intensity")
        try:
            if self.mesmer_server:
                import asyncio
                
                # Check if any devices have protocols (meaning they're connected and initialized)
                has_connected = bool(self.mesmer_server._device_protocols)
                if has_connected:
                    self.logger.debug(f"[vibration] Pulsing {len(self.mesmer_server._device_protocols)} device(s) at {intensity:.0%}")
                    # Use quick_pulse for rapid text cycles (100ms pulse vs 500ms test)
                    coro = self.mesmer_server.quick_pulse_all_devices(intensity=intensity)
                    
                    # Try to run in existing event loop
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Schedule as task in running loop
                            asyncio.create_task(coro)
                            self.logger.debug(f"[vibration] Scheduled vibration task in running loop")
                        else:
                            # Run in new event loop
                            asyncio.run(coro)
                            self.logger.debug(f"[vibration] Ran vibration in new event loop")
                    except RuntimeError:
                        # No event loop, create one
                        asyncio.run(coro)
                        self.logger.debug(f"[vibration] Created event loop and ran vibration")
                else:
                    self.logger.warning(f"[vibration] No devices with active protocols found")
            else:
                self.logger.warning(f"[vibration] MesmerIntifaceServer not available")
        except Exception as e:
            self.logger.error(f"[vibration] Failed to trigger vibration: {e}", exc_info=True)
    
    def _on_change_subtext(self, text: str) -> None:
        """Update subtext overlay (scrolling bands).
        
        Visual calls this when it wants a subtext change. We get the text from
        the text_director (respecting user's weights/split modes) instead of
        using the provided text.
        
        Args:
            text: Text string from visual (IGNORED - we use text_director instead)
        """
        if self.text_renderer is None or self.compositor is None:
            return
        
        # Get text from text_director if available
        if self.text_director:
            try:
                actual_text, split_mode = self.text_director.get_random_text()
                if not actual_text:
                    # No texts enabled, clear display on ALL compositors
                    for comp in self._get_all_compositors():
                        try:
                            comp.clear_text_textures()
                        except Exception as e:
                            self.logger.error(f"[visual] Failed to clear text on compositor: {e}")
                    return
                # TODO: Use split_mode when rendering
                text = actual_text
                self.logger.debug(f"[visual] Subtext from director: '{text}' (split: {split_mode})")
            except Exception as e:
                self.logger.warning(f"[visual] Failed to get subtext from director: {e}")
                # Fall back to provided text
        
        try:
            # Render subtext bands
            rendered = self.text_renderer.render_subtext([text])
            
            # Add to compositor (implementation depends on TextRenderer API)
            # For now, just log
            self.logger.debug(f"Subtext updated: {text[:20]}...")
            
        except Exception as e:
            self.logger.error(f"Failed to change subtext: {e}", exc_info=True)
    
    def _on_rotate_spiral(self) -> None:
        """Rotate spiral (standard speed)."""
        if self.compositor is None:
            return
        
        try:
            # Standard rotation amount (varies by visual)
            self.compositor.director.rotate_spiral(2.0)
        except Exception as e:
            self.logger.error(f"Failed to rotate spiral: {e}", exc_info=True)
    
    def _on_rotate_spiral_speed(self, speed: float) -> None:
        """Rotate spiral at variable speed (for AccelerateVisual).
        
        Args:
            speed: Rotation speed multiplier
        """
        if self.compositor is None:
            return
        
        try:
            self.compositor.director.rotate_spiral(speed)
        except Exception as e:
            self.logger.error(f"Failed to rotate spiral: {e}", exc_info=True)
    
    def _on_change_video(self, selection: Any) -> None:
        """Load and start video playback.

        Args:
            selection: Either a playlist index or a Path provided by ThemeBank
        """
        if self.video_streamer is None:
            if not hasattr(self, "_warned_missing_streamer"):
                self.logger.warning("[visual] Video requested but video_streamer is not available")
                self._warned_missing_streamer = True
            return

        if self.compositor is None:
            if not hasattr(self, "_warned_missing_compositor"):
                self.logger.warning("[visual] Video requested but compositor is not ready")
                self._warned_missing_compositor = True
            return
        
        # Reset diagnostic counters for the upcoming video
        self._video_frame_miss_count = 0
        self._video_frame_miss_logged = False
        self._video_first_upload_logged = False

        with self._perf_section("video.load", warn_ms=40.0, info_ms=25.0):
            try:
                if isinstance(selection, Path):
                    path = selection
                else:
                    video_paths = self._get_video_paths()
                    if not isinstance(selection, int):
                        self.logger.warning(f"[visual] Invalid video selection: {selection}")
                        return
                    if 0 <= selection < len(video_paths):
                        path = video_paths[selection]
                    else:
                        self.logger.warning(f"[visual] Video index {selection} out of range")
                        return

                success = self.video_streamer.load_video(path)
                    
                if success:
                    self.logger.info(f"[visual] Loaded video: {path.name}")
                    self._log_themebank_media_snapshot(image_path=str(path))
                    
                    # Mark that next frame is first frame of new video (for fade transition)
                    self._video_first_frame = True
                    
                    # Start zoom-in animation for video (300 frames for videos)
                    if hasattr(self.compositor, 'start_zoom_animation'):
                        self.compositor.start_zoom_animation(target_zoom=1.5, start_zoom=1.0, duration_frames=300)
                    
                    # Notify text director of media change (for CENTERED_SYNC mode)
                    if self.text_director and hasattr(self.text_director, 'on_media_change'):
                        self.text_director.on_media_change()
                    
                    # CRITICAL: Increment cycle marker ONLY after successful video load
                    if self.current_visual and hasattr(self.current_visual, '_cycle_marker'):
                        self.current_visual._cycle_marker += 1
                        self.logger.debug(f"[visual] Cycle marker incremented (video): {self.current_visual._cycle_marker}")
                else:
                    self.logger.warning(f"[visual] Failed to load video: {path.name}")
                
            except Exception as e:
                self.logger.error(f"Failed to change video: {e}", exc_info=True)
    
    # ===== Helper Methods =====
    
    def _get_image_paths(self) -> list[Path]:
        """Get image paths from theme bank.
        
        Returns:
            List of image paths (or dummy list if no theme bank)
        """
        if self.theme_bank is None:
            # Return dummy paths for testing
            return [Path(f"image_{i}.jpg") for i in range(20)]
        
        # Get active theme's image paths
        try:
            primary_idx = self.theme_bank._active_theme_indices[1]
            if primary_idx is not None:
                theme = self.theme_bank._themes[primary_idx]
                return [self.theme_bank._root_path / p for p in theme.image_path]
        except Exception:
            pass
        
        return []
    
    def _get_text_lines(self) -> list[str]:
        """Get text lines from theme bank.
        
        Returns:
            List of text strings (or dummy list if no theme bank)
        """
        if self.theme_bank is None:
            return [
                "Relax", "Breathe", "Focus", "Let go", "Sink deeper",
                "Feel the spiral", "Watch the colors", "Empty your mind"
            ]
        
        # Get active theme's text lines
        try:
            primary_idx = self.theme_bank._active_theme_indices[1]
            if primary_idx is not None:
                theme = self.theme_bank._themes[primary_idx]
                return list(theme.text_line)
        except Exception:
            pass
        
        return []
    
    def _get_video_paths(self) -> list[Path]:
        """Get video paths from theme bank.
        
        Returns:
            List of video paths (or dummy list if no theme bank)
        """
        if self.theme_bank is None:
            return [Path(f"video_{i}.mp4") for i in range(5)]
        
        # Get active theme's animation paths
        try:
            primary_idx = self.theme_bank._active_theme_indices[1]
            if primary_idx is not None:
                theme = self.theme_bank._themes[primary_idx]
                return [self.theme_bank._root_path / p for p in theme.animation_path]
        except Exception:
            pass
        
        return []

    def _get_video_streamer_state(self) -> dict[str, Any]:
        """Collect lightweight diagnostics about the current video streamer."""
        if not self.video_streamer:
            return {"available": False}

        state: dict[str, Any] = {"available": True}

        try:
            state["loaded"] = self.video_streamer.is_loaded()
        except Exception:
            state["loaded"] = "error"

        if hasattr(self.video_streamer, "get_frame_count"):
            try:
                state["buffered_frames"] = self.video_streamer.get_frame_count()
            except Exception:
                state["buffered_frames"] = "error"

        if hasattr(self.video_streamer, "get_current_video_path"):
            try:
                path = self.video_streamer.get_current_video_path()
                state["video"] = str(path) if path else None
            except Exception:
                state["video"] = "error"

        return state
    
    # ===== Info Methods =====

