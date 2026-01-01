[CmdletBinding()]
param(
    [string]$Device = "192.168.1.150:44975",
    [string]$Adb = ""
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$androidRoot = Join-Path $repoRoot "mesmerglass\vr\android-client"

if (-not $Adb) {
    $candidate = Join-Path $repoRoot "platform-tools\adb.exe"
    if (Test-Path $candidate) {
        $Adb = $candidate
    } else {
        $Adb = "adb"
    }
}

Set-Location $androidRoot

Write-Host "== Build debug APK =="
& .\gradlew.bat ":app:assembleDebug" --no-daemon --console=plain -q

Write-Host "== Connect device (best-effort) =="
try {
    & $Adb connect $Device | Out-Host
} catch {
    Write-Warning $_
}

$raw = & $Adb devices
$devLine = ($raw | Select-Object -Skip 1 | Where-Object { $_ -match "\sdevice$" } | Select-Object -First 1)
if (-not $devLine) {
    $raw | Out-Host
    throw "No online adb devices found. Connect a device (USB or adb connect) and retry."
}
$dev = ($devLine -split "\s+")[0]
Write-Host "Using device: $dev"

$apk = Join-Path $androidRoot "app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apk)) {
    throw "APK not found: $apk"
}

Write-Host "== Install =="
& $Adb -s $dev install -r $apk | Out-Host

Write-Host "== Launch =="
& $Adb -s $dev shell monkey -p com.hypnotic.vrreceiver -c android.intent.category.LAUNCHER 1 | Out-Host

Write-Host "Done."
