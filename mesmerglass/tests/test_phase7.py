"""Quick test launcher for Phase 7 Main Application."""
import sys
import logging
from PyQt6.QtWidgets import QApplication
from mesmerglass.ui.main_application import MainApplication
from mesmerglass.logging_utils import setup_logging

if __name__ == "__main__":
    setup_logging(level="INFO")
    logger = logging.getLogger(__name__)
    logger.info("Starting Phase 7 MainApplication test")
    
    app = QApplication(sys.argv)
    window = MainApplication()
    window.show()
    
    sys.exit(app.exec())
