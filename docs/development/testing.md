# Testing Guide

## Overview
This guide covers testing procedures for MesmerGlass components and features. The test suite has been completely reorganized with a comprehensive test runner and categorized test execution.

## Quick Start

### Using the Test Runner
The recommended way to run tests is via the MesmerGlass CLI wrapper:

```powershell
# Run all tests
python -m mesmerglass test-run all

# Run only fast tests (excludes slow/integration tests)
python -m mesmerglass test-run fast

# Run only unit tests (excludes integration and bluetooth tests)
python -m mesmerglass test-run unit

# Run integration tests
python -m mesmerglass test-run integration

# Run bluetooth-specific tests
python -m mesmerglass test-run bluetooth

# Run slow tests only
python -m mesmerglass test-run slow

# Run with verbose output
python -m mesmerglass test-run all -v

# Run with coverage report
python -m mesmerglass test-run -c
```

### Direct pytest Usage
```powershell
# Run all tests directly
python -m pytest

# Run with verbosity
python -m pytest -v

# Run with coverage
python -m pytest --cov=mesmerglass

# Run tests in parallel (faster)
python -m pytest -n auto

# Stop on first failure
python -m pytest -x

# Run specific test markers
python -m pytest -m "not slow"
python -m pytest -m "integration"
python -m pytest -m "bluetooth"
```

### Specific Tests
```powershell
# Test specific files
python -m pytest mesmerglass/tests/test_buttplug.py
python -m pytest mesmerglass/tests/test_ui.py
python -m pytest mesmerglass/tests/test_bluetooth.py
python -m pytest mesmerglass/tests/test_device_control.py
python -m pytest mesmerglass/tests/test_mesmerintiface_integration.py

# Single test function
python -m pytest mesmerglass/tests/test_buttplug.py::test_server_startup

# Run tests by pattern
python -m pytest -k "bluetooth"
python -m pytest -k "device"
```

## Test Categories

The test suite is organized into several categories with specific markers:

### Test Markers
- `slow` - Tests that take longer to execute (>2 seconds)
- `integration` - Tests that test multiple components together
- `bluetooth` - Tests requiring Bluetooth functionality
- `unit` - Pure unit tests (default, no marker needed)

### 1. Core Server Tests (`test_buttplug.py`)
- Server startup/shutdown
- Device detection and management
- Command handling and routing
- Protocol implementation
- Virtual device integration

### 2. Bluetooth Functionality Tests (`test_bluetooth.py`)
- Bluetooth device scanning and discovery
- Device identification and protocol detection
- Connection lifecycle management
- Lovense and WeVibe protocol support
- Error handling and recovery

### 3. Device Control Tests (`test_device_control.py`)
- MesmerIntiface server integration
- Device control command processing
- Vibration and pattern control
- Multi-device coordination
- Real device simulation

### 4. Integration Tests (`test_mesmerintiface_integration.py`)
- Full system integration testing
- MesmerIntiface with MesmerGlass integration
- Pulse engine coordination
- End-to-end device workflows
- Performance and reliability testing
### 5. UI Tests (`test_ui.py`)
- Media Controls
  - Video file selection and playback
  - Opacity controls and display settings
  - Window management and positioning
- Text Effects
  - Text input and processing
  - Font selection and rendering
  - Effect modes and transitions
  - Effect intensity control
- Audio Controls
  - Audio file selection and loading
  - Volume controls and audio processing
  - Playback state management
- Launch/Display
  - Overlay window creation and management
  - Display selection and configuration
  - Multi-monitor support
- Dev Tools
  - Virtual toy creation and management
  - Virtual toy removal and cleanup
  - Intensity control and testing
  - Multiple toy coordination

## Test Infrastructure

### Test Runner Features
The `python -m mesmerglass test-run` wrapper provides:
- **Categorized Execution**: Run specific types of tests based on markers
- **Verbose Output**: `-v`
- **Coverage**: `-c`

### Custom Markers
Defined in `pytest.ini`:
```ini
[tool:pytest]
markers =
    slow: marks tests as slow (deselected with -m 'not slow')
    integration: marks tests as integration tests
    bluetooth: marks tests as requiring Bluetooth functionality
```

