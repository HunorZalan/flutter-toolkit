"""Builds the UI command metadata from a live ProjectConfig.

If `cfg.has_flavors` is false, flavor groups / presets are omitted entirely
(per user requirement E: hide ALL flavor UI when flavors are not defined).
Commands that are disabled by toggles or missing integration sections are
marked with `"disabled": True` so the UI can grey them out but keep the tab
visible in navigation.

Host-OS awareness: options that require a specific host OS (e.g. CocoaPods →
macOS, .exe build → Windows) are marked disabled when the server runs on a
different platform.  This is separate from the *target-platform* toggles in
ftk.yaml (``cfg.platform_enabled``), which express what the *project* ships.
An option is disabled if *either* check fails.
"""
from __future__ import annotations
import sys
from typing import Any

from ftk.config import ProjectConfig

COMMAND_ORDER = [
    "clean", "build", "deploy", "backup", "info", "analyze", "codegen",
    "icons", "unused", "translations", "test", "run", "sonar", "notes", "help",
]

_DRY_RUN = "Dry run (preview only)"
_HINT_DEFAULT_FLAVOR = "No selection = default flavor"
_HINT_ALL = "No selection = all"
_FMT_7Z = "--format 7z"

_IS_MAC = sys.platform == "darwin"
_IS_WIN = sys.platform == "win32"
_IS_LINUX = sys.platform.startswith("linux")

# Map platform names to the host OS that can actually execute them.
_HOST_REQUIRED: dict[str, str] = {
    "ios": "darwin", "macos": "darwin",
    "windows": "win32", "linux": "linux",
}

# Common language code → display name (for tooltips).
_LANG_NAMES: dict[str, str] = {
    "en": "English", "hu": "Hungarian", "ro": "Romanian", "ru": "Russian",
    "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "cs": "Czech",
    "sk": "Slovak", "bg": "Bulgarian", "uk": "Ukrainian", "hr": "Croatian",
    "sr": "Serbian", "sl": "Slovenian", "tr": "Turkish", "ar": "Arabic",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "hi": "Hindi",
    "sv": "Swedish", "da": "Danish", "fi": "Finnish", "nb": "Norwegian",
    "el": "Greek", "he": "Hebrew", "th": "Thai", "vi": "Vietnamese",
}


def _host_can_run(platform: str) -> bool:
    """True if the current host OS can execute builds / commands for *platform*."""
    required = _HOST_REQUIRED.get(platform)
    if required is None:
        return True
    if required == "linux":
        return _IS_LINUX
    return sys.platform == required


def _platform_disabled(cfg: ProjectConfig, platform: str) -> bool:
    """Disabled if the project turned off the platform OR the host can't run it."""
    return not cfg.platform_enabled(platform) or not _host_can_run(platform)


def _flavor_options(cfg: ProjectConfig, flag_prefix: str = "-f") -> list[dict]:
    return [{"flag": f"{flag_prefix} {f.name}", "label": f.name, "disabled": False,
             "tip": f"Build the {f.display_name or f.name} flavor."}
            for f in cfg.flavors]


def _flavor_group(cfg: ProjectConfig, hint: str = _HINT_DEFAULT_FLAVOR) -> dict | None:
    if not cfg.has_flavors:
        return None
    return {"label": "Flavor", "type": "checkboxes", "hint": hint,
            "options": _flavor_options(cfg)}


def _flavor_presets(cfg: ProjectConfig, base_flags: list[str]) -> list[dict]:
    if not cfg.has_flavors:
        return []
    out = [{"label": f.name, "flags": [f"-f {f.name}", *base_flags], "disabled": False}
           for f in cfg.flavors]
    out.append({"label": "All", "flags": base_flags, "default": True, "disabled": False})
    return out


# ---- Clean ----

