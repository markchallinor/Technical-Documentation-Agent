"""Fail if organisation-identifying terms appear anywhere in this public repository.

The terms themselves are never stored in the repository, so the guard
doesn't publish what it protects. They come from either:

  * the BLOCKED_TERMS environment variable (in CI, from a repository secret
    of the same name), with one term per line or comma-separated, or
  * a local, git-ignored `.blocked-terms` file at the repository root, one term
    per line.

Terms match whole words and are case-insensitive. Prefix a term with `case:`
to match case-sensitively (for example `case:SOMEWORD`). Lines starting with
`#` are comments.

The check covers every tracked and untracked (non-ignored) file, plus
commit messages. Failures report the location and the term's number in the
list, never the term itself.

If no terms are configured, the test is skipped.
"""

from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_FILE = ROOT / ".blocked-terms"


def load_terms() -> list[str]:
    raw = os.environ.get("BLOCKED_TERMS", "")
    if TERMS_FILE.is_file():
        raw += "\n" + TERMS_FILE.read_text(encoding="utf-8")
    terms = []
    for line in re.split(r"[\n,]", raw):
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def compile_term(term: str) -> re.Pattern:
    flags = 0
    if term.startswith("case:"):
        term = term[len("case:"):]
    else:
        flags = re.IGNORECASE
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", flags)


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def repo_files() -> list[Path]:
    listed = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    if listed:
        return [ROOT / p for p in listed if (ROOT / p).is_file()]
    return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


class NoIdentifyingTermsTest(unittest.TestCase):
    def test_no_identifying_terms(self):
        terms = load_terms()
        if not terms:
            self.skipTest("No blocked terms configured (set BLOCKED_TERMS or create .blocked-terms)")
        patterns = [compile_term(t) for t in terms]
        hits = []
        for path in repo_files():
            if path == TERMS_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = path.relative_to(ROOT).as_posix()
            for n, line in enumerate(text.splitlines(), start=1):
                for i, pattern in enumerate(patterns, start=1):
                    if pattern.search(line):
                        hits.append(f"{rel}:{n} matches blocked term #{i}")
        for n, line in enumerate(git("log", "--format=%B").splitlines(), start=1):
            for i, pattern in enumerate(patterns, start=1):
                if pattern.search(line):
                    hits.append(f"commit messages, line {n}, matches blocked term #{i}")
        self.assertEqual(hits, [], "Identifying terms found:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
