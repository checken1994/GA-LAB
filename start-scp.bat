@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title SCP Start

cd /d "%~dp0"

echo.
echo ============================================================
echo   SCP START - Khoi dong toan bo he thong
echo ============================================================
echo.

REM --- Check .env ---
if not exist ".env" (
    echo [FAIL] KHONG TIM THAY .env
    echo    Chay install-scp.bat truoc, hoac copy .env.example thanh .env
    echo    Dien OPENROUTER_API_KEY trong .env
    echo.
    pause
    exit /b 1
)

REM --- Check venv ---
if not exist "scp\venv\Scripts\python.exe" (
    echo [FAIL] venv chua tao. Chay install-scp.bat truoc.
    echo.
    pause
    exit /b 1
)

REM --- Check deps installed ---
if not exist "mini-services\llm-bridge\node_modules" (
    echo [FAIL] Dependencies chua cai. Chay install-scp.bat truoc.
    echo.
    pause
    exit /b 1
)

REM --- Ensure data dir exists (Windows fix) ---
if not exist "data" mkdir data

REM --- Stop old instances (Fix 4-d-018: kill by port + window-title, NOT by image name) ---
REM Previously: a global taskkill-by-image-name command killed EVERY
REM   Bun-based process on the system -- including unrelated dev servers,
REM   Discord bots, other Node tools using the Bun runtime. Operator lost
REM   other work.
REM Fix: rely on window-title kill (lines below) + port-based PID kill
REM   (netstat to find PID on ports 11434/3030/8000/3000, then taskkill /pid).
REM   This only kills SCP-owned processes, leaving other Bun apps alone.
echo [0/4] Dung services cu (neu co)...
taskkill /f /fi "WINDOWTITLE eq SCP-LLM-Bridge*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq SCP-Loop-Scheduler*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq SCP-Python*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq SCP-Dashboard*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":11434 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3030 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
timeout /t 3 /nobreak >nul

echo.
echo [INFO] Khoi dong 4 services...
echo.

REM --- 1. LLM Bridge (port 11434) ---
echo [1/4] LLM Bridge - port 11434
start "SCP-LLM-Bridge" cmd /k "cd /d %~dp0mini-services\llm-bridge && bun run dev"
timeout /t 3 /nobreak >nul

REM --- 2. Loop Scheduler (port 3030) ---
echo [2/4] Loop Scheduler - port 3030
start "SCP-Loop-Scheduler" cmd /k "cd /d %~dp0mini-services\loop-scheduler && set LOOP_LOG_PATH=%~dp0data\loop_runs.jsonl && bun run dev"
timeout /t 1 /nobreak >nul

REM --- 3. SCP Python (port 8000) - run from ROOT (not scp/) so data/ resolves correctly ---
echo [3/4] SCP Python - port 8000 (boot ~60s, vui long doi...)
start "SCP-Python" cmd /k "cd /d %~dp0 && scp\venv\Scripts\python.exe -m scp 8000"

REM --- 4. Dashboard Next.js (port 3000) ---
echo [4/4] Dashboard Next.js - port 3000
start "SCP-Dashboard" cmd /k "cd /d %~dp0dashboard && bun run dev"

REM --- Wait for SCP boot ---
echo.
echo [INFO] Doi SCP khoi dong (polling /health, toi da 180s)...
set /a COUNT=0
:waitloop
set /a COUNT+=1
curl -sf --max-time 2 http://127.0.0.1:8000/health >nul 2>&1
if not errorlevel 1 (
    echo [OK] SCP san sang sau ~!COUNT! giay
    goto :ready
)
if !COUNT! geq 90 (
    echo [WARN] SCP chua san sang sau 180s - kiem tra cua so SCP-Python
    goto :ready
)
timeout /t 2 /nobreak >nul
goto :waitloop

:ready
echo.
echo ============================================================
echo   [DONE] SCP SYSTEM DANG CHAY!
echo ============================================================
echo.
echo   Dashboard:       http://localhost:3000
echo   SCP /health:     http://127.0.0.1:8000/health
echo   LLM Bridge:      http://127.0.0.1:11434/api/tags
echo   Loop Scheduler:  http://127.0.0.1:3030/
echo.
echo   4 cua so dang chay:
echo     - SCP-LLM-Bridge
echo     - SCP-Loop-Scheduler
echo     - SCP-Python
echo     - SCP-Dashboard
echo.
echo   Dung tat ca: chay stop-scp.bat
echo.

REM --- Try to open browser ---
start http://localhost:3000

echo.
echo Nhan phim bat ky de thoat script nay (services van chay)
pause >nul
