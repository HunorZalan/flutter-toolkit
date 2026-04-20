"""flutter test with coverage + HTML report."""
from __future__ import annotations
import argparse
import os
import shutil

from ftk.common import (
    C, find_flutter, header, ok, warn, err, info,
    run_cmd, clear_flutter_lock,
)
from ftk.config import ProjectConfig


def _show_coverage(lcov_path: str) -> None:
    """Parse lcov.info and print a coverage summary."""
    if not os.path.isfile(lcov_path):
        warn("coverage/lcov.info not found - run with --coverage first.")
        return
    total = hit = 0
    try:
        with open(lcov_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("LF:"):
                    total += int(line[3:].strip())
                elif line.startswith("LH:"):
                    hit += int(line[3:].strip())
    except (OSError, ValueError) as exc:
        err(f"Failed to parse lcov.info: {exc}")
    if total:
        pct = hit / total * 100
        msg = f"Coverage: {hit}/{total} lines ({pct:.1f}%)"
        if pct >= 80:
            ok(msg)
        elif pct >= 50:
            warn(msg)
        else:
            err(msg)


def _gen_html_report(project_root: str, dry_run: bool) -> None:
    """Generate an HTML coverage report via genhtml."""
    lcov = os.path.join(project_root, "coverage", "lcov.info")
    if not os.path.isfile(lcov):
        warn("coverage/lcov.info not found - run with --coverage first.")
    elif not shutil.which("genhtml"):
        warn("genhtml not found - install lcov (apt/brew/choco).")
    else:
        out_dir = os.path.join(project_root, "coverage", "html")
        if run_cmd(["genhtml", lcov, "-o", out_dir, "--quiet"],
                   cwd=project_root, label="genhtml", dry_run=dry_run):
            ok(f"HTML report: {out_dir}/index.html")


def _build_test_cmd(flutter_exe, args):
    cmd = [flutter_exe, "test"]
    if args.coverage:
        cmd.append("--coverage")
    if args.reporter:
        cmd.extend(["--reporter", args.reporter])
    if args.concurrency:
        cmd.extend(["--concurrency", str(args.concurrency)])
    for tag in (args.tags or []):
        cmd.extend(["--tags", tag])
    for tag in (args.exclude_tags or []):
        cmd.extend(["--exclude-tags", tag])
    if args.name:
        cmd.extend(["--name", args.name])
    if args.plain_name:
        cmd.extend(["--plain-name", args.plain_name])
    if args.paths:
        cmd.extend(args.paths)
    return cmd


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk test", description="Flutter test runner with coverage support")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--coverage", "-c", action="store_true")
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--reporter", "-r", choices=["compact", "expanded", "json"])
    parser.add_argument("--concurrency", "-j", type=int)
    parser.add_argument("--tags", "-t", nargs="+")
    parser.add_argument("--exclude-tags", nargs="+")
    parser.add_argument("--name")
    parser.add_argument("--plain-name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project_root = cfg.root
    dry_run = args.dry_run

    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Test{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {project_root}")

    flutter_exe = find_flutter()
    if not flutter_exe:
        err("Flutter not found.")
        return 1
    ok(f"Flutter found: {flutter_exe}")
    clear_flutter_lock(flutter_exe)

    header("Flutter Test")
    cmd = _build_test_cmd(flutter_exe, args)
    success = run_cmd(cmd, cwd=project_root, label="flutter test", dry_run=dry_run)

    if args.coverage or args.html:
        header("Coverage Summary")
        _show_coverage(os.path.join(project_root, "coverage", "lcov.info"))
    if args.html:
        header("Generate HTML Coverage Report")
        _gen_html_report(project_root, dry_run)

    header("Summary")
    if success:
        ok("All tests passed.")
    else:
        err("Some tests failed - check output above.")
    print()
    return 0 if success else 1
