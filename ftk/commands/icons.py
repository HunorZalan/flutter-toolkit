"""Flutter + Web multi-flavor icon generator.

Requires Pillow (install with: pip install 'flutter-toolkit[icons]').
Generates launcher/adaptive/round/notification icons for all configured
flavors across iOS / Android / Web / Windows / macOS / Linux.
"""
from __future__ import annotations
import argparse
import os
from collections import Counter
from dataclasses import dataclass

from ftk.common import header, ok, warn, err, info, missing_dep, init_colours
from ftk.config import ProjectConfig, FlavorConfig


WHITE       = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)
PLATFORMS         = ("ios", "android", "web")
DESKTOP_PLATFORMS = ("windows", "macos", "linux")
ALL_PLATFORMS     = (*PLATFORMS, *DESKTOP_PLATFORMS)

LAUNCHER_LOGO_RATIO       = 0.90
ROUND_LOGO_RATIO          = 0.65
ADAPTIVE_FOREGROUND_RATIO = 0.70


@dataclass(frozen=True)
class IosIconSpec:
    base_size: float
    scale: int
    filename: str

    @property
    def pixel_size(self) -> int:
        return int(self.base_size * self.scale)


@dataclass(frozen=True)
class AndroidDensity:
    folder: str
    px: int


IOS_ICONS: list[IosIconSpec] = [
    IosIconSpec(20,    1, "Icon-App-20x20@1x.png"),
    IosIconSpec(20,    2, "Icon-App-20x20@2x.png"),
    IosIconSpec(20,    3, "Icon-App-20x20@3x.png"),
    IosIconSpec(29,    1, "Icon-App-29x29@1x.png"),
    IosIconSpec(29,    2, "Icon-App-29x29@2x.png"),
    IosIconSpec(29,    3, "Icon-App-29x29@3x.png"),
    IosIconSpec(40,    1, "Icon-App-40x40@1x.png"),
    IosIconSpec(40,    2, "Icon-App-40x40@2x.png"),
    IosIconSpec(40,    3, "Icon-App-40x40@3x.png"),
    IosIconSpec(50,    1, "Icon-App-50x50@1x.png"),
    IosIconSpec(50,    2, "Icon-App-50x50@2x.png"),
    IosIconSpec(57,    1, "Icon-App-57x57@1x.png"),
    IosIconSpec(57,    2, "Icon-App-57x57@2x.png"),
    IosIconSpec(60,    2, "Icon-App-60x60@2x.png"),
    IosIconSpec(60,    3, "Icon-App-60x60@3x.png"),
    IosIconSpec(72,    1, "Icon-App-72x72@1x.png"),
    IosIconSpec(72,    2, "Icon-App-72x72@2x.png"),
    IosIconSpec(76,    1, "Icon-App-76x76@1x.png"),
    IosIconSpec(76,    2, "Icon-App-76x76@2x.png"),
    IosIconSpec(83.5,  2, "Icon-App-83.5x83.5@2x.png"),
    IosIconSpec(1024,  1, "Icon-App-1024x1024@1x.png"),
]
ANDROID_DENSITIES: list[AndroidDensity] = [
    AndroidDensity("mdpi",    48),
    AndroidDensity("hdpi",    72),
    AndroidDensity("xhdpi",   96),
    AndroidDensity("xxhdpi",  144),
    AndroidDensity("xxxhdpi", 192),
]
NOTIFICATION_SIZES: dict[str, int] = {
    "mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96,
}
WEB_STANDARD_SIZES = [
    16, 32, 48, 57, 60, 70, 72, 76, 96, 114, 120, 128,
    144, 150, 152, 167, 180, 192, 256, 310, 384, 512,
]
WEB_MASKABLE_SIZES = [192, 512]
WINDOWS_ICO_SIZES = [16, 32, 48, 256]
MACOS_ICON_SIZES: list[tuple[int, int, str]] = [
    (16,   1, "app_icon_16.png"),
    (16,   2, "app_icon_16@2x.png"),
    (32,   1, "app_icon_32.png"),
    (32,   2, "app_icon_32@2x.png"),
    (128,  1, "app_icon_128.png"),
    (128,  2, "app_icon_128@2x.png"),
    (256,  1, "app_icon_256.png"),
    (256,  2, "app_icon_256@2x.png"),
    (512,  1, "app_icon_512.png"),
    (512,  2, "app_icon_512@2x.png"),
]
LINUX_ICON_SIZES = [16, 32, 48, 64, 128, 256, 512]

