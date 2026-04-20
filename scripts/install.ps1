# =========================================================================
#  flutter-toolkit - one-shot installer (Windows / PowerShell).
#
#  Run from your Flutter project root for the full setup:
#      cd C:\path\to\my-flutter-app
#      powershell -ExecutionPolicy Bypass -File C:\path\to\flutter-toolkit\scripts\install.ps1
#
#  Does, in one shot:
#    1. pip install -e ".[all]"  (installs the `ftk` package + extras)
#    2. Adds Python Scripts dir to your user PATH (persistent)
#    3. Registers the project at the cwd (if it has ftk.yaml)
#    4. Installs a scheduled task "FlutterToolkitServer" (logon trigger)
#    5. Starts the service and opens http://localhost:8742
#
#  Run from the toolkit repo (no project context) and only steps 1-2 run.
# =========================================================================
$ErrorActionPreference = "Stop"

$ScriptDir   = $PSScriptRoot
$ToolkitDir  = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ProjectDir  = (Get-Location).Path

Write-Host ""
Write-Host "=== flutter-toolkit installer (Windows / PowerShell) ===" -ForegroundColor Cyan
Write-Host "Toolkit : $ToolkitDir"
Write-Host "Project : $ProjectDir"
Write-Host ""

# --- Detect Python -------------------------------------------------------
$py = $null
foreach ($cand in @("python", "py -3", "python3")) {
    $exe = $cand.Split(" ")[0]
    if (Get-Command $exe -ErrorAction SilentlyContinue) { $py = $cand; break }
}
if (-not $py) {
    Write-Host "[ERROR] No Python 3.10+ on PATH." -ForegroundColor Red
    Write-Host "        Install from https://www.python.org/downloads/"
    exit 1
}
$pyver = (& cmd /c "$py --version 2>&1").Trim()
Write-Host "[1/5] $pyver ($py)"

# --- Install pip package -------------------------------------------------
Write-Host "[2/5] Installing flutter-toolkit (with all extras)..."
& cmd /c "$py -m pip install --upgrade pip --quiet" 2>$null | Out-Null
Push-Location $ToolkitDir
& cmd /c "$py -m pip install -e .[all] --upgrade"
$pipRc = $LASTEXITCODE
Pop-Location
if ($pipRc -ne 0) {
    Write-Host "[ERROR] pip install failed." -ForegroundColor Red
    exit 1
}

# --- Add Scripts dir to user PATH ---------------------------------------
$scriptsDir = (& cmd /c "$py -c `"import sysconfig;print(sysconfig.get_path('scripts'))`"").Trim()
Write-Host "[3/5] Scripts dir: $scriptsDir"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
if ($userPath.Split(";") -contains $scriptsDir) {
    Write-Host "      Already in user PATH."
} else {
    $newPath = if ($userPath) { $userPath.TrimEnd(";") + ";" + $scriptsDir } else { $scriptsDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "      Added to user PATH (persistent)." -ForegroundColor Green
}

# --- Verify --------------------------------------------------------------
Write-Host "[4/5] Verifying ftk install..."
& cmd /c "$py -m ftk --version"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] ftk verification failed." -ForegroundColor Red
    exit 1
}

# --- Detect Flutter project ---------------------------------------------
if (-not (Test-Path (Join-Path $ProjectDir "ftk.yaml"))) {
    Write-Host ""
    Write-Host "=== Toolkit installed, no project autostart configured ===" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To make the web UI auto-start at every login, open a NEW terminal,"
    Write-Host "cd into your Flutter project (the one with ftk.yaml) and re-run:"
    Write-Host ""
    Write-Host "  cd C:\path\to\my-flutter-app"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$ScriptDir\install.ps1`""
    Write-Host ""
    Write-Host "Or just start the server manually:  ftk server"
    Write-Host ""
    exit 0
}

# --- Install scheduled task ---------------------------------------------
Write-Host "[5/5] Installing FlutterToolkitServer scheduled task..."

# Register project (no-op if already registered)
& cmd /c "$py -m ftk projects add `"$ProjectDir`"" 2>$null | Out-Null

# Resolve project id from ftk.yaml
$projectId = ""
try {
    $pyParts = $py.Split(" ")
    $pyExe = $pyParts[0]
    $pyArgs = @()
    if ($pyParts.Length -gt 1) { $pyArgs = $pyParts[1..($pyParts.Length - 1)] }
    $projectId = (& $pyExe @pyArgs -c "import sys; from ftk.config import load_config; print(load_config(sys.argv[1]).id)" "$ProjectDir" 2>$null).Trim()
} catch {}

$ftkExe = Join-Path $scriptsDir "ftk.exe"
if (-not (Test-Path $ftkExe)) {
    Write-Host "[ERROR] ftk.exe not found at $ftkExe" -ForegroundColor Red
    exit 1
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
Write-Host "      Launcher : $wrapper"

$taskName = "FlutterToolkitServer"
$xmlFile  = Join-Path $env:TEMP "flutter_toolkit_task.xml"
$xml = @"
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
"@
$xml | Set-Content -Encoding Unicode -Path $xmlFile

# Replace existing task if present
& schtasks.exe /Query /TN $taskName 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    & schtasks.exe /End    /TN $taskName 2>$null | Out-Null
    & schtasks.exe /Delete /TN $taskName /F 2>$null | Out-Null
}

& schtasks.exe /Create /TN $taskName /XML $xmlFile /F 2>$null | Out-Null
$taskRc = $LASTEXITCODE
Remove-Item $xmlFile -ErrorAction SilentlyContinue
if ($taskRc -ne 0) {
    Write-Host "[ERROR] Could not create scheduled task (error $taskRc)." -ForegroundColor Red
    Write-Host "        Try running PowerShell as Administrator."
    exit 1
}
Write-Host "      Task     : $taskName  (auto-starts at every logon)"

& schtasks.exe /Run /TN $taskName 2>$null | Out-Null

# Wait up to ~10s for the server to come up
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
    Write-Host "URL       : http://127.0.0.1:8742"
    Write-Host "Restart   : `"$ScriptDir\reset.bat`""
    Write-Host "Uninstall : `"$ScriptDir\uninstall.bat`""
    Start-Process "http://127.0.0.1:8742"
} else {
    Write-Host "=== Done - service installed, give it a few seconds ===" -ForegroundColor Yellow
    Write-Host "URL       : http://127.0.0.1:8742"
    Write-Host "Restart   : `"$ScriptDir\reset.bat`""
    Write-Host "Uninstall : `"$ScriptDir\uninstall.bat`""
}
Write-Host ""
