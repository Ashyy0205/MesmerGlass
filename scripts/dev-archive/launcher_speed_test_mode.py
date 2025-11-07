#!/usr/bin/env python3
"""
Launcher Speed Test Mode - Automatically cycles through different rotation speeds
"""

import sys
import time
import logging
from pathlib import Path
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesmerglass.ui.launcher import Launcher

class LauncherSpeedTestMode(Launcher):
    """Launcher in speed test mode - automatically cycles through speeds"""
    
    def __init__(self):
        super().__init__(title="Launcher Speed Test Mode")
        
        # Test speeds to cycle through
        self.test_speeds = [4.0, 8.0, 16.0, 24.0]
        self.current_speed_index = 0
        self.speed_duration = 8000  # 8 seconds per speed in milliseconds
        
        # Setup speed change timer
        self.speed_change_timer = QTimer()
        self.speed_change_timer.timeout.connect(self._change_speed)
        self.speed_change_timer.start(self.speed_duration)
        
        # Ensure at least one display is selected for overlay creation
        # This is critical for the spiral timer to start
        if hasattr(self, 'list_displays') and self.list_displays.count() > 0:
            self.list_displays.item(0).setCheckState(Qt.CheckState.Checked)
            print(f"[LAUNCHER_TEST] Selected display 0 for overlay")
        
        # Start with first speed
        self._set_test_speed(self.test_speeds[0])
        
        print(f"[LAUNCHER_TEST] Started with speed {self.test_speeds[0]}")
        print(f"[LAUNCHER_TEST] Expected zoom rate: {0.05 * self.test_speeds[0]}")
        
        # Load a simple spiral visual mode for testing
        try:
            mode_path = Path(__file__).parent.parent / "mesmerglass" / "modes" / "speed_test.json"
            if mode_path.exists():
                print(f"[LAUNCHER_TEST] Loading spiral mode: {mode_path}")
                self._on_custom_mode_requested(str(mode_path))
                print(f"[LAUNCHER_TEST] Spiral mode loaded successfully")
            else:
                print(f"[LAUNCHER_TEST] Speed test mode not found: {mode_path}")
        except Exception as e:
            print(f"[LAUNCHER_TEST] Failed to load spiral mode: {e}")
        
        # Launch the visual session to start spirals and overlays
        try:
            # Ensure spiral is enabled before launching
            if hasattr(self, '_on_spiral_toggled'):
                self._on_spiral_toggled(True)
                print(f"[LAUNCHER_TEST] Enabled spiral before launch")
            
            self.launch()
            print(f"[LAUNCHER_TEST] Visual session launched successfully")
            
            # Force spiral timer start if needed
            if hasattr(self, 'spiral_timer') and not self.spiral_timer.isActive():
                self.spiral_timer.start()
                print(f"[LAUNCHER_TEST] Manually started spiral timer")
                
        except Exception as e:
            print(f"[LAUNCHER_TEST] Failed to launch visual session: {e}")
            # Fallback to manual spiral enable
            try:
                self._on_spiral_toggled(True)
                print(f"[LAUNCHER_TEST] Manual spiral enable successful")
            except Exception as e2:
                print(f"[LAUNCHER_TEST] Manual spiral enable failed: {e2}")
        
        # Track zoom state
        self.zoom_level = 1.0
        self.last_zoom_level = 1.0
        
    def _set_test_speed(self, speed: float):
        """Set the rotation speed for testing"""
        if hasattr(self, 'spiral_director') and self.spiral_director:
            self.spiral_director.set_rotation_speed(speed)
            
            # Reset phase accumulator for clean measurement
            if hasattr(self.spiral_director, '_phase_accumulator'):
                self.spiral_director._phase_accumulator = 0.0
    
    def _change_speed(self):
        """Change to next speed in the test sequence"""
        self.current_speed_index = (self.current_speed_index + 1) % len(self.test_speeds)
        new_speed = self.test_speeds[self.current_speed_index]
        
        print(f"[LAUNCHER_TEST] Changing speed to {new_speed}")
        print(f"[LAUNCHER_TEST] Expected zoom rate: {0.05 * new_speed}")
        self._set_test_speed(new_speed)
        
        # Reset zoom level for clean measurement
        self.zoom_level = 1.0
        self.last_zoom_level = 1.0

def main():
    """Run launcher in speed test mode"""
    app = QApplication(sys.argv)
    
    # Create and show the launcher in test mode
    launcher = LauncherSpeedTestMode()
    launcher.show()
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()