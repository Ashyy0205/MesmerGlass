"""
Visual Test: Playback Pool Cycling

Tests that a cue with multiple playbacks in its pool actually switches between them.
Shows visual output with playback names and timing.

Setup:
- Creates a test session with one cue
- Cue has 3 playbacks in pool with different names
- Selection mode: "on_media_cycle" (should switch every media cycle)
- Duration: 30 seconds (long enough to see multiple switches)
- Each playback has simple spiral with different arm counts for visual distinction

Expected behavior:
- Cue starts with first playback from pool
- Every ~3-5 seconds (media cycle), should switch to different playback
- Console shows which playback is loaded
- Visual shows spiral arm count changing (3, 5, 7 arms)
"""

import sys
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont

# Add mesmerglass to path
sys.path.insert(0, str(Path(__file__).parent))

from mesmerglass.session.cue import Cue, PlaybackEntry, PlaybackSelectionMode
from mesmerglass.session.cuelist import Cuelist
from mesmerglass.session.runner import SessionRunner
from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.mesmerloom.window_compositor import LoomWindowCompositor
from mesmerglass.mesmerloom.visual_director import VisualDirector
from mesmerglass.engine.text_director import TextDirector
from mesmerglass.content.themebank import ThemeBank


class PlaybackPoolTestWindow(QMainWindow):
    """Visual test window showing playback pool cycling."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playback Pool Visual Test")
        self.resize(800, 200)
        
        # Central widget with large text labels
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("🔄 Playback Pool Cycling Test")
        title.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Current playback label
        self.playback_label = QLabel("Playback: (not started)")
        self.playback_label.setFont(QFont("Arial", 16))
        self.playback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playback_label.setStyleSheet("color: #00FF00; background: black; padding: 10px;")
        layout.addWidget(self.playback_label)
        
        # Spiral info label
        self.spiral_label = QLabel("Spiral: (not started)")
        self.spiral_label.setFont(QFont("Arial", 14))
        self.spiral_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.spiral_label)
        
        # Timing label
        self.timing_label = QLabel("Elapsed: 0.0s | Cycles: 0")
        self.timing_label.setFont(QFont("Arial", 12))
        self.timing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.timing_label)
        
        # Status label
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: yellow;")
        layout.addWidget(self.status_label)
        
        # Initialize session components
        self.session_runner: Optional[SessionRunner] = None
        self.visual_director: Optional[VisualDirector] = None
        self.start_time = 0.0
        self.last_playback_name = ""
        self.playback_change_count = 0
        
        # Create test session
        self._create_test_session()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(16)  # 60fps
        
    def _create_test_session(self):
        """Create a test session with playback pool."""
        try:
            self.status_label.setText("Status: Creating test playbacks...")
            
            # Create test directory for playbacks
            test_dir = Path(__file__).parent / "test_playback_pool_data"
            test_dir.mkdir(exist_ok=True)
            
            # Create 3 test playback JSON files with different spiral settings
            playback_configs = [
                {
                    "name": "Playback A - 3 Arms",
                    "arms": 3,
                    "cycle_speed": 30,
                    "file": test_dir / "playback_a.playback.json"
                },
                {
                    "name": "Playback B - 5 Arms", 
                    "arms": 5,
                    "cycle_speed": 50,
                    "file": test_dir / "playback_b.playback.json"
                },
                {
                    "name": "Playback C - 7 Arms",
                    "arms": 7,
                    "cycle_speed": 70,
                    "file": test_dir / "playback_c.playback.json"
                }
            ]
            
            # Write playback files
            import json
            for config in playback_configs:
                playback_data = {
                    "version": "1.0",
                    "name": config["name"],
                    "spiral": {
                        "enabled": True,
                        "arms": config["arms"],
                        "type": "logarithmic",
                        "rotation_speed": 1.0,
                        "direction": "clockwise"
                    },
                    "media": {
                        "mode": "images",
                        "cycle_speed": config["cycle_speed"],
                        "fade_duration": 0.5,
                        "use_theme_bank": True
                    },
                    "text": {
                        "enabled": False,
                        "messages": []
                    },
                    "zoom": {
                        "enabled": False
                    }
                }
                config["file"].write_text(json.dumps(playback_data, indent=2))
            
            self.status_label.setText("Status: Creating engines...")
            
            # Create visual components
            self.spiral_director = SpiralDirector()
            self.compositor = LoomWindowCompositor(
                self.spiral_director,
                is_primary=True
            )
            self.text_director = TextDirector()
            
            # Create a simple theme bank with test images
            from mesmerglass.content.theme import ThemeConfig
            media_root = Path(__file__).parent / "MEDIA"
            test_theme = ThemeConfig(
                name="Test Theme",
                enabled=True,
                image_path=["Images/*.jpg", "Images/*.png"],
                animation_path=[],
                font_path=[],
                text_line=[]
            )
            self.theme_bank = ThemeBank(
                themes=[test_theme],
                root_path=media_root,
                image_cache_size=10
            )
            
            self.visual_director = VisualDirector(
                self.compositor,
                self.text_director,
                self.theme_bank
            )
            
            self.status_label.setText("Status: Creating cue with playback pool...")
            
            # Create cue with playback pool
            cue = Cue(
                name="Test Cue - Cycling Playbacks",
                duration_seconds=30,  # Long enough to see multiple switches
                playback_pool=[
                    PlaybackEntry(
                        playback_path=str(playback_configs[0]["file"]),
                        weight=1.0,
                        min_cycles=1,
                        max_cycles=3
                    ),
                    PlaybackEntry(
                        playback_path=str(playback_configs[1]["file"]),
                        weight=1.0,
                        min_cycles=1,
                        max_cycles=3
                    ),
                    PlaybackEntry(
                        playback_path=str(playback_configs[2]["file"]),
                        weight=1.0,
                        min_cycles=1,
                        max_cycles=3
                    )
                ],
                selection_mode=PlaybackSelectionMode.ON_MEDIA_CYCLE,  # Switch at media cycle
                audio_tracks=[]
            )
            
            # Create cuelist
            cuelist = Cuelist(
                name="Playback Pool Test",
                description="Test playback switching within a cue",
                cues=[cue],
                loop_mode="once"
            )
            
            self.status_label.setText("Status: Starting session runner...")
            
            # Create and start session runner
            self.session_runner = SessionRunner(
                cuelist=cuelist,
                visual_director=self.visual_director,
                audio_engine=None
            )
            
            # Start the session
            if not self.session_runner.start():
                self.status_label.setText("❌ Status: Failed to start session!")
                self.status_label.setStyleSheet("color: red;")
                return
            
            self.start_time = time.time()
            self.status_label.setText("✅ Status: Session running - watching for playback changes...")
            self.status_label.setStyleSheet("color: #00FF00;")
            
            print("\n" + "="*80)
            print("🔄 PLAYBACK POOL TEST STARTED")
            print("="*80)
            print(f"Cue: {cue.name}")
            print(f"Duration: {cue.duration_seconds}s")
            print(f"Selection Mode: {cue.selection_mode.value}")
            print(f"Playbacks in pool: {len(cue.playback_pool)}")
            for i, entry in enumerate(cue.playback_pool):
                print(f"  {i+1}. {Path(entry.playback_path).stem} (weight={entry.weight}, cycles={entry.min_cycles}-{entry.max_cycles})")
            print("\nEXPECTED: Playback should change every media cycle (~3-5 seconds)")
            print("WATCHING: Visual label will show current playback name")
            print("="*80 + "\n")
            
        except Exception as e:
            import traceback
            self.status_label.setText(f"❌ Status: Error - {e}")
            self.status_label.setStyleSheet("color: red;")
            print(f"ERROR creating test session: {e}")
            traceback.print_exc()
    
    def _update_display(self):
        """Update display with current session state."""
        if not self.session_runner or not self.visual_director:
            return
        
        try:
            # Update session
            self.session_runner.update(dt=0.016)
            
            # Get current playback info from current_visual
            if self.visual_director.current_visual and hasattr(self.visual_director.current_visual, 'playback_name'):
                playback_name = self.visual_director.current_visual.playback_name
                
                # Detect playback changes
                if playback_name != self.last_playback_name:
                    if self.last_playback_name:  # Not the first playback
                        self.playback_change_count += 1
                        print(f"\n🔄 PLAYBACK CHANGED! (#{self.playback_change_count})")
                        print(f"   From: {self.last_playback_name}")
                        print(f"   To:   {playback_name}")
                        print(f"   Time: {time.time() - self.start_time:.1f}s")
                    
                    self.last_playback_name = playback_name
                
                self.playback_label.setText(f"Playback: {playback_name} (Changes: {self.playback_change_count})")
            else:
                self.playback_label.setText("Playback: (none loaded)")
            
            # Get spiral info
            arms = self.spiral_director.arm_count
            direction = "clockwise" if self.spiral_director.rotation_speed > 0 else "counter-clockwise"
            speed = abs(self.spiral_director.rotation_speed)
            self.spiral_label.setText(f"Spiral: {arms} arms | {direction} | speed={speed:.2f}")
            
            # Get timing info
            elapsed = time.time() - self.start_time if self.start_time > 0 else 0.0
            cycles = self.visual_director.get_cycle_count()
            self.timing_label.setText(f"Elapsed: {elapsed:.1f}s | Media Cycles: {cycles} | Playback Changes: {self.playback_change_count}")
            
        except Exception as e:
            print(f"Update error: {e}")
    
    def closeEvent(self, event):
        """Clean up on close."""
        print("\n" + "="*80)
        print("🏁 TEST ENDED")
        print(f"Total playback changes: {self.playback_change_count}")
        if self.playback_change_count == 0:
            print("❌ FAILED: No playback changes detected!")
            print("   The playback pool is NOT switching between playbacks.")
        else:
            print(f"✅ SUCCESS: {self.playback_change_count} playback changes detected!")
        print("="*80 + "\n")
        
        if self.session_runner:
            self.session_runner.stop()
        event.accept()


def main():
    """Run the visual test."""
    app = QApplication(sys.argv)
    window = PlaybackPoolTestWindow()
    window.show()
    
    # Also show the compositor window
    if hasattr(window, 'compositor'):
        window.compositor.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
