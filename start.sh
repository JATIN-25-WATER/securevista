#!/usr/bin/env bash
# One-command local/offline startup for the Campus CCTV Feed Analyzer.
# See start.ps1 for the Windows/PowerShell equivalent with the same behavior.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend/app"
VENV_PY="$BACKEND/.venv/bin/python"
REBUILD=false
[[ "${1:-}" == "--rebuild" ]] && REBUILD=true

echo "== Campus CCTV Feed Analyzer -- startup =="

if [[ ! -x "$VENV_PY" ]]; then
  echo "Creating backend virtual environment..."
  python3 -m venv "$BACKEND/.venv"
  "$VENV_PY" -m pip install --upgrade pip -q

  echo "Installing PyTorch (trying CUDA build first, falling back to CPU)..."
  if ! "$VENV_PY" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126; then
    echo "CUDA build unavailable, installing CPU-only PyTorch instead."
    "$VENV_PY" -m pip install torch torchvision
  fi

  echo "Installing remaining backend dependencies..."
  "$VENV_PY" -m pip install -r "$BACKEND/requirements.txt"
fi

DIST_DIR="$FRONTEND/dist"
if [[ "$REBUILD" == true || ! -d "$DIST_DIR" ]]; then
  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    echo "Installing frontend dependencies..."
    (cd "$FRONTEND" && npm install)
  fi
  echo "Building frontend..."
  (cd "$FRONTEND" && npm run build)
fi

echo "Seeding database (idempotent)..."
(cd "$BACKEND" && "$VENV_PY" seed.py)

echo "Starting server on http://localhost:8000 ..."
( sleep 3 && (xdg-open http://localhost:8000/login 2>/dev/null || open http://localhost:8000/login 2>/dev/null || true) ) &

cd "$BACKEND"
exec "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
