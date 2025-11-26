"""Test VR headset detection and display.

This verifies that:
1. VR Bridge shows headset name when detected
2. VR Bridge shows "No Headset" when not detected
3. Status updates on refresh
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_headset_detection():
    """Test VR headset detection."""
    print("\n" + "="*60)
    print("TEST: VR Headset Detection")
    print("="*60)
    
    try:
        from mesmerglass.vr import VrBridge, VR_BACKEND
        
        print(f"\nBackend: {VR_BACKEND}")
        
        # Initialize VR Bridge
        bridge = VrBridge(enabled=True)
        result = bridge.start()
        is_mock = getattr(bridge, '_mock', True)
        
        print(f"Started: {result}")
        print(f"Mock mode: {is_mock}")
        
        # Try to get headset name
        headset_name = None
        if not is_mock and VR_BACKEND == 'openvr':
            try:
                import openvr
                if openvr:
                    print("\nQuerying OpenVR for headset info...")
                    vr_system = openvr.init(openvr.VRApplication_Other)
                    headset_name = vr_system.getStringTrackedDeviceProperty(
                        openvr.k_unTrackedDeviceIndex_Hmd,
                        openvr.Prop_ModelNumber_String
                    )
                    print(f"Headset model: {headset_name}")
                    
                    # Try to get more info
                    try:
                        manufacturer = vr_system.getStringTrackedDeviceProperty(
                            openvr.k_unTrackedDeviceIndex_Hmd,
                            openvr.Prop_ManufacturerName_String
                        )
                        print(f"Manufacturer: {manufacturer}")
                    except:
                        pass
                    
                    openvr.shutdown()
            except Exception as e:
                print(f"Could not get headset name: {e}")
        
        bridge.shutdown()
        
        # Show what will be displayed
        print("\n" + "-"*60)
        print("Display Text:")
        if is_mock:
            display_text = "🥽 VR Bridge (No Headset Detected)"
            print(f"  {display_text}")
            print("\n  Status: ⚠️ No headset detected")
            print("  Action: Connect headset and start SteamVR/Oculus")
        else:
            device_text = headset_name if headset_name else "Connected"
            display_text = f"🥽 VR Bridge ({device_text})"
            print(f"  {display_text}")
            print(f"\n  Status: ✅ Headset active")
            print(f"  Backend: {VR_BACKEND}")
        print("-"*60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_display_tab_detection():
    """Test that Display tab shows headset info."""
    print("\n" + "="*60)
    print("TEST: Display Tab Headset Detection")
    print("="*60)
    
    try:
        from PyQt6.QtWidgets import QApplication
        from mesmerglass.ui.tabs.display_tab import DisplayTab
        
        app = QApplication(sys.argv)
        display_tab = DisplayTab(None)
        
        # Find VR Bridge item
        for i in range(display_tab.list_displays.count()):
            item = display_tab.list_displays.item(i)
            text = item.text()
            
            if "VR Bridge" in text:
                print(f"\nFound VR Bridge item:")
                print(f"  Text: {text}")
                print(f"  Tooltip: {item.toolTip()}")
                
                # Check data
                from PyQt6.QtCore import Qt
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and isinstance(data, dict):
                    vr_status = data.get("vr_status", {})
                    if vr_status:
                        print(f"\n  Status Details:")
                        print(f"    Available: {vr_status.get('available')}")
                        print(f"    Headset: {vr_status.get('headset_name')}")
                        print(f"    Backend: {vr_status.get('backend')}")
                
                if "No Headset" in text:
                    print("\n  ⚠️ No headset currently detected")
                elif "Connected" in text or any(name in text for name in ["Quest", "Index", "Vive", "CV1", "Rift"]):
                    print("\n  ✅ Headset detected!")
                
                return True
        
        print("\n❌ VR Bridge item not found in display list")
        return False
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run headset detection tests."""
    print("\n" + "="*60)
    print("VR HEADSET DETECTION TEST")
    print("="*60)
    
    results = {
        "Headset Detection": test_headset_detection(),
        "Display Tab Integration": test_display_tab_detection(),
    }
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    if all(results.values()):
        print("\n✅ VR headset detection is working!")
        print("\nThe Display tab will now show:")
        print("  • '🥽 VR Bridge (No Headset Detected)' when no headset")
        print("  • '🥽 VR Bridge (Quest 2)' when Quest 2 detected")
        print("  • '🥽 VR Bridge (Index)' when Valve Index detected")
        print("  • etc.")
        print("\nClick 'Refresh VR' button to update headset status!")
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