def _clean(cfg: ProjectConfig) -> dict:
    mac_off = not _IS_MAC
    return {
        "title": "Clean & Reinstall", "icon": "broom", "description":
            "Reset project state, kill processes, clean builds, reinstall dependencies.",
        "script": "clean", "inject_flags": [],
        "groups": [
            {"label": "Steps", "type": "checkboxes", "hint": "No selection = full reset",
             "options": [
                 {"flag": "--kill", "label": "Kill dart/flutter processes"},
                 {"flag": "--clean", "label": "Flutter clean + delete pubspec.lock + ios/Pods"},
                 {"flag": "--build-cache", "label": "Delete build/ and .dart_tool/"},
                 {"flag": "--android", "label": "Android gradlew clean + cache",
                  "disabled": _platform_disabled(cfg, "android")},
                 {"flag": "--ios", "label": "iOS pod deintegrate + DerivedData",
                  "disabled": _platform_disabled(cfg, "ios")},
                 {"flag": "--derived-data", "label": "Delete Xcode DerivedData/Runner-*", "disabled": mac_off},
                 {"flag": "--get", "label": "Flutter pub get (+ pod install on macOS)"},
                 {"flag": "--upgrade", "label": "Pub upgrade --major-versions"},
                 {"flag": "--pub-cache", "label": "Pub cache clean (global)"},
                 {"flag": "--flutter-upgrade", "label": "Flutter SDK upgrade"},
             ]},
            {"label": "Pub diagnostics", "type": "checkboxes", "options": [
                 {"flag": "--pub-outdated", "label": "Pub outdated (report only)"},
                 {"flag": "--pub-deps", "label": "Pub deps (dependency tree)"},
                 {"flag": "--upgrade-dry-run", "label": "Pub upgrade --dry-run (preview)"},
            ]},
            {"label": "Pub resolution mode", "type": "select",
             "hint": "How pub get / upgrade resolves packages",
             "options": [
                 {"flag": "", "label": "Default (online)"},
                 {"flag": "--pub-offline", "label": "--offline (use cached packages)"},
                 {"flag": "--pub-enforce-lockfile", "label": "--enforce-lockfile (CI / prod)"},
             ]},
            {"label": "Pub options", "type": "checkboxes", "options": [
                 {"flag": "--no-precompile", "label": "--no-precompile"},
                 {"flag": "--no-example", "label": "--no-example"},
            ]},
            {"label": "CocoaPods (macOS)", "type": "checkboxes",
             "hint": "Runs in ios/ (and macos/ if present).",
             "options": [
                 {"flag": "--pod-install",       "label": "pod install",               "disabled": mac_off},
                 {"flag": "--pod-repo-update",   "label": "pod install --repo-update", "disabled": mac_off},
                 {"flag": "--pod-clean-install",  "label": "pod install --clean-install","disabled": mac_off},
                 {"flag": "--pod-verbose",       "label": "pod install --verbose",     "disabled": mac_off},
                 {"flag": "--pod-update",        "label": "pod update",                "disabled": mac_off},
                 {"flag": "--pod-update-no-repo","label": "pod update --no-repo-update","disabled": mac_off},
                 {"flag": "--pod-deintegrate",   "label": "pod deintegrate",           "disabled": mac_off},
                 {"flag": "--pod-cache-clean",   "label": "pod cache clean --all",     "disabled": mac_off},
                 {"flag": "--pod-repo-list",     "label": "pod repo list",             "disabled": mac_off},
                 {"flag": "--pod-env",           "label": "pod env",                   "disabled": mac_off},
             ]},
            {"label": "Xcode (macOS)", "type": "checkboxes", "options": [
                 {"flag": "--open-xcode", "label": "Open Runner.xcworkspace in Xcode", "disabled": mac_off},
            ]},
            {"label": "Options", "type": "checkboxes", "options": [
                {"flag": "--yes", "label": "Auto-confirm prompts", "default": True},
                {"flag": "--dry-run", "label": _DRY_RUN},
            ]},
        ],
        "presets": [
            {"label": "Android only", "flags": ["--clean", "--build-cache", "--android", "--get", "--yes"],
            "disabled": _platform_disabled(cfg, "android")},
            {"label": "iOS only", "flags": ["--clean", "--build-cache", "--ios", "--get", "--yes"],
            "disabled": _platform_disabled(cfg, "ios")},
            {"label": "iOS full", "flags": ["--clean", "--build-cache", "--ios", "--get",
                                            "--pod-install", "--derived-data", "--yes"],
            "disabled": _platform_disabled(cfg, "ios")},
            {"label": "Quick",        "flags": ["--clean", "--get", "--yes"]},
            {"label": "Full reset",     "flags": [
                "--kill", "--clean", "--build-cache", "--android", "--ios",
                "--get", "--pub-cache", "--yes",
            ]},
            {"label": "Full + Upgrade", "flags": [
                "--kill", "--clean", "--build-cache", "--android", "--ios",
                "--get", "--pub-cache", "--upgrade", "--flutter-upgrade", "--yes",
            ], "default": True},
            {"label": "Upgrade only",   "flags": ["--upgrade", "--flutter-upgrade", "--yes"],},
        ],
    }


