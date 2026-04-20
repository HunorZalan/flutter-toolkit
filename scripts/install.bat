@echo off
rem =========================================================================
rem  flutter-toolkit - one-shot installer (Windows).
rem
rem  Recommended invocation (from cmd, in your project dir):
rem      cd C:\Users\YOU\my-flutter-app
rem      C:\Users\YOU\flutter-toolkit\scripts\install.bat
rem
rem  Or right-click -> Run as administrator. The script will:
rem    - find your project from cwd, or fall back to the registry's
rem      last-active project, or the only registered project
rem    - auto-elevate via UAC if installing the service requires admin
rem    - install pip package + add to PATH + create scheduled task
rem    - start the service and open http://localhost:8742
rem
rem  The window ALWAYS stays open at the end so you can read the output.
rem =========================================================================
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "TOOLKIT_DIR=%%~fI"
set "FAIL_RC=0"

rem ---- Resolve PROJECT_DIR (arg > cwd > registry) -------------------------
set "PROJECT_DIR="
if not "%~1"=="" (
    if exist "%~1\ftk.yaml" set "PROJECT_DIR=%~1"
)
if not defined PROJECT_DIR (
    if exist "%CD%\ftk.yaml" set "PROJECT_DIR=%CD%"
)

rem ---- Detect Python ------------------------------------------------------
set "PY="
where python  >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    echo [ERROR] No Python 3.10+ found on PATH.
    echo         Install from https://www.python.org/downloads/ and tick
    echo         "Add python.exe to PATH" in the installer.
    set "FAIL_RC=1" & goto :end
)
for /f "tokens=2" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"

rem ---- Registry fallback for project (after Python is known) -------------
if not defined PROJECT_DIR (
    for /f "delims=" %%i in ('%PY% -c "from ftk.projects import get_last_project_id, find_project, list_projects; ps=list_projects(); fb=ps[0] if ps else None; e=find_project(get_last_project_id() or '') or fb; print(e.root if e else '')" 2^>nul') do set "PROJECT_DIR=%%i"
    if defined PROJECT_DIR (
        if not exist "!PROJECT_DIR!\ftk.yaml" set "PROJECT_DIR="
    )
)

echo.
echo === flutter-toolkit installer (Windows) ===
echo Toolkit  : !TOOLKIT_DIR!
echo Python   : !PYVER! ^(%PY%^)
if defined PROJECT_DIR (
    echo Project  : !PROJECT_DIR!
) else (
    echo Project  : ^(none detected - will install package only^)
)
echo.

rem ---- Admin check (only required for the scheduled-task step) ----------
set "IS_ADMIN=0"
net session >nul 2>&1 && set "IS_ADMIN=1"

if defined PROJECT_DIR if "!IS_ADMIN!"=="0" (
    echo Service install requires administrator privileges.
    echo A Windows UAC prompt is about to appear - click Yes to continue.
    echo The elevated installer opens in a new window; you can close this one.
    echo.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '\"!PROJECT_DIR!\"' -Verb RunAs"
    echo.
    echo Press any key to close this window...
    pause >nul
    endlocal & exit /b 0
)

rem ---- 1. Install pip package --------------------------------------------
echo [1/5] Installing flutter-toolkit (with all extras)...
%PY% -m pip install --upgrade pip --quiet 2>nul
pushd "!TOOLKIT_DIR!" >nul
%PY% -m pip install -e ".[all]" --upgrade
set "PIP_RC=!errorlevel!"
popd >nul
if not "!PIP_RC!"=="0" (
    echo [ERROR] pip install failed ^(exit code !PIP_RC!^).
    set "FAIL_RC=1" & goto :end
)

rem ---- 2. PATH -----------------------------------------------------------
for /f "delims=" %%i in ('%PY% -c "import sysconfig;print(sysconfig.get_path('scripts'))"') do set "SCRIPTS_DIR=%%i"
echo [2/5] Scripts dir: !SCRIPTS_DIR!
echo !PATH! | findstr /I /C:"!SCRIPTS_DIR!" >nul
if not "!errorlevel!"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$d='!SCRIPTS_DIR!'; $p=[Environment]::GetEnvironmentVariable('Path','User'); if (-not $p) { $p = '' }; if (-not ($p.Split(';') -contains $d)) { $np = if ($p) { $p.TrimEnd(';') + ';' + $d } else { $d }; [Environment]::SetEnvironmentVariable('Path', $np, 'User'); Write-Host '       Added to user PATH (persistent).' -ForegroundColor Green } else { Write-Host '       Already in user PATH.' }"
) else (
    echo       Already on PATH for this shell.
)

rem ---- 3. Verify ---------------------------------------------------------
echo [3/5] Verifying ftk install...
%PY% -m ftk --version
if not "!errorlevel!"=="0" (
    echo [ERROR] ftk verification failed.
    set "FAIL_RC=1" & goto :end
)

rem ---- 4. Bail out gracefully if no project detected ---------------------
if not defined PROJECT_DIR (
    echo.
    echo === Toolkit installed; no project autostart configured ===
    echo.
    echo To enable autostart for a Flutter project:
    echo   1^) Register the project:
    echo        ftk projects add C:\path\to\my-flutter-app
    echo   2^) Re-run this installer ^(it'll pick up the project automatically^):
    echo        "%SCRIPT_DIR%install.bat"
    echo.
    echo Or just start the server manually any time:
    echo   ftk server
    echo.
    goto :end
)

