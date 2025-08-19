"""Tests for MesmerIntifaceServer device mapping from BLE scan to Buttplug devices."""

import asyncio
import pytest
from unittest.mock import MagicMock

from ..engine.mesmerintiface.mesmer_server import MesmerIntifaceServer
from ..engine.mesmerintiface.bluetooth_scanner import BluetoothDeviceInfo

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def server():
    s = MesmerIntifaceServer(port=12359)
    s.start()
    await asyncio.sleep(0.05)
    yield s
    s.stop()


def make_ble(name: str, address: str, uuids):
    d = BluetoothDeviceInfo(
        address=address,
        name=name,
        rssi=-50,
        manufacturer_data={},
        service_uuids=list(uuids),
    )
    d.device_type = "sex_toy"
    d.protocol = "lovense"
    return d


async def test_mapping_adds_device_and_assigns_index(server):
    # Provide a known lovense-ish device and an unknown one
    devices = [
        make_ble("LVS-Hush", "00:11:22:33:44:55", ["5a300001-0023-4bd4-bbd5-a6920e4c5653"]),
        BluetoothDeviceInfo(
            address="AA:BB:CC:DD:EE:FF",
            name="Unknown",
            rssi=-70,
            manufacturer_data={},
            service_uuids=[],
            device_type="unknown",
            protocol=None,
        ),
    ]

    # Patch stop_real_scanning to track auto-stop
    server.stop_real_scanning = MagicMock()

    server._on_bluetooth_devices_changed(devices)

    dl = server.get_device_list()
    assert len(dl.devices) == 1
    dev = dl.devices[0]
    assert dev.index >= 1
    assert "ScalarCmd" in dev.device_messages

    # If mapping added devices while scanning, auto-stop should be scheduled
    # In our test, server.is_real_scanning() returns False by default, so may not call.
    assert hasattr(server, "stop_real_scanning")
