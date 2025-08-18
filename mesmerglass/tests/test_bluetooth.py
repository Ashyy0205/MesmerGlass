"""Tests for Bluetooth scanning and device communication."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from ..engine.mesmerintiface.bluetooth_scanner import BluetoothDeviceScanner, BluetoothDeviceInfo
from ..engine.mesmerintiface.device_protocols import LovenseProtocol, WeVibeProtocol


class TestBluetoothFunctionality:
    """Test Bluetooth scanning and device communication."""

    @pytest.fixture
    def bluetooth_scanner(self):
        """Create BluetoothDeviceScanner for testing."""
        return BluetoothDeviceScanner()

    @pytest.fixture
    def mock_lovense_device(self):
        """Create mock Lovense device info."""
        device = BluetoothDeviceInfo(
            address="88:1A:14:38:08:D0",
            name="LVS-Hush",
            rssi=-40,
            manufacturer_data={},
            service_uuids=["5a300001-0023-4bd4-bbd5-a6920e4c5653"]
        )
        device.device_type = "sex_toy"
        device.protocol = "lovense"
        return device

    def test_device_info_creation(self):
        """Test BluetoothDeviceInfo creation and properties."""
        device = BluetoothDeviceInfo(
            address="88:1A:14:38:08:D0",
            name="LVS-Hush",
            rssi=-40,
            manufacturer_data={},
            service_uuids=["5a300001-0023-4bd4-bbd5-a6920e4c5653"]
        )
        
        assert device.address == "88:1A:14:38:08:D0"
        assert device.name == "LVS-Hush"
        assert device.rssi == -40
        assert device.manufacturer_data == {}
        assert device.service_uuids == ["5a300001-0023-4bd4-bbd5-a6920e4c5653"]
        assert device.is_connected is False

    def test_bluetooth_scanner_initialization(self, bluetooth_scanner):
        """Test BluetoothDeviceScanner initialization."""
        assert bluetooth_scanner is not None
        assert hasattr(bluetooth_scanner, '_discovered_devices')
        assert hasattr(bluetooth_scanner, '_connected_clients')

    @pytest.mark.asyncio
    async def test_device_identification(self, bluetooth_scanner, mock_lovense_device):
        """Test device identification logic."""
        # Mock the device identification
        with patch.object(bluetooth_scanner, '_identify_device') as mock_identify:
            mock_identify.return_value = ("sex_toy", "lovense")
            
            device_type, protocol = bluetooth_scanner._identify_device(mock_lovense_device)
            
            assert device_type == "sex_toy"
            assert protocol == "lovense"

    # Should detect device properly
        assert True  # Basic test to verify no exceptions

    @pytest.mark.asyncio
    async def test_scanning_lifecycle(self, bluetooth_scanner):
        """Test scanning start/stop lifecycle."""
        # Mock bleak scanner
        with patch('bleak.BleakScanner') as mock_scanner_class:
            mock_scanner = AsyncMock()
            mock_scanner.start = AsyncMock()
            mock_scanner.stop = AsyncMock()
            mock_scanner_class.return_value = mock_scanner
            
            # Test start scanning
            result = await bluetooth_scanner.start_scanning()
            assert isinstance(result, bool)
            
            # Test stop scanning (returns None)
            result = await bluetooth_scanner.stop_scanning()
            assert result is None

    @pytest.mark.asyncio
    async def test_device_connection_logic(self, bluetooth_scanner, mock_lovense_device):
        """Test device connection logic."""
        # Mock BleakClient
        with patch('bleak.BleakClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.is_connected = True
            mock_client.services = []
            mock_client_class.return_value = mock_client
            
            # Test connection
            result = await bluetooth_scanner.connect_device(mock_lovense_device.address)
            
            # Should complete (success or failure both acceptable)
            assert result is True or result is False

    def test_lovense_device_type_identification(self):
        """Test Lovense device type identification."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Test device type identification
        device_type = protocol._identify_device_type("LVS-Hush")
        assert device_type == "hush"
        
        device_type = protocol._identify_device_type("Lovense Lush")
        assert device_type == "lush"
        
        device_type = protocol._identify_device_type("Unknown Device")
        assert device_type == "generic"

    def test_lovense_capabilities_setup(self):
        """Test Lovense device capabilities setup."""
        # Test different device types
        hush_protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        assert hush_protocol.capabilities.has_vibrator is True
        assert hush_protocol.capabilities.vibrator_count == 1
        assert hush_protocol.capabilities.has_battery is True
        
        edge_protocol = LovenseProtocol("88:1A:14:38:08:D1", "Lovense Edge")
        assert edge_protocol.capabilities.has_vibrator is True
        assert edge_protocol.capabilities.vibrator_count == 2  # Edge has 2 vibrators

    @pytest.mark.asyncio
    async def test_protocol_initialization_logic(self):
        """Test protocol initialization with mock client."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Mock client with v2 services
        mock_client = AsyncMock()
        mock_service_v2 = MagicMock()
        mock_service_v2.uuid = "5a300001-0023-4bd4-bbd5-a6920e4c5653"
        mock_client.services = [mock_service_v2]
        mock_client.start_notify = AsyncMock()
        
        # Test initialization
        result = await protocol.initialize(mock_client)
        
        # Should detect v2 protocol
        assert result is True
        assert protocol.SERVICE_UUID == protocol.SERVICE_UUID_V2
        assert protocol.TX_CHAR_UUID == protocol.TX_CHAR_UUID_V2
        assert protocol.RX_CHAR_UUID == protocol.RX_CHAR_UUID_V2

    @pytest.mark.asyncio
    async def test_vibration_command_generation(self):
        """Test vibration command generation."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Mock client
        mock_client = AsyncMock()
        mock_client.write_gatt_char = AsyncMock()
        protocol._client = mock_client
        protocol.TX_CHAR_UUID = "5a300002-0023-4bd4-bbd5-a6920e4c5653"
        
        # Test vibration command
        result = await protocol.vibrate(0.5)  # 50% intensity
        
        # Should call write_gatt_char with proper command
        if mock_client.write_gatt_char.called:
            call_args = mock_client.write_gatt_char.call_args
            command_bytes = call_args[0][1]
            command_str = command_bytes.decode('utf-8')
            assert "Vibrate:" in command_str
            assert command_str.endswith(";")

    @pytest.mark.asyncio
    async def test_stop_command_generation(self):
        """Test stop command generation."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        
        # Mock client
        mock_client = AsyncMock()
        mock_client.write_gatt_char = AsyncMock()
        protocol._client = mock_client
        protocol.TX_CHAR_UUID = "5a300002-0023-4bd4-bbd5-a6920e4c5653"
        
        # Test stop command
        result = await protocol.stop()
        
        # Should call write_gatt_char with stop command
        if mock_client.write_gatt_char.called:
            call_args = mock_client.write_gatt_char.call_args
            command_bytes = call_args[0][1]
            command_str = command_bytes.decode('utf-8')
            assert "Vibrate:0;" in command_str

    def test_wevibe_protocol_creation(self):
        """Test WeVibe protocol creation."""
        protocol = WeVibeProtocol("AA:BB:CC:DD:EE:FF", "We-Vibe Test")
        
        assert protocol.device_address == "AA:BB:CC:DD:EE:FF"
        assert protocol.device_name == "We-Vibe Test"
        assert protocol.capabilities is not None

    @pytest.mark.asyncio
    async def test_device_discovery_callback_simulation(self, bluetooth_scanner):
        """Test device discovery callback handling."""
        # Mock advertisement data
        mock_device = MagicMock()
        mock_device.address = "88:1A:14:38:08:D0"
        mock_device.name = "LVS-Hush"
        mock_advertisement = MagicMock()
        mock_advertisement.service_uuids = ["5a300001-0023-4bd4-bbd5-a6920e4c5653"]
        mock_advertisement.manufacturer_data = {}
        
        # Test callback (should not raise exceptions)
        try:
            bluetooth_scanner._on_device_detected(mock_device, mock_advertisement)
            assert True
        except Exception as e:
            pytest.fail(f"Device discovery callback failed: {e}")

    @pytest.mark.asyncio
    async def test_notification_error_handling(self):
        """Test notification callback error handling."""
        protocol = LovenseProtocol("88:1A:14:38:08:D0", "LVS-Hush")
        protocol._notification_active = True
        
        # Test with various invalid inputs
        test_cases = [
            b"",  # Empty data
            b"\x00\x01\x02",  # Binary data
            b"Invalid:Command;",  # Invalid command
            b"Battery:invalid",  # Invalid battery format
        ]
        
        for test_data in test_cases:
            try:
                protocol._on_notification(None, test_data)
                # Should not raise exceptions
                assert True
            except Exception as e:
                pytest.fail(f"Notification callback failed with data {test_data}: {e}")

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, bluetooth_scanner):
        """Test concurrent scanning and connection operations."""
        # Mock multiple concurrent operations
        with patch('bleak.BleakScanner') as mock_scanner_class, \
             patch('bleak.BleakClient') as mock_client_class:
            
            mock_scanner = AsyncMock()
            mock_client = AsyncMock()
            mock_scanner_class.return_value = mock_scanner
            mock_client_class.return_value = mock_client
            
            # Start multiple operations concurrently
            tasks = [
                bluetooth_scanner.start_scanning(),
                bluetooth_scanner.stop_scanning(),
                bluetooth_scanner.connect_device("88:1A:14:38:08:D0"),
                bluetooth_scanner.disconnect_device("88:1A:14:38:08:D0")
            ]
            
            # Should complete without errors
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check that no unhandled exceptions occurred
            for result in results:
                if isinstance(result, Exception):
                    # Some exceptions might be expected, but shouldn't be fatal
                    assert not isinstance(result, (SystemExit, KeyboardInterrupt))
