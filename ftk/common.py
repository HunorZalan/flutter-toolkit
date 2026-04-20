"""Shared utilities for flutter-toolkit (ftk)."""
from __future__ import annotations
import os
import subprocess
import sys
import shutil
from pathlib import Path


def resolve_project_root(cli_root: str | None = None) -> str:
    """
    Priority:
      1. cli_root argument (--root flag, --project via registry)
      2. FLUTTER_PROJECT_ROOT env var
      3. FTK_PROJECT_ROOT env var (alias)
      4. Walk up from cwd until pubspec.yaml or ftk.yaml is found
      5. Fallback: cwd
    """
    if cli_root:
        return os.path.abspath(cli_root)
    env = os.environ.get("FLUTTER_PROJECT_ROOT") or os.environ.get("FTK_PROJECT_ROOT")
    if env:
        return os.path.abspath(env)
    here = Path(os.getcwd())
    for parent in [here, *here.parents]:
        if (parent / "ftk.yaml").exists() or (parent / "pubspec.yaml").exists():
            return str(parent)
    return str(here)


class C:
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

    @staticmethod
    def strip() -> None:
        for attr in ("RED", "YELLOW", "GREEN", "CYAN", "BOLD", "RESET"):
            setattr(C, attr, "")


def init_colours() -> None:
    """Disable ANSI colours when not running in a terminal."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        try:
            os.system("")
        except OSError:
            pass
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        C.strip()


def header(title: str) -> None:
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")


def ok(msg: str)   -> None: print(f"  {C.GREEN}\u2714  {msg}{C.RESET}")
def warn(msg: str) -> None: print(f"  {C.YELLOW}\u26a0  {msg}{C.RESET}")
def err(msg: str)  -> None: print(f"  {C.RED}\u2718  {msg}{C.RESET}")
def info(msg: str) -> None: print(f"     {msg}")


def skip(label: str, reason: str = "skipped by user") -> None:
    warn(f"{label} \u2013 {reason}")


def confirm(prompt: str, *, auto_yes: bool = False, dry_run: bool = False) -> bool:
    if dry_run:
        info(f"[dry-run] would ask: {prompt}")
        return False
    if auto_yes:
        info(f"[--yes] {prompt} \u2192 confirmed automatically")
        return True
    try:
        answer = input(f"\n  {C.YELLOW}{prompt} [y/N]: {C.RESET}").strip().lower()
        return answer in ("y", "yes", "i")
    except (KeyboardInterrupt, EOFError):
        print()
        return False


def run_cmd(
    cmd: list[str],
    *,
    cwd: str | None = None,
    label: str | None = None,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> bool:
    display = label or " ".join(cmd)
    if dry_run:
        info(f"[dry-run] would run: $ {display}")
        return True
    info(f"$ {display}")
    try:
        merged_env = None
        if env:
            merged_env = {**os.environ, **env}
        result = subprocess.run(cmd, cwd=cwd, env=merged_env)
        if result.returncode == 0:
            ok(f"{display}  \u2192  OK")
            return True
        err(f"{display}  \u2192  exit code {result.returncode}")
        return False
    except FileNotFoundError:
        err(f"Command not found: {cmd[0]}")
        return False
    except Exception as exc:
        err(f"{display}  \u2192  {exc}")
        return False


def run_capture(cmd: list[str], *, cwd: str | None = None) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return result.stdout.strip()
    except OSError:
        return f"[{cmd[0]} not found]"
    except Exception as exc:
        return f"[error: {exc}]"


_FLUTTER_BAT = "flutter.bat"


def _flutter_search_paths() -> list[str]:
    candidates: list[str] = []
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        for base in [
            r"C:\flutter\bin",
            r"C:\src\flutter\bin",
            os.path.join(home, "flutter", "bin"),
            os.path.join(home, "fvm", "default", "bin"),
        ]:
            candidates.append(os.path.join(base, _FLUTTER_BAT))
            candidates.append(os.path.join(base, "flutter"))
    else:
        candidates.extend([
            os.path.join(home, ".fvm", "default", "bin", "flutter"),
            os.path.join(home, "fvm", "default", "bin", "flutter"),
            "/usr/local/bin/flutter",
            os.path.join(home, "development", "flutter", "bin", "flutter"),
            os.path.join(home, "Documents", "flutter", "bin", "flutter"),
            os.path.join(home, "flutter", "bin", "flutter"),
            "/opt/homebrew/bin/flutter",
            "/snap/bin/flutter",
        ])
    return candidates


def _probe_executable(candidate: str) -> bool:
    try:
        p = Path(candidate)
        if not p.is_file():
            return False
        if sys.platform == "win32":
            return p.suffix.lower() in (".bat", ".exe", "")
        return os.access(candidate, os.X_OK)
    except OSError:
        return False


def find_flutter() -> str | None:
    quick = shutil.which("flutter")
    if quick:
        return quick
    if sys.platform == "win32":
        quick_bat = shutil.which(_FLUTTER_BAT)
        if quick_bat:
            return quick_bat
    seen: set[str] = set()
    for candidate in _flutter_search_paths():
        if candidate in seen:
            continue
        seen.add(candidate)
        if _probe_executable(candidate):
            return candidate
    return None


def fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def dir_size(path: str) -> int:
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += dir_size(entry.path)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _find_flutter_sdk_root(flutter_exe: str | None) -> str | None:
    if not flutter_exe:
        return None
    p = Path(flutter_exe).resolve()
    if p.parent.name == "bin":
        return str(p.parent.parent)
    return None


def clear_flutter_lock(flutter_exe: str | None) -> None:
    sdk = _find_flutter_sdk_root(flutter_exe)
    if not sdk:
        return
    lockfile = Path(sdk) / "bin" / "cache" / "lockfile"
    if not lockfile.exists():
        return
    try:
        lockfile.unlink()
        warn(f"Removed stale Flutter lockfile: {lockfile}")
    except OSError:
        if sys.platform == "win32":
            _force_release_lockfile(lockfile)
        else:
            err(f"Could not remove lockfile: {lockfile}")
            info("Try manually: rm " + str(lockfile))


def _force_release_lockfile(lockfile: Path) -> None:
    import time
    warn("Lockfile in use - killing blocking processes...")
    for name in ("dart.exe", _FLUTTER_BAT):
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    time.sleep(1)
    try:
        lockfile.unlink()
        ok(f"Lockfile removed: {lockfile}")
    except OSError as exc:
        err(f"Still cannot remove lockfile: {exc}")
        info("Try manually: taskkill /F /IM dart.exe && del " + str(lockfile))


def missing_dep(pkg: str, extra: str) -> None:
    """Uniform error shown when an optional dependency is missing."""
    err(f"Missing optional dependency '{pkg}'.")
    info(f"Install with: pip install 'flutter-toolkit[{extra}]'  (or [all])")
