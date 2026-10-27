---
name: docs-refresh
description: Update a repository's agent-generated documentation for code changes made since the docs were last generated. Use when the engineer asks to refresh or update the docs of a repository that already has a baseline.
---

# Refresh documentation for code changes

You are updating existing agent-generated documentation so it matches the current code. An engineer is supervising this run.

Agent files are installed at `__AGENT_HOME__`.

## Step 0 – Rules and preconditions

1. Read `__AGENT_HOME__/RULES.md` in full and follow it for the rest of this run.
2. Run `git status`. The working tree must be clean (apart from `.docs-agent/` and `.claude/settings.local.json`), and the branch must not be the default branch. Otherwise stop and ask the engineer. Suggest a branch name such as `docs/refresh-YYYY-MM`.

## Step 1 – Find what changed

1. Run `python3 __AGENT_HOME__/scripts/markers.py commits`. It prints the source commits the docs were generated from, oldest first.
   - If it prints nothing, or `markers.py check` reports unstamped sections, the repository has no complete baseline. Stop and tell the engineer to use `docs-bootstrap`.
2. Take the **oldest** commit as the starting point, `<since>`.
3. Run:

   ```
   python3 __AGENT_HOME__/extractors/extract_facts.py
   python3 __AGENT_HOME__/scripts/map_changes.py --since <since>
   ```

4. Show the engineer the summary: the number of changed files, the affected sections and the unmapped files. If more than about 15 sections are affected, agree with the engineer whether to refresh them all now or in batches.

## Step 2 – Update affected sections

For each affected section:

1. Read the current section.
2. Read what changed: `git diff <since>..HEAD -- <the files mapped to this section>`.
3. Read the current code at the relevant lines.
4. Update the section so it matches the current code. Keep correct content, fix outdated content, add new items and remove items that no longer exist. Update every citation whose line numbers moved.
5. Set the marker to `commit=PENDING`.

Leave human-owned content outside markers untouched, even if it now looks out of date. List it in your report so the engineer can raise it with the team.

## Step 3 – Unmapped changes

Look at each unmapped file from Step 1:

- If it affects the docs (for example a new module, a new external service or a new deployment file), update the right sections. Add a glob for it to `docs/_agent/docs-map.json`.
- If it doesn't (for example a test fixture or a style change), leave it.

Then compare the new facts file with the docs, as in step 3 of the `docs-verify` skill, to catch new environment variables, routes, models or CI jobs.

## Step 4 – Stamp and check

Every section has now been checked against `HEAD`: either updated, or confirmed unaffected because none of its mapped files changed. So re-stamp them all:

```
python3 __AGENT_HOME__/scripts/markers.py stamp --all
python3 __AGENT_HOME__/scripts/markers.py check
python3 __AGENT_HOME__/scripts/check_citations.py
```

Fix anything reported.

## Step 5 – Hand over

Report to the engineer as described in section 8 of the rules, including the sections changed and any human-owned content that may be out of date. Then tell them:

> Start a **new** Claude Code session and run `docs-verify` on the sections changed on this branch. Then run `check_output.py` and raise the PR.
