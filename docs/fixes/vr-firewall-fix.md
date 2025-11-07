# VR Connection Troubleshooting - Firewall Fix

## Problem
**VR client shows blue screen (waiting for connection)**  
**Server never receives UDP discovery packets from VR headset**

## Root Cause
Windows Firewall is blocking incoming UDP packets on port 8766 (discovery) and possibly TCP on port 8765 (streaming).

## Evidence
- ✅ VR client broadcasting discovery every 3 seconds: `MESMERGLASS_VR_CLIENT:Pacific:8765`
- ✅ Server listening on port 8766 (UDP) and 8765 (TCP)
- ✅ Both devices on same network (192.168.1.x)
- ❌ Server logs show **NO** discovery packets received
- ❌ VR headset shows blue screen (waiting)

## Solution: Add Firewall Rules

### Step 1: Run Firewall Setup Script as Administrator

1. **Close all terminals**
2. **Right-click PowerShell** → Select **"Run as Administrator"**
3. Run these commands:
   ```powershell
   cd C:\Users\Ash\Desktop\MesmerGlass
   .\add_firewall_rules.ps1
   ```

This will create two firewall rules:
- **UDP port 8766**: Allow VR discovery packets (inbound)
- **TCP port 8765**: Allow VR streaming connections (inbound)

### Step 2: Test VR Connection

After adding firewall rules, test the connection:

```powershell
# Start VR test server (60 seconds)
.\.venv\Scripts\python.exe -m mesmerglass vr-test --pattern checkerboard --duration 60
```

In another terminal (or while server is running):
```powershell
# Restart VR app
$env:PATH += ";C:\Users\$env:USERNAME\AppData\Local\Android\Sdk\platform-tools"
adb shell am force-stop com.hypnotic.vrreceiver
adb shell am start -n com.hypnotic.vrreceiver/.MainActivity
```

### Expected Results AFTER Firewall Fix

**Server logs should show:**
```
[INFO] 🔍 Discovery service started on port 8766
[INFO] 📡 Listening for VR headsets...
[INFO] 🎮 VR STREAMING SERVER STARTED
[INFO] 🎯 Discovered VR headset: 192.168.1.223 (Pacific)
[INFO] ✅ Client connected from 192.168.1.223
```

**VR headset should show:**
- Checkerboard pattern (black and white squares)
- NO MORE blue "waiting for connection" screen

**VR client logs should show:**
```
Found MesmerGlass server at [SERVER_IP]
Connected to TCP stream on port 8765
```

## Verification Commands

### Check if firewall rules exist:
```powershell
Get-NetFirewallRule -DisplayName "MesmerGlass*" | Select-Object DisplayName, Enabled, Direction, Action | Format-Table -AutoSize
```

### Check if server is listening on ports:
```powershell
# While vr-test is running, check in another terminal:
Get-NetUDPEndpoint | Where-Object {$_.LocalPort -eq 8766}
Get-NetTCPConnection | Where-Object {$_.LocalPort -eq 8765 -and $_.State -eq "Listen"}
```

### Check VR client logs:
```powershell
$env:PATH += ";C:\Users\$env:USERNAME\AppData\Local\Android\Sdk\platform-tools"
adb logcat -d | Select-String "Found MesmerGlass|Connected|TCP stream" | Select-Object -Last 10
```

## Manual Firewall Rules (Alternative Method)

If the script doesn't work, add rules manually:

### Windows Defender Firewall with Advanced Security:
1. Press `Win + R`, type `wf.msc`, press Enter
2. Click **"Inbound Rules"** → **"New Rule..."**
3. Rule Type: **Port** → Next
4. Protocol: **UDP**, Specific local ports: **8766** → Next
5. Action: **Allow the connection** → Next
6. Profile: Check **All** (Domain, Private, Public) → Next
7. Name: `MesmerGlass VR Discovery (UDP 8766)` → Finish
8. **Repeat for TCP 8765** (MesmerGlass VR Streaming)

## Still Not Working?

### Check network interface binding:
Server binds to `0.0.0.0:8766` which should listen on all interfaces. Verify with:
```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*"}
```

Make sure `192.168.1.154` (Ethernet) is active.

### Test UDP connectivity:
From VR headset (via adb shell):
```bash
# Test if server is reachable
adb shell ping -c 3 192.168.1.154

# Test if UDP port is open (requires nc/netcat on Android)
adb shell echo "test" | nc -u 192.168.1.154 8766
```

### Disable Windows Firewall temporarily (TEST ONLY):
```powershell
# ONLY for testing - re-enable after!
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False

# Re-enable after testing
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
```

If connection works with firewall disabled, you **definitely** need the firewall rules.

## Next Steps After Connection Works

Once you see the checkerboard pattern in VR:
1. Try live visual streaming:
   ```powershell
   .\.venv\Scripts\python.exe -m mesmerglass vr-stream --intensity 0.75 --fps 30
   ```
2. Verify spiral and images appear in VR
3. Test with different patterns and intensities

## Technical Details

**Discovery Protocol:**
- VR client broadcasts UDP packet to `255.255.255.255:8766` (broadcast address)
- Message format: `MESMERGLASS_VR_CLIENT:<device_name>:<tcp_port>`
- Server receives packet, extracts client IP and port
- Server initiates TCP connection to client

**Why Firewall Blocks It:**
- Windows Firewall blocks **all unsolicited incoming connections** by default
- UDP broadcast from unknown IP (192.168.1.223) → **BLOCKED**
- Python.exe not in firewall exceptions → **BLOCKED**
- Need explicit inbound rule for UDP 8766 → **MUST ADD**

**Why This Worked on Other Systems:**
- Some systems have "Public network" firewall disabled
- Some antivirus/firewalls auto-prompt for Python apps
- Corporate networks may have different policies
- This is a fresh Windows install or strict firewall config
