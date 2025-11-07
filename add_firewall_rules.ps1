# MesmerGlass VR Firewall Rules Setup
# This script adds Windows Firewall rules to allow VR streaming
# Run this script as Administrator

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "MesmerGlass VR Firewall Rules Setup" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click PowerShell and select 'Run as Administrator', then run:" -ForegroundColor Yellow
    Write-Host "  cd C:\Users\Ash\Desktop\MesmerGlass" -ForegroundColor Yellow
    Write-Host "  .\add_firewall_rules.ps1" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

Write-Host "✅ Running as Administrator" -ForegroundColor Green
Write-Host ""

# Python executable path
$pythonPath = "C:\Users\Ash\Desktop\MesmerGlass\.venv\Scripts\python.exe"

# Check if Python exists
if (-not (Test-Path $pythonPath)) {
    Write-Host "❌ ERROR: Python not found at: $pythonPath" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "Found Python at: $pythonPath" -ForegroundColor Green
Write-Host ""

# Remove existing rules if they exist
Write-Host "Checking for existing MesmerGlass firewall rules..." -ForegroundColor Cyan
$existingRules = Get-NetFirewallRule -DisplayName "MesmerGlass*" -ErrorAction SilentlyContinue
if ($existingRules) {
    Write-Host "Removing existing rules..." -ForegroundColor Yellow
    $existingRules | Remove-NetFirewallRule
    Write-Host "✅ Removed existing rules" -ForegroundColor Green
} else {
    Write-Host "No existing rules found" -ForegroundColor Gray
}
Write-Host ""

# Add UDP rule for discovery (port 5556)
Write-Host "Adding UDP rule for VR discovery (port 5556)..." -ForegroundColor Cyan
try {
    New-NetFirewallRule `
        -DisplayName "MesmerGlass VR Discovery (UDP 5556)" `
        -Description "Allows VR headsets to discover MesmerGlass streaming server via UDP broadcast" `
        -Direction Inbound `
        -Protocol UDP `
        -LocalPort 5556 `
        -Action Allow `
        -Profile Any `
        -Program $pythonPath `
        -Enabled True | Out-Null
    Write-Host "✅ UDP discovery rule added (port 5556)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to add UDP rule: $_" -ForegroundColor Red
}

# Add TCP rule for streaming (port 5555)
Write-Host "Adding TCP rule for VR streaming (port 5555)..." -ForegroundColor Cyan
try {
    New-NetFirewallRule `
        -DisplayName "MesmerGlass VR Streaming (TCP 5555)" `
        -Description "Allows VR headsets to connect to MesmerGlass streaming server via TCP" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort 5555 `
        -Action Allow `
        -Profile Any `
        -Program $pythonPath `
        -Enabled True | Out-Null
    Write-Host "✅ TCP streaming rule added (port 5555)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to add TCP rule: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Firewall Rules Summary" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Display the created rules
Get-NetFirewallRule -DisplayName "MesmerGlass*" | ForEach-Object {
    $rule = $_
    $portFilter = $rule | Get-NetFirewallPortFilter
    Write-Host "Rule: $($rule.DisplayName)" -ForegroundColor Green
    Write-Host "  Direction: $($rule.Direction)" -ForegroundColor Gray
    Write-Host "  Protocol: $($portFilter.Protocol)" -ForegroundColor Gray
    Write-Host "  Port: $($portFilter.LocalPort)" -ForegroundColor Gray
    Write-Host "  Action: $($rule.Action)" -ForegroundColor Gray
    Write-Host "  Enabled: $($rule.Enabled)" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now run the VR test server:" -ForegroundColor Yellow
Write-Host "  .\.venv\Scripts\python.exe -m mesmerglass vr-test --pattern checkerboard --duration 60" -ForegroundColor Yellow
Write-Host ""
pause
