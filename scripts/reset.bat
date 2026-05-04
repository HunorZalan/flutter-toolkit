@echo off
rem flutter-toolkit - reset/restart the running server.
rem Works whether ftk is running as a scheduled task, or started manually.
rem Window stays open at the end so you can see what happened.
setlocal

set "TASK=FlutterToolkitServer"

rem Try the scheduled task first (clean reset)
schtasks /Query /TN "%TASK%" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Restarting scheduled task %TASK%...
    schtasks /End /TN "%TASK%" >nul 2>&1
    timeout /t 1 /nobreak >nul
    schtasks /Run /TN "%TASK%"
    echo Done.
    goto :end
)

rem Fallback: hit the HTTP restart endpoint
echo No scheduled task found. Calling /api/restart...
powershell -NoProfile -Command ^
    "try { $r=(Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8742/api/restart'); if($r.ok){Write-Host 'Server restarted.'}else{Write-Host 'Restart failed.'} } catch { Write-Host 'Server not reachable at 127.0.0.1:8742' }"

:end
echo.
echo Press any key to close this window...
pause >nul
endlocal
