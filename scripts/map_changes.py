#!/usr/bin/env python3
"""Work out which documentation sections are affected by code changes.

Uses the repository's docs map (docs/_agent/docs-map.json), which maps file
globs to section ids:

    {"version": 1, "mappings": [
        {"globs": ["migrations/**", "app/models.py"], "sections": ["data.schema", "data.migrations"]}
    ]}

Usage:
  map_changes.py --since COMMIT [--repo PATH] [--map FILE] [--json]
  map_changes.py --files a.py b.py [--map FILE] [--json]

Changed files that match no mapping are listed separately, so the refresh
skill (and the engineer) can decide whether the map needs a new entry.
Documentation files themselves are ignored.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docs_agent_common import git, load_config, path_matches  # noqa: E402


def affected(changed: list[str], mapping: dict, docs_dir: str) -> tuple[dict[str, list[str]], list[str]]:
    sections: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for path in changed:
        if path.startswith(docs_dir.rstrip("/") + "/"):
            continue
        hit = False
        for entry in mapping.get("mappings", []):
            if path_matches(path, entry.get("globs", [])):
                hit = True
                for section in entry.get("sections", []):
                    sections.setdefault(section, []).append(path)
        if not hit:
            unmapped.append(path)
    return dict(sorted(sections.items())), unmapped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map changed files to affected doc sections.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--since", help="commit to diff from (changes since then up to HEAD)")
    group.add_argument("--files", nargs="+", help="explicit list of changed files")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--map", help="docs map file (default: <docs>/_agent/docs-map.json)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    docs_dir = load_config(repo)["docs_dir"]
    map_path = Path(args.map) if args.map else repo / docs_dir / "_agent" / "docs-map.json"
    if not map_path.is_file():
        print(f"No docs map at {map_path}", file=sys.stderr)
        return 2
    mapping = json.loads(map_path.read_text(encoding="utf-8"))

    if args.since:
        out = git(repo, "diff", "--name-only", f"{args.since}..HEAD")
        if not out and git(repo, "rev-parse", "--verify", args.since).strip() == "":
            print(f"Unknown commit: {args.since}", file=sys.stderr)
            return 2
        changed = [p for p in out.splitlines() if p]
    else:
        changed = args.files

    sections, unmapped = affected(changed, mapping, docs_dir)
    if args.json:
        print(json.dumps({"changed_files": len(changed), "sections": sections, "unmapped_files": unmapped}, indent=2))
    else:
        print(f"{len(changed)} changed files, {len(sections)} affected sections, {len(unmapped)} unmapped files")
        for section, files in sections.items():
            print(f"  {section}: {', '.join(files[:5])}{' …' if len(files) > 5 else ''}")
        if unmapped:
            print("Unmapped files (check whether any should update the docs or the map):")
            for p in unmapped[:50]:
                print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
