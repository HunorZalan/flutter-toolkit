"""Manage the global flutter-toolkit project registry."""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

from ftk.common import C, header, ok, warn, err, info, init_colours
from ftk.config import ProjectConfig
from ftk.projects import (
    list_projects, add_project, remove_project, find_project,
    set_last_project_id, clear_last_project, registry_file,
)


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------

def _ftk_exe() -> str | None:
    """Find the ftk executable next to the current Python interpreter."""
    candidate = shutil.which("ftk")
    if candidate:
        return candidate
    # Fallback: Scripts dir next to sys.executable
    scripts = os.path.join(os.path.dirname(sys.executable), "ftk.exe")
    if os.path.isfile(scripts):
        return scripts
    return None


def _create_windows_task(entry) -> bool:
    """Create and start the FlutterToolkitServer scheduled task. Returns True on success."""
    ftk = _ftk_exe()
    if not ftk:
        err("Could not locate ftk.exe - run install.bat first.")
        return False

    project_dir = entry.root
    project_id  = entry.id
    ftk_dir     = os.path.join(project_dir, ".ftk")
    os.makedirs(ftk_dir, exist_ok=True)

    # VBS silent launcher (no console window)
    wrapper = os.path.join(ftk_dir, "start_server_bg.vbs")
    run_arg = f'"{ftk}" --project {project_id} server'
    with open(wrapper, "w", encoding="ascii") as f:
        f.write('Dim shell\n')
        f.write('Set shell = CreateObject("WScript.Shell")\n')
        f.write(f'shell.CurrentDirectory = "{project_dir}"\n')
        f.write(f'shell.Run """{ftk}"" --project {project_id} server", 0, False\n')

    # Task XML
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
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
    <Arguments>"{wrapper}"</Arguments>
    <WorkingDirectory>{project_dir}</WorkingDirectory>
  </Exec></Actions>
