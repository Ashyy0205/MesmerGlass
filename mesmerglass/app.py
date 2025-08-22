import sys, threading, traceback, signal, time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import qInstallMessageHandler
from .ui.launcher import Launcher
from .qss import QSS
from . import __app_name__, __version__
from .logging_utils import setup_logging  # add logging setup
import logging, faulthandler

_DIAG_INSTALLED = False

def _install_diagnostics():
    global _DIAG_INSTALLED
    if _DIAG_INSTALLED:
        return
    _DIAG_INSTALLED = True
    log = logging.getLogger("diag")
    # Faulthandler for native crash backtraces
    try:
        faulthandler.enable(all_threads=True)
        log.info("DIAG faulthandler enabled")
    except Exception:
        pass
    # Excepthooks
    def _excepthook(t, v, tb):
        log.error("UNCAUGHT %s: %s", t.__name__, v)
        for line in traceback.format_tb(tb):
            log.error(line.rstrip())
    sys.excepthook = _excepthook
    if hasattr(threading, 'excepthook'):
        def _thread_excepthook(args):
            log.error("THREAD EXC in %s: %s", getattr(args, 'thread', None), args.exc_value)
            for line in traceback.format_tb(args.exc_traceback):
                log.error(line.rstrip())
        threading.excepthook = _thread_excepthook  # type: ignore[attr-defined]
    # Qt message handler
    try:
        def _qt_msg_handler(mode, ctx, msg):  # type: ignore[unused-argument]
            try:
                log.error("QT: %s", msg)
            except Exception:
                pass
        qInstallMessageHandler(_qt_msg_handler)
        log.info("DIAG Qt message handler installed")
    except Exception:
        pass
    # Signal handlers for termination
    def _sig_handler(signum, frame):  # pragma: no cover
        log.warning("DIAG signal %s received", signum)
    for s in (signal.SIGINT, signal.SIGTERM):
        try: signal.signal(s, _sig_handler)
        except Exception: pass
    # Watchdog thread logging phases every 5s so we know if UI stalls
    def _watchdog():
        while True:
            log.debug("DIAG heartbeat t=%s", int(time.time()))
            time.sleep(5)
    try:
        threading.Thread(target=_watchdog, daemon=True).start()
    except Exception:
        pass


def run():
    # Ensure logging is configured when launching GUI directly
    setup_logging(add_console=True)
    _install_diagnostics()
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = Launcher(f"{__app_name__} — {__version__}")
    try:
        app.aboutToQuit.connect(lambda: logging.getLogger("diag").info("DIAG aboutToQuit"))
    except Exception:
        pass
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

