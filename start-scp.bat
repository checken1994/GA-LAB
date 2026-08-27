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

REM --- Check dashboard dependencies ---
if not exist "dashboard\node_modules\next\dist\bin\next" (
    echo [INFO] Dashboard dependencies chua co - dang cai theo bun.lock...
    pushd dashboard
    bun install --frozen-lockfile
    if errorlevel 1 (
        echo [FAIL] Khong cai duoc dashboard dependencies.
        popd
        pause
        exit /b 1
    )
    popd
)

REM --- Check local Ollama dependency (not a Bun llm-bridge child) ---
powershell -NoProfile -NonInteractive -Command "try { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo [FAIL] Ollama khong phan hoi tai 127.0.0.1:11434.
    echo    Khoi dong Ollama roi chay lai launcher.
    pause
    exit /b 1
)

REM --- Build dashboard from current source before any restart ---
pushd dashboard
bun run build
if errorlevel 1 (
    echo [FAIL] Dashboard build that bai - giu nguyen cac service dang chay.
    popd
    pause
    exit /b 1
)
popd

REM --- Ensure data dir exists (Windows fix) ---
if not exist "data" mkdir data

REM --- Stop old instances (Fix 4-d-018: kill by port + window-title, NOT by image name) ---
REM Previously: a global taskkill-by-image-name command killed EVERY
REM   Bun-based process on the system -- including unrelated dev servers,
REM   Discord bots, other Node tools using the Bun runtime. Operator lost
REM   other work.
REM Fix: rely on window-title kill (lines below) + port-based PID kill
REM   (netstat to find PID on ports 11434/3030/8002/3000, then taskkill /pid).
REM   This only kills SCP-owned processes, leaving other Bun apps alone.
echo [0/4] Dung services cu (neu co)...
taskkill /f /fi "WINDOWTITLE eq SCP-LLM-Bridge*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq SCP-Loop-Scheduler*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq SCP-Python*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq SCP-Dashboard*" >nul 2>&1
REM Port 11434 belongs to external Ollama; never kill it from the SCP launcher.
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3030 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8002 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
timeout /t 3 /nobreak >nul

echo.
echo [INFO] Khoi dong 3 child services + Ollama...
echo.

REM --- 1. Ollama (external dependency, port 11434) ---
echo [1/4] Ollama - port 11434 (da kiem tra, khong khoi dong child)

REM --- 2. Loop Scheduler (port 3030) ---
echo [2/4] Loop Scheduler - port 3030
start "SCP-Loop-Scheduler" cmd /k "cd /d %~dp0mini-services\loop-scheduler && set SCP_BASE_URL=http://127.0.0.1:8002 && set SCP_INTERNAL_URL=http://127.0.0.1:8002 && set LOOP_SCHEDULER_URL=http://127.0.0.1:3030 && set LLM_BRIDGE_URL=http://127.0.0.1:11434 && set OLLAMA_HOST=http://127.0.0.1:11434 && set OLLAMA_ENABLED=true && set SCP_LLM_PROVIDER_MODE=ollama_only && set LOOP_LOG_PATH=%~dp0data\loop_runs.jsonl && bun run dev"
timeout /t 1 /nobreak >nul

REM --- 3. SCP Python (port 8002) - run from ROOT (not scp/) so data/ resolves correctly ---
echo [3/4] SCP Python - port 8002 (boot ~60s, vui long doi...)
start "SCP-Python" cmd /k "cd /d %~dp0 && scp\venv\Scripts\python.exe -m scp 8002"

REM --- 4. Dashboard Next.js (port 3000) ---
echo [4/4] Dashboard Next.js - port 3000 (standalone build)
start "SCP-Dashboard" cmd /k "cd /d %~dp0dashboard && set SCP_INTERNAL_URL=http://127.0.0.1:8002 && set LOOP_SCHEDULER_URL=http://127.0.0.1:3030 && set LLM_BRIDGE_URL=http://127.0.0.1:11434 && bun run start"

REM --- Wait for SCP boot ---
echo.
echo [INFO] Doi SCP khoi dong (polling /health, toi da 180s)...
set /a COUNT=0
:waitloop
set /a COUNT+=1
curl -sf --max-time 2 http://127.0.0.1:8002/health >nul 2>&1
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
echo   SCP /health:     http://127.0.0.1:8002/health
echo   Ollama:          http://127.0.0.1:11434/api/tags
echo   Loop Scheduler:  http://127.0.0.1:3030/
echo.
echo   3 cua so child dang chay + Ollama:
echo     - Ollama (external)
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
