"""Shared helpers for the documentation agent scripts.

Standard library only, so the scripts run on any machine with Python 3.9+
and nothing needs installing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Iterable, Iterator

AGENT_HOME = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = {
    "docs_dir": "docs",
    "expected_repositories": None,
    "style_guide": None,
    "evidence_exclude": [
        "docs/**",
        "wiki/**",
        "**/*.md",
        "**/*.rst",
        "**/*.adoc",
        "**/README*",
        "**/CHANGELOG*",
        "**/HISTORY*",
    ],
    "skip_dirs": [
        ".git", "node_modules", "vendor", "bower_components", "dist", "build",
        "target", "out", ".venv", "venv", "env", "__pycache__", ".tox",
        ".mypy_cache", ".pytest_cache", ".next", ".nuxt", "coverage",
        ".docs-agent", ".idea", ".vscode",
    ],
    "pii_allowed_email_domains": ["example.com", "example.org", "example.net"],
    "secret_scanner": "auto",
}

# Paths the agent's own tooling creates in a target repo. They are excluded
# from git by install.sh and ignored by the output check.
AGENT_LOCAL_PATHS = (".docs-agent/", ".claude/settings.local.json")


def agent_version() -> str:
    return (AGENT_HOME / "VERSION").read_text(encoding="utf-8").strip()


def load_config(repo: Path, config_path: str | None = None) -> dict:
    """Built-in defaults, overridden by <repo>/.docs-agent/config.json or --config."""
    config = dict(DEFAULT_CONFIG)
    path = Path(config_path) if config_path else repo / ".docs-agent" / "config.json"
    if path.is_file():
        overrides = json.loads(path.read_text(encoding="utf-8"))
        config.update({k: v for k, v in overrides.items() if not k.startswith("_")})
    return config


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a glob with `**` support into a regex over '/'-separated paths."""
    out = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**/", i):
                out += "(?:.*/)?"
                i += 3
                continue
            if pattern.startswith("**", i):
                out += ".*"
                i += 2
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    """True if `path` matches any pattern. Patterns without '/' also match the basename."""
    base = path.rsplit("/", 1)[-1]
    for pattern in patterns:
        regex = glob_to_regex(pattern)
        if regex.match(path) or ("/" not in pattern and regex.match(base)):
            return True
    return False


def iter_repo_files(repo: Path, skip_dirs: Iterable[str]) -> Iterator[str]:
    """Yield repo-relative POSIX paths of all files, skipping vendored and tool directories."""
    skip = set(skip_dirs)
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        rel_root = Path(root).relative_to(repo).as_posix()
        for name in sorted(files):
            yield name if rel_root == "." else f"{rel_root}/{name}"


def read_text(path: Path, limit_bytes: int = 2_000_000) -> str | None:
    """Read a text file, returning None for binary or very large files."""
    try:
        if path.stat().st_size > limit_bytes:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def git(repo: Path, *args: str) -> str:
    """Run a read-only git command in `repo` and return stdout ('' on failure)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
