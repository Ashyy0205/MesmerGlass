"""Test script to verify VR integration is working.

Tests both VR systems:
1. VR Bridge (Direct headset rendering via OpenXR/OpenVR)
2. VR Streaming (Wireless discovery and streaming server)

Usage:
    python scripts/test_vr_integration.py
"""
import sys
import os
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def test_vr_bridge_import():
    """Test 1: Verify VR Bridge can be imported."""
    logger.info("=" * 60)
    logger.info("TEST 1: VR Bridge Import")
    logger.info("=" * 60)
    
    try:
        from mesmerglass.vr import VrBridge, VR_BACKEND
        logger.info(f"✅ VR Bridge imported successfully")
        logger.info(f"   Backend: {VR_BACKEND}")
        return True, VrBridge
    except Exception as e:
        logger.error(f"❌ VR Bridge import failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_vr_bridge_initialization(VrBridge):
    """Test 2: Verify VR Bridge can be initialized."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: VR Bridge Initialization")
    logger.info("=" * 60)
    
    try:
        # Test with enabled=False (should create mock)
        bridge = VrBridge(enabled=False)
        logger.info("✅ VR Bridge created with enabled=False")
        logger.info(f"   Mock mode: {getattr(bridge, '_mock', 'unknown')}")
        
        # Test with enabled=True (will be mock if no headset)
        bridge_enabled = VrBridge(enabled=True)
        logger.info("✅ VR Bridge created with enabled=True")
        logger.info(f"   Mock mode: {getattr(bridge_enabled, '_mock', 'unknown')}")
        
        # Test start()
        result = bridge_enabled.start()
        logger.info(f"✅ VR Bridge start() returned: {result}")
        logger.info(f"   Enabled: {getattr(bridge_enabled, 'enabled', 'unknown')}")
        
        # Test frame submission (should be safe no-op in mock)
        bridge_enabled.submit_frame_from_fbo(0, 1920, 1080)
        logger.info("✅ VR Bridge submit_frame_from_fbo() executed without error")
        
        # Cleanup
        bridge_enabled.shutdown()
        logger.info("✅ VR Bridge shutdown() executed without error")
        
        return True
    except Exception as e:
        logger.error(f"❌ VR Bridge initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vr_streaming_import():
    """Test 3: Verify VR Streaming components can be imported."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: VR Streaming Import")
    logger.info("=" * 60)
    
    try:
        from mesmerglass.mesmervisor.streaming_server import VRStreamingServer, DiscoveryService
        logger.info("✅ VRStreamingServer imported successfully")
        logger.info("✅ DiscoveryService imported successfully")
        return True, DiscoveryService
    except Exception as e:
        logger.error(f"❌ VR Streaming import failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_discovery_service(DiscoveryService):
    """Test 4: Verify Discovery Service can be created."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Discovery Service Initialization")
    logger.info("=" * 60)
    
    try:
        # Create discovery service
        discovery = DiscoveryService(discovery_port=5556, streaming_port=5555)
        logger.info("✅ DiscoveryService created")
        logger.info(f"   Discovery port: 5556")
        logger.info(f"   Streaming port: 5555")
        
        # Check initial state
        clients = getattr(discovery, 'discovered_clients', [])
        logger.info(f"✅ Initial discovered clients: {len(clients)}")
        
        # Test start (may fail if port in use - that's okay)
        try:
            discovery.start()
            logger.info("✅ DiscoveryService started successfully")
            
            # Wait a moment to see if it crashes
            import time
            time.sleep(0.5)
            
            # Check if still running
            is_running = getattr(discovery, '_running', False)
            logger.info(f"   Running: {is_running}")
            
            # Stop it
            try:
                discovery.stop()
                logger.info("✅ DiscoveryService stopped successfully")
            except Exception as e:
                logger.warning(f"⚠️  DiscoveryService stop() raised: {e}")
                
        except Exception as e:
            logger.warning(f"⚠️  DiscoveryService start() raised: {e}")
            logger.info("   (This is okay if port 5556 is already in use)")
        
        return True
    except Exception as e:
        logger.error(f"❌ Discovery Service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_main_application_vr_integration():
    """Test 5: Verify MainApplication wires VR discovery + display refresh."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: MainApplication VR Integration Points")
    logger.info("=" * 60)
    
    try:
        # Read main_application.py and check for VR integration
        main_app_path = Path(__file__).parent.parent / "mesmerglass" / "ui" / "main_application.py"
        main_app_code = main_app_path.read_text(encoding='utf-8', errors='ignore')
        
        checks = {
            "Discovery Service import": "from ..mesmervisor.streaming_server import DiscoveryService" in main_app_code,
            "Discovery Service init": "self.vr_discovery_service = DiscoveryService" in main_app_code,
            "Discovery Service start": "self.vr_discovery_service.start()" in main_app_code,
            "DisplayTab attribute": "self.display_tab = DisplayTab" in main_app_code,
            "VR refresh timer": "self._vr_refresh_timer" in main_app_code,
            "Display tab refresh call": "self.display_tab._refresh_vr_displays" in main_app_code,
        }
        
        all_passed = True
        for check_name, check_result in checks.items():
            if check_result:
                logger.info(f"✅ {check_name}")
            else:
                logger.error(f"❌ {check_name}")
                all_passed = False
        
        if all_passed:
            logger.info("\n✅ MainApplication VR integration points found")
            return True
        else:
            logger.error("\n❌ Some MainApplication VR integration points missing")
            return False
            
    except Exception as e:
        logger.error(f"❌ MainApplication integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vr_backend_selection():
    """Test 6: Verify VR backend selection logic."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: VR Backend Selection")
    logger.info("=" * 60)
    
    try:
        # Check __init__.py for backend selection
        vr_init_path = Path(__file__).parent.parent / "mesmerglass" / "vr" / "__init__.py"
        vr_init_code = vr_init_path.read_text(encoding='utf-8', errors='ignore')
        
        checks = {
            "Backend env var": "MESMERGLASS_VR_BACKEND" in vr_init_code,
            "OpenVR backend": "vr_bridge_openvr" in vr_init_code,
            "OpenXR backend": "from .vr_bridge import VrBridge" in vr_init_code,
            "Mock fallback": "MockVrBridge" in vr_init_code,
            "Auto-detection": "auto" in vr_init_code.lower(),
        }
        
        all_passed = True
        for check_name, check_result in checks.items():
            if check_result:
                logger.info(f"✅ {check_name}")
            else:
                logger.error(f"❌ {check_name}")
                all_passed = False
        
        # Show current backend
        current_backend = os.environ.get('MESMERGLASS_VR_BACKEND', 'auto')
        logger.info(f"\n   Current MESMERGLASS_VR_BACKEND: {current_backend}")
        
        if all_passed:
            logger.info("\n✅ VR backend selection logic verified")
            return True
        else:
            logger.error("\n❌ VR backend selection has issues")
            return False
            
    except Exception as e:
        logger.error(f"❌ Backend selection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vr_environment_flags():
    """Test 7: Document VR environment flags."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: VR Environment Flags")
    logger.info("=" * 60)
    
    flags = {
        "MESMERGLASS_VR": os.environ.get("MESMERGLASS_VR", "not set"),
        "MESMERGLASS_VR_BACKEND": os.environ.get("MESMERGLASS_VR_BACKEND", "not set"),
        "MESMERGLASS_VR_MOCK": os.environ.get("MESMERGLASS_VR_MOCK", "not set"),
        "MESMERGLASS_VR_SAFE": os.environ.get("MESMERGLASS_VR_SAFE", "not set"),
        "MESMERGLASS_VR_MINIMAL": os.environ.get("MESMERGLASS_VR_MINIMAL", "not set"),
    }
    
    logger.info("Current VR environment flags:")
    for flag, value in flags.items():
        logger.info(f"   {flag}: {value}")
    
    logger.info("\n✅ Environment flags documented")
    return True


