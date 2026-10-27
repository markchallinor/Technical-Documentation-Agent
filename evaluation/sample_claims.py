#!/usr/bin/env python3
"""Draw a random sample of generated claims for an SME to mark.

Writes a CSV with one row per sampled claim (a line inside a generated
section that cites code) and one row per sampled Unknown item. The SME fills
in the `verdict` column, then `score.py` turns it into accuracy figures.

Verdicts:
  claim rows:   correct | partly | incorrect
  unknown rows: genuine  (the code really can't answer it)
                findable (the answer was in the code; the agent missed it)

Usage:
  sample_claims.py [--docs DIR] [--claims 50] [--unknowns 10] [--seed 1] [--out sample.csv]
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_citations import CROSS_REPO, LINE_ANCHOR, LINK, UNKNOWN  # noqa: E402
from markers import scan  # noqa: E402


def has_citation(line: str) -> bool:
    return bool(CROSS_REPO.search(line)) or any(LINE_ANCHOR.match(m.group(1)) for m in LINK.finditer(line))


def collect(docs: Path) -> tuple[list[dict], list[dict]]:
    sections, _ = scan(docs)
    claims, unknowns = [], []
    for s in sections:
        lines = (docs.parent / s.file).read_text(encoding="utf-8").splitlines()
        for n in range(s.begin_line + 1, s.end_line):
            text = lines[n - 1].strip()
            row = {"file": s.file, "line": n, "section": s.section, "text": re.sub(r"\s+", " ", text)[:400]}
            if UNKNOWN.search(text):
                unknowns.append({**row, "type": "unknown"})
            elif has_citation(text):
                claims.append({**row, "type": "claim"})
    return claims, unknowns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample generated claims for SME review.")
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--claims", type=int, default=50)
    parser.add_argument("--unknowns", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1, help="fixed seed so the sample can be reproduced")
    parser.add_argument("--out", default=".docs-agent/sme-sample.csv")
    args = parser.parse_args(argv)

    claims, unknowns = collect(Path(args.docs).resolve())
    rng = random.Random(args.seed)
    rows = rng.sample(claims, min(args.claims, len(claims))) + rng.sample(unknowns, min(args.unknowns, len(unknowns)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "type", "file", "line", "section", "text", "verdict", "notes"])
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            writer.writerow({"id": i, **row, "verdict": "", "notes": ""})
    print(f"Sampled {min(args.claims, len(claims))} of {len(claims)} claims and "
          f"{min(args.unknowns, len(unknowns))} of {len(unknowns)} Unknown items into {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
