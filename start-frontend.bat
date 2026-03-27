@echo off
setlocal EnableDelayedExpansion

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
npm run dev
