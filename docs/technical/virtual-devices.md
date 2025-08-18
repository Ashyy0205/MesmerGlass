# Virtual Device Testing

## Overview
MesmerGlass includes a comprehensive virtual device testing framework that allows developers to test functionality without physical devices.

## Features
- Virtual toy simulation
- Real-time intensity monitoring
- Connection state tracking
- Command verification

## Usage

### 1. Developer Mode
```powershell
# 1. Start the application
python run.py

# 2. Press Ctrl+Shift+D to open dev tools
# 3. Use "Add Virtual Toy" button to create test devices
# 4. Monitor device status in real-time
```

### 2. CLI Testing
```powershell
# Start a virtual toy
python run.py toy -n "Test Device"

# Test commands
python run.py test -i 0.8 -d 2000
```

## Virtual Toy Properties
- Name customization
- Real-time intensity feedback
- Connection state monitoring
- Command logging

## Device States
1. Disconnected
2. Connecting
3. Connected
4. Active (receiving commands)
5. Error

## Debugging Tips
1. Use dev tools window to monitor device state
2. Check server logs for command processing
3. Verify intensity changes in real-time
4. Test connection handling with multiple devices

## Common Issues
1. Connection Failures
   - Verify server is running
   - Check port configuration
   - Review firewall settings

2. Command Processing
   - Validate command format
   - Check intensity ranges
   - Verify timing parameters

## Example Test Sequence
```powershell
# 1. Start server
python run.py server

# 2. Launch virtual toy
python run.py toy -n "Test Device"

# 3. Run test sequence
python run.py test -i 0.3 -d 1000  # 30% for 1s
python run.py test -i 0.6 -d 500   # 60% for 0.5s
python run.py test -i 1.0 -d 100   # 100% for 0.1s
```