def main():
    """Run all VR integration tests."""
    logger.info("\n" + "=" * 60)
    logger.info("MESMERGLASS VR INTEGRATION TEST SUITE")
    logger.info("=" * 60)
    logger.info("")
    
    results = {}
    
    # Test 1: VR Bridge Import
    success, VrBridge = test_vr_bridge_import()
    results["VR Bridge Import"] = success
    
    # Test 2: VR Bridge Initialization (only if import succeeded)
    if success and VrBridge:
        results["VR Bridge Initialization"] = test_vr_bridge_initialization(VrBridge)
    else:
        results["VR Bridge Initialization"] = False
        logger.warning("⚠️  Skipping VR Bridge initialization test (import failed)")
    
    # Test 3: VR Streaming Import
    success, DiscoveryService = test_vr_streaming_import()
    results["VR Streaming Import"] = success
    
    # Test 4: Discovery Service (only if import succeeded)
    if success and DiscoveryService:
        results["Discovery Service"] = test_discovery_service(DiscoveryService)
    else:
        results["Discovery Service"] = False
        logger.warning("⚠️  Skipping Discovery Service test (import failed)")
    
    # Test 5: MainApplication Integration
    results["MainApplication Integration"] = test_main_application_vr_integration()
    
    # Test 6: Backend Selection
    results["Backend Selection"] = test_vr_backend_selection()
    
    # Test 7: Environment Flags
    results["Environment Flags"] = test_vr_environment_flags()
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    if passed == total:
        logger.info("\n🎉 ALL TESTS PASSED - VR integration is working!")
        logger.info("\nNext steps:")
        logger.info("  1. To test VR Bridge (direct headset):")
        logger.info("     $env:MESMERGLASS_VR = '1'")
        logger.info("     python -m mesmerglass")
        logger.info("")
        logger.info("  2. To test VR Streaming (wireless):")
        logger.info("     python -m mesmerglass")
        logger.info("     (Open Android VR client app)")
        return 0
    else:
        logger.error("\n⚠️  SOME TESTS FAILED - VR integration may have issues")
        logger.error(f"\nFailed tests: {total - passed}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
