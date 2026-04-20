"""Scaffold an `ftk.yaml` in the current project."""
from __future__ import annotations
import argparse
from pathlib import Path

from ftk.common import header, ok, warn, err, info, init_colours
from ftk.config import ProjectConfig, CONFIG_FILENAME, write_template


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    init_colours()
    parser = argparse.ArgumentParser(prog="ftk init", description="Create a starter ftk.yaml.")
    parser.add_argument("--with-flavors", action="store_true",
                        help="Include a sample flavors section.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing ftk.yaml.")
    args = parser.parse_args(argv)

    header("Initialise ftk.yaml")
    root = cfg.root
    dst = Path(root) / CONFIG_FILENAME
    info(f"Target: {dst}")
    if dst.exists() and not args.force:
        warn(f"{CONFIG_FILENAME} already exists. Use --force to overwrite.")
        return 1
    if args.force and dst.exists():
        dst.unlink()
    path = write_template(root, with_flavors=args.with_flavors)
    ok(f"Created {path}")
    info("Next: edit the file, then run `ftk` or `ftk help`.")
    return 0
