"""Flutter clean & reinstall."""
from __future__ import annotations
import argparse
import glob
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from ftk.common import (
    C, find_flutter, header, ok, warn, err, info, skip, confirm,
    run_cmd, clear_flutter_lock, fmt_size, dir_size,
)
from ftk.config import ProjectConfig

_IS_MAC = sys.platform == "darwin"
_IS_WIN = sys.platform == "win32"
_NO_FLUTTER = "Flutter not found - skipping."


def _flutter_cmd(flutter_exe: str, *args: str) -> list[str]:
    return [flutter_exe, *args]


def _is_running_in_ide() -> bool:
    indicators = ["TERMINAL_EMULATOR", "IDEA_INITIAL_DIRECTORY", "VSCODE_PID", "TERM_PROGRAM"]
    for var in indicators:
        if os.environ.get(var):
            return True
    if "jetbrains" in os.environ.get("__CFBundleIdentifier", "").lower():
        return True
    if "android studio" in os.environ.get("_", "").lower():
        return True
    return False


def _remove(path: str, label: str, *, dry_run: bool) -> None:
    p = Path(path)
    if dry_run:
        if p.exists():
            info(f"[dry-run] would delete: {label}")
        else:
            info(f"[dry-run] {label} not found - would skip.")
        return
    if not p.exists():
        info(f"{label} not found - skipping.")
        return
    try:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        ok(f"{label} deleted.")
    except Exception as exc:
        err(f"Could not delete {label}: {exc}")


def _kill_with_psutil(psutil) -> None:
    killed = 0
    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info["name"] or "").lower()
        if "dart" in name or "flutter" in name:
            try:
                proc.kill()
                ok(f"Killed  {proc.info['name']}  (pid {proc.info['pid']})")
                killed += 1
            except Exception as exc:
                warn(f"Could not kill {proc.info['name']} (pid {proc.info['pid']}): {exc}")
    ok("No dart/flutter processes found." if killed == 0 else f"Killed {killed} process(es).")


def _kill_with_pkill() -> None:
    any_killed = False
    for name in ("dart", "flutter"):
        result = subprocess.run(["pkill", "-f", name], capture_output=True)
        if result.returncode == 0:
            ok(f"pkill -f {name}  -> OK")
            any_killed = True
        elif result.returncode == 1:
            info(f"pkill -f {name}  -> no processes found")
        else:
            warn(f"pkill -f {name}  -> exit code {result.returncode}")
    if not any_killed:
        ok("No dart/flutter processes found.")


def _kill_with_powershell() -> None:
    ps_cmd = (
        'Get-Process | Where-Object { $_.ProcessName -match "dart|flutter" }'
        " | Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True,
    )
    if result.returncode == 0:
        ok("dart/flutter processes stopped (PowerShell).")
    else:
        warn(f"PowerShell kill returned code {result.returncode}")


def kill_dart_flutter(*, dry_run: bool, force: bool = False) -> None:
    header("Kill dart / flutter processes")
    if _is_running_in_ide() and not force:
        warn("Running inside IDE - skipping process kill to protect Analysis Server.")
        info("Tip: pass --kill to force.")
        return
    if dry_run:
        info("[dry-run] would kill dart/flutter processes")
        return
    try:
        import psutil  # type: ignore[import-untyped]
        _kill_with_psutil(psutil)
    except ImportError:
        if _IS_WIN:
            _kill_with_powershell()
        else:
            _kill_with_pkill()


def _gradlew_path(android_dir: str) -> str | None:
    bat = os.path.join(android_dir, "gradlew.bat")
    sh = os.path.join(android_dir, "gradlew")
    candidates = [bat, sh] if _IS_WIN else [sh, bat]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _stop_gradle_daemon(android_dir: str, gradlew: str, *, dry_run: bool) -> None:
    if dry_run:
        info("[dry-run] would run: gradlew --stop")
        return
    info("Stopping Gradle daemon to release file locks...")
    result = subprocess.run([gradlew, "--stop"], cwd=android_dir, capture_output=True, text=True)
    if result.returncode == 0:
        ok("Gradle daemon stopped.")
        if result.stdout.strip():
            info(result.stdout.strip())
    else:
        info("Gradle daemon was not running (or already stopped).")


