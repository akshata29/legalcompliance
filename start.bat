@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   Legal Compliance App ^| EU Securities Compliance Tool
echo ============================================================
echo.

:: ─── Preflight: require .env ─────────────────────────────────────────────────
if not exist "%~dp0.env" (
    echo [ERROR] .env file not found.
    echo         Copy .env.example to .env and fill in your values.
    echo.
    pause
    exit /b 1
)

:: ─── Backend ─────────────────────────────────────────────────────────────────
echo [1/2] Preparing Python backend...
cd /d "%~dp0backend"

if not exist ".venv" (
    echo   Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Is Python 3.11+ installed?
        pause & exit /b 1
    )
)

echo   Installing / verifying dependencies...
.venv\Scripts\python.exe -m pip install -q --upgrade pip
.venv\Scripts\pip.exe install -q -r requirements.txt

echo   Starting FastAPI backend on http://localhost:8000 ...
start "Legal Compliance -- Backend" cmd /k ".venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --reload"

:: ─── Frontend ─────────────────────────────────────────────────────────────────
echo.
echo [2/2] Preparing React frontend...
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo   Installing npm packages ^(first run, may take a minute^)...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Is Node.js 18+ installed?
        pause & exit /b 1
    )
)

echo   Starting Vite dev server on http://localhost:3000 ...
start "Legal Compliance -- Frontend" cmd /k "npm run dev"

:: ─── Done ─────────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Backend  ^>  http://localhost:8000
echo   Frontend ^>  http://localhost:3000
echo   API Docs ^>  http://localhost:8000/docs
echo ============================================================
echo   Both servers are starting in separate windows.
echo   Press any key to close this launcher.
echo ============================================================
pause >nul
