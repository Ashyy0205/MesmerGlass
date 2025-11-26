# Development Environment Setup

## Prerequisites

### Required Software
1. Python 3.12+ (64-bit)
2. Git
3. Visual Studio Code (recommended)
4. Intiface Central (for device testing)

### System Requirements
- Windows 10/11
- 8GB RAM recommended
- OpenGL 2.0+ capable GPU
- Multi-monitor setup (for testing)

## Initial Setup

### 1. Clone Repository
```powershell
git clone https://github.com/Ashyy0205/MesmerGlass.git
cd MesmerGlass
```

### 2. Create Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

> **Note:** `psutil` now ships with the main requirements list. If you see `ModuleNotFoundError: psutil` when launching the CLI, rerun `pip install -r requirements.txt` inside the active virtual environment to pull the new dependency.

### 4. IDE Setup

#### VS Code
1. Install Extensions:
   - Python
   - Pylance
   - Python Test Explorer
   - GitLens

2. Configure Settings:
   ```json
   {
     "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
     "python.testing.pytestEnabled": true,
     "python.testing.unittestEnabled": false,
     "editor.formatOnSave": true,
     "python.formatting.provider": "black"
   }
   ```

## Project Structure

```
MesmerGlass/
├── mesmerglass/
│   ├── __init__.py
│   ├── app.py
│   ├── cli.py
│   ├── engine/
│   │   ├── audio.py
│   │   ├── video.py
│   │   └── pulse.py
│   ├── ui/
│   │   ├── launcher.py
│   │   └── pages/
│   └── tests/
├── docs/
├── media/
├── requirements.txt
└── run.py
```

## Development Tools

### Code Quality
```powershell
# Format code
python -m black mesmerglass

# Lint code
python -m flake8 mesmerglass

# Type checking
python -m mypy mesmerglass
```

### Testing
```powershell
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=mesmerglass

# Run specific test
python -m pytest mesmerglass/tests/test_video.py
```

### Documentation
```powershell
# Generate API docs
python -m pdoc --html mesmerglass

# Serve docs locally
python -m http.server -d docs/html
```

## Development Workflow

### 1. Feature Development

#### Branch Creation
```powershell
git checkout -b feature/new-feature
```

#### Implementation Steps
1. Write tests first
2. Implement feature
3. Update documentation
4. Run quality checks
5. Submit PR

### 2. Testing

#### Unit Tests
- Write tests in `tests/` directory
- Follow test naming conventions
- Include edge cases
- Test async code properly

#### Integration Tests
- Test component interactions
- Verify UI behavior
- Check device communication
- Test multi-monitor scenarios

### 3. Documentation

#### Code Documentation
- Use docstrings
- Document parameters
- Include examples
- Explain complex logic

#### User Documentation
- Update README.md
- Add feature documentation
- Include screenshots
- Document CLI changes

## Best Practices

### Code Style
1. Follow PEP 8
2. Use type hints
3. Write clear docstrings
4. Keep functions focused

### Testing
1. Write tests first
2. Cover edge cases
3. Mock external services
4. Test async code properly

### Git Workflow
1. Use feature branches
2. Write clear commits
3. Keep PRs focused
4. Update documentation

### Performance
1. Profile code
2. Monitor memory usage
3. Handle cleanup properly
4. Test with real data

## Debugging

### VS Code Debug Configuration
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal"
    },
    {
      "name": "MesmerGlass",
      "type": "python",
      "request": "launch",
      "program": "run.py",
      "args": ["--debug"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Common Issues

#### Import Errors
- Check virtual environment
- Verify PYTHONPATH
- Check package installation

#### Device Connection
- Check Intiface running
- Verify WebSocket port
- Check device paired

#### UI Issues
- Check Qt version
- Verify window flags
- Check event connections

## Deployment

### Building Releases
```powershell
# Create distribution
python setup.py sdist bdist_wheel

# Create installer
python package.py
```

### Testing Release
1. Clean environment test
2. Fresh install test
3. Upgrade test
4. Uninstall test

## Support

### Getting Help
- GitHub Issues
- Documentation
- Dev Discord

### Contributing
- Read CONTRIBUTING.md
- Follow code style
- Include tests
- Update docs

## BLE UUID Inspector

To aid adding new Bluetooth toys, use the inspector tool:

```powershell
python -m mesmerglass.devtools.ble_inspect --scan-seconds 6
```

Interactive mode lists discovered devices and lets you choose one to dump all services & characteristics.

Flags:
- `--address AA:BB:CC:DD:EE:FF` inspect directly (skips interactive list)
- `--json` machine-readable output
- `--scan-seconds N` adjust discovery window (default 5)
- `--active` attempt an active scan (or set `MESMERGLASS_BLE_ACTIVE_SCAN=1`)

Runtime logging of full services is now suppressed unless you set:

```powershell
$env:MESMERGLASS_BLE_SERVICE_DUMP = "1"
```

Add any new service UUIDs you discover to `KNOWN_SERVICE_UUIDS` in `bluetooth_scanner.py` or extend protocol classes.
