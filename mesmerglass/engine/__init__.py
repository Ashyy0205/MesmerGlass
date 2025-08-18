"""Engine module for MesmerGlass."""

from .buttplug_server import ButtplugServer
from .pulse import PulseEngine, clamp
from .video import VideoStream
from .audio import Audio2
from .device_manager import DeviceManager

# MesmerIntiface - Pure Python device control
try:
    from .mesmerintiface import MesmerIntifaceServer, BluetoothDeviceScanner, DeviceProtocolManager
    MESMER_INTIFACE_AVAILABLE = True
except ImportError:
    MESMER_INTIFACE_AVAILABLE = False
    # Fallback to None for graceful degradation
    MesmerIntifaceServer = None
    BluetoothDeviceScanner = None
    DeviceProtocolManager = None

__all__ = [
    'ButtplugServer', 'PulseEngine', 'clamp', 'VideoStream', 'Audio2', 'DeviceManager',
    'MesmerIntifaceServer', 'BluetoothDeviceScanner', 'DeviceProtocolManager',
    'MESMER_INTIFACE_AVAILABLE'
]
