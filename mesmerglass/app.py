import sys, threading, traceback, signal, time, os
import asyncio
import qasync
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import qInstallMessageHandler
from .ui.main_application import MainApplication
from .qss import QSS
from . import __app_name__, __version__
from .logging_utils import setup_logging
import logging, faulthandler
from .platform_paths import ensure_windows_start_menu_shortcut

_DIAG_INSTALLED = False

def _install_diagnostics():
    global _DIAG_INSTALLED
    if _DIAG_INSTALLED:
        return
    # Allow disabling diagnostics entirely (useful for fragile VR runs)
    if os.environ.get("MESMERGLASS_NO_DIAG", "0") in ("1", "true", "True", "yes"):
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
    # Can be disabled via env or in VR mode by default
    _disable_watchdog = (
        os.environ.get("MESMERGLASS_NO_WATCHDOG", "0") in ("1", "true", "True", "yes")
        or os.environ.get("MESMERGLASS_VR", "0") in ("1",)
    )
    if _disable_watchdog:
        try:
            log.info("DIAG watchdog disabled (env VR or NO_WATCHDOG)")
        except Exception:
            pass
    else:
        def _watchdog():
            while True:
                try:
                    log.debug("DIAG heartbeat t=%s", int(time.time()))
                except Exception:
                    pass
                time.sleep(5)
        try:
            threading.Thread(target=_watchdog, daemon=True).start()
        except Exception:
            pass


def run():
    # Ensure logging is configured when launching GUI directly
    log_mode_env = os.environ.get("MESMERGLASS_LOG_MODE")
    debug_mode = os.environ.get("MESMERGLASS_DEBUG", "0") in ("1", "true", "True", "yes")
    log_level = "DEBUG" if debug_mode else "WARNING"
    if not logging.getLogger().handlers:
        setup_logging(level=log_level, add_console=True, log_mode=log_mode_env)
    _install_diagnostics()

    # First-run / install conveniences (safe no-ops outside frozen Windows builds)
    ensure_windows_start_menu_shortcut(app_name=__app_name__)
    
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Setup qasync event loop for async/await support with PyQt6
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # app.setStyleSheet(QSS)  # Temporarily disabled for easier testing
    win = MainApplication()
    try:
        app.aboutToQuit.connect(lambda: logging.getLogger("diag").info("DIAG aboutToQuit"))
    except Exception:
        pass
    win.show()
    
    # Run the event loop with qasync
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    run()