</Task>"""

    xml_path = os.path.join(tempfile.gettempdir(), "flutter_toolkit_task.xml")
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    task = "FlutterToolkitServer"
    # Remove old task if present
    subprocess.run(["schtasks", "/End",    "/TN", task], capture_output=True)
    subprocess.run(["schtasks", "/Delete", "/TN", task, "/F"], capture_output=True)

    r = subprocess.run(["schtasks", "/Create", "/TN", task, "/XML", xml_path, "/F"],
                       capture_output=True)
    try:
        os.remove(xml_path)
    except OSError:
        pass

    if r.returncode != 0:
        # Likely needs admin - try to elevate via PowerShell
        warn("Task creation needs administrator privileges. Requesting elevation...")
        ps_cmd = (
            f"schtasks /Create /TN {task} /XML '{xml_path}' /F; "
            f"schtasks /Run /TN {task}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command \"{ps_cmd}\"'"],
            capture_output=True,
        )
        time.sleep(3)
        # Check if it worked
        r2 = subprocess.run(["schtasks", "/Query", "/TN", task], capture_output=True)
        if r2.returncode != 0:
            err("Could not create scheduled task even with elevation.")
            info("Run install.bat as Administrator from your project directory.")
            return False

    subprocess.run(["schtasks", "/Run", "/TN", task], capture_output=True)
    return True


def _maybe_restart_service(entry=None) -> None:
    """Restart the OS service, or create + start it if not yet installed."""
    if sys.platform == "win32":
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", "FlutterToolkitServer"],
            capture_output=True,
        )
        if r.returncode == 0:
            # Task exists - restart it
            subprocess.run(["schtasks", "/End", "/TN", "FlutterToolkitServer"], capture_output=True)
            time.sleep(1)
            subprocess.run(["schtasks", "/Run", "/TN", "FlutterToolkitServer"], capture_output=True)
            info("Service restarted with new project.")
        elif entry is not None:
            # Task doesn't exist - create it now
            info("Service not installed yet - creating scheduled task...")
            if _create_windows_task(entry):
                ok("Service installed and started.")
                info("URL: http://127.0.0.1:8742")
            # else: error already printed inside _create_windows_task
        else:
            warn("Service not installed yet.")
            info("Run install.bat from your project directory to install the service.")

    elif sys.platform == "darwin":
        plist_label = "com.flutter-toolkit.server"
        plist_path  = os.path.expanduser(f"~/Library/LaunchAgents/{plist_label}.plist")
        if os.path.exists(plist_path):
            uid = os.getuid()
            subprocess.run(["launchctl", "bootout", f"gui/{uid}/{plist_label}"], capture_output=True)
            time.sleep(1)
            subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist_path], capture_output=True)
            info("Service restarted with new project.")
        else:
            warn("Service not installed yet.")
            info("Run install.sh from your project directory to install the service.")

    else:  # Linux
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "flutter-toolkit.service"],
            capture_output=True,
        )
        if r.returncode == 0:
            subprocess.run(["systemctl", "--user", "restart", "flutter-toolkit.service"],
                           capture_output=True)
            info("Service restarted with new project.")
        else:
            warn("Service not installed yet.")
            info("Run install.sh from your project directory to install the service.")


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def _cmd_list(_args) -> int:
    entries = list_projects()
    header("Registered projects")
    info(f"Registry: {registry_file()}")
    if not entries:
        warn("No projects registered. Use `ftk projects add <path>`.")
        return 0
    for p in entries:
        marker = f" {C.GREEN}[active]{C.RESET}" if p.active else ""
        print(f"  {C.BOLD}{p.id:<20}{C.RESET}  {p.name:<30}  {p.root}{marker}")
    return 0


def _cmd_add(args) -> int:
    try:
        entry = add_project(args.path, project_id=args.id or "", name=args.name or "")
    except FileNotFoundError as exc:
        err(str(exc))
        return 1
    ok(f"Added project {entry.id!r} -> {entry.root}")
    _maybe_restart_service(entry)
    return 0


def _cmd_remove(args) -> int:
    entry = find_project(args.id)
    target_id = entry.id if entry else args.id
    if remove_project(target_id):
        ok(f"Removed project {target_id!r}")
        return 0
    err(f"No project with id {args.id!r}")
    return 1


def _cmd_use(args) -> int:
    entry = find_project(args.id)
    if not entry:
        err(f"Unknown project {args.id!r}. Use `ftk projects list`.")
        return 1
    set_last_project_id(entry.id)
    ok(f"Active project set to {entry.id!r} ({entry.root})")
    return 0


def _cmd_clear(_args) -> int:
    clear_last_project()
    ok("Cleared active project.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(cfg: ProjectConfig, argv: list[str]) -> int: # noqa: S1172 - cfg required by command interface
    init_colours()
    parser = argparse.ArgumentParser(prog="ftk projects", description="Manage the project registry.")
    sub = parser.add_subparsers(dest="sub", metavar="{list,add,rm,use,clear}")

    sub.add_parser("list", aliases=["ls"], help="List registered projects.")
    p_add = sub.add_parser("add", help="Register a project directory.")
    p_add.add_argument("path")
    p_add.add_argument("--id",   help="Short id (default: folder name).")
    p_add.add_argument("--name", help="Human-readable name.")
    p_rm = sub.add_parser("rm", aliases=["remove"], help="Remove a project.")
    p_rm.add_argument("id")
    p_use = sub.add_parser("use", help="Mark a project as active.")
    p_use.add_argument("id")
    sub.add_parser("clear", help="Forget the active project.")

    if not argv:
        return _cmd_list(None)
    args = parser.parse_args(argv)
    if args.sub in (None, "list", "ls"):
        return _cmd_list(args)
    if args.sub == "add":
        return _cmd_add(args)
    if args.sub in ("rm", "remove"):
        return _cmd_remove(args)
    if args.sub == "use":
        return _cmd_use(args)
    if args.sub == "clear":
        return _cmd_clear(args)
    parser.print_help()
    return 1
