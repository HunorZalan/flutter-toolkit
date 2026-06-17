"""Flutter project info & diagnostics."""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ftk.common import (
    C, find_flutter, header, ok, warn, err, info,
    fmt_size, dir_size, run_cmd, run_capture, clear_flutter_lock,
)
from ftk.config import ProjectConfig


_SKIP_EXT = {".sha1", ".json", ".xml", ".txt", ".log", ".md"}
_ANDROID_STUDIO = "Android Studio"

# Default set of env checks if cfg.env_checks is empty
DEFAULT_ENV_CHECKS = {
    "Flutter", "Dart", "Python", "pip", "Git",
    "Java", "Kotlin", "Android SDK", "Gradle", "ADB",
    "Xcode", "CocoaPods", "Swift", "Ruby",
    "Node.js", "npm", "Homebrew", "Firebase CLI", "FlutterFire CLI", "Chrome", "Cordova", "Grunt",
    "PHP", "Pillow", "Rust",
    _ANDROID_STUDIO, "MySQL", "VS Code", "SonarScanner",
}


def _version_oneliner(cmd: list[str]) -> str:
    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, **kwargs)
        for line in result.stdout.strip().splitlines():
            if line.strip():
                return line.strip()
        for line in result.stderr.strip().splitlines():
            if line.strip():
                return line.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _win_cmd_fallback(cmd: str, args: list[str]) -> str:
    v = _version_oneliner([cmd] + args)
    if v:
        return v
    if sys.platform == "win32":
        return _version_oneliner([cmd + ".cmd"] + args)
    return ""


def _find_files(base_dir: str, extensions: set[str], *, recursive: bool = False):
    base = Path(base_dir)
    if not base.is_dir():
        return []
    items = base.rglob("*") if recursive else base.iterdir()
    results = []
    for f in sorted(items):
        if f.is_file() and f.suffix in extensions and f.suffix not in _SKIP_EXT:
            try:
                results.append((str(f.relative_to(base)), f.stat().st_size))
            except OSError:
                pass
    return results


def _print_section(label, items):
    if not items:
        return 0
    print(f"\n  {C.BOLD}[{label}]{C.RESET}")
    total = 0
    for name, size in items:
        ok(f"  {name:<50} {C.BOLD}{fmt_size(size):>10}{C.RESET}")
        total += size
    return total


def _find_app_bundles(ios_build_dir):
    base = Path(ios_build_dir)
    if not base.is_dir():
        return []
    results = []
    for config_dir in sorted(base.iterdir()):
        if not config_dir.is_dir() or config_dir.name == "ipa":
            continue
        for item in sorted(config_dir.iterdir()):
            if item.is_dir() and item.suffix == ".app":
                rel = str(item.relative_to(base))
                results.append((rel, dir_size(str(item))))
    return results


def _collect_web_items(project_root: str) -> list[tuple[str, int]]:
    items = []
    web_dir = os.path.join(project_root, "build", "web")
    if os.path.isdir(web_dir):
        items.append(("build/web/", dir_size(web_dir)))
    build_dir = os.path.join(project_root, "build")
    if not os.path.isdir(build_dir):
        return items
    for d in sorted(Path(build_dir).iterdir()):
        if d.is_dir() and d.name.startswith("web_"):
            items.append((f"build/{d.name}/", dir_size(str(d))))
    return items


def _collect_desktop_files(base_path: Path, project_root: str, exts: set[str]) -> list[tuple[str, int]]:
    items = []
    for f in sorted(base_path.rglob("*")):
        if f.is_file() and f.suffix in exts:
            try:
                items.append((str(f.relative_to(Path(project_root))), f.stat().st_size))
            except OSError:
                pass
    return items


def _collect_desktop_items(project_root: str, platform: str, exts: set[str]) -> list[tuple[str, int]]:
    base = os.path.join(project_root, "build", platform)
    if not os.path.isdir(base):
        return []
    base_path = Path(base)
    items = _collect_desktop_files(base_path, project_root, exts) if exts else []
    if platform == "macos":
        for d in sorted(base_path.rglob("*.app")):
            if d.is_dir():
                items.append((str(d.relative_to(Path(project_root))), dir_size(str(d))))
    return items


