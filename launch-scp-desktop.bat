@echo off
setlocal
cd /d "%~dp0desktop"
if not exist "node_modules\electron\dist\electron.exe" (
  echo [SCP] Chua cai desktop dependencies. Dang chay npm install...
  call npm install
  if errorlevel 1 (
    echo [FAIL] npm install that bai.
    pause
    exit /b 1
  )
)
echo [SCP] Dang khoi dong SCP DNA Desktop - model 1.6...
call npm start
