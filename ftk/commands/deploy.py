"""Deploy Flutter web build(s) via FTP / FTPS / SFTP."""
from __future__ import annotations
import argparse
import fnmatch
import os
import sys
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, replace
from ftk.common import C, header, ok, warn, err, info, skip, confirm, fmt_size, missing_dep
from ftk.config import ProjectConfig, DeployTargetConfig


_SYSTEM_SKIP = {".DS_Store", "Thumbs.db", "desktop.ini"}
_UPLOAD_LAST = {"index.html", "manifest.json", "flutter_service_worker.js"}
CONNECT_TIMEOUT = 60


class Deployer(ABC):
    def __init__(self, target: DeployTargetConfig):
        self.t = target

    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def disconnect(self) -> None: ...
    @abstractmethod
    def list_remote(self) -> list[str]: ...
    @abstractmethod
    def download_file(self, remote_rel: str, local_path: str) -> None: ...
    @abstractmethod
    def upload_file(self, local_path: str, remote_rel: str) -> None: ...


class FtpDeployer(Deployer):
    def __init__(self, target):
        super().__init__(target)
        self.ftp = None

    def connect(self) -> None:
        from ftplib import FTP, FTP_TLS
        port = self.t.port or 21
        pwd = self.t.resolved_password()
        if self.t.protocol == "ftps":
            self.ftp = FTP_TLS()
            self.ftp.connect(self.t.host, port, timeout=CONNECT_TIMEOUT)
            self.ftp.login(self.t.user, pwd)
            self.ftp.prot_p()
        else:
            warn("Plain FTP transmits credentials in clear text. "
                 "Consider switching to ftps or sftp in your deploy target config.")
            self.ftp = FTP()  # NOSONAR - user warned above about cleartext
            self.ftp.connect(self.t.host, port, timeout=CONNECT_TIMEOUT)
            self.ftp.login(self.t.user, pwd)
        self.ftp.set_pasv(self.t.passive)
        self.ftp.cwd(self.t.remote_path)

    def disconnect(self) -> None:
        if self.ftp is None:
            return
        try:
            self.ftp.quit()
        except Exception:
            try: self.ftp.close()
            except Exception: pass
        self.ftp = None

    def list_remote(self) -> list[str]:
        files: list[str] = []
        self._walk(".", files)
        return files

    def _walk(self, path: str, out: list[str]) -> None:
        try:
            entries = list(self.ftp.mlsd(path))
            for name, facts in entries:
                if name in (".", ".."):
                    continue
                full = f"{path}/{name}" if path != "." else name
                t = facts.get("type", "")
                if t == "dir":
                    self._walk(full, out)
                elif t == "file":
                    out.append(full)
        except Exception:
            self._walk_legacy(path, out)

    def _walk_legacy(self, path: str, out: list[str]) -> None:
        try:
            lines: list[str] = []
            self.ftp.retrlines(f"LIST {path}", lines.append)
        except Exception:
            return
        for line in lines:
            parts = line.split(maxsplit=8)
            if len(parts) < 9:
                continue
            name = parts[8]
            if name in (".", ".."):
                continue
            is_dir = line.startswith("d")
            full = f"{path}/{name}" if path != "." else name
            if is_dir:
                self._walk_legacy(full, out)
            else:
                out.append(full)

    def download_file(self, remote_rel: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            self.ftp.retrbinary(f"RETR {remote_rel}", f.write)

    def upload_file(self, local_path: str, remote_rel: str) -> None:
        self._ensure_remote_dir(os.path.dirname(remote_rel))
        with open(local_path, "rb") as f:
            self.ftp.storbinary(f"STOR {remote_rel}", f)

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        if not remote_dir or remote_dir == ".":
            return
        cur = ""
        for p in remote_dir.replace("\\", "/").split("/"):
            if not p:
                continue
            cur = f"{cur}/{p}" if cur else p
            try:
                self.ftp.mkd(cur)
            except Exception:
                pass


class SftpDeployer(Deployer):
    def __init__(self, target):
        super().__init__(target)
        self.client = None
        self.sftp = None

    def connect(self) -> None:
        try:
            import paramiko
        except ImportError:
            missing_dep("paramiko", "deploy")
            sys.exit(1)
        port = self.t.port or 22
        pwd = self.t.resolved_password()
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.t.host, port=port,
            username=self.t.user, password=pwd,
            timeout=CONNECT_TIMEOUT,
        )
        self.sftp = self.client.open_sftp()
        self.sftp.chdir(self.t.remote_path)

    def disconnect(self) -> None:
        for name in ("sftp", "client"):
            obj = getattr(self, name, None)
            if obj is not None:
                try: obj.close()
                except Exception: pass
                setattr(self, name, None)

    def list_remote(self) -> list[str]:
        files: list[str] = []
        self._walk(".", files)
        return files

    def _walk(self, path: str, out: list[str]) -> None:
        import stat as _stat
        try:
            entries = self.sftp.listdir_attr(path)
        except Exception:
            return
        for entry in entries:
            full = f"{path}/{entry.filename}" if path != "." else entry.filename
            if _stat.S_ISDIR(entry.st_mode):
                self._walk(full, out)
            else:
                out.append(full)

    def download_file(self, remote_rel: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.sftp.get(remote_rel, local_path)

    def upload_file(self, local_path: str, remote_rel: str) -> None:
        self._ensure_remote_dir(os.path.dirname(remote_rel))
        self.sftp.put(local_path, remote_rel)

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        if not remote_dir or remote_dir == ".":
            return
        cur = ""
        for p in remote_dir.replace("\\", "/").split("/"):
            if not p:
                continue
            cur = f"{cur}/{p}" if cur else p
            try:
                self.sftp.stat(cur)
            except FileNotFoundError:
                try:
                    self.sftp.mkdir(cur)
                except Exception:
                    pass

def _effective_remote_path(target: DeployTargetConfig, env: str) -> str | None:
    """Return the effective remote path for the given env.

    Returns None (and prints an error) if env='dev' but dev_remote_path is not set.
    """
    if env == "dev":
        if not target.dev_remote_path:
            err(
                f"No dev_remote_path configured for flavor '{target.flavor}'. "
                f"Add dev_remote_path to its deploy target in ftk.yaml."
            )
            return None
        return target.dev_remote_path
    return target.remote_path

def _make_deployer(target: DeployTargetConfig) -> Deployer:
    proto = target.protocol.lower()
    if proto in ("ftp", "ftps"):
        return FtpDeployer(target)
    if proto == "sftp":
        return SftpDeployer(target)
    err(f"Unsupported protocol: {target.protocol}")
    sys.exit(1)


@dataclass
class BackupResult:
    success: bool
    failed_count: int = 0
    remote_files: list[str] = field(default_factory=list)


@dataclass
class DeployStats:
    uploaded: int = 0
    overwrote: int = 0
    new_files: int = 0
    skipped: int = 0
    failed: int = 0
    bytes: int = 0


def _build_dir_for(project_root: str, flavor_name: str | None) -> str | None:
    candidates = []
    if flavor_name:
        candidates.append(os.path.join(project_root, "build", f"web_{flavor_name}"))
    candidates.append(os.path.join(project_root, "build", "web"))
    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "index.html")):
            return c
    return None


