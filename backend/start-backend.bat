@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   Legal Compliance -- Backend (FastAPI)
echo ============================================================
echo.

:: ─── Require .env in repo root ───────────────────────────────────────────────
if not exist "%~dp0..\env" (
    if not exist "%~dp0..\.env" (
        echo [ERROR] .env file not found at repo root.
        echo         Copy .env.example to .env and fill in your values.
        echo.
        pause & exit /b 1
    )
)

:: ─── Virtual environment ─────────────────────────────────────────────────────
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv. Is Python 3.11+ installed and on PATH?
        pause & exit /b 1
    )
) else (
    echo [1/3] Virtual environment found.
)

:: ─── Dependencies ────────────────────────────────────────────────────────────
echo [2/3] Installing / verifying dependencies...
.venv\Scripts\python.exe -m pip install -q --upgrade pip
.venv\Scripts\pip.exe install -q -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Check requirements.txt and your internet connection.
    pause & exit /b 1
)

:: ─── Launch ──────────────────────────────────────────────────────────────────
echo [3/3] Starting FastAPI on http://localhost:8000 ...
echo.
echo   API Docs ^>  http://localhost:8000/docs
echo   Press Ctrl+C to stop.
echo ============================================================
echo.

.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --reload
