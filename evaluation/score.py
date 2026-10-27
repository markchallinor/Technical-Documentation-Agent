#!/usr/bin/env python3
"""Score an SME-marked sample against the quality bar.

Quality bar (docs/STRATEGY.md section 7.2):
  pilot:   at least 90% of claims correct
  rollout: at least 95% of claims correct
  both:    at least 80% of sampled Unknown items genuine

"partly" counts as not correct. Rows with no verdict are reported and ignored.

Usage:
  score.py SAMPLE.csv [--stage pilot|rollout]
Exit code 0 if the bar is met, 1 if not.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter

THRESHOLDS = {"pilot": 0.90, "rollout": 0.95}
UNKNOWN_THRESHOLD = 0.80
CLAIM_VERDICTS = {"correct", "partly", "incorrect"}
UNKNOWN_VERDICTS = {"genuine", "findable"}


def score(rows: list[dict]) -> dict:
    claims = Counter()
    unknowns = Counter()
    unmarked = invalid = 0
    for row in rows:
        verdict = (row.get("verdict") or "").strip().lower()
        if not verdict:
            unmarked += 1
        elif row.get("type") == "claim" and verdict in CLAIM_VERDICTS:
            claims[verdict] += 1
        elif row.get("type") == "unknown" and verdict in UNKNOWN_VERDICTS:
            unknowns[verdict] += 1
        else:
            invalid += 1
    claim_total = sum(claims.values())
    unknown_total = sum(unknowns.values())
    return {
        "claims": dict(claims),
        "claim_accuracy": claims["correct"] / claim_total if claim_total else None,
        "unknowns": dict(unknowns),
        "unknown_genuine_rate": unknowns["genuine"] / unknown_total if unknown_total else None,
        "unmarked_rows": unmarked,
        "invalid_rows": invalid,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score an SME-marked sample.")
    parser.add_argument("sample")
    parser.add_argument("--stage", choices=THRESHOLDS, default="pilot")
    args = parser.parse_args(argv)

    with open(args.sample, newline="", encoding="utf-8") as fh:
        result = score(list(csv.DictReader(fh)))

    acc, gen = result["claim_accuracy"], result["unknown_genuine_rate"]
    print(f"Claims: {result['claims']}")
    print(f"Claim accuracy: {acc:.1%} (bar for {args.stage}: {THRESHOLDS[args.stage]:.0%})" if acc is not None else "Claim accuracy: no marked claims")
    print(f"Unknown items: {result['unknowns']}")
    print(f"Genuine Unknowns: {gen:.1%} (bar: {UNKNOWN_THRESHOLD:.0%})" if gen is not None else "Genuine Unknowns: no marked Unknown items")
    if result["unmarked_rows"] or result["invalid_rows"]:
        print(f"Ignored: {result['unmarked_rows']} unmarked rows, {result['invalid_rows']} rows with an unrecognised verdict")

    met = acc is not None and acc >= THRESHOLDS[args.stage] and (gen is None or gen >= UNKNOWN_THRESHOLD)
    print("Quality bar MET" if met else "Quality bar NOT met")
    return 0 if met else 1


if __name__ == "__main__":
    sys.exit(main())