def _kill_gradle_daemons() -> None:
    """Kill any lingering Gradle/Java daemon processes that hold cache locks."""
    if _IS_WIN:
        # On Windows, Gradle daemons are java.exe holding .lock files.
        ps_cmd = (
            'Get-Process java -ErrorAction SilentlyContinue '
            '| Where-Object { $_.CommandLine -match "gradle" } '
            '| Stop-Process -Force -ErrorAction SilentlyContinue'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, timeout=15,
        )
    else:
        # On macOS/Linux, pkill Gradle daemons.
        subprocess.run(
            ["pkill", "-f", "GradleDaemon"],
            capture_output=True,
        )


def _force_remove_dir(path: str, label: str) -> None:
    """Remove a directory with retry on Windows for locked files."""
    import time as _time
    p = Path(path)
    if not p.exists():
        info(f"{label} not found - skipping.")
        return
    last_exc = None
    for attempt in range(3):
        try:
            shutil.rmtree(p, onerror=_rmtree_onerror)
            ok(f"{label} deleted.")
            return
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                _time.sleep(1 + attempt)
    err(f"Could not delete {label}: {last_exc}")


def _rmtree_onerror(func, path, exc_info):
    """Handle read-only and locked files during rmtree."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


# ---- pod helpers ----

def _pod_dirs(project_root: str, cfg: ProjectConfig | None = None) -> list[tuple[str, str]]:
    dirs = []
    for sub, label in (("ios", "ios"), ("macos", "macos")):
        if cfg and not cfg.platform_enabled(sub):
            continue
        d = os.path.join(project_root, sub)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "Podfile")):
            dirs.append((d, label))
    return dirs


def _require_pod() -> bool:
    if shutil.which("pod") is None:
        err("CocoaPods (`pod`) not found. Install: sudo gem install cocoapods")
        return False
    return True


def _run_pod(cmd: list[str], *, cwd: str, label: str, dry_run: bool) -> bool:
    return run_cmd(cmd, cwd=cwd, label=label, dry_run=dry_run)


def _pod_install(project_root: str, cfg: ProjectConfig | None = None, *,
                  extra_flags: list[str], dry_run: bool) -> bool:
    if not _IS_MAC:
        info("pod install requires macOS - skipping.")
        return True
    if not _require_pod():
        return False
    all_ok = True
    for pod_dir, label in _pod_dirs(project_root, cfg):
        cmd = ["pod", "install", *extra_flags]
        if not _run_pod(cmd, cwd=pod_dir, label=f"pod install ({label})", dry_run=dry_run):
            all_ok = False
    return all_ok


def _flutter_or_skip(flutter_exe, cmd_args, results, run_fn):
    """Run a flutter command, or record failure if flutter is not available."""
    if flutter_exe:
        results.append(run_fn(_flutter_cmd(flutter_exe, *cmd_args)))
    else:
        err(_NO_FLUTTER)
        results.append(False)


def _run_standalone_pods(args, pod_dirs, dry_run, results) -> None:
    """Execute standalone pod commands from the CLI args."""
    _POD_COMMANDS = [
        ("pod_deintegrate",   ["pod", "deintegrate"]),
        ("pod_install",       ["pod", "install"]),
        ("pod_repo_update",   ["pod", "install", "--repo-update"]),
        ("pod_clean_install", ["pod", "install", "--clean-install"]),
        ("pod_verbose",       ["pod", "install", "--verbose"]),
        ("pod_update",        ["pod", "update"]),
        ("pod_update_no_repo",["pod", "update", "--no-repo-update"]),
    ]
    for attr, cmd in _POD_COMMANDS:
        if not getattr(args, attr, False):
            continue
        for d, lbl in pod_dirs:
            label = f"{' '.join(cmd)} ({lbl})"
            results.append(_run_pod(cmd, cwd=d, label=label, dry_run=dry_run))


def _clean_derived_data_runner(*, dry_run: bool) -> None:
    if not _IS_MAC:
        info("DerivedData cleanup requires macOS - skipping.")
        return
    pattern = os.path.expanduser("~/Library/Developer/Xcode/DerivedData/Runner-*")
    matches = glob.glob(pattern)
    if not matches:
        info("No DerivedData/Runner-* found - nothing to delete.")
        return
    for m in matches:
        _remove(m, f"DerivedData/{os.path.basename(m)}", dry_run=dry_run)


def _clean_android(project_root, *, dry_run, confirm_fn, run_fn):
    header("Android - gradlew clean")
    android_dir = os.path.join(project_root, "android")
    if not os.path.isdir(android_dir):
        warn("android/ folder not found - skipping.")
        return True
    gradlew = _gradlew_path(android_dir)
    gradle_success = True
    if gradlew is None:
        warn("gradlew not found - skipping gradlew clean.")
    else:
        if not _IS_WIN:
            try:
                os.chmod(gradlew, os.stat(gradlew).st_mode | stat.S_IXUSR)
            except OSError:
                pass
        _stop_gradle_daemon(android_dir, gradlew, dry_run=dry_run)
        gradle_success = run_fn(
            [gradlew, "clean", "--no-daemon"], cwd=android_dir, label="gradlew clean"
        )
        _stop_gradle_daemon(android_dir, gradlew, dry_run=dry_run)
    _remove(os.path.join(android_dir, ".gradle"),        "android/.gradle",      dry_run=dry_run)
    _remove(os.path.join(android_dir, "build"),          "android/build/",       dry_run=dry_run)
    _remove(os.path.join(android_dir, "app", "build"),   "android/app/build/",   dry_run=dry_run)
    _remove(os.path.join(android_dir, "app", ".cxx"),    "android/app/.cxx/",    dry_run=dry_run)
    _delete_gradle_cache(dry_run=dry_run, confirm_fn=confirm_fn)
    return gradle_success


def _delete_gradle_cache(*, dry_run, confirm_fn):
    """Delete ~/.gradle/caches with daemon cleanup to avoid lock errors."""
    global_cache = os.path.join(os.path.expanduser("~"), ".gradle", "caches")
    if not os.path.isdir(global_cache):
        return
    if not dry_run:
        info(f"Global Gradle cache size: {fmt_size(dir_size(global_cache))}")
    if not confirm_fn("Delete global ~/.gradle/caches?"):
        return
    if dry_run:
        info("[dry-run] would delete ~/.gradle/caches")
        return
    # Kill lingering daemon processes that hold lock files
    info("Killing Gradle daemon processes to release file locks...")
    _kill_gradle_daemons()
    _force_remove_dir(global_cache, "~/.gradle/caches")


def _clean_ios(project_root, cfg, *, dry_run):
    active_apple = [p for p in ("iOS", "macOS") if cfg.platform_enabled(p.lower())]
    header(f"{' + '.join(active_apple) or 'Apple'} - pod deintegrate + DerivedData")
    if _IS_WIN:
        info("Running on Windows - iOS/macOS pod steps skipped.")
        return True
    pod_ok = True
    if _require_pod():
        for pod_dir, label in _pod_dirs(project_root, cfg):
            _remove(os.path.join(pod_dir, "Podfile.lock"), f"{label}/Podfile.lock", dry_run=dry_run)
            _remove(os.path.join(pod_dir, "Pods"), f"{label}/Pods/", dry_run=dry_run)
            if not _run_pod(["pod", "deintegrate"], cwd=pod_dir,
                            label=f"pod deintegrate ({label})", dry_run=dry_run):
                pod_ok = False
            _run_pod(["pod", "repo", "update"], cwd=pod_dir,
                     label=f"pod repo update ({label})", dry_run=dry_run)
            ephemeral = os.path.join(pod_dir, "Flutter", "ephemeral")
            if os.path.isdir(ephemeral):
                _remove(ephemeral, f"{label}/Flutter/ephemeral/", dry_run=dry_run)
    else:
        pod_ok = False
    _clean_derived_data_runner(dry_run=dry_run)
    return pod_ok


def _pub_get_section(flutter_exe, project_root, cfg, pub_modifiers, *, dry_run, run_fn):
    header("flutter pub get")
    if not flutter_exe:
        err(_NO_FLUTTER)
        return False
    cmd = _flutter_cmd(flutter_exe, "pub", "get", *pub_modifiers)
    success = run_fn(cmd)
    if not success and _IS_WIN:
        warn("Tip: Flutter symlink support requires Windows Developer Mode.")
    if success and _IS_MAC:
        pods = _pod_dirs(project_root, cfg)
        if pods:
            header("pod install (after pub get)")
            return _pod_install(project_root, cfg, extra_flags=[], dry_run=dry_run)
    return success


def _cocoapods_section(args, project_root, cfg, *, dry_run, results):
    header("CocoaPods")
    if not _IS_MAC:
        warn("CocoaPods commands require macOS - skipping all.")
        return
    if not _require_pod():
        results.append(False)
        return
    pod_dirs = _pod_dirs(project_root, cfg)
    if not pod_dirs:
        warn("No ios/ or macos/ with Podfile found.")
    else:
        _run_standalone_pods(args, pod_dirs, dry_run, results)
    if args.pod_cache_clean:
        results.append(_run_pod(["pod", "cache", "clean", "--all"],
                                cwd=project_root, label="pod cache clean --all", dry_run=dry_run))
    if args.pod_repo_list:
        _run_pod(["pod", "repo", "list"], cwd=project_root,
                 label="pod repo list", dry_run=dry_run)
    if args.pod_env:
        _run_pod(["pod", "env"], cwd=project_root,
                 label="pod env", dry_run=dry_run)


def _build_pub_modifiers(args):
    mods: list[str] = []
    if args.pub_offline:
        mods.append("--offline")
    if args.pub_enforce_lockfile:
        mods.append("--enforce-lockfile")
    if args.no_precompile:
        mods.append("--no-precompile")
    if args.no_example:
        mods.append("--no-example")
    return mods


def _pub_cache_section(flutter_exe, *, dry_run, confirm_fn, run_fn, results):
    header("flutter pub cache clean")
    if not flutter_exe:
        err(_NO_FLUTTER)
        results.append(False)
        return
    pub_cache = os.path.join(os.path.expanduser("~"), ".pub-cache")
    if os.path.isdir(pub_cache) and not dry_run:
        info(f"Current pub cache size: {fmt_size(dir_size(pub_cache))}  ({pub_cache})")
    if confirm_fn("Clear the global pub cache? All packages re-download on next pub get."):
        results.append(run_fn(_flutter_cmd(flutter_exe, "pub", "cache", "clean", "--force")))
    else:
        skip("pub cache clean")
        results.append(True)


def _pub_upgrade_section(flutter_exe, pub_modifiers, *, confirm_fn, run_fn, results):
    header("flutter pub upgrade --major-versions")
    if not confirm_fn("This may introduce breaking changes. Run pub upgrade --major-versions?"):
        skip("pub upgrade")
        results.append(True)
    elif flutter_exe:
        mods = [m for m in pub_modifiers if m != "--enforce-lockfile"]
        results.append(run_fn(_flutter_cmd(flutter_exe, "pub", "upgrade",
                                           "--major-versions", *mods)))
    else:
        err(_NO_FLUTTER)
        results.append(False)


def _flutter_upgrade_section(flutter_exe, *, confirm_fn, run_fn, results, force=False):
    header("flutter upgrade")
    if not confirm_fn("Upgrade the Flutter SDK itself (flutter upgrade)?"):
        skip("flutter upgrade")
        results.append(True)
    elif flutter_exe:
        cmd_args = ("upgrade", "--force") if force else ("upgrade",)
        results.append(run_fn(_flutter_cmd(flutter_exe, *cmd_args)))
    else:
        err(_NO_FLUTTER)
        results.append(False)

# ── 1. Kill ────────────────────────────────────────────
def _step_kill(args, flutter_exe, *, dry_run: bool, run_all: bool) -> None:
    if (run_all or args.kill) and not args.no_kill:
        kill_dart_flutter(dry_run=dry_run, force=args.kill)
    clear_flutter_lock(flutter_exe)


# ── 2. Clean ───────────────────────────────────────────
def _step_clean(args, cfg, project_root, flutter_exe, results, *,
                dry_run: bool, run_fn, run_all: bool) -> None:
    if not (run_all or args.clean):
        return
    header("flutter clean")
    _flutter_or_skip(flutter_exe, ("clean",), results, run_fn)
    header("Delete pubspec.lock")
    _remove(os.path.join(project_root, "pubspec.lock"), "pubspec.lock", dry_run=dry_run)
    for sub in ("ios", "macos"):
        if not cfg.platform_enabled(sub):
            continue
        d = os.path.join(project_root, sub)
        if os.path.isdir(d):
            _remove(os.path.join(d, "Pods"),        f"{sub}/Pods/",       dry_run=dry_run)
            _remove(os.path.join(d, "Podfile.lock"), f"{sub}/Podfile.lock", dry_run=dry_run)
            _remove(os.path.join(d, ".symlinks"),    f"{sub}/.symlinks/",   dry_run=dry_run)
    
    for sub in ("linux", "windows"):
        if not cfg.platform_enabled(sub):
            continue
        eph = os.path.join(project_root, sub, "flutter", "ephemeral")
        _remove(eph, f"{sub}/flutter/ephemeral/", dry_run=dry_run)


# ── 3. Build-cache ─────────────────────────────────────
def _step_build_cache(args, project_root, results, *, dry_run: bool, run_all: bool) -> None:
    if not (run_all or args.build_cache):
        return
    header("Delete build cache (build/ + .dart_tool/)")
    dart_tool_dir = os.path.join(project_root, ".dart_tool")
    build_dir     = os.path.join(project_root, "build")
    before = sum(dir_size(d) for d in (dart_tool_dir, build_dir) if os.path.isdir(d))
    _remove(dart_tool_dir, ".dart_tool/", dry_run=dry_run)
    _remove(build_dir,     "build/",      dry_run=dry_run)
    ok(f"Freed {fmt_size(before)}.")
    results.append(True)


# ── 4. Pub extra (upgrade-dry-run / outdated / deps) ─
def _step_pub_extras(args, flutter_exe, pub_modifiers, results, *, run_fn) -> None:
    if args.upgrade_dry_run:
        header("flutter pub upgrade --dry-run")
        mods = [m for m in pub_modifiers if m != "--enforce-lockfile"]
        _flutter_or_skip(flutter_exe, ("pub", "upgrade", "--dry-run", *mods), results, run_fn)
    if args.pub_outdated:
        header("flutter pub outdated")
        _flutter_or_skip(flutter_exe, ("pub", "outdated"), results, run_fn)
    if args.pub_deps:
        header("flutter pub deps")
        _flutter_or_skip(flutter_exe, ("pub", "deps"), results, run_fn)


# ── 5. CocoaPods ───────────────────────────────────────
def _step_cocoapods(args, project_root, cfg, results, *, dry_run: bool) -> None:
    _any_pod = any([args.pod_install, args.pod_repo_update, args.pod_clean_install,
                    args.pod_verbose, args.pod_update, args.pod_update_no_repo,
                    args.pod_deintegrate, args.pod_cache_clean, args.pod_repo_list,
                    args.pod_env])
    if _any_pod:
        _cocoapods_section(args, project_root, cfg, dry_run=dry_run, results=results)


# ── 6. Xcode ──────────────────────────────────────
def _step_open_xcode(args, project_root, *, run_fn) -> None:
    if not args.open_xcode:
        return
    header("Open Runner.xcworkspace")
    if not _IS_MAC:
        warn("--open-xcode requires macOS.")
        return
    ws = os.path.join(project_root, "ios", "Runner.xcworkspace")
    if os.path.isdir(ws):
        run_fn(["open", ws], label="open ios/Runner.xcworkspace")
    else:
        warn("ios/Runner.xcworkspace not found. Run `flutter pub get` first.")


# ── 7. Summary ──────────────────────────────────────────
def _print_clean_summary(results: list[bool], *, dry_run: bool) -> int:
    header("Summary")
    failed = results.count(False)
    total  = len(results)
    if dry_run:
        ok(f"Dry run complete - {total} step(s) would run.")
    elif failed == 0:
        ok(f"All {total} step(s) completed successfully.")
    else:
        err(f"{failed}/{total} step(s) failed.")
    print()
    return 0 if (dry_run or failed == 0) else 1


# ── 8. Chief Dispatcher ─────────────────────────────────────────
def _dispatch_steps(args, cfg, flutter_exe, pub_modifiers, results, *,
                    run_all: bool, dry_run: bool, confirm_fn, run_fn) -> None:
    project_root = cfg.root

    _step_kill(args, flutter_exe, dry_run=dry_run, run_all=run_all)
    _step_clean(args, cfg, project_root, flutter_exe, results,
                dry_run=dry_run, run_fn=run_fn, run_all=run_all)
    _step_build_cache(args, project_root, results, dry_run=dry_run, run_all=run_all)

    if run_all or args.pub_cache:
        _pub_cache_section(flutter_exe, dry_run=dry_run,
                           confirm_fn=confirm_fn, run_fn=run_fn, results=results)
    if run_all or args.android:
        results.append(_clean_android(project_root, dry_run=dry_run,
                                      confirm_fn=confirm_fn, run_fn=run_fn))
    if run_all or args.ios:
        results.append(_clean_ios(project_root, cfg, dry_run=dry_run))
    if args.derived_data and not (run_all or args.ios):
        header("Delete Xcode DerivedData/Runner-*")
        _clean_derived_data_runner(dry_run=dry_run)
    if run_all or args.get:
        results.append(_pub_get_section(flutter_exe, project_root, cfg,
                                        pub_modifiers, dry_run=dry_run, run_fn=run_fn))
    if args.upgrade:
        _pub_upgrade_section(flutter_exe, pub_modifiers,
                             confirm_fn=confirm_fn, run_fn=run_fn, results=results)

    _step_pub_extras(args, flutter_exe, pub_modifiers, results, run_fn=run_fn)

    if args.flutter_upgrade:
        _flutter_upgrade_section(flutter_exe, confirm_fn=confirm_fn,
                             run_fn=run_fn, results=results,
                             force=args.flutter_upgrade_force)

    _step_cocoapods(args, project_root, cfg, results, dry_run=dry_run)
    _step_open_xcode(args, project_root, run_fn=run_fn)


# ── 9. run() - Just need to hook it up and configure it ────────────────────
def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk clean", description="Flutter clean & reinstall")
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--kill", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--build-cache", action="store_true")
    parser.add_argument("--android", action="store_true")
    parser.add_argument("--ios", action="store_true")
    parser.add_argument("--derived-data", action="store_true")
    parser.add_argument("--get", action="store_true")
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument("--pub-cache", action="store_true")
    parser.add_argument("--flutter-upgrade", action="store_true")
    parser.add_argument("--flutter-upgrade-force", action="store_true")
    parser.add_argument("--pub-outdated", action="store_true")
    parser.add_argument("--pub-deps", action="store_true")
    parser.add_argument("--upgrade-dry-run", action="store_true")
    pub_res = parser.add_mutually_exclusive_group()
    pub_res.add_argument("--pub-offline", action="store_true")
    pub_res.add_argument("--pub-enforce-lockfile", action="store_true")
    parser.add_argument("--no-precompile", action="store_true")
    parser.add_argument("--no-example", action="store_true")
    parser.add_argument("--pod-install", action="store_true")
    parser.add_argument("--pod-repo-update", action="store_true")
    parser.add_argument("--pod-clean-install", action="store_true")
    parser.add_argument("--pod-verbose", action="store_true")
    parser.add_argument("--pod-update", action="store_true")
    parser.add_argument("--pod-update-no-repo", action="store_true")
    parser.add_argument("--pod-deintegrate", action="store_true")
    parser.add_argument("--pod-cache-clean", action="store_true")
    parser.add_argument("--pod-repo-list", action="store_true")
    parser.add_argument("--pod-env", action="store_true")
    parser.add_argument("--open-xcode", action="store_true")
    parser.add_argument("--no-kill", action="store_true")
    args = parser.parse_args(argv)

    dry_run      = args.dry_run
    project_root = cfg.root
    flutter_exe  = find_flutter()

    def _confirm(prompt: str) -> bool:
        return confirm(prompt, auto_yes=args.yes, dry_run=dry_run)

    def _run(cmd, cwd=None, label=None):
        return run_cmd(cmd, cwd=cwd or project_root, label=label, dry_run=dry_run)

    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Clean & Reinstall{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {project_root}")

    selective_flags = [
        args.kill, args.clean, args.build_cache, args.android, args.ios,
        args.derived_data, args.get, args.pub_cache,
        args.upgrade, args.flutter_upgrade,
        args.pub_outdated, args.pub_deps, args.upgrade_dry_run,
        args.pod_install, args.pod_repo_update, args.pod_clean_install, args.pod_verbose,
        args.pod_update, args.pod_update_no_repo, args.pod_deintegrate,
        args.pod_cache_clean, args.pod_repo_list, args.pod_env, args.open_xcode,
    ]
    pub_modifiers = _build_pub_modifiers(args)
    run_all = not any(selective_flags)
    info(f"Mode         : {'FULL RESET' if run_all else 'selective'}{'  [DRY RUN]' if dry_run else ''}")
    if flutter_exe:
        ok(f"Flutter found: {flutter_exe}")
    else:
        warn("Flutter not found - Flutter-dependent steps will be skipped.")

    results: list[bool] = []
    _dispatch_steps(args, cfg, flutter_exe, pub_modifiers, results,
                    run_all=run_all, dry_run=dry_run,
                    confirm_fn=_confirm, run_fn=_run)
    return _print_clean_summary(results, dry_run=dry_run)
