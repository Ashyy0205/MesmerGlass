"""VR Diagnostic Tool - Check VR system status in real-time.

This script provides live diagnostics for both VR systems:
- VR Bridge (Direct headset via OpenXR/OpenVR)
- VR Streaming (Wireless discovery)

Usage:
    python scripts/vr_diagnostic.py
"""
import sys
import os
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_vr_bridge_status():
    """Check VR Bridge status."""
    print_header("VR BRIDGE STATUS (Direct Headset Rendering)")
    
    # Check environment variables
    vr_enabled = os.environ.get('MESMERGLASS_VR', 'not set')
    vr_backend = os.environ.get('MESMERGLASS_VR_BACKEND', 'not set (auto)')
    vr_mock = os.environ.get('MESMERGLASS_VR_MOCK', 'not set')
    
    print(f"  Environment Variables:")
    print(f"    MESMERGLASS_VR: {vr_enabled}")
    print(f"    MESMERGLASS_VR_BACKEND: {vr_backend}")
    print(f"    MESMERGLASS_VR_MOCK: {vr_mock}")
    print()
    
    # Try to initialize VR Bridge
    try:
        from mesmerglass.vr import VrBridge, VR_BACKEND
        print(f"  ✅ VrBridge import successful")
        print(f"  Backend: {VR_BACKEND}")
        
        # Try to create and start
        bridge = VrBridge(enabled=True)
        result = bridge.start()
        is_mock = getattr(bridge, '_mock', False)
        
        print(f"  Start result: {result}")
        print(f"  Mock mode: {is_mock}")
        
        if is_mock:
            print()
            print("  ⚠️  VR Bridge is in MOCK MODE")
            print("     This means no headset was detected.")
            print()
            print("  To use direct VR headset rendering:")
            print("     1. Connect your PC VR headset (Oculus, Vive, Index, WMR)")
            print("     2. Start SteamVR or Oculus software")
            print("     3. Set: $env:MESMERGLASS_VR = '1'")
            print("     4. Launch MesmerGlass")
        else:
            print()
            print("  ✅ VR BRIDGE IS ACTIVE!")
            print("     Headset detected and ready for rendering.")
            
        bridge.shutdown()
        
    except Exception as e:
        print(f"  ❌ VR Bridge error: {e}")
        import traceback
        traceback.print_exc()


def check_vr_streaming_status():
    """Check VR Streaming status."""
    print_header("VR STREAMING STATUS (Wireless Headsets)")
    
    print("  Starting discovery service...")
    
    try:
        from mesmerglass.mesmervisor.streaming_server import DiscoveryService
        
        discovery = DiscoveryService(discovery_port=5556, streaming_port=5555)
        discovery.start()
        
        print("  ✅ Discovery service started on port 5556")
        print("  📡 Listening for VR headset broadcasts...")
        print()
        print("  Scanning for 10 seconds...")
        
        # Scan for 10 seconds
        for i in range(10):
            time.sleep(1)
            clients = getattr(discovery, 'discovered_clients', [])
            if clients:
                print(f"\r  Found {len(clients)} device(s)... ", end='', flush=True)
            else:
                print(f"\r  Scanning... {10-i}s remaining ", end='', flush=True)
        
        print()
        print()
        
        # Check results
        clients = getattr(discovery, 'discovered_clients', [])
        
        if clients:
            print(f"  ✅ FOUND {len(clients)} VR DEVICE(S):")
            print()
            for idx, client in enumerate(clients, 1):
                name = client.get('name', 'Unknown')
                ip = client.get('ip', '0.0.0.0')
                port = client.get('port', 0)
                print(f"    {idx}. {name}")
                print(f"       IP: {ip}")
                print(f"       Port: {port}")
                print()
            
            print("  These devices will appear in the Display tab under 'VR Devices (Wireless)'")
            print("  Check them in the list and launch spiral windows to stream.")
        else:
            print("  ⚠️  NO VR DEVICES FOUND")
            print()
            print("  Wireless VR requires:")
            print("     1. Android VR client app running on your headset")
            print("     2. Headset on the same WiFi network")
            print("     3. Client app broadcasting 'VR_HEADSET_HELLO' packets")
            print("     4. Port 5556 not blocked by firewall")
        
        discovery.stop()
        
    except Exception as e:
        print(f"  ❌ Discovery service error: {e}")
        import traceback
        traceback.print_exc()


def check_display_integration():
    """Check how VR integrates with display system."""
    print_header("DISPLAY INTEGRATION")
    
    print("  VR systems integrate with displays differently:")
    print()
    print("  📱 VR Streaming (Wireless):")
    print("     • DOES appear in Display tab")
    print("     • Listed under 'VR Devices (Wireless)'")
    print("     • Check the device to enable streaming")
    print("     • Auto-refreshes every 2 seconds")
    print()
    print("  🥽 VR Bridge (Direct Headset):")
    print("     • DOES NOT appear in Display tab")
    print("     • Enabled via environment variable: MESMERGLASS_VR=1")
    print("     • Auto-connects when spiral windows launch")
    print("     • Works alongside desktop displays")
    print()
    print("  You can use BOTH systems simultaneously:")
    print("     • Desktop display shows spiral")
    print("     • Direct VR headset receives frames")
    print("     • Wireless Android clients receive stream")


def show_quick_start():
    """Show quick start instructions."""
    print_header("QUICK START GUIDE")
    
    print()
    print("  🥽 To use DIRECT VR HEADSET (PC VR):")
    print()
    print("     # PowerShell commands:")
    print("     $env:MESMERGLASS_VR = '1'")
    print("     $env:MESMERGLASS_VR_BACKEND = 'openvr'  # or 'openxr'")
    print("     .\\.venv\\Scripts\\python.exe -m mesmerglass")
    print()
    print("     # Then in MesmerGlass:")
    print("     1. Go to Display tab")
    print("     2. Select your primary monitor")
    print("     3. Click 'Launch' button")
    print("     4. Spiral appears on monitor AND in headset")
    print()
    print()
    print("  📱 To use WIRELESS VR HEADSET (Android):")
    print()
    print("     # PowerShell commands:")
    print("     .\\.venv\\Scripts\\python.exe -m mesmerglass")
    print()
    print("     # Then in MesmerGlass:")
    print("     1. Open Android VR client app on headset")
    print("     2. Go to Display tab in MesmerGlass")
    print("     3. Wait for device to appear under 'VR Devices (Wireless)'")
    print("     4. Check the device in the list")
    print("     5. Click 'Launch' button")
    print("     6. Frames stream to headset over WiFi")
    print()


def main():
    """Run VR diagnostics."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  MESMERGLASS VR DIAGNOSTIC TOOL".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    
    check_vr_bridge_status()
    check_vr_streaming_status()
    check_display_integration()
    show_quick_start()
    
    print()
    print("=" * 70)
    print("  Diagnostic complete!")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
