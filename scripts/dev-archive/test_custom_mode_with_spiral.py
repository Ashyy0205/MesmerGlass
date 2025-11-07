"""
Enhanced Test: Custom Mode with Spiral Window Creation

This test:
1. Launches the GUI
2. Loads sinking.json
3. Enables spiral
4. Creates spiral windows (simulates clicking Launch)
5. Verifies spiral settings match the mode
"""

import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main test with spiral window creation."""
    logger.info("="*70)
    logger.info("Enhanced Custom Mode Test - With Spiral Windows")
    logger.info("="*70)
    
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from mesmerglass.ui.launcher import Launcher
    
    app = QApplication(sys.argv)
    app.setApplicationName("MesmerGlass - Enhanced Test")
    
    logger.info("Creating launcher...")
    launcher = Launcher(title="MesmerGlass - Enhanced Test")
    launcher.show()
    
    mode_path = project_root / "mesmerglass" / "modes" / "sinking.json"
    
    if not mode_path.exists():
        logger.error(f"Mode not found: {mode_path}")
        return 1
    
    def run_enhanced_test():
        """Run the enhanced test sequence."""
        try:
            print("\n" + "="*70)
            print("STEP 1: Load custom mode")
            print("="*70)
            logger.info("\n" + "="*70)
            logger.info("STEP 1: Load custom mode")
            logger.info("="*70)
            
            success = launcher.visual_director.select_custom_visual(mode_path)
            if not success:
                logger.error("❌ Failed to load custom mode")
                return
            
            logger.info("✅ Custom mode loaded")
            
            # Lock controls
            if hasattr(launcher.page_mesmerloom, 'lock_controls'):
                launcher.page_mesmerloom.lock_controls()
            if hasattr(launcher.page_visual_programs, 'lock_visual_selector'):
                launcher.page_visual_programs.lock_visual_selector()
            
            logger.info("\n" + "="*70)
            logger.info("STEP 2: Enable spiral")
            logger.info("="*70)
            
            launcher.spiral_enabled = True
            logger.info("✅ Spiral enabled")
            
            logger.info("\n" + "="*70)
            logger.info("STEP 3: Create spiral windows (simulate Launch)")
            logger.info("="*70)
            
            # Auto-select first display
            if hasattr(launcher, 'list_displays') and launcher.list_displays:
                item = launcher.list_displays.item(0)
                if item:
                    item.setCheckState(Qt.CheckState.Checked)
                    logger.info("✅ Selected display 0")
            
            # Create spiral windows
            launcher._create_spiral_windows()
            
            if not launcher.spiral_windows:
                logger.error("❌ No spiral windows created")
                return
            
            logger.info(f"✅ Created {len(launcher.spiral_windows)} spiral window(s)")
            
            logger.info("\n" + "="*70)
            logger.info("STEP 4: Verify spiral settings")
            logger.info("="*70)
            
            # Get spiral director from first window
            win = launcher.spiral_windows[0]
            if not hasattr(win, 'comp') or not hasattr(win.comp, 'spiral_director'):
                logger.error("❌ Spiral director not found")
                return
            
            spiral = win.comp.spiral_director
            
            # Check settings from sinking.json:
            # "type": "logarithmic" (type 1)
            # "rotation_speed": 4.0
            # "opacity": 0.4
            # "reverse": true (should make speed negative)
            
            logger.info(f"  Spiral Type: {spiral.spiral_type} (expected: 1 for logarithmic)")
            logger.info(f"  Rotation Speed: {spiral.rotation_speed} (expected: -4.0 for reverse)")
            logger.info(f"  Opacity: {spiral.opacity} (expected: 0.4)")
            
            # Verify reverse
            if spiral.rotation_speed < 0:
                logger.info("✅ Reverse spiral active (negative rotation)")
            else:
                logger.error("❌ Reverse NOT active (expected negative rotation)")
                logger.error(f"   Got: {spiral.rotation_speed}, Expected: -4.0")
            
            # Verify opacity
            if abs(spiral.opacity - 0.4) < 0.01:
                logger.info("✅ Opacity correct")
            else:
                logger.error(f"❌ Opacity wrong: {spiral.opacity} (expected 0.4)")
            
            # Verify type
            if spiral.spiral_type == 1:
                logger.info("✅ Spiral type correct (logarithmic)")
            else:
                logger.error(f"❌ Spiral type wrong: {spiral.spiral_type} (expected 1)")
            
            logger.info("\n" + "="*70)
            logger.info("TEST COMPLETE")
            logger.info("="*70)
            logger.info("The spiral window should now be visible on screen.")
            logger.info("Manually verify:")
            logger.info("  • Spiral rotates COUNTERCLOCKWISE (reverse)")
            logger.info("  • Spiral is semi-transparent (40% opacity)")
            logger.info("  • Images cycle in the background")
            logger.info("")
            
        except Exception as e:
            logger.error(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Import Qt after creating app
    from PyQt6.QtCore import Qt
    
    # Run test after 3 seconds
    QTimer.singleShot(3000, run_enhanced_test)
    
    return app.exec()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
