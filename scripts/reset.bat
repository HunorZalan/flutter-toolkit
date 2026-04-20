@echo off
rem flutter-toolkit - reset/restart the running server.
rem Works whether ftk is running as a scheduled task, or started manually.
rem Window stays open at the end so you can see what happened.
setlocal

rem Try the scheduled task first (clean reset)
schtasks /Query /TN "FlutterToolkitServer" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Restarting scheduled task FlutterToolkitServer...
    schtasks /End /TN "FlutterToolkitServer" >nul 2>&1
    timeout /t 1 >nul
    schtasks /Run /TN "FlutterToolkitServer"
    echo Done.
    goto :end
)

rem Fallback: hit the HTTP endpoint (works when the server is running manually)
echo Calling /api/restart...
powershell -NoProfile -Command "try { (Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8742/api/restart').ok } catch { Write-Host 'Server not reachable at 127.0.0.1:8742' }"

:end
echo.
echo Press any key to close this window...
pause >nul
endlocal
