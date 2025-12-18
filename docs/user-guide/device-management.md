# Device Management

MesmerGlass v1.0 uses **MesmerIntiface** (built-in) for Bluetooth device scanning, connection, and control.
No external Intiface Central is required.

## Connect a device

1. Put your device into pairing mode (manufacturer instructions vary).
2. Open MesmerGlass and go to the **Device** tab.
3. Click **Start Scanning**.
4. Select your device from the list, then click **Connect Selected**.
5. Use **Test Vibration** to verify the connection.

## Tips

- Keep the device close to the Bluetooth adapter for first connection.
- If your device supports multiple connection modes, prefer its Bluetooth LE mode.

## Troubleshooting

- **Nothing appears during scan**:
  - Confirm Bluetooth is enabled in Windows.
  - Re-enter pairing mode (many devices time out).
  - Move the device closer to your PC.

- **Connect fails or immediately disconnects**:
  - Power-cycle the device.
  - Remove/forget the device in Windows Bluetooth settings (if present), then try again.
  - Ensure the device is not already connected to another app/phone.

- **Control feels unresponsive**:
  - Try disconnecting/reconnecting.
  - Reduce other Bluetooth traffic nearby.

## CLI and developer notes

If you’re looking for command-line tools, start with:
- [docs/cli.md](../cli.md)
