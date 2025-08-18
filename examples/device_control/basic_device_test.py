"""Test MesmerIntiface Implementation

This script demonstrates the new MesmerIntiface pure Python implementation
for real Bluetooth device control without requiring Rust dependencies.
"""

import sys
import os
import asyncio
import logging

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mesmerglass.engine.mesmerintiface import MesmerIntifaceServer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_mesmer_intiface():
    """Test the MesmerIntiface server implementation."""
    print("=== MesmerIntiface Test ===")
    print("Pure Python Bluetooth device control for MesmerGlass")
    print()
    
    # Create server
    server = MesmerIntifaceServer(port=12350)
    
    try:
        # Start server
        print("🚀 Starting MesmerIntiface server...")
        server.start()
        await asyncio.sleep(0.5)
        
        # Get initial status
        status = server.get_status()
        print("📊 Server Status:")
        for key, value in status.items():
            print(f"   {key}: {value}")
        print()
        
        # Start Bluetooth scanning
        print("🔍 Starting Bluetooth device scan...")
        scan_success = await server.start_real_scanning()
        
        if scan_success:
            print("✅ Bluetooth scanning started")
            print("⏱️  Scanning for devices (10 seconds)...")
            
            # Scan for devices
            await asyncio.sleep(10.0)
            
            # Check discovered devices
            status = server.get_status()
            print("\n📱 Scan Results:")
            print(f"   Discovered devices: {status['discovered_devices']}")
            print(f"   Device types found: {status['device_types']}")
            print(f"   Buttplug devices: {status['buttplug_devices']}")
            
            # List discovered devices
            device_list = server.get_device_list()
            if device_list.devices:
                print(f"\n🎯 Found {len(device_list.devices)} compatible device(s):")
                for device in device_list.devices:
                    print(f"   - {device.name} (index: {device.index})")
                    
                    # Show device capabilities
                    if "ScalarCmd" in device.device_messages:
                        vibrators = len(device.device_messages["ScalarCmd"])
                        print(f"     • {vibrators} vibrator(s)")
                    if "RotateCmd" in device.device_messages:
                        rotators = len(device.device_messages["RotateCmd"])
                        print(f"     • {rotators} rotator(s)")
                    
                    # Test connection (only to first device)
                    if device == device_list.devices[0]:
                        print(f"\n🔗 Testing connection to {device.name}...")
                        connected = await server.connect_real_device(device.index)
                        
                        if connected:
                            print("✅ Connected successfully!")
                            
                            # Test vibration command
                            print("📳 Testing vibration (50% for 3 seconds)...")
                            await server.send_real_device_command(
                                device.index, 
                                "vibrate", 
                                intensity=0.5
                            )
                            await asyncio.sleep(3.0)
                            
                            # Stop vibration
                            print("⏹️  Stopping vibration...")
                            await server.send_real_device_command(device.index, "stop")
                            
                            # Test rotation if supported
                            if "RotateCmd" in device.device_messages:
                                print("🔄 Testing rotation (50% for 2 seconds)...")
                                await server.send_real_device_command(
                                    device.index,
                                    "rotate",
                                    speed=0.5,
                                    clockwise=True
                                )
                                await asyncio.sleep(2.0)
                                await server.send_real_device_command(device.index, "stop")
                            
                            # Disconnect
                            print("🔌 Disconnecting...")
                            await server.disconnect_real_device(device.index)
                            print("✅ Disconnected")
                            
                        else:
                            print("❌ Failed to connect")
                            
            else:
                print("❌ No compatible devices found")
                print("\n💡 Tips:")
                print("   • Make sure your device is in pairing mode")
                print("   • Check that Bluetooth is enabled") 
                print("   • Verify device compatibility with supported brands:")
                print("     - Lovense (Lush, Max, Nora, Edge, Hush, Domi)")
                print("     - We-Vibe (Sync)")
                print("     - And other Buttplug-compatible devices")
            
            # Stop scanning
            print("\n🛑 Stopping device scan...")
            await server.stop_real_scanning()
            
        else:
            print("❌ Failed to start Bluetooth scanning")
            print("💡 This may be due to:")
            print("   • Missing bleak dependency (run: pip install bleak)")
            print("   • Bluetooth not available on this system")
            print("   • Insufficient permissions")
        
        print("\n✅ Test completed")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        await server.shutdown()
        print("✅ Cleanup complete")

async def test_device_database():
    """Test the device database functionality."""
    print("\n=== Device Database Test ===")
    
    from mesmerglass.engine.mesmerintiface import DeviceDatabase
    
    db = DeviceDatabase()
    
    print(f"📚 Loaded {len(db.get_all_devices())} device definitions")
    print(f"🏭 Supported manufacturers: {len(set(d.manufacturer for d in db.get_all_devices()))}")
    print(f"🔧 Supported protocols: {db.get_supported_protocols()}")
    
    # Test device identification
    print("\n🔍 Testing device identification:")
    
    test_cases = [
        ("LVS-Lush", []),
        ("LVS-Max", []),
        ("Sync", ["f000aa80-0451-4000-b000-000000000000"]),
        ("Unknown Device", [])
    ]
    
    for name, uuids in test_cases:
        device = db.identify_device(name, uuids)
        if device:
            print(f"   ✅ {name} → {device.name} ({device.protocol})")
        else:
            print(f"   ❌ {name} → Not recognized")

if __name__ == "__main__":
    print("MesmerIntiface - Pure Python Bluetooth Device Control")
    print("=" * 50)
    
    # Run tests
    asyncio.run(test_device_database())
    asyncio.run(test_mesmer_intiface())