def show_build_sizes(project_root: str) -> None:
    header("Build Sizes")
    totals: dict[str, int] = {}

    def _section(label, items):
        if items:
            totals[label] = _print_section(label, items)
            return True
        return False

    found = False
    found |= _section("ANDROID APK", _find_files(os.path.join(project_root, "build", "app", "outputs", "flutter-apk"), {".apk"}))
    found |= _section("ANDROID AAB", _find_files(os.path.join(project_root, "build", "app", "outputs", "bundle"), {".aab"}, recursive=True))
    ios_build = os.path.join(project_root, "build", "ios")
    ios_apps = _find_app_bundles(ios_build)
    ios_ipas = _find_files(os.path.join(ios_build, "ipa"), {".ipa"})
    found |= _section("iOS", ios_apps + [("ipa/" + n, s) for n, s in ios_ipas])

    found |= _section("WEB", _collect_web_items(project_root))

    for platform, exts in (("windows", {".exe", ".msix"}), ("macos", {".dmg"}), ("linux", set())):
        found |= _section(platform.upper(), _collect_desktop_items(project_root, platform, exts))

    print()
    if not found:
        warn("No build artifacts found. Run a flutter build first.")
        return
    info("-" * 50)
    for lbl, total in totals.items():
        info(f"  {lbl} total: {fmt_size(total)}")


# -------- Environment checks --------

def _pillow_version() -> str:
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import PIL; print(PIL.__version__)"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _java_version() -> str:
    v = _version_oneliner(["java", "-version"])
    if v:
        return v
    jh = os.environ.get("JAVA_HOME", "")
    return f"JAVA_HOME={jh} (java not on PATH)" if jh else ""


def _kotlin_version() -> str:
    for cmd in (["kotlin", "-version"], ["kotlinc", "-version"]):
        v = _version_oneliner(cmd)
        if v:
            return v
    # Android Studio bundled kotlinc fallback
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Android",
                         _ANDROID_STUDIO, "plugins", "Kotlin", "kotlinc", "bin", "kotlinc.bat"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Android",
                         _ANDROID_STUDIO, "plugins", "Kotlin", "kotlinc", "bin", "kotlinc.bat"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Android Studio.app/Contents/plugins/Kotlin/kotlinc/bin/kotlinc",
        ]
    else:
        candidates = []
    for c in candidates:
        if os.path.isfile(c):
            v = _version_oneliner([c, "-version"])
            if v:
                return v
    return ""


def _php_version() -> str:
    v = _win_cmd_fallback("php", ["--version"])
    if v:
        return v
    if sys.platform == "darwin":
        for path in (
            "/Applications/XAMPP/xamppfiles/bin/php",
            "/opt/homebrew/bin/php",
        ):
            if os.path.isfile(path):
                v = _version_oneliner([path, "--version"])
                if v:
                    return v
    if sys.platform == "win32":
        for path in (
            r"C:\xampp\php\php.exe",
            r"C:\wamp64\bin\php\php.exe",
            os.path.join(os.environ.get("PROGRAMFILES", ""), "PHP", "php.exe"),
        ):
            if os.path.isfile(path):
                v = _version_oneliner([path, "--version"])
                if v:
                    return v
    return ""


def _composer_version() -> str:
    v = _win_cmd_fallback("composer", ["--version"])
    if v:
        return v
    if sys.platform == "darwin":
        for path in (
            os.path.expanduser("~/.composer/vendor/bin/composer"),
            "/Applications/XAMPP/xamppfiles/bin/composer",
            "/opt/homebrew/bin/composer",
        ):
            if os.path.isfile(path):
                v = _version_oneliner([path, "--version"])
                if v:
                    return v
    if sys.platform == "win32":
        bat = os.path.join(os.environ.get("APPDATA", ""), "Composer",
                           "vendor", "bin", "composer.bat")
        if os.path.isfile(bat):
            return _version_oneliner([bat, "--version"])
    return ""