def _collect_local_files(build_dir: str) -> list[str]:
    out: list[str] = []
    base = Path(build_dir)
    for f in base.rglob("*"):
        if not f.is_file() or f.name in _SYSTEM_SKIP:
            continue
        out.append(str(f.relative_to(base)).replace("\\", "/"))
    return sorted(out)


def _is_skipped(rel_path: str, patterns: list[str]) -> bool:
    name = os.path.basename(rel_path)
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel_path, p) for p in patterns)


def _sort_for_safe_upload(files: list[str]) -> list[str]:
    last = [f for f in files if os.path.basename(f) in _UPLOAD_LAST]
    rest = [f for f in files if os.path.basename(f) not in _UPLOAD_LAST]
    return rest + last


def _download_remote_files(deployer, remote_files, tmp_dir):
    failed = 0
    total = len(remote_files)
    every = max(1, total // 20)
    for i, rel in enumerate(remote_files, 1):
        local = os.path.join(tmp_dir, *rel.split("/"))
        try:
            deployer.download_file(rel, local)
        except Exception as e:
            warn(f"  Failed to backup {rel}: {e}")
            failed += 1
            continue
        if i % every == 0 or i == total:
            info(f"  [{i}/{total}] downloaded")
    return failed


def _create_backup_zip(tmp_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(tmp_dir):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, tmp_dir)
                zf.write(full, arc)


def _backup_remote(deployer, target, flavor_name, project_root, dry_run,
                   *, env_suffix: str = "") -> BackupResult:
    info("Listing remote files for backup...")
    try:
        remote_files = deployer.list_remote()
    except Exception as e:
        err(f"Failed to list remote files: {e}")
        return BackupResult(success=False)
    if not remote_files:
        warn("Remote is empty - no backup needed.")
        return BackupResult(success=True, remote_files=[])
    remote_files = [r.removeprefix("./") for r in remote_files]
    info(f"Found {len(remote_files)} remote file(s). Downloading to ZIP...")
    label = f"{flavor_name or 'default'}{env_suffix}"
    backup_dir_rel = target.backup_dir or f"build/deploy_backups/{label}"
    backup_dir = os.path.join(project_root, *backup_dir_rel.split("/"))
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_name = f"backup_{label}_{ts}.zip"
    zip_path = os.path.join(backup_dir, zip_name)
    if dry_run:
        info(f"[dry-run] would create backup: {zip_path}")
        return BackupResult(success=True, remote_files=remote_files)
    import shutil as _shutil
    tmp_dir = os.path.join(backup_dir, f".tmp_{ts}")
    try:
        failed = _download_remote_files(deployer, remote_files, tmp_dir)
        nothing_downloaded = not os.path.isdir(tmp_dir) or not any(Path(tmp_dir).rglob("*"))
        if nothing_downloaded:
            err("Backup failed: no files were downloaded.")
            return BackupResult(success=False, failed_count=failed)
        _create_backup_zip(tmp_dir, zip_path)
        ok(f"Backup created: {zip_path} ({fmt_size(os.path.getsize(zip_path))})")
        if failed:
            warn(f"  Note: {failed} file(s) could not be backed up.")
        return BackupResult(success=True, failed_count=failed, remote_files=remote_files)
    finally:
        if os.path.isdir(tmp_dir):
            _shutil.rmtree(tmp_dir, ignore_errors=True)


def _resolve_remote_files(deployer, target, project_root, skip_backup, auto_yes,
                          *, env: str = "prod"):
    env_suffix = f"_{env}" if env != "prod" else ""
    if skip_backup:
        warn("Backup skipped (--no-backup).")
        try:
            return True, [r.removeprefix("./") for r in deployer.list_remote()]
        except Exception:
            return True, []

    result = _backup_remote(deployer, target, target.flavor, project_root,
                            dry_run=False, env_suffix=env_suffix)
    if not result.success:
        warn("Backup failed - aborting deploy.")
        return False, []
    if result.failed_count > 0 and not auto_yes:
        if not confirm(f"{result.failed_count} file(s) could not be backed up. Continue?",
                       auto_yes=False, dry_run=False):
            skip("Deploy aborted.")
            return False, []
    return True, result.remote_files


def _upload_files(deployer, sorted_files, build_dir, remote_set, skip_patterns):
    stats = DeployStats()
    total = len(sorted_files)
    every = max(1, total // 20)
    for i, rel in enumerate(sorted_files, 1):
        if _is_skipped(rel, skip_patterns):
            stats.skipped += 1
            continue
        local_path = os.path.join(build_dir, rel.replace("/", os.sep))
        try:
            existed = rel in remote_set
            deployer.upload_file(local_path, rel)
            size = os.path.getsize(local_path)
            stats.uploaded += 1
            stats.bytes += size
            if existed:
                stats.overwrote += 1
            else:
                stats.new_files += 1
        except Exception as e:
            err(f"  Failed: {rel} - {e}")
            stats.failed += 1
        if i % every == 0 or i == total:
            info(f"  [{i}/{total}] processed ({fmt_size(stats.bytes)})")
    return stats


def _print_deploy_summary(flavor_name, stats, env: str = "prod"):
    env_tag = f" [{env}]" if env != "prod" else ""
    print()
    info(f"  {flavor_name}{env_tag} summary:")
    ok(  f"    Uploaded   : {stats.uploaded}  ({fmt_size(stats.bytes)})")
    info(f"    New files  : {stats.new_files}")
    info(f"    Overwrote  : {stats.overwrote}")
    if stats.skipped:
        info(f"    Skipped    : {stats.skipped}")
    if stats.failed:
        err( f"    Failed     : {stats.failed}")


def _validate_deploy_target_and_build(
    target: DeployTargetConfig, 
    project_root: str, 
    env: str
) -> tuple[DeployTargetConfig | None, str | None]:
    """Validate the deployment target configuration and build directory."""
    flavor_name = target.flavor or "default"

    if not target.host or not target.user:
        err(f"Target {flavor_name} is not configured (missing host/user).")
        return None, None

    if not target.resolved_password():
        err(f"No password set for {flavor_name}. Set env var {target.password_env or '<password>'}.")
        return None, None

    effective_path = _effective_remote_path(target, env)
    if effective_path is None:
        return None, None

    build_dir = _build_dir_for(project_root, target.flavor)
    if not build_dir:
        err(f"No web build found for '{flavor_name}'.")
        info(f"  Run `ftk build --web --flavor {flavor_name}` first.")
        return None, None

    working_target = replace(target, remote_path=effective_path)
    return working_target, build_dir


def _log_dry_run(local_files: list[str]) -> None:
    """Display simulation information in dry-run mode."""
    info("[dry-run] would connect, backup, and upload")
    for rel in _sort_for_safe_upload(local_files)[:5]:
        info(f"  [dry-run] would upload: {rel}")
    if len(local_files) > 5:
        info(f"  ... and {len(local_files) - 5} more")


def _deploy_flavor(
    target: DeployTargetConfig,
    project_root: str,
    *,
    auto_yes: bool,
    dry_run: bool,
    skip_backup: bool,
    env: str = "prod",
) -> bool:
    flavor_name = target.flavor or "default"
    env_tag = f" [{env}]" if env != "prod" else ""
    header(f"Deploy: {flavor_name}{env_tag}")

    working_target, build_dir = _validate_deploy_target_and_build(target, project_root, env)
    if not working_target or not build_dir:
        return False

    local_files = _collect_local_files(build_dir)
    info(f"Build dir   : {os.path.relpath(build_dir, project_root)}")
    info(f"Local files : {len(local_files)}")
    info(f"Protocol    : {working_target.protocol}")
    info(f"Server      : {working_target.user}@{working_target.host}:{working_target.port or 'default'}")
    info(f"Remote path : {working_target.remote_path}")

    if dry_run:
        _log_dry_run(local_files)
        return True

    target_desc = f"{flavor_name}{env_tag}"
    if not confirm(f"Deploy {len(local_files)} file(s) to {target_desc}?", auto_yes=auto_yes, dry_run=False):
        skip("Deploy cancelled.")
        return False

    deployer = _make_deployer(working_target)
    info("Connecting...")
    try:
        deployer.connect()
        ok("Connected.")
    except Exception as e:
        err(f"Connection failed: {e}")
        return False

    try:
        proceed, remote_files = _resolve_remote_files(
            deployer, target, project_root, skip_backup, auto_yes, env=env
        )
        if not proceed:
            return False

        sorted_files = _sort_for_safe_upload(local_files)
        info("Uploading files (assets first, HTML last)...")
        stats = _upload_files(
            deployer, sorted_files, build_dir, set(remote_files), working_target.skip_patterns
        )
    finally:
        deployer.disconnect()

    _print_deploy_summary(flavor_name, stats, env=env)
    return stats.failed == 0


def _deploy_all_flavors(cfg, flavors, args):
    results = []
    envs = ["prod", "dev"] if args.env == "both" else [args.env]
    for flavor in flavors:
        target = cfg.deploy_target(flavor)
        if not target:
            err(f"No deploy target for flavor: {flavor}")
            results.append((f"{flavor}[prod]", False))
            continue
        for env in envs:
            print(f"\n{C.BOLD}{'-' * 60}{C.RESET}")
            ok_flag = _deploy_flavor(
                target, cfg.root,
                auto_yes=args.yes, dry_run=args.dry_run,
                skip_backup=args.no_backup, env=env,
            )
            label = f"{flavor}[{env}]" if (len(envs) > 1 or env != "prod") else flavor
            results.append((label, ok_flag))
    return results


def _list_targets(cfg):
    header("Configured deploy targets")
    for t in cfg.integrations.deploy:
        configured = "OK" if (t.host and t.user and t.resolved_password()) else "--"
        dev_info = f"  |  dev: {t.dev_remote_path}" if t.dev_remote_path else ""
        info(
            f"  [{configured}] {t.flavor:<10} {t.protocol:<5} "
            f"{t.user}@{t.host or '(not set)'} -> {t.remote_path}{dev_info}"
        )
    print()


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    if not cfg.integrations.deploy:
        err("No deploy targets configured in ftk.yaml integrations.deploy.")
        return 1

    target_names = [t.flavor for t in cfg.integrations.deploy if t.flavor]
    default_target = target_names[0] if target_names else ""

    p = argparse.ArgumentParser(prog="ftk deploy", description="Deploy web builds")
    p.add_argument("--flavor", "-f", nargs="+", action="append",
                   choices=target_names if target_names else None,
                   metavar="FLAVOR")
    p.add_argument("--env", "-e",
                   choices=["prod", "dev", "both"], default="prod",
                   metavar="ENV",
                   help="Target environment: prod (default), dev, or both")
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--dry-run",   action="store_true")
    p.add_argument("--yes", "-y", action="store_true")
    p.add_argument("--list-targets", action="store_true")
    args = p.parse_args(argv)

    if args.list_targets:
        _list_targets(cfg)
        return 0

    flavors = [f for sub in args.flavor for f in sub] if args.flavor else [default_target]

    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Deploy{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {cfg.root}")
    info(f"Flavor(s)    : {', '.join(flavors)}")
    extras = []
    if args.env != "prod":  extras.append(f"ENV={args.env.upper()}")
    if args.dry_run:        extras.append("DRY RUN")
    if args.no_backup:      extras.append("NO BACKUP")
    if extras:
        info(f"Flags        : {', '.join(extras)}")

    results = _deploy_all_flavors(cfg, flavors, args)

    header("Summary")
    failed = sum(1 for _, r in results if not r)
    for name, r in results:
        (ok if r else err)(f"  {name}: {'OK' if r else 'FAILED'}")
    print()
    return 0 if failed == 0 else 1
