"""Top-level CLI for flutter-toolkit.

Exposes sub-commands that mirror the legacy `tool/python/*` scripts while
accepting a common `--project` / `--root` flag for multi-project selection.

    ftk build --apk --flavor flavorA
    ftk clean
    ftk server start --port 8742
    ftk projects add /path/to/project --id myapp
"""
from __future__ import annotations
import argparse
import sys
from typing import Callable

from ftk import __version__
from ftk.common import init_colours, C, info, ok, err, warn
from ftk.projects import (
    resolve as resolve_project,
    list_projects, add_project, remove_project, set_last_project_id, find_project,
)
from ftk.config import ProjectConfig, load_config, write_template


# Map sub-command -> entrypoint module. Entrypoints each expose `run(cfg, argv)`
# where `cfg` is a ProjectConfig and `argv` is the remaining argv list.
COMMANDS: dict[str, tuple[str, str]] = {
    "clean":        ("ftk.commands.clean",        "Clean Flutter caches, locks, and build artifacts"),
    "build":        ("ftk.commands.build",        "Build web / APK / AAB / iOS / IPA / desktop"),
    "info":         ("ftk.commands.info",         "Report Flutter/Dart/SDK environment and artefact sizes"),
    "codegen":      ("ftk.commands.codegen",      "Run code generation tasks"),
    "analyze":      ("ftk.commands.analyze",      "flutter analyze + dart fix + dart format"),
    "test":         ("ftk.commands.test",         "flutter test with coverage & lcov HTML report"),
    "icons":        ("ftk.commands.icons",        "Generate icons / splash / favicons / notification icons"),
    "unused":       ("ftk.commands.unused",       "Find unused .dart files"),
    "translations": ("ftk.commands.translations", "Validate translation JSONs and key usage"),
    "deploy":       ("ftk.commands.deploy",       "Deploy web build via FTP/FTPS/SFTP"),
    "backup":       ("ftk.commands.backup",       "Create archive backup of the project"),
    "sonar":        ("ftk.commands.sonar",        "Run sonar-scanner"),
    "run":          ("ftk.commands.run_menu",     "Interactive menu (legacy run.py)"),
    "help":         ("ftk.commands.help_cmd",     "Topic-based help"),
    "server":       ("ftk.commands.server_cmd",   "Start / stop / status of the FastAPI UI server"),
    "projects":     ("ftk.commands.projects_cmd", "Manage the multi-project registry"),
    "init":         ("ftk.commands.init_cmd",     "Create a starter ftk.yaml"),
}

ALIASES: dict[str, str] = {
    "c":   "clean",
    "b":   "build",
    "i":   "info",
    "ic":  "icons",
    "u":   "unused",
    "t":   "translations",
    "te":  "test",
    "a":   "analyze",
    "h":   "help",
    "d":   "deploy",
    "bk":  "backup",
    "s":   "sonar",
    "srv": "server",
    "proj": "projects",
    "ls":  "projects",  # convenient shortcut
}


def _print_banner() -> None:
    print(f"{C.BOLD}{C.CYAN}flutter-toolkit{C.RESET} {C.BOLD}v{__version__}{C.RESET}")


def _print_help() -> None:
    _print_banner()
    print("\nUsage: ftk [--project ID | --root DIR] <command> [args...]\n")
    print("Commands:")
    width = max(len(k) for k in COMMANDS)
    for k, (_, desc) in COMMANDS.items():
        print(f"  {k.ljust(width)}  {desc}")
    print("\nAliases: " + ", ".join(f"{a}={t}" for a, t in ALIASES.items()))
    print("\nGlobal flags:")
    print("  --project ID    Select a project from the registry")
    print("  --root DIR      Override project root")
    print("  --version       Print ftk version")
    print("  --help          Show this help\n")
    print("Examples:")
    print("  ftk build --apk --flavor flavorA")
    print("  ftk clean --no-kill")
    print("  ftk --project myapp info")
    print("  ftk projects add . --id myapp")
    print("  ftk server start")


def _split_global_flags(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", "-P", dest="project")
    parser.add_argument("--root", "-R", dest="root")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--help", "-h", action="store_true")
    args, rest = parser.parse_known_args(argv)
    return args, rest


def _import_entry(modpath: str) -> Callable[[ProjectConfig, list[str]], int]:
    mod = __import__(modpath, fromlist=["run"])
    fn = getattr(mod, "run", None)
    if not callable(fn):
        raise SystemExit(f"Command module {modpath} has no run()")
    return fn


def _resolve_help_flags(globals_, cmd_name, cmd_args):
    is_bare_help = globals_.help and not cmd_args and cmd_name in ("help", "-h", "--help")
    if is_bare_help:
        _print_help()
        sys.exit(0)
    if globals_.help:
        cmd_args = ["--help", *cmd_args]
    return cmd_args


def _resolve_config(globals_, needs_project_cfg):
    try:
        if needs_project_cfg:
            return resolve_project(cli_root=globals_.root, cli_project=globals_.project)
        from ftk.common import resolve_project_root
        root = globals_.root or resolve_project_root(None)
        return load_config(root)
    except SystemExit:
        raise
    except Exception as exc:
        err(f"Failed to resolve project: {exc}")
        sys.exit(2)


_TOGGLE_COMMANDS = frozenset((
    "clean", "build", "info", "analyze", "test", "icons",
    "unused", "translations", "deploy", "backup", "sonar", "run",
))


def _resolve_command(cmd_name: str, cmd_args: list[str]) -> tuple[str, list[str]]:
    """Normalize aliases and handle bare help requests. May call sys.exit."""
    if cmd_name in ALIASES:
        cmd_name = ALIASES[cmd_name]
    if cmd_name in ("help", "--help", "-h") and not cmd_args:
        _print_help()
        sys.exit(0)
    if cmd_name not in COMMANDS:
        err(f"Unknown command: {cmd_name}")
        info("Run `ftk --help` to see the full list.")
        sys.exit(2)
    return cmd_name, cmd_args


def _load_and_run(cmd_name: str, cmd_args: list[str], cfg: ProjectConfig) -> None:
    """Import command module, check toggles, and run. May call sys.exit."""
    modpath, _desc = COMMANDS[cmd_name]
    try:
        entry = _import_entry(modpath)
    except ImportError as exc:
        err(f"Could not load command {cmd_name!r}: {exc}")
        sys.exit(2)
    if cmd_name in _TOGGLE_COMMANDS and not cfg.command_enabled(cmd_name):
        warn(f"Command '{cmd_name}' is disabled in ftk.yaml (or its integration section is missing).")
        sys.exit(0)
    sys.exit(entry(cfg, cmd_args) or 0)


def main(argv: list[str] | None = None) -> None:
    init_colours()
    raw = list(sys.argv[1:] if argv is None else argv)
    globals_, rest = _split_global_flags(raw)

    if globals_.version:
        _print_banner()
        sys.exit(0)

    if not rest:
        _print_help()
        sys.exit(0)

    cmd_name = rest[0]
    cmd_args = _resolve_help_flags(globals_, cmd_name, rest[1:])
    cmd_name, cmd_args = _resolve_command(cmd_name, cmd_args)

    needs_project_cfg = cmd_name not in ("projects", "init", "help")
    cfg = _resolve_config(globals_, needs_project_cfg)

    if needs_project_cfg and cfg.warnings:
        for w in cfg.warnings:
            warn(w)

    if globals_.project and needs_project_cfg:
        set_last_project_id(globals_.project)

    _load_and_run(cmd_name, cmd_args, cfg)


if __name__ == "__main__":
    main()