def _ruby_version() -> str:
    v = _version_oneliner(["ruby", "--version"])
    if v:
        return v
    if sys.platform == "darwin":
        for path in (
            "/opt/homebrew/opt/ruby/bin/ruby",
            "/usr/local/opt/ruby/bin/ruby",
            "/usr/bin/ruby",
        ):
            if os.path.isfile(path):
                v = _version_oneliner([path, "--version"])
                if v:
                    return v
    elif sys.platform == "win32":
        sys_drive = os.environ.get("SYSTEMDRIVE", "C:") + "\\"
        if os.path.isdir(sys_drive):
            try:
                entries = sorted(os.listdir(sys_drive), reverse=True)
            except OSError:
                entries = []
            for entry in entries:
                if entry.lower().startswith("ruby"):
                    exe = os.path.join(sys_drive, entry, "bin", "ruby.exe")
                    if os.path.isfile(exe):
                        v = _version_oneliner([exe, "--version"])
                        if v:
                            return v
    return ""

def _get_android_sdk_root() -> str:
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ""
    if sdk and os.path.isdir(sdk):
        return sdk
    if sys.platform == "win32":
        candidate = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
    elif sys.platform == "darwin":
        candidate = os.path.expanduser("~/Library/Android/sdk")
    else:
        candidate = os.path.expanduser("~/Android/Sdk")
    return candidate if os.path.isdir(candidate) else ""


def _android_sdk_version() -> str:
    sdk = _get_android_sdk_root()
    if not sdk:
        return ""
    bt_dir = os.path.join(sdk, "build-tools")
    versions = []
    if os.path.isdir(bt_dir):
        versions = sorted(
            [d for d in os.listdir(bt_dir) if os.path.isdir(os.path.join(bt_dir, d))],
            reverse=True,
        )
    bt = versions[0] if versions else ""
    return f"{sdk}  |  build-tools: {bt}" if bt else sdk


def _gradle_version(project_root: str) -> str:
    props = os.path.join(project_root, "android", "gradle", "wrapper", "gradle-wrapper.properties")
    if os.path.isfile(props):
        try:
            for line in Path(props).read_text(encoding="utf-8").splitlines():
                if "distributionUrl" in line:
                    m = re.search(r"gradle-([0-9.]+)", line)
                    if m:
                        return f"{m.group(1)} (wrapper)"
        except OSError:
            pass
    return _version_oneliner(["gradle", "--version"])


def _adb_version() -> str:
    v = _version_oneliner(["adb", "--version"])
    if v:
        return v
    sdk = _get_android_sdk_root()
    if sdk:
        adb = os.path.join(sdk, "platform-tools", "adb.exe" if sys.platform == "win32" else "adb")
        if os.path.isfile(adb):
            return _version_oneliner([adb, "--version"])
    return ""


def _android_studio_version() -> str:
    if sys.platform == "win32":
        dirs = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Android", _ANDROID_STUDIO),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Android", _ANDROID_STUDIO),
        ]
    elif sys.platform == "darwin":
        dirs = ["/Applications/Android Studio.app/Contents/Resources"]
    else:
        return ""
    for d in dirs:
        p = os.path.join(d, "product-info.json")
        if os.path.isfile(p):
            try:
                data = json.loads(Path(p).read_text(encoding="utf-8"))
                v = data.get("dataDirectoryName", "").replace("AndroidStudio", "").strip()
                return f"{_ANDROID_STUDIO} {v}" if v else _ANDROID_STUDIO
            except (OSError, json.JSONDecodeError, KeyError):
                return _ANDROID_STUDIO
    return ""


