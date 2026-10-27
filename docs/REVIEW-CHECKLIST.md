# Review checklist: documentation agent (Agent 1)

A checklist for whoever reviews the agent before it is used, for example an architect or security lead. Each item says where to check it. Review against a specific release tag, and record it here: `v_____`.

## 1. Scope and design

- [ ] The agent runs only interactively, started and supervised by an engineer. There are no workflows, schedules, bots or services. *Check:* [ARCHITECTURE.md](ARCHITECTURE.md), and confirm `.github/workflows/` only contains `tests.yml`, which tests this repository's own code.
- [ ] The agent writes only to the documentation folder of the repository it runs in. *Check:* [RULES.md](../RULES.md) section 1, and the `Edit` rule in [claude-settings.template.json](../config/claude-settings.template.json).
- [ ] People raise every PR, and repository owners approve it. *Check:* [RUNBOOK.md](RUNBOOK.md) step 5; `git push` and `git commit` are denied to the agent.

## 2. Data handling

- [ ] Your agreement with your model provider covers sending this source code to the Claude model service. *Check:* [SECURITY.md](SECURITY.md), "Data handling".
- [ ] Secret files are blocked from being read, and the extractor records names only, never values. *Check:* the `deny` list in the settings template; the docstring and `sensitive_files` in [extract_facts.py](../extractors/extract_facts.py); the test `test_secret_values_never_extracted`.
- [ ] The residual risk of secrets hard-coded in source, and the recommendation to scan and rotate before the baseline, are accepted. *Check:* [SECURITY.md](SECURITY.md), "Residual risk".
- [ ] The scripts make no network calls and use only the Python standard library. *Check:* the imports in `scripts/`, `extractors/` and `evaluation/`.

## 3. Permissions

- [ ] The allow list is the minimum needed. *Check:* the settings template, against each skill's steps.
- [ ] The deny list covers network access, git changes, installing packages, deletion and secret files. *Check:* the settings template.
- [ ] Anything not listed prompts the engineer (`defaultMode: default`), and the runbook tells them what to decline. *Check:* [RUNBOOK.md](RUNBOOK.md), "While the agent is running".
- [ ] If Copilot is used instead of Claude Code, its approval prompts stay on. *Check:* [SECURITY.md](SECURITY.md), "Permissions".

## 4. Output safety

- [ ] `check_output.py` fails on any change outside `docs/`, on possible secrets and on personal data, and prints locations only, never values. *Check:* [check_output.py](../scripts/check_output.py); the tests in [test_check_output.py](../tests/test_check_output.py).
- [ ] Running `check_output.py` is a required step before every PR. *Check:* the `docs-verify` skill step 4, and [RUNBOOK.md](RUNBOOK.md) step 5.
- [ ] Internal hostnames and IP addresses are warned on, and the rules forbid them. *Check:* [RULES.md](../RULES.md) section 5.

## 5. Accuracy and accountability

- [ ] Every claim must cite file and line, and citations are checked by script. *Check:* [RULES.md](../RULES.md) section 3; [check_citations.py](../scripts/check_citations.py).
- [ ] Verification runs in a separate session from drafting. *Check:* the bootstrap skill step 7, and [RUNBOOK.md](RUNBOOK.md) step 4.
- [ ] The quality bar (90% for the pilot, 95% after) is measured on an SME-marked sample before going beyond the pilot. *Check:* [evaluation/](../evaluation/); [STRATEGY.md](STRATEGY.md) section 7.2.
- [ ] Every generated section records the source commit and agent version. *Check:* [markers.py](../scripts/markers.py), the `stamp` command.
- [ ] Ownership is never inferred from people's names. *Check:* [RULES.md](../RULES.md) section 5; the `index.ownership` template.

## 6. Prompt injection

- [ ] The rules treat repository content as data, not instructions. *Check:* [RULES.md](../RULES.md) section 2.
- [ ] Even if an injected instruction were followed, the permissions and `check_output.py` limit the impact to the PR diff, which people review. *Check:* [SECURITY.md](SECURITY.md), threat T3.

## 7. Change control

- [ ] Engineers install from a reviewed release tag. *Check:* [RUNBOOK.md](RUNBOOK.md) steps 1 and 9.
- [ ] Any change to the rules, skills, permissions or checks bumps `VERSION`, is recorded in `CHANGELOG.md`, and needs re-approval. *Check:* [CLAUDE.md](../CLAUDE.md); [RUNBOOK.md](RUNBOOK.md) step 9.
- [ ] The tests pass on the release tag. *Check:* the `Tests` workflow run for the tag, or `python3 -m unittest discover -s tests`.
- [ ] The repository contains no internal names, hostnames, sample output or credentials. *Check:* `tests/test_no_identifying_terms.py` runs in CI with the `BLOCKED_TERMS` secret set and passes; `config/` contains examples only.

## Outcome

| | |
|---|---|
| Release reviewed | |
| Decision | Approved / Approved with conditions / Not approved |
| Conditions | |
| Reviewer | |
| Date | |
