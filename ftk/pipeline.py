"""Run several ftk commands one after another (a "queue").

Usage
    ftk pipeline [--keep-going] [--plan] <command> [flags] + <command> [flags] + ...
    python -m ftk.pipeline --root <project> <command> [flags] + ...

Example
    ftk pipeline build --web --yes + deploy -f prod --yes + backup --yes

* Steps are separated by a lone ``+``.
* The chain stops at the first failing step, unless --keep-going is given.
* --plan only prints the steps.
* Exit code: 0 when every step succeeded, otherwise the exit code of the first failing step.

The web UI's "Queue" tab runs exactly this. Lines such as ``=== Step 2/4: deploy ... ===`` and
``Step 2/4 finished (exit 0, 3.1s)`` are what the UI parses to show per-step progress.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

SEP = "+"
# Commands that may be chained (the real, runnable ones; not notes / help / run / queue).
ALLOWED = frozenset({
    "clean", "build", "deploy", "backup", "info", "analyze", "codegen",
    "icons", "unused", "translations", "test", "sonar",
})
USAGE = "usage: ftk pipeline [--keep-going] [--plan] <command> [flags] + <command> [flags] ..."


class UsageError(ValueError):
    pass


def parse(argv):
    """Return ``(keep_going, plan, steps)``; raises UsageError."""
    keep_going = plan = False
    rest = list(argv)
    while rest and rest[0] in ("--keep-going", "--plan"):
        flag = rest.pop(0)
        keep_going = keep_going or flag == "--keep-going"
        plan = plan or flag == "--plan"
    if not rest:
        raise UsageError("no steps given")
    steps = [[]]
    for tok in rest:
        if tok == SEP:
            steps.append([])
        else:
            steps[-1].append(tok)
    for n, step in enumerate(steps, 1):
        if not step:
            raise UsageError(f"step {n} is empty (stray '{SEP}'?)")
        if step[0] not in ALLOWED:
            raise UsageError(
                f"step {n}: '{step[0]}' cannot be queued (allowed: {', '.join(sorted(ALLOWED))})"
            )
    return keep_going, plan, steps


def _say(text: str = "", *, err: bool = False) -> None:
    print(text, file=sys.stderr if err else sys.stdout, flush=True)


def _ensure_utf8() -> None:
    """Piped output on Windows defaults to the ANSI code page; the UI expects UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _run_step(root: str, step: list) -> int:
    cmd = [sys.executable, "-m", "ftk", "--root", root, *step]
    try:
        # stdin/stdout/stderr are inherited on purpose: the server's prompt detection and
        # the answers it writes to our stdin reach the step unchanged.
        return subprocess.call(cmd, cwd=root)
    except OSError as exc:
        _say(f"✘ cannot start '{step[0]}': {exc}")
        return 127


def run(cfg, argv) -> int:
    _ensure_utf8()
    try:
        keep_going, plan, steps = parse(argv)
    except UsageError as exc:
        _say(f"✘ pipeline: {exc}", err=True)
        _say(USAGE, err=True)
        return 2
    total = len(steps)
    if plan:
        _say("=== Queue plan ===")
        for i, step in enumerate(steps, 1):
            _say(f"{i}. {' '.join(step)}")
        return 0

    results = []  # (label, exit code or None when skipped, seconds)
    first_failure = 0
    stopped = False
    began = time.monotonic()
    for i, step in enumerate(steps, 1):
        label = " ".join(step)
        if stopped:
            _say(f"– Step {i}/{total} skipped ({label})")
            results.append((label, None, 0.0))
            continue
        _say(f"\n=== Step {i}/{total}: {label} ===")
        t0 = time.monotonic()
        rc = _run_step(cfg.root, step)
        took = time.monotonic() - t0
        results.append((label, rc, took))
        if rc == 0:
            _say(f"✔ Step {i}/{total} finished (exit 0, {took:.1f}s)")
        else:
            _say(f"✘ Step {i}/{total} failed (exit {rc}, {took:.1f}s)")
            first_failure = first_failure or rc
            stopped = not keep_going

    _say("\n=== Queue summary ===")
    for n, (label, rc, took) in enumerate(results, 1):
        if rc is None:
            _say(f"– {n}. {label}  (skipped)")
        elif rc == 0:
            _say(f"✔ {n}. {label}  ({took:.1f}s)")
        else:
            _say(f"✘ {n}. {label}  (exit {rc}, {took:.1f}s)")
    done = sum(1 for _, rc, _ in results if rc == 0)
    _say(f"{done}/{total} step(s) succeeded in {time.monotonic() - began:.1f}s")
    return first_failure


def main(argv=None) -> int:
    """Entry point for ``python -m ftk.pipeline`` (used by the web UI server)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    root = os.getcwd()
    if argv[:1] == ["--root"] and len(argv) >= 2:
        root, argv = argv[1], argv[2:]
    from ftk.config import load_config

    try:
        return run(load_config(root), argv)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
