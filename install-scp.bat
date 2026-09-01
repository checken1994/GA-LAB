@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title SCP Install

cd /d "%~dp0"

echo.
echo ============================================================
echo   SCP INSTALL - fresh-machine bootstrap (API-Only)
echo ============================================================
echo.

REM --- 1. Python: installer and launcher MUST use the same interpreter. ---
echo [1/7] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Python chua cai hoac khong co trong PATH.
    echo   Cai Python 3.12+ va tick "Add Python to PATH".
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo   [OK] Python !PYVER! ^(system interpreter^)

REM --- 2. Node ---
echo [2/7] Kiem tra Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Node.js chua cai.
    pause
    exit /b 1
)

REM --- 3. Bun ---
echo [3/7] Kiem tra Bun...
bun --version >nul 2>&1
if errorlevel 1 (
    echo   [INFO] Bun chua co - cai qua npm...
    call npm install -g bun
    if errorlevel 1 (
        echo   [FAIL] Khong cai duoc Bun.
        pause
        exit /b 1
    )
)

REM --- 4. Python deps: system Python, same interpreter used by start-scp.bat. ---
echo [4/7] Cai Python dependencies...
python -m pip install -r "%~dp0scp\requirements.txt"
if errorlevel 1 (
    echo   [FAIL] Python dependency install that bai.
    pause
    exit /b 1
)
python -m pip check
if errorlevel 1 (
    echo   [FAIL] pip check phat hien dependency conflict.
    pause
    exit /b 1
)
echo   [OK] Python dependency graph hop le

REM --- 5. Mini-service deps retained for supported auxiliary workflows. ---
echo [5/7] Cai mini-service dependencies...
if exist "%~dp0mini-services\llm-bridge\package.json" (
    pushd "%~dp0mini-services\llm-bridge"
    if not exist "node_modules" call bun install
    if errorlevel 1 (
        popd
        echo   [FAIL] llm-bridge dependency install that bai.
        pause
        exit /b 1
    )
    popd
)
pushd "%~dp0mini-services\loop-scheduler"
if not exist "node_modules" call bun install
if errorlevel 1 (
    popd
    echo   [FAIL] loop-scheduler dependency install that bai.
    pause
    exit /b 1
)
popd

REM --- 6. Dashboard deps ---
echo [6/7] Cai Dashboard dependencies...
pushd "%~dp0dashboard"
call bun install --frozen-lockfile
if errorlevel 1 (
    popd
    echo   [FAIL] Dashboard dependency install that bai.
    pause
    exit /b 1
)
popd

REM --- 7. Secure local environment, create-only. ---
echo [7/7] Tao/kiem tra .env...
if not exist "%~dp0.env.example" (
    echo   [FAIL] Khong tim thay root .env.example
    pause
    exit /b 1
)
python "%~dp0scripts\bootstrap_local_env.py" --template "%~dp0.env.example" --output "%~dp0.env" --secret-dir "%~dp0.private-secrets"
if errorlevel 1 (
    echo   [FAIL] Khong tao duoc secure .env.
    pause
    exit /b 1
)

REM `python -m scp --help` loads the real .env and executes production_guard,
REM but does not start the server. This makes bootstrap config failure fatal.
pushd "%~dp0"
python -m scp --help >nul
if errorlevel 1 (
    popd
    echo   [FAIL] Boot configuration/production guard khong chap nhan .env.
    echo   Sua .env theo thong bao cua: python -m scp --help
    pause
    exit /b 1
)
popd
echo   [OK] Boot configuration contract hop le

REM --- Runtime data tree MUST live at project root. ---
cd /d "%~dp0"
if not exist "data" mkdir data
if not exist "data\knowledge" mkdir data\knowledge
if not exist "data\backups" mkdir data\backups
if not exist "data\shadow" mkdir data\shadow
if not exist "data\stats" mkdir data\stats
if not exist "data\errors" mkdir data\errors
if not exist "data\archive" mkdir data\archive
if not exist "data\bypasses" mkdir data\bypasses

if not exist "data\ast_diff_cache.json" echo {} > data\ast_diff_cache.json
if not exist "data\callgraph.json" echo {} > data\callgraph.json
if not exist "data\diff_rescan_cache.json" echo {} > data\diff_rescan_cache.json
if not exist "data\llm_fix_cache.json" echo {} > data\llm_fix_cache.json
if not exist "data\rollback_tokens.json" echo {} > data\rollback_tokens.json
if not exist "data\speculative_cache.json" echo {} > data\speculative_cache.json
if not exist "data\audit_bugs.jsonl" type nul > data\audit_bugs.jsonl
if not exist "data\deep_audit_results.jsonl" type nul > data\deep_audit_results.jsonl
if not exist "data\evolution_audit.jsonl" type nul > data\evolution_audit.jsonl
if not exist "data\permission_requests.jsonl" type nul > data\permission_requests.jsonl
if not exist "data\policy_appeals.jsonl" type nul > data\policy_appeals.jsonl
if not exist "data\policy_blocks.jsonl" type nul > data\policy_blocks.jsonl
if not exist "data\regression_watch.jsonl" type nul > data\regression_watch.jsonl

echo.
echo ============================================================
echo   [DONE] INSTALL HOAN TAT - bootstrap contract da verify
 echo ============================================================
echo.
echo   De dung OpenRouter: dien OPENROUTER_API_KEY trong .env.
echo   Host provider phai nam trong SCP_LLM_EGRESS_ALLOWLIST.
echo   Sau do chay start-scp.bat.
echo.
pause >nul
