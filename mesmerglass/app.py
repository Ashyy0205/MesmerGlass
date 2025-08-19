import sys
from PyQt6.QtWidgets import QApplication
from .ui.launcher import Launcher
from .qss import QSS
from . import __app_name__, __version__
from .logging_utils import setup_logging  # add logging setup


def run():
    # Ensure logging is configured when launching GUI directly
    setup_logging(add_console=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = Launcher(f"{__app_name__} — {__version__}")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