# ---- Build ----

def _build(cfg: ProjectConfig) -> dict:
    def opt(flag: str, label: str, platform: str) -> dict:
        return {"flag": flag, "label": label,
                "disabled": _platform_disabled(cfg, platform)}

    groups = [
        {"label": "Build Types", "type": "checkboxes", "hint": _HINT_ALL, "options": [
            opt("--web", "Web (release)",            "web"),
            opt("--apk", "Android APK",              "android"),
            opt("--aab", "Android App Bundle (AAB)", "android"),
            opt("--ios", "iOS app (macOS only)",     "ios"),
            opt("--ipa", "IPA for App Store (macOS only)", "ios"),
            opt("--windows", "Windows (.exe)", "windows"),
            opt("--macos",   "macOS (.app)",   "macos"),
            opt("--linux",   "Linux (ELF)",    "linux"),
        ]},
    ]
    fg = _flavor_group(cfg)
    if fg:
        groups.append(fg)
    groups.extend([
        {"label": "Mode", "type": "select", "options": [
            {"flag": "", "label": "release (default)"},
            {"flag": "-m debug", "label": "debug"},
        ]},
        {"label": "Options", "type": "checkboxes", "options": [
            {"flag": "--yes", "label": "Auto-confirm prompts", "default": True},
            {"flag": "--dry-run", "label": _DRY_RUN},
            {"flag": "--verbose", "label": "Verbose flutter output"},
            {"flag": "--no-obfuscate", "label": "Skip obfuscation on release"},
        ]},
    ])
    return {
        "title": "Build", "icon": "hammer", "description":
            "Build web / Android / iOS / desktop artifacts.",
        "script": "build", "inject_flags": [],
        "groups": groups,
        "presets": _build_presets(cfg),
    }


def _build_presets(cfg: ProjectConfig) -> list[dict]:
    mobile_flags = []
    if not _platform_disabled(cfg, "android"):
        mobile_flags.extend(["--apk", "--aab"])
    if not _platform_disabled(cfg, "ios"):
        mobile_flags.extend(["--ios", "--ipa"])
    return [
        {"label": "Web", "flags": ["--web", "--yes"],
         "disabled": _platform_disabled(cfg, "web")},
        {"label": "All mobile", "flags": mobile_flags + ["--yes"],
         "disabled": not mobile_flags},
        {"label": "Android", "flags": ["--apk", "--aab", "--yes"],
         "disabled": _platform_disabled(cfg, "android")},
        {"label": "iOS + IPA", "flags": ["--ios", "--ipa", "--yes"],
         "disabled": _platform_disabled(cfg, "ios")},
        {"label": "All", "flags": ["--yes"], "default": True},
    ]


# ---- Info ----

def _info() -> dict:
    return {
        "title": "Info & Diagnostics", "icon": "chart",
        "description": "Read-only project diagnostics.",
        "script": "info",
        "groups": [
            {"label": "Sections", "type": "checkboxes", "hint": _HINT_ALL, "options": [
                {"flag": "--env", "label": "Development environment"},
                {"flag": "--sizes", "label": "Build artifact sizes"},
                {"flag": "--doctor", "label": "Flutter doctor -v"},
                {"flag": "--devices", "label": "Connected devices"},
                {"flag": "--emulators", "label": "Available emulators"},
                {"flag": "--deps", "label": "Dependency tree"},
                {"flag": "--outdated", "label": "Outdated packages"},
                {"flag": "--disk", "label": "Disk usage"},
                {"flag": "--android-licenses", "label": "Accept Android SDK licenses"},
                {"flag": "--config", "label": "Flutter config"},
                {"flag": "--firebase",         "label": "Firebase status & projects"},
                {"flag": "--mac-setup", "label": "macOS setup (PATH + Xcode + workspaces)", "disabled": not _IS_MAC},
            ]},
        ],
    }


