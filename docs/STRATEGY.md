# Technical Documentation Agent: Strategy and design

**Purpose:** document a software service from its code, and keep that documentation up to date
**Works on:** any service, whether it is one repository or many
**Audience:** whoever decides to use the agent, the people who review it before use (for example an architect or security lead), and the engineers who run it

---

## 1. Why use it

Technical documentation is often missing, incomplete or out of date. The code is the only reliable description of how a service works. When that happens:

- knowledge sits with individuals rather than in the repository
- onboarding new people is slow
- architectural decisions and integrations are implicit
- changes carry risks nobody can see

The agent reads a service's code and produces documentation in which every statement points to the code it came from. Where the code can't answer a question, it says so rather than guessing.

**Goals**

1. **Baseline.** Produce accurate, evidence-backed technical documentation for each repository of a service, plus a cross-repository view when the service has more than one.
2. **Single source of truth.** Keep the documentation next to the code, so it is the reference people use.
3. **Stay current.** Keep it up to date: first through supervised refreshes, and later automatically on every pull request.
4. **Reviewable and safe.** Simple enough for reviewers to approve before use. It runs wherever the code already is, and nothing about the service being documented ever goes into this repository.

**Non-goals**

- Rewriting or refactoring code
- End-user or marketing documentation
- Replacing human architectural judgement. The agent drafts and people approve.

---

## 2. Two agents, delivered separately

The work is split into two agents. Each one is built, reviewed and approved separately.

| | **Agent 1: Documentation agent** (this repo, now) | **Agent 2: PR update agent** (later) |
|---|---|---|
| Purpose | Create the baseline documentation and refresh it on demand | Update the documentation automatically on every pull request |
| How it runs | **Interactively.** An engineer starts and supervises every run in Claude Code. | **Unattended**, in CI (for example GitHub Actions) |
| Writes to repositories | Only through PRs the engineer raises under their own account | Through a bot identity, on developers' PR branches |
| Credentials | The engineer's existing Claude Code (or Copilot) access. No stored secrets. | A service account and a stored model token |
| Review | This document and the agent repo | A separate design and review, once Agent 1 is proven |

**Why split it**

- **A much smaller first review.** Reviewers approve "an engineer runs Claude Code with these written instructions, it writes only to `docs/`, and a person raises and approves the PR". There is no unattended execution, bot identity, stored secret or write access to developers' branches.
- **Fewer dependencies.** Agent 1 needs no CI changes, service accounts or agreement from teams to have a bot commit to their PRs.
- **It proves quality first.** The accuracy of the generated docs is tested and tuned under supervision before anything runs on its own.
- **Agent 2 gets a clean start.** Agent 1 builds the foundations Agent 2 needs (section 10), so Agent 2 becomes "a CI wrapper around Agent 1's refresh skill".

**The trade-off.** The docs start to drift as soon as the baseline is merged. Section 7.4 sets out how to keep that small until Agent 2 is in place.

---

## 3. Design principles and assumptions

| Assumption | How the design handles it |
|---|---|
| The code being documented may be private or sensitive | The agent is **generic and configuration-driven**. Repository names, URLs and organisation details live in local config, never in this repo. The agent runs wherever engineers already work on the code. |
| This agent repository may be public | It contains no names, hostnames, sample output, credentials or screenshots from any service it is used on. Example config uses placeholders only, and a test guards against identifying terms. |
| Someone reviews the agent before it runs | Every component has a clear purpose, explicit permissions and a documented data flow. Agent instructions are plain, versioned Markdown rather than buried in code. |
| The code may be old and mixed | Expect several languages and frameworks, dead code, vendored dependencies and inconsistent conventions. Discovery has to be robust and honest about uncertainty. |
| Teams use GitHub, with **Claude Code** and/or **GitHub Copilot** | Agent behaviour is packaged as files both tools read natively (Agent Skills and instruction files). Agent 1 is designed for Claude Code (section 7). The scripts work with any git host. |
| Sending code to an AI model must be allowed | Users confirm that their agreement with the model provider covers their code before use. Hard-coded secrets in source remain a residual risk (see [SECURITY.md](SECURITY.md)). |
| CODEOWNERS may be missing or wrong | Owners are recorded as `Unknown – needs SME input` unless the engineer confirms CODEOWNERS is accurate. They are never inferred from people's names in git history. |
| Existing documentation may be out of date | It is never used as evidence. Where a `docs/` folder already exists, the agent stops and the engineer decides how to handle it. |
| Teams may have a house style | Docs follow plain English by default. Teams can name their own style guide in config (`style_guide`). |

