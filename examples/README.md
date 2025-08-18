# MesmerGlass Examples

This directory contains example scripts and demonstrations for MesmerGlass functionality.

## Directory Structure

### `/device_control/`
Examples demonstrating device control and MesmerIntiface functionality:

- **`demo_mesmer_intiface.py`** - Complete demonstration of MesmerIntiface capabilities
- **`basic_device_test.py`** - Basic device scanning and control test

### `/testing/`
Validation and testing scripts:

- **`integration_validation.py`** - Integration tests for MesmerIntiface components

## Running Examples

All examples should be run from the project root directory:

```bash
# Device control demo
python examples/device_control/demo_mesmer_intiface.py

# Basic device testing
python examples/device_control/basic_device_test.py

# Integration validation
python examples/testing/integration_validation.py
```

## Requirements

Make sure you have installed the project dependencies:

```bash
pip install -r requirements.txt
```

For Bluetooth device control, ensure `bleak` is installed and your system supports Bluetooth LE.
