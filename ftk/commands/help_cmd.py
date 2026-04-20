"""Show help for ftk commands."""
from __future__ import annotations
import importlib
import sys

from ftk.common import C, header, info, ok, warn, err, init_colours
from ftk.config import ProjectConfig


OVERVIEW = """\
flutter-toolkit (ftk) - project-agnostic helper for Flutter apps.

Usage:
  ftk [--project ID|--root PATH] <command> [options]
  ftk <command> --help         Show full option list for a command.

Global options:
  --project, -P  ID       Use the project registered with this id.
  --root, -r     PATH     Use this directory as the project root.
  --version               Print version and exit.
  --help, -h              Show this help.

Configuration:
  ftk init                Generate an ftk.yaml starter file.
  ftk projects ls|add|rm|use   Manage the global project registry.

Environment:
  FTK_HOME                Override the registry directory (default: ~/.ftk).
  FTK_PROJECT             Use a registered project by id.
  FTK_PROJECT_ROOT        Use this path as the project root.
"""


def _list_commands(cfg: ProjectConfig) -> None:
    from ftk.cli import COMMANDS, ALIASES
    header("Available commands")
    alias_map: dict[str, list[str]] = {}
    for a, target in ALIASES.items():
        alias_map.setdefault(target, []).append(a)
    for name, (_mod, desc) in COMMANDS.items():
        aliases = alias_map.get(name, [])
        alias_str = f" ({', '.join(aliases)})" if aliases else ""
        enabled = cfg.command_enabled(name) if cfg else True
        tag = "" if enabled else f"  {C.YELLOW}(disabled){C.RESET}"
        print(f"  {C.BOLD}{name:<14}{C.RESET}{alias_str:<10}  {desc}{tag}")


def _show_one(cmd_name: str, cfg: ProjectConfig) -> int:
    from ftk.cli import COMMANDS, ALIASES
    if cmd_name in ALIASES:
        cmd_name = ALIASES[cmd_name]
    if cmd_name not in COMMANDS:
        err(f"Unknown command: {cmd_name}")
        return 1
    mod_path, _desc = COMMANDS[cmd_name]
    try:
        module = importlib.import_module(mod_path)
    except ImportError as exc:
        err(f"Could not import {mod_path}: {exc}")
        return 1
    if not hasattr(module, "run"):
        err(f"{mod_path} has no run() entry point.")
        return 1
    print()
    try:
        module.run(cfg, ["--help"])
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise
    return 0


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    init_colours()
    if not argv:
        print(OVERVIEW)
        _list_commands(cfg)
        print()
        return 0
    return _show_one(argv[0].lstrip("-"), cfg)
