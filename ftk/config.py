"""YAML-driven configuration loader for flutter-toolkit.

A project is described by an `ftk.yaml` file at its root. Any section can be
omitted: if `flavors` is missing, flavor-aware code paths become no-ops; if
`integrations.deploy` is missing, the deploy command is disabled; etc.

The loader is tolerant: unknown keys are accepted, missing keys fall back to
sensible defaults derived from the existing your project.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install flutter-toolkit with: pip install flutter-toolkit"
    ) from exc


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FlavorConfig:
    name: str
    display_name: str = ""
    ios_info_plist: str = ""
    ios_config_dir: str = ""
    web_new_prefix: bool = True
    web_base_href: str = ""
    adaptive_bg: str = "#FFFFFF"
    notification_color: str = "#1B5E20"

    @property
    def web_assets_dir(self) -> str:
        return f"tool/web_{self.name}"

    @property
    def effective_web_base_href(self) -> str:
        if self.web_base_href:
            return self.web_base_href
        prefix = "new" if self.web_new_prefix else ""
        return f"/{prefix}{self.name}/"

    @property
    def ios_google_plist_dir(self) -> str:
        return f"ios/config/{self.ios_config_dir or self.name}"

    @property
    def source_primary(self) -> str:
        name = self.display_name or self.name
        return f"tool/icons/{name}.png"

    @property
    def splash_source(self) -> str:
        name = self.display_name or self.name
        return f"assets/img/{name}/splash.png"

    @property
    def web_folder(self) -> str:
        return f"tool/web_{self.name}/icons"


@dataclass
class DeployTargetConfig:
    flavor: str
    host: str
    user: str
    password: str = ""
    password_env: str = ""
    remote_path: str = "/"
    protocol: str = "ftp"          # ftp / ftps / sftp
    port: int | None = None
    backup_dir: str = ""           # optional remote backup directory
    passive: bool = True
    skip_patterns: list[str] = field(default_factory=list)

    def resolved_password(self) -> str:
        if self.password_env:
            val = os.environ.get(self.password_env)
            if val:
                return val
        return self.password


@dataclass
class BackupConfig:
    default_format: str = "zip"            # zip / 7z / tar.* / tar
    password: str = ""                     # used for encrypted zip/7z
    default_excludes: list[str] = field(default_factory=lambda: [
        "build", ".dart_tool", ".gradle", ".idea", ".vscode", "node_modules",
        "coverage", "Pods", ".symlinks", ".flutter-plugins",
        ".flutter-plugins-dependencies", ".git", ".scannerwork",
    ])
    output_dir: str = ""                   # optional default output directory


@dataclass
class SonarConfig:
    scanner_name: str = "sonar-scanner"
    extra_args: list[str] = field(default_factory=list)


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8742
    log_dir: str = "tool/python/log"
    notes_file: str = "tool/python/notes.txt"
    auto_reload: bool = False


@dataclass
class IntegrationsConfig:
    sonar: SonarConfig | None = None
    backup: BackupConfig | None = None
    deploy: list[DeployTargetConfig] = field(default_factory=list)
    server: ServerConfig = field(default_factory=ServerConfig)


@dataclass
class PathsConfig:
    lib_dir: str = "lib"
    translation_dir: str = "assets/translations"
    keys_file: str = "lib/helpers/constants/translation_keys.dart"
    entry_points: list[str] = field(default_factory=lambda: ["lib/main.dart"])
    web_post_build_files: list[str] = field(default_factory=lambda: [
        "favicon.ico", "favicon.png", "firebase-messaging-sw.js",
        "index.html", "manifest.json",
    ])


@dataclass
class BuildConfig:
    default_mode: str = "release"
    no_obfuscate: bool = False
    desktop_targets: list[str] = field(default_factory=lambda: ["windows", "macos", "linux"])


@dataclass
class CommandToggles:
    """Enable / disable individual top-level commands (shown in UI)."""
    clean: bool = True
    build: bool = True
    info: bool = True
    analyze: bool = True
    icons: bool = True
    unused: bool = True
    translations: bool = True
    test: bool = True
    deploy: bool = True
    run: bool = True
    backup: bool = True
    sonar: bool = True
    notes: bool = True
    help: bool = True


@dataclass
class PlatformToggles:
    """Which target platforms / host OSes this project supports.

    Used by the UI to grey-out (not hide) build/icon/run options the project
    does not ship. Host-OS flags (`windows`, `macos`, `linux`) describe desktop
    build targets, not the machine currently running ftk.
    """
    web: bool = True
    android: bool = True
    ios: bool = True
    windows: bool = True
    macos: bool = True
    linux: bool = True


@dataclass
class ProjectConfig:
    # Identity
    id: str = ""                       # short id used in the registry
    name: str = ""                     # human-readable name
    root: str = ""                     # absolute path to the project root
    config_path: str = ""              # absolute path to ftk.yaml (empty if none)

    # Data
    flavors: list[FlavorConfig] = field(default_factory=list)
    default_flavor: str = ""
    paths: PathsConfig = field(default_factory=PathsConfig)
    languages: list[str] = field(default_factory=lambda: ["en"])
    build: BuildConfig = field(default_factory=BuildConfig)
    commands: CommandToggles = field(default_factory=CommandToggles)
    platforms: PlatformToggles = field(default_factory=PlatformToggles)
    env_checks: list[str] = field(default_factory=list)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)

    # Diagnostics
    warnings: list[str] = field(default_factory=list)

    # ---- Helpers ---------------------------------------------------------

    @property
    def has_flavors(self) -> bool:
        return bool(self.flavors)

    @property
    def flavor_names(self) -> list[str]:
        return [f.name for f in self.flavors]

    def flavor(self, name: str) -> FlavorConfig | None:
        for f in self.flavors:
            if f.name == name:
                return f
        return None

    def deploy_target(self, flavor_name: str) -> DeployTargetConfig | None:
        for t in self.integrations.deploy:
            if t.flavor == flavor_name:
                return t
        return None

    def abs(self, *parts: str) -> str:
        return os.path.join(self.root, *parts)

    def platform_enabled(self, name: str) -> bool:
        """True if the project supports building / running on this platform."""
        return bool(getattr(self.platforms, name, True))

    def command_enabled(self, name: str) -> bool:
        """A command is enabled if its toggle is on AND the required section exists."""
        base = getattr(self.commands, name, True)
        if not base:
            return False
        if name == "deploy":
            return bool(self.integrations.deploy)
        if name == "sonar":
            return self.integrations.sonar is not None
        if name == "backup":
            return self.integrations.backup is not None
        if name == "translations":
            return bool(self.languages) and len(self.languages) >= 1
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

CONFIG_FILENAME = "ftk.yaml"
LEGACY_CONFIG_FILENAME = ".ftk.yaml"


def _find_config_file(project_root: str) -> str | None:
    for fn in (CONFIG_FILENAME, LEGACY_CONFIG_FILENAME):
        p = Path(project_root) / fn
        if p.is_file():
            return str(p)
    return None


def _coerce_flavor(data: dict[str, Any]) -> FlavorConfig:
    return FlavorConfig(
        name            = str(data.get("name", "")).strip(),
        display_name    = str(data.get("display_name", "") or data.get("displayName", "")),
        ios_info_plist  = str(data.get("ios_info_plist", "")),
        ios_config_dir  = str(data.get("ios_config_dir", "")),
        web_new_prefix  = bool(data.get("web_new_prefix", True)),
        web_base_href   = str(data.get("web_base_href", "")),
        adaptive_bg     = str(data.get("adaptive_bg", "#FFFFFF")),
        notification_color = str(data.get("notification_color", "#1B5E20")),
    )


def _coerce_deploy(data: dict[str, Any]) -> DeployTargetConfig:
    return DeployTargetConfig(
        flavor       = str(data.get("flavor", "")).strip(),
        host         = str(data.get("host", "")),
        user         = str(data.get("user", "")),
        password     = str(data.get("password", "")),
        password_env = str(data.get("password_env", "")),
        remote_path  = str(data.get("remote_path", "/")),
        protocol     = str(data.get("protocol", "ftp")).lower(),
        port         = (int(data["port"]) if data.get("port") is not None else None),
        backup_dir   = str(data.get("backup_dir", "")),
        passive      = bool(data.get("passive", True)),
        skip_patterns = list(data.get("skip_patterns", []) or []),
    )


def _coerce_integrations(data: dict[str, Any]) -> IntegrationsConfig:
    ig = IntegrationsConfig()
    if "sonar" in data and data["sonar"] is not None:
        s = data["sonar"]
        ig.sonar = SonarConfig(
            scanner_name = str(s.get("scanner_name", "sonar-scanner")),
            extra_args   = list(s.get("extra_args", []) or []),
        )
    if "backup" in data and data["backup"] is not None:
        b = data["backup"]
        ig.backup = BackupConfig(
            default_format = str(b.get("default_format", "zip")),
            password       = str(b.get("password", "")),
            default_excludes = list(b.get("default_excludes", []) or []) or BackupConfig().default_excludes,
            output_dir     = str(b.get("output_dir", "")),
        )
    if "deploy" in data and data["deploy"] is not None:
        ig.deploy = [_coerce_deploy(d) for d in data["deploy"] if isinstance(d, dict)]
    if "server" in data and data["server"] is not None:
        s = data["server"]
        ig.server = ServerConfig(
            host        = str(s.get("host", "127.0.0.1")),
            port        = int(s.get("port", 8742)),
            log_dir     = str(s.get("log_dir", "tool/python/log")),
            notes_file  = str(s.get("notes_file", "tool/python/notes.txt")),
            auto_reload = bool(s.get("auto_reload", False)),
        )
    return ig


def _coerce_paths(data: dict[str, Any]) -> PathsConfig:
    p = PathsConfig()
    return PathsConfig(
        lib_dir         = str(data.get("lib_dir", p.lib_dir)),
        translation_dir = str(data.get("translation_dir", p.translation_dir)),
        keys_file       = str(data.get("keys_file", p.keys_file)),
        entry_points    = list(data.get("entry_points", []) or p.entry_points),
        web_post_build_files = list(data.get("web_post_build_files", []) or p.web_post_build_files),
    )


def _coerce_build(data: dict[str, Any]) -> BuildConfig:
    b = BuildConfig()
    return BuildConfig(
        default_mode   = str(data.get("default_mode", b.default_mode)),
        no_obfuscate   = bool(data.get("no_obfuscate", b.no_obfuscate)),
        desktop_targets= list(data.get("desktop_targets", []) or b.desktop_targets),
    )


def _coerce_commands(data: dict[str, Any]) -> CommandToggles:
    t = CommandToggles()
    for key in t.__dataclass_fields__:
        if key in data:
            setattr(t, key, bool(data[key]))
    return t


def _coerce_platforms(data: dict[str, Any]) -> PlatformToggles:
    t = PlatformToggles()
    for key in t.__dataclass_fields__:
        if key in data:
            setattr(t, key, bool(data[key]))
    return t


def _load_yaml_file(cfg_path: str) -> tuple[dict | None, str | None]:
    try:
        with open(cfg_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        return None, f"Failed to parse {cfg_path}: {exc}"
    if not isinstance(raw, dict):
        return None, f"{cfg_path}: top level must be a mapping."
    return raw, None


def _parse_flavors_section(raw: dict) -> tuple[list[FlavorConfig], str]:
    raw_flavors = raw.get("flavors") or []
    flavors: list[FlavorConfig] = []
    if isinstance(raw_flavors, list) and raw_flavors:
        flavors = [_coerce_flavor(d) for d in raw_flavors if isinstance(d, dict) and d.get("name")]
    explicit_default = raw.get("default_flavor", "")
    default_flavor = str(explicit_default or (flavors[0].name if flavors else ""))
    return flavors, default_flavor


def _apply_nested_sections(cfg: ProjectConfig, raw: dict) -> None:
    _section_map: list[tuple[str, type, Any]] = [
        ("paths",        dict, lambda d: _coerce_paths(d)),
        ("build",        dict, lambda d: _coerce_build(d)),
        ("commands",     dict, lambda d: _coerce_commands(d)),
        ("platforms",    dict, lambda d: _coerce_platforms(d)),
        ("env_checks",   list, lambda d: [str(x) for x in d]),
        ("integrations", dict, lambda d: _coerce_integrations(d)),
    ]
    for key, expected_type, coercer in _section_map:
        value = raw.get(key)
        if isinstance(value, expected_type):
            setattr(cfg, key, coercer(value))


def load_config(project_root: str, *, project_id: str = "", name: str = "") -> ProjectConfig:
    """Load `ftk.yaml` from project_root. Returns a fully-populated ProjectConfig.

    If no `ftk.yaml` is present, returns a default ProjectConfig (all commands
    enabled, no flavors). A warning is added so callers can surface it to users.
    """
    root = os.path.abspath(project_root)
    cfg_path = _find_config_file(root)
    cfg = ProjectConfig(
        id=project_id or os.path.basename(root),
        name=name or os.path.basename(root),
        root=root,
        config_path=cfg_path or "",
    )
    if not cfg_path:
        cfg.warnings.append(
            f"No ftk.yaml found in {root} - using defaults. "
            f"Run `ftk init` to create one."
        )
        return cfg

    raw, error = _load_yaml_file(cfg_path)
    if error:
        cfg.warnings.append(error)
        return cfg

    project_section = raw.get("project", {}) or {}
    cfg.id   = project_id or str(project_section.get("id", cfg.id))
    cfg.name = name       or str(project_section.get("name", cfg.name))

    cfg.flavors, cfg.default_flavor = _parse_flavors_section(raw)

    raw_langs = raw.get("languages") or []
    if isinstance(raw_langs, list) and raw_langs:
        cfg.languages = [str(l) for l in raw_langs]

    _apply_nested_sections(cfg, raw)

    return cfg


def write_template(project_root: str, *, with_flavors: bool = False) -> str:
    """Write a starter ftk.yaml into project_root and return its path."""
    dst = Path(project_root) / CONFIG_FILENAME
    if dst.exists():
        return str(dst)
    if with_flavors:
        tmpl = TEMPLATE_WITH_FLAVORS
    else:
        tmpl = TEMPLATE_MINIMAL
    dst.write_text(tmpl, encoding="utf-8")
    return str(dst)


TEMPLATE_MINIMAL = """\
# flutter-toolkit configuration (ftk.yaml)
project:
  id: my-flutter-app
  name: My Flutter App

languages: [en]

paths:
  lib_dir: lib
  translation_dir: assets/translations
  keys_file: lib/helpers/constants/translation_keys.dart
  entry_points: [lib/main.dart]

build:
  default_mode: release
  no_obfuscate: false
  desktop_targets: [windows, macos, linux]

commands:
  clean: true
  build: true
  info: true
  analyze: true
  test: true
  unused: true
  translations: true
  icons: false
  deploy: false
  backup: false
  sonar: false
  run: true
  notes: true
  help: true

integrations:
  server:
    host: 127.0.0.1
    port: 8742
"""


TEMPLATE_WITH_FLAVORS = TEMPLATE_MINIMAL + """\

flavors:
  - name: flavorA
    display_name: Flavor A
    ios_info_plist: Info-FlavorA.plist
    ios_config_dir: FlavorA
    web_new_prefix: true
    adaptive_bg: "#FFFFFF"
    notification_color: "#1B5E20"

default_flavor: flavorA
"""
