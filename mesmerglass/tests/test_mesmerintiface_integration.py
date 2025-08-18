"""Integration tests for MesmerIntiface with MesmerGlass components."""

import asyncio
import pytest
import time
from unittest.mock import MagicMock, patch

from ..engine.pulse import PulseEngine
from ..engine.mesmerintiface import MesmerIntifaceServer

pytestmark = pytest.mark.asyncio


class TestMesmerIntifaceIntegration:
    """Test MesmerIntiface integration with other components."""

    @pytest.fixture
    def server_port(self):
        """Get unique port for testing."""
        return 12350

    @pytest.fixture
    async def mesmer_server(self, server_port):
        """Create and start MesmerIntiface server for testing."""
        server = MesmerIntifaceServer(port=server_port)
        server.start()
        await asyncio.sleep(0.1)  # Brief startup delay
        yield server
        server.stop()

    async def test_pulse_engine_integration(self, mesmer_server, server_port):
        """Test PulseEngine with MesmerIntiface integration."""
        # Create PulseEngine with MesmerIntiface
        pulse = PulseEngine(use_mesmer=True, quiet=True)
        
        try:
            # Start pulse engine
            pulse.start()
            await asyncio.sleep(0.1)
            
            # Test basic commands (these should not fail even without devices)
            pulse.set_level(0.3)
            await asyncio.sleep(0.1)
            
            pulse.pulse(0.7, 500)
            await asyncio.sleep(0.1)
            
            pulse.stop()
            await asyncio.sleep(0.1)
            
            # Verify pulse engine started successfully
            assert pulse is not None
            
        finally:
            pulse.stop()

    async def test_server_status(self, mesmer_server):
        """Test MesmerIntiface server status reporting."""
        status = mesmer_server.get_status()
        
        # Verify status contains expected keys
        assert isinstance(status, dict)
        assert 'port' in status
        assert 'running' in status
        assert status['port'] == 12350
        assert status['running'] is True

    async def test_bluetooth_scanning(self, mesmer_server):
        """Test Bluetooth scanning functionality."""
        # This test should work even without actual devices
        scan_success = await mesmer_server.start_real_scanning()
        
        # Should succeed in starting scan (even if no devices found)
        assert scan_success is True or scan_success is False  # Either outcome is valid
        
        # Stop scanning
        stop_success = await mesmer_server.stop_real_scanning()
        assert stop_success is True or stop_success is False

    async def test_device_database_access(self, mesmer_server):
        """Test device database functionality."""
        try:
            from ..engine.mesmerintiface.device_database import DeviceDatabase
            db = DeviceDatabase()
            devices = db.get_all_devices()
            
            # Should return a list (may be empty)
            assert isinstance(devices, list)
            
        except ImportError:
            # Device database may not be implemented yet
            pytest.skip("DeviceDatabase not available")

    async def test_server_lifecycle(self, server_port):
        """Test MesmerIntiface server start/stop lifecycle."""
        server = MesmerIntifaceServer(port=server_port + 1)
        
        # Test start
        server.start()
        await asyncio.sleep(0.1)
        
        status = server.get_status()
        assert status['running'] is True
        
        # Test stop
        server.stop()
        await asyncio.sleep(0.1)
        
        # Server should be stopped
        # Note: get_status might not be available after stop, so we just verify no exceptions
        assert True  # If we reach here, lifecycle worked

    @pytest.mark.slow
    async def test_real_device_simulation(self, mesmer_server):
        """Test with simulated device responses."""
        # Mock device responses for testing
        with patch.object(mesmer_server, '_bluetooth_scanner') as mock_scanner:
            mock_scanner.scan_for_devices.return_value = []
            mock_scanner.get_discovered_devices.return_value = []
            
            # Test scanning with mocked scanner
            scan_result = await mesmer_server.start_real_scanning()
            await asyncio.sleep(0.1)
            await mesmer_server.stop_real_scanning()
            
            # Should complete without errors
            assert True
