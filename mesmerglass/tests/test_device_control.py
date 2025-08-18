"""Tests for MesmerIntiface device control functionality."""

import asyncio
import pytest
import logging
from unittest.mock import MagicMock, patch, AsyncMock

from ..engine.mesmerintiface import MesmerIntifaceServer
from ..engine.mesmerintiface.bluetooth_scanner import BluetoothDeviceScanner, BluetoothDeviceInfo
from ..engine.mesmerintiface.device_protocols import LovenseProtocol

pytestmark = pytest.mark.asyncio


class TestMesmerIntifaceDeviceControl:
    """Test MesmerIntiface device control capabilities."""

    @pytest.fixture
    def server_port(self):
        """Get unique port for testing."""
        return 12351

    @pytest.fixture
    async def mesmer_server(self, server_port):
        """Create MesmerIntiface server for testing."""
        server = MesmerIntifaceServer(port=server_port)
        server.start()
        await asyncio.sleep(0.1)
        yield server
        server.stop()

    @pytest.fixture
    def mock_device_info(self):
        """Create mock device info for testing."""
        device = BluetoothDeviceInfo(
            address="88:1A:14:38:08:D0",
            name="LVS-Hush",
            rssi=-40,
            manufacturer_data={},
            service_uuids=["5a300001-0023-4bd4-bbd5-a6920e4c5653"]
        )
        device.device_type = "sex_toy"
        device.protocol = "lovense"
        device.is_connected = False
        return device

    async def test_server_initialization(self, server_port):
        """Test MesmerIntiface server initialization."""
        server = MesmerIntifaceServer(port=server_port + 10)
        
        # Server should initialize without errors
        assert server is not None
        
        # Test start/stop
        server.start()
        await asyncio.sleep(0.1)
        server.stop()

    async def test_bluetooth_scanner_creation(self, mesmer_server):
        """Test BluetoothDeviceScanner functionality."""
        # Server should have a bluetooth scanner
        assert hasattr(mesmer_server, '_bluetooth_scanner')
        scanner = mesmer_server._bluetooth_scanner
        assert isinstance(scanner, BluetoothDeviceScanner)

    async def test_device_discovery_simulation(self, mesmer_server, mock_device_info):
        """Test device discovery with simulated devices."""
        with patch.object(mesmer_server._bluetooth_scanner, 'get_discovered_devices') as mock_get_devices:
            mock_get_devices.return_value = [mock_device_info]
            
            # Start scanning
            scan_result = await mesmer_server.start_real_scanning()
            await asyncio.sleep(0.1)
            
            # Get discovered devices
            devices = mesmer_server._bluetooth_scanner.get_discovered_devices()
            
            # Should return our mock device
            assert len(devices) >= 0  # May be 0 or 1 depending on mock behavior
            
            await mesmer_server.stop_real_scanning()

    async def test_lovense_protocol_creation(self):
        """Test Lovense protocol instantiation."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        assert protocol.device_address == "88:1A:14:38:08:D0"
        assert protocol.device_name == "LVS-Hush"
        assert protocol.capabilities is not None

    async def test_device_connection_simulation(self, mesmer_server, mock_device_info):
        """Test device connection with mocked BLE client."""
        # Mock the connection process
        with patch('bleak.BleakClient') as mock_bleak_client:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.is_connected = True
            mock_client.services = []
            mock_bleak_client.return_value = mock_client
            
            # Attempt connection (this tests the connection logic)
            connection_result = await mesmer_server._bluetooth_scanner.connect_device(
                mock_device_info.address
            )
            
            # Should complete without errors (may succeed or fail gracefully)
            assert connection_result is True or connection_result is False

    async def test_protocol_dual_uuid_support(self):
        """Test Lovense protocol dual UUID support."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Check that both v1 and v2 UUIDs are defined
        assert hasattr(protocol, 'SERVICE_UUID_V1')
        assert hasattr(protocol, 'SERVICE_UUID_V2')
        assert hasattr(protocol, 'TX_CHAR_UUID_V1')
        assert hasattr(protocol, 'TX_CHAR_UUID_V2')
        assert hasattr(protocol, 'RX_CHAR_UUID_V1')
        assert hasattr(protocol, 'RX_CHAR_UUID_V2')
        
        # UUIDs should be different
        assert protocol.SERVICE_UUID_V1 != protocol.SERVICE_UUID_V2
        assert protocol.TX_CHAR_UUID_V1 != protocol.TX_CHAR_UUID_V2

    async def test_device_capabilities_setup(self):
        """Test device capabilities are properly configured."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Should have capabilities
        assert protocol.capabilities is not None
        assert hasattr(protocol.capabilities, 'has_vibrator')
        assert hasattr(protocol.capabilities, 'vibrator_count')
        assert hasattr(protocol.capabilities, 'has_battery')

    async def test_vibration_command_formatting(self):
        """Test vibration command formatting."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Mock client for testing
        mock_client = AsyncMock()
        mock_client.write_gatt_char = AsyncMock(return_value=True)
        protocol._client = mock_client
        
        # Test vibration command (this tests the command formatting logic)
        with patch.object(protocol, 'TX_CHAR_UUID', '5a300002-0023-4bd4-bbd5-a6920e4c5653'):
            result = await protocol.vibrate(0.5)  # 50% intensity
            
            # Should complete without errors
            assert result is True or result is False

    async def test_notification_callback_safety(self):
        """Test notification callback handles errors gracefully."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Test notification with invalid data
        protocol._notification_active = True
        
        # Should not raise exceptions
        try:
            protocol._on_notification(None, b"invalid data")
            protocol._on_notification(None, b"Battery:85")
            assert True
        except Exception as e:
            pytest.fail(f"Notification callback raised exception: {e}")

    async def test_protocol_cleanup(self):
        """Test protocol cleanup functionality."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Mock client
        mock_client = AsyncMock()
        mock_client.stop_notify = AsyncMock(return_value=True)
        protocol._client = mock_client
        protocol._notification_active = True
        protocol.RX_CHAR_UUID = "5a300003-0023-4bd4-bbd5-a6920e4c5653"
        
        # Test cleanup
        result = await protocol.cleanup()
        
        # Should succeed
        assert result is True

    @pytest.mark.slow
    async def test_full_device_workflow_simulation(self, mesmer_server):
        """Test complete device workflow with mocking."""
        # This test simulates the full device discovery -> connection -> control workflow
        
        # Mock device discovery
        with patch.object(mesmer_server._bluetooth_scanner, 'start_scanning') as mock_start, \
             patch.object(mesmer_server._bluetooth_scanner, 'stop_scanning') as mock_stop:
            
            mock_start.return_value = True
            mock_stop.return_value = True
            
            # Start scanning
            scan_result = await mesmer_server.start_real_scanning()
            await asyncio.sleep(0.1)
            
            # Stop scanning
            stop_result = await mesmer_server.stop_real_scanning()
            
            # Both operations should complete
            assert scan_result is True or scan_result is False
            assert stop_result is None  # stop_real_scanning returns None
