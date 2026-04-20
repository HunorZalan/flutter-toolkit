"""Interactive menu (same spirit as the original tool/python/run.py)."""
from __future__ import annotations
import importlib
import shlex

from ftk.common import C, init_colours, err
from ftk.config import ProjectConfig


def _banner(cfg: ProjectConfig) -> None:
    print(f"\n  {C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}  flutter-toolkit  -  {cfg.name or cfg.id or 'project'}{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"  {C.BOLD}Root: {cfg.root}{C.RESET}")


def _menu_items(cfg: ProjectConfig) -> list[tuple[str, str, str]]:
    from ftk.cli import COMMANDS, ALIASES
    alias_map: dict[str, str] = {}
    for a, target in ALIASES.items():
        if len(a) <= 2 and target not in alias_map:
            alias_map[target] = a
    items: list[tuple[str, str, str]] = []
    for name, (_mod, desc) in COMMANDS.items():
        if name in ("help", "server", "projects", "init", "run"):
            continue
        if not cfg.command_enabled(name):
            continue
        items.append((name, alias_map.get(name, ""), desc))
    return items


def _print_menu(items: list[tuple[str, str, str]]) -> None:
    print()
    for i, (name, alias, desc) in enumerate(items, 1):
        a = f"({alias})" if alias else "   "
        print(f"    {C.BOLD}{i:>2}{C.RESET}  {name:<14} {a:<4}  {desc}")
    print(f"    {C.BOLD} 0{C.RESET}  exit")
    print()


def _resolve(raw: str, items: list[tuple[str, str, str]]) -> str | None:
    from ftk.cli import COMMANDS, ALIASES
    raw = raw.strip().lower()
    if raw in ("0", "q", "quit", "exit", ""):
        return None
    try:
        idx = int(raw)
        if 1 <= idx <= len(items):
            return items[idx - 1][0]
    except ValueError:
        pass
    if raw in COMMANDS:
        return raw
    if raw in ALIASES:
        return ALIASES[raw]
    return raw


def _dispatch(cmd_name: str, args: list[str], cfg: ProjectConfig) -> int:
    from ftk.cli import COMMANDS
    if cmd_name not in COMMANDS:
        err(f"Unknown command: {cmd_name}")
        return 1
    mod_path, _ = COMMANDS[cmd_name]
    module = importlib.import_module(mod_path)
    try:
        return module.run(cfg, args)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise
        return 0
    except KeyboardInterrupt:
        return 130


_HELP_TEXT = """\
Usage: ftk run [--help]

Interactive launcher menu. With no args, shows the list of enabled ftk
commands and prompts for a selection; after each command it pauses with
"Press Enter to continue" so you can inspect output.

  --help, -h   Show this help and exit.

Use `ftk <command> --help` to see options for individual commands.
"""


def _prompt_params(name: str) -> list[str] | None:
    """Ask for parameters; returns None on Ctrl-C/EOF (skip this command)."""
    try:
        raw = input(f"  {C.YELLOW}[{name}]{C.RESET} Parameters (Enter for defaults): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None
    try:
        return shlex.split(raw) if raw else []
    except ValueError:
        return raw.split()


def _wait_for_enter() -> bool:
    """Pause after a command; returns False if the user wants to quit."""
    try:
        input(f"\n  {C.BOLD}Press Enter to continue...{C.RESET}")
        return True
    except (KeyboardInterrupt, EOFError):
        return False


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    if argv and argv[0] in ("--help", "-h", "help"):
        print(_HELP_TEXT)
        return 0
    init_colours()
    _banner(cfg)
    _bye = f"\n\n  {C.CYAN}Bye!{C.RESET}\n"
    last_code = 0
    while True:
        items = _menu_items(cfg)
        _print_menu(items)
        try:
            raw = input(f"  {C.BOLD}Choose [0-{len(items)}]: {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(_bye)
            return last_code
        name = _resolve(raw, items)
        if name is None:
            print(_bye)
            return last_code
        params = _prompt_params(name)
        if params is None:
            continue
        last_code = _dispatch(name, params, cfg)
        msg = f"{C.GREEN}\u2714 Done.{C.RESET}" if last_code == 0 else f"{C.RED}\u2718 Exited with code {last_code}.{C.RESET}"
        print(f"\n  {msg}")
        if not _wait_for_enter():
            print(_bye)
            return last_code
