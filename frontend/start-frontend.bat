@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   Legal Compliance -- Frontend (React / Vite)
echo ============================================================
echo.

cd /d "%~dp0"

:: ─── Node modules ────────────────────────────────────────────────────────────
if not exist "node_modules" (
    echo [1/2] Installing npm packages ^(first run, may take a minute^)...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Is Node.js 18+ installed and on PATH?
        pause & exit /b 1
    )
) else (
    echo [1/2] node_modules found.
)

:: ─── Launch ──────────────────────────────────────────────────────────────────
echo [2/2] Starting Vite dev server on http://localhost:3000 ...
echo.
echo   App      ^>  http://localhost:3000
echo   API proxy ^> http://localhost:3000/api  ->  http://localhost:8000
echo   Press Ctrl+C to stop.
echo ============================================================
echo.

call npm run dev
