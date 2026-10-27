#!/usr/bin/env python3
"""Read, check and stamp the agent's section markers in a docs folder.

Generated sections look like this:

    <!-- agent:begin section=data.schema commit=PENDING -->
    ...
    <!-- agent:end -->

The agent always writes commit=PENDING. `stamp` replaces it with the real
source commit and the agent version, so the record is exact and never
typed by the model.

Usage:
  markers.py list    [--docs DIR]
  markers.py check   [--docs DIR]
  markers.py stamp   [--docs DIR] [--repo PATH] [--commit SHA] [--all]
  markers.py commits [--docs DIR]      # distinct source commits, oldest first
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docs_agent_common import agent_version, git  # noqa: E402

BEGIN = re.compile(r"<!--\s*agent:begin\s+([^>]*?)\s*-->")
END = re.compile(r"<!--\s*agent:end\s*-->")
ATTR = re.compile(r"(\w[\w-]*)=(\S+)")
FENCE = re.compile(r"^\s*(```|~~~)")
SECTION_ID = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$")


@dataclass
class Section:
    file: str
    section: str
    commit: str
    agent: str
    begin_line: int
    end_line: int


def parse_file(path: Path, rel: str) -> tuple[list[Section], list[str]]:
    sections: list[Section] = []
    errors: list[str] = []
    open_attrs: dict | None = None
    open_line = 0
    in_fence = False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue  # marker examples inside code blocks are not real markers
        begin = BEGIN.search(line)
        end = END.search(line)
        if begin:
            if open_attrs is not None:
                errors.append(f"{rel}:{n}: agent:begin inside the section opened at line {open_line}")
            open_attrs = dict(ATTR.findall(begin.group(1)))
            open_line = n
            if "section" not in open_attrs:
                errors.append(f"{rel}:{n}: agent:begin has no section=")
            elif not SECTION_ID.match(open_attrs["section"]):
                errors.append(f"{rel}:{n}: section id '{open_attrs['section']}' should look like file.section (lower case)")
        elif end:
            if open_attrs is None:
                errors.append(f"{rel}:{n}: agent:end without a matching agent:begin")
                continue
            sections.append(Section(
                file=rel,
                section=open_attrs.get("section", ""),
                commit=open_attrs.get("commit", ""),
                agent=open_attrs.get("agent", ""),
                begin_line=open_line,
                end_line=n,
            ))
            open_attrs = None
    if open_attrs is not None:
        errors.append(f"{rel}:{open_line}: agent:begin is never closed")
    return sections, errors


def scan(docs: Path) -> tuple[list[Section], list[str]]:
    sections: list[Section] = []
    errors: list[str] = []
    for path in sorted(docs.rglob("*.md")):
        found, errs = parse_file(path, path.relative_to(docs.parent).as_posix())
        sections.extend(found)
        errors.extend(errs)
    seen: dict[str, str] = {}
    for s in sections:
        where = f"{s.file}:{s.begin_line}"
        if s.section in seen:
            errors.append(f"{where}: duplicate section id '{s.section}' (also at {seen[s.section]})")
        else:
            seen[s.section] = where
    return sections, errors


def stamp(docs: Path, commit: str, version: str, restamp_all: bool = False) -> int:
    """Set commit and agent version on every PENDING marker (or every marker with restamp_all)."""
    changed = 0

    def replace(m: re.Match) -> str:
        nonlocal changed
        attrs = dict(ATTR.findall(m.group(1)))
        if not restamp_all and attrs.get("commit", "PENDING") != "PENDING":
            return m.group(0)
        changed += 1
        return f"<!-- agent:begin section={attrs.get('section', '')} commit={commit} agent={version} -->"

    for path in sorted(docs.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        in_fence = False
        for i, line in enumerate(lines):
            if FENCE.match(line):
                in_fence = not in_fence
            elif not in_fence:
                lines[i] = BEGIN.sub(replace, line)
        updated = "".join(lines)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read, check and stamp agent section markers.")
    parser.add_argument("command", choices=["list", "check", "stamp", "commits"])
    parser.add_argument("--docs", default="docs", help="docs folder (default: docs)")
    parser.add_argument("--repo", default=".", help="source repository, used to resolve HEAD for stamp")
    parser.add_argument("--commit", help="commit to stamp (default: HEAD of --repo)")
    parser.add_argument("--all", action="store_true",
                        help="stamp: re-stamp every section, not just PENDING ones (after a refresh has checked them all)")
    parser.add_argument("--json", action="store_true", help="machine-readable output for list")
    args = parser.parse_args(argv)

    docs = Path(args.docs).resolve()
    if not docs.is_dir():
        print(f"No docs folder at {docs}", file=sys.stderr)
        return 2
    sections, errors = scan(docs)

    if args.command == "list":
        if args.json:
            print(json.dumps([asdict(s) for s in sections], indent=2))
        else:
            for s in sections:
                print(f"{s.section:45} {s.commit[:12]:12} {s.agent:8} {s.file}:{s.begin_line}")
        return 0

    if args.command == "check":
        for e in errors:
            print(f"ERROR {e}")
        pending = [s for s in sections if s.commit in ("", "PENDING")]
        for s in pending:
            print(f"WARN  {s.file}:{s.begin_line}: section '{s.section}' not stamped yet (run markers.py stamp)")
        print(f"{len(sections)} sections, {len(errors)} errors, {len(pending)} unstamped")
        return 1 if errors else 0

    if args.command == "stamp":
        if errors:
            for e in errors:
                print(f"ERROR {e}")
            print("Fix marker errors before stamping.")
            return 1
        commit = args.commit or git(Path(args.repo), "rev-parse", "HEAD").strip()
        if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
            print("Could not determine the source commit. Pass --commit or run from inside the repository.", file=sys.stderr)
            return 2
        count = stamp(docs, commit, agent_version(), restamp_all=args.all)
        print(f"Stamped {count} sections with commit {commit[:12]} and agent {agent_version()}")
        return 0

    commits = sorted({s.commit for s in sections if s.commit not in ("", "PENDING")})
    if not commits:
        return 0
    # Order by commit date so the refresh skill can diff from the oldest.
    dated = []
    for c in commits:
        ts = git(Path(args.repo), "show", "-s", "--format=%ct", c).strip()
        dated.append((int(ts) if ts.isdigit() else 0, c))
    for _, c in sorted(dated):
        print(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