---

## 4. Approach in one page

```
 ┌─────────────────────── wherever the code is worked on ────────────────────┐
 │                                                                            │
 │  Engineer runs Claude Code with the agent's skills, one repo at a time     │
 │                                                                            │
 │  Source repo ──► [1] Fact extraction ──► facts.json                       │
 │                          (scripts, no AI)                                  │
 │                               │                                            │
 │                               ▼                                            │
 │                      [2] Drafting ──► docs/ drafts + evidence              │
 │                               │                                            │
 │                               ▼                                            │
 │                      [3] Verification ──► claims checked against code,     │
 │                               │            secret and PII scan             │
 │                               ▼                                            │
 │                      [4] Engineer raises PR ──► repo owners review/merge   │
 │                                                                            │
 │  If the service has several repos, once each one is done:                  │
 │                      [5] Cross-repo synthesis ──► central system docs      │
 │                                                                            │
 │  Regularly (for example monthly):                                          │
 │                      [6] Refresh ──► update docs for changes since the     │
 │                                       last refresh ──► PR ──► review       │
 └────────────────────────────────────────────────────────────────────────────┘
```

Core principles:

1. **Facts first, prose second.** Deterministic scripts extract what can be known for certain: languages, dependencies, entry points, routes, environment variable *names*, CI pipelines, infrastructure-as-code resources, database migrations and OpenAPI specs. The AI explains and connects those facts; it does not invent them.
2. **Every claim has evidence.** Generated statements cite `path/to/file:line` in the source repo. If the agent can't find evidence, it writes "Unknown – needs SME input" instead of guessing.
3. **A person runs and approves everything.** Every run is started and watched by an engineer. The agent never pushes to any branch; the engineer raises the PR and the repo owners approve it.
4. **Generated and human-written content coexist.** Generated sections are fenced with markers so the agent only rewrites what it owns, and human additions survive.
5. **Least privilege.** The agent reads source and writes only under `docs/**`.

---

## 5. Where the documentation lives

**One repository:** the docs live in its `docs/` folder. Nothing else is needed.

**Several repositories:** there are three options.

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Docs in each repo** (`/docs` folder) | Each repo documents itself | Docs sit next to the code and can change in the same PR, ownership is clear, easy to review | No single view of the whole system |
| **B. One central docs repo** | All docs in a separate repo | One place, easy to publish | Code and docs are reviewed separately, so drift creeps back |
| **C. Hybrid (recommended)** | Per-repo `/docs` for repo-level detail, plus a central "system" docs repo for cross-cutting content, published together | Docs stay close to code *and* there is one central reference | Slightly more setup: an aggregation build |

**Recommendation: Option C** for multi-repository services. It is also what Agent 2 needs, because per-PR updates only work if the docs live in the same repo as the code.

- **Per repo (`/docs`):** what this repo does, how to run it, its architecture, interfaces, configuration, data, deployment, operations and decisions.
- **Central repo:** the system landscape (C4 context and containers), integration map, data flows across repos, glossary, ownership, cross-cutting decisions and documentation standards.
- **Publishing:** any static docs tool that reads Markdown works, for example MkDocs, Backstage TechDocs, Docusaurus or the GOV.UK Tech Docs Template. Publishing is an ordinary docs build, separate from the agent.

---

## 6. Documentation structure (the templates)

Use **Diátaxis** to organise content (tutorials, how-to guides, reference, explanation), **C4** for architecture diagrams (generated as Mermaid so they are version-controlled text), and lightweight **ADRs** for decisions.

### 6.1 Per-repository template (`/docs`)