# ---- Analyze ----

def _analyze() -> dict:
    return {
        "title": "Analyze & Format", "icon": "shield",
        "description": "Static analysis, auto-fix, formatting.",
        "script": "analyze", "inject_flags": [],
        "groups": [
            {"label": "Analysis", "type": "checkboxes", "hint": _HINT_ALL, "options": [
                {"flag": "--analyze", "label": "Flutter analyze"},
                {"flag": "--fatal-infos", "label": "Treat info issues as fatal"},
                {"flag": "--no-fatal-warnings", "label": "Don\u2019t treat warnings as fatal"},
                {"flag": "--metrics", "label": "Code metrics"},
            ]},
            {"label": "Formatting", "type": "checkboxes", "options": [
                {"flag": "--format-check", "label": "Check formatting (read-only)"},
                {"flag": "--format", "label": "Apply formatting (modifies files!)"},
            ]},
            {"label": "Auto-fix", "type": "checkboxes", "options": [
                {"flag": "--fix-preview", "label": "Preview fixes (dry-run)"},
                {"flag": "--fix", "label": "Apply fixes (modifies files!)"},
            ]},
            {"label": "Options", "type": "checkboxes", "options": [
                {"flag": "--dry-run", "label": _DRY_RUN},
            ]},
        ],
    }
    
# ---- Codegen ----

def _codegen() -> dict:
    return {
        "title": "Code Generation", "icon": "hammer",
        "description": (
            "Run build_runner to generate Dart code. "
            "flutter_gen_runner runs automatically if present in pubspec."
        ),
        "script": "codegen", "inject_flags": [],
        "groups": [
            {"label": "Action", "type": "checkboxes",
             "hint": "No selection = build (default)",
             "options": [
                 {"flag": "--build", "label": "build (one-shot generation)"},
                 {"flag": "--watch", "label": "watch (continuous, Stop to exit)"},
                 {"flag": "--clean", "label": "clean cache, then build"},
             ]},
            {"label": "Options", "type": "checkboxes", "options": [
                {"flag": "--dry-run", "label": "Dry run (preview only)"},
            ]},
        ],
        "presets": [
            {"label": "Build",   "flags": ["--build"], "default": True},
            {"label": "Watch",   "flags": ["--watch"]},
            {"label": "Clean + Build", "flags": ["--clean", "--build"]},
        ],
    }



# ---- Icons ----

def _icons(cfg: ProjectConfig) -> dict:
    groups = []
    fg = _flavor_group(cfg, "No selection = all flavors")
    if fg:
        groups.append(fg)

    def popt(flag: str, label: str, platform: str) -> dict:
        return {"flag": flag, "label": label,
                "disabled": not cfg.platform_enabled(platform)}

    groups.extend([
        {"label": "Platform", "type": "checkboxes", "hint": "No selection = ios/android/web", "options": [
            popt("-p ios",     "iOS",              "ios"),
            popt("-p android", "Android",          "android"),
            popt("-p web",     "Web",              "web"),
            popt("-p windows", "Windows (.ico)",   "windows"),
            popt("-p macos",   "macOS (appiconset)", "macos"),
            popt("-p linux",   "Linux (PNG)",      "linux"),
        ]},
        {"label": "Options", "type": "checkboxes", "options": [
            {"flag": "-n", "label": "Only generate missing files"},
        ]},
    ])
    mobile_flags = [f for f in ["-p ios", "-p android"]
                     if not _platform_disabled(cfg, f.split()[-1])]
    desktop_flags = [f for f in ["-p windows", "-p macos", "-p linux"]
                      if not _platform_disabled(cfg, f.split()[-1])]
    return {
        "title": "Icon Generator", "icon": "palette",
        "description": "Generate iOS/Android/Web/Desktop icons. Requires Pillow.",
        "script": "icons", "groups": groups,
        "presets": [
            {"label": "Web", "flags": ["-p web"],
             "disabled": _platform_disabled(cfg, "web")},
            {"label": "Mobile", "flags": mobile_flags,
             "disabled": not mobile_flags},
            {"label": "Desktop", "flags": desktop_flags,
             "disabled": not desktop_flags},
        ],
        "disabled": not cfg.has_flavors,
    }


