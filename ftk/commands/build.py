"""Flavor-aware Flutter builder (web / apk / aab / ios / ipa / desktop)."""
from __future__ import annotations
import argparse
import os
import shutil
import sys

from ftk.common import (
    C, find_flutter, header, ok, warn, err, info,
    run_cmd, clear_flutter_lock,
)
from ftk.config import ProjectConfig, FlavorConfig


ALL_BUILD_TYPES = ("web", "apk", "aab", "ios", "ipa")
DESKTOP_BUILD_TYPES = ("windows", "macos", "linux")
_GOOGLE_PLIST = "GoogleService-Info.plist"
ALL_PLATFORMS = (*ALL_BUILD_TYPES, *DESKTOP_BUILD_TYPES)
_TYPE_SHORTCUTS = {
    "android": ("apk", "aab"),
    "ios_all": ("ios", "ipa"),
    "desktop": ("windows", "macos", "linux"),
}


def _p(project_root: str, *parts: str) -> str:
    return os.path.join(project_root, *parts)


def _check_platform_for_desktop(build_type: str) -> bool:
    platform_map = {"windows": ("win32",), "macos": ("darwin",), "linux": ("linux",)}
    required = platform_map.get(build_type, ())
    if sys.platform not in required:
        warn(f"{build_type} build requires {required[0] if required else '?'} - skipping on {sys.platform}.")
        return False
    return True


def _check_macos() -> bool:
    if sys.platform != "darwin":
        warn(f"iOS builds require macOS - skipping on {sys.platform}.")
        return False
    return True


def _copy_file(src, dst, label, *, dry_run: bool) -> bool:
    if dry_run:
        info(f"[dry-run] would copy: {label}")
        return True
    if not os.path.exists(src):
        err(f"Source not found: {src}")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    ok(f"Copied: {label}")
    return True


def _copy_dir(src, dst, label, *, dry_run: bool) -> bool:
    if dry_run:
        info(f"[dry-run] would copy directory: {label}")
        return True
    if not os.path.isdir(src):
        err(f"Source directory not found: {src}")
        return False
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    ok(f"Copied directory: {label}")
    return True


def _postbuild_copy_assets(src_dir, dst_dir, files, *, dry_run):
    all_ok = True
    for fname in files:
        src = os.path.join(src_dir, fname)
        dst = os.path.join(dst_dir, fname)
        if not os.path.exists(src):
            warn(f"{fname} not found in {src_dir}/ - skipping")
            continue
        if not _copy_file(src, dst, f"{fname} -> build/web/", dry_run=dry_run):
            all_ok = False
    return all_ok


def _postbuild_copy_icons(src_dir, dst_dir, web_assets_dir, *, dry_run):
    icons_src = os.path.join(src_dir, "icons")
    icons_dst = os.path.join(dst_dir, "icons")
    if not os.path.isdir(icons_src):
        warn(f"icons/ not found in {web_assets_dir}/ - skipping")
        return True
    return _copy_dir(icons_src, icons_dst, "icons/ -> build/web/icons/", dry_run=dry_run)


def _postbuild_web(flavor: FlavorConfig, *, cfg: ProjectConfig, dry_run: bool, default_flavor: str) -> bool:
    src_dir = _p(cfg.root, flavor.web_assets_dir)
    dst_dir = _p(cfg.root, "build", "web")
    if not os.path.isdir(src_dir):
        if flavor.name != default_flavor:
            err(f"Web assets directory not found: {src_dir}")
            return False
        info(f"Web assets dir not found ({flavor.web_assets_dir}) - skipping copy for default flavor.")
        return True
    if not dry_run and not os.path.isdir(dst_dir):
        err(f"Build output not found: {dst_dir} - did the build fail?")
        return False
    info(f"Post-build: replacing web assets from {flavor.web_assets_dir}/")
    files_ok = _postbuild_copy_assets(src_dir, dst_dir, cfg.paths.web_post_build_files, dry_run=dry_run)
    icons_ok = _postbuild_copy_icons(src_dir, dst_dir, flavor.web_assets_dir, dry_run=dry_run)
    all_ok = files_ok and icons_ok
    if all_ok:
        ok("Web post-build complete.")
    return all_ok


