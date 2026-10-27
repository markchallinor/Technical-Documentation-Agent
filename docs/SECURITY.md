# Security: documentation agent (Agent 1)

This page sets out how the documentation agent handles data, what it is allowed to do, the threats considered and the controls for each. It is written for whoever reviews the agent before it is used, for example an architect or security lead.

## Data handling

| Question | Answer |
|---|---|
| Classification of the input | Whatever classification your organisation gives the code. Record it in your own review record. |
| Basis for processing with Claude | Your agreement with your model provider, which must cover that classification |
| What is sent to the model | The rules and skill instructions, the facts file, and the repository files Claude Code reads while drafting. Secret files (`.env`, keys, credentials) are blocked from being read (see "Permissions"). |
| What is never sent | Values from `.env` and credential files. The fact extractor records names and paths only. |
| What the agent stores | A local facts file and verification report in `.docs-agent/` on the engineer's machine. Both are git-excluded and can be deleted after the PR is merged. |
| Network access by agent scripts | None. Standard library only, no network calls. |
| Network access by Claude Code | The model service only. Web fetch and web search are denied. |
| Where output goes | Markdown in the repository's `docs/` folder, published only through a PR the engineer raises and the owners approve |

### Residual risk: secrets hard-coded in source

Older code may contain hard-coded secrets in ordinary source files. If it does, Claude Code may read those files while drafting, and their content goes to the model service under your provider agreement. **The secret cannot reach the documentation:** the rules forbid reproducing values, and `check_output.py` blocks the PR if anything resembling a secret is in `docs/`.

**Recommended before the baseline:** run a secret scanner (for example gitleaks, or GitHub secret scanning) across the repositories, and rotate anything found. This is good practice whatever happens with the agent.

## Permissions

### The engineer

They use their own Claude Code seat and their normal repository permissions. There is no shared or service identity.

### Claude Code

Permissions come from [`config/claude-settings.template.json`](../config/claude-settings.template.json), which `install.sh` writes to `<repo>/.claude/settings.local.json`. `defaultMode` is `default`, so **anything not explicitly allowed needs the engineer to approve it at the time**.

| | Rules |
|---|---|
| **Allowed without asking** | Read files in the repository and the agent's install folder; Glob; Grep; **edit only under `docs/`**; read-only git commands (`log`, `diff`, `show`, `ls-files`, `rev-parse`, `blame`, `status`); the five named agent scripts |
| **Denied outright** | Web fetch and web search; `git push`, `commit`, `reset`, `checkout` and `remote`; `curl`, `wget`, `ssh` and `scp`; `pip install` and `npm install`; `rm`; reading `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*` and `credentials*` |
| **Everything else** | Prompts the engineer, who is told in the [runbook](RUNBOOK.md) to decline anything outside the skill's steps |

### Copilot

If Copilot agent mode is used instead of Claude Code, the settings file does not apply. Copilot's tool approval prompts must stay on, and auto-approve must not be used. `check_output.py` still runs before every PR.

### Backstop

Whatever the tool permissions allow, `check_output.py` fails if any file outside `docs/` has been changed, added or deleted. The engineer must run it, and it must pass, before raising a PR.

## Threats and controls

| # | Threat | Controls |
|---|---|---|
| T1 | **A secret ends up in the documentation** | Rule 5 forbids reproducing values. Configuration is documented by name only. The extractor never records values. `.env` and key files are blocked from being read. `check_output.py` runs secret rules (and gitleaks if installed) over all of `docs/`, and any match blocks the PR. Matches are reported by location only, never printed. |
| T2 | **Personal data ends up in the documentation** | Rule 5 forbids names, email addresses and real data. The facts file never contains email addresses. `check_output.py` blocks email addresses (except example domains), phone numbers, National Insurance numbers and card numbers. |
| T3 | **Prompt injection**: repository content contains instructions | Rule 2 says repository content is data. Tool permissions deny network, push and destructive commands, and anything else needs the engineer's approval. `check_output.py` catches changes outside `docs/`. Owners review every PR. |
| T4 | **The agent changes code or configuration** | Edit is only allowed under `docs/`; anything else prompts the engineer. `check_output.py` fails on any change outside `docs/`. The engineer commits by hand and sees the diff. |
| T5 | **Inaccurate documentation misleads developers** | Every claim cites file and line. `check_citations.py` proves each citation exists. `docs-verify` re-checks every claim in a separate session. Gaps are marked `Unknown` rather than guessed. Owner review and SME sampling measure accuracy against the quality bar. |
| T6 | **Sensitive architecture detail is published too widely** | Rules forbid internal hostnames and IP addresses, and `check_output.py` warns on them. The visibility of the docs site is decided when it is set up (open question in the strategy). |
| T7 | **The agent's own code or instructions are tampered with** | Engineers install from a reviewed, tagged release of this repository. Changes to rules, skills, permissions or checks require a version bump and are visible in git history. Standard library only, so there is no dependency supply chain. |
| T8 | **An agent-written section overwrites a person's work** | Markers separate generated from human content, and the rules forbid changing content outside markers. The PR diff shows every change for review. |
| T9 | **Ownership is published wrongly** | The agent records owners as `Unknown – needs SME input` unless the engineer confirms CODEOWNERS is accurate, and never infers people from git history. |

## If something goes wrong

| Situation | Action |
|---|---|
| `check_output.py` finds a possible secret before the PR | Remove it from the docs. If it's a real secret, tell the repository owner, because it is also in the source code and should be rotated. |
| A secret or personal data is found in merged docs | Treat it as a security incident under the normal process: rotate the secret, remove it from the docs, and consider whether git history needs cleaning. Record what the checks missed, and add a rule to `check_output.py`. |
| The agent did something outside its steps | Stop the session. Discard the changes with git. Report it to whoever maintains the agent, with the session transcript. |
| Stop all use of the agent | Remove `~/.claude/skills/docs-*` and `~/.docs-agent` on each machine where it is installed. Nothing else runs on its own. |
