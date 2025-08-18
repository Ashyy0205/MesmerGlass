# Device Control Documentation

## Overview
The device control system manages communication with external devices using the Buttplug protocol over WebSocket connections.

## Components

### 1. PulseEngine
```python
from mesmerglass.engine.pulse import PulseEngine

# Example usage
engine = PulseEngine()
await engine.connect("ws://127.0.0.1:12345")
await engine.send_scalar(0.75)  # 75% intensity
```

### 2. Connection Management

#### WebSocket Client
```python
class ButtplugClient:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.devices = []
        
    async def connect(self, url: str):
        """Establish WebSocket connection"""
        self.ws = await websockets.connect(url)
        await self._handshake()
```

#### Device Discovery
```python
async def scan_for_devices(self):
    """Start device scanning"""
    await self.ws.send({
        "type": "StartScanning"
    })
    
async def handle_device_added(self, msg):
    """Process new device discovery"""
    device = Device(msg["device"])
    self.devices.append(device)
```

### 3. Command Protocol

#### Message Types
```python
class MessageType:
    HANDSHAKE = "RequestServerInfo"
    SCAN = "StartScanning"
    STOP_SCAN = "StopScanning"
    SCALAR = "ScalarCmd"
    VIBRATE = "VibrateCmd"
```

#### Command Handling
```python
async def send_command(self, device_id: int, cmd_type: str, params: dict):
    """Send command to specific device"""
    message = {
        "type": cmd_type,
        "device_id": device_id,
        **params
    }
    await self.ws.send(json.dumps(message))
```

## Features

### 1. Device Management

#### Connection States
- Disconnected
- Connecting
- Connected
- Scanning
- Error

#### Device Types
- Scalar devices
- Rotary devices
- Linear devices
- Custom protocols

### 2. Command Types

#### Basic Commands
```python
async def vibrate(self, intensity: float):
    """Send vibration command"""
    await self.send_scalar(intensity)

async def pulse(self, duration_ms: int):
    """Send timed pulse"""
    await self.send_scalar(1.0)
    await asyncio.sleep(duration_ms / 1000.0)
    await self.send_scalar(0.0)
```

#### Pattern Support
```python
class Pattern:
    def __init__(self, steps: List[Tuple[float, float]]):
        """Initialize pattern with [(intensity, duration), ...]"""
        self.steps = steps
        
    async def play(self, engine: PulseEngine):
        """Execute pattern"""
        for intensity, duration in self.steps:
            await engine.send_scalar(intensity)
            await asyncio.sleep(duration)
```

### 3. Safety Features

#### Connection Management
```python
def ensure_safe_disconnect(self):
    """Ensure clean disconnection"""
    try:
        # Zero all outputs
        await self.send_scalar(0.0)
        # Close connection
        await self.ws.close()
    except:
        pass  # Already disconnected
```

#### Error Recovery
```python
async def handle_error(self, error):
    """Handle communication errors"""
    if isinstance(error, ConnectionError):
        await self.reconnect()
    elif isinstance(error, CommandError):
        await self.reset_device()
```

## API Reference

### PulseEngine Class
```python
class PulseEngine:
    def __init__(self):
        """Initialize pulse engine"""
        
    async def connect(self, url: str):
        """Connect to WebSocket server"""
        
    async def send_scalar(self, level: float):
        """Send scalar command"""
        
    async def start_pattern(self, pattern: Pattern):
        """Start pattern playback"""
        
    async def stop(self):
        """Stop all activity"""
```

### Pattern Class
```python
class Pattern:
    def __init__(self, steps: List[Tuple[float, float]]):
        """Initialize pattern"""
        
    async def play(self, engine: PulseEngine):
        """Execute pattern"""
        
    def loop(self, count: int):
        """Create looped pattern"""
```

## Testing

### Unit Tests
```python
async def test_connection():
    engine = PulseEngine()
    connected = await engine.connect("ws://localhost:12345")
    assert connected
    
async def test_scalar_command():
    engine = PulseEngine()
    await engine.connect("ws://localhost:12345")
    response = await engine.send_scalar(0.5)
    assert response["status"] == "ok"
```

### Integration Tests
- Device discovery
- Command execution
- Pattern playback
- Error handling

## Best Practices

### Connection Management
1. Always zero outputs before disconnect
2. Implement reconnection logic
3. Handle timeouts gracefully
4. Validate server responses

### Command Timing
1. Respect rate limits
2. Buffer commands appropriately
3. Handle latency variations
4. Implement command queuing

### Error Handling
1. Validate all inputs
2. Handle connection drops
3. Implement safe states
4. Log all errors

### Security
1. Validate server certificates
2. Use secure WebSocket when available
3. Implement command validation
4. Handle malformed responses
