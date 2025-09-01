"""BLE Inspection Utility

Interactive (or CLI) tool to list nearby BLE devices and dump raw services/characteristics
for a selected device. Aids adding support for new toys (UUID discovery).

Usage (inside venv):
  python -m mesmerglass.devtools.ble_inspect              # list devices, choose interactively
  python -m mesmerglass.devtools.ble_inspect --address AA:BB:CC:DD:EE:FF  # inspect specific
Optional flags:
  --json  : output machine-readable JSON
  --scan-seconds N : scan duration (default 5)

Environment helpers:
  MESMERGLASS_BLE_ACTIVE_SCAN=1 for active scan attempt.
"""
from __future__ import annotations
import asyncio, json, argparse, sys, os
from dataclasses import asdict
from bleak import BleakScanner, BleakClient

async def scan(seconds: float, active: bool):
    # Simple approach: rely on BleakScanner.discover which blocks for duration
    # Active scan hint only if supported
    if active:
        try:
            return await BleakScanner.discover(scanning_mode="active")  # type: ignore[arg-type]
        except Exception:
            pass
    return await BleakScanner.discover(timeout=seconds)

async def inspect(address: str):
    # Find device first
    discovered = await BleakScanner.discover()
    target = None
    for d in discovered:
        if d.address.lower() == address.lower():
            target = d
            break
    if not target:
        raise SystemExit(f"Device {address} not found in discovery run ({len(discovered)} devices).")
    client = BleakClient(target)
    await client.connect()
    try:
        # Some backends lazily populate services; accessing client.services forces fetch on connect.
        services = client.services
        svc_dump = []
        for svc in services:
            chars = []
            for ch in svc.characteristics:
                chars.append({
                    "uuid": ch.uuid,
                    "properties": list(ch.properties),
                    "descriptors": [d.handle for d in getattr(ch, 'descriptors', [])] if getattr(ch, 'descriptors', []) else []
                })
            svc_dump.append({
                "service_uuid": svc.uuid,
                "characteristics": chars
            })
        return {
            "address": target.address,
            "name": target.name,
            "rssi": getattr(target, 'rssi', None),
            "metadata": getattr(target, 'metadata', {}),
            "services": svc_dump,
        }
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

async def main_async(argv):
    ap = argparse.ArgumentParser(description="BLE device UUID inspector")
    ap.add_argument('--address', '-a', help='Bluetooth address to inspect')
    ap.add_argument('--scan-seconds', type=float, default=5.0, help='Scan duration')
    ap.add_argument('--json', action='store_true', help='Output JSON only')
    ap.add_argument('--active', action='store_true', help='Attempt active scan')
    args = ap.parse_args(argv)

    if not args.address:
        # Perform scan and list devices
        devices = await scan(args.scan_seconds, args.active or os.environ.get('MESMERGLASS_BLE_ACTIVE_SCAN')=='1')
        if not devices:
            print('No BLE devices discovered.')
            return 1
        print(f"Discovered {len(devices)} devices:\n")
        for idx, d in enumerate(devices, 1):
            uuids = getattr(d, 'metadata', {}).get('uuids') or []
            print(f"[{idx}] {d.name or 'Unknown'}  addr={d.address}  RSSI={getattr(d,'rssi', '?')} uuids={len(uuids)}")
        selection = input('\nSelect device # to inspect (or blank to quit): ').strip()
        if not selection:
            return 0
        try:
            sel_idx = int(selection)
            if sel_idx < 1 or sel_idx > len(devices):
                print('Invalid selection.')
                return 1
        except ValueError:
            print('Invalid selection.')
            return 1
        args.address = devices[sel_idx - 1].address

    info = await inspect(args.address)
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"\n=== BLE Device Inspection: {info['name'] or 'Unknown'} ({info['address']}) ===")
        print(f"RSSI: {info['rssi']}")
        print(f"Metadata keys: {list(info['metadata'].keys())}")
        print('\nServices:')
        for svc in info['services']:
            print(f"  Service {svc['service_uuid']}")
            for ch in svc['characteristics']:
                props = ','.join(ch['properties'])
                print(f"    Char {ch['uuid']} props=[{props}] descs={ch['descriptors']}")
        print('\nTip: Add new service UUIDs to KNOWN_SERVICE_UUIDS or protocol class as needed.')
    return 0

def main():
    try:
        rc = asyncio.run(main_async(sys.argv[1:]))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)

if __name__ == '__main__':
    main()
