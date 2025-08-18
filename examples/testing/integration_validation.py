"""Integration Test for MesmerGlass with MesmerIntiface

This test validates the complete integration of MesmerIntiface
into the MesmerGlass application stack.
"""

import sys
import os
import asyncio
import threading
import time

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def test_pulse_engine_integration():
    """Test PulseEngine with MesmerIntiface."""
    print("=== PulseEngine Integration Test ===")
    
    from mesmerglass.engine.pulse import PulseEngine
    from mesmerglass.engine.mesmerintiface import MesmerIntifaceServer
    
    # Create MesmerIntiface server
    print("🚀 Starting MesmerIntiface server...")
    server = MesmerIntifaceServer(port=12350)
    server.start()
    
    # Wait for server to start
    time.sleep(1.0)
    
    try:
        # Create PulseEngine with MesmerIntiface
        print("🔧 Creating PulseEngine with MesmerIntiface...")
        pulse = PulseEngine(use_mesmer=True, quiet=False)
        
        # Start pulse engine
        print("▶️  Starting PulseEngine...")
        pulse.start()
        
        # Wait for connection
        time.sleep(1.0)
        
        # Test basic commands
        print("📳 Testing pulse commands...")
        pulse.set_level(0.3)
        time.sleep(0.5)
        
        pulse.pulse(0.7, 500)
        time.sleep(0.5)
        
        pulse.set_level(0.0)
        time.sleep(0.2)
        
        print("✅ PulseEngine integration test completed")
        
        # Stop pulse engine
        print("⏹️  Stopping PulseEngine...")
        pulse.stop()
        
    except Exception as e:
        print(f"❌ PulseEngine integration test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup server
        print("🧹 Cleaning up server...")
        asyncio.run(server.shutdown())

def test_device_manager():
    """Test device manager integration."""
    print("\n=== Device Manager Test ===")
    
    from mesmerglass.engine.device_manager import DeviceManager, Device
    
    manager = DeviceManager()
    
    # Test adding devices
    manager.add_device({
        "DeviceIndex": 1,
        "DeviceName": "Test Vibrator",
        "DeviceMessages": {
            "ScalarCmd": [{"ActuatorType": "Vibrate", "Features": [{"StepCount": 20}]}]
        }
    })
    
    manager.add_device({
        "DeviceIndex": 2, 
        "DeviceName": "Test Rotator",
        "DeviceMessages": {
            "RotateCmd": [{"Features": [{"StepCount": 20}]}]
        }
    })
    
    # Test device list
    device_list = manager.get_device_list()
    print(f"📱 Found {len(device_list.devices)} devices:")
    for device in device_list.devices:
        print(f"   - {device.name} (index: {device.index})")
    
    # Test device selection
    print("🎯 Testing device selection...")
    success = manager.select_device(1)
    print(f"   Selection result: {success}")
    print(f"   Selected index: {manager.get_selected_index()}")
    
    # Test device removal
    print("🗑️  Testing device removal...")
    manager.remove_device(2)
    device_list = manager.get_device_list()
    print(f"   Devices after removal: {len(device_list.devices)}")
    
    print("✅ Device manager test completed")

def test_module_imports():
    """Test that all modules import correctly."""
    print("\n=== Module Import Test ===")
    
    modules = [
        "mesmerglass.engine.mesmerintiface",
        "mesmerglass.engine.mesmerintiface.bluetooth_scanner",
        "mesmerglass.engine.mesmerintiface.device_protocols", 
        "mesmerglass.engine.mesmerintiface.device_database",
        "mesmerglass.engine.mesmerintiface.mesmer_server",
        "mesmerglass.engine.pulse",
        "mesmerglass.engine.device_manager"
    ]
    
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except Exception as e:
            print(f"❌ {module}: {e}")
    
    print("✅ Module import test completed")

if __name__ == "__main__":
    print("MesmerGlass + MesmerIntiface Integration Test")
    print("=" * 50)
    
    try:
        test_module_imports()
        test_device_manager() 
        test_pulse_engine_integration()
        
        print("\n🎉 All integration tests completed!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
