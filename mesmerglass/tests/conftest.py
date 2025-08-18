"""pytest configuration file."""

import pytest

pytest_plugins = [
    "pytest_asyncio",
]

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (may take several seconds)"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "bluetooth: marks tests that require Bluetooth functionality"
    )
