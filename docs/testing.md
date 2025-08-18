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
```

### Specific Tests
```powershell
# Test categories
python -m pytest mesmerglass/tests/test_buttplug.py
python -m pytest mesmerglass/tests/test_device_scan.py

# Single test function
python -m pytest mesmerglass/tests/test_buttplug.py::test_server_startup
```

## Test Categories

### 1. Core Server Tests
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
