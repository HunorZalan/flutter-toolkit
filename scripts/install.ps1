# =========================================================================
#  flutter-toolkit - one-shot installer (Windows / PowerShell).
#
#  Run from your Flutter project root:
#      cd C:\path\to\my-flutter-app
#      powershell -ExecutionPolicy Bypass -File C:\path\to\flutter-toolkit\scripts\install.ps1
#
#  If the service is already installed and you just added a new project,
#  re-running this script registers the project and restarts the service
#  automatically — a full reinstall is NOT needed.
# =========================================================================
$ErrorActionPreference = "Stop"

$ScriptDir  = $PSScriptRoot
$ToolkitDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ProjectDir = (Get-Location).Path
$TaskName   = "FlutterToolkitServer"

Write-Host ""
Write-Host "=== flutter-toolkit installer (Windows / PowerShell) ===" -ForegroundColor Cyan
Write-Host "Toolkit : $ToolkitDir"
Write-Host "Project : $ProjectDir"
Write-Host ""

# ---- Detect Python -------------------------------------------------------
$py = $null
foreach ($cand in @("python", "py -3", "python3")) {
    $exe = $cand.Split(" ")[0]
    if (Get-Command $exe -ErrorAction SilentlyContinue) { $py = $cand; break }
}
if (-not $py) {
    Write-Host "[ERROR] No Python 3.10+ on PATH." -ForegroundColor Red
    exit 1
}
$pyver = (& cmd /c "$py --version 2>&1").Trim()
Write-Host "[info] $pyver ($py)"

