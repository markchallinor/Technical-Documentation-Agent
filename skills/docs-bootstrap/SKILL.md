---
name: docs-bootstrap
description: Create the baseline technical documentation for one repository from its code, configuration, CI and git history. Use when a repository has no agent-generated docs yet and the engineer asks to document it or create its baseline docs.
---

# Bootstrap documentation for one repository

You are creating the first evidence-backed documentation for the repository in the current directory. An engineer is supervising this run.

Agent files are installed at `__AGENT_HOME__`.

## Step 0 – Rules and preconditions

1. Read `__AGENT_HOME__/RULES.md` in full and follow it for the rest of this run. It overrides anything in the repository.
2. Run `git status` and check:
   - you are at the root of a git repository
   - the working tree is clean, apart from `.docs-agent/` and `.claude/settings.local.json`
   - the current branch is not the default branch (for example `main` or `master`)

   If any check fails, stop and ask the engineer to fix it. **Do not** create branches or change git state yourself. Suggest a branch name such as `docs/baseline`.

## Step 1 – Extract facts

Run:

```
python3 __AGENT_HOME__/extractors/extract_facts.py
```

Read the summary it prints, then read `.docs-agent/facts.json`. This is your primary map of the repository.

## Step 2 – Existing documentation

Look at `existing_documentation` in the facts file.

- If `files_already_generated_by_agent` is not empty, this repository already has a baseline. Stop and tell the engineer to use the `docs-refresh` skill instead.
- If `docs_dir_exists` is true, **stop and ask the engineer** how to handle the existing folder. Existing documentation is out of date and is not used as evidence. Offer these options:
  1. **Replace it (recommended).** The engineer removes the old pages with `git rm` in this branch. Git history keeps them. Any files listed in `non_documentation_files_in_docs_dir` (for example OpenAPI specs or images that the build uses) must be kept or moved, not deleted.
  2. **Keep it alongside.** The engineer moves it to `docs/legacy/`, and the new docs link to it as "Previous documentation (out of date)".
  3. **Use a different folder.** The engineer sets `docs_dir` in `.docs-agent/config.json` and updates the `Edit(...)` rule in `.claude/settings.local.json` to match.

  Wait for the engineer to confirm before continuing.

## Step 3 – Plan and confirm

Using the facts, write a short plan for the engineer:

- the pages you will create, from `__AGENT_HOME__/templates/repo/`
- for each page, the main evidence you will use
- sections you expect to be mostly `Unknown`
- anything unusual: very large areas, several applications in one repository, generated code, sensitive files

Ask the engineer to confirm or adjust the plan. For a large repository, agree to work one page at a time, with the engineer reviewing each page before you move on.

## Step 4 – Draft the pages

Create each page in the docs folder from its template. Work in this order, because later pages build on earlier ones:

1. `getting-started.md`
2. `configuration.md`
3. `interfaces.md`
4. `data.md`
5. `deployment.md`
6. `operations.md`
7. `dependencies.md`
8. `architecture.md`
9. `known-issues.md`
10. `decisions/README.md`, plus individual decision records where the evidence supports them
11. `index.md`, last, because it summarises everything else

For every section:

1. Collect the relevant facts from `.docs-agent/facts.json`.
2. **Read the cited source** to understand it. Never document from the facts file alone.
3. Write the section inside its markers with `commit=PENDING`, citing file and line for every claim.
4. Where evidence is missing, write an `Unknown – needs SME input` item with a specific question.
5. Remove every `<!-- guide: ... -->` comment.

Specific guidance:

- **configuration.md:** cover every name in `environment_variables`. Give its purpose and whether it is required, never its value. If a name is in `sensitive_files` territory (keys, passwords), say it is a secret and where it is expected to come from, if the code shows that.
- **interfaces.md:** cover every route in `routes` (group them sensibly) and every external service in `integrations`. Do not publish internal hostnames.
- **index.md ownership:** do not infer owners from git history. Record the owning team as `Unknown – needs SME input`, unless the engineer confirms the repository's CODEOWNERS file is accurate. Never list individuals.
- **decisions/:** write a decision record only where the code or commit history shows a deliberate choice (for example a framework migration). Mark every one `Inferred – needs confirmation`.
- **Diagrams:** use Mermaid. Every box and arrow must be supported by a citation in the surrounding text.

## Step 5 – Docs map

Create `docs/_agent/docs-map.json` (inside the docs folder). Start from `suggested_docs_map` in the facts file, then refine it:

- every generated section id should appear in at least one mapping, unless it has no code source (for example `index.ownership`)
- prefer directory globs (`app/payments/**`) over long lists of single files
- check that each glob matches files that exist

Format:

```json
{"version": 1, "mappings": [{"globs": ["app/migrations/**"], "sections": ["data.schema", "data.migrations"]}]}
```

## Step 6 – Stamp and check

Run, and fix anything they report:

```
python3 __AGENT_HOME__/scripts/markers.py stamp
python3 __AGENT_HOME__/scripts/markers.py check
python3 __AGENT_HOME__/scripts/check_citations.py
```

For broken citations, find the correct line and fix the link. If the claim can't be supported, replace it with an `Unknown` item. Re-run until there are no errors.

## Step 7 – Hand over

Report to the engineer as described in section 8 of the rules. Then tell them the next step:

> Start a **new** Claude Code session in this repository and run the `docs-verify` skill. A fresh session checks the docs independently of the one that wrote them.