def _android_cmd(flutter_exe, build_type, flavor, mode, *, verbose, no_obfuscate) -> list[str]:
    cmd = [flutter_exe, "build", build_type, f"--{mode}", "-t", "lib/main.dart"]
    if flavor:
        cmd.extend(["--flavor", flavor.name])
    if mode == "release" and not no_obfuscate:
        sub = flavor.name if flavor else "default"
        symbols = os.path.join("build", "app", "outputs", "symbols", sub)
        cmd.extend(["--obfuscate", f"--split-debug-info={symbols}"])
    if verbose:
        cmd.append("--verbose")
    return cmd


def _resolve_flavors(cfg, args):
    if not cfg.has_flavors:
        return [None]
    if getattr(args, "flavor", None) is None:
        default = cfg.flavor(cfg.default_flavor) or cfg.flavors[0]
        return [default]
    if "all" in args.flavor:
        return list(cfg.flavors)
    return [cfg.flavor(n) for n in args.flavor]


def _resolve_build_types(args):
    seen: set[str] = set()
    build_types: list[str] = []

    def _add(types):
        for t in types:
            if t not in seen:
                seen.add(t)
                build_types.append(t)

    _add(t for t in ALL_PLATFORMS if getattr(args, t, False))
    for shortcut, expanded in _TYPE_SHORTCUTS.items():
        if getattr(args, shortcut.replace("_", "-"), False) or getattr(args, shortcut, False):
            _add(expanded)
    return build_types or list(ALL_BUILD_TYPES)


def _rename_web_output(project_root, flavor_name, *, dry_run):
    src = _p(project_root, "build", "web")
    dst = _p(project_root, "build", f"web_{flavor_name}")
    if dry_run:
        info(f"[dry-run] would rename: build/web/ -> build/web_{flavor_name}/")
        return
    if not os.path.isdir(src):
        return
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.rename(src, dst)
    ok(f"Renamed: build/web/ -> build/web_{flavor_name}/")


def _build_web(flutter_exe, flavor, *, cfg, project_root, dry_run, verbose, multi_flavor):
    flavor_label = flavor.name if flavor else "default"
    header(f"Web build - {flavor_label}")
    cmd = [flutter_exe, "build", "web", "--release"]
    if flavor:
        cmd.extend([
            f"--dart-define=FLAVOR={flavor.name}",
            f"--base-href={flavor.effective_web_base_href}",
        ])
    cmd.extend(["-O4", "--strip-wasm", "--source-maps"])
    if verbose:
        cmd.append("--verbose")
    ok_ = run_cmd(cmd, cwd=project_root, label=f"flutter build web ({flavor_label})", dry_run=dry_run)
    if ok_ and flavor:
        ok_ = _postbuild_web(flavor, cfg=cfg, dry_run=dry_run, default_flavor=cfg.default_flavor)
        if multi_flavor:
            _rename_web_output(project_root, flavor.name, dry_run=dry_run)
    return ok_


def _copy_ios_plist(project_root, flavor, *, dry_run):
    if not flavor:
        return True
    src = _p(project_root, flavor.ios_google_plist_dir, _GOOGLE_PLIST)
    dst = _p(project_root, "ios", "Runner", _GOOGLE_PLIST)
    return _copy_file(src, dst, f"{_GOOGLE_PLIST} -> ios/Runner/", dry_run=dry_run)


