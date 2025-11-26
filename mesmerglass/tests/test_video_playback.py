"""Test video playback in PlaybackEditor."""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)

def test_video_playback():
    """Test PlaybackEditor video mode."""
    logger.info("Starting video playback test")
    
    app = QApplication(sys.argv)
    
    # Import after QApplication created
    from mesmerglass.ui.editors.playback_editor import PlaybackEditor
    
    # Create editor
    editor = PlaybackEditor()
    editor.show()
    
    # Close the app once the editor window is gone
    editor.destroyed.connect(app.quit)

    # Wait 3 seconds for initialization
    def switch_to_videos():
        logger.info("Switching to Videos Only mode...")
        # Find media mode combo (index 2 = Videos Only)
        editor.media_mode_combo.setCurrentIndex(2)
        logger.info("Switched to Videos Only mode")
        # Reset modified flag so scripted close does not trigger save prompts
        editor.is_modified = False

        # Close after 10 seconds (gives renderer time to update)
        QTimer.singleShot(10000, safe_close)

    def safe_close():
        logger.info("Closing editor after video playback test...")
        editor.is_modified = False
        editor.close()
    
    QTimer.singleShot(3000, switch_to_videos)
    
    exit_code = app.exec()
    assert exit_code == 0, f"QApplication exited with code {exit_code}"

if __name__ == "__main__":
    test_video_playback()
