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
        text_director: Optional[Any] = None
    ):
        """Initialize visual director.
        
        Args:
            theme_bank: ThemeBank instance for image/text selection
            compositor: LoomCompositor instance for rendering
            text_renderer: TextRenderer instance for text overlays
            video_streamer: VideoStreamer instance for video playback
            text_director: TextDirector instance for text library management
        """
        self.theme_bank = theme_bank
        self.compositor = compositor
        self.text_renderer = text_renderer
        self.video_streamer = video_streamer
        self.text_director = text_director
        
        self.current_visual: Optional[Visual] = None
        self._paused = False
        self._frame_count = 0
        self._video_first_frame = False  # Track first frame of new video for fade
        self._pending_image_path = None  # Path of image we're waiting to load
        
        self.logger = logging.getLogger(__name__)
    
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
    
    def select_custom_visual(self, mode_path: Path) -> bool:
        """
        Select and initialize a CustomVisual from mode file.
        
        Args:
            mode_path: Path to JSON mode file
        
        Returns:
            True if successfully loaded, False on error
        """
        try:
            from .custom_visual import CustomVisual
            
            # Validate mode file first
            is_valid, error_msg = CustomVisual.validate_mode_file(mode_path)
            if not is_valid:
                self.logger.error(f"[CustomVisual] Invalid mode file: {error_msg}")
                return False
            
            self.logger.info(f"[CustomVisual] Loading mode from: {mode_path.name}")
            
            # Create CustomVisual instance
            custom_visual = CustomVisual(
                mode_path=mode_path,
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
            
            # Store as current visual
            self.current_visual = custom_visual
            self._paused = False
            self._frame_count = 0
            
            # Reset visual to initial state
            self.current_visual.reset()
            
            self.logger.info(f"[CustomVisual] Mode '{custom_visual.mode_name}' loaded successfully")
            return True
            
        except ImportError:
            self.logger.error("[CustomVisual] CustomVisual class not available")
            return False
        except Exception as e:
            self.logger.error(f"[CustomVisual] Failed to load mode: {e}", exc_info=True)
            return False
    
    # ===== Update Loop =====
    
    def update(self, dt: Optional[float] = None) -> None:
        """Update current visual (advance cycler).
        
        Args:
            dt: Delta time in seconds (unused, cyclers are frame-based)
        """
        # CRITICAL: Process async image loading in ThemeBank
        if self.theme_bank and hasattr(self.theme_bank, 'async_update'):
            self.theme_bank.async_update()
        
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
        try:
            cycler.advance()
            self._frame_count += 1
            
            # Update video playback if this visual supports videos
            # CustomVisual handles its own video state via is_showing_video() method
            should_update_video = (
                self.video_streamer and self.compositor and 
                hasattr(self.current_visual, 'is_showing_video') and 
                self.current_visual.is_showing_video()
            )
            
            if should_update_video:
                try:
                    # Advance video playback
                    self.video_streamer.update(global_fps=60.0)
                    
                    # Get current frame and upload to compositor
                    frame = self.video_streamer.get_current_frame()
                    if frame:
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
                except Exception as ve:
                    # Only log video errors occasionally to avoid spam
                    if self._frame_count % 300 == 0:
                        self.logger.warning(f"[visual] Video update error: {ve}")
            
            # Debug: Log every 60 frames to verify update is being called
            if self._frame_count % 60 == 0:
                is_complete = self.current_visual.complete()
                self.logger.info(f"[visual] Update: frame={self._frame_count} progress={self.current_visual.progress():.2f} complete={is_complete}")
        except Exception as e:
            self.logger.error(f"Error advancing cycler: {e}", exc_info=True)
    
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
    
    # ===== Playback Control =====
    
    def pause(self) -> None:
        """Pause current visual."""
        self._paused = True
    
    def resume(self) -> None:
        """Resume current visual."""
        self._paused = False
    
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
        self.logger.info(f"[visual] _on_change_image called (index={index}) frame={self._frame_count}")
        
        # CRITICAL: Don't attempt image loading if compositor doesn't exist yet
        # Compositor is created when Launch is clicked, not during UI init
        if self.compositor is None:
            self.logger.warning(f"[visual] Compositor not ready - deferring image load")
            return
        
        try:
            # Use ThemeBank to get next image
            if not self.theme_bank:
                self.logger.warning(f"[visual] ThemeBank not available")
                return
            
            image_data = self.theme_bank.get_image()
            
            if not image_data:
                # Image not ready yet (async loading) - just continue, next change will load it
                self.logger.info(f"[visual] Image still loading - will load on next cycle")
                return
            
            # Log the image path to verify correct directory
            image_path_str = str(image_data.path) if hasattr(image_data, 'path') else 'unknown'
            
            # Check if we ALREADY uploaded this image (retry after first successful load)
            # This prevents re-uploading the same image multiple times when retries succeed
            if hasattr(self, '_last_uploaded_image_path') and self._last_uploaded_image_path == image_path_str:
                self.logger.info(f"[visual] Image already uploaded and displaying - ignoring retry: {image_path_str}")
                return  # Don't re-upload or restart zoom for same image
            
            # This is a NEW image (or first successful load of a retry)
            if hasattr(self, '_last_uploaded_image_path'):
                self.logger.info(f"[visual] Loading NEW image from ThemeBank: {image_path_str}")
            else:
                self.logger.info(f"[visual] Loading FIRST image from ThemeBank: {image_path_str}")
            
            # ImageData has width, height, and data (numpy array) - ready for GPU upload
            self.logger.info(f"[visual] Image loaded: {image_data.width}x{image_data.height}")
            
            # Upload to GPU
            from ..content.texture import upload_image_to_gpu
            texture_id = upload_image_to_gpu(image_data, generate_mipmaps=False)
            
            self.logger.info(f"[visual] Uploaded to GPU: texture_id={texture_id}")
            
            # Mark this image as uploaded to prevent re-uploading on retries
            self._last_uploaded_image_path = image_path_str
            
            self.compositor.set_background_texture(
                texture_id,
                zoom=1.0,
                image_width=image_data.width,
                image_height=image_data.height
            )
            
            # Start zoom-in animation (48 frames for images) - BUT skip if custom mode handles its own zoom
            should_start_zoom = True
            if self.is_custom_mode_active():
                # Custom modes manage their own zoom settings - let them restart zoom animation
                should_start_zoom = False
                # Notify custom visual that new image was uploaded so it can restart zoom
                if self.current_visual and hasattr(self.current_visual, '_restart_zoom_animation'):
                    self.current_visual._restart_zoom_animation()
                    self.logger.info(f"[visual] Background texture set successfully (custom mode restarted zoom)")
                else:
                    self.logger.info(f"[visual] Background texture set successfully (custom mode manages zoom)")
            elif hasattr(self.compositor, '_zoom_animation_enabled') and not self.compositor._zoom_animation_enabled:
                # Zoom disabled by user
                should_start_zoom = False
                self.logger.info(f"[visual] Background texture set successfully (zoom disabled)")
            
            if should_start_zoom and hasattr(self.compositor, 'start_zoom_animation'):
                self.compositor.start_zoom_animation(target_zoom=1.5, start_zoom=1.0, duration_frames=48)
                self.logger.info(f"[visual] Background texture set successfully with zoom animation")
            
            # Notify text director of media change (for CENTERED_SYNC mode)
            # Call this when image is actually uploaded (not before)
            if self.text_director and hasattr(self.text_director, 'on_media_change'):
                self.text_director.on_media_change()
            
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
    
    def _on_change_text(self, text: str) -> None:
        """Update main text overlay.
        
        Visual calls this when it wants a text change. We get the text from
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
                    # No texts enabled, clear display
                    self.compositor.clear_text_textures()
                    return
                # TODO: Use split_mode when rendering
                text = actual_text
                self.logger.debug(f"[visual] Text from director: '{text}' (split: {split_mode})")
            except Exception as e:
                self.logger.warning(f"[visual] Failed to get text from director: {e}")
                # Fall back to provided text
        
        try:
            # Render text to texture
            rendered = self.text_renderer.render_main_text(text, large=True, shadow=True)
            
            if rendered and hasattr(rendered, 'texture_data'):
                # Clear existing text
                self.compositor.clear_text_textures()
                
                # Add new text
                self.compositor.add_text_texture(
                    rendered.texture_data,
                    x=0.5,
                    y=0.5,
                    alpha=1.0,
                    scale=1.5
                )
        except Exception as e:
            self.logger.error(f"Failed to change text: {e}", exc_info=True)
    
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
                    # No texts enabled, clear display
                    self.compositor.clear_text_textures()
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
    
    def _on_change_video(self, index: int) -> None:
        """Load and start video playback.
        
        Args:
            index: Video index
        """
        if self.video_streamer is None or self.compositor is None:
            return
        
        try:
            video_paths = self._get_video_paths()
            
            if 0 <= index < len(video_paths):
                path = video_paths[index]
                success = self.video_streamer.load_video(path)
                
                if success:
                    self.logger.info(f"[visual] Loaded video: {path.name}")
                    
                    # Mark that next frame is first frame of new video (for fade transition)
                    self._video_first_frame = True
                    
                    # Start zoom-in animation for video (300 frames for videos)
                    if hasattr(self.compositor, 'start_zoom_animation'):
                        self.compositor.start_zoom_animation(target_zoom=1.5, start_zoom=1.0, duration_frames=300)
                    
                    # CRITICAL: Disable static image background when video starts
                    # The video frames will be uploaded continuously via update()
                    # No need to clear the texture - video frames will overwrite it
                    
                    # Notify text director of media change (for CENTERED_SYNC mode)
                    if self.text_director and hasattr(self.text_director, 'on_media_change'):
                        self.text_director.on_media_change()
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
    
    # ===== Info Methods =====