def _build_ios(flutter_exe, flavor, *, project_root, mode, dry_run, verbose):
    flavor_label = flavor.name if flavor else "default"
    header(f"iOS build ({mode}) - {flavor_label}")
    if not _check_macos():
        return None
    if not _copy_ios_plist(project_root, flavor, dry_run=dry_run):
        return False
    cmd = [flutter_exe, "build", "ios", f"--{mode}"]
    if flavor:
        cmd.extend(["--flavor", flavor.name])
    cmd.append("--simulator" if mode == "debug" else "--no-codesign")
    if verbose:
        cmd.append("--verbose")
    return run_cmd(cmd, cwd=project_root, label="flutter build ios", dry_run=dry_run)


def _build_ipa(flutter_exe, flavor, *, project_root, dry_run, verbose, no_obfuscate):
    flavor_label = flavor.name if flavor else "default"
    header(f"iOS IPA (release) - {flavor_label}")
    if not _check_macos():
        return None
    if not _copy_ios_plist(project_root, flavor, dry_run=dry_run):
        return False
    cmd = [flutter_exe, "build", "ipa", "--release", "--export-method", "app-store"]
    if flavor:
        cmd.extend(["--flavor", flavor.name])
    if not no_obfuscate:
        sub = flavor.name if flavor else "default"
        symbols = os.path.join("build", "ios", "symbols", sub)
        cmd.extend(["--obfuscate", f"--split-debug-info={symbols}"])
    if verbose:
        cmd.append("--verbose")
    return run_cmd(cmd, cwd=project_root, label="flutter build ipa", dry_run=dry_run)


def _build_desktop(flutter_exe, dt, flavor, *, mode, project_root, dry_run, verbose, no_obfuscate):
    header(f"{dt} ({mode}) - {flavor.name if flavor else 'default'}")
    if not _check_platform_for_desktop(dt):
        return True
    cmd = [flutter_exe, "build", dt, f"--{mode}", "-t", "lib/main.dart"]
    if flavor:
        cmd.extend(["--flavor", flavor.name])
    if mode == "release" and not no_obfuscate:
        sub = flavor.name if flavor else "default"
        symbols = os.path.join("build", dt, "symbols", sub)
        cmd.extend(["--obfuscate", f"--split-debug-info={symbols}"])
    if verbose:
        cmd.append("--verbose")
    return run_cmd(cmd, cwd=project_root, label=f"flutter build {dt}", dry_run=dry_run)


def _collect_result(result, results):
    """Append a build result. Returns True if a fatal failure occurred."""
    if result is False:
        results.append(False)
        return True
    if result is not None:
        results.append(result)
    return False


def _build_android_types(flutter_exe, flavor, build_types, *, mode, project_root,
                         dry_run, verbose, no_obfuscate, results):
    """Build APK and/or AAB for a single flavor."""
    flavor_label = flavor.name if flavor else "default"
    for kind in ("apk", "aab"):
        if kind not in build_types:
            continue
        header(f"Android {kind.upper()} ({mode}) - {flavor_label}")
        btype = "apk" if kind == "apk" else "appbundle"
        cmd = _android_cmd(flutter_exe, btype, flavor, mode,
                           verbose=verbose, no_obfuscate=no_obfuscate)
        results.append(run_cmd(cmd, cwd=project_root,
                               label=f"flutter build {btype} --{mode}",
                               dry_run=dry_run))


def _build_flavor(flutter_exe, flavor, build_types, *, cfg, project_root, mode,
                  dry_run, verbose, no_obfuscate, multi_flavor, results):
    if "web" in build_types:
        results.append(_build_web(flutter_exe, flavor, cfg=cfg,
            project_root=project_root, dry_run=dry_run, verbose=verbose,
            multi_flavor=multi_flavor))

    _build_android_types(flutter_exe, flavor, build_types, mode=mode,
                         project_root=project_root, dry_run=dry_run,
                         verbose=verbose, no_obfuscate=no_obfuscate,
                         results=results)

    if "ios" in build_types:
        result = _build_ios(flutter_exe, flavor, project_root=project_root,
            mode=mode, dry_run=dry_run, verbose=verbose)
        if _collect_result(result, results):
            return

    if "ipa" in build_types:
        result = _build_ipa(flutter_exe, flavor, project_root=project_root,
            dry_run=dry_run, verbose=verbose, no_obfuscate=no_obfuscate)
        if _collect_result(result, results):
            return

    for dt in ("windows", "macos", "linux"):
        if dt in build_types:
            results.append(_build_desktop(flutter_exe, dt, flavor, mode=mode,
                project_root=project_root, dry_run=dry_run, verbose=verbose,
                no_obfuscate=no_obfuscate))


