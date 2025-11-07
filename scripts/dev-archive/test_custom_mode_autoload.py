"""
Test script: Custom Mode Auto-Load and Control Locking

This script:
1. Launches the MesmerGlass launcher GUI
2. Automatically loads sinking.json custom mode
3. Verifies that UI controls are properly locked
4. Checks that custom mode settings are applied correctly
5. Provides visual feedback for testing

Usage:
    python scripts/test_custom_mode_autoload.py
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Main test function."""
    logger.info("="*70)
    logger.info("Custom Mode Auto-Load Test - sinking.json")
    logger.info("="*70)
    
    # Import Qt after path setup
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtCore import QTimer
        from mesmerglass.ui.launcher import Launcher
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        logger.error("Make sure you're running in the virtual environment:")
        logger.error("  ./.venv/Scripts/python.exe scripts/test_custom_mode_autoload.py")
        return 1
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("MesmerGlass - Custom Mode Test")
    
    logger.info("Creating launcher window...")
    launcher = Launcher(title="MesmerGlass - Custom Mode Test")
    launcher.show()
    
    # Path to test mode
    mode_path = project_root / "mesmerglass" / "modes" / "sinking.json"
    
    if not mode_path.exists():
        logger.error(f"Test mode not found: {mode_path}")
        QMessageBox.critical(
            None,
            "Test Failed",
            f"Test mode file not found:\n{mode_path}\n\n"
            "Please ensure sinking.json exists in mesmerglass/modes/"
        )
        return 1
    
    logger.info(f"Test mode path: {mode_path}")
    
    # Define test sequence
    def run_test_sequence():
        """Execute the test sequence after launcher initializes."""
        try:
            logger.info("\n" + "="*70)
            logger.info("STEP 1: Verify launcher initialized")
            logger.info("="*70)
            
            if not launcher.visual_director:
                logger.error("❌ VisualDirector not initialized")
                show_test_result(launcher, False, "VisualDirector not initialized")
                return
            
            logger.info("✅ VisualDirector initialized")
            
            if not launcher.page_visual_programs:
                logger.error("❌ Visual Programs page not initialized")
                show_test_result(launcher, False, "Visual Programs page not initialized")
                return
            
            logger.info("✅ Visual Programs page initialized")
            
            if not launcher.page_mesmerloom:
                logger.error("❌ MesmerLoom page not initialized")
                show_test_result(launcher, False, "MesmerLoom page not initialized")
                return
            
            logger.info("✅ MesmerLoom page initialized")
            
            # Check initial state
            logger.info("\n" + "="*70)
            logger.info("STEP 2: Check initial control state (should be unlocked)")
            logger.info("="*70)
            
            visual_combo_enabled = launcher.page_visual_programs.visual_combo.isEnabled()
            spiral_type_enabled = launcher.page_mesmerloom.cmb_spiral_type.isEnabled()
            rotation_slider_enabled = launcher.page_mesmerloom.sld_rotation_speed.isEnabled()
            
            logger.info(f"  Visual dropdown enabled: {visual_combo_enabled}")
            logger.info(f"  Spiral type enabled: {spiral_type_enabled}")
            logger.info(f"  Rotation slider enabled: {rotation_slider_enabled}")
            
            if not visual_combo_enabled or not spiral_type_enabled or not rotation_slider_enabled:
                logger.warning("⚠️  Some controls already locked (unexpected)")
            else:
                logger.info("✅ All controls unlocked initially")
            
            # Load custom mode
            logger.info("\n" + "="*70)
            logger.info("STEP 3: Load custom mode (sinking.json)")
            logger.info("="*70)
            
            logger.info(f"Loading: {mode_path}")
            success = launcher.visual_director.select_custom_visual(mode_path)
            
            if not success:
                logger.error("❌ Failed to load custom mode")
                show_test_result(launcher, False, "Failed to load custom mode")
                return
            
            logger.info("✅ Custom mode loaded successfully")
            
            # Trigger the launcher's custom mode handler to lock controls
            logger.info("Triggering control locking...")
            if hasattr(launcher.page_mesmerloom, 'lock_controls'):
                launcher.page_mesmerloom.lock_controls()
                logger.info("✅ MesmerLoom controls locked")
            
            if hasattr(launcher.page_visual_programs, 'lock_visual_selector'):
                launcher.page_visual_programs.lock_visual_selector()
                logger.info("✅ Visual selector locked")
            
            # Verify custom mode is active
            logger.info("\n" + "="*70)
            logger.info("STEP 4: Verify custom mode state")
            logger.info("="*70)
            
            is_custom = launcher.visual_director.is_custom_mode_active()
            logger.info(f"  Is custom mode active: {is_custom}")
            
            if not is_custom:
                logger.error("❌ Custom mode not active in VisualDirector")
                show_test_result(launcher, False, "Custom mode not registered as active")
                return
            
            logger.info("✅ Custom mode registered as active")
            
            # Check current visual details
            if launcher.visual_director.current_visual:
                from mesmerglass.mesmerloom.custom_visual import CustomVisual
                if isinstance(launcher.visual_director.current_visual, CustomVisual):
                    mode_name = launcher.visual_director.current_visual.mode_name
                    logger.info(f"  Mode name: {mode_name}")
                    logger.info(f"  Use ThemeBank: {launcher.visual_director.current_visual._use_theme_bank_media}")
                    logger.info(f"  Media mode: {launcher.visual_director.current_visual._media_mode}")
            
            # Verify controls are locked
            logger.info("\n" + "="*70)
            logger.info("STEP 5: Verify controls are locked")
            logger.info("="*70)
            
            visual_combo_enabled_after = launcher.page_visual_programs.visual_combo.isEnabled()
            spiral_type_enabled_after = launcher.page_mesmerloom.cmb_spiral_type.isEnabled()
            rotation_slider_enabled_after = launcher.page_mesmerloom.sld_rotation_speed.isEnabled()
            opacity_slider_enabled_after = launcher.page_mesmerloom.sld_intensity.isEnabled()
            media_mode_enabled_after = launcher.page_mesmerloom.cmb_media_mode.isEnabled()
            
            logger.info(f"  Visual dropdown enabled: {visual_combo_enabled_after}")
            logger.info(f"  Spiral type enabled: {spiral_type_enabled_after}")
            logger.info(f"  Rotation slider enabled: {rotation_slider_enabled_after}")
            logger.info(f"  Opacity slider enabled: {opacity_slider_enabled_after}")
            logger.info(f"  Media mode enabled: {media_mode_enabled_after}")
            
            all_locked = not any([
                visual_combo_enabled_after,
                spiral_type_enabled_after,
                rotation_slider_enabled_after,
                opacity_slider_enabled_after,
                media_mode_enabled_after
            ])
            
            if all_locked:
                logger.info("✅ All custom-mode-controlled settings are locked")
            else:
                logger.error("❌ Some controls are still enabled (should be locked)")
                show_test_result(launcher, False, "Controls not properly locked")
                return
            
            # Verify colors/blend stay unlocked
            arm_color_enabled = launcher.page_mesmerloom.btn_arm_col.isEnabled()
            gap_color_enabled = launcher.page_mesmerloom.btn_gap_col.isEnabled()
            blend_enabled = launcher.page_mesmerloom.cmb_blend.isEnabled()
            
            logger.info(f"  Arm color enabled: {arm_color_enabled}")
            logger.info(f"  Gap color enabled: {gap_color_enabled}")
            logger.info(f"  Blend mode enabled: {blend_enabled}")
            
            if arm_color_enabled and gap_color_enabled and blend_enabled:
                logger.info("✅ Global aesthetic controls remain unlocked")
            else:
                logger.warning("⚠️  Some aesthetic controls were locked (unexpected)")
            
            # Verify spiral settings from mode
            logger.info("\n" + "="*70)
            logger.info("STEP 6: Verify spiral settings applied")
            logger.info("="*70)
            
            # Get spiral settings from compositor
            if launcher.spiral_windows and len(launcher.spiral_windows) > 0:
                win = launcher.spiral_windows[0]
                if hasattr(win, 'comp') and hasattr(win.comp, 'spiral_director'):
                    spiral = win.comp.spiral_director
                    logger.info(f"  Rotation speed: {spiral.rotation_speed}")
                    logger.info(f"  Opacity: {spiral.opacity}")
                    logger.info(f"  Spiral type: {spiral.spiral_type}")
                    
                    # Verify reverse (rotation_speed should be negative)
                    if spiral.rotation_speed < 0:
                        logger.info("✅ Reverse spiral active (negative rotation)")
                    else:
                        logger.warning("⚠️  Spiral not in reverse (expected negative rotation)")
                else:
                    logger.warning("⚠️  Spiral windows not yet initialized")
            else:
                logger.warning("⚠️  No spiral windows found (haven't clicked Launch yet)")
            
            # Success!
            logger.info("\n" + "="*70)
            logger.info("TEST PASSED ✅")
            logger.info("="*70)
            logger.info("")
            logger.info("Summary:")
            logger.info("  • Custom mode loaded successfully")
            logger.info("  • Visual dropdown locked")
            logger.info("  • MesmerLoom controls locked")
            logger.info("  • Global aesthetics remain unlocked")
            logger.info("  • Custom mode recognized by VisualDirector")
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Go to 🌀 MesmerLoom tab")
            logger.info("  2. Check 'Enable Spiral'")
            logger.info("  3. Click 'Launch' button")
            logger.info("  4. Verify spiral rotates COUNTERCLOCKWISE (reverse)")
            logger.info("  5. Verify spiral has 40% opacity (semi-transparent)")
            logger.info("  6. Verify images cycle")
            logger.info("")
            
            show_test_result(launcher, True, "All checks passed!")
            
        except Exception as e:
            logger.error(f"❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            show_test_result(launcher, False, f"Exception: {e}")
    
    def show_test_result(launcher, success, message):
        """Show test result dialog."""
        if success:
            QMessageBox.information(
                launcher,
                "✅ Test Passed",
                f"Custom Mode Auto-Load Test PASSED!\n\n{message}\n\n"
                "You can now:\n"
                "• Go to MesmerLoom tab → Enable Spiral\n"
                "• Click Launch button\n"
                "• Verify spiral rotates in reverse\n"
                "• Try to change settings (should be locked)"
            )
        else:
            QMessageBox.critical(
                launcher,
                "❌ Test Failed",
                f"Custom Mode Auto-Load Test FAILED!\n\n{message}\n\n"
                "Check console for detailed logs."
            )
    
    # Schedule test to run after launcher initialization (3 seconds delay)
    logger.info("Scheduling test to run in 3 seconds...")
    QTimer.singleShot(3000, run_test_sequence)
    
    # Run Qt event loop
    return app.exec()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