# ---- Registry fallback for project (if cwd has no ftk.yaml) -----------
if (-not (Test-Path (Join-Path $ProjectDir "ftk.yaml"))) {
    try {
        $fb = (& cmd /c "$py -c `"from ftk.projects import get_last_project_id,find_project,list_projects;import os;ps=list_projects();fb=ps[0] if ps else None;e=find_project(get_last_project_id() or '') or fb;print(e.root if e and os.path.isfile(os.path.join(e.root,'ftk.yaml')) else '')`"" 2>$null).Trim()
        if ($fb) { $ProjectDir = $fb; Write-Host "      Registry project: $ProjectDir" -ForegroundColor Green }
    } catch {}
}

# =========================================================================
# FAST PATH — task already exists + project found -> register + restart
# =========================================================================
if (Test-Path (Join-Path $ProjectDir "ftk.yaml")) {
    $taskExists = $false
    & schtasks.exe /Query /TN $TaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $taskExists = $true }

    if ($taskExists) {
        Write-Host "Service already installed. Registering project and restarting..." -ForegroundColor Cyan
        & cmd /c "$py -m pip install -e `"$ToolkitDir\[all]`" --upgrade -q" 2>$null | Out-Null
        & cmd /c "$py -m ftk projects add `"$ProjectDir`"" 2>$null | Out-Null
        & schtasks.exe /End /TN $TaskName 2>$null | Out-Null
        Start-Sleep -Seconds 1
        & schtasks.exe /Run /TN $TaskName 2>$null | Out-Null
        Write-Host "Done. Project registered and service restarted." -ForegroundColor Green
        Write-Host "URL: http://127.0.0.1:8742"
        Write-Host ""
        exit 0
    }
}

# =========================================================================
# FULL INSTALL
# =========================================================================

# ---- 1. Install pip package ---------------------------------------------
Write-Host "[1/5] Installing flutter-toolkit (with all extras)..."
& cmd /c "$py -m pip install --upgrade pip --quiet" 2>$null | Out-Null
Push-Location $ToolkitDir
& cmd /c "$py -m pip install -e .[all] --upgrade"
$pipRc = $LASTEXITCODE
Pop-Location
if ($pipRc -ne 0) { Write-Host "[ERROR] pip install failed." -ForegroundColor Red; exit 1 }

# ---- 2. PATH ------------------------------------------------------------
$scriptsDir = (& cmd /c "$py -c `"import sysconfig;print(sysconfig.get_path('scripts'))`"").Trim()
Write-Host "[2/5] Scripts dir: $scriptsDir"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
if ($userPath.Split(";") -notcontains $scriptsDir) {
    $newPath = if ($userPath) { $userPath.TrimEnd(";") + ";" + $scriptsDir } else { $scriptsDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "      Added to user PATH (persistent)." -ForegroundColor Green
} else {
    Write-Host "      Already in user PATH."
}

# ---- 3. Verify ----------------------------------------------------------
Write-Host "[3/5] Verifying ftk install..."
& cmd /c "$py -m ftk --version"
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] ftk verification failed." -ForegroundColor Red; exit 1 }

# ---- 4. Bail if no project ----------------------------------------------
if (-not (Test-Path (Join-Path $ProjectDir "ftk.yaml"))) {
    Write-Host ""
    Write-Host "=== Toolkit installed, no project autostart configured ===" -ForegroundColor Yellow
    Write-Host "  ftk projects add C:\path\to\my-flutter-app"
    Write-Host "  Re-run: $ScriptDir\install.ps1"
    Write-Host "  Or:     ftk server"
    Write-Host ""
    exit 0
}

# ---- 5. Install scheduled task ------------------------------------------
Write-Host "[4/5] Registering project..."
& cmd /c "$py -m ftk projects add `"$ProjectDir`"" 2>$null | Out-Null

$projectId = ""
try {
    $projectId = (& cmd /c "$py -c `"from ftk.config import load_config;print(load_config(r'$ProjectDir').id)`"" 2>$null).Trim()
} catch {}

$ftkExe = Join-Path $scriptsDir "ftk.exe"
if (-not (Test-Path $ftkExe)) {
    Write-Host "[ERROR] ftk.exe not found at $ftkExe" -ForegroundColor Red; exit 1
}

$ftkDir = Join-Path $ProjectDir ".ftk"
if (-not (Test-Path $ftkDir)) { New-Item -ItemType Directory -Path $ftkDir | Out-Null }
$wrapper = Join-Path $ftkDir "start_server_bg.vbs"
$runArg = if ($projectId) { "`"$ftkExe`" --project $projectId server" } else { "`"$ftkExe`" server" }
@"
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "$ProjectDir"
shell.Run "$runArg", 0, False
"@ | Set-Content -Encoding ASCII -Path $wrapper

Write-Host "[5/5] Creating scheduled task $TaskName..."
$xmlFile = Join-Path $env:TEMP "flutter_toolkit_task.xml"
@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>flutter-toolkit web UI - http://localhost:8742</Description></RegistrationInfo>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>
  </Settings>
  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>
  <Actions><Exec>
    <Command>wscript.exe</Command>
    <Arguments>"$wrapper"</Arguments>
    <WorkingDirectory>$ProjectDir</WorkingDirectory>
  </Exec></Actions>
</Task>
"@ | Set-Content -Encoding Unicode -Path $xmlFile

& schtasks.exe /Query /TN $TaskName 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    & schtasks.exe /End    /TN $TaskName 2>$null | Out-Null
    & schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
}
& schtasks.exe /Create /TN $TaskName /XML $xmlFile /F 2>$null | Out-Null
$taskRc = $LASTEXITCODE
Remove-Item $xmlFile -ErrorAction SilentlyContinue
if ($taskRc -ne 0) {
    Write-Host "[ERROR] Could not create scheduled task. Try running as Administrator." -ForegroundColor Red
    exit 1
}
Write-Host "      Task: $TaskName (auto-starts at logon)"
& schtasks.exe /Run /TN $TaskName 2>$null | Out-Null

$up = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8742/api/health" -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch {}
}

Write-Host ""
if ($up) {
    Write-Host "=== Done - server is running ===" -ForegroundColor Green
    Start-Process "http://127.0.0.1:8742"
} else {
    Write-Host "=== Done - service installed, give it a few seconds ===" -ForegroundColor Yellow
}
Write-Host "URL       : http://127.0.0.1:8742"
Write-Host "Restart   : `"$ScriptDir\reset.bat`""
Write-Host "Uninstall : `"$ScriptDir\uninstall.bat`""
Write-Host ""
