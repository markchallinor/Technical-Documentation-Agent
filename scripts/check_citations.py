#!/usr/bin/env python3
"""Check that every code citation in the docs points at a real file and line.

This is the deterministic half of verification: it proves each citation
exists. The docs-verify skill then reads each cited line to check the claim
says what the code does.

Citation forms recognised:
  [app/models.py:42](../app/models.py#L42)       relative link, single line
  [app/models.py:42-50](../app/models.py#L42-L50) relative link, line range
  `repo-name:path/to/file.py:42`                 cross-repo (central docs)

Also reports, per generated section: citation count, Unknown and Inferred
items, and sections with no citations at all.

Usage:
  check_citations.py [--docs DIR] [--workspace DIR] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from markers import scan  # noqa: E402

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
LINE_ANCHOR = re.compile(r"^(.*?)#L(\d+)(?:-L?(\d+))?$")
CROSS_REPO = re.compile(r"`([A-Za-z0-9_.\-]+):([^`:\s]+):(\d+)(?:-(\d+))?`")
UNKNOWN = re.compile(r"\*\*Unknown – needs SME input")
INFERRED = re.compile(r"\*\*Inferred – needs confirmation")


def count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def check_target(target: Path, start: int, end: int | None, root: Path) -> str | None:
    try:
        target.relative_to(root)
    except ValueError:
        return "points outside the repository"
    if not target.is_file():
        return "file does not exist"
    total = count_lines(target)
    last = end or start
    if start < 1 or last > total or last < start:
        return f"line {start}{'-' + str(end) if end else ''} is outside the file ({total} lines)"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check code citations in generated docs.")
    parser.add_argument("--docs", default="docs", help="docs folder (default: docs)")
    parser.add_argument("--workspace", help="folder holding all repos side by side, for cross-repo citations")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    docs = Path(args.docs).resolve()
    repo_root = docs.parent
    workspace = Path(args.workspace).resolve() if args.workspace else None
    if not docs.is_dir():
        print(f"No docs folder at {docs}", file=sys.stderr)
        return 2

    broken: list[dict] = []
    per_section: dict[str, dict] = {}
    sections, _ = scan(docs)
    by_file: dict[str, list] = {}
    for s in sections:
        by_file.setdefault(s.file, []).append(s)
        per_section[s.section] = {"file": s.file, "citations": 0, "unknown": 0, "inferred": 0}

    totals = {"citations": 0, "unknown": 0, "inferred": 0}
    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(repo_root).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            section = next((s.section for s in by_file.get(rel, []) if s.begin_line <= n <= s.end_line), None)
            found = 0
            for m in LINK.finditer(line):
                href = m.group(1)
                if href.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                anchor = LINE_ANCHOR.match(href)
                if not anchor:
                    continue  # a link to another doc page, not a code citation
                target = (path.parent / unquote(anchor.group(1))).resolve()
                start, end = int(anchor.group(2)), int(anchor.group(3)) if anchor.group(3) else None
                found += 1
                problem = check_target(target, start, end, repo_root)
                if problem:
                    broken.append({"location": f"{rel}:{n}", "citation": href, "problem": problem})
            for m in CROSS_REPO.finditer(line):
                found += 1
                if workspace is None:
                    continue
                repo_dir = workspace / m.group(1)
                start, end = int(m.group(3)), int(m.group(4)) if m.group(4) else None
                problem = check_target((repo_dir / m.group(2)).resolve(), start, end, repo_dir.resolve())
                if problem:
                    broken.append({"location": f"{rel}:{n}", "citation": m.group(0), "problem": problem})
            unknown = len(UNKNOWN.findall(line))
            inferred = len(INFERRED.findall(line))
            totals["citations"] += found
            totals["unknown"] += unknown
            totals["inferred"] += inferred
            if section:
                per_section[section]["citations"] += found
                per_section[section]["unknown"] += unknown
                per_section[section]["inferred"] += inferred

    uncited = [k for k, v in per_section.items() if v["citations"] == 0 and v["unknown"] == 0]
    result = {"totals": totals, "broken_citations": broken, "sections_without_citations": uncited, "sections": per_section}

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for b in broken:
            print(f"ERROR {b['location']}: {b['citation']} – {b['problem']}")
        for s in uncited:
            print(f"WARN  section '{s}' has no citations and no Unknown items")
        if totals["citations"] and workspace is None and any(CROSS_REPO.search(p.read_text(encoding="utf-8")) for p in docs.rglob("*.md")):
            print("NOTE  cross-repo citations were counted but not checked (pass --workspace)")
        print(f"{totals['citations']} citations, {len(broken)} broken, "
              f"{totals['unknown']} Unknown, {totals['inferred']} Inferred, {len(uncited)} uncited sections")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