# ---- Unused ----

def _unused() -> dict:
    return {
        "title": "Unused Dart Files", "icon": "search",
        "description": "Find unused .dart files in lib/. Read-only.",
        "script": "unused",
        "groups": [
            {"label": "Options", "type": "checkboxes", "options": [
                {"flag": "--include-commented", "label": "Count commented-out imports"},
            ]},
        ],
    }


# ---- Translations ----

def _translations(cfg: ProjectConfig) -> dict:
    lang_options = [{"flag": f"--lang {lng}", "label": lng,
                     "tip": f"Check {_LANG_NAMES.get(lng, lng)} translations only."}
                    for lng in cfg.languages]
    return {
        "title": "Translation Checker", "icon": "globe",
        "description": "Validate translation JSON files. Read-only.",
        "script": "translations",
        "groups": [
            {"label": "Languages", "type": "checkboxes", "hint": _HINT_ALL,
             "options": lang_options},
        ],
    }


# ---- Test ----

def _test() -> dict:
    return {
        "title": "Test", "icon": "check",
        "description": "Run Flutter tests with optional coverage.",
        "script": "test", "inject_flags": [],
        "groups": [
            {"label": "Coverage", "type": "checkboxes", "options": [
                {"flag": "--coverage", "label": "Collect code coverage"},
                {"flag": "--html", "label": "Generate HTML coverage report (requires lcov)"},
            ]},
            {"label": "Reporter", "type": "select", "options": [
                {"flag": "", "label": "compact (default)"},
                {"flag": "--reporter expanded", "label": "expanded"},
                {"flag": "--reporter json", "label": "json"},
            ]},
            {"label": "Options", "type": "checkboxes", "options": [
                {"flag": "--dry-run", "label": _DRY_RUN},
            ]},
        ],
    }


# ---- Deploy ----

def _deploy(cfg: ProjectConfig) -> dict:
    from pathlib import Path as _Path
    build_root = _Path(cfg.root) / "build"
    flavor_names = [f.name for f in cfg.flavors] if cfg.has_flavors else [None]
    missing_builds = []
    for fname in flavor_names:
        candidates = []
        if fname:
            candidates.append(build_root / f"web_{fname}")
        candidates.append(build_root / "web")
        if not any((c / "index.html").exists() for c in candidates):
            missing_builds.append(fname or "default")

    groups = []
    fg = _flavor_group(cfg)
    if fg:
        groups.append(fg)

    has_dev = any(t.dev_remote_path for t in cfg.integrations.deploy)
    if has_dev:
        groups.append({
            "label": "Environment",
            "type": "select",
            "options": [
                {"flag": "",            "label": "Production (default)"},
                {"flag": "--env dev",   "label": "Development"},
                {"flag": "--env both",  "label": "Both (prod + dev)"},
            ],
        })

    groups.extend([
        {"label": "Action", "type": "checkboxes", "hint": "Check to list targets only", "options": [
            {"flag": "--list-targets", "label": "List configured targets (no deploy)"},
        ]},
        {"label": "Options", "type": "checkboxes", "options": [
            {"flag": "--yes",       "label": "Auto-confirm", "default": True},
            {"flag": "--no-backup", "label": "Skip backup"},
            {"flag": "--dry-run",   "label": _DRY_RUN},
        ]},
    ])

    result = {
        "title": "Deploy", "icon": "upload",
        "description": "Upload web build to remote server.",
        "script": "deploy", "inject_flags": [],
        "groups": groups,
        "presets": _flavor_presets(cfg, ["--yes"]) + [
            {"label": "List targets", "flags": ["--list-targets"]},
        ],
        "disabled": not cfg.command_enabled("deploy"),
    }
    if missing_builds:
        result["warning"] = f"⚠ No web build for: {', '.join(missing_builds)} - run Build → Web first."
    return result


