"""Find unused dart files."""
from __future__ import annotations
import argparse
import os
import re
from pathlib import Path

from ftk.common import header, ok, err, info, warn, init_colours
from ftk.config import ProjectConfig


GENERATED_SUFFIXES = (
    ".g.dart", ".freezed.dart", ".config.dart", ".gr.dart",
    ".pb.dart", ".mocks.dart", ".reflectable.dart", ".chopper.dart", ".drift.dart",
)
GENERATED_NAMES = {"generated_plugin_registrant.dart"}
GENERATED_DIRS = {"generated"}
QUOTE_RE = re.compile(r"""['"]([^'"]+)['"]""")
IMPORT_RE = re.compile(r"^\s*import\b")
EXPORT_RE = re.compile(r"^\s*export\b")
PART_RE = re.compile(r"^\s*part\b(?!\s+of\b)")
COMMENT_RE = re.compile(r"^\s*//")
COND_IF_RE = re.compile(r"if\s*\(\s*dart\.library\.\w+\s*\)\s*['\"]([^'\"]+)['\"]")


def _is_generated(rel: Path) -> bool:
    if rel.name in GENERATED_NAMES:
        return True
    if any(rel.name.endswith(s) for s in GENERATED_SUFFIXES):
        return True
    if any(part in GENERATED_DIRS for part in rel.parts[:-1]):
        return True
    return False


def _strip_block_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i:i+2] == "/*":
            end = text.find("*/", i + 2)
            if end == -1:
                break
            block = text[i:end+2]
            out.append("\n" * block.count("\n"))
            i = end + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _join_continuation_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if IMPORT_RE.match(line) or EXPORT_RE.match(line) or PART_RE.match(line):
            while not stripped.endswith(";") and i + 1 < len(lines):
                i += 1
                stripped += " " + lines[i].strip()
            result.append(stripped)
        else:
            result.append(line)
        i += 1
    return result


def _resolve_relative(raw: str, source_file: Path, lib_dir: Path) -> str | None:
    resolved = (source_file.parent / raw).resolve()
    try:
        return resolved.relative_to(lib_dir.resolve()).as_posix()
    except ValueError:
        return None


def _classify_path(raw: str, source_file: Path, pkg_prefix: str, lib_dir: Path) -> str | None:
    if raw.startswith(pkg_prefix):
        tail = raw[len(pkg_prefix):]
        if _is_generated(Path(tail)):
            return None
        return tail
    if raw.endswith(".dart") and not raw.startswith("package:") and not raw.startswith("dart:"):
        return _resolve_relative(raw, source_file, lib_dir)
    return None


def _is_import_line(line: str, include_commented: bool) -> bool:
    """Return True if line is an import/export/part directive (or a commented one when opted-in)."""
    if IMPORT_RE.match(line) or EXPORT_RE.match(line) or PART_RE.match(line):
        return True
    if not COMMENT_RE.match(line):
        return False
    return include_commented and ("import" in line or "export" in line or "part" in line)


def _extract_paths(line: str, file: Path, pkg_prefix: str, lib_dir: Path) -> set[str]:
    """Extract resolved import paths from a single directive line."""
    result: set[str] = set()
    for cond in COND_IF_RE.findall(line):
        r = _classify_path(cond, file, pkg_prefix, lib_dir)
        if r:
            result.add(r)
    primary = COND_IF_RE.sub("", line)
    for raw in QUOTE_RE.findall(primary):
        r = _classify_path(raw, file, pkg_prefix, lib_dir)
        if r:
            result.add(r)
    return result


def _imports_from_file(file: Path, pkg_prefix: str, lib_dir: Path, include_commented: bool) -> set[str]:
    try:
        raw_text = file.read_text(encoding="utf-8")
    except Exception as exc:
        warn(f"Could not read {file}: {exc}")
        return set()
    text = _strip_block_comments(raw_text)
    lines = _join_continuation_lines(text.splitlines())
    result: set[str] = set()
    for line in lines:
        if _is_import_line(line, include_commented):
            result |= _extract_paths(line, file, pkg_prefix, lib_dir)
    return result


def _read_package_name(pubspec: Path) -> str | None:
    try:
        for line in pubspec.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^name:\s+(\S+)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return None

def _collect_files(lib_dir: Path):
    all_files = sorted(
        f for f in lib_dir.rglob("*.dart")
        if not _is_generated(f.relative_to(lib_dir))
    )
    file_map = {f.relative_to(lib_dir).as_posix(): f for f in all_files}
    return all_files, file_map


def _resolve_entry_points(cfg: ProjectConfig, root: Path, lib_dir: Path, file_map: dict):
    entry_rels = set()

    for ep in cfg.paths.entry_points:
        p = Path(root) / ep
        try:
            rel = p.relative_to(lib_dir).as_posix()
            entry_rels.add(rel)
        except ValueError:
            continue

    if not entry_rels:
        entry_rels.add("main.dart")

    queue = [file_map[e] for e in entry_rels if e in file_map]
    return entry_rels, queue


def _collect_reachable(queue, lib_dir: Path, pkg_prefix: str, file_map: dict, include_commented: bool):
    reachable: set[str] = set()

    while queue:
        f = queue.pop()
        rel = f.relative_to(lib_dir).as_posix()

        if rel in reachable:
            continue

        reachable.add(rel)

        for imp in _imports_from_file(f, pkg_prefix, lib_dir, include_commented):
            if imp not in reachable and imp in file_map:
                queue.append(file_map[imp])

    return reachable


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk unused", description="Find unused .dart files in lib/")
    parser.add_argument("--include-commented", action="store_true")
    args = parser.parse_args(argv)

    init_colours()

    root = cfg.root
    lib_dir = Path(root) / cfg.paths.lib_dir

    if not lib_dir.exists():
        err(f"'{lib_dir}' not found.")
        return 1

    package_name = _read_package_name(Path(root) / "pubspec.yaml")
    if not package_name:
        err("Package name not found in pubspec.yaml")
        return 1

    pkg_prefix = f"package:{package_name}/"
    info(f"Package : {package_name}")

    all_files, file_map = _collect_files(lib_dir)
    entry_rels, queue = _resolve_entry_points(cfg, root, lib_dir, file_map)
    reachable = _collect_reachable(
        queue, lib_dir, pkg_prefix, file_map, args.include_commented
    )

    unused = sorted(
        f.relative_to(lib_dir).as_posix()
        for f in all_files
        if f.relative_to(lib_dir).as_posix() not in entry_rels
        and f.relative_to(lib_dir).as_posix() not in reachable
    )

    header("Unused Files")

    if unused:
        for f in unused:
            err(f"{cfg.paths.lib_dir}/{f}")
    else:
        ok("All files are imported somewhere.")

    header("Summary")
    info(f"Total .dart files : {len(all_files)}")
    info(f"Entry points      : {len(entry_rels)}")
    info(f"Imported files    : {len(all_files) - len(unused) - len(entry_rels)}")
    info(f"Unused files      : {len(unused)}")

    print()
    return 0