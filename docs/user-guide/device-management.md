# Device Management

MesmerGlass supports optional device synchronization via the Buttplug protocol.

In the GUI, MesmerGlass prefers its built-in **MesmerIntiface** server (Bluetooth LE) and starts it automatically.

## GUI usage

1. Open the **Device** tab
2. Click **Scan** (or equivalent) to discover nearby devices
3. Connect/select a device
4. Start a session and verify intensity changes during cues

If MesmerIntiface is unavailable on your machine, MesmerGlass will still run; only device control is affected.

## CLI usage

MesmerGlass exposes a simple “pulse” command for testing:

```powershell
python -m mesmerglass pulse --level 0.5 --duration 500
```

Notes:

- `pulse` is also available as the legacy alias `test`.
- `python run.py ...` also works and forwards to the same CLI.

## Virtual device testing (dev)

For deterministic testing without hardware:

```powershell
# Start a local Buttplug server
python -m mesmerglass server --port 0

# Run a deterministic virtual toy
python -m mesmerglass toy --name "Virtual Test Toy" --port 12345
```

## Troubleshooting

### Device not found

- Ensure the device is in pairing mode
- Ensure Windows Bluetooth is enabled
- Try re-running scan after toggling Bluetooth off/on

### Connection issues / firewall

- Local Buttplug servers use localhost WebSockets; firewall issues are rare
- Wireless VR discovery/streaming uses UDP/5556 + TCP/5555 (separate from device control)