## Writing Tests

### Test Structure Guidelines

#### Basic Test Structure
```python
import pytest
import asyncio
from unittest.mock import MagicMock, patch

@pytest.mark.asyncio
async def test_async_feature():
    """Test description with clear purpose."""
    # Setup
    server = MesmerIntifaceServer(port=12345)
    await server.start()
    
    try:
        # Test execution
        result = await server.some_operation()
        assert result == expected_value
        
        # Additional assertions
        assert server.is_running
        
    finally:
        # Cleanup
        await server.stop()

def test_sync_feature():
    """Test synchronous functionality."""
    # Setup
    device_info = BluetoothDeviceInfo(
        address="88:1A:14:38:08:D0",
        name="LVS-Hush",
        rssi=-40
    )
    
    # Test execution
    assert device_info.address == "88:1A:14:38:08:D0"
    assert device_info.name == "LVS-Hush"
```

#### Using Test Fixtures
```python
@pytest.fixture
async def mesmer_server():
    """Provide a running MesmerIntiface server for testing."""
    server = MesmerIntifaceServer(port=get_free_port())
    await server.start()
    yield server
    await server.stop()

@pytest.fixture
def mock_device():
    """Provide a mock Bluetooth device for testing."""
    return BluetoothDeviceInfo(
        address="88:1A:14:38:08:D0",
        name="LVS-Hush",
        rssi=-40
    )
```

### Test Categories and Markers

#### Unit Tests (Default)
- Test individual functions/methods in isolation
- Use mocks for external dependencies
- Fast execution (< 1 second)
- No special marker needed

#### Integration Tests
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_device_workflow():
    """Test complete device discovery and control workflow."""
    # Tests multiple components working together
```

#### Bluetooth Tests
```python
@pytest.mark.bluetooth
@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_bluetooth_scanning():
    """Test actual Bluetooth functionality."""
    # Tests requiring real Bluetooth hardware
```

#### Slow Tests
```python
@pytest.mark.slow
@pytest.mark.asyncio
async def test_long_running_operation():
    """Test that takes significant time."""
    # Tests that take > 2 seconds
```
### UI Test Guidelines
1. Use `QTest.qWait()` after UI operations to ensure state updates
2. Clean up windows and overlays properly using `deleteLater()` and `close()`
3. Use proper widget hierarchy for finding controls with `findChild()`
4. Handle async operations with pytest-asyncio and proper event loop management
5. Test UI components in isolation with mock backend services

### Bluetooth Test Guidelines
1. Use mocks for Bluetooth operations unless testing real hardware
2. Clean up connections and servers properly in teardown
3. Use appropriate timeouts for async operations (default 30s)
4. Handle device discovery with proper callback simulation
5. Test error conditions and recovery scenarios

### Integration Test Guidelines
1. Test component interactions and data flow
2. Use realistic test data and scenarios
3. Verify end-to-end functionality
4. Include performance and reliability testing
5. Clean up all resources and connections

### Best Practices
1. **Test Independence**: Each test should work in isolation without dependencies
2. **Clear Naming**: Use descriptive test names that explain what is being tested
3. **Proper Cleanup**: Always clean up resources in try/finally blocks or fixtures
4. **Mock External Dependencies**: Mock hardware, network, and file system operations
5. **Assert Meaningfully**: Test both positive and negative cases with clear assertions

## Common Test Patterns

### Testing Async Operations
```python
@pytest.mark.asyncio
async def test_async_operation():
    with patch('mesmerglass.engine.mesmerintiface.some_async_call') as mock_call:
        mock_call.return_value = expected_result
        result = await function_under_test()
        assert result == expected_result
        mock_call.assert_called_once()
```

### Testing Device Protocols
```python
def test_lovense_protocol():
    protocol = LovenseProtocol()
    command = protocol.create_vibration_command(intensity=50)
    assert command == b"Vibrate:10;"  # Expected Lovense format
