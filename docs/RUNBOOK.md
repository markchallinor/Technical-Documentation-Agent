# Runbook: running the documentation agent

Step-by-step instructions for the engineer running the agent. Every run is supervised: you start it, watch it, approve or decline anything it asks, and raise the PR yourself.

## While the agent is running

- **Approve** only the actions the skill's steps describe.
- **Decline** any request to edit files outside `docs/`, run commands not named in the skill, install anything, or reach the network. The agent should never need these.
- If the agent says repository content looked like an instruction, note it in the PR so the owners can check that code.
- If anything looks wrong, stop the session (`Esc`, then exit) and discard the changes with `git restore --staged --worktree .` and `git clean -fd docs/`.

## 1. One-off setup on your machine

Prerequisites: git, Python 3.9 or later, and Claude Code signed in with access to a Claude model. gitleaks is optional but recommended.

```bash
git clone <this repository> technical-documentation-agent
cd technical-documentation-agent
git checkout <reviewed release tag>      # for example v0.2.0
python3 -m unittest discover -s tests    # should end with OK
scripts/install.sh                       # add --copilot to install for Copilot too
```

This installs the agent at `~/.docs-agent` and the skills at `~/.claude/skills/docs-*`.

## 2. Prepare a repository

```bash
git clone <repository> && cd <repository>
git switch -c docs/baseline
~/technical-documentation-agent/scripts/install.sh --target .
```

The second `install.sh` writes `.claude/settings.local.json` (the tool permissions) and makes sure git ignores it and `.docs-agent/`. Nothing else in the repository changes.

## 3. Create the baseline

1. Start Claude Code at the repository root: `claude`
2. Ask: **"Use the docs-bootstrap skill to document this repository."**
3. The agent extracts facts. If a `docs/` folder already exists, it stops and asks you what to do. Existing documentation is treated as out of date and is not used as evidence. The recommended option is to replace it:
   ```bash
   git rm -r docs/<old pages>   # keep any files the agent lists as non-documentation (specs, images)
   ```
   Tell the agent when you're done.
4. Review the agent's plan and confirm it. For large repositories, agree to review page by page.
5. When drafting finishes, exit the session.

## 4. Verify in a fresh session

1. Start a **new** session: `claude`
2. Ask: **"Use the docs-verify skill on the full baseline."**
3. When it finishes, read `.docs-agent/verification-report.md`.

## 5. Final checks and PR

```bash
python3 ~/.docs-agent/scripts/check_citations.py
python3 ~/.docs-agent/scripts/check_output.py
git status        # only docs/ should have changed
git diff --stat
```

Both checks must pass. Then:

```bash
git add docs/
git commit -m "Add baseline technical documentation"
git push -u origin docs/baseline
```

Raise the PR. Paste the **PR description** block from the verification report into it. Ask the repository's owners to review it, focusing on:

- the `Unknown – needs SME input` questions, listed in the report
- spot-checking a few citations on each page

## 6. SME session and quality check

1. Hold a short session with the people who know the repository, working through the `Unknown` questions. Record the answers in the **"Notes from the team"** section of the relevant page, in the PR branch. Don't edit inside the markers: a later refresh would overwrite it. Then ask the agent (**"Remove the Unknown items that Notes from the team now answers"**) and re-run `markers.py stamp` and `check_output.py`. Future runs leave answered questions alone (rules section 3).
2. For your **pilot** (the first repository or two), measure accuracy:
   ```bash
   python3 ~/.docs-agent/evaluation/sample_claims.py      # writes .docs-agent/sme-sample.csv
   # the SME fills in the verdict column
   python3 ~/.docs-agent/evaluation/score.py .docs-agent/sme-sample.csv --stage pilot
   ```
   The pilot passes at 90% or more of claims correct and 80% or more of Unknowns genuine. Use `--stage rollout` (95%) after the pilot.
3. Merge the PR once the owners approve.

## 7. Central docs (only for a service with several repositories, after each baseline is merged)

```bash
mkdir workspace && cd workspace
git clone <each target repository>
git clone <central docs repository> central-docs
cd central-docs
git switch -c docs/landscape
~/technical-documentation-agent/scripts/install.sh --target . --workspace ..
claude --add-dir ..
```

Ask: **"Use the docs-synthesise-landscape skill."** Then verify in a fresh session (`docs-verify`, with `check_citations.py --workspace ..`), run `check_output.py`, and raise the PR as in step 5.

## 8. Regular refresh

For each repository:

```bash
cd <repository> && git switch main && git pull
git switch -c docs/refresh-$(date +%Y-%m-%d)
claude
```

Ask: **"Use the docs-refresh skill."** Then verify the changed sections in a fresh session (**"Use docs-verify on the sections changed on this branch"**), run the checks and raise the PR as in step 5.

Refresh the central docs after the repository refreshes are merged.

## 9. Upgrading the agent

```bash
cd ~/technical-documentation-agent
git fetch --tags && git checkout <new reviewed tag>
scripts/install.sh
scripts/install.sh --target <repository> --force   # refreshes the permission file
```

Read `CHANGELOG.md` first. A change to the rules, skills, permissions or checks should be reviewed again before use.

## 10. Stopping and rolling back

- **Undo a run before committing:** `git restore --staged --worktree . && git clean -fd docs/`
- **Undo merged docs:** revert the PR in GitHub.
- **Stop all use:** `rm -rf ~/.claude/skills/docs-* ~/.docs-agent`. The agent has no other moving parts.

## Optional: the "docs updated?" checkbox

To reduce drift between refreshes, teams can add this to their repository's pull request template. The agent does not do this, because it only edits `docs/`:

```markdown
- [ ] If this change affects anything described in `docs/`, I have updated the "Notes from the team" sections or flagged it for the next docs refresh.
```