_ASSET_XCASSETS = "Assets.xcassets"


def _require_pil():
    try:
        from PIL import Image, ImageDraw  # noqa: F401
        return Image, ImageDraw
    except ImportError:
        missing_dep("Pillow", "icons")
        return None, None


# ---------------------------------------------------------------------------
# Helpers (all take a live PIL module reference — never import at module top)
# ---------------------------------------------------------------------------

def _p(root: str, *parts: str) -> str:
    return os.path.join(root, *parts)


def _load_source(root: str, flavor: FlavorConfig, pil_image):
    primary = _p(root, flavor.source_primary)
    if os.path.exists(primary):
        info(f"Source (primary) : {primary}")
        img = pil_image.open(primary).convert("RGBA")
        info(f"Size             : {img.width}x{img.height}px")
        return img
    fallback = _p(root, flavor.splash_source)
    if not os.path.exists(fallback):
        raise FileNotFoundError(f"Source image not found: {primary} or {fallback}")
    info(f"Source (fallback): {fallback}")
    img = pil_image.open(fallback).convert("RGBA")
    info(f"Size             : {img.width}x{img.height}px")
    return img


def _make_circle_mask(pil_image, pil_draw, size: int):
    mask = pil_image.new("L", (size, size), 0)
    pil_draw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


