# Run with:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'

function Find-Python {
    $candidates = @('py -3','py','python3','python')
    foreach ($c in $candidates) {
        try {
            & $c --version | Out-Null
            if ($LASTEXITCODE -eq 0 -or $?) { return $c }
        } catch {}
    }
    throw 'Python not found. Install Python 3 and ensure it is on PATH.'
}

$py = Find-Python
Write-Host ('Using Python: ' + $py)

# 1) Create venv if missing
if (-not (Test-Path '.venv')) {
    Write-Host 'Creating virtual environment in .venv...'
    & $py -m venv .venv
} else {
    Write-Host 'Virtual environment (.venv) already exists.'
}

# Path to venv Python
$venvPy = Join-Path '.\.venv\Scripts' 'python.exe'

# 2) Upgrade pip/setuptools/wheel
Write-Host 'Upgrading pip, setuptools, wheel...'
& $venvPy -m pip install --upgrade pip setuptools wheel

# 3) Install requirements.txt if present
if (Test-Path 'requirements.txt') {
    Write-Host 'Installing dependencies from requirements.txt...'
    & $venvPy -m pip install -r requirements.txt
} else {
    Write-Host 'No requirements.txt found — skipping.'
}

# 4) Optional dev requirements
if (Test-Path 'requirements-dev.txt') {
    Write-Host 'Installing development dependencies from requirements-dev.txt...'
    & $venvPy -m pip install -r requirements-dev.txt
}

Write-Host ''
Write-Host '✅ Setup complete.'
Write-Host 'Activate your environment with:'
Write-Host '  .\.venv\Scripts\Activate.ps1'
