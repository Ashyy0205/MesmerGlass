# VR Registration Files

This directory contains SteamVR/OpenXR registration files for future use.

## Files

- **`actions.json`** - OpenXR action manifest (input system)
- **`mesmerglass.vrmanifest`** - SteamVR application registration manifest

## Usage

These files are needed when completing VR registration with SteamVR. See:
- `docs/technical/vr-implementation-summary.md` - Overview of VR implementation
- `docs/technical/vr-troubleshooting.md` - Registration instructions

## Status

VR rendering is fully functional but blocked on SteamVR app registration.
The registration process requires:
1. Updating manifest paths to point to these files
2. Registering via SteamVR Settings → Developer → Add Application Manifest
3. Restarting SteamVR

**Current Blocker**: Manual registration attempts have not yet succeeded.
