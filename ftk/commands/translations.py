"""Translation validator (13 checks)."""
from __future__ import annotations
import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from ftk.common import C, header, ok, warn, err, info
from ftk.config import ProjectConfig


ANY_DART_RE = re.compile(r"""['"]([^'"]*\.dart)['"]""")


def _parse_imports(file_path: str, lib_dir: str) -> list[str]:
    base = os.path.dirname(file_path)
    imports = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith('//'):
                    continue
                for m in ANY_DART_RE.finditer(line):
                    raw = m.group(1)
                    if raw.startswith("package:"):
                        imports.append(os.path.join(lib_dir, raw.split("/", 1)[-1]))
                    else:
                        imports.append(os.path.normpath(os.path.join(base, raw)))
    except (OSError, UnicodeDecodeError):
        pass
    return imports


def _reachable_files(entry_points: list[str], lib_dir: str) -> set[str]:
    visited: set[str] = set()
    queue = list(entry_points)
    while queue:
        path = queue.pop()
        abs_path = os.path.abspath(path)
        if abs_path in visited or not os.path.isfile(abs_path):
            continue
        visited.add(abs_path)
        for imp in _parse_imports(abs_path, lib_dir):
            queue.append(imp)
    return visited


def _all_keys(translations: dict) -> set[str]:
    r: set[str] = set()
    for lang in translations:
        r |= set(translations[lang].keys())
    return r


def _check_identical(translations: dict) -> int:
    """Check 7: identical translations across languages."""
    lang_list = list(translations.keys())
    pairs = [(lang_list[i], lang_list[j])
             for i in range(len(lang_list)) for j in range(i + 1, len(lang_list))]
    c = 0
    for k in sorted(_all_keys(translations)):
        for l1, l2 in pairs:
            v1, v2 = translations[l1].get(k), translations[l2].get(k)
            if v1 and v2 and v1 == v2:
                preview = v1[:60] + ("..." if len(v1) > 60 else "")
                warn(f"'{k}'  [{l1} == {l2}]  \"{preview}\"")
                c += 1
    return c


def _duplicates_in_language(lang: str, data: dict) -> int:
    v2k: dict = defaultdict(list)
    for k, v in data.items():
        v2k[v].append(k)
    c = 0
    for val, ks in v2k.items():
        if len(ks) > 1:
            preview = val[:50] + ("..." if len(val) > 50 else "")
            warn(f"[{lang}] same value ({len(ks)}x): \"{preview}\"")
            for k in ks:
                info(f"  -> '{k}'")
            c += 1
    return c


def _check_duplicates(translations: dict) -> int:
    """Check 8: duplicate values within the same language."""
    return sum(_duplicates_in_language(lang, data) for lang, data in translations.items())


def _check_placeholders(translations: dict) -> int:
    """Check 10: placeholder consistency across languages."""
    c = 0
    for k in sorted(_all_keys(translations)):
        per_lang = {l: set(re.findall(r"\{(\w+)\}", translations[l].get(k, "")))
                    for l in translations if k in translations[l]}
        if not per_lang:
            continue
        ref = next(iter(per_lang.values()))
        for l, ph in per_lang.items():
            if ph != ref:
                err(f"'{k}' [{l}] placeholder mismatch: expected {sorted(ref)}, got {sorted(ph)}")
                c += 1
    return c


def _report(header_title: str, items: list[str], empty_msg: str, log_fn):
    header(header_title)

    for item in items:
        log_fn(item)

    if not items:
        ok(empty_msg)

    return len(items)


def _check_name_mismatches(dart_keys):
    mis = [f"'{n}' -> '{v}'" for n, v in sorted(dart_keys.items()) if n != v]
    return _report(
        "1 - Dart constant name != JSON key value",
        mis,
        "All constant names match their values.",
        err,
    )


