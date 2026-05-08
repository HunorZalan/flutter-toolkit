"""Flutter code generation — build_runner (+ flutter_gen_runner auto)."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from ftk.common import (
    C, find_flutter, header, ok, warn, err, info,
    run_cmd, clear_flutter_lock,
)
from ftk.config import ProjectConfig

_IS_WIN = sys.platform == "win32"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _dart_exe(flutter_exe: str) -> str:
    sdk = Path(flutter_exe).resolve().parent.parent
    dart = sdk / "bin" / "cache" / "dart-sdk" / "bin" / ("dart.exe" if _IS_WIN else "dart")
    if dart.is_file():
        return str(dart)
    warn("Bundled Dart SDK not found, falling back to 'dart' on PATH.")
    return "dart"


def _has_package(project_root: str, *package_names: str) -> bool:
    pubspec = Path(project_root) / "pubspec.yaml"
    if not pubspec.is_file():
        return False
    try:
        content = pubspec.read_text(encoding="utf-8")
        return any(pkg in content for pkg in package_names)
    except OSError:
        return False


# ── Steps ────────────────────────────────────────────────────────────────────

def _run_build(dart: str, *, project_root: str, dry_run: bool, results: list[bool]) -> None:
    header("build_runner build")
    info("flutter_gen_runner runs automatically if present in pubspec.")
    cmd = [dart, "run", "build_runner", "build"]
    results.append(run_cmd(cmd, cwd=project_root,
                           label="dart run build_runner build",
                           dry_run=dry_run))


def _run_watch(dart: str, *, project_root: str, dry_run: bool, results: list[bool]) -> None:
    header("build_runner watch")
    info("Watching for changes. Use the Stop button to exit.")
    info("flutter_gen_runner runs automatically if present in pubspec.")
    cmd = [dart, "run", "build_runner", "watch"]
    results.append(run_cmd(cmd, cwd=project_root,
                           label="dart run build_runner watch",
                           dry_run=dry_run))


def _run_clean(dart: str, *, project_root: str, dry_run: bool, results: list[bool]) -> None:
    header("build_runner clean")
    cmd = [dart, "run", "build_runner", "clean"]
    results.append(run_cmd(cmd, cwd=project_root,
                           label="dart run build_runner clean",
                           dry_run=dry_run))


# ── Banner / summary ─────────────────────────────────────────────────────────

def _print_banner(project_root: str, dry_run: bool) -> None:
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Code Generation{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {project_root}")
    if dry_run:
        info("Mode         : DRY RUN")


def _print_summary(results: list[bool], *, dry_run: bool) -> int:
    header("Summary")
    failed = results.count(False)
    total  = len(results)
    if total == 0:
        warn("No steps were executed.")
    elif dry_run:
        ok(f"Dry run complete — {total} step(s) would run.")
    elif failed == 0:
        ok(f"All {total} step(s) completed successfully.")
    else:
        err(f"{failed}/{total} step(s) failed.")
    print()
    return 0 if (dry_run or failed == 0) else 1


# ── Entry point ───────────────────────────────────────────────────────────────

def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ftk codegen",
        description="Code generation via build_runner (flutter_gen_runner runs automatically)",
    )
    parser.add_argument("--build", action="store_true",
                        help="build_runner build (one-shot)")
    parser.add_argument("--watch", action="store_true",
                        help="build_runner watch (continuous, use Stop to exit)")
    parser.add_argument("--clean", action="store_true",
                        help="build_runner clean (clear cache), then build")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project_root = cfg.root
    _print_banner(project_root, args.dry_run)

    flutter_exe = find_flutter()
    if not flutter_exe:
        err("Flutter not found.")
        return 1
    ok(f"Flutter found: {flutter_exe}")
    clear_flutter_lock(flutter_exe)

    if not _has_package(project_root, "build_runner"):
        warn("build_runner not found in pubspec.yaml.")
        warn("Add it to dev_dependencies: build_runner: ^2.x.x")
        return 1

    dart    = _dart_exe(flutter_exe)
    results: list[bool] = []

    run_all = not any([args.build, args.watch, args.clean])

    if args.clean:
        _run_clean(dart, project_root=project_root, dry_run=args.dry_run, results=results)

    if run_all or args.build:
        _run_build(dart, project_root=project_root, dry_run=args.dry_run, results=results)

    if args.watch:
        _run_watch(dart, project_root=project_root, dry_run=args.dry_run, results=results)

    return _print_summary(results, dry_run=args.dry_run)
