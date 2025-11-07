#!/usr/bin/env python3
"""
VMC Speed Test Mode - Automatically cycles through different rotation speeds
"""

import sys
import logging
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QTimer

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesmerglass.mesmerloom.compositor import LoomCompositor
from mesmerglass.mesmerloom.spiral import SpiralDirector

class VMCSpeedTestMode(QMainWindow):
    """VMC in speed test mode - automatically cycles through speeds"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VMC Speed Test Mode")
        self.setGeometry(100, 100, 1280, 720)
        
        # Test speeds to cycle through
        self.test_speeds = [4.0, 8.0, 16.0, 24.0]
        self.current_speed_index = 0
        self.speed_duration = 8000  # 8 seconds per speed in milliseconds
        
        # Zoom tracking
        self.zoom_level = 1.0
        self.zoom_rate = 0.0
        self.last_zoom_time = time.time()
        
        # Create spiral director
        self.spiral_director = SpiralDirector()
        self.spiral_director.set_rotation_speed(self.test_speeds[0])
        
        # Create compositor
        self.compositor = LoomCompositor(self.spiral_director, self)
        self.setCentralWidget(self.compositor)
        
        # Setup timers
        self.spiral_timer = QTimer()
        self.spiral_timer.timeout.connect(self._on_spiral_tick)
        self.spiral_timer.start(16)  # 60 FPS
        
        self.speed_change_timer = QTimer()
        self.speed_change_timer.timeout.connect(self._change_speed)
        self.speed_change_timer.start(self.speed_duration)
        
        print(f"[VMC_TEST] Started with speed {self.test_speeds[0]}")
        print(f"[VMC_TEST] Expected zoom rate: {0.05 * self.test_speeds[0]}")
        
    def _on_spiral_tick(self):
        """Update spiral with standard rotation method"""
        try:
            # Use standard spiral rotation - the method now handles RPM calculation internally
            self.spiral_director.rotate_spiral(4.0)  # amount is ignored in new RPM mode
            
            # Update spiral director
            self.spiral_director.update(1/60.0)
            
            # Get uniforms and print debug info every 4th tick
            if not hasattr(self, '_tick_count'):
                self._tick_count = 0
            self._tick_count += 1
            
            if self._tick_count % 4 == 0:
                uniforms = self.spiral_director.export_uniforms()
                
                # Calculate zoom rate (simulated since VMC doesn't have actual zoom)
                current_time = time.time()
                dt = current_time - self.last_zoom_time
                if dt > 0:
                    # Simulate zoom based on rotation speed
                    current_rotation_speed = uniforms.get('rotation_speed', 4.0)
                    expected_zoom_rate = 0.05 * current_rotation_speed
                    # Add small variation to simulate real zoom
                    zoom_delta = expected_zoom_rate * dt * 0.1  # 10% of expected rate
                    self.zoom_level += zoom_delta
                    self.zoom_rate = zoom_delta / dt if dt > 0 else 0.0
                self.last_zoom_time = current_time
                
                print(f"[VMC rotation_debug] phase={uniforms.get('uPhase', 0):.6f}")
                print(f"[VMC rotation_debug] time={uniforms.get('time', 0):.6f}")
                print(f"[VMC rotation_debug] rotation_speed={uniforms.get('rotation_speed', 0)}")
                print(f"[VMC rotation_debug] uEffectiveSpeed={uniforms.get('uEffectiveSpeed', 0)}")
                print(f"[VMC rotation_debug] uBaseSpeed={uniforms.get('uBaseSpeed', 0)}")
                print(f"[VMC rotation_debug] uIntensity={uniforms.get('uIntensity', 0)}")
                print(f"[VMC zoom_debug] zoom_level={self.zoom_level:.6f}")
                print(f"[VMC zoom_debug] zoom_rate={self.zoom_rate:.6f}")
            
            # Update compositor
            if hasattr(self.compositor, 'update'):
                self.compositor.update()
                
        except Exception as e:
            logging.getLogger(__name__).error(f"Spiral tick error: {e}")
    
    def _change_speed(self):
        """Change to next speed in the test sequence"""
        self.current_speed_index = (self.current_speed_index + 1) % len(self.test_speeds)
        new_speed = self.test_speeds[self.current_speed_index]
        
        print(f"[VMC_TEST] Changing speed to {new_speed}")
        print(f"[VMC_TEST] Expected zoom rate: {0.05 * new_speed}")
        self.spiral_director.set_rotation_speed(new_speed)
        
        # Reset phase accumulator and zoom for clean measurement
        if hasattr(self.spiral_director, '_phase_accumulator'):
            self.spiral_director._phase_accumulator = 0.0
        self.zoom_level = 1.0

def main():
    app = QApplication(sys.argv)
    
    # Create and show the test window
    window = VMCSpeedTestMode()
    window.show()
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()