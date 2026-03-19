# Legal Compliance App startup script (PowerShell)
# Usage: .\start.ps1

$Root = $PSScriptRoot

# ─── Backend ─────────────────────────────────────────────────────────────────
Write-Host "`n[1/2] Starting FastAPI backend..." -ForegroundColor Cyan
Push-Location "$Root\backend"

if (-not (Test-Path ".venv")) {
    Write-Host "  Creating virtual environment..."
    python -m venv .venv
}

Write-Host "  Activating venv and installing deps..."
& ".venv\Scripts\pip.exe" install -q -r requirements.txt

Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "& '.venv\Scripts\uvicorn.exe' main:app --host 0.0.0.0 --port 8000 --reload" `
    -WorkingDirectory "$Root\backend" `
    -WindowStyle Normal

Pop-Location

# ─── Frontend ─────────────────────────────────────────────────────────────────
Write-Host "`n[2/2] Starting React frontend..." -ForegroundColor Cyan
Push-Location "$Root\frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "  Installing npm packages (first run)..."
    npm install
}

Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "npm run dev" `
    -WorkingDirectory "$Root\frontend" `
    -WindowStyle Normal

Pop-Location

Write-Host "`n══════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Backend:   http://localhost:8000"              -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:3000"              -ForegroundColor Green
Write-Host "  API Docs:  http://localhost:8000/docs"         -ForegroundColor Green
Write-Host "══════════════════════════════════════════════`n" -ForegroundColor Green