def _paste_centered(pil_image, canvas, logo, size: int, ratio: float):
    logo = logo.copy()
    logo_size = int(size * ratio)
    logo.thumbnail((logo_size, logo_size), pil_image.Resampling.LANCZOS)
    offset = ((size - logo.width) // 2, (size - logo.height) // 2)
    canvas.paste(logo, offset, logo)
    return canvas


def _make_launcher(pil_image, src, size: int):
    return _paste_centered(pil_image, pil_image.new("RGBA", (size, size), WHITE), src, size, LAUNCHER_LOGO_RATIO)


def _make_round(pil_image, pil_draw, src, size: int):
    canvas = pil_image.new("RGBA", (size, size), TRANSPARENT)
    bg     = pil_image.new("RGBA", (size, size), WHITE)
    canvas.paste(bg, mask=_make_circle_mask(pil_image, pil_draw, size))
    return _paste_centered(pil_image, canvas, src, size, ROUND_LOGO_RATIO)


def _make_adaptive_fg(pil_image, src, size: int):
    return _paste_centered(pil_image, pil_image.new("RGBA", (size, size), TRANSPARENT), src, size, ADAPTIVE_FOREGROUND_RATIO)


def _make_notification(pil_image, src, size: int):
    small = src.copy()
    small.thumbnail((size, size), pil_image.Resampling.LANCZOS)
    _, _, _, a = small.split()
    gray        = small.convert("L")
    gray_bytes  = gray.tobytes()
    alpha_bytes = a.tobytes()
    combined    = bytes(int(g * av / 255) for g, av in zip(gray_bytes, alpha_bytes))
    alpha_mask  = pil_image.frombytes("L", gray.size, combined)
    canvas      = pil_image.new("RGBA", (size, size), TRANSPARENT)
    white_layer = pil_image.new("RGBA", gray.size, WHITE)
    white_layer.putalpha(alpha_mask)
    offset = ((size - white_layer.width) // 2, (size - white_layer.height) // 2)
    canvas.paste(white_layer, offset, white_layer)
    return canvas


def _dominant_color(pil_image, img) -> tuple[int, int, int, int]:
    small  = img.resize((64, 64), pil_image.Resampling.LANCZOS).convert("RGBA")
    pixels = [px for px in small.getdata() if px[3] > 128]
    if not pixels:
        return (1, 117, 194, 255)

    def bucket(v: int) -> int:
        return (v // 32) * 32

    counts = Counter((bucket(r), bucket(g), bucket(b)) for r, g, b, _ in pixels)
    r, g, b = counts.most_common(1)[0][0]
    return (r + 16, g + 16, b + 16, 255)


def _should_write(path: str, only_new: bool) -> bool:
    return not (only_new and os.path.exists(path))


def _save_png(img, path: str, only_new: bool = False) -> None:
    if not _should_write(path, only_new):
        print(f"      ~ {os.path.basename(path):<44} (skip)")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    kb = os.path.getsize(path) / 1024
    print(f"      + {os.path.basename(path):<44} ({kb:6.1f} KB)")


def _write_xml(path: str, content: str, only_new: bool = False) -> None:
    if not _should_write(path, only_new):
        print(f"      ~ {os.path.basename(path):<44} (skip)")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"      + {os.path.basename(path):<44} (XML)")


def _adaptive_xml(fg_ref: str, bg_ref: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        f'    <background android:drawable="{bg_ref}"/>\n'
        f'    <foreground android:drawable="{fg_ref}"/>\n'
        "</adaptive-icon>\n"
    )


def _colors_xml(notif_hex: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        '    <color name="ic_launcher_background">#ffffff</color>\n'
        f'    <color name="notification_color">{notif_hex}</color>\n'
        "</resources>\n"
    )


# ---------------------------------------------------------------------------
# Per-platform generators
# ---------------------------------------------------------------------------

def _gen_ios(root: str, flavor: FlavorConfig, only_new: bool, pil_image, pil_draw) -> None:
    info("[iOS] Generating icons...")
    src = _load_source(root, flavor, pil_image)
    out_dir = _p(root, "ios", "Runner", _ASSET_XCASSETS, f"AppIcon-{flavor.name}.appiconset")
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for spec in IOS_ICONS:
        px   = spec.pixel_size
        dest = os.path.join(out_dir, spec.filename)
        if not _should_write(dest, only_new):
            print(f"      ~ {spec.filename:<44} (skip)")
            continue
        canvas = pil_image.new("RGBA", (px, px), WHITE)
        thumb  = src.copy()
        thumb.thumbnail((px, px), pil_image.Resampling.LANCZOS)
        canvas.paste(thumb, ((px - thumb.width) // 2, (px - thumb.height) // 2), thumb)
        _save_png(canvas, dest)
        written += 1
    info(f"-> {written}/{len(IOS_ICONS)} iOS icons in {out_dir}")


def _gen_android(root: str, flavor: FlavorConfig, only_new: bool, pil_image, pil_draw) -> None:
    info("[Android] Generating icons...")
    src = _load_source(root, flavor, pil_image)
    base_dir = _p(root, "android", "app", "src", flavor.name, "res")
    info("mipmap icons:")
    for density in ANDROID_DENSITIES:
        out = os.path.join(base_dir, f"mipmap-{density.folder}")
        _save_png(_make_launcher(pil_image, src, density.px),       os.path.join(out, "ic_launcher.png"),            only_new)
        _save_png(_make_round(pil_image, pil_draw, src, density.px), os.path.join(out, "ic_launcher_round.png"),      only_new)
        _save_png(_make_adaptive_fg(pil_image, src, density.px),    os.path.join(out, "ic_launcher_foreground.png"), only_new)
    info("drawable notification icons:")
    for density, px in NOTIFICATION_SIZES.items():
        out = os.path.join(base_dir, f"drawable-{density}")
        _save_png(_make_notification(pil_image, src, px), os.path.join(out, "ic_notification.png"), only_new)
    info("XML files:")
    any_dir = os.path.join(base_dir, "mipmap-anydpi-v26")
    xml = _adaptive_xml("@mipmap/ic_launcher_foreground", "@color/ic_launcher_background")
    _write_xml(os.path.join(any_dir, "ic_launcher.xml"),       xml, only_new)
    _write_xml(os.path.join(any_dir, "ic_launcher_round.xml"), xml, only_new)
    _write_xml(os.path.join(base_dir, "values", "colors.xml"),
               _colors_xml(flavor.notification_color), only_new)
    info(f"-> Android icons in {base_dir}")


def _gen_web(root: str, flavor: FlavorConfig, only_new: bool, pil_image, pil_draw) -> None:
    info("[Web] Generating icons...")
    src = _load_source(root, flavor, pil_image)
    out_dir = _p(root, flavor.web_folder)
    os.makedirs(out_dir, exist_ok=True)
    theme_color = _dominant_color(pil_image, src)
    info(f"Theme color: RGB{theme_color[:3]}")
    count = 0
    for size in WEB_STANDARD_SIZES:
        name = f"Icon-{size}.png"
        dest = os.path.join(out_dir, name)
        if not _should_write(dest, only_new):
            print(f"      ~ {name:<44} (skip)")
            continue
        resized = src.resize((size, size), pil_image.Resampling.LANCZOS)
        resized.save(dest, format="PNG", optimize=True)
        kb = os.path.getsize(dest) / 1024
        print(f"      + {name:<44} ({kb:.1f} KB)")
        count += 1
    for size in WEB_MASKABLE_SIZES:
        name = f"Icon-maskable-{size}.png"
        dest = os.path.join(out_dir, name)
        if not _should_write(dest, only_new):
            print(f"      ~ {name:<44} (skip)")
            continue
        inner   = int(size * 0.80)
        pad     = (size - inner) // 2
        resized = src.resize((inner, inner), pil_image.Resampling.LANCZOS)
        canvas  = pil_image.new("RGBA", (size, size), TRANSPARENT)
        canvas.paste(resized, (pad, pad))
        canvas.save(dest, format="PNG", optimize=True)
        kb = os.path.getsize(dest) / 1024
        print(f"      + {name:<44} ({kb:.1f} KB)")
        count += 1
    name = "Icon-310x150.png"
    dest = os.path.join(out_dir, name)
    if _should_write(dest, only_new):
        tile = pil_image.new("RGBA", (310, 150), theme_color)
        logo = src.resize((120, 120), pil_image.Resampling.LANCZOS)
        tile.paste(logo, (95, 15), logo)
        tile.save(dest, format="PNG", optimize=True)
        kb = os.path.getsize(dest) / 1024
        print(f"      + {name:<44} ({kb:.1f} KB)")
        count += 1
    else:
        print(f"      ~ {name:<44} (skip)")
    info(f"-> {count} web icons in {out_dir}")


def _gen_windows(root: str, flavor: FlavorConfig, only_new: bool, pil_image, pil_draw) -> None:
    info("[Windows] Generating .ico...")
    src = _load_source(root, flavor, pil_image)
    dest = _p(root, "windows", "runner", "resources", "app_icon.ico")
    if not _should_write(dest, only_new):
        print("      ~ app_icon.ico (skip)")
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    frames = [src.resize((s, s), pil_image.Resampling.LANCZOS) for s in WINDOWS_ICO_SIZES]
    frames[0].save(dest, format="ICO", sizes=[(s, s) for s in WINDOWS_ICO_SIZES], append_images=frames[1:])
    kb = os.path.getsize(dest) / 1024
    print(f"      + app_icon.ico ({kb:.1f} KB)")
    info(f"-> Windows icon in {dest}")


def _gen_macos(root: str, flavor: FlavorConfig, only_new: bool, pil_image, pil_draw) -> None:
    info("[macOS] Generating icons...")
    src = _load_source(root, flavor, pil_image)
    out_dir = _p(root, "macos", "Runner", _ASSET_XCASSETS, "AppIcon.appiconset")
    os.makedirs(out_dir, exist_ok=True)
    written, seen = 0, set()
    for base_size, scale, fname in MACOS_ICON_SIZES:
        if fname in seen:
            continue
        seen.add(fname)
        px = base_size * scale
        dest = os.path.join(out_dir, fname)
        if not _should_write(dest, only_new):
            print(f"      ~ {fname:<44} (skip)")
            continue
        _save_png(src.resize((px, px), pil_image.Resampling.LANCZOS), dest)
        written += 1
    info(f"-> {written}/{len(seen)} macOS icons in {out_dir}")


def _gen_linux(root: str, flavor: FlavorConfig, only_new: bool, pil_image, pil_draw) -> None:
    info("[Linux] Generating icons...")
    src = _load_source(root, flavor, pil_image)
    base_dir = _p(root, "linux", "icons")
    os.makedirs(base_dir, exist_ok=True)
    count = 0
    for size in LINUX_ICON_SIZES:
        name = f"app_icon_{size}.png"
        dest = os.path.join(base_dir, name)
        if not _should_write(dest, only_new):
            print(f"      ~ {name:<44} (skip)")
            continue
        _save_png(src.resize((size, size), pil_image.Resampling.LANCZOS), dest)
        count += 1
    info(f"-> {count}/{len(LINUX_ICON_SIZES)} Linux icons in {base_dir}")


_GENERATORS = {
    "ios":     _gen_ios,
    "android": _gen_android,
    "web":     _gen_web,
    "windows": _gen_windows,
    "macos":   _gen_macos,
    "linux":   _gen_linux,
}


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------

def _check(path: str, label: str) -> bool:
    exists = os.path.exists(path)
    print(f"    [{'OK' if exists else 'FAIL'}] {label}")
    return exists


def _verify_ios(root: str, flavor: FlavorConfig) -> bool:
    d = _p(root, "ios", "Runner", _ASSET_XCASSETS, f"AppIcon-{flavor.name}.appiconset")
    expected = {s.filename for s in IOS_ICONS}
    found = {f for f in os.listdir(d) if f.endswith(".png")} if os.path.isdir(d) else set()
    missing = expected - found
    print(f"    [{'OK' if not missing else 'FAIL'}] iOS: {len(found)}/{len(expected)} PNG files")
    for f in sorted(missing):
        print(f"         Missing: {f}")
    return not missing


def _verify_android(root: str, flavor: FlavorConfig) -> bool:
    base = _p(root, "android", "app", "src", flavor.name, "res")
    paths = [
        (os.path.join(base, "mipmap-xxxhdpi",    "ic_launcher.png"),            "mipmap-xxxhdpi/ic_launcher.png"),
        (os.path.join(base, "mipmap-xxxhdpi",    "ic_launcher_round.png"),      "mipmap-xxxhdpi/ic_launcher_round.png"),
        (os.path.join(base, "mipmap-xxxhdpi",    "ic_launcher_foreground.png"), "mipmap-xxxhdpi/ic_launcher_foreground.png"),
        (os.path.join(base, "mipmap-anydpi-v26", "ic_launcher.xml"),            "mipmap-anydpi-v26/ic_launcher.xml"),
        (os.path.join(base, "mipmap-anydpi-v26", "ic_launcher_round.xml"),      "mipmap-anydpi-v26/ic_launcher_round.xml"),
        (os.path.join(base, "values",            "colors.xml"),                 "values/colors.xml"),
        (os.path.join(base, "drawable-xxxhdpi",  "ic_notification.png"),        "drawable-xxxhdpi/ic_notification.png"),
    ]
    return all(_check(p, l) for p, l in paths)


def _verify_web(root: str, flavor: FlavorConfig) -> bool:
    out = _p(root, flavor.web_folder)
    expected = (
        {f"Icon-{s}.png" for s in WEB_STANDARD_SIZES}
        | {f"Icon-maskable-{s}.png" for s in WEB_MASKABLE_SIZES}
        | {"Icon-310x150.png"}
    )
    found = {f for f in os.listdir(out) if f.endswith(".png")} if os.path.isdir(out) else set()
    missing = expected - found
    print(f"    [{'OK' if not missing else 'FAIL'}] Web: {len(found)}/{len(expected)} PNG files")
    for f in sorted(missing):
        print(f"         Missing: {f}")
    return not missing


def _verify_windows(root: str, flavor: FlavorConfig) -> bool:
    return _check(_p(root, "windows", "runner", "resources", "app_icon.ico"), "Windows: app_icon.ico")


def _verify_macos(root: str, flavor: FlavorConfig) -> bool:
    out = _p(root, "macos", "Runner", _ASSET_XCASSETS, "AppIcon.appiconset")
    expected = {fn for _, _, fn in MACOS_ICON_SIZES}
    found = {f for f in os.listdir(out) if f.endswith(".png")} if os.path.isdir(out) else set()
    missing = expected - found
    print(f"    [{'OK' if not missing else 'FAIL'}] macOS: {len(found)}/{len(expected)} PNG files")
    return not missing


def _verify_linux(root: str, flavor: FlavorConfig) -> bool:
    base = _p(root, "linux", "icons")
    expected = {f"app_icon_{s}.png" for s in LINUX_ICON_SIZES}
    found = {f for f in os.listdir(base) if f.endswith(".png")} if os.path.isdir(base) else set()
    missing = expected - found
    print(f"    [{'OK' if not missing else 'FAIL'}] Linux: {len(found)}/{len(expected)} PNG files")
    return not missing


_VERIFIERS = {
    "ios": _verify_ios, "android": _verify_android, "web": _verify_web,
    "windows": _verify_windows, "macos": _verify_macos, "linux": _verify_linux,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _generate_icons(root, flavors, platforms, only_new, pil_image, pil_draw):
    for flavor in flavors:
        header(f"FLAVOR: {flavor.name.upper()}")
        try:
            for plat in platforms:
                gen = _GENERATORS.get(plat)
                if gen:
                    gen(root, flavor, only_new, pil_image, pil_draw)
        except FileNotFoundError as exc:
            err(str(exc))


def _verify_icons(root, flavors, platforms) -> bool:
    all_ok = True
    for flavor in flavors:
        info(f"Flavor: {flavor.name}")
        for plat in platforms:
            verifier = _VERIFIERS.get(plat)
            if verifier and not verifier(root, flavor):
                all_ok = False
    return all_ok


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    init_colours()
    if not cfg.has_flavors:
        err("ftk icons requires `flavors:` to be defined in ftk.yaml.")
        info("Each flavor's source image is resolved via `tool/icons/<DisplayName>.png`.")
        return 1

    parser = argparse.ArgumentParser(prog="ftk icons", description="Generate app icons for all flavors.")
    parser.add_argument("--flavor", "-f", nargs="+",
                        choices=[*cfg.flavor_names, "all"], metavar="FLAVOR",
                        help=f"Flavors to generate (default: all). Choices: {', '.join(cfg.flavor_names)}, all")
    parser.add_argument("--platform", "-p", nargs="+", choices=list(ALL_PLATFORMS),
                        help=f"Platforms (default: {', '.join(PLATFORMS)})")
    parser.add_argument("--new", "-n", action="store_true",
                        help="Skip icons that already exist.")
    args = parser.parse_args(argv)

    pil_image, pil_draw = _require_pil()
    if pil_image is None:
        return 1

    if not args.flavor or "all" in args.flavor:
        selected_flavors = list(cfg.flavors)
    else:
        selected_flavors = [cfg.flavor(n) for n in args.flavor if cfg.flavor(n)]
    selected_platforms = args.platform or list(PLATFORMS)

    header("Flutter Icon Generator")
    info(f"Project root : {cfg.root}")
    info(f"Flavors      : {', '.join(f.name for f in selected_flavors)}")
    info(f"Platforms    : {', '.join(selected_platforms)}")
    info(f"Mode         : {'only-new (skip existing)' if args.new else 'overwrite'}")

    _generate_icons(cfg.root, selected_flavors, selected_platforms, args.new, pil_image, pil_draw)

    header("Verification")
    all_ok = _verify_icons(cfg.root, selected_flavors, selected_platforms)

    print()
    if all_ok:
        ok("All icons generated successfully.")
        return 0
    warn("Some icons are missing - see output above.")
    return 1
