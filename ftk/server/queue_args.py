"""Validation helpers for the web UI's *queue* command (a chain of ftk commands).

The UI sends ``{"command": "queue", "args": [...]}`` where *args* look like::

    ["--keep-going", "build", "--web", "--yes", "+", "deploy", "-f", "prod", "--yes"]

Every step is validated with the very same rules as a normal single run (``prepare_one``
is the server's own ``_prepare_command``), so a queue can never do more than the UI
could do step by step.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

SEP = "+"
LEADING_FLAGS = frozenset({"--keep-going"})
STEP_EXCLUDED = frozenset({"queue", "notes", "help", "run"})
MAX_STEPS = 25


def split_steps(args: list) -> list:
    steps: list = [[]]
    for a in args:
        if a == SEP:
            steps.append([])
        else:
            steps[-1].append(a)
    return steps


def prepare_queue_command(cfg, commands_config: dict, args: list,
                          prepare_one: Callable) -> Optional[tuple]:
    """Return ``(cmd, merged_args, script)`` for the whole chain, or None when invalid."""
    block = commands_config.get("queue")
    if not block or block.get("disabled"):
        return None
    rest = list(args)
    lead: list = []
    while rest and rest[0] in LEADING_FLAGS:
        flag = rest.pop(0)
        if flag not in lead:
            lead.append(flag)
    steps = split_steps(rest)
    if len(steps) > MAX_STEPS or any(not s for s in steps):
        return None
    argv = list(lead)
    for i, step in enumerate(steps):
        name, flags = step[0], step[1:]
        if not isinstance(name, str) or name in STEP_EXCLUDED:
            return None
        prepared = prepare_one(cfg, commands_config, name, flags)
        if prepared is None:
            return None
        if i:
            argv.append(SEP)
        argv.append(name)
        argv.extend(prepared[1])  # validated flags (+ injected ones)
    cmd = [sys.executable, "-m", "ftk.pipeline", "--root", cfg.root, *argv]
    return cmd, argv, "pipeline"


def queue_timeout(command: str, merged: list, per_run: int) -> int:
    """The per-run time limit, multiplied by the number of steps for a queue."""
    if command != "queue":
        return per_run
    return per_run * (merged.count(SEP) + 1)
