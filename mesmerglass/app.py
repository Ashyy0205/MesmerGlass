import sys
from PyQt6.QtWidgets import QApplication
from .ui.launcher import Launcher
from .qss import QSS
from . import __app_name__, __version__

def run():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = Launcher(f"{__app_name__} — {__version__}")
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run()