def _print_build_banner(project_root, flavors, build_types, mode,
                        dry_run, verbose, no_obfuscate):
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  Flutter Build{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    info(f"Project root : {project_root}")
    info(f"Flavor(s)    : {', '.join(f.name if f else '-' for f in flavors)}")
    info(f"Build types  : {', '.join(build_types)}")
    info(f"Mode         : {mode}")
    extras = []
    if dry_run: extras.append("DRY RUN")
    if verbose: extras.append("VERBOSE")
    if no_obfuscate: extras.append("NO OBFUSCATE")
    if extras:
        info(f"Flags        : {', '.join(extras)}")


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk build", description="Flutter build - web, Android, iOS, desktop")
    g = parser.add_argument_group("build types")
    g.add_argument("--web", action="store_true")
    g.add_argument("--apk", action="store_true")
    g.add_argument("--aab", action="store_true")
    g.add_argument("--android", action="store_true")
    g.add_argument("--ios", action="store_true")
    g.add_argument("--ipa", action="store_true")
    g.add_argument("--ios-all", action="store_true")
    g.add_argument("--windows", action="store_true")
    g.add_argument("--macos", action="store_true")
    g.add_argument("--linux", action="store_true")
    g.add_argument("--desktop", action="store_true")
    if cfg.has_flavors:
        parser.add_argument("--flavor", "-f", nargs="+",
            choices=[*cfg.flavor_names, "all"], metavar="FLAVOR",
            help=f"Flavor(s) (default: {cfg.default_flavor}). Choices: {', '.join(cfg.flavor_names)}, all")
    parser.add_argument("--mode", "-m", choices=["debug", "release"], default=cfg.build.default_mode)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-obfuscate", action="store_true", default=cfg.build.no_obfuscate)
    args = parser.parse_args(argv)

    dry_run = args.dry_run
    verbose = args.verbose
    no_obfuscate = args.no_obfuscate
    project_root = cfg.root

    flavors: list[FlavorConfig | None] = _resolve_flavors(cfg, args)
    build_types = _resolve_build_types(args)

    _print_build_banner(project_root, flavors, build_types, args.mode,
                        dry_run, verbose, no_obfuscate)

    flutter_exe = find_flutter()
    if not flutter_exe:
        err("Flutter not found - cannot build.")
        return 1
    ok(f"Flutter found: {flutter_exe}")
    clear_flutter_lock(flutter_exe)

    results: list[bool] = []
    multi_flavor = len(flavors) > 1

    for flavor in flavors:
        if flavor:
            print(f"\n{C.BOLD}{'-' * 60}{C.RESET}")
            print(f"{C.BOLD}  FLAVOR: {flavor.name.upper()}{C.RESET}")
            print(f"{C.BOLD}{'-' * 60}{C.RESET}")

        _build_flavor(flutter_exe, flavor, build_types, cfg=cfg,
                      project_root=project_root, mode=args.mode,
                      dry_run=dry_run, verbose=verbose,
                      no_obfuscate=no_obfuscate, multi_flavor=multi_flavor,
                      results=results)

    header("Summary")
    failed = results.count(False)
    total = len(results)
    if total == 0:
        warn("No builds were executed.")
    elif dry_run:
        ok(f"Dry run complete - {total} build(s) would run.")
    elif failed == 0:
        ok(f"All {total} build(s) completed successfully.")
    else:
        err(f"{failed}/{total} build(s) failed.")
    print()
    return 0 if (dry_run or failed == 0) else 1
