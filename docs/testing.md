# Testing Guide

## Overview
This guide covers testing procedures for MesmerGlass components and features.

## Running Tests

### Full Test Suite
```powershell
# Run all tests
python -m pytest

# Run with verbosity
python -m pytest -v

# Run with coverage
python -m pytest --cov=mesmerglass

# Run tests in parallel (faster)
python -m pytest -n auto

# Stop on first failure
python -m pytest -x

# Show brief output
python -m pytest -q
```

### Specific Tests
```powershell
# Test categories
python -m pytest mesmerglass/tests/test_buttplug.py
python -m pytest mesmerglass/tests/test_ui.py

# Single test function
python -m pytest mesmerglass/tests/test_buttplug.py::test_server_startup
```

## Test Categories

### 1. Core Server Tests (`test_buttplug.py`)
- Server startup/shutdown
- Device detection
- Command handling
- Protocol implementation

### 2. Device Management Tests
- Device scanning
- Selection handling
- State management
- Command routing

### 3. Pulse Engine Tests
- Initialization
- Command processing
- Timing accuracy
- Error handling

### 4. Virtual Device Tests
- Connection
- Command handling
- State synchronization
- Error recovery

### 5. UI Tests (`test_ui.py`)
- Media Controls
  - Video file selection
  - Opacity controls
  - Display settings
- Text Effects
  - Text input
  - Font selection
  - Effect modes
  - Effect intensity
- Audio Controls
  - Audio file selection
  - Volume controls
  - Playback state
- Launch/Display
  - Overlay window creation
  - Display selection
  - Window management
- Dev Tools
  - Virtual toy creation
  - Virtual toy removal
  - Intensity control
  - Multiple toy handling

## Writing Tests

### UI Test Guidelines
1. Use `QTest.qWait()` after UI operations to ensure state updates
2. Clean up windows and overlays properly
3. Use proper widget hierarchy for finding controls
4. Handle async operations with pytest-asyncio

### Virtual Device Test Guidelines
1. Clean up connections and servers
2. Use appropriate timeouts for operations
3. Handle async device discovery properly
4. Verify device state after commands

### Common Issues
1. **Window Cleanup**: Always ensure windows are properly closed and deleted
2. **Async Operations**: Use proper await/async patterns
3. **Widget Finding**: Navigate widget hierarchy correctly
4. **Test Independence**: Each test should work in isolation
- Connection handling
- Command processing
- State management
- Error simulation

### 5. UI Component Tests
- Launcher functionality
- Device page operation
- Settings persistence
- Dev tools operation

## Writing New Tests

### Test Structure
```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_feature():
    # Setup
    server = ButtplugServer(port=12345)
    await server.start()
    
    try:
        # Test steps
        result = await server.some_operation()
        assert result == expected_value
    finally:
        # Cleanup
        await server.stop()
```

### Test Decorators
- `@pytest.mark.asyncio`: For async tests
- `@pytest.mark.timeout(seconds)`: Add timeout
- `@pytest.mark.parametrize`: Test multiple values

## CI/CD Integration
Tests are automatically run on:
- Pull requests
- Main branch commits
- Release tags

## Common Test Issues
1. Async Test Failures
   - Ensure proper cleanup
   - Check for event loop conflicts
   - Verify timeout settings

2. Device Connection Issues
   - Mock external services
   - Use virtual devices
   - Handle timeouts properly

3. UI Test Problems
   - Use proper Qt test fixtures
   - Handle window management
   - Clean up resources