| File | Contents | Main sources of evidence |
|---|---|---|
| `index.md` | Purpose, status, tech stack summary, ownership (Unknown until confirmed) | Entry points, manifests, commit activity |
| `architecture.md` | C4 container and component view, key modules, request flow | Directory structure, entry points, routing, DI configuration |
| `getting-started.md` | Prerequisites, local setup, build, test, run | Makefile, package scripts, Dockerfile, CI config |
| `configuration.md` | Environment variables and feature flags: **names, purpose and defaults only, never values** | Config loaders, `.env.example`, IaC |
| `interfaces.md` | Inbound APIs, outbound calls, events and queues, external services | Route definitions, OpenAPI, HTTP clients, message consumers |
| `data.md` | Data stores, schemas, migrations, personal data and retention notes | Migrations, ORM models, IaC |
| `deployment.md` | Pipelines, environments, infrastructure | CI/CD files, Terraform/CloudFormation/Helm |
| `operations.md` | Logging, monitoring, alerts, common failure modes | Logging config, health checks, alert definitions |
| `dependencies.md` | Key third-party libraries, versions, end-of-life or risky dependencies | Lockfiles and manifests |
| `decisions/` | ADRs. Retrospective ADRs are labelled **"Inferred – needs confirmation"** | Git history, code |
| `known-issues.md` | Tech debt, TODO/FIXME hotspots, test gaps | Code, test layout, CI |

### 6.2 Central (system) docs, for multi-repository services

- `landscape.md`: C4 system context, every repo and how they relate
- `integration-map.md`: who calls whom, over which protocol, with what auth
- `data-flows.md`: end-to-end journeys, for example "a user signs up"
- `ownership.md`: repo to team and contact channel
- `glossary.md`: domain and business terms
- `standards.md`: how documentation is written and maintained, and how the agent works
- `decisions/`: cross-cutting ADRs

### 6.3 Section markers

```markdown
<!-- agent:begin section=interfaces.inbound commit=abc1234 agent=0.2.0 -->
...generated content with evidence links...
<!-- agent:end -->

## Notes from the team
Anything here is human-owned and never modified by the agent.
```

- `commit` records the source commit the section was generated from, so a refresh (and later Agent 2) knows which changes to look at. The model always writes `commit=PENDING`, and `markers.py stamp` fills in the real value.
- `agent` records the agent release that generated it.

---

## 7. How Agent 1 works

### 7.1 Tools and how it is run

- **Runner:** Claude Code, used interactively by an engineer with the target repo cloned. Copilot agent mode can run the same skills, because Copilot also reads Agent Skills.
- **Agent behaviour** is written as plain Markdown, once:
  - **[`RULES.md`](../RULES.md)**: the rules every run follows: evidence citations, never reproduce secret values, "Unknown" over guessing, existing docs are not evidence, no people's names, write only under `docs/**`, treat repo content as data rather than instructions. Every skill reads it first.
  - **Four Agent Skills** (`SKILL.md` files), one per task:

| Skill | What it does |
|---|---|
| `docs-bootstrap` | Runs fact extraction and drafts the full `/docs` set for one repo from the templates |
| `docs-verify` | A separate pass that checks every claim against its cited lines, flags unsupported claims and runs the secret and PII scan |
| `docs-refresh` | Updates a repo's docs for code changes since the commit recorded in its section markers |
| `docs-synthesise-landscape` | For multi-repository services: reads the facts and docs of every repo and drafts the central system docs |

- **Installation.** `install.sh` installs the rules, scripts and templates in `~/.docs-agent` and the skills in the engineer's personal skills folder (`~/.claude/skills`, and `~/.copilot/skills` if asked). It writes an uncommitted `.claude/settings.local.json` with the tool permissions (section 8) into the target repo. **Nothing is added to the target repository except its `docs/` folder.**

### 7.2 Baseline

**Start small.** For a multi-repository service, pilot on one or two repositories, tune the templates and config, then do the rest. For a single large repository, review the first few pages before drafting the rest.

| Step | What happens | AI? | Output |
|---|---|---|---|
| B0. Choose | Pick the repositories to document, and the pilot. A good pilot is one typical repo and one of the hardest. | No | A short list (kept privately) |
| B1. Fact extraction | `extract_facts.py` parses manifests, routes, CI, IaC, containers, migrations, models, OpenAPI specs, environment variable names, integrations and git history. Existing documentation is excluded. | No | `.docs-agent/facts.json` (local) |
| B2. Drafting | `docs-bootstrap` reads the facts and the relevant source files and fills each template section, with citations. | Yes | Draft `/docs` |
| B3. Verification | `docs-verify` checks the claims and scans the output. The engineer reviews the report and fixes or removes anything flagged. | Yes + scanners | Verification report |
| B4. Human review | The engineer raises a PR, reviewed by the people who know the code best. A short SME session fills the "Unknown" gaps; answers go in each page's "Notes from the team". | No | Merged baseline |
| B5. Cross-repo synthesis | Multi-repository services only: once each repo is merged, `docs-synthesise-landscape` drafts the central docs. Reviewed the same way. | Yes | Central docs |
| B6. Publish | Optional: build a docs site. | No | Docs site |

