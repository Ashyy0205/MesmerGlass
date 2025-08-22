"""MesmerGlass CLI and GUI launcher.

Adds structured logging flags and config to aid debugging and support.
"""

import sys, argparse, asyncio, logging, warnings
import faulthandler
from mesmerglass.app import run
from mesmerglass.engine.pulse import PulseEngine
from mesmerglass.engine.buttplug_server import ButtplugServer
from mesmerglass.logging_utils import setup_logging, get_default_log_path

# Monkey patch to suppress Bleak event loop closure errors
def patch_bleak_errors():
    """Patch asyncio to suppress event loop closure errors during shutdown."""
    try:
        import asyncio
        
        # Store the original call_soon_threadsafe method
        original_call_soon_threadsafe = asyncio.BaseEventLoop.call_soon_threadsafe
        
        def safe_call_soon_threadsafe(self, callback, *args, context=None):
            """Wrapper that catches and suppresses event loop closure errors."""
            try:
                return original_call_soon_threadsafe(self, callback, *args, context=context if context is not None else None)
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    # Silently ignore event loop closure errors during shutdown
                    return None
                else:
                    # Re-raise other runtime errors
                    raise
        
        # Replace the method
        asyncio.BaseEventLoop.call_soon_threadsafe = safe_call_soon_threadsafe
        
    except Exception:
        # If patching fails, just continue without it
        pass

# Apply the patch
patch_bleak_errors()

"""Legacy runner remains for convenience; virtual toy ops removed."""

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="MesmerGlass - CLI and GUI Interface")

    # Global logging options
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set log level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=str(get_default_log_path()),
        help="Path to log file (default: per-user MesmerGlass directory)",
    )
    parser.add_argument(
        "--log-format",
        choices=["plain", "json"],
        default="plain",
        help="Log format (plain or json-like)",
    )
    
    # Add command subparsers
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # GUI command (default)
    gui_parser = subparsers.add_parser("gui", help="Start the GUI (default)")
    
    # Test device command
    test_parser = subparsers.add_parser("test", help="Test device functionality")
    test_parser.add_argument("-i", "--intensity", type=float, default=0.5,
                           help="Test intensity (0.0-1.0)")
    test_parser.add_argument("-d", "--duration", type=int, default=1000,
                           help="Test duration in milliseconds")
    test_parser.add_argument("-p", "--port", type=int, default=12345,
                           help="Server port")
                           
    # Server command
    server_parser = subparsers.add_parser("server", help="Start a Buttplug server")
    server_parser.add_argument("-p", "--port", type=int, default=12345,
                            help="Server port")
    
    return parser.parse_args()

def run_server(port: int):
    """Run a Buttplug server in CLI mode."""
    server = ButtplugServer(port=port)
    logging.getLogger(__name__).info("Starting Buttplug server on port %s", port)
    server.start()
    try:
        while True:
            devices = server.get_device_list()
            if devices.devices:
                logging.getLogger(__name__).info("Connected devices:")
                for dev in devices.devices:
                    logging.getLogger(__name__).info(" - %s (index=%s)", dev.name, dev.index)
            input("Press Enter to refresh device list or Ctrl+C to quit...")
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down server...")
        server.stop()

if __name__ == "__main__":
    try:
        faulthandler.enable(all_threads=True)
    except Exception:
        pass
    args = parse_args()

    # Configure logging once per run
    setup_logging(
        level=args.log_level,
        log_file=args.log_file,
        json_format=(args.log_format == "json"),
        add_console=True,
    )

    if args.command == "server":
        run_server(args.port)
    else:  # gui or no command
        run()  # Start GUI