def _check_missing_in_json(translations):
    issues = []
    for k in sorted(_all_keys(translations)):
        missing_langs = [l for l in translations if k not in translations[l]]
        if missing_langs:
            issues.append(f"'{k}' -> missing in: {missing_langs}")

    return _report(
        "2 - Missing keys in some JSON files",
        issues,
        "All keys present in all JSON files.",
        err,
    )


def _check_json_vs_dart(dart_keys, translations):
    dart_vals = set(dart_keys.values())
    all_keys = _all_keys(translations)

    extras = [f"'{k}' -> not in Dart class" for k in sorted(all_keys - dart_vals)]
    missing = [f"'{k}' -> not in any JSON file" for k in sorted(dart_vals - all_keys)]

    total = 0
    total += _report(
        "3 - JSON key not in Dart class",
        extras,
        "All JSON keys are in the Dart class.",
        warn,
    )
    total += _report(
        "4 - Dart class key not in any JSON",
        missing,
        "All Dart keys exist in at least one JSON file.",
        err,
    )

    return total


def _check_usage(dart_keys, reachable_content, unreachable_content):
    truly_unused = [
        f"'{n}' -> never referenced in lib"
        for n in sorted(dart_keys)
        if n not in reachable_content and n not in unreachable_content
    ]

    dead = [
        f"'{n}' -> only used in unreachable dart files"
        for n in sorted(dart_keys)
        if n not in reachable_content and n in unreachable_content
    ]

    total = 0
    total += _report(
        "5 - Unused keys",
        truly_unused,
        "All keys are referenced somewhere in lib.",
        warn,
    )
    total += _report(
        "6 - Keys only used in unreachable dart files",
        dead,
        "No keys found that are exclusively used in unreachable files.",
        warn,
    )

    return total


def _run_key_checks(dart_keys, translations, reachable_content, unreachable_content):
    """Checks 1-6: key consistency and usage."""
    total = 0

    total += _check_name_mismatches(dart_keys)
    total += _check_missing_in_json(translations)
    total += _check_json_vs_dart(dart_keys, translations)
    total += _check_usage(dart_keys, reachable_content, unreachable_content)

    return total


def _report_count(header_title: str, count: int, ok_msg: str):
    header(header_title)
    if count == 0:
        ok(ok_msg)
    return count


def _check_empty_values(translations):
    issues = []

    for lang, data in translations.items():
        for k, v in sorted(data.items()):
            if not v or not v.strip():
                issues.append(f"[{lang}] '{k}' -> empty value")

    header("9 - Empty or whitespace-only values")
    for i in issues:
        err(i)

    if not issues:
        ok("No empty translation values.")

    return len(issues)


def _check_naming(dart_keys):
    bad = [
        f"'{n}' -> not camelCase"
        for n in sorted(dart_keys)
        if not re.match(r"^[a-z][a-zA-Z0-9]*$", n)
    ]

    header("11 - Naming convention (camelCase)")
    for i in bad:
        warn(i)

    if not bad:
        ok("All keys follow camelCase convention.")

    return len(bad)


def _check_whitespace(translations):
    issues = []

    for lang, data in translations.items():
        for k, v in sorted(data.items()):
            if v != v.strip():
                issues.append(f"[{lang}] '{k}' -> whitespace around value")

    header("12 - Leading or trailing whitespace")
    for i in issues:
        warn(i)

    if not issues:
        ok("No leading or trailing whitespace found.")

    return len(issues)


def _run_quality_checks(dart_keys, translations):
    total = 0

    header("7 - Identical translations across languages")
    c = _check_identical(translations)
    if c == 0:
        ok("No identical translations across languages.")
    total += c

    header("8 - Duplicate values within the same language")
    c = _check_duplicates(translations)
    if c == 0:
        ok("No duplicate values within any language.")
    total += c

    header("9 - Empty or whitespace-only values")
    total += _check_empty_values(translations)

    header("10 - Placeholder consistency")
    c = _check_placeholders(translations)
    if c == 0:
        ok("All placeholders are consistent.")
    total += c

    header("11 - Naming convention (camelCase)")
    total += _check_naming(dart_keys)

    header("12 - Leading or trailing whitespace")
    total += _check_whitespace(translations)

    return total