def _mysql_version_win() -> str:
    for path, label in ((r"C:\xampp\mysql\bin\mysql.exe", "XAMPP"),):
        if not os.path.isfile(path):
            continue
        v = _version_oneliner([path, "--version"])
        if v:
            return f"[{label}] {v}"
    wamp = r"C:\wamp64\bin\mysql"
    if not os.path.isdir(wamp):
        return ""
    for ver in sorted(os.listdir(wamp), reverse=True):
        exe = os.path.join(wamp, ver, "bin", "mysql.exe")
        if not os.path.isfile(exe):
            continue
        v = _version_oneliner([exe, "--version"])
        if v:
            return f"[WAMP] {v}"
    return ""


def _mysql_version_mac() -> str:
    exe = "/Applications/XAMPP/xamppfiles/bin/mysql"
    if not os.path.isfile(exe):
        return ""
    v = _version_oneliner([exe, "--version"])
    return f"[XAMPP] {v}" if v else ""


def _mysql_version() -> str:
    v = _version_oneliner(["mysql", "--version"])
    if v:
        return v
    if sys.platform == "win32":
        return _mysql_version_win()
    if sys.platform == "darwin":
        return _mysql_version_mac()
    return ""


def _vscode_version() -> str:
    v = _win_cmd_fallback("code", ["--version"])
    if v:
        return v.splitlines()[0]
    if sys.platform == "darwin":
        mac_code = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
        if os.path.isfile(mac_code):
            v = _version_oneliner([mac_code, "--version"])
            return v.splitlines()[0] if v else ""
    return ""


def _sonar_version() -> str:
    v = _win_cmd_fallback("sonar-scanner", ["--version"])
    if v:
        return v
    if sys.platform == "win32":
        return _version_oneliner(["sonar-scanner.bat", "--version"])
    return ""

def _rust_version() -> str:
    v = _version_oneliner(["rustc", "--version"])
    if v:
        cargo = _version_oneliner(["cargo", "--version"])
        return f"{v}  |  {cargo}" if cargo else v

    # 2. Fallback: ~/.cargo/bin
    if sys.platform == "win32":
        cargo_bin = os.path.join(os.environ.get("USERPROFILE", ""), ".cargo", "bin")
        rustc_exe  = os.path.join(cargo_bin, "rustc.exe")
        cargo_exe  = os.path.join(cargo_bin, "cargo.exe")
    else:
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        rustc_exe  = os.path.join(cargo_bin, "rustc")
        cargo_exe  = os.path.join(cargo_bin, "cargo")

    if os.path.isfile(rustc_exe):
        v = _version_oneliner([rustc_exe, "--version"])
        if v:
            cargo_v = (
                _version_oneliner([cargo_exe, "--version"])
                if os.path.isfile(cargo_exe) else ""
            )
            return f"{v}  |  {cargo_v}" if cargo_v else v

    return ""