**Quality bar before going beyond the pilot.** On a sample, at least 90% of claims are verified correct by an SME, there are no secrets in the output, and the "Unknown" items are genuine unknowns rather than things the agent missed. `evaluation/` scores this.

### 7.3 Refresh (on demand)

An engineer runs `docs-refresh` on a repo:

1. It reads the commit recorded in each section marker and lists the code changes since then.
2. It uses the repo's `docs/_agent/docs-map.json` (section 10) to work out which sections those changes affect.
3. It regenerates only those sections. A fresh session then runs `docs-verify` on them.
4. The engineer raises a PR with the changes, and the repo owners review it.

This is the same work Agent 2 will do automatically, run by a person instead.

### 7.4 Keeping drift small until Agent 2 exists

- **Regular refreshes.** Run `docs-refresh` on a regular schedule (for example monthly), and straight after any significant change.
- **PR template checkbox.** Add "Have you updated `docs/` if this change affects it?" to the repo's PR template.
- **Ownership.** Once owners are confirmed, add CODEOWNERS entries for `docs/` so documentation changes reach the right reviewers.
- **Standards.** Publish `standards.md`, so developers know how and where to make manual updates.

---

## 8. Security and governance

The full detail is in [SECURITY.md](SECURITY.md), with a checklist in [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md). In summary:

- **Data:** source code is sent to the Claude model service, so the user's agreement with their model provider must cover it. The agent's scripts make no network calls, and Claude Code's only external connection is the model service.
- **Identities:** the engineer's own Claude Code access and their own git account. There is **no bot identity, service account or stored secret**.
- **Permissions:** Claude Code may read the repository and edit only under `docs/`. Network access, git changes, package installs, deletion and secret files are denied, and anything else needs the engineer's approval at the time.
- **Backstop:** `check_output.py` must pass before every PR. It fails on any change outside `docs/`, on anything that looks like a secret and on personal data, and it reports locations without printing values.
- **Accuracy:** every claim cites file and line, `check_citations.py` proves the citations exist, and verification runs in a separate session. An SME-marked sample is scored against the quality bar.
- **Auditability:** every generated section records its source commit and agent release, and each PR description carries the verification report summary.
- **Residual risk:** secrets hard-coded in source files may be read by the model while drafting. They are blocked from the output, but scanning the repositories and rotating anything found before the first run is recommended.

---

## 9. How the agent repo is laid out

```
technical-documentation-agent/
├── README.md                    # What it is, quick start, links
├── RULES.md                     # Rules every run follows
├── VERSION, CHANGELOG.md        # Release and what changed
├── CLAUDE.md                    # Guidance for people working on this repo
├── docs/
│   ├── STRATEGY.md              # This document
│   ├── ARCHITECTURE.md          # Components, data flow, trust boundaries
│   ├── SECURITY.md              # Data handling, permissions, threats and controls
│   ├── RUNBOOK.md               # Step-by-step instructions for engineers
│   └── REVIEW-CHECKLIST.md      # Checklist for whoever reviews the agent before use
├── skills/                      # Agent Skills, read by Claude Code and Copilot
│   ├── docs-bootstrap/SKILL.md
│   ├── docs-verify/SKILL.md
│   ├── docs-refresh/SKILL.md
│   └── docs-synthesise-landscape/SKILL.md
├── templates/
│   ├── repo/                    # Per-repository pages (section 6.1)
│   └── central/                 # Central pages (section 6.2)
├── extractors/extract_facts.py  # Deterministic fact extraction (no AI)
├── scripts/
│   ├── markers.py               # List, check and stamp section markers
│   ├── check_citations.py       # Prove every cited file and line exists
│   ├── check_output.py          # Only docs/ changed; no secrets or personal data
│   ├── map_changes.py           # Changed files → affected sections (docs-map.json)
│   └── install.sh               # Install skills; write local tool permissions
├── config/
│   ├── claude-settings.template.json  # Claude Code allow and deny rules
│   └── agent.example.json       # Optional per-repo settings
├── evaluation/                  # SME sampling and accuracy scoring
├── tests/                       # Unit tests (standard library unittest)
└── .github/workflows/tests.yml  # Tests this repo's code only; never runs the agent
```

