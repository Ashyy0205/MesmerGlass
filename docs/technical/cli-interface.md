# CLI Interface

## Command Overview
MesmerGlass provides a comprehensive CLI interface for testing, development, and automation.

## Available Commands

### 1. GUI Mode
```powershell
# Start the graphical interface (default)
python run.py
# or explicitly
python run.py gui
```

### 2. Test Mode
```powershell
# Test device with custom intensity and duration
python run.py test -i 0.8 -d 2000

# Parameters:
# -i, --intensity : Float value 0.0-1.0 (default: 0.5)
# -d, --duration  : Duration in milliseconds (default: 1000)
# -p, --port      : Server port (default: 12345)
```

### 3. Virtual Toy Mode
```powershell
# Start a virtual toy for testing
python run.py toy -n "Test Device" -p 12345

# Parameters:
# -n, --name : Device name (default: "CLI Virtual Toy")
# -p, --port : Server port (default: 12345)
```

### 4. Server Mode
```powershell
# Start a standalone Buttplug server
python run.py server -p 12345

# Parameters:
# -p, --port : Server port (default: 12345)
```

## Common Use Cases

### Testing Device Integration
```powershell
# 1. Start a server
python run.py server

# 2. Start a virtual toy (new terminal)
python run.py toy -n "Test Device"

# 3. Run test commands (another terminal)
python run.py test -i 0.5 -d 1000
```

### Development Testing
```powershell
# 1. Start GUI
python run.py

# 2. Toggle dev mode with Ctrl+Shift+D
# 3. Add virtual toys through dev tools window
```

## Exit Codes
- 0: Successful execution
- 1: General error
- 2: Configuration error
- 3: Connection error
