"""Create archive backup of the project."""
from __future__ import annotations
import argparse
import os
import re
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

from ftk.common import header, ok, warn, err, info, confirm, fmt_size, missing_dep
from ftk.config import ProjectConfig


FORMATS: dict[str, dict] = {
    "zip":     {"ext": ".zip",     "label": "ZIP (.zip)  -  universal"},
    "tar.gz":  {"ext": ".tar.gz",  "label": "TAR+GZip (.tar.gz)  -  fast"},
    "tar.bz2": {"ext": ".tar.bz2", "label": "TAR+BZip2 (.tar.bz2)  -  balanced"},
    "tar.xz":  {"ext": ".tar.xz",  "label": "TAR+XZ (.tar.xz)  -  best ratio"},
    "tar":     {"ext": ".tar",     "label": "TAR (.tar)  -  no compression"},
    "7z":      {"ext": ".7z",      "label": "7-Zip (.7z)  -  encrypted headers"},
    "tar.zst": {"ext": ".tar.zst", "label": "TAR+Zstd (.tar.zst)  -  modern/fast"},
}
TAR_MODES = {"tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz", "tar": "w:"}

_BACKUP_RE = re.compile(r"^backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.")
_BACKUP_GLOB = "backup_*"


class _Progress:
    def __init__(self, total: int):
        self.total = total
        self.last = 0.0
        self.width = 30

    def update(self, current: int, raw_bytes: int, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last < 0.1:
            return
        self.last = now
        filled = int(self.width * current / self.total) if self.total else 0
        bar = "#" * filled + "." * (self.width - filled)
        print(
            f"  [{bar}] {current:>{len(str(self.total))}}/{self.total}  {fmt_size(raw_bytes)}",
            flush=True,
        )


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M")


def _default_output_dir(project_root: str) -> Path:
    root = Path(project_root)
    return root.parent / f"{root.name}_backups"


def _build_output_path(project_root: str, fmt: str, output: str | None) -> Path:
    ext = FORMATS[fmt]["ext"]
    name = f"backup_{_timestamp()}{ext}"
    if output:
        p = Path(output).expanduser()
        return p / name if p.is_dir() or not p.suffix else p
    return _default_output_dir(project_root) / name


def _should_skip_file(p: Path, root: Path, dirpath: str, excludes: set[str], out_resolved):
    if dirpath == str(root) and p.name in excludes:
        return True
    rel_parts = p.relative_to(root).parts
    is_root_backup = len(rel_parts) == 1 and _BACKUP_RE.match(rel_parts[0])
    if is_root_backup:
        return True
    try:
        if out_resolved and p.resolve() == out_resolved:
            return True
    except OSError:
        pass
    return False


def _collect_files(project_root: str, excludes: set[str], out_path: Path) -> list[Path]:
    root = Path(project_root)
    try:
        out_resolved = out_path.resolve()
    except OSError:
        out_resolved = None
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        for fn in filenames:
            p = Path(dirpath) / fn
            if not _should_skip_file(p, root, dirpath, excludes, out_resolved):
                files.append(p)
    return files


def _rotate_backups(out_dir: Path, keep: int) -> int:
    if keep <= 0:
        return 0
    candidates = sorted(
        (p for p in out_dir.glob(_BACKUP_GLOB) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted = 0
    for p in candidates[keep:]:
        try:
            p.unlink()
            deleted += 1
            info(f"Rotated out  : {p.name}")
        except OSError as e:
            warn(f"Could not delete {p.name}: {e}")
    return deleted


def _create_zip(out: Path, files: list[Path], root: Path, password: str) -> int:
    try:
        import pyzipper
    except ImportError:
        missing_dep("pyzipper", "backup")
        return -1
    total_raw = 0
    n = len(files)
    prog = _Progress(n)
    with pyzipper.AESZipFile(out, "w",
                             compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        if password:
            zf.setpassword(password.encode())
        for i, f in enumerate(files, 1):
            zf.write(f, str(f.relative_to(root)))
            total_raw += f.stat().st_size
            prog.update(i, total_raw, force=(i == n))
    print()
    return total_raw


def _create_tar(out: Path, files: list[Path], root: Path, mode: str) -> int:
    total_raw = 0
    n = len(files)
    prog = _Progress(n)
    with tarfile.open(out, mode) as tf:  # NOSONAR — write-only archive creation
        for i, f in enumerate(files, 1):
            tf.add(f, arcname=str(f.relative_to(root)))
            total_raw += f.stat().st_size
            prog.update(i, total_raw, force=(i == n))
    print()
    return total_raw


def _create_7z(out: Path, files: list[Path], root: Path, password: str) -> int:
    try:
        import py7zr
    except ImportError:
        missing_dep("py7zr", "backup")
        return -1
    total_raw = 0
    n = len(files)
    prog = _Progress(n)
    with py7zr.SevenZipFile(out, "w",
                            password=password or None,
                            header_encryption=bool(password),
                            filters=[{"id": py7zr.FILTER_LZMA2, "preset": 1}]) as zf:
        for i, f in enumerate(files, 1):
            zf.write(f, str(f.relative_to(root)))
            total_raw += f.stat().st_size
            prog.update(i, total_raw, force=(i == n))
    print()
    return total_raw


def _create_tar_zst(out: Path, files: list[Path], root: Path) -> int:
    try:
        import zstandard
    except ImportError:
        missing_dep("zstandard", "backup")
        return -1
    total_raw = 0
    n = len(files)
    prog = _Progress(n)
    cctx = zstandard.ZstdCompressor(level=3)
    with out.open("wb") as raw_f:
        with cctx.stream_writer(raw_f) as zst_f:
            with tarfile.open(fileobj=zst_f, mode="w|") as tf:  # NOSONAR — write-only archive creation
                for i, f in enumerate(files, 1):
                    tf.add(f, arcname=str(f.relative_to(root)))
                    total_raw += f.stat().st_size
                    prog.update(i, total_raw, force=(i == n))
    print()
    return total_raw


def _encryption_label(fmt, password):
    if fmt == "zip" and password:
        return "Yes (AES-256)"
    if fmt == "7z" and password:
        return "Encrypted (7z)"
    return "No"


def _dispatch_archive(fmt, tmp_out, files, root, password):
    if fmt == "zip":
        return _create_zip(tmp_out, files, root, password)
    if fmt == "7z":
        return _create_7z(tmp_out, files, root, password)
    if fmt == "tar.zst":
        return _create_tar_zst(tmp_out, files, root)
    return _create_tar(tmp_out, files, root, TAR_MODES[fmt])


def _print_summary(fmt, exclude_set, out, keep, bcfg, project_root):
    header("Flutter Project Backup")
    info(f"Project root : {project_root}")
    info(f"Format       : {FORMATS[fmt]['label']}")
    info(f"Encrypted    : {_encryption_label(fmt, bcfg.password)}")
    info(f"Output       : {out}")
    if exclude_set:
        info(f"Excluding    : {', '.join(sorted(exclude_set))}")
    else:
        info("Excluding    : (nothing - full archive)")
    if keep > 0:
        info(f"Keep         : {keep} most recent backup(s)")


def _run_dry_run(project_root, exclude_set, out):
    info("[dry-run] Scanning files for preview...")
    files = _collect_files(project_root, exclude_set, out)
    raw_total = sum(f.stat().st_size for f in files)
    info(f"Would archive: {len(files):,} files  ({fmt_size(raw_total)})")
    info("[dry-run] No archive will be created.")


def _create_and_report(fmt, out, files, root, password, keep):
    tmp_out = out.with_suffix(out.suffix + ".tmp")
    try:
        raw = _dispatch_archive(fmt, tmp_out, files, root, password)
        if raw < 0:
            return 1
        tmp_out.replace(out)
        compressed = out.stat().st_size
        ratio = (1 - compressed / raw) * 100 if raw else 0.0
        ok(f"Archive      : {out.name}")
        ok(f"Raw size     : {fmt_size(raw)}")
        ok(f"Compressed   : {fmt_size(compressed)}  ({ratio:.1f}% saved)")
        ok(f"Location     : {out}")
        if keep > 0:
            deleted = _rotate_backups(out.parent, keep)
            if deleted:
                ok(f"Rotated      : removed {deleted} old backup(s)")
        return 0
    except Exception as exc:
        err(f"Archive failed: {exc}")
        for stray in (tmp_out, out):
            try: stray.unlink(missing_ok=True)
            except OSError: pass
        return 1


def _list_project_folders(project_root, default_excludes):
    """Print project directories with exclusion markers."""
    for p in sorted(Path(project_root).iterdir()):
        if p.is_dir():
            marker = " [default-excluded]" if p.name in default_excludes else ""
            print(f"{p.name}{marker}")


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    bcfg = cfg.integrations.backup
    if bcfg is None:
        err("integrations.backup is not configured in ftk.yaml")
        return 1

    default_fmt = bcfg.default_format if bcfg.default_format in FORMATS else "zip"
    default_excludes = set(bcfg.default_excludes)

    parser = argparse.ArgumentParser(prog="ftk backup", description="Create a timestamped project archive")
    parser.add_argument("--format", "-f", choices=list(FORMATS), default=default_fmt)
    parser.add_argument("--exclude", "-e", nargs="+", default=[])
    parser.add_argument("--no-default-excludes", action="store_true")
    parser.add_argument("--output", "-o")
    parser.add_argument("--keep", "-k", type=int, default=0)
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-folders", action="store_true")
    args = parser.parse_args(argv)

    project_root = cfg.root

    if args.list_folders:
        _list_project_folders(project_root, default_excludes)
        return 0

    if bcfg.output_dir and not args.output:
        args.output = bcfg.output_dir

    fmt = args.format
    out = _build_output_path(project_root, fmt, args.output)
    exclude_set: set[str] = set(args.exclude)
    if not args.no_default_excludes:
        exclude_set |= default_excludes

    _print_summary(fmt, exclude_set, out, args.keep, bcfg, project_root)

    if args.dry_run:
        _run_dry_run(project_root, exclude_set, out)
        return 0

    info("Scanning files...")
    files = _collect_files(project_root, exclude_set, out)
    if not files:
        err("No files found to archive.")
        return 1
    raw_total = sum(f.stat().st_size for f in files)
    info(f"Files found  : {len(files):,}  ({fmt_size(raw_total)})")

    if not confirm(
        f"Create {FORMATS[fmt]['label']} backup of {fmt_size(raw_total)}?",
        auto_yes=args.yes,
    ):
        warn("Backup cancelled.")
        return 1

    info("Creating archive...")
    out.parent.mkdir(parents=True, exist_ok=True)
    return _create_and_report(fmt, out, files, Path(project_root), bcfg.password, args.keep)
