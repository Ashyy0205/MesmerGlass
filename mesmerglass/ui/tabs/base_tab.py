"""Base tab class for Phase 7 vertical tab interface.

Provides standard interface and lifecycle methods for all tabs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
    from ..main_application import MainApplication


class BaseTab(QWidget):
    """Base class for all tabs in the main application.
    
    Provides:
    - Standard lifecycle hooks (on_show, on_hide, on_update)
    - Access to parent window and shared engines
    - Consistent interface for all tabs
    """
    
    def __init__(self, parent: MainApplication):
        super().__init__(parent)
        self.main_window = parent
    
    def on_show(self):
        """Called when tab becomes visible.
        
        Override to refresh data, start timers, etc.
        """
        pass
    
    def on_hide(self):
        """Called when tab becomes hidden.
        
        Override to pause timers, save state, etc.
        """
        pass
    
    def on_update(self, *args, **kwargs):
        """Called when tab needs to refresh data.
        
        Override to reload data from disk, update displays, etc.
        """
        pass
    
    # === Convenient access to shared engines ===
    
    @property
    def visual_director(self):
        """Access to VisualDirector."""
        return self.main_window.visual_director
    
    @property
    def audio_engine(self):
        """Access to AudioEngine."""
        return self.main_window.audio_engine
    
    @property
    def compositor(self):
        """Access to LoomCompositor."""
        return self.main_window.compositor
    
    @property
    def spiral_director(self):
        """Access to SpiralDirector."""
        return self.main_window.spiral_director
    
    @property
    def text_director(self):
        """Access to TextDirector."""
        return self.main_window.text_director
    
    @property
    def device_manager(self):
        """Access to DeviceManager."""
        return self.main_window.device_manager
    
    def mark_dirty(self):
        """Mark session as having unsaved changes."""
        self.main_window.mark_session_dirty()
