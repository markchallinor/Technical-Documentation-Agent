#!/usr/bin/env python3
"""Extract deterministic facts from a repository, with no AI involved.

Reads the repository and its git history and writes a JSON facts file
(default: <repo>/.docs-agent/facts.json). The documentation skills draft
from these facts and cite the file and line numbers recorded here.

Safety properties, for review:
  * Read-only. The only write is the facts file.
  * Never records the value of an environment variable or the contents of
    a sensitive file (.env, keys, credentials): names and paths only.
  * Never records email addresses. Contributor names stay in the local
    facts file, which is excluded from git by install.sh.
  * Standard library only. No network access.

Every detector is best-effort pattern matching. The drafting skill confirms
each fact by reading the cited source before documenting it.

Usage: python3 extract_facts.py [--repo PATH] [--out PATH] [--config PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from docs_agent_common import (  # noqa: E402
    agent_version,
    git,
    iter_repo_files,
    line_number,
    load_config,
    path_matches,
    read_text,
)

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

MAX_ITEMS = 500
MAX_LOCATIONS = 5

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".rb": "Ruby",
    ".erb": "Ruby (ERB templates)", ".java": "Java", ".kt": "Kotlin", ".scala": "Scala",
    ".go": "Go", ".php": "PHP", ".cs": "C#", ".rs": "Rust", ".swift": "Swift",
    ".html": "HTML", ".htm": "HTML", ".njk": "Nunjucks", ".jinja": "Jinja",
    ".jinja2": "Jinja", ".hbs": "Handlebars", ".css": "CSS", ".scss": "SCSS",
    ".sass": "Sass", ".less": "Less", ".vue": "Vue", ".svelte": "Svelte",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell", ".sql": "SQL",
    ".tf": "Terraform", ".hcl": "HCL", ".yml": "YAML", ".yaml": "YAML",
    ".json": "JSON", ".xml": "XML", ".groovy": "Groovy", ".gradle": "Gradle",
}
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".rb", ".java", ".kt",
    ".scala", ".go", ".php", ".cs", ".rs", ".swift", ".vue", ".svelte", ".groovy",
    ".sh", ".bash",
}
CONFIG_EXTENSIONS = {".yml", ".yaml", ".properties", ".ini", ".cfg", ".toml", ".conf", ".json", ".env.example"}

RUNTIME_FILES = {
    ".nvmrc": "Node.js", ".node-version": "Node.js", ".python-version": "Python",
    "runtime.txt": "Python (Heroku/Cloud Foundry style)", ".ruby-version": "Ruby",
    ".java-version": "Java", ".tool-versions": "asdf (multiple)", ".go-version": "Go",
}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
    "Gemfile.lock", "composer.lock", "go.sum", "packages.lock.json", "uv.lock",
    "requirements.lock", "Cargo.lock",
}
SENSITIVE_NAME = re.compile(
    r"(^|/)(\.env(\..+)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|id_rsa.*|id_ed25519.*|"
    r".*credentials.*|.*secrets?\.(ya?ml|json|txt))$",
    re.IGNORECASE,
)
ENV_EXAMPLE_NAME = re.compile(r"(^|/)(\.env\.(example|sample|template|dist)|env\.(example|sample)|example\.env)$", re.I)

ENV_NAME = r"([A-Z][A-Z0-9_]{1,})"
PY, JS, RB, JVM, GO, PHP, CS = {".py"}, {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"}, {".rb"}, {".java", ".kt", ".scala", ".groovy"}, {".go"}, {".php"}, {".cs"}
ENV_PATTERNS = [
    # (source, file extensions, pattern)
    ("python", PY, re.compile(r"os\.environ\.get\(\s*['\"]" + ENV_NAME + r"['\"]")),
    ("python", PY, re.compile(r"os\.environ\[\s*['\"]" + ENV_NAME + r"['\"]\s*\]")),
    ("python", PY, re.compile(r"os\.getenv\(\s*['\"]" + ENV_NAME + r"['\"]")),
    ("env-helper", PY | PHP, re.compile(r"\benv(?:\.(?:str|bool|int|float|list|dict|url|db_url|db|json|path))?\(\s*['\"]" + ENV_NAME + r"['\"]")),
    ("javascript", JS, re.compile(r"process\.env\." + ENV_NAME)),
    ("javascript", JS, re.compile(r"process\.env\[\s*['\"`]" + ENV_NAME + r"['\"`]\s*\]")),
    ("ruby", RB, re.compile(r"ENV\[\s*['\"]" + ENV_NAME + r"['\"]\s*\]")),
    ("ruby", RB, re.compile(r"ENV\.fetch\(\s*['\"]" + ENV_NAME + r"['\"]")),
    ("java", JVM, re.compile(r"System\.getenv\(\s*\"" + ENV_NAME + r"\"")),
    ("go", GO, re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"" + ENV_NAME + r"\"")),
    ("php", PHP, re.compile(r"(?<![\w.])getenv\(\s*['\"]" + ENV_NAME + r"['\"]")),
    ("dotnet", CS, re.compile(r"Environment\.GetEnvironmentVariable\(\s*\"" + ENV_NAME + r"\"")),
    ("shell", {".sh", ".bash"}, re.compile(r"\$\{?" + ENV_NAME + r"\b")),
]
SHELL_ASSIGNED = re.compile(r"^\s*(?:local\s+|export\s+|readonly\s+|declare\s+(?:-\w+\s+)?)?" + ENV_NAME + r"=", re.M)
SHELL_FOR_VAR = re.compile(r"\bfor\s+" + ENV_NAME + r"\s+in\b")
SHELL_BUILTINS = {
    "BASH_SOURCE", "BASH_REMATCH", "BASH_VERSION", "LINENO", "RANDOM", "PWD", "OLDPWD", "IFS",
    "PPID", "UID", "EUID", "SECONDS", "PIPESTATUS", "FUNCNAME", "OPTARG", "OPTIND", "REPLY",
}
ENV_CONFIG_PATTERN = re.compile(r"\$\{" + ENV_NAME + r"(?::?-?[^}]*)?\}")
DOCKER_ENV_PATTERN = re.compile(r"^\s*(?:ENV|ARG)\s+" + ENV_NAME, re.M)
ENV_EXAMPLE_LINE = re.compile(r"^\s*(?:export\s+)?" + ENV_NAME + r"\s*=", re.M)

JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
ROUTE_PATTERNS = [
    # (framework, extensions or None for any, compiled regex, method group, path group)
    ("express-style", JS_EXT, re.compile(r"\b(?:app|router|server|api|route|routes)\.(get|post|put|patch|delete|all|use)\(\s*['\"`]([^'\"`]+)['\"`]"), 1, 2),
    ("flask", {".py"}, re.compile(r"@[\w.]+\.route\(\s*['\"]([^'\"]+)['\"](?:[^)]*methods\s*=\s*[\[(]([^\])]*)[\])])?"), 2, 1),
    ("fastapi", {".py"}, re.compile(r"@[\w.]+\.(get|post|put|patch|delete|api_route)\(\s*['\"]([^'\"]+)['\"]"), 1, 2),
    ("spring", {".java", ".kt"}, re.compile(r"@(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:(?:value|path)\s*=\s*)?\{?\s*\"([^\"]*)\""), 1, 2),
    ("laravel", {".php"}, re.compile(r"Route::(get|post|put|patch|delete|any|match|resource|apiResource)\(\s*['\"]([^'\"]+)['\"]"), 1, 2),
    ("aspnet", {".cs"}, re.compile(r"\[(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete|Route)\(\s*\"([^\"]*)\""), 1, 2),
    ("go-http", {".go"}, re.compile(r"\.(HandleFunc|Handle)\(\s*\"([^\"]+)\""), 1, 2),
    ("go-router", {".go"}, re.compile(r"\.(GET|POST|PUT|PATCH|DELETE)\(\s*\"([^\"]+)\""), 1, 2),
]
DJANGO_URL = re.compile(r"\b(path|re_path|url)\(\s*r?['\"]([^'\"]*)['\"]")
RAILS_ROUTE = re.compile(r"^\s*(get|post|put|patch|delete|match|resources|resource|namespace|scope|root)\b\s*\(?\s*['\":]?([\w/:.\-{}]*)", re.M)

MODEL_PATTERNS = [
    ("django", {".py"}, re.compile(r"^class\s+(\w+)\((?:[\w.]*\.)?(?:models\.Model|Model|Page|AbstractUser|AbstractBaseUser)\b", re.M)),
    ("sqlalchemy", {".py"}, re.compile(r"^class\s+(\w+)\((?:Base|db\.Model|DeclarativeBase|SQLModel)\b", re.M)),
    ("rails", {".rb"}, re.compile(r"^\s*class\s+(\w+)\s*<\s*(?:ApplicationRecord|ActiveRecord::Base)", re.M)),
    ("jpa", {".java", ".kt"}, re.compile(r"@Entity\b[\s\S]{0,300}?\bclass\s+(\w+)")),
    ("laravel", {".php"}, re.compile(r"class\s+(\w+)\s+extends\s+(?:Model|Authenticatable)\b")),
    ("sequelize/typeorm", JS_EXT, re.compile(r"(?:@Entity\([^)]*\)\s*(?:export\s+)?class\s+(\w+)|sequelize\.define\(\s*['\"](\w+)['\"])")),
]
MIGRATION_DIR = re.compile(r"(^|/)(migrations|migrate|alembic/versions|flyway|db/changelog|database/migrations)(/|$)")

INTEGRATION_HINTS = {
    "PostgreSQL": r"\b(psycopg2?|postgres(?:ql)?|pg\.Pool|PG::)\b",
    "MySQL": r"\b(mysqlclient|pymysql|mysql2?)\b",
    "Redis": r"\bredis\b",
    "Celery": r"\bcelery\b",
    "RabbitMQ/AMQP": r"\b(amqp|rabbitmq|pika|kombu)\b",
    "Kafka": r"\bkafka\b",
    "AWS SQS": r"\bsqs\b",
    "AWS SNS": r"\bsns\b",
    "AWS S3": r"\b(s3|boto3\.client\(['\"]s3)\b",
    "Elasticsearch/OpenSearch": r"\b(elasticsearch|opensearch)\b",
    "MongoDB": r"\b(mongodb|pymongo|mongoose)\b",
    "GOV.UK Notify": r"\b(notifications[_-]python[_-]client|notifications-node-client|govuk[_-]?notify|NotificationsAPIClient)\b",
    "Sentry": r"\bsentry\b",
    "Zendesk": r"\bzendesk\b",
    "Salesforce": r"\bsalesforce\b",
    "Google Analytics/Tag Manager": r"\b(googletagmanager|google-analytics|gtag\()",
    "Wagtail CMS": r"\bwagtail\b",
    "Contentful": r"\bcontentful\b",
    "OAuth/OIDC": r"\b(oauth2?|openid|oidc|authlib|passport)\b",
}
URL_LITERAL = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?")
URL_IGNORE = re.compile(r"(^|\.)(example\.(com|org|net)|localhost|w3\.org|schema\.org|xmlns\.com|apache\.org)$")
TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
TEST_FILE = re.compile(
    r"(^|/)(tests?|spec|__tests__|src/test)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(spec|test)\.[jt]sx?$|_spec\.rb$|Tests?\.(java|kt|cs)$"
)


class Facts:
    def __init__(self, repo: Path, config: dict):
        self.repo = repo
        self.config = config
        self.all_files = list(iter_repo_files(repo, config["skip_dirs"]))
        excluded = config["evidence_exclude"]
        self.evidence_files = [f for f in self.all_files if not path_matches(f, excluded)]
        self.doc_files = [f for f in self.all_files if path_matches(f, excluded)]
        self.sensitive = [f for f in self.all_files if SENSITIVE_NAME.search(f) and not ENV_EXAMPLE_NAME.search(f)]
        self._text_cache: dict[str, str | None] = {}

    def text(self, rel: str) -> str | None:
        if rel not in self._text_cache:
            self._text_cache[rel] = None if rel in self.sensitive else read_text(self.repo / rel)
        return self._text_cache[rel]

    def code_files(self):
        for rel in self.evidence_files:
            if Path(rel).suffix in CODE_EXTENSIONS:
                yield rel


def loc(rel: str, line: int) -> str:
    return f"{rel}:{line}"


def capped(items: list, limit: int = MAX_ITEMS) -> dict:
    return {"items": items[:limit], "total": len(items), "truncated": len(items) > limit}


def yaml_child_keys(text: str, parent: str) -> list[tuple[str, int]]:
    """Return (key, line) pairs directly under a top-level YAML key. Indentation-based, best effort."""
    lines = text.splitlines()
    keys: list[tuple[str, int]] = []
    inside = False
    child_indent = None
    for i, raw in enumerate(lines, start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            inside = bool(re.match(rf"^['\"]?{re.escape(parent)}['\"]?\s*:", raw))
            child_indent = None
            continue
        if not inside:
            continue
        if child_indent is None:
            child_indent = indent
        if indent == child_indent:
            m = re.match(r"^\s*['\"]?([^'\":#\s][^'\":#]*?)['\"]?\s*:", raw)
            if m:
                keys.append((m.group(1), i))
    return keys


# ---------------------------------------------------------------- detectors

def detect_git(f: Facts) -> dict:
    head = git(f.repo, "rev-parse", "HEAD").strip()
    if not head:
        return {"available": False}
    log = git(f.repo, "log", "--format=%aI|%an").splitlines()
    dates = [datetime.fromisoformat(l.split("|", 1)[0]) for l in log if "|" in l]
    now = datetime.now(timezone.utc)
    last_12 = [d for d in dates if d >= now - timedelta(days=365)]
    recent_authors = Counter(
        l.split("|", 1)[1] for l in log
        if "|" in l and datetime.fromisoformat(l.split("|", 1)[0]) >= now - timedelta(days=730)
    )
    churn = Counter(
        p for p in git(f.repo, "log", "--since=12.months", "--name-only", "--format=").splitlines() if p.strip()
    )
    return {
        "available": True,
        "head_commit": head,
        "branch": git(f.repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "commit_count": len(dates),
        "first_commit_date": min(dates).date().isoformat() if dates else None,
        "last_commit_date": max(dates).date().isoformat() if dates else None,
        "commits_last_12_months": len(last_12),
        "tag_count": len([t for t in git(f.repo, "tag").splitlines() if t.strip()]),
        "most_changed_files_last_12_months": [{"file": p, "commits": n} for p, n in churn.most_common(20)],
        "recent_contributors_for_sme_finding_only": [
            {"name": n, "commits_last_24_months": c} for n, c in recent_authors.most_common(15)
        ],
        "_note": "Contributor names are for the engineer to find SMEs. Do not publish them in docs.",
    }


def detect_languages(f: Facts) -> list[dict]:
    files: Counter = Counter()
    lines: Counter = Counter()
    for rel in f.evidence_files:
        lang = LANGUAGES.get(Path(rel).suffix.lower())
        if not lang:
            continue
        files[lang] += 1
        text = f.text(rel)
        if text:
            lines[lang] += text.count("\n") + 1
    return [{"language": l, "files": n, "lines": lines[l]} for l, n in files.most_common()]


def detect_runtimes(f: Facts) -> list[dict]:
    out = []
    for rel in f.all_files:
        name = rel.rsplit("/", 1)[-1]
        if name in RUNTIME_FILES and rel not in f.sensitive:
            text = (f.text(rel) or "").strip().splitlines()
            out.append({"runtime": RUNTIME_FILES[name], "file": rel, "value": text[0][:80] if text else ""})
    return out


def parse_package_json(text: str) -> dict:
    data = json.loads(text)
    return {
        "ecosystem": "npm",
        "name": data.get("name"),
        "engines": data.get("engines", {}),
        "scripts": sorted((data.get("scripts") or {}).keys()),
        "dependencies": [{"name": k, "version": v} for k, v in (data.get("dependencies") or {}).items()],
        "dev_dependencies": [{"name": k, "version": v} for k, v in (data.get("devDependencies") or {}).items()],
    }


def parse_requirements(text: str) -> dict:
    deps = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$", line)
        if m:
            deps.append({"name": m.group(1), "version": m.group(3).split(";")[0].strip()})
    return {"ecosystem": "pip", "dependencies": deps}


def parse_pyproject(text: str) -> dict:
    out = {"ecosystem": "python (pyproject)", "dependencies": []}
    if tomllib is None:
        return out
    try:
        data = tomllib.loads(text)
    except Exception:
        return out
    project = data.get("project", {})
    out["name"] = project.get("name")
    out["requires_python"] = project.get("requires-python")
    for dep in project.get("dependencies", []):
        m = re.match(r"^([A-Za-z0-9_.\-]+)(.*)$", dep)
        if m:
            out["dependencies"].append({"name": m.group(1), "version": m.group(2).strip()})
    poetry = data.get("tool", {}).get("poetry", {})
    for k, v in poetry.get("dependencies", {}).items():
        out["dependencies"].append({"name": k, "version": v if isinstance(v, str) else json.dumps(v)})
    return out


def parse_gemfile(text: str) -> dict:
    deps = [
        {"name": m.group(1), "version": m.group(2) or ""}
        for m in re.finditer(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?", text, re.M)
    ]
    ruby = re.search(r"^\s*ruby\s+['\"]([^'\"]+)['\"]", text, re.M)
    return {"ecosystem": "bundler", "ruby": ruby.group(1) if ruby else None, "dependencies": deps}


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_pom(text: str) -> dict:
    deps = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"ecosystem": "maven", "dependencies": []}
    for el in root.iter():
        if _strip_ns(el.tag) == "dependency":
            fields = {_strip_ns(c.tag): (c.text or "").strip() for c in el}
            deps.append({"name": f"{fields.get('groupId', '')}:{fields.get('artifactId', '')}", "version": fields.get("version", "")})
    return {"ecosystem": "maven", "dependencies": deps}


def parse_gradle(text: str) -> dict:
    deps = [
        {"name": m.group(2), "version": "", "configuration": m.group(1)}
        for m in re.finditer(r"\b(implementation|api|compile|runtimeOnly|compileOnly|testImplementation)\s*\(?\s*['\"]([^'\"]+)['\"]", text)
    ]
    return {"ecosystem": "gradle", "dependencies": deps}


def parse_composer(text: str) -> dict:
    data = json.loads(text)
    return {
        "ecosystem": "composer",
        "dependencies": [{"name": k, "version": v} for k, v in (data.get("require") or {}).items()],
        "dev_dependencies": [{"name": k, "version": v} for k, v in (data.get("require-dev") or {}).items()],
    }


def parse_go_mod(text: str) -> dict:
    module = re.search(r"^module\s+(\S+)", text, re.M)
    go = re.search(r"^go\s+(\S+)", text, re.M)
    deps = [{"name": m.group(1), "version": m.group(2)} for m in re.finditer(r"^\s*(?:require\s+)?([\w.\-/]+\.[\w.\-/]+)\s+(v[\w.\-+]+)", text, re.M)]
    return {"ecosystem": "go", "module": module.group(1) if module else None, "go": go.group(1) if go else None, "dependencies": deps}


def parse_csproj(text: str) -> dict:
    deps = [{"name": m.group(1), "version": m.group(2)} for m in re.finditer(r"<PackageReference\s+Include=\"([^\"]+)\"(?:\s+Version=\"([^\"]*)\")?", text)]
    fw = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", text)
    return {"ecosystem": "nuget", "target_framework": fw.group(1) if fw else None, "dependencies": deps}


MANIFEST_PARSERS = [
    (re.compile(r"(^|/)package\.json$"), parse_package_json),
    (re.compile(r"(^|/)requirements[^/]*\.(txt|in)$|(^|/)requirements/[^/]+\.(txt|in)$"), parse_requirements),
    (re.compile(r"(^|/)pyproject\.toml$"), parse_pyproject),
    (re.compile(r"(^|/)Gemfile$"), parse_gemfile),
    (re.compile(r"(^|/)pom\.xml$"), parse_pom),
    (re.compile(r"(^|/)build\.gradle(\.kts)?$"), parse_gradle),
    (re.compile(r"(^|/)composer\.json$"), parse_composer),
    (re.compile(r"(^|/)go\.mod$"), parse_go_mod),
    (re.compile(r"\.csproj$"), parse_csproj),
]
OTHER_MANIFESTS = re.compile(r"(^|/)(Pipfile|setup\.py|setup\.cfg|Cargo\.toml|bower\.json|mix\.exs)$")


def detect_manifests(f: Facts) -> dict:
    manifests, lockfiles, others = [], [], []
    for rel in f.all_files:
        name = rel.rsplit("/", 1)[-1]
        if name in LOCKFILES:
            lockfiles.append(rel)
            continue
        if OTHER_MANIFESTS.search(rel):
            others.append(rel)
            continue
        for pattern, parser in MANIFEST_PARSERS:
            if pattern.search(rel):
                text = f.text(rel)
                if text is None:
                    break
                try:
                    parsed = parser(text)
                except (ValueError, KeyError, TypeError):
                    parsed = {"ecosystem": "unknown", "dependencies": [], "parse_error": True}
                parsed["file"] = rel
                for key in ("dependencies", "dev_dependencies"):
                    if key in parsed:
                        parsed[key] = parsed[key][:300]
                manifests.append(parsed)
                break
    return {"manifests": manifests, "lockfiles": lockfiles, "other_manifest_files": others}


def detect_make_targets(f: Facts) -> list[dict]:
    out = []
    for rel in f.evidence_files:
        if rel.rsplit("/", 1)[-1] in ("Makefile", "makefile", "GNUmakefile") or rel.endswith(".mk"):
            text = f.text(rel) or ""
            for m in re.finditer(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*:(?!=)", text, re.M):
                if m.group(1) != ".PHONY":
                    out.append({"target": m.group(1), "location": loc(rel, line_number(text, m.start()))})
    return out


def detect_ci(f: Facts) -> list[dict]:
    out = []
    for rel in f.all_files:
        text = None
        if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", rel):
            text = f.text(rel) or ""
            name = re.search(r"^name:[ \t]*['\"]?(.+?)['\"]?[ \t]*$", text, re.M)
            on_inline = re.search(r"^['\"]?on['\"]?:[ \t]*(\S.*)$", text, re.M)
            triggers = [on_inline.group(1)] if on_inline else [k for k, _ in yaml_child_keys(text, "on")]
            out.append({
                "system": "GitHub Actions", "file": rel,
                "name": name.group(1) if name else None,
                "triggers": triggers,
                "jobs": [{"job": k, "location": loc(rel, n)} for k, n in yaml_child_keys(text, "jobs")],
            })
        elif rel.rsplit("/", 1)[-1] == "Jenkinsfile":
            text = f.text(rel) or ""
            out.append({"system": "Jenkins", "file": rel, "stages": [
                {"stage": m.group(1), "location": loc(rel, line_number(text, m.start()))}
                for m in re.finditer(r"stage\s*\(\s*['\"]([^'\"]+)['\"]", text)
            ]})
        elif rel == ".gitlab-ci.yml":
            text = f.text(rel) or ""
            reserved = {"stages", "variables", "include", "default", "image", "services", "workflow", "before_script", "after_script", "cache"}
            jobs = [(m.group(1), line_number(text, m.start())) for m in re.finditer(r"^([A-Za-z0-9_\-:. ]+):\s*$", text, re.M)]
            out.append({"system": "GitLab CI", "file": rel, "jobs": [
                {"job": k, "location": loc(rel, n)} for k, n in jobs if k not in reserved and not k.startswith(".")
            ]})
        elif rel == ".circleci/config.yml":
            text = f.text(rel) or ""
            out.append({"system": "CircleCI", "file": rel, "jobs": [{"job": k, "location": loc(rel, n)} for k, n in yaml_child_keys(text, "jobs")]})
        elif re.search(r"(^|/)azure-pipelines[^/]*\.ya?ml$", rel):
            text = f.text(rel) or ""
            out.append({"system": "Azure Pipelines", "file": rel, "stages_and_jobs": [
                {"name": m.group(2), "kind": m.group(1), "location": loc(rel, line_number(text, m.start()))}
                for m in re.finditer(r"-\s*(stage|job|deployment):\s*(\S+)", text)
            ]})
        elif rel in (".travis.yml", "bitbucket-pipelines.yml", "buildspec.yml", "cloudbuild.yaml", "cloudbuild.yml"):
            out.append({"system": rel, "file": rel})
    return out


def detect_containers(f: Facts) -> dict:
    dockerfiles, compose = [], []
    for rel in f.all_files:
        name = rel.rsplit("/", 1)[-1]
        if name.startswith("Dockerfile") or name.endswith(".Dockerfile") or name == "Containerfile":
            text = f.text(rel) or ""
            entry = {"file": rel, "base_images": [], "exposed_ports": [], "commands": []}
            for m in re.finditer(r"^\s*FROM\s+(\S+)", text, re.M | re.I):
                entry["base_images"].append({"image": m.group(1), "location": loc(rel, line_number(text, m.start()))})
            for m in re.finditer(r"^\s*EXPOSE\s+(.+)$", text, re.M | re.I):
                entry["exposed_ports"].append(m.group(1).strip())
            for m in re.finditer(r"^\s*(CMD|ENTRYPOINT)\b", text, re.M | re.I):
                entry["commands"].append(loc(rel, line_number(text, m.start())))
            dockerfiles.append(entry)
        elif re.match(r"^(docker-)?compose[^/]*\.ya?ml$", name):
            text = f.text(rel) or ""
            compose.append({"file": rel, "services": [{"service": k, "location": loc(rel, n)} for k, n in yaml_child_keys(text, "services")]})
    return {"dockerfiles": dockerfiles, "compose_files": compose}


def detect_infrastructure(f: Facts) -> dict:
    terraform, cloudformation, kubernetes, other = [], [], [], []
    for rel in f.all_files:
        name = rel.rsplit("/", 1)[-1]
        suffix = Path(rel).suffix
        if suffix == ".tf":
            text = f.text(rel) or ""
            for m in re.finditer(r"^\s*(resource|module|data|provider)\s+\"([^\"]+)\"(?:\s+\"([^\"]+)\")?", text, re.M):
                terraform.append({"kind": m.group(1), "type": m.group(2), "name": m.group(3), "location": loc(rel, line_number(text, m.start()))})
            if re.search(r"^\s*backend\s+\"", text, re.M):
                terraform.append({"kind": "backend", "location": loc(rel, line_number(text, re.search(r'^\s*backend\s+"', text, re.M).start()))})
        elif suffix in (".yml", ".yaml", ".json") and rel not in f.sensitive:
            text = f.text(rel) or ""
            head = text[:4000]
            if "AWSTemplateFormatVersion" in head or re.search(r"Type:\s*['\"]?AWS::", head):
                for m in re.finditer(r"Type['\"]?\s*:\s*['\"]?(AWS::[\w:]+)", text):
                    cloudformation.append({"type": m.group(1), "location": loc(rel, line_number(text, m.start()))})
            elif re.search(r"^apiVersion:\s*\S+", head, re.M) and re.search(r"^kind:\s*\w+", head, re.M):
                for m in re.finditer(r"^kind:\s*(\w+)", text, re.M):
                    kubernetes.append({"kind": m.group(1), "location": loc(rel, line_number(text, m.start()))})
            elif name in ("manifest.yml", "manifest.yaml") and "applications:" in head:
                other.append({"platform": "Cloud Foundry", "file": rel, "apps": [
                    m.group(1) for m in re.finditer(r"^[ \t]*-[ \t]*name:[ \t]*(\S+)", text, re.M)
                ]})
            elif re.match(r"^copilot/[^/]+/manifest\.ya?ml$", rel):
                kind = re.search(r"^type:[ \t]*['\"]?(.+?)['\"]?[ \t]*$", text, re.M)
                other.append({"platform": "AWS Copilot", "file": rel, "service": rel.split("/")[1], "type": kind.group(1) if kind else None})
            elif name == "Chart.yaml":
                chart = re.search(r"^name:[ \t]*(\S+)", text, re.M)
                other.append({"platform": "Helm chart", "file": rel, "chart": chart.group(1) if chart else None})
            elif name in ("serverless.yml", "serverless.yaml"):
                other.append({"platform": "Serverless Framework", "file": rel, "functions": [k for k, _ in yaml_child_keys(text, "functions")]})
            elif name == "app.json" and '"buildpacks"' in head:
                other.append({"platform": "Heroku-style app.json", "file": rel})
        elif name == "Procfile":
            text = f.text(rel) or ""
            other.append({"platform": "Procfile", "file": rel, "processes": [
                {"process": m.group(1), "location": loc(rel, line_number(text, m.start()))} for m in re.finditer(r"^([\w-]+):", text, re.M)
            ]})
    return {
        "terraform": capped(terraform),
        "cloudformation": capped(cloudformation),
        "kubernetes": capped(kubernetes),
        "other_platforms": other,
    }


def detect_env_vars(f: Facts) -> dict:
    found: dict[str, dict] = defaultdict(lambda: {"occurrences": 0, "locations": [], "sources": set(), "in_example_file": False})

    def add(name: str, rel: str, line: int, source: str):
        entry = found[name]
        entry["occurrences"] += 1
        entry["sources"].add(source)
        if len(entry["locations"]) < MAX_LOCATIONS and loc(rel, line) not in entry["locations"]:
            entry["locations"].append(loc(rel, line))

    for rel in f.all_files:
        if rel in f.sensitive:
            continue
        name = rel.rsplit("/", 1)[-1]
        suffix = Path(rel).suffix
        if ENV_EXAMPLE_NAME.search(rel):
            text = f.text(rel) or ""
            for m in ENV_EXAMPLE_LINE.finditer(text):
                add(m.group(1), rel, line_number(text, m.start()), "example-env-file")
                found[m.group(1)]["in_example_file"] = True
            continue
        if path_matches(rel, f.config["evidence_exclude"]):
            continue
        if suffix in CODE_EXTENSIONS:
            if TEST_FILE.search(rel):
                continue  # test fixtures are not configuration
            text = f.text(rel)
            if not text:
                continue
            local_names = set()
            if suffix in (".sh", ".bash"):
                local_names = SHELL_BUILTINS | set(SHELL_ASSIGNED.findall(text)) | set(SHELL_FOR_VAR.findall(text))
            for source, exts, pattern in ENV_PATTERNS:
                if suffix not in exts:
                    continue
                for m in pattern.finditer(text):
                    if m.group(1) not in local_names:
                        add(m.group(1), rel, line_number(text, m.start()), source)
        elif name.startswith("Dockerfile"):
            text = f.text(rel) or ""
            for m in DOCKER_ENV_PATTERN.finditer(text):
                add(m.group(1), rel, line_number(text, m.start()), "dockerfile")
        elif suffix in CONFIG_EXTENSIONS:
            text = f.text(rel)
            if not text:
                continue
            for m in ENV_CONFIG_PATTERN.finditer(text):
                add(m.group(1), rel, line_number(text, m.start()), "config-interpolation")
    items = [
        {"name": n, "occurrences": e["occurrences"], "sources": sorted(e["sources"]),
         "in_example_file": e["in_example_file"], "locations": e["locations"]}
        for n, e in sorted(found.items())
    ]
    return {**capped(items), "_note": "Names and locations only. Values are never extracted."}


def detect_routes(f: Facts) -> dict:
    routes = []
    for rel in f.code_files():
        if TEST_FILE.search(rel):
            continue
        suffix = Path(rel).suffix
        text = f.text(rel)
        if not text:
            continue
        for framework, exts, pattern, mg, pg in ROUTE_PATTERNS:
            if exts and suffix not in exts:
                continue
            for m in pattern.finditer(text):
                method = ",".join(re.findall(r"[A-Za-z]+", m.group(mg) or "")) or "ANY"
                routes.append({"framework": framework, "method": method.upper(), "path": m.group(pg), "location": loc(rel, line_number(text, m.start()))})
        if suffix == ".py" and (rel.endswith("urls.py") or "/urls/" in rel):
            for m in DJANGO_URL.finditer(text):
                routes.append({"framework": "django", "method": "ANY", "path": m.group(2), "location": loc(rel, line_number(text, m.start()))})
    for rel in f.evidence_files:
        if rel.endswith("config/routes.rb"):
            text = f.text(rel) or ""
            for m in RAILS_ROUTE.finditer(text):
                routes.append({"framework": "rails", "method": m.group(1).upper(), "path": m.group(2), "location": loc(rel, line_number(text, m.start()))})
    return capped(routes)


def detect_data(f: Facts) -> dict:
    migration_dirs: dict[str, list[str]] = defaultdict(list)
    for rel in f.evidence_files:
        if MIGRATION_DIR.search(rel) and not rel.endswith(("__init__.py", ".pyc")):
            migration_dirs[rel.rsplit("/", 1)[0]].append(rel.rsplit("/", 1)[-1])
    migrations = [
        {"directory": d, "count": len(files), "first": sorted(files)[0], "last": sorted(files)[-1]}
        for d, files in sorted(migration_dirs.items())
    ]
    models = []
    for rel in f.code_files():
        suffix = Path(rel).suffix
        text = f.text(rel)
        if not text:
            continue
        for orm, exts, pattern in MODEL_PATTERNS:
            if suffix not in exts:
                continue
            for m in pattern.finditer(text):
                name = next((g for g in m.groups() if g), None)
                if name:
                    models.append({"orm": orm, "model": name, "location": loc(rel, line_number(text, m.start()))})
    sql_files = [rel for rel in f.evidence_files if rel.endswith(".sql")]
    return {"migrations": migrations, "models": capped(models), "sql_files": sql_files[:100]}


def detect_api_specs(f: Facts) -> list[dict]:
    out = []
    for rel in f.all_files:
        if Path(rel).suffix not in (".yml", ".yaml", ".json") or rel in f.sensitive:
            continue
        text = f.text(rel)
        if not text:
            continue
        head = text[:2000]
        m = re.search(r"^\s*['\"]?(openapi|swagger)['\"]?\s*:\s*['\"]?([\d.]+)", head, re.M)
        if m:
            title = re.search(r"['\"]?title['\"]?\s*:\s*['\"]?([^'\"\n,]+)", text)
            out.append({"file": rel, "spec": m.group(1), "version": m.group(2), "title": title.group(1).strip() if title else None})
    return out


def detect_integrations(f: Facts) -> dict:
    hints = {name: {"occurrences": 0, "locations": []} for name in INTEGRATION_HINTS}
    compiled = {name: re.compile(p, re.I) for name, p in INTEGRATION_HINTS.items()}
    domains: dict[str, dict] = defaultdict(lambda: {"occurrences": 0, "locations": []})
    for rel in f.evidence_files:
        suffix = Path(rel).suffix
        if suffix not in CODE_EXTENSIONS and suffix not in CONFIG_EXTENSIONS and not rel.endswith(("requirements.txt", "Gemfile")):
            continue
        if TEST_FILE.search(rel):
            continue
        text = f.text(rel)
        if not text:
            continue
        for name, pattern in compiled.items():
            for m in pattern.finditer(text):
                hints[name]["occurrences"] += 1
                if len(hints[name]["locations"]) < MAX_LOCATIONS:
                    hints[name]["locations"].append(loc(rel, line_number(text, m.start())))
        for m in URL_LITERAL.finditer(text):
            domain = m.group(1).lower()
            if URL_IGNORE.search(domain):
                continue
            domains[domain]["occurrences"] += 1
            if len(domains[domain]["locations"]) < MAX_LOCATIONS:
                domains[domain]["locations"].append(loc(rel, line_number(text, m.start())))
    return {
        "technology_hints": {k: v for k, v in hints.items() if v["occurrences"]},
        "url_domains_in_code": dict(sorted(domains.items(), key=lambda kv: -kv[1]["occurrences"])[:100]),
        "_note": "Keyword and URL matches only. Confirm in code before documenting. Do not publish internal hostnames.",
    }


def detect_tests(f: Facts) -> dict:
    tests = [rel for rel in f.evidence_files if TEST_FILE.search(rel) and Path(rel).suffix in CODE_EXTENSIONS]
    dirs = Counter(rel.split("/", 1)[0] if "/" in rel else "." for rel in tests)
    return {"test_file_count": len(tests), "by_top_level_directory": dict(dirs.most_common()), "sample": tests[:20]}


def detect_todos(f: Facts) -> dict:
    per_file: Counter = Counter()
    kinds: Counter = Counter()
    for rel in f.code_files():
        text = f.text(rel)
        if not text:
            continue
        for m in TODO_PATTERN.finditer(text):
            per_file[rel] += 1
            kinds[m.group(1)] += 1
    return {"total": sum(per_file.values()), "by_kind": dict(kinds), "top_files": [{"file": p, "count": n} for p, n in per_file.most_common(20)]}


def detect_existing_docs(f: Facts) -> dict:
    docs_dir = f.config["docs_dir"].rstrip("/") + "/"
    in_docs = [rel for rel in f.all_files if rel.startswith(docs_dir)]
    non_markdown = [rel for rel in in_docs if Path(rel).suffix.lower() not in (".md", ".markdown", ".rst", ".adoc", ".txt")]
    agent_owned = [rel for rel in in_docs if "<!-- agent:begin" in (f.text(rel) or "")]
    return {
        "_note": "Existing documentation is out of date and must not be used as evidence.",
        "docs_dir": docs_dir,
        "docs_dir_exists": bool(in_docs),
        "files_in_docs_dir": len(in_docs),
        "non_documentation_files_in_docs_dir": non_markdown[:100],
        "files_already_generated_by_agent": agent_owned,
        "other_documentation_files": [rel for rel in f.doc_files if not rel.startswith(docs_dir)][:200],
    }


def suggest_docs_map(facts: dict) -> dict:
    """Heuristic starting point for docs/_agent/docs-map.json. The bootstrap skill refines it."""
    mappings: list[dict] = []

    def add(globs, sections):
        globs = sorted({g for g in globs if g})
        if globs:
            mappings.append({"globs": globs, "sections": sections})

    m = facts["dependencies"]
    add([x["file"] for x in m["manifests"]] + m["lockfiles"] + m["other_manifest_files"],
        ["dependencies.key-libraries", "dependencies.risks", "index.tech-stack"])
    add([r["file"] for r in facts["runtimes"]], ["dependencies.runtimes", "getting-started.prerequisites"])
    add([t["location"].rsplit(":", 1)[0] for t in facts["make_targets"]] +
        [c["file"] for c in facts["containers"]["compose_files"]], ["getting-started.local-setup"])
    add([d + "/**" for d in facts["tests"]["by_top_level_directory"] if d != "."], ["getting-started.tests", "known-issues.test-gaps"])
    add([c["file"] for c in facts["ci"]], ["deployment.pipelines"])
    infra = facts["infrastructure"]
    add([i["location"].rsplit(":", 1)[0] for i in infra["terraform"]["items"]] +
        [i["location"].rsplit(":", 1)[0] for i in infra["cloudformation"]["items"]] +
        [i["location"].rsplit(":", 1)[0] for i in infra["kubernetes"]["items"]] +
        [o["file"] for o in infra["other_platforms"]] +
        [d["file"] for d in facts["containers"]["dockerfiles"]],
        ["deployment.infrastructure", "deployment.environments"])
    add([r["location"].rsplit(":", 1)[0] for r in facts["routes"]["items"]] + [s["file"] for s in facts["api_specs"]],
        ["interfaces.inbound"])
    add([d["directory"] + "/**" for d in facts["data"]["migrations"]] +
        [x["location"].rsplit(":", 1)[0] for x in facts["data"]["models"]["items"]], ["data.schema", "data.migrations"])
    env_files = {l.rsplit(":", 1)[0] for e in facts["environment_variables"]["items"] for l in e["locations"]}
    add(list(env_files), ["configuration.environment-variables"])
    return {"version": 1, "mappings": mappings}


def extract(repo: Path, config: dict) -> dict:
    f = Facts(repo, config)
    facts = {
        "meta": {
            "agent_version": agent_version(),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "repository_directory": repo.name,
            "file_count": len(f.all_files),
            "evidence_file_count": len(f.evidence_files),
        },
        "git": detect_git(f),
        "languages": detect_languages(f),
        "runtimes": detect_runtimes(f),
        "dependencies": detect_manifests(f),
        "make_targets": detect_make_targets(f),
        "ci": detect_ci(f),
        "containers": detect_containers(f),
        "infrastructure": detect_infrastructure(f),
        "environment_variables": detect_env_vars(f),
        "routes": detect_routes(f),
        "data": detect_data(f),
        "api_specs": detect_api_specs(f),
        "integrations": detect_integrations(f),
        "tests": detect_tests(f),
        "todo_markers": detect_todos(f),
        "sensitive_files": {"paths": f.sensitive, "_note": "Contents never read. Mention existence only."},
        "existing_documentation": detect_existing_docs(f),
    }
    facts["suggested_docs_map"] = suggest_docs_map(facts)
    return facts


def summary(facts: dict) -> str:
    g = facts["git"]
    lines = [
        f"Files scanned: {facts['meta']['file_count']} ({facts['meta']['evidence_file_count']} usable as evidence)",
        f"Languages: {', '.join(l['language'] for l in facts['languages'][:6]) or 'none detected'}",
        f"Commits: {g.get('commit_count', 'n/a')} (last {g.get('last_commit_date', 'n/a')})",
        f"Manifests: {len(facts['dependencies']['manifests'])}, CI definitions: {len(facts['ci'])}",
        f"Routes: {facts['routes']['total']}, environment variables: {facts['environment_variables']['total']}",
        f"Migration directories: {len(facts['data']['migrations'])}, models: {facts['data']['models']['total']}",
        f"Sensitive files (names only): {len(facts['sensitive_files']['paths'])}",
    ]
    ed = facts["existing_documentation"]
    if ed["docs_dir_exists"]:
        lines.append(f"WARNING: {ed['docs_dir']} already exists with {ed['files_in_docs_dir']} files. "
                     "Decide how to handle it before drafting (see the bootstrap skill).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="repository to scan (default: current directory)")
    parser.add_argument("--out", help="output file (default: <repo>/.docs-agent/facts.json)")
    parser.add_argument("--config", help="config file (default: <repo>/.docs-agent/config.json if present)")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        parser.error(f"not a directory: {repo}")
    config = load_config(repo, args.config)
    facts = extract(repo, config)
    out = Path(args.out) if args.out else repo / ".docs-agent" / "facts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, default=sorted) + "\n", encoding="utf-8")
    print(summary(facts))
    print(f"Facts written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