def _chrome_version() -> str:
    if sys.platform == "win32":
        ps_cmd = '(Get-Item "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe" -ErrorAction SilentlyContinue).GetValue("") | ForEach-Object { (Get-Item $_).VersionInfo.FileVersion }'
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            v = r.stdout.strip()
            if v:
                return f"Google Chrome {v}"
        except (OSError, subprocess.TimeoutExpired):
            pass
        return ""
    elif sys.platform == "darwin":
        return _version_oneliner(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"])
    return _version_oneliner(["google-chrome", "--version"])


def _dart_version(flutter_exe: str | None) -> str:
    if flutter_exe:
        sdk = Path(flutter_exe).resolve().parent.parent
        dart = sdk / "bin" / "cache" / "dart-sdk" / "bin" / ("dart.exe" if sys.platform == "win32" else "dart")
        if dart.is_file():
            return _version_oneliner([str(dart), "--version"])
    return _version_oneliner(["dart", "--version"])


def _flutterfire_version() -> str:
    v = _version_oneliner(["flutterfire", "--version"])
    if v:
        return v
    if sys.platform == "win32":
        pub_bin = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Pub", "Cache", "bin")
        exe = os.path.join(pub_bin, "flutterfire.bat")
    else:
        exe = os.path.expanduser("~/.pub-cache/bin/flutterfire")
    if os.path.isfile(exe):
        return _version_oneliner([exe, "--version"])
    return ""


def show_environment(enabled: set[str], flutter_exe: str | None, project_root: str) -> None:
    header("Development Environment")
    checks = [
        ("Flutter", lambda: run_capture([flutter_exe, "--version"], cwd=project_root).splitlines()[0] if flutter_exe else None),
        ("Dart", lambda: _dart_version(flutter_exe)),
        ("Python", lambda: _version_oneliner([sys.executable, "--version"])),
        ("pip", lambda: _version_oneliner([sys.executable, "-m", "pip", "--version"])),
        ("Git", lambda: _version_oneliner(["git", "--version"])),
        ("Java", _java_version),
        ("Rust", _rust_version),
        ("Kotlin", _kotlin_version),
        ("Android SDK", _android_sdk_version),
        ("Gradle", lambda: _gradle_version(project_root)),
        ("ADB", _adb_version),
        ("Xcode", lambda: _version_oneliner(["xcodebuild", "-version"]) if sys.platform == "darwin" else None),
        ("CocoaPods", lambda: _version_oneliner(["pod", "--version"]) if sys.platform == "darwin" else None),
        ("Swift", lambda: _version_oneliner(["swift", "--version"]) if sys.platform == "darwin" else None),
        ("Ruby", _ruby_version),
        ("Node.js", lambda: _version_oneliner(["node", "--version"])),
        ("Homebrew", lambda: _version_oneliner(["brew", "--version"]) if sys.platform == "darwin" else None),
        ("npm", lambda: _win_cmd_fallback("npm", ["--version"])),
        ("Firebase CLI", lambda: _win_cmd_fallback("firebase", ["--version"])),
        ("FlutterFire CLI", _flutterfire_version),
        ("Cordova", lambda: _win_cmd_fallback("cordova", ["--version"])),
        ("Grunt", lambda: _win_cmd_fallback("grunt", ["--version"])),
        ("Chrome", _chrome_version),
        ("PHP", _php_version),
        ("Composer", _composer_version),
        ("Pillow", _pillow_version),
        (_ANDROID_STUDIO, _android_studio_version),
        ("MySQL", _mysql_version),
        ("VS Code", _vscode_version),
        ("SonarScanner", _sonar_version),
    ]
    found = missing = 0
    for label, getter in checks:
        if label not in enabled:
            continue
        try:
            result = getter()
            if result is None:
                info(f"  {label:<16} n/a (not applicable on this platform)")
                continue
            if result:
                ok(f"{label:<16} {result}")
                found += 1
            else:
                warn(f"{label:<16} not found")
                missing += 1
        except Exception:
            warn(f"{label:<16} not found")
            missing += 1
    print()
    info(f"Found: {found}  |  Missing/skipped: {missing}")


def _parse_emulator_ids(output: str) -> list[str]:
    ids = []
    # Split on the bullet character used by `flutter emulators` output.
    # Using str.split avoids regex backtracking risk (S5852).
    _BULLET = " \u2022 "
    _BULLET_UTF8 = " \u00e2\u20ac\u00a2 "
    for line in output.splitlines():
        if _BULLET not in line and _BULLET_UTF8 not in line:
            continue
        parts = line.strip().split(_BULLET) if _BULLET in line else line.strip().split(_BULLET_UTF8)
        if len(parts) < 4:
            continue
        first = parts[0].strip()
        if first.lower() == "id" or " " in first:
            continue
        ids.append(first)
    return ids


def _show_devices(flutter_exe, project_root):
    header("Flutter & Dart Versions")
    if flutter_exe:
        for line in run_capture([flutter_exe, "--version"], cwd=project_root).splitlines():
            info(line)
        for line in run_capture([flutter_exe, "dart", "--version"], cwd=project_root).splitlines():
            info(line)
    header("flutter devices")
    if flutter_exe:
        run_cmd([flutter_exe, "devices"], cwd=project_root)


def _show_emulators(flutter_exe, project_root):
    header("flutter emulators")
    if not flutter_exe:
        return
    output = run_capture([flutter_exe, "emulators"], cwd=project_root)
    print(output)
    ids = _parse_emulator_ids(output)
    if not ids:
        return
    info("")
    info("Launch commands (copy & paste):")
    for eid in ids:
        ok(f"  flutter emulators --launch {eid}")


def _show_disk(project_root):
    header("Disk Usage")
    for path, label in [
        (os.path.join(project_root, "build"), "Project build/"),
        (os.path.join(project_root, ".dart_tool"), "Project .dart_tool/"),
        (os.path.expanduser("~/.pub-cache"), "Pub cache (~/.pub-cache)"),
        (os.path.expanduser("~/.gradle/caches"), "Gradle cache (~/.gradle/caches)"),
    ]:
        if os.path.isdir(path):
            ok(f"{label:<35} {fmt_size(dir_size(path)):<10}  {path}")
        else:
            warn(f"{label:<35} -  (not found)")
    if sys.platform == "darwin":
        dd = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
        if os.path.isdir(dd):
            ok(f"{'Xcode DerivedData':<35} {fmt_size(dir_size(dd)):<10}  {dd}")
    info("")
    info("Tip: run `ftk clean` to free up space.")


def _flutter_section(flutter_exe, project_root, title, cmd_args):
    """Run a single flutter command section with header."""
    header(title)
    if flutter_exe:
        run_cmd([flutter_exe, *cmd_args], cwd=project_root)


def _run_flutter_sections(flutter_exe, project_root, args, run_all):
    if run_all or args.doctor:
        _flutter_section(flutter_exe, project_root, "flutter doctor -v", ["doctor", "-v"])

    if run_all or args.deps is not None:
        style = args.deps or "tree"
        _flutter_section(flutter_exe, project_root,
                         f"flutter pub deps (--style={style})",
                         ["pub", "deps", f"--style={style}"])

    if run_all or args.outdated:
        _flutter_section(flutter_exe, project_root, "flutter pub outdated", ["pub", "outdated"])

    if run_all or args.config:
        _flutter_section(flutter_exe, project_root, "Flutter Config", ["config", "--list"])

    if args.android_licenses:
        _flutter_section(flutter_exe, project_root,
                         "flutter doctor --android-licenses", ["doctor", "--android-licenses"])

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

def _show_firebase_info(project_root: str) -> None:
    header("Firebase")
    import shutil as _shutil

    firebase_exe = _shutil.which("firebase") or (
        _shutil.which("firebase.cmd") if sys.platform == "win32" else None
    )

    if firebase_exe is None:
        warn("Firebase CLI not found.")
        info("Install: npm install -g firebase-tools")
        return

    run_cmd([firebase_exe, "--version"], cwd=project_root)

    try:
        r = subprocess.run(
            [firebase_exe, "projects:list"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        warn(f"firebase projects:list failed: {exc}")
        return

    stdout = r.stdout or ""        # ← None-biztos

    if r.returncode == 0:
        ok("Logged in. Projects:")
        for line in stdout.strip().splitlines()[:12]:
            clean = _strip_ansi(line)
            if clean.strip():
                info(f"  {clean}")
    else:
        warn("Not logged in - run `firebase login`")

def _run_basic_sections(run_all, args, flutter_exe, project_root, enabled):
    if run_all or args.env:
        show_environment(enabled, flutter_exe, project_root)
    if run_all or args.devices:
        _show_devices(flutter_exe, project_root)
    if run_all or args.emulators:
        _show_emulators(flutter_exe, project_root)
    if run_all or args.sizes:
        show_build_sizes(project_root)
    if run_all or args.disk:
        _show_disk(project_root)
    if run_all or args.firebase:
        _show_firebase_info(project_root)


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk info", description="Project info & diagnostics")
    parser.add_argument("--env", action="store_true")
    parser.add_argument("--sizes", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--devices", action="store_true")
    parser.add_argument("--emulators", action="store_true")
    parser.add_argument("--deps", choices=["tree", "compact"], const="tree", nargs="?")
    parser.add_argument("--outdated", action="store_true")
    parser.add_argument("--disk", action="store_true")
    parser.add_argument("--android-licenses", action="store_true")
    parser.add_argument("--config", action="store_true")
    parser.add_argument("--firebase", action="store_true")
    parser.add_argument("--mac-setup", action="store_true",
                        help="Configure Flutter PATH, Xcode, Simulator, and open the Runner workspaces (macOS only)")
    args = parser.parse_args(argv)

    project_root = cfg.root
    run_all = not any([args.env, args.sizes, args.doctor, args.devices, args.emulators,
                    args.deps is not None, args.outdated, args.disk, args.android_licenses,
                    args.config, args.firebase, args.mac_setup])

    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Info{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {project_root}")
    info(f"Mode         : {'all read-only sections' if run_all else 'selective'}")

    flutter_exe = find_flutter()
    if flutter_exe:
        ok(f"Flutter found: {flutter_exe}")
    else:
        warn("Flutter not found - Flutter-dependent sections will be skipped.")
    clear_flutter_lock(flutter_exe)

    enabled = set(cfg.env_checks) if cfg.env_checks else DEFAULT_ENV_CHECKS
    _run_basic_sections(run_all, args, flutter_exe, project_root, enabled)
    _run_flutter_sections(flutter_exe, project_root, args, run_all)

    if args.mac_setup or (run_all and sys.platform == "darwin"):
        _run_mac_setup(flutter_exe, project_root, cfg)

    print()
    return 0


def _setup_xcode(project_root):
    xcode_dev = "/Applications/Xcode.app/Contents/Developer"
    if not Path(xcode_dev).is_dir():
        warn(f"Xcode not found at {xcode_dev} - install Xcode from the App Store.")
        return
    if os.isatty(0):
        run_cmd(["sudo", "xcode-select", "--switch", xcode_dev],
                cwd=project_root, label="xcode-select --switch")
        run_cmd(["sudo", "xcodebuild", "-runFirstLaunch"],
                cwd=project_root, label="xcodebuild -runFirstLaunch")
        return
    warn("No interactive terminal - sudo commands skipped.")
    info("Run these manually in a terminal:")
    info(f"  sudo xcode-select --switch {xcode_dev}")
    info("  sudo xcodebuild -runFirstLaunch")


def _setup_precache(flutter_exe, project_root, cfg):
    if not flutter_exe:
        return
    precache_flags = []
    if cfg.platform_enabled("ios"):
        precache_flags.append("--ios")
    if cfg.platform_enabled("macos"):
        precache_flags.append("--macos")
    if not precache_flags:
        info("No Apple platforms enabled - skipping precache.")
        return
    label = "flutter precache " + " ".join(precache_flags)
    run_cmd([flutter_exe, "precache", *precache_flags],
            cwd=project_root, label=label)


def _open_workspaces(project_root, cfg):
    for app in ("Simulator", "Xcode"):
        run_cmd(["open", "-a", app], cwd=project_root, label=f"open -a {app}")

    for sub, platform in [("ios/Runner.xcworkspace", "ios"),
                           ("macos/Runner.xcworkspace", "macos")]:
        if not cfg.platform_enabled(platform):
            continue
        ws = os.path.join(project_root, sub)
        if os.path.isdir(ws):
            run_cmd(["open", ws], cwd=project_root, label=f"open {sub}")
        else:
            info(f"{sub} not found - skipping (run `flutter pub get` first).")


def _run_mac_setup(flutter_exe: str | None, project_root: str,
                   cfg: ProjectConfig) -> None:
    header("macOS setup")
    if sys.platform != "darwin":
        warn(f"--mac-setup only runs on macOS (current: {sys.platform}).")
        return

    # 1. Flutter PATH in ~/.zshrc
    flutter_bin = _flutter_bin_dir(flutter_exe)
    if flutter_bin:
        _ensure_path_in_zshrc(flutter_bin)
    else:
        warn("Flutter bin directory not discovered - skipping PATH patch.")

    # 2. Rosetta (Apple Silicon)
    import platform as _platform
    if _platform.machine() == "arm64":
        info("Apple Silicon detected - ensuring Rosetta 2 is installed...")
        run_cmd(["softwareupdate", "--install-rosetta", "--agree-to-license"],
                cwd=project_root, label="softwareupdate --install-rosetta")

    # 3. Xcode CLI + first-launch
    _setup_xcode(project_root)

    # 4. CocoaPods
    import shutil as _shutil
    if _shutil.which("pod") is None:
        info("CocoaPods not found - installing...")
        run_cmd(["sudo", "gem", "install", "cocoapods"],
                cwd=project_root, label="gem install cocoapods")
    else:
        ok(f"CocoaPods found: {_shutil.which('pod')}")

    # 5. Firebase CLI
    if _shutil.which("firebase") is None:          # _shutil, nem shutil!
        info("Firebase CLI not found - installing via brew...")
        run_cmd(["brew", "install", "firebase-cli"],
                cwd=project_root, label="brew install firebase-cli")
    else:
        ok(f"Firebase CLI found: {_shutil.which('firebase')}")

    # 6. FlutterFire CLI
    if _shutil.which("flutterfire") is None:       # _shutil, nem shutil!
        info("FlutterFire CLI not found - activating...")
        run_cmd(["dart", "pub", "global", "activate", "flutterfire_cli"],
                cwd=project_root, label="dart pub global activate flutterfire_cli")
    else:
        ok(f"FlutterFire CLI found: {_shutil.which('flutterfire')}")

    # 7. Firebase login check
    header("Firebase")
    _r = subprocess.run(["firebase", "projects:list"],
                        capture_output=True, text=True, timeout=10)
    if _r.returncode == 0:
        ok("Firebase: already logged in")
        for line in _r.stdout.strip().splitlines()[:6]:   # első pár projekt
            info(f"  {line}")
    else:
        warn("Firebase: not logged in")
        if os.isatty(0):
            run_cmd(["firebase", "login"], cwd=project_root, label="firebase login")
        else:
            info("Run manually: firebase login")
            
    # 8. flutter precache (active Apple platforms only)
    _setup_precache(flutter_exe, project_root, cfg)

    # 9. Available iOS simulators
    header("Available iOS Simulators")
    run_cmd(["xcrun", "simctl", "list", "devices", "available"],
            cwd=project_root, label="xcrun simctl list devices available")

    # 10. Base64-encoded FLAVOR strings (needed for Xcode build configs)
    if cfg.has_flavors:
        import base64
        header("Flavor base64 strings")
        for f in cfg.flavors:
            raw = f"FLAVOR={f.name}"
            encoded = base64.b64encode(raw.encode()).decode()
            ok(f"{raw:30s} -> {encoded}")

    # 11. Open apps + workspaces
    _open_workspaces(project_root, cfg)
    ok("macOS setup complete.")


def _flutter_bin_dir(flutter_exe: str | None) -> str | None:
    if not flutter_exe:
        return None
    p = Path(flutter_exe).resolve()
    # .../flutter/bin/flutter  ->  .../flutter/bin
    if p.parent.name == "bin":
        return str(p.parent)
    return None


def _ensure_path_in_zshrc(flutter_bin: str) -> None:
    zshrc = Path.home() / ".zshrc"
    line = f'export PATH="$PATH:{flutter_bin}"'
    try:
        existing = zshrc.read_text(encoding="utf-8") if zshrc.exists() else ""
    except OSError as exc:
        warn(f"Cannot read {zshrc}: {exc}")
        return
    if flutter_bin in existing:
        ok(f"PATH already contains {flutter_bin} in ~/.zshrc")
        return
    try:
        with open(zshrc, "a", encoding="utf-8") as f:
            prefix = "" if existing.endswith("\n") or not existing else "\n"
            f.write(f"{prefix}# Added by ftk --mac-setup\n{line}\n")
        ok(f"Appended Flutter PATH to {zshrc}")
        info("Run `source ~/.zshrc` in your shell to pick it up.")
    except OSError as exc:
        warn(f"Cannot append to {zshrc}: {exc}")
