# BLE UUID Inspector

The BLE UUID Inspector is a developer tool for discovering the full set of GATT Services and Characteristics a Bluetooth LE device exposes. Use it when:

- Adding support for a new toy / protocol variant.
- Verifying alternative ("alt") service UUID mappings (e.g., Lovense 5a30 vs 5230 variants).
- Capturing a machine‑readable snapshot to open an issue or contribute a PR.

## Location
`mesmerglass/devtools/ble_inspect.py`

Run it inside the project virtual environment.

## Basic Usage
```powershell
# Interactive scan (default 5s) then choose device
python -m mesmerglass.devtools.ble_inspect

# Longer scan window (e.g. devices with slow advertising interval)
python -m mesmerglass.devtools.ble_inspect --scan-seconds 10
```

After the scan finishes you will see a numbered list like:
```
Discovered 6 devices:
[1] LVS-Hush      addr=88:1A:14:38:08:D0  RSSI=-54 uuids=3
[2] LVS-R01       addr=6C:FD:22:63:BE:F7  RSSI=-47 uuids=2
[3] Unknown       addr=12:34:56:78:9A:BC  RSSI=-80 uuids=0
...
Select device # to inspect (or blank to quit):
```
Enter the number to get a structured service dump.

## Direct Address Mode
If you already know the address (from OS / earlier scan):
```powershell
python -m mesmerglass.devtools.ble_inspect --address 6C:FD:22:63:BE:F7
```

## JSON Output
Produce machine‑readable JSON (ideal for attaching to an issue/PR):
```powershell
python -m mesmerglass.devtools.ble_inspect --address 6C:FD:22:63:BE:F7 --json > diamo.json
```

Example JSON excerpt:
```json
{
  "address": "6C:FD:22:63:BE:F7",
  "name": "LVS-R01",
  "services": [
    {
      "service_uuid": "52300001-0023-4bd4-bbd5-a6920e4c5653",
      "characteristics": [
        {"uuid": "52300002-0023-4bd4-bbd5-a6920e4c5653", "properties": ["write","write-without-response"], "descriptors": []},
        {"uuid": "52300003-0023-4bd4-bbd5-a6920e4c5653", "properties": ["notify"], "descriptors": []}
      ]
    }
  ]
}
```

## Active Scan (Optional)
Some adapters / environments benefit from trying an active scan:
```powershell
python -m mesmerglass.devtools.ble_inspect --active
# or env var
$env:MESMERGLASS_BLE_ACTIVE_SCAN = "1"; python -m mesmerglass.devtools.ble_inspect
```
If unsupported, it silently falls back to a normal passive scan.

## Tuning Scan Duration
If a device advertises infrequently (power‑saving), increase the window:
```powershell
python -m mesmerglass.devtools.ble_inspect --scan-seconds 12
```

## When to Add a New UUID
Add a new service UUID if it appears consistently for a known vendor but is not in `KNOWN_SERVICE_UUIDS` inside `bluetooth_scanner.py`. For Lovense variants, look for prefixes like `5a30` or `5230`.

## Integration Steps for a New Device
1. Run the inspector and save JSON output.
2. Identify primary control service/characteristics (usually write + notify pair).
3. Update:
   - `bluetooth_scanner.py` `KNOWN_SERVICE_UUIDS` mapping.
   - Relevant protocol class (e.g. `LovenseProtocol`) with new SERVICE / TX / RX UUID constants.
4. (Optional) Add a test case referencing new UUID constants.
5. Run `pytest`.
6. Open a PR attaching the JSON snapshot.

## Reducing Runtime Noise
Normal runtime logs now omit full service dumps unless you explicitly enable:
```powershell
$env:MESMERGLASS_BLE_SERVICE_DUMP = "1"  # restores detailed service+char logging
```
Use the inspector instead of leaving service dumps enabled during regular usage.

## Troubleshooting
| Symptom | Action |
|---------|--------|
| Device not listed | Increase `--scan-seconds`; try `--active`; ensure it’s advertising (wake the device). |
| Address known but inspect fails | Device may have stopped advertising—wake it and retry. |
| Services list empty | Some stacks need a reconnect; rerun command; ensure adapter drivers up to date. |
| Missing notify characteristic | Some devices enable notify only after a specific write; capture baseline then test again after using the main app. |

## Safety & Privacy
The tool only reads public advertisement and GATT metadata—no personal data. Do not share dumps that include proprietary or identifying device names if privacy is a concern.

---
**Next:** After adding UUIDs, run `python -m pytest mesmerglass/tests/test_bluetooth.py` to confirm nothing regressed.
