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
.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --reload
