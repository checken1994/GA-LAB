@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title SCP Install

cd /d "%~dp0"

echo.
echo ============================================================
echo   SCP INSTALL - Cai dat dependencies (chay 1 lan duy nhat)
echo ============================================================
echo.

REM --- Check Python ---
echo [1/7] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Python chua cai.
    echo   Tai tu https://www.python.org/downloads/
    echo   Khi cai, TICK "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo   [OK] Python !PYVER!

REM --- Check Node ---
echo [2/7] Kiem tra Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Node.js chua cai.
    echo   Tai tu https://nodejs.org/
    echo.
    pause
    exit /b 1
)
for /f %%i in ('node --version 2^>^&1') do set NODEVER=%%i
echo   [OK] Node.js !NODEVER!

REM --- Check Bun ---
echo [3/7] Kiem tra Bun...
bun --version >nul 2>&1
if errorlevel 1 (
    echo   [WARN] Bun chua cai. Dang thu cai qua npm...
    call npm install -g bun
    if errorlevel 1 (
        echo   [FAIL] Khong cai duoc Bun qua npm.
        echo   Cai Node.js truoc: https://nodejs.org/
        echo   Roi chay: npm install -g bun
        echo.
        pause
        exit /b 1
    )
)
for /f %%i in ('bun --version 2^>^&1') do set BUNVER=%%i
echo   [OK] Bun !BUNVER!

REM --- Check venv ---
echo [4/7] Kiem tra Python venv...
cd /d "%~dp0scp"
if not exist "venv\Scripts\python.exe" (
    echo   Dang tao venv...
    python -m venv venv
    if errorlevel 1 (
        echo   [FAIL] Khong tao duoc venv
        echo.
        pause
        exit /b 1
    )
)
echo   [OK] venv da co
call venv\Scripts\activate.bat
echo   [OK] venv activated

REM --- Install Python deps (from scp/requirements.txt) ---
echo [5/7] Cai Python dependencies tu scp\requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo   [FAIL] pip install loi
    echo.
    pause
    exit /b 1
)
echo   [OK] Python deps da cai

REM --- Install LLM Bridge deps ---
echo [6/7] Cai LLM Bridge dependencies (z-ai-web-dev-sdk)...
cd /d "%~dp0mini-services\llm-bridge"
if not exist "node_modules" (
    call bun install
    if errorlevel 1 (
        echo   [FAIL] Loi bun install cho llm-bridge
        echo.
        pause
        exit /b 1
    )
)
echo   [OK] LLM Bridge deps da cai

REM --- Install Loop Scheduler + Dashboard deps ---
echo [7/7] Cai Loop Scheduler + Dashboard dependencies...
cd /d "%~dp0mini-services\loop-scheduler"
if not exist "node_modules" call bun install 2>nul

cd /d "%~dp0dashboard"
if not exist "node_modules" (
    call bun install
    if errorlevel 1 (
        echo   [WARN] Loi bun install dashboard - thu npm install
        call npm install
    )
)
echo   [OK] Dashboard deps da cai

REM --- Setup .env ---
cd /d "%~dp0"
if not exist ".env" (
    if exist "scp\.env.example" (
        copy "scp\.env.example" ".env" >nul
        echo.
        echo [NOTE] Da tao .env tu template.
        echo    Mo .env bang Notepad, dien OPENROUTER_API_KEY
        echo    Lay key tai https://openrouter.ai/keys
    )
)

REM --- Create data/ dirs at PROJECT ROOT (Fix 4-d-014) ---
REM Previously: `cd /d "%~dp0scp" && mkdir data` created the data tree
REM   INSIDE the scp/ sub-folder -- WRONG.
REM   but start-scp.bat runs `python -m scp` from project root, so SCP
REM   looks for `data\` (= .\data\ at cwd, NOT a sub-folder of scp/).
REM   On Windows the data dirs were created in the wrong place and SCP
REM   silently re-created fresh empty ones at the project root,
REM   dropping all installed seed files.
REM
REM Fix: cd to project root (%~dp0) before mkdir, so data\ lands beside
REM   install-scp.bat -- exactly where SCP's cwd-relative reads expect it.
cd /d "%~dp0"
if not exist "data" (
    mkdir data
    echo   [OK] Created data\ at project root (Fix 4-d-014)

    REM Seed cache + audit files at project root data\
    echo {} > data\ast_diff_cache.json
    echo {} > data\callgraph.json
    echo {} > data\diff_rescan_cache.json
    echo {} > data\llm_fix_cache.json
    echo {} > data\rollback_tokens.json
    echo {} > data\speculative_cache.json
    type nul > data\audit_bugs.jsonl
    type nul > data\deep_audit_results.jsonl
    type nul > data\evolution_audit.jsonl
    type nul > data\permission_requests.jsonl
    type nul > data\policy_appeals.jsonl
    type nul > data\policy_blocks.jsonl
    type nul > data\regression_watch.jsonl

    REM Subdirectories referenced by SCP code (storage_manager.py,
    REM domain_store.py, shadow_canary.py, bypass_encrypt.py, judge.py):
    REM   data\knowledge\  - domain-separated KB (DomainKnowledgeStore)
    REM   data\backups\    - DB backups (3-tier: local + GitHub + HF)
    REM   data\shadow\     - shadow-canary temp files (autofix V4)
    REM   data\archive\    - archived data (compressed, > 30 days old)
    REM   data\bypasses\   - attack pattern log (bypass_encrypt.py)
    REM Plus two future-use dirs documented in the install spec:
    REM   data\stats\, data\errors\
    mkdir data\knowledge 2>nul
    mkdir data\backups   2>nul
    mkdir data\shadow     2>nul
    mkdir data\stats      2>nul
    mkdir data\errors     2>nul
    mkdir data\archive    2>nul
    mkdir data\bypasses   2>nul
    echo   [OK] Created data\ subdirs (knowledge, backups, shadow, stats, errors, archive, bypasses)
)

cd /d "%~dp0"
echo.
echo ============================================================
echo   [DONE] INSTALL HOAN TAT!
echo ============================================================
echo.
echo   Buoc tiep theo: chay start-scp.bat de khoi dong SCP
echo.
echo   Nhan phim bat ky de thoat...
pause >nul