def _check_unreachable_dart(existing, unreachable, lib_dir, root):
    """Check 13: unreachable dart files."""
    header("13 - Unreachable dart files")
    if not existing:
        warn("No entry points found - skipping.")
        return 0
    reachable_from_un = _reachable_files(list(unreachable), lib_dir)
    un = sorted(unreachable - reachable_from_un)
    for f in un:
        warn(f"'{os.path.relpath(f, root)}' -> not reachable from any entry point")
    if not un:
        ok("All dart files are reachable from entry points.")
    return len(un)


def _load_translations(trans_dir, langs):
    translations: dict[str, dict] = {}

    for lang in langs:
        path = os.path.join(trans_dir, f"{lang}.json")
        if not os.path.isfile(path):
            err(f"{path} not found!")
            return None

        with open(path, encoding="utf-8") as f:
            translations[lang] = json.load(f)

    return translations


def _load_dart_keys(keys_file):
    if not os.path.isfile(keys_file):
        err(f"{keys_file} not found!")
        return None

    dart_keys: dict[str, str] = {}
    pattern = re.compile(r"static\s+const\s+(\w+)\s*=\s*'([^']+)'", re.DOTALL)

    with open(keys_file, encoding="utf-8") as f:
        for m in pattern.finditer(f.read()):
            dart_keys[m.group(1)] = m.group(2)

    return dart_keys


def _collect_dart_files(lib_dir):
    return {
        os.path.abspath(os.path.join(r, f))
        for r, _, files in os.walk(lib_dir)
        for f in files if f.endswith(".dart")
    }


def _build_contents(keys_file, entry_points, lib_dir):
    keys_abs = os.path.abspath(keys_file)
    existing = [ep for ep in entry_points if os.path.isfile(ep)]
    all_dart = _collect_dart_files(lib_dir)

    if existing:
        reachable = _reachable_files(existing, lib_dir)
    else:
        warn("No entry points found - falling back to full scan.")
        reachable = all_dart

    unreachable = all_dart - reachable - {keys_abs}

    def read_all(paths):
        out = ""
        for p in paths:
            if p == keys_abs:
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    out += f.read() + "\n"
            except (OSError, UnicodeDecodeError):
                continue
        return out

    return (
        existing,
        unreachable,
        read_all(reachable),
        read_all(unreachable),
    )


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ftk translations", description="Validate translation JSONs")
    parser.add_argument("--lang", nargs="+", help="Only check these languages")
    args = parser.parse_args(argv)

    root = cfg.root
    lib_dir = os.path.join(root, cfg.paths.lib_dir)
    keys_file = os.path.join(root, cfg.paths.keys_file)
    trans_dir = os.path.join(root, cfg.paths.translation_dir)
    langs = args.lang or cfg.languages
    entry_points = [os.path.join(root, ep) for ep in cfg.paths.entry_points]

    print(f"\n{C.BOLD}Flutter Translation Checker{C.RESET}")
    info(f"Lib:          {lib_dir}")
    info(f"Keys file:    {keys_file}")
    info(f"Translations: {trans_dir}")
    info(f"Languages:    {langs}")

    translations = _load_translations(trans_dir, langs)
    if translations is None:
        return 1

    dart_keys = _load_dart_keys(keys_file)
    if dart_keys is None:
        return 1

    existing, unreachable, reachable_content, unreachable_content = _build_contents(
        keys_file, entry_points, lib_dir
    )

    total = 0
    total += _run_key_checks(dart_keys, translations, reachable_content, unreachable_content)
    total += _run_quality_checks(dart_keys, translations)
    total += _check_unreachable_dart(existing, unreachable, lib_dir, root)

    header("SUMMARY")
    if total == 0:
        ok("All checks passed. No issues found.")
    elif total > 5:
        err(f"Total issues found: {total}")
    else:
        warn(f"Total issues found: {total}")

    print()
    return 0
