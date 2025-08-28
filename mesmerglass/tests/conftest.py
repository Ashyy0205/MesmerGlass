"""pytest configuration file."""

import pytest, os, logging, warnings

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

@pytest.fixture(autouse=True, scope="session")
def _silence_servers_and_logs():
    os.environ["MESMERGLASS_NO_SERVER"] = "1"
    logging.getLogger("mesmerglass.server").setLevel(logging.ERROR)
    logging.getLogger("mesmerglass.mesmerintiface").setLevel(logging.ERROR)
    logging.getLogger("asyncio").setLevel(logging.ERROR)
    # Suppress common noisy port reuse warnings
    warnings.filterwarnings("ignore", message=".*only one usage of each socket address.*")
    warnings.filterwarnings("ignore", message=".*address already in use.*")
    yield
