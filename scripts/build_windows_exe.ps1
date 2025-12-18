param(
    [string]$Version = "1.0.0",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $repoRoot

if (-not $PythonExecutable) {
    $venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
    if (Test-Path $venvPython) {
        $PythonExecutable = $venvPython
    } else {
        $PythonExecutable = "python"
    }
}

if (-not (Get-Command $PythonExecutable -ErrorAction SilentlyContinue)) {
    throw "Python executable '$PythonExecutable' was not found."
}

$distDir = Join-Path $repoRoot "dist"
$pyiWorkDir = Join-Path $repoRoot "build\\pyinstaller"
$specPath = Join-Path $repoRoot "build\\mesmerglass.spec"

if (-not (Test-Path $specPath)) {
    throw "Spec file not found at $specPath"
}

if (Test-Path (Join-Path $distDir "MesmerGlass")) {
    Remove-Item (Join-Path $distDir "MesmerGlass") -Recurse -Force
}
if (Test-Path $pyiWorkDir) {
    Remove-Item $pyiWorkDir -Recurse -Force
}

Write-Host "[1/1] Building MesmerGlass.exe with PyInstaller..." -ForegroundColor Cyan
$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--workpath", $pyiWorkDir,
    "--distpath", $distDir,
    $specPath
)
& $PythonExecutable $pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$appDir = Join-Path $distDir "MesmerGlass"
$exePath = Join-Path $appDir "MesmerGlass.exe"
if (Test-Path $exePath) {
    Write-Host "MesmerGlass.exe created at $exePath" -ForegroundColor Green
} else {
    Write-Warning "Build succeeded but MesmerGlass.exe was not found."
}
