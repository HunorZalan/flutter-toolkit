"""Global project registry for flutter-toolkit.

Stored at `~/.ftk/projects.yaml`. Each entry maps a short id to an absolute
project path. A separate file, `~/.ftk/last_project`, records the last-used
project so that running `ftk` from anywhere still finds the right workspace.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

from ftk.config import load_config, ProjectConfig


REGISTRY_DIRNAME = ".ftk"
REGISTRY_FILENAME = "projects.yaml"
LAST_PROJECT_FILENAME = "last_project"


def registry_dir() -> Path:
    """Location is overridable with the FTK_HOME env var."""
    override = os.environ.get("FTK_HOME")
    base = Path(override) if override else Path.home() / REGISTRY_DIRNAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def registry_file() -> Path:
    return registry_dir() / REGISTRY_FILENAME


def last_project_file() -> Path:
    return registry_dir() / LAST_PROJECT_FILENAME


@dataclass
class ProjectEntry:
    id: str
    name: str
    root: str
    active: bool = False


def _read_registry() -> dict[str, Any]:
    f = registry_file()
    if not f.is_file():
        return {"projects": []}
    try:
        with open(f, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) if yaml else None  # type: ignore
    except Exception:
        return {"projects": []}
    if not isinstance(data, dict):
        return {"projects": []}
    data.setdefault("projects", [])
    return data


def _write_registry(data: dict[str, Any]) -> None:
    f = registry_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    if yaml is None:
        raise RuntimeError("PyYAML is required to write the registry.")
    with open(f, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def list_projects() -> list[ProjectEntry]:
    data = _read_registry()
    active = get_last_project_id()
    out: list[ProjectEntry] = []
    for p in data.get("projects", []):
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", ""))
        out.append(ProjectEntry(
            id=pid,
            name=str(p.get("name", pid)),
            root=str(p.get("root", "")),
            active=(pid == active),
        ))
    return out


def add_project(root: str, *, project_id: str = "", name: str = "") -> ProjectEntry:
    root_abs = os.path.abspath(root)
    if not os.path.isdir(root_abs):
        raise FileNotFoundError(f"Project root does not exist: {root_abs}")
    cfg = load_config(root_abs, project_id=project_id, name=name)
    entry = ProjectEntry(
        id=cfg.id or os.path.basename(root_abs),
        name=cfg.name or os.path.basename(root_abs),
        root=root_abs,
    )
    data = _read_registry()
    projects = [p for p in data.get("projects", []) if p.get("id") != entry.id and p.get("root") != entry.root]
    projects.append(asdict(entry))
    data["projects"] = projects
    _write_registry(data)
    if not get_last_project_id():
        set_last_project_id(entry.id)
    return entry


def remove_project(project_id: str) -> bool:
    data = _read_registry()
    before = len(data.get("projects", []))
    data["projects"] = [p for p in data.get("projects", []) if p.get("id") != project_id]
    after = len(data["projects"])
    if after != before:
        _write_registry(data)
        if get_last_project_id() == project_id:
            clear_last_project()
        return True
    return False


def find_project(project_id_or_path: str) -> ProjectEntry | None:
    for p in list_projects():
        if p.id == project_id_or_path:
            return p
    abs_path = os.path.abspath(project_id_or_path)
    for p in list_projects():
        if os.path.abspath(p.root) == abs_path:
            return p
    return None


def get_last_project_id() -> str:
    f = last_project_file()
    if not f.is_file():
        return ""
    try:
        return f.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def set_last_project_id(project_id: str) -> None:
    f = last_project_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(project_id, encoding="utf-8")


def clear_last_project() -> None:
    f = last_project_file()
    if f.exists():
        try:
            f.unlink()
        except OSError:
            pass


def resolve(
    *,
    cli_root: str | None = None,
    cli_project: str | None = None,
) -> ProjectConfig:
    """Resolve the active project config using (in priority order):

      1. --root DIR      explicit directory
      2. --project ID    lookup in the global registry
      3. FTK_PROJECT env / last_project file
      4. Walk up from cwd (any directory containing ftk.yaml or pubspec.yaml)
    """
    if cli_root:
        return load_config(os.path.abspath(cli_root))
    if cli_project:
        entry = find_project(cli_project)
        if entry:
            return load_config(entry.root, project_id=entry.id, name=entry.name)
        raise SystemExit(f"Unknown project id: {cli_project!r} - run `ftk projects list`.")
    env = os.environ.get("FTK_PROJECT")
    if env:
        entry = find_project(env)
        if entry:
            return load_config(entry.root, project_id=entry.id, name=entry.name)
    last = get_last_project_id()
    if last:
        entry = find_project(last)
        if entry and os.path.isdir(entry.root):
            return load_config(entry.root, project_id=entry.id, name=entry.name)
    from ftk.common import resolve_project_root
    root = resolve_project_root(None)
    return load_config(root)
