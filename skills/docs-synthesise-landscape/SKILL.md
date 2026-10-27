---
name: docs-synthesise-landscape
description: Build the central, cross-repository system documentation (landscape, integration map, data flows, ownership, glossary) from the baseline docs and facts of all repositories. Use when the engineer asks to create or update the central or system-level docs.
---

# Synthesise the central system documentation

You are writing the documentation that explains how all the repositories fit together. An engineer is supervising this run.

Agent files are installed at `__AGENT_HOME__`.

## Setup this skill expects

The engineer starts Claude Code in the **central docs repository**, inside a workspace folder that holds every repository side by side:

```
workspace/
├── central-docs/      ← Claude Code runs here; only its docs/ is written
├── repo-one/
├── repo-two/
└── ...
```

Each repository has its baseline docs merged and up to date.

## Step 0 – Rules and preconditions

1. Read `__AGENT_HOME__/RULES.md` in full and follow it for the rest of this run.
2. Run `git status` in the central docs repository. The working tree must be clean and the branch must not be the default branch. Otherwise stop and ask the engineer.
3. List the sibling repositories in the workspace (`../*/` folders containing `.git`). Show the list to the engineer and confirm it is complete. If `.docs-agent/config.json` sets `expected_repositories`, check the count matches it.

## Step 1 – Gather facts for every repository

For each repository, run:

```
python3 __AGENT_HOME__/extractors/extract_facts.py --repo ../<repo> --out .docs-agent/facts/<repo>.json
```

Also check each repository has agent-generated docs (`../<repo>/docs/index.md` with markers). If any don't, list them and ask the engineer whether to continue without them.

Write `docs/_agent/sources.json`, recording for each repository its directory name and `git.head_commit` from its facts file. This records exactly which version of each repository the central docs describe.

## Step 2 – Work out the connections

Use the facts and each repository's `interfaces.md`, `data.md` and `deployment.md`. Read the code to confirm every connection.

- **Calls between repositories:** match outbound HTTP calls and `url_domains_in_code` in one repository to routes in another. Match shared API specs.
- **Shared messaging:** the same queue, topic or Celery broker names in more than one repository.
- **Shared data:** the same database, schema or table names used by more than one repository. Treat matching environment variable names (for example two repositories both reading `DATABASE_URL`) as a lead only, never as proof.
- **Shared infrastructure:** the same platform, cluster or Terraform modules.
- **External services:** services outside the system used by one or more repositories (for example an email, payment or identity provider).

Every connection you document needs a citation at **both** ends, in the form `` `repo-name:path/to/file.py:42` ``. A connection with evidence at only one end must be labelled `Inferred – needs confirmation`.

## Step 3 – Write the central pages

Create each page from `__AGENT_HOME__/templates/central/`:

1. `integration-map.md`: every connection from step 2, as a table and a Mermaid diagram
2. `landscape.md`: the C4 system context and container view of the whole service. One line per repository saying what it does, linking to its docs.
3. `data-flows.md`: the main end-to-end journeys a user or system goes through, built from the integration map. Only include journeys the evidence supports. Ask the engineer which journeys matter most.
4. `ownership.md`: one row per repository, with its status. Record every owning team as `Unknown – needs SME input`, unless the engineer confirms a repository's CODEOWNERS file is accurate. Never list individuals.
5. `glossary.md`: domain terms that appear across repositories (model names, page types, service names), each with where it is used
6. `decisions/README.md`: cross-cutting decisions visible across repositories (for example a shared framework or platform), each marked `Inferred – needs confirmation`

`standards.md` is a fixed page. Copy it from the template unchanged.

Use `commit=PENDING` in every marker, as the rules require.

## Step 4 – Stamp and check

```
python3 __AGENT_HOME__/scripts/markers.py stamp
python3 __AGENT_HOME__/scripts/check_citations.py --workspace ..
python3 __AGENT_HOME__/scripts/check_output.py
```

Fix anything reported.

## Step 5 – Hand over

Report to the engineer as described in section 8 of the rules. Also list:

- connections labelled `Inferred` that need confirming
- repositories with no connections found, which may mean something is missing

Then tell them to verify in a fresh session with `docs-verify`, passing `--workspace ..` to `check_citations.py`.
