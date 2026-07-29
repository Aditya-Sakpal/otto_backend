# Run the contextual follow-up agent from the backend repo root.
# Usage (from backend/):  .\scripts\run_contextual_follow_up.ps1 --lead-id <uuid>
# Requires: backend venv activated (pip install -r requirements.txt) so structlog, etc. are available.

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:PYTHONPATH = Join-Path $BackendRoot "app\agents"
Set-Location $BackendRoot
python -m contextual_follow_up_agent @args
