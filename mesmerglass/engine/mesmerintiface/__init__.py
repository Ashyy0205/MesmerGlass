"""MesmerIntiface - Pure Python Bluetooth Device Control

A Python implementation of core Intiface functionality, providing real Bluetooth
device discovery and control without requiring Rust dependencies.

Based on the Buttplug protocol and Intiface Central architecture, this module
implements the essential device control features needed for MesmerGlass.
"""

from .bluetooth_scanner import BluetoothDeviceScanner
from .device_protocols import DeviceProtocolManager, LovenseProtocol, WeVibeProtocol
from .mesmer_server import MesmerIntifaceServer
from .device_database import DeviceDatabase

__all__ = [
    'BluetoothDeviceScanner',
    'DeviceProtocolManager', 
    'LovenseProtocol',
    'WeVibeProtocol',
    'MesmerIntifaceServer',
    'DeviceDatabase'
]

__version__ = "1.0.0"