# ---- Run ----

def _run_cmds(cfg: ProjectConfig) -> dict:
    _mobile: list[tuple[str, str, str]] = [
        ("android", "Android \u00b7 Debug",   "flutter run --flavor {f} --debug --dart-define=FLAVOR={f}"),
        ("android", "Android \u00b7 Release", "flutter run --flavor {f} --release --dart-define=FLAVOR={f}"),
        ("android", "Android \u00b7 Profile", "flutter run --flavor {f} --profile --dart-define=FLAVOR={f}"),
        ("ios",     "iOS \u00b7 Debug",       "flutter run --flavor {f} --debug --dart-define=FLAVOR={f}"),
        ("ios",     "iOS \u00b7 Release",     "flutter run --flavor {f} --release --dart-define=FLAVOR={f}"),
        ("ios",     "iOS \u00b7 Profile",     "flutter run --flavor {f} --profile --dart-define=FLAVOR={f}"),
    ]
    cmds: list[dict] = []
    if cfg.has_flavors:
        _other: list[tuple[str, str, str]] = [
            ("web",     "Web (Chrome)",  "flutter run -d chrome --dart-define=FLAVOR={f}"),
            ("windows", "Windows",       "flutter run -d windows --dart-define=FLAVOR={f} --debug"),
            ("macos",   "macOS",         "flutter run -d macos --flavor {f} --debug"),
            ("linux",   "Linux",         "flutter run -d linux --dart-define=FLAVOR={f} --debug"),
        ]
        for platform, label, fmt in _mobile + _other:
            disabled = _platform_disabled(cfg, platform)
            for f in cfg.flavors:
                cmds.append({"cmd": fmt.format(f=f.name), "mode": label,
                             "disabled": disabled})
    else:
        _plain: list[tuple[str, str, str]] = [
            ("web",     "Web (Chrome)",  "flutter run -d chrome"),
            ("windows", "Windows",       "flutter run -d windows --debug"),
            ("macos",   "macOS",         "flutter run -d macos --debug"),
            ("linux",   "Linux",         "flutter run -d linux --debug"),
        ]
        for platform, label, raw in _mobile + _plain:
            cmds.append({"cmd": raw, "mode": label,
                         "disabled": _platform_disabled(cfg, platform)})
    return {
        "title": "Run Launcher", "icon": "hammer",
        "static": True, "fullscreen": True, "hide_run_controls": False,
        "description": "Copyable flutter run commands for development.",
        "script": "", "groups": [], "run_commands": cmds,
    }


# ---- Backup ----

def _backup(cfg: ProjectConfig) -> dict:
    return {
        "title": "Backup", "icon": "archive",
        "description": "Archive the project. Default output: ../<project>_backups/",
        "script": "backup", "inject_flags": [],
        "groups": [
            {"label": "Format", "type": "select", "options": [
                {"flag": _FMT_7Z,      "label": "7-Zip (.7z) - encrypted headers"},
                {"flag": "--format zip",     "label": "ZIP (.zip) - universal"},
                {"flag": "--format tar.gz",  "label": "TAR+GZip - fast"},
                {"flag": "--format tar.bz2", "label": "TAR+BZip2 - balanced"},
                {"flag": "--format tar.xz",  "label": "TAR+XZ - best ratio"},
                {"flag": "--format tar.zst", "label": "TAR+Zstd - modern"},
                {"flag": "--format tar",     "label": "TAR - no compression"},
            ]},
            {"label": "Exclude folders & files", "type": "dynamic_folders",
             "hint": "Default-excluded entries are pre-checked."},
            {"label": "Rotation", "type": "select", "options": [
                {"flag": "",          "label": "Keep all (default)"},
                {"flag": "--keep 3",  "label": "Keep last 3"},
                {"flag": "--keep 5",  "label": "Keep last 5"},
                {"flag": "--keep 10", "label": "Keep last 10"},
                {"flag": "--keep 20", "label": "Keep last 20"},
            ]},
            {"label": "Options", "type": "checkboxes", "options": [
                {"flag": "--yes",                 "label": "Auto-confirm", "default": True},
                {"flag": "--dry-run",             "label": _DRY_RUN},
                {"flag": "--no-default-excludes", "label": "Include everything (no default excludes)"},
            ]},
        ],
        "presets": [
            {"label": "Quick", "flags": [_FMT_7Z, "--yes"], "default": True},
            {"label": "Full archive", "flags": [_FMT_7Z, "--no-default-excludes", "--yes"]},
            {"label": "Best ratio", "flags": ["--format tar.xz", "--yes"]},
            {"label": "Keep last 5", "flags": [_FMT_7Z, "--keep 5", "--yes"]},
        ],
        "disabled": not cfg.command_enabled("backup"),
    }


