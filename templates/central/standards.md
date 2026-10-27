# Documentation standards

This page explains how this technical documentation is written and kept up to date.

## Where documentation lives

- Each repository documents itself in its own `docs/` folder.
- This repository holds documentation that spans repositories: the landscape, integration map, data flows, ownership and glossary.

## Generated and human-written content

Much of the documentation is drafted by a documentation agent from the code, then reviewed by the owning team. Generated sections are wrapped in markers:

```markdown
<!-- agent:begin section=data.schema commit=1a2b3c4 agent=0.1.0 -->
...
<!-- agent:end -->
```

- `commit` is the source commit the section was generated from.
- `agent` is the version of the documentation agent that generated it.
- **Do not edit inside the markers by hand.** The next refresh will overwrite your change. Instead, change the code or raise it with the team that runs the agent.
- **Write anything else in the "Notes from the team" section** of each page, or in new sections without markers. The agent never changes content outside markers.

## Evidence

- Every generated statement links to the file and line it came from. If a link looks wrong, the statement may be wrong too. Please report it.
- **Unknown – needs SME input** marks a question the code cannot answer. If you know the answer, add it to "Notes from the team" and tell the team that runs the agent.
- **Inferred – needs confirmation** marks a reasonable reading of the code that a person should confirm.

## What is never documented

Secret values, personal data, internal hostnames and IP addresses. Configuration is documented by name and purpose only.

## Keeping it current

- The agent refreshes each repository's documentation on a regular schedule, and after significant changes.
- When you raise a pull request, tick the "docs updated" checkbox if your change affects anything in `docs/`, and update the "Notes from the team" sections where needed.
- Automatic updates on every pull request are planned as a later piece of work.

## Writing style

Follow the team's style guide. If there isn't one, write plain English: short sentences, active voice and sentence case headings.
