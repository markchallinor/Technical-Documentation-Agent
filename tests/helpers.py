"""Test helpers: build throwaway git repositories from a dict of files."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("scripts", "extractors", "evaluation"):
    sys.path.insert(0, str(ROOT / sub))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def make_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "tester@example.com")
    git(root, "config", "user.name", "Tester")
    git(root, "config", "commit.gpgsign", "false")
    write_files(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")
    return root


class RepoTestCase(unittest.TestCase):
    """Gives each test a fresh temporary directory at self.tmp."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
