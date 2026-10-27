# Technical Documentation Agent

An AI documentation agent that documents a software service from its code, whether the service is one repository or many. It runs with Claude Code (or GitHub Copilot) wherever an engineer already works on the code, reads a repository's code, and writes evidence-backed Markdown into that repository's `docs/` folder. The engineer raises a PR for the repository's owners to review.

It can be used on any codebase. This repository contains the agent only: never code, names or output from the services it is used on.

## How it works

1. **Deterministic scripts** extract facts from the code, configuration, CI, infrastructure and git history. No AI is involved, and no secret values are recorded.
2. **Claude Code**, following [`RULES.md`](RULES.md) and a skill, drafts each documentation page from the facts and the code. Every claim cites the file and line it came from, and gaps are marked `Unknown – needs SME input` rather than guessed.
3. **A separate verification session** checks every claim against the code.
4. **Safety checks** confirm that only `docs/` changed and that no secrets or personal data are in the output.
5. **The engineer** raises the PR, and the repository's owners review it.

Automatic updates on every pull request will come later, as a separate agent with its own review (see [the strategy](docs/STRATEGY.md), section 10).

## Skills

| Skill | Use it to |
|---|---|
| `docs-bootstrap` | Create a repository's baseline documentation |
| `docs-verify` | Check generated docs against the code and produce the PR report |
| `docs-refresh` | Update docs for code changes since they were generated |
| `docs-synthesise-landscape` | Build central, cross-repository docs for a service with several repos |

## Quick start

```bash
python3 -m unittest discover -s tests          # check the agent itself
scripts/install.sh                             # install for this user
cd <repository> && git switch -c docs/baseline
<path to this repo>/scripts/install.sh --target .
claude                                          # then: "Use the docs-bootstrap skill to document this repository"
```

Full instructions are in the [runbook](docs/RUNBOOK.md).

## Documents

| Document | For |
|---|---|
| [Strategy and design](docs/STRATEGY.md) | Why and how: approach, design, adoption |
| [Architecture](docs/ARCHITECTURE.md) | Components, data flow and trust boundaries |
| [Security](docs/SECURITY.md) | Data handling, permissions, threats and controls |
| [Runbook](docs/RUNBOOK.md) | Step-by-step instructions for engineers |
| [Review checklist](docs/REVIEW-CHECKLIST.md) | Reviewing the agent before you use it |

## Repository layout

```
RULES.md                 rules every run follows
skills/                  the four skills (instructions for Claude Code and Copilot)
templates/repo/          per-repository page templates
templates/central/       central docs page templates
extractors/              fact extraction (no AI)
scripts/                 markers, citations, output checks, change mapping, installer
config/                  permission template and example config
evaluation/              SME sampling and accuracy scoring
tests/                   unit tests (standard library unittest)
docs/                    strategy, architecture, security, runbook, review checklist
```

## Requirements

Python 3.9 or later (standard library only), git, and Claude Code with access to a Claude model. gitleaks is optional.
