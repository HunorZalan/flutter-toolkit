"""Manage the global flutter-toolkit project registry."""
from __future__ import annotations
import argparse
import os

from ftk.common import C, header, ok, warn, err, info, init_colours
from ftk.config import ProjectConfig
from ftk.projects import (
    list_projects, add_project, remove_project, find_project,
    set_last_project_id, clear_last_project, registry_file,
)


def _cmd_list(_args) -> int:  # noqa: S3516 – always 0; listing never fails
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
    return 0


def _cmd_remove(args) -> int:
    if remove_project(args.id):
        ok(f"Removed project {args.id!r}")
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


def run(cfg: ProjectConfig, argv: list[str]) -> int:  # noqa: S1172 – cfg required by command interface
    init_colours()
    parser = argparse.ArgumentParser(prog="ftk projects", description="Manage the project registry.")
    sub = parser.add_subparsers(dest="sub", metavar="{list,add,rm,use,clear}")

    sub.add_parser("list", aliases=["ls"], help="List registered projects.")
    p_add = sub.add_parser("add", help="Register a project directory.")
    p_add.add_argument("path")
    p_add.add_argument("--id", help="Short id (default: folder name).")
    p_add.add_argument("--name", help="Human-readable name.")
    p_rm = sub.add_parser("rm", aliases=["remove"], help="Remove a project.")
    p_rm.add_argument("id")
    p_use = sub.add_parser("use", help="Mark a project as active (default for next run).")
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