All scripts use the Python standard library only, so there are no third-party dependencies to review.

---

## 10. Designed for Agent 2

Agent 1 builds these in now. They cost little, and they mean Agent 2 can be added without reworking the docs:

- **Section markers** with source commit and agent release (section 6.3), so changed sections can be found automatically
- **A `docs/_agent/docs-map.json` per repo**, generated during the baseline, mapping file globs to doc sections, for example `migrations/**` → `data.schema`
- **The `docs-refresh` skill**, which already does "update the docs for these code changes"
- **`check_output.py`**, the same safety check Agent 2 will run in CI
- **The same `RULES.md` and `docs-verify` step**

**Outline of Agent 2 (for a later, separate review)**

- A reusable CI workflow that each repo calls on pull requests. It runs `docs-refresh` against the PR's changes and commits doc updates to the PR branch, or posts them as suggestions.
- Engine options: Claude Code run headless, or Copilot CLI run non-interactively. A bot identity and a stored model token.
- Safeguards: no loops from its own commits, no runs on fork PRs, cost and time limits per PR, a kill switch, and a drift check that reports when mapped code changes but its docs section does not.

---

## 11. Measuring success

| Metric | Target |
|---|---|
| Repos with a reviewed baseline | Every repo chosen |
| Claim accuracy (SME sample) | ≥ 90% at pilot, ≥ 95% after |
| "Unknown" items resolved after SME sessions | ≥ 80% |
| Repos refreshed on schedule (until Agent 2) | Every documented repo |
| Secrets or personal data in published docs | 0 |
| Developer feedback ("docs were useful and correct") | Survey after a few months |
| Onboarding time for a new developer | Measurable reduction |

---

## 12. Adoption plan

| Stage | Activities | Exit criteria |
|---|---|---|
| 0. Agree | Answer the questions in section 13 and agree how the agent will be reviewed | Agreed approach |
| 1. Review | Reviewers work through [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md) against a release tag | Review passed |
| 2. Pilot | Baseline one or two repos, followed by SME review | Quality bar met (section 7.2) |
| 3. Tune | Adjust config, templates and docs maps | Re-run pilot passes |
| 4. Roll out | Baseline the remaining repos, then the central docs if there are several repos | All baselines merged |
| 5. Run | Regular refreshes; publish the docs if wanted | Docs stay current |
| 6. Agent 2 | Design, review and introduce per-PR automation | Separate approval |

---

## 13. Questions to answer before use

Keep your answers, and any decisions specific to your organisation, in your own private review record. Don't add them to this repository.

**For Agent 1**

1. **Model access:** how will engineers access Claude Code, and which models? Can it be installed where they work on the code?
2. **Data handling:** does your agreement with the model provider cover sending this code?
3. **Agent access:** are the permissions in section 8 acceptable: read the code, write only to `docs/`, a person raises every PR?
4. **Tooling:** are Python 3.9+ and git available? Can gitleaks be installed? For several repos, can an engineer clone them all into one workspace?
5. **Docs location:** for several repos, is the hybrid model (section 5) right, and is there a central docs repo?
6. **Publishing:** will the docs be published as a site? If so, with what tool, where, and who can see it?
7. **Existing documentation:** where is it, and can in-repo copies be replaced in the baseline PR?
8. **People:** who reviews each PR and answers SME questions? Is CODEOWNERS accurate?
9. **Pilot:** which repository or repositories?
10. **Secret scanning:** have the repositories been scanned for hard-coded secrets? See the residual risk in section 8.
11. **Style:** is there a house style guide to set in config?
12. **Budget:** what model usage is acceptable for the baseline and for refreshes?

**Deferred to Agent 2**

- Which engine runs in CI
- Runner type and network access to the model service
- A service account for the bot, and its tokens
- Whether teams accept bot commits on their PRs, or only suggestions
- The per-PR budget
