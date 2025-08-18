"""Test suite for the Buttplug protocol implementation."""

import asyncio
import pytest
import pytest_asyncio
import time
import sys
from pathlib import Path
from unittest.mock import MagicMock

pytestmark = pytest.mark.asyncio  # Mark all tests as async

# Port cycling for parallel test execution
_test_port = 12345
def get_next_port():
    """Get next available port for testing."""
    global _test_port
    _test_port += 1
    return _test_port

from ..engine.buttplug_server import ButtplugServer
from ..engine.pulse import PulseEngine, clamp
from .virtual_toy import VirtualToy  # Virtual toy for testing
from .virtual_toy import VirtualToy

# Utility for running async tests
async def run_for(coroutine, duration: float):
    """Run a coroutine for a specific duration."""
    try:
        await asyncio.wait_for(coroutine, timeout=duration)
    except asyncio.TimeoutError:
        pass  # Expected when we want to run for a fixed duration

@pytest_asyncio.fixture
async def server():
    """Fixture that provides a ButtplugServer instance."""
    port = get_next_port()
    server = ButtplugServer(port=port)
    server.start()
    # Give server time to start
    await asyncio.sleep(0.1)
    yield server
    server.stop()
    await asyncio.sleep(0.1)

@pytest_asyncio.fixture
async def virtual_toy(server):
    """Fixture that provides a VirtualToy instance."""
    port = server.port  # Use same port as server
    toy = VirtualToy(port=port)
    await asyncio.sleep(0.1)  # Give time for setup
    yield toy
    await toy.disconnect()

@pytest.fixture
def pulse_engine():
    """Fixture that provides a PulseEngine instance."""
    engine = PulseEngine(quiet=True)
    yield engine
    engine.stop()

# ==== Test ButtplugServer ====
async def test_server_startup(server):
    """Test that server starts up correctly."""
    toy = VirtualToy(port=server.port)
    assert await toy.connect()
    await toy.disconnect()

async def test_server_device_detection(server, virtual_toy):
    """Test that server detects connected devices."""
    assert await virtual_toy.connect()
    assert virtual_toy.state.is_active == False
    assert virtual_toy.state.level == 0.0

async def test_server_command_handling(server, virtual_toy):
    """Test that server properly handles device commands."""
    assert await virtual_toy.connect()
    
    # Start listening for commands
    listen_task = asyncio.create_task(virtual_toy.start_listening())
    await asyncio.sleep(0.1)  # Wait for listener to start
    
    # Create engine and send commands
    engine = PulseEngine(url=f"ws://127.0.0.1:{server.port}", quiet=True, server=server)
    engine.start()
    await asyncio.sleep(1.0)  # Wait for connection and device discovery
    
    # Test different intensities
    test_levels = [0.0, 0.5, 1.0, 0.25, 0.0]
    for level in test_levels:
        engine.set_level(level)
        await asyncio.sleep(0.2)  # Wait for command to process
        assert abs(virtual_toy.state.level - level) < 0.01
        assert virtual_toy.state.is_active == (level > 0)
    
    engine.stop()
    listen_task.cancel()

# ==== Test PulseEngine ====
# Remove global asyncio mark for this test
@pytest.mark.asyncio(loop_scope="session")
def test_clamp_function():
    """Test the clamp utility function."""
    assert clamp(0.5, 0, 1) == 0.5
    assert clamp(-0.5, 0, 1) == 0
    assert clamp(1.5, 0, 1) == 1.0
    assert clamp(0.3, 0.4, 0.8) == 0.4
    assert clamp(0.9, 0.4, 0.8) == 0.8

async def test_pulse_engine_lifecycle(pulse_engine):
    """Test PulseEngine start/stop lifecycle."""
    pulse_engine.start()
    assert pulse_engine._enabled
    await asyncio.sleep(0.1)
    
    pulse_engine.stop()
    assert not pulse_engine._enabled
    await asyncio.sleep(0.1)

async def test_pulse_engine_commands(server, virtual_toy, pulse_engine):
    """Test PulseEngine command generation."""
    assert await virtual_toy.connect()
    listen_task = asyncio.create_task(virtual_toy.start_listening())
    await asyncio.sleep(0.1)  # Wait for listener to start
    
    # Update engine's URL to match server's port
    pulse_engine.url = f"ws://127.0.0.1:{server.port}"
    pulse_engine._server = server  # Use test server
    pulse_engine.start()
    await asyncio.sleep(1.0)  # Wait for connection and device discovery
    
    # Test sustained level
    pulse_engine.set_level(0.7)
    await asyncio.sleep(0.2)
    assert abs(virtual_toy.state.level - 0.7) < 0.01
    
    # Test pulse
    pulse_engine.pulse(1.0, 200)  # 200ms pulse
    await asyncio.sleep(0.1)
    assert virtual_toy.state.level > 0.9  # Should be at peak
    await asyncio.sleep(0.3)  # Wait for pulse to end
    assert virtual_toy.state.level < 0.1  # Should be back to base level
    
    pulse_engine.stop()
    listen_task.cancel()

# ==== Integration Tests ====
async def test_full_integration(server, virtual_toy):
    """Test full integration between server, engine, and virtual toy."""
    assert await virtual_toy.connect()
    listen_task = asyncio.create_task(virtual_toy.start_listening())
    
    engine = PulseEngine(quiet=True)
    engine.start()
    await asyncio.sleep(0.5)
    
    # Test a complex pattern
    patterns = [
        (0.3, 300),  # Low pulse
        (0.7, 200),  # Medium pulse
        (1.0, 100),  # Short peak
        (0.0, 200),  # Rest
        (0.5, 300),  # Medium sustained
    ]
    
    for level, duration_ms in patterns:
        engine.pulse(level, duration_ms)
        await asyncio.sleep(duration_ms / 1000 + 0.1)  # Wait for pattern to complete

async def test_device_scanning():
    """Test scanning for devices with a virtual toy."""
    
    # Start the server
    server = ButtplugServer(port=get_next_port())
    server.start()
    
    # Create and connect virtual toy
    toy = VirtualToy(name="Test Virtual Toy", port=server.port)
    connected = await toy.connect()
    assert connected, "Virtual toy should connect successfully"
    
    # Wait for device registration
    await asyncio.sleep(1.0)
    
    # Get device list
    device_list = server.get_device_list()
    assert len(device_list.devices) == 1, "Should find exactly one device"
    assert device_list.devices[0].name == "Test Virtual Toy", "Device name should match"
    
    # Cleanup
    await toy.disconnect()
    server.stop()
    await asyncio.sleep(0.1)  # Allow cleanup to complete
    listen_task.cancel()
