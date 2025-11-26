"""Test the Phase 7 Display tab VR integration.

This script verifies:
1. Display tab renders monitor + VR sections
2. VR discovery results populate the list correctly
3. Environment flag hooks remain in the new entrypoint
"""
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesmerglass.ui.tabs.display_tab import DisplayTab


app = QApplication.instance() or QApplication(sys.argv)


class DummyDiscoveryService:
    """Minimal stub that mimics the discovery interface."""

    def __init__(self, clients=None):
        self.discovered_clients = clients or []


class DummyMainApp(QWidget):
    """Provide the properties DisplayTab expects from MainApplication."""

    def __init__(self, discovery_service=None):
        super().__init__()
        self.vr_discovery_service = discovery_service
        self.visual_director = None
        self.audio_engine = None
        self.compositor = None
        self.spiral_director = None
        self.text_director = None
        self.device_manager = None

    def mark_session_dirty(self):
        """DisplayTab calls this via BaseTab.mark_dirty; no-op for tests."""
        pass


def _create_display_tab(clients=None):
    discovery = DummyDiscoveryService(clients)
    main_app = DummyMainApp(discovery)
    tab = DisplayTab(main_app)
    return tab, discovery


def test_display_tab_has_vr_sections():
    """Ensure Display tab lists monitors + VR section headers."""
    print("\n" + "="*60)
    print("TEST: Display Tab Sections")
    print("="*60)
    
    try:
        display_tab, _ = _create_display_tab()
        texts = [display_tab.list_displays.item(i).text() for i in range(display_tab.list_displays.count())]
        has_monitor = any(text.startswith("🖥️") for text in texts)
        has_vr_label = any("VR Devices" in text for text in texts)
        
        if has_monitor:
            print("✅ Monitor entries found")
        else:
            print("❌ No monitor entries detected")
        
        if has_vr_label:
            print("✅ VR devices section present")
        else:
            print("❌ VR devices section missing")
        
        result = has_monitor and has_vr_label
        if result:
            print("\n✅ TEST PASSED: Display tab sections OK")
        else:
            print("\n❌ TEST FAILED: Display tab missing sections")
        return result
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_display_tab_refresh_with_clients():
    """Ensure VR discovery clients populate the list with checkable items."""
    print("\n" + "="*60)
    print("TEST: Display Tab VR Refresh")
    print("="*60)
    
    try:
        fake_clients = [
            {"name": "QA Headset", "ip": "10.0.0.42"},
            {"name": "Android Viewer", "ip": "10.0.0.99"},
        ]
        display_tab, discovery = _create_display_tab(fake_clients)
        discovery.discovered_clients = fake_clients
        display_tab._refresh_vr_displays()
        
        found_clients = []
        for i in range(display_tab.list_displays.count()):
            item = display_tab.list_displays.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict) and data.get("type") == "vr":
                found_clients.append(data.get("client", {}))
                print(f"✅ Found VR item: {item.text()}")
                print(f"   Data: {data}")
                print(f"   Checked: {item.checkState() == Qt.CheckState.Checked}")
        
        if len(found_clients) == len(fake_clients):
            print("\n✅ TEST PASSED: All discovered clients rendered")
            return True
        else:
            print("\n❌ TEST FAILED: Missing VR clients")
            return False
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """Test that MESMERGLASS_VR flag is still handled in the new entrypoint."""
    print("\n" + "="*60)
    print("TEST: Backward Compatibility (env var)")
    print("="*60)
    
    try:
        app_path = Path(__file__).parent.parent / "mesmerglass" / "app.py"
        app_code = app_path.read_text(encoding='utf-8', errors='ignore')
        
        if 'MESMERGLASS_VR' in app_code:
            print("✅ MESMERGLASS_VR guard still present in app entrypoint")
            print("\n✅ TEST PASSED: Environment flag support intact")
            return True
        else:
            print("❌ MESMERGLASS_VR guard missing from app entrypoint")
            print("\n❌ TEST FAILED")
            return False
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DISPLAY TAB VR INTEGRATION TEST SUITE")
    print("="*60)
    
    results = {
        "Display Tab Sections": test_display_tab_has_vr_sections(),
        "Display Tab VR Refresh": test_display_tab_refresh_with_clients(),
        "Backward Compatibility": test_backward_compatibility(),
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nDisplay tab wiring is ready:")
        print("  1. Launch MesmerGlass (python run.py)")
        print("  2. Open the Display tab")
        print("  3. Check a monitor + discovered VR client")
        print("  4. Launch session to mirror visuals")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
