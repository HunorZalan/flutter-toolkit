@echo off
rem flutter-toolkit uninstaller (Windows).
rem Usage:  scripts\uninstall.bat   (auto-elevates if needed; window stays open)
setlocal EnableDelayedExpansion
pushd "%~dp0\.."
set "FAIL_RC=0"
set "SCRIPT_DIR=%~dp0"

rem ---- Admin self-elevate (needed to remove the scheduled task) ---------
net session >nul 2>&1
if not "!errorlevel!"=="0" (
    echo Uninstall needs administrator privileges.
    echo A Windows UAC prompt is about to appear - click Yes to continue.
    echo.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    echo Elevated uninstaller launched in a new window.
    echo.
    echo Press any key to close this window...
    pause >nul
    popd & endlocal & exit /b 0
)

echo.
echo === flutter-toolkit uninstaller ===
echo.

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    echo [ERROR] Python not found.
    set "FAIL_RC=1" & goto :end
)

echo [1/4] Stopping scheduled-task service if present...
schtasks /Query /TN "FlutterToolkitServer" >nul 2>&1 && schtasks /End /TN "FlutterToolkitServer" >nul 2>&1
schtasks /Query /TN "FlutterToolkitServer" >nul 2>&1 && schtasks /Delete /TN "FlutterToolkitServer" /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8742 " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/4] Removing flutter-toolkit Python package...
%PY% -m pip uninstall -y flutter-toolkit

for /f "delims=" %%i in ('%PY% -c "import sysconfig;print(sysconfig.get_path('scripts'))"') do set "SCRIPTS=%%i"

echo [3/4] Cleaning Scripts dir from user PATH (if we added it)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$d='!SCRIPTS!'; $p=[Environment]::GetEnvironmentVariable('Path','User'); if ($p) { $np = ($p.Split(';') ^| Where-Object { $_ -and $_ -ne $d }) -join ';'; [Environment]::SetEnvironmentVariable('Path', $np, 'User'); Write-Host '      Cleaned.' }"

echo [4/4] Registry folder: %USERPROFILE%\.ftk
set /p ANS="      Remove the ftk registry (project list)? [y/N] "
if /I "!ANS!"=="y" (
    if exist "%USERPROFILE%\.ftk" rmdir /s /q "%USERPROFILE%\.ftk"
    echo       Removed.
) else (
    echo       Kept.
)

echo.
echo Done.

:end
popd
echo.
echo Press any key to close this window...
pause >nul
endlocal & exit /b %FAIL_RC%