# ---- Sonar ----

def _sonar(cfg: ProjectConfig) -> dict:
    sonar_cfg = cfg.integrations.sonar if cfg.integrations else None
    scanner_name = (sonar_cfg.scanner_name if sonar_cfg else "") or "sonar-scanner"
    cmd_only = scanner_name.lower().endswith((".cmd", ".bat")) and not _IS_WIN

    return {
        "title": "Sonar Scanner", "icon": "search",
        "description": "Runs configured SonarScanner from the project root.",
        "script": "sonar", "groups": [],
        "disabled": not cfg.command_enabled("sonar") or cmd_only,
        "disabled_reason": "Scanner is Windows-only (.cmd)" if cmd_only else None,
    }


# ---- Notes ----

def _notes() -> dict:
    return {
        "title": "Notes", "icon": "edit",
        "static": True, "fullscreen": True, "type": "notes",
        "description": "Quick notes. Auto-saved.",
        "script": "", "groups": [],
    }


# ---- Help ----

def _help(cfg: ProjectConfig) -> dict:
    enabled_cmds = [k for k in COMMAND_ORDER if k not in ("notes", "help", "run")]
    return {
        "title": "Help & Usage", "icon": "help",
        "description": "Show command-line usage.",
        "script": "help",
        "groups": [
            {"label": "Sections", "type": "checkboxes", "hint": "No selection = show everything",
             "options": [{"flag": k, "label": k} for k in enabled_cmds]},
        ],
    }


# ---- Normalise + build ----

def _normalise_option_fields(block: dict) -> dict:
    for grp in block.get("groups", []):
        for opt in grp.get("options", []) or []:
            opt.setdefault("disabled", False)
    for preset in block.get("presets", []) or []:
        preset.setdefault("disabled", False)
    for rc in block.get("run_commands", []) or []:
        rc.setdefault("disabled", False)
    block.setdefault("disabled", False)
    block.setdefault("static", False)
    block.setdefault("fullscreen", False)
    block.setdefault("hide_run_controls", False)
    return block


def build(cfg: ProjectConfig) -> dict[str, Any]:
    """Return the full COMMANDS_CONFIG dict for the UI."""
    registry = {
        "clean":        _clean(cfg),
        "build":        _build(cfg),
        "deploy":       _deploy(cfg),
        "backup":       _backup(cfg),
        "info":         _info(),
        "analyze":      _analyze(),
        "codegen":      _codegen(),
        "icons":        _icons(cfg),
        "unused":       _unused(),
        "translations": _translations(cfg),
        "test":         _test(),
        "run":          _run_cmds(cfg),
        "sonar":        _sonar(cfg),
        "notes":        _notes(),
        "help":         _help(cfg),
    }
    out: dict[str, Any] = {}
    for key in COMMAND_ORDER:
        if key not in registry:
            continue
        block = registry[key]
        if not cfg.command_enabled(key) and key not in ("run", "notes", "help"):
            block["disabled"] = True
        out[key] = _normalise_option_fields(block)
    return out
