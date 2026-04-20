"""flutter analyze + dart fix + dart format."""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

from ftk.common import (
    C, find_flutter, header, ok, warn, err, info,
    run_cmd, run_capture, clear_flutter_lock,
)
from ftk.config import ProjectConfig


def _dart_cmd(flutter_exe: str, *args: str) -> list[str]:
    sdk = Path(flutter_exe).resolve().parent.parent
    dart = sdk / "bin" / "cache" / "dart-sdk" / "bin" / ("dart.exe" if sys.platform == "win32" else "dart")
    if dart.is_file():
        return [str(dart), *args]
    warn("Bundled Dart SDK not found, falling back to 'flutter dart'")
    return [flutter_exe, "dart", *args]


def _count_metrics(lib_path: Path) -> bool:
    """Count lines of code, comments, and blanks in all Dart files."""
    dart_files = list(lib_path.rglob("*.dart"))
    total_lines = total_code = total_comments = total_blank = 0
    for f in dart_files:
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                total_lines += 1
                s = line.strip()
                if not s:
                    total_blank += 1
                elif s.startswith("//") or s.startswith("/*") or s.startswith("*"):
                    total_comments += 1
                else:
                    total_code += 1
        except (OSError, UnicodeDecodeError):
            pass
    ok(f"Dart files    : {len(dart_files)}")
    ok(f"Total lines   : {total_lines:,}")
    info(f"  Code        : {total_code:,}")
    info(f"  Comments    : {total_comments:,}")
    info(f"  Blank       : {total_blank:,}")
    if total_code > 0:
        info(f"  Comment ratio: {total_comments / total_code * 100:.1f}%")
    return True


def _run_analyze(flutter_exe, args, run_fn, results):
    header("flutter analyze")
    cmd = [flutter_exe, "analyze"]
    if args.fatal_infos:
        cmd.append("--fatal-infos")
    if args.no_fatal_warnings:
        cmd.append("--no-fatal-warnings")
    results.append(run_fn(cmd, label="flutter analyze"))


def _run_format(flutter_exe, args, lib_dir, run_fn, results):
    cmd = list(_dart_cmd(flutter_exe, "format"))
    if args.line_length:
        cmd.extend(["--line-length", str(args.line_length)])
    cmd.append(lib_dir)
    header("dart format")
    results.append(run_fn(cmd, label="dart format"))


def _run_format_check(flutter_exe, args, lib_dir, run_fn, results):
    cmd = list(_dart_cmd(flutter_exe, "format"))
    if args.line_length:
        cmd.extend(["--line-length", str(args.line_length)])
    cmd.extend(["--set-exit-if-changed", lib_dir])
    header("dart format (check)")
    results.append(run_fn(cmd, label="dart format (check)"))


def _validate_project(project_root):
    """Check project and find flutter. Returns flutter_exe or None on error."""
    if not os.path.isfile(os.path.join(project_root, "pubspec.yaml")):
        err(f"No pubspec.yaml in {project_root} - not a Flutter project.")
        return None
    flutter_exe = find_flutter()
    if not flutter_exe:
        err("Flutter not found.")
        return None
    if run_capture([flutter_exe, "--version"], cwd=project_root) is None:
        err("Flutter found but failed to execute.")
        return None
    ok(f"Flutter found: {flutter_exe}")
    clear_flutter_lock(flutter_exe)
    return flutter_exe

def _run_metrics(project_root: str, lib_dir: str, results: list[bool]) -> None:
    """Collect and display code metrics, appending success/failure to results."""
    header("Code Metrics")
    lib_path = Path(project_root) / lib_dir
    if not lib_path.is_dir():
        warn(f"{lib_dir}/ directory not found.")
        results.append(False)
    else:
        results.append(_count_metrics(lib_path))

def _run_fix_steps(flutter_exe, args, run_fn, results: list[bool]) -> None:
    if args.fix_preview:
        header("dart fix --dry-run")
        results.append(run_fn([*_dart_cmd(flutter_exe, "fix"), "--dry-run"], label="dart fix --dry-run"))
    if args.fix:
        header("dart fix --apply")
        results.append(run_fn([*_dart_cmd(flutter_exe, "fix"), "--apply"], label="dart fix --apply"))


def _dispatch_checks(flutter_exe, args, project_root: str, lib_dir: str, run_fn) -> list[bool]:
    run_all = not any([args.analyze, args.fix, args.fix_preview, args.format, args.format_check, args.metrics])
    results: list[bool] = []

    if run_all or args.analyze:
        _run_analyze(flutter_exe, args, run_fn, results)
    _run_fix_steps(flutter_exe, args, run_fn, results)
    if run_all or args.format:
        _run_format(flutter_exe, args, lib_dir, run_fn, results)
    if args.format_check:
        _run_format_check(flutter_exe, args, lib_dir, run_fn, results)
    if run_all or args.metrics:
        _run_metrics(project_root, lib_dir, results)

    return results


def _print_summary(results: list[bool]) -> int:
    header("Summary")
    failed = results.count(False)
    if failed == 0:
        ok(f"All {len(results)} check(s) passed.")
    else:
        err(f"{failed}/{len(results)} check(s) failed.")
    print()
    return 0 if failed == 0 else 1


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk analyze", description="Static analysis, formatting & metrics")
    parser.add_argument("--analyze", "-a", action="store_true")
    parser.add_argument("--fatal-infos", action="store_true")
    parser.add_argument("--no-fatal-warnings", action="store_true")
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--fix-preview", action="store_true")
    parser.add_argument("--format", "-f", action="store_true")
    parser.add_argument("--format-check", action="store_true")
    parser.add_argument("--line-length", "-l", type=int, metavar="N")
    parser.add_argument("--metrics", "-m", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Analyze & Format{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {cfg.root}")

    flutter_exe = _validate_project(cfg.root)
    if not flutter_exe:
        return 1

    def _run(cmd, label=None):
        return run_cmd(cmd, cwd=cfg.root, label=label, dry_run=args.dry_run)

    results = _dispatch_checks(flutter_exe, args, cfg.root, cfg.paths.lib_dir, _run)
    return _print_summary(results)
