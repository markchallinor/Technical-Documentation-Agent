#!/usr/bin/env python3
"""Safety check to run before raising a documentation PR.

Fails (exit code 1) if:
  * any file outside the docs folder has been changed, added or deleted
  * the docs contain anything that looks like a secret
  * the docs contain personal data (email addresses, phone numbers,
    National Insurance numbers, card numbers)
  * section markers are malformed or not yet stamped

Warns (does not fail) on IP addresses and internal-looking hostnames, which
a person should look at.

Findings are reported by location and rule only. The matched text is never
printed, so the check itself cannot leak a secret into a terminal or log.

Usage:
  check_output.py [--repo PATH] [--base REF] [--config PATH]

  --base REF   also check files changed in commits since REF (for example
               origin/main), not just uncommitted changes
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docs_agent_common import AGENT_LOCAL_PATHS, git, load_config, read_text  # noqa: E402
from markers import scan  # noqa: E402

SECRET_RULES = [
    ("aws-access-key-id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("url-with-credentials", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s:/@]+@[^\s/]+", re.I)),
    ("assigned-secret", re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)\b"
        r"[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']")),
    ("django-secret-key", re.compile(r"(?i)SECRET_KEY\s*=\s*[\"'][^\"']{20,}[\"']")),
]
PLACEHOLDER = re.compile(r"(?i)(example|changeme|placeholder|your[-_]|<[^>]+>|\*{4,}|x{6,}|dummy|redacted)")

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
NI_NUMBER = re.compile(r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b")
UK_PHONE = re.compile(r"(?<![\w.])(?:\+44\s?\(?0?\)?\s?|0)(?:7\d{3}|1\d{2,4}|2\d)\s?\d{3,4}\s?\d{3,4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
INTERNAL_HOST = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:internal|local|corp|lan|intra|svc\.cluster\.local)\b", re.I)


def luhn(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def changed_paths(repo: Path, base: str | None) -> list[str]:
    paths = set()
    for line in git(repo, "status", "--porcelain=v1", "-uall").splitlines():
        entry = line[3:]
        for p in entry.split(" -> "):
            paths.add(p.strip().strip('"'))
    if base:
        paths.update(p for p in git(repo, "diff", "--name-only", f"{base}...HEAD").splitlines() if p)
    return sorted(paths)


def run_gitleaks(docs: Path) -> int | None:
    """Return the number of gitleaks findings, or None if gitleaks is not installed."""
    exe = shutil.which("gitleaks")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run(
            [exe, "detect", "--no-git", "--source", str(docs), "--redact", "--no-banner",
             "--report-format", "json", "--report-path", str(report), "--exit-code", "0"],
            capture_output=True, text=True,
        )
        if not report.is_file():
            return 0
        try:
            return len(json.loads(report.read_text() or "[]"))
        except json.JSONDecodeError:
            return 0


def scan_text(rel: str, text: str, allowed_domains: set[str]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for n, line in enumerate(text.splitlines(), start=1):
        where = f"{rel}:{n}"
        for rule, pattern in SECRET_RULES:
            for m in pattern.finditer(line):
                if not PLACEHOLDER.search(m.group(0)):
                    errors.append(f"{where}: possible secret ({rule})")
        for m in EMAIL.finditer(line):
            domain = m.group(1).lower()
            if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
                errors.append(f"{where}: email address (personal data or a real mailbox)")
        if NI_NUMBER.search(line):
            errors.append(f"{where}: possible National Insurance number")
        if UK_PHONE.search(line):
            errors.append(f"{where}: possible UK phone number")
        for m in CARD.finditer(line):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and luhn(digits) and len(set(digits)) > 1:
                errors.append(f"{where}: possible payment card number")
        for m in IPV4.finditer(line):
            if not m.group(0).startswith(("0.", "127.")) and m.group(0) != "255.255.255.255":
                warnings.append(f"{where}: IP address – check it is safe to publish")
        if "<!-- guide:" in line:
            warnings.append(f"{where}: template guidance comment left in the page")
        if INTERNAL_HOST.search(line):
            warnings.append(f"{where}: internal-looking hostname – check it is safe to publish")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safety check before raising a documentation PR.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", help="git ref to compare committed changes against, for example origin/main")
    parser.add_argument("--config")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    config = load_config(repo, args.config)
    docs_dir = config["docs_dir"].strip("/")
    docs = repo / docs_dir
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Only the docs folder may change.
    for p in changed_paths(repo, args.base):
        if p.startswith(AGENT_LOCAL_PATHS):
            continue
        if not (p == docs_dir or p.startswith(docs_dir + "/")):
            errors.append(f"{p}: changed outside {docs_dir}/ – the agent may only change documentation")

    if not docs.is_dir():
        errors.append(f"{docs_dir}/ does not exist")
    else:
        # 2. Secrets and personal data in every docs file.
        allowed = {d.lower() for d in config["pii_allowed_email_domains"]}
        for path in sorted(p for p in docs.rglob("*") if p.is_file()):
            text = read_text(path)
            if text is None:
                continue
            e, w = scan_text(path.relative_to(repo).as_posix(), text, allowed)
            errors.extend(e)
            warnings.extend(w)

        scanner = config.get("secret_scanner", "auto")
        if scanner in ("auto", "gitleaks"):
            count = run_gitleaks(docs)
            if count is None and scanner == "gitleaks":
                errors.append("gitleaks is required by config but is not installed")
            elif count:
                errors.append(f"gitleaks reported {count} possible secret(s) in {docs_dir}/ (run gitleaks with --redact to see locations)")
            elif count is None:
                warnings.append("gitleaks not installed – only the built-in secret rules were applied")

        # 3. Markers well formed and stamped.
        sections, marker_errors = scan(docs)
        errors.extend(marker_errors)
        for s in sections:
            if s.commit in ("", "PENDING"):
                errors.append(f"{s.file}:{s.begin_line}: section '{s.section}' not stamped (run markers.py stamp)")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print("PASSED" if not errors else f"FAILED with {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
