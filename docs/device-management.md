# Device Management

## Overview
MesmerGlass supports device scanning and selection through both UI and CLI interfaces.

## Features
- Device discovery and scanning
- Device selection and control
- Real-time status monitoring
- Virtual device support for testing

## Usage

### GUI Mode
1. Enable device sync in the "Device sync" section
2. Click "Scan for devices" to search
3. Use "Select device" to choose active device
4. Monitor status in the UI

### CLI Mode
```powershell
# Start server
python run.py server

# Add virtual device
python run.py toy -n "Test Device"

# Test device
python run.py test -i 0.8 -d 2000
```

## Components

### Core Classes
1. DeviceManager
   - Device tracking
   - Selection management
   - State validation

2. ButtplugServer
   - Protocol handling
   - Device discovery
   - Command routing

3. UI Integration
   - DevicePage
   - DeviceSelectionDialog
   - Dev Tools Window

## Implementation Details

### Device Discovery
```python
server = ButtplugServer(port=12345)
server.start()

# Device scanning
await server._send({
    "RequestDeviceList": {"Id": msg_id}
})

# Start scanning
await server._send({
    "StartScanning": {"Id": msg_id}
})
```

### Device Selection
```python
# Select by index
server.select_device(device_index)

# Clear selection
server.select_device(None)
```

## Testing

### Virtual Device Testing
1. Start dev mode (Ctrl+Shift+D)
2. Add virtual devices
3. Test commands and responses
4. Monitor device states

### CLI Testing
```powershell
# Full test sequence
python run.py server
python run.py toy -n "Test Device"
python run.py test -i 0.5 -d 1000
```

## Troubleshooting

### Common Issues
1. Connection Problems
   - Verify server is running
   - Check port settings
   - Review firewall rules

2. Device Not Found
   - Ensure device is powered on
   - Try rescanning
   - Check device compatibility

3. Command Failures
   - Verify device selection
   - Check intensity ranges
   - Monitor dev tools output
