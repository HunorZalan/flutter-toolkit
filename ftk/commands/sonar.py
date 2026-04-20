"""Run sonar-scanner (parity with tool/python/sonar.py)."""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from ftk.common import C, header, ok, err, info, warn
from ftk.config import ProjectConfig


_DONE_MARKERS = ("EXECUTION SUCCESS", "EXECUTION FAILURE", "Total time:")


def _find_scanner(cfg: ProjectConfig) -> Path | None:
    sonar_cfg = cfg.integrations.sonar
    name = sonar_cfg.scanner_name if sonar_cfg else "sonar-scanner"

    # Build a list of candidate names.  The config may contain a
    # Windows-specific name like "sonar-scanner.7.1.0.cmd".  On macOS /
    # Linux we also try without the .cmd / .bat suffix and the plain
    # "sonar-scanner" fallback.
    candidates = [name]
    if sys.platform != "win32":
        for ext in (".cmd", ".bat"):
            if name.lower().endswith(ext):
                candidates.append(name[: -len(ext)])
                break
    if "sonar-scanner" not in candidates:
        candidates.append("sonar-scanner")

    for cand in candidates:
        local = Path(cfg.root) / cand
        if local.is_file():
            return local
        on_path = shutil.which(cand)
        if on_path:
            return Path(on_path)
    return None


def _clear_scanner_lock(project_root: str) -> None:
    lock_dir = Path(project_root) / ".scannerwork"
    if not lock_dir.exists():
        return
    warn("Removing stale .scannerwork lock...")
    try:
        shutil.rmtree(lock_dir)
        ok(".scannerwork removed.")
    except OSError as exc:
        warn(f"Could not remove .scannerwork: {exc}")
        if sys.platform == "win32":
            info("Try manually: rmdir /s /q .scannerwork")
        else:
            info("Try manually: rm -rf .scannerwork")


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk sonar", description="Run sonar-scanner")
    parser.parse_args(argv)

    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  SonarQube Scanner{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {cfg.root}")

    scanner = _find_scanner(cfg)
    if scanner is None:
        name = cfg.integrations.sonar.scanner_name if cfg.integrations.sonar else "sonar-scanner"
        err(f"Scanner not found: {name} (searched project root and PATH).")
        return 1
    ok(f"Scanner found: {scanner}")
    _clear_scanner_lock(cfg.root)

    info(f"$ {scanner.name}")
    print()
    if sys.platform == "win32":
        cmd = ["cmd", "/c", str(scanner)]
    else:
        cmd = [str(scanner)]
    try:
        proc = subprocess.Popen(
            cmd, cwd=cfg.root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        err(f"Cannot execute: {scanner}")
        return 1

    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        print(line, end="", flush=True)
        if any(m in line for m in _DONE_MARKERS):
            break
    proc.stdout.close()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    _clear_scanner_lock(cfg.root)

    print()
    if proc.returncode == 0:
        ok("SonarScanner finished successfully.")
    else:
        err(f"SonarScanner exited with code {proc.returncode}")
    return proc.returncode or 0