```

### Testing Error Handling
```python
@pytest.mark.asyncio
async def test_connection_error_handling():
    with patch('bleak.BleakClient.connect') as mock_connect:
        mock_connect.side_effect = BleakError("Connection failed")
        
        with pytest.raises(DeviceConnectionError):
            await connect_to_device("invalid_address")
```

## Troubleshooting

### Common Test Issues

#### 1. Async Test Failures
**Symptoms**: Tests hang, timeout, or fail with event loop errors
**Solutions**:
- Ensure proper cleanup in try/finally blocks
- Check for unclosed connections or resources
- Verify timeout settings are appropriate
- Use `pytest-asyncio` for async test management

#### 2. Import Errors
#### 2.5 Windows Socket/Port Conflicts
**Symptoms**: `[WinError 10048] only one usage of each socket address...` during tests that start servers.
**Solutions**:
- Prefer dynamic ports in tests by passing `port=0` when creating `ButtplugServer`/`MesmerIntifaceServer` to bind an ephemeral free port. Read `server.port` after `start()` to get the actual port.
- Avoid running multiple instances bound to the same fixed port concurrently.

#### 2.6 Windows BLE Event Loop Warnings
**Symptoms**: `RuntimeError: Event loop is closed` from bleak scanner during teardown.
**Notes**: These can occur when a background BLE callback fires during test shutdown. We guard these internally; the warnings are benign. Ensure proper teardown order and allow a short sleep after stopping servers.

**Symptoms**: `ImportError` or `ModuleNotFoundError` in tests
**Solutions**:
- Verify relative imports use correct paths (e.g., `..engine.mesmerintiface`)
- Check class names match actual implementation
- Ensure test files are in proper package structure

#### 3. Device Connection Issues
**Symptoms**: Bluetooth tests fail, connection timeouts
**Solutions**:
- Mock external Bluetooth services for unit tests
- Use virtual devices for testing
- Handle timeouts properly with realistic values
- Test error conditions separately

#### 4. UI Test Problems
**Symptoms**: Widget not found, UI tests fail randomly
**Solutions**:
- Use proper Qt test fixtures and event loops
- Handle window management with proper cleanup
- Wait for UI updates with `QTest.qWait()`
- Navigate widget hierarchy correctly

#### 5. Test Dependencies
**Symptoms**: Tests pass individually but fail when run together
**Solutions**:
- Ensure each test cleans up properly
- Use fresh fixtures for each test
- Avoid global state modifications
- Reset mocks between tests

### Debugging Tests

#### Running Individual Tests with Debug Info
```powershell
# Run single test with verbose output
python -m pytest mesmerglass/tests/test_bluetooth.py::test_device_connection -v -s

# Run with debug logging
python -m pytest --log-level=DEBUG

# Run with coverage and see which lines aren't tested
python run_tests.py unit --coverage
```

#### Using pytest Debugging
```python
# Add debug breakpoint in test
import pytest
def test_something():
    # Set breakpoint for debugging
    import pdb; pdb.set_trace()
    
    # Or use pytest breakpoint
    pytest.set_trace()
```

## Performance Testing

### Timing Tests
```python
import time
import pytest

@pytest.mark.slow
def test_performance():
    start_time = time.time()
    
    # Operation under test
    result = expensive_operation()
    
    duration = time.time() - start_time
    assert duration < 2.0  # Should complete in under 2 seconds
    assert result is not None
```

### Memory Usage Tests
```python
import psutil
import os

def test_memory_usage():
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss
    
    # Operation that might leak memory
    for _ in range(1000):
        create_and_destroy_object()
    
    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory
    
    # Memory increase should be reasonable (< 10MB)
    assert memory_increase < 10 * 1024 * 1024
```

## CI/CD Integration

Tests are automatically run on:
- Pull requests to main branch
- Direct commits to main branch  
- Release tag creation
- Scheduled nightly builds

### CI Test Categories
- **Fast Tests**: Run on every commit (`python run_tests.py fast`)
- **Full Suite**: Run on pull requests (`python run_tests.py all`)
- **Integration Tests**: Run on release candidates (`python run_tests.py integration`)

### Test Coverage Requirements
- Minimum 80% code coverage for new features
- Critical paths must have 95%+ coverage
- All public APIs must have tests
