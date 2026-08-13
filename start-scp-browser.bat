@echo off
setlocal EnableExtensions
set "DEBUG_URL=http://127.0.0.1:9222/json/list"
set "BROWSER=C:\Users\check\AppData\Local\CocCoc\Browser\Application\browser.exe"
set "BROWSER_PROCESS=browser"
set "SCP_PROFILE=C:\Users\check\AppData\Local\SCP\CocCocDevToolsProfile"
if defined SCP_BROWSER_PROFILE_DIR set "SCP_PROFILE=%SCP_BROWSER_PROFILE_DIR%"

if not exist "%BROWSER%" goto BROWSER_MISSING

rem Neu da co phien browser noi voi SCP thi dung lai.
powershell -NoProfile -NonInteractive -Command "try { Invoke-WebRequest -UseBasicParsing '%DEBUG_URL%' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto ALREADY_READY

rem Khong the gan remote debugging vao Cốc Cốc dang chay.
powershell -NoProfile -NonInteractive -Command "$p=@(Get-Process -Name '%BROWSER_PROCESS%' -ErrorAction SilentlyContinue); if($p.Count -gt 0){ exit 2 } else { exit 1 }"
if not errorlevel 2 goto START_BROWSER
if /I "%SCP_FORCE_CLOSE_BROWSER%"=="1" goto FORCE_CLOSE

echo Cốc Cốc dang chay nhung chua noi DevTools voi SCP.
echo Hay luu cong viec va dong TOAN BO cua so Cốc Cốc, roi chay lai file nay.
echo Neu chi con tien trinh nen va ban chap thuan dong no, dung:
echo   $env:SCP_FORCE_CLOSE_BROWSER='1'; .\start-scp-browser.bat; Remove-Item Env:SCP_FORCE_CLOSE_BROWSER
endlocal
exit /b 2

:FORCE_CLOSE
echo SCP_FORCE_CLOSE_BROWSER=1: dang dong cac tien trinh Cốc Cốc.
taskkill /F /IM browser.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:START_BROWSER
if not exist "%SCP_PROFILE%" mkdir "%SCP_PROFILE%" >nul 2>&1
echo Dang mo Cốc Cốc voi profile SCP:
echo   %SCP_PROFILE%
echo DevTools: %DEBUG_URL%
start "" "%BROWSER%" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%SCP_PROFILE%" --new-window "https://chatgpt.com/"

timeout /t 5 /nobreak >nul
powershell -NoProfile -NonInteractive -Command "try { Invoke-WebRequest -UseBasicParsing '%DEBUG_URL%' -TimeoutSec 5 | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto DEBUG_READY
echo Khong tao duoc listener DevTools tai %DEBUG_URL%.
echo Hay kiem tra Cốc Cốc da mo cua so moi voi profile SCP.
endlocal
exit /b 3

:ALREADY_READY
echo Da co browser session dang noi voi SCP: %DEBUG_URL%
endlocal
exit /b 0

:BROWSER_MISSING
echo Khong tim thay Cốc Cốc tai:
echo   %BROWSER%
endlocal
exit /b 1

:DEBUG_READY
echo DevTools da san sang: %DEBUG_URL%
endlocal
exit /b 0
