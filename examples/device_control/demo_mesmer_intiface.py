"""MesmerIntiface Demo

This script demonstrates the completed MesmerIntiface pure Python implementation
that replaces the need for external Intiface Central dependency.
"""

import sys
import os
import asyncio
import time

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mesmerglass.engine.mesmerintiface import MesmerIntifaceServer

async def demo_mesmer_intiface():
    """Demonstrate MesmerIntiface capabilities."""
    
    print("🌟 MesmerIntiface - Pure Python Bluetooth Device Control")
    print("=" * 55)
    print()
    print("✨ Features:")
    print("   • No external dependencies (no Rust, no Intiface Central)")
    print("   • Full Buttplug v3 protocol compatibility")
    print("   • Direct Bluetooth LE device communication")
    print("   • Lovense & We-Vibe protocol support")
    print("   • Seamless MesmerGlass integration")
    print()
    
    # Create and start server
    print("🚀 Starting MesmerIntiface server...")
    server = MesmerIntifaceServer(port=12350)
    server.start()
    
    await asyncio.sleep(0.5)
    
    try:
        # Show server status
        status = server.get_status()
        print("📊 Server Status:")
        for key, value in status.items():
            print(f"   {key}: {value}")
        print()
        
        # Demonstrate device database
        print("📚 Device Database:")
        from mesmerglass.engine.mesmerintiface.device_database import DeviceDatabase
        db = DeviceDatabase()
        devices = db.get_all_devices()
        manufacturers = set(d.manufacturer for d in devices)
        protocols = db.get_supported_protocols()
        
        print(f"   Supported devices: {len(devices)}")
        print(f"   Manufacturers: {', '.join(sorted(manufacturers))}")
        print(f"   Protocols: {', '.join(protocols)}")
        print()
        
        # Show example device definitions
        print("🎯 Example Device Definitions:")
        examples = [
            ("Lovense Lush", "lovense"),
            ("Lovense Max", "lovense"), 
            ("We-Vibe Sync", "we-vibe")
        ]
        
        for device_name, protocol in examples:
            device = next((d for d in devices if device_name.lower() in d.name.lower()), None)
            if device:
                capabilities = []
                if device.capabilities.get("vibrate", 0) > 0:
                    capabilities.append(f"{device.capabilities['vibrate']} vibrator(s)")
                if device.capabilities.get("rotate", 0) > 0:
                    capabilities.append(f"{device.capabilities['rotate']} rotator(s)")
                print(f"   • {device.name}: {', '.join(capabilities) if capabilities else 'Unknown capabilities'}")
        print()
        
        # Demonstrate virtual device simulation  
        print("🤖 Virtual Device Simulation:")
        print("   (For testing without real hardware)")
        
        # Add virtual devices to demonstrate protocol
        virtual_devices = [
            {
                "name": "Virtual Lovense Lush",
                "address": "AA:BB:CC:DD:EE:F1",
                "protocol": "lovense",
                "capabilities": {"vibrators": 1}
            },
            {
                "name": "Virtual We-Vibe Sync", 
                "address": "AA:BB:CC:DD:EE:F2",
                "protocol": "we-vibe",
                "capabilities": {"vibrators": 2}
            }
        ]
        
        for i, vdev in enumerate(virtual_devices):
            device_info = {
                "DeviceIndex": i + 1,
                "DeviceName": vdev["name"],
                "DeviceMessages": {}
            }
            
            # Add appropriate message types based on capabilities
            if "vibrators" in vdev["capabilities"]:
                vibrator_count = vdev["capabilities"]["vibrators"]
                device_info["DeviceMessages"]["ScalarCmd"] = [
                    {
                        "Index": j,
                        "ActuatorType": "Vibrate",
                        "Features": [{"StepCount": 20}]
                    }
                    for j in range(vibrator_count)
                ]
                
            # Simulate device addition
            server._add_virtual_device(device_info)
            print(f"   + Added {vdev['name']} ({vdev['protocol']} protocol)")
        
        print()
        
        # Get updated device list
        device_list = server.get_device_list()
        print(f"📱 Available Devices: {len(device_list.devices)}")
        for device in device_list.devices:
            print(f"   • {device.name} (index: {device.index})")
            if "ScalarCmd" in device.device_messages:
                vibrators = len(device.device_messages["ScalarCmd"])
                print(f"     - {vibrators} vibrator(s) available")
        print()
        
        # Demonstrate device commands
        if device_list.devices:
            test_device = device_list.devices[0]
            print(f"🎮 Testing Device Commands on {test_device.name}:")
            
            print("   • Testing vibration patterns...")
            patterns = [
                (0.3, 1000, "Gentle"),
                (0.6, 800, "Medium"), 
                (0.9, 600, "Strong"),
                (0.0, 500, "Stop")
            ]
            
            for intensity, duration_ms, description in patterns:
                print(f"     - {description}: {int(intensity*100)}% for {duration_ms}ms")
                await server.send_real_device_command(
                    test_device.index,
                    "vibrate", 
                    intensity=intensity
                )
                await asyncio.sleep(duration_ms / 1000.0)
            
            print("   ✅ Command test completed")
        
        print()
        print("🌟 MesmerIntiface Integration Benefits:")
        print("   ✅ Pure Python implementation")
        print("   ✅ No external app dependencies") 
        print("   ✅ Direct Bluetooth control")
        print("   ✅ Cross-platform compatibility")
        print("   ✅ Extensible device protocol system")
        print("   ✅ Full MesmerGlass integration")
        print()
        
    except Exception as e:
        print(f"❌ Demo error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("🧹 Shutting down server...")
        await server.shutdown()
        print("✅ Demo completed")

def main():
    """Run the MesmerIntiface demo."""
    print("Starting MesmerIntiface Demo...")
    print()
    
    try:
        asyncio.run(demo_mesmer_intiface())
    except KeyboardInterrupt:
        print("\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")

if __name__ == "__main__":
    main()
