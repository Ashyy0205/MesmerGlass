"""MesmerGlass CLI and GUI launcher."""

import sys
import argparse
import asyncio
from typing import Optional
from mesmerglass.app import run
from mesmerglass.engine.pulse import PulseEngine
from mesmerglass.engine.buttplug_server import ButtplugServer
from mesmerglass.tests.virtual_toy import VirtualToy

async def cli_test_device(intensity: float = 0.5, duration_ms: int = 1000, server_port: int = 12345):
    """Test a device with specific intensity."""
    print(f"[cli] Starting device test (intensity={intensity}, duration={duration_ms}ms)")
    
    # Start server
    server = ButtplugServer(port=server_port)
    server.start()
    print("[cli] Server started")
    
    # Create and connect virtual toy
    toy = VirtualToy(name="CLI Test Toy", port=server_port)
    connected = await toy.connect()
    if not connected:
        print("[cli] Failed to connect virtual toy")
        server.stop()
        return
    print("[cli] Virtual toy connected")
    
    # Start pulse engine
    engine = PulseEngine()
    engine.start()  # This runs in its own thread
    print("[cli] Pulse engine started")
    
    # Allow time for engine to connect
    await asyncio.sleep(1.0)
    
    # Send test pulse
    print(f"[cli] Sending pulse: {intensity*100}% for {duration_ms}ms")
    engine.pulse(intensity, duration_ms)
    
    # Wait for pulse to complete
    await asyncio.sleep(duration_ms/1000.0 + 0.1)
    
    # Cleanup
    await toy.disconnect()
    server.stop()
    engine.stop()
    await asyncio.sleep(0.5)  # Allow time for cleanup
    print("[cli] Test complete")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="MesmerGlass - CLI and GUI Interface")
    
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
                           
    # Virtual toy command
    toy_parser = subparsers.add_parser("toy", help="Start a virtual toy")
    toy_parser.add_argument("-n", "--name", type=str, default="CLI Virtual Toy",
                          help="Toy name")
    toy_parser.add_argument("-p", "--port", type=int, default=12345,
                          help="Server port")
                          
    # Server command
    server_parser = subparsers.add_parser("server", help="Start a Buttplug server")
    server_parser.add_argument("-p", "--port", type=int, default=12345,
                            help="Server port")
    
    return parser.parse_args()

async def run_virtual_toy(name: str, port: int):
    """Run a virtual toy in CLI mode."""
    toy = VirtualToy(name=name, port=port)
    print(f"[cli] Starting virtual toy: {name} on port {port}")
    connected = await toy.connect()
    if not connected:
        print("[cli] Failed to connect toy")
        return
    print("[cli] Virtual toy connected and running")
    try:
        while True:
            await asyncio.sleep(1)
            level = toy.state.level
            if level > 0:
                print(f"[cli] Toy level: {int(level*100)}%")
    except KeyboardInterrupt:
        print("\n[cli] Shutting down toy...")
        await toy.disconnect()

def run_server(port: int):
    """Run a Buttplug server in CLI mode."""
    server = ButtplugServer(port=port)
    print(f"[cli] Starting Buttplug server on port {port}")
    server.start()
    try:
        while True:
            devices = server.get_device_list()
            if devices.devices:
                print("\n[cli] Connected devices:")
                for dev in devices.devices:
                    print(f"- {dev.name} (index: {dev.index})")
            input("Press Enter to refresh device list or Ctrl+C to quit...")
    except KeyboardInterrupt:
        print("\n[cli] Shutting down server...")
        server.stop()

if __name__ == "__main__":
    args = parse_args()
    
    if args.command == "test":
        asyncio.run(cli_test_device(args.intensity, args.duration, args.port))
    elif args.command == "toy":
        asyncio.run(run_virtual_toy(args.name, args.port))
    elif args.command == "server":
        run_server(args.port)
    else:  # gui or no command
        run()  # Start GUI
