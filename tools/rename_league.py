#!/usr/bin/env python3
"""Rename the league everywhere: display name, short name, file prefixes, repository.

The league's current identity: "Pitch Slapped Baseball League", short name
"PSBL", file prefix "psbl", repository "psbl-assets". Secrets, workflow
files and Python packages use generic names (LEAGUE_*, league-*, core,
league_bot), so they never change.

Usage (dry run first, then --write):

    python3 tools/rename_league.py --name "Fenway Dynasty League" --short FDL --dry-run
    python3 tools/rename_league.py --name "Fenway Dynasty League" --short FDL --write

Options:
    --prefix   file prefix for images and emoji (default: the short name in lower case)
    --repo     new repository name (default: <prefix>-assets)

After --write, rebuild everything that is generated from the identity:

    python3 tools/build_brand_package.py
    python3 tools/build_discord_assets.py
    python3 tools/build_constitution.py --pdf
    python3 tools/build_channel_intros.py
    python3 tools/build_news_templates.py
    python3 tools/normalize_discohook_templates.py
    python3 tools/build_send_console.py

and rename the GitHub repository (Settings > General) to the new --repo name.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_NAME = "Pitch Slapped Baseball League"
OLD_SHORT = "PSBL"
OLD_PREFIX = "psbl"
OLD_REPO = "psbl-assets"
SKIP_DIRS = {".git", "__pycache__", "site", "archive", "build"}
TEXT_EXT = {".py", ".md", ".yml", ".yaml", ".json", ".txt", ".html", ".css", ".js", ".jsx",
            ".jsxinc", ".toml", ".sh", ".svg", ".otio", ".csv", ".xml", ""}


def replacements(name: str, short: str, prefix: str, repo: str) -> list[tuple[re.Pattern, str]]:
    return [
        (re.compile(re.escape(OLD_REPO)), repo),
        (re.compile(re.escape(OLD_NAME.upper())), name.upper()),
        (re.compile(re.escape(OLD_NAME)), name),
        (re.compile(r"(?<![A-Za-z])" + OLD_SHORT + r"(?![A-Za-z])"), short),
        (re.compile(r"(?<![A-Za-z0-9])" + OLD_PREFIX + r"(?=[-_])"), prefix),
    ]


def rename_path_part(part: str, prefix: str, short: str) -> str:
    part = re.sub(r"^" + OLD_PREFIX + r"(?=[-_])", prefix, part)
    return re.sub(r"^" + OLD_SHORT + r"(?=_)", short, part)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--short", required=True)
    ap.add_argument("--prefix")
    ap.add_argument("--repo")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Z0-9]{2,6}", a.short):
        sys.exit("--short must be 2 to 6 capital letters or digits, e.g. FDL")
    prefix = a.prefix or a.short.lower()
    repo = a.repo or f"{prefix}-assets"
    reps = replacements(a.name, a.short, prefix, repo)

    text_changes = 0
    files_changed = 0
    moves: list[tuple[Path, Path]] = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            path = Path(root) / f
            if path.suffix.lower() in TEXT_EXT:
                try:
                    old = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    old = None
                if old is not None:
                    new = old
                    for pat, rep in reps:
                        new, n = pat.subn(rep, new)
                        text_changes += n
                    if new != old:
                        files_changed += 1
                        if a.write:
                            path.write_text(new, encoding="utf-8")
            new_name = rename_path_part(f, prefix, a.short)
            if new_name != f:
                moves.append((path, path.with_name(new_name)))
    for src, dst in moves:
        if a.write:
            src.rename(dst)
    verb = "Changed" if a.write else "Would change"
    print(f"{verb} {text_changes} mentions in {files_changed} files and rename {len(moves)} files.")
    if not a.write:
        for src, dst in moves[:15]:
            print(f"  {src.relative_to(ROOT)} -> {dst.name}")
        if len(moves) > 15:
            print(f"  ... and {len(moves) - 15} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
