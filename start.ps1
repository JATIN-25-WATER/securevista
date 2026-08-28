#requires -Version 5.1
<#
  One-command local/offline startup for the Campus CCTV Feed Analyzer.

  - Creates the backend virtualenv and installs dependencies on first run
    (CUDA-enabled torch if available, falling back to CPU automatically).
  - Installs and builds the frontend on first run (or when -Rebuild is passed).
  - Seeds the database with demo users/cameras/zones/SOPs if empty.
  - Starts the single backend process, which also serves the built frontend,
    so the whole system is reachable at one URL.

  After the first run (and after `pip install`/`npm install` complete once),
  everything runs fully offline.
#>
param(
  [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend\app"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

Write-Host "== Campus CCTV Feed Analyzer -- startup ==" -ForegroundColor Cyan

# --- Backend venv + dependencies -------------------------------------------------
if (-not (Test-Path $venvPython)) {
  Write-Host "Creating backend virtual environment..." -ForegroundColor Yellow
  python -m venv (Join-Path $backend ".venv")

  Write-Host "Installing PyTorch (trying CUDA build first, falling back to CPU)..." -ForegroundColor Yellow
  & $venvPython -m pip install --upgrade pip -q
  & $venvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
  if ($LASTEXITCODE -ne 0) {
    Write-Host "CUDA build unavailable, installing CPU-only PyTorch instead." -ForegroundColor Yellow
    & $venvPython -m pip install torch torchvision
  }

  Write-Host "Installing remaining backend dependencies..." -ForegroundColor Yellow
  & $venvPython -m pip install -r (Join-Path $backend "requirements.txt")
}

# --- Frontend build ----------------------------------------------------------------
$distDir = Join-Path $frontend "dist"
if ($Rebuild -or -not (Test-Path $distDir)) {
  if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location $frontend
    npm install
    Pop-Location
  }
  Write-Host "Building frontend..." -ForegroundColor Yellow
  Push-Location $frontend
  npm run build
  Pop-Location
}

# --- Seed database -------------------------------------------------------------------
Write-Host "Seeding database (idempotent)..." -ForegroundColor Yellow
Push-Location $backend
& $venvPython seed.py
Pop-Location

# --- Launch --------------------------------------------------------------------------
Write-Host "Starting server on http://localhost:8000 ..." -ForegroundColor Green
Start-Job -ScriptBlock {
  Start-Sleep -Seconds 3
  Start-Process "http://localhost:8000/login"
} | Out-Null

Push-Location $backend
& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Pop-Location