rem ---- 5. Install scheduled task ----------------------------------------
echo [4/5] Registering project in the ftk registry...
%PY% -m ftk projects add "!PROJECT_DIR!" >nul 2>&1

set "PROJECT_ID="
for /f "delims=" %%i in ('%PY% -c "import sys; from ftk.config import load_config; print(load_config(sys.argv[1]).id)" "!PROJECT_DIR!" 2^>nul') do set "PROJECT_ID=%%i"

set "FTK_EXE=!SCRIPTS_DIR!\ftk.exe"
if not exist "!FTK_EXE!" (
    echo [ERROR] ftk.exe not found at !FTK_EXE!
    echo         Look in !SCRIPTS_DIR! for ftk* and rename if needed.
    set "FAIL_RC=1" & goto :end
)

if not exist "!PROJECT_DIR!\.ftk" mkdir "!PROJECT_DIR!\.ftk"
set "WRAPPER=!PROJECT_DIR!\.ftk\start_server_bg.vbs"
if defined PROJECT_ID (
    > "!WRAPPER!" (
        echo Dim shell
        echo Set shell = CreateObject^("WScript.Shell"^)
        echo shell.CurrentDirectory = "!PROJECT_DIR!"
        echo shell.Run """!FTK_EXE!"" --project !PROJECT_ID! server", 0, False
    )
) else (
    > "!WRAPPER!" (
        echo Dim shell
        echo Set shell = CreateObject^("WScript.Shell"^)
        echo shell.CurrentDirectory = "!PROJECT_DIR!"
        echo shell.Run """!FTK_EXE!"" server", 0, False
    )
)

echo [5/5] Creating scheduled task FlutterToolkitServer...
echo       Launcher : !WRAPPER!

set "TASK=FlutterToolkitServer"
set "XML=%TEMP%\flutter_toolkit_task.xml"
> "!XML!" (
    echo ^<?xml version="1.0" encoding="UTF-16"?^>
    echo ^<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^>
    echo   ^<RegistrationInfo^>^<Description^>flutter-toolkit web UI - http://localhost:8742^</Description^>^</RegistrationInfo^>
    echo   ^<Settings^>
    echo     ^<MultipleInstancesPolicy^>IgnoreNew^</MultipleInstancesPolicy^>
    echo     ^<DisallowStartIfOnBatteries^>false^</DisallowStartIfOnBatteries^>
    echo     ^<StopIfGoingOnBatteries^>false^</StopIfGoingOnBatteries^>
    echo     ^<AllowHardTerminate^>true^</AllowHardTerminate^>
    echo     ^<StartWhenAvailable^>true^</StartWhenAvailable^>
    echo     ^<AllowStartOnDemand^>true^</AllowStartOnDemand^>
    echo     ^<Enabled^>true^</Enabled^>
    echo     ^<ExecutionTimeLimit^>PT0S^</ExecutionTimeLimit^>
    echo     ^<RestartOnFailure^>^<Interval^>PT1M^</Interval^>^<Count^>3^</Count^>^</RestartOnFailure^>
    echo   ^</Settings^>
    echo   ^<Triggers^>^<LogonTrigger^>^<Enabled^>true^</Enabled^>^</LogonTrigger^>^</Triggers^>
    echo   ^<Actions^>^<Exec^>
    echo     ^<Command^>wscript.exe^</Command^>
    echo     ^<Arguments^>"!WRAPPER!"^</Arguments^>
    echo     ^<WorkingDirectory^>!PROJECT_DIR!^</WorkingDirectory^>
    echo   ^</Exec^>^</Actions^>
    echo ^</Task^>
)

schtasks /Query /TN "!TASK!" >nul 2>&1
if "!errorlevel!"=="0" (
    schtasks /End /TN "!TASK!" >nul 2>&1
    schtasks /Delete /TN "!TASK!" /F >nul 2>&1
)

schtasks /Create /TN "!TASK!" /XML "!XML!" /F
set "TASK_RC=!errorlevel!"
del "!XML!" >nul 2>&1
if not "!TASK_RC!"=="0" (
    echo [ERROR] schtasks /Create failed ^(exit code !TASK_RC!^).
    echo         Even with admin, this can happen if the task XML is malformed.
    echo         Open Task Scheduler ^(taskschd.msc^) and check for stale tasks.
    set "FAIL_RC=1" & goto :end
)

schtasks /Run /TN "!TASK!" >nul 2>&1

set "UP=1"
for /l %%n in (1,1,10) do (
    if "!UP!"=="1" (
        timeout /t 1 /nobreak >nul
        curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8742/api/health 2>nul | findstr "200" >nul && set "UP=0"
    )
)

echo.
if "!UP!"=="0" (
    echo === Done - server is running ===
    echo URL       : http://127.0.0.1:8742
    echo Restart   : "!SCRIPT_DIR!reset.bat"
    echo Uninstall : "!SCRIPT_DIR!uninstall.bat"
    start http://127.0.0.1:8742
) else (
    echo === Done - service installed; give it a few seconds ===
    echo URL       : http://127.0.0.1:8742
    echo Restart   : "!SCRIPT_DIR!reset.bat"
    echo Uninstall : "!SCRIPT_DIR!uninstall.bat"
)
echo.

:end
echo.
if "%FAIL_RC%"=="0" (
    echo --- finished successfully ---
) else (
    echo --- FINISHED WITH ERRORS, scroll up to read the messages ---
)
echo.
echo Press any key to close this window...
pause >nul
endlocal & exit /b %FAIL_RC%
