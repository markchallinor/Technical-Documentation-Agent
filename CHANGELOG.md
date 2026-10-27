# Changelog

## 0.2.0 – unreleased

The agent is now generic: it can document any service, whether it is one repository or many.

- Rewrote the strategy as a general design document. It has no assumptions about any particular organisation, estate or environment, and organisation-specific decisions belong in each user's own review record.
- Central, cross-repository docs are optional, for services with several repositories.
- New setting `style_guide`: docs follow plain English unless a house style guide is named (`RULES.md` section 7).
- New setting `expected_repositories`, in place of a fixed repository count.
- Ownership: CODEOWNERS is used only when the engineer confirms it is accurate.
- Removed platform- and sector-specific examples from the templates and skills.
- Added `tests/test_no_identifying_terms.py`, which fails if blocked terms (kept outside the repository) appear in files or commit messages.

## 0.1.0 – unreleased

First version of Agent 1, for review:

- rules for every run (`RULES.md`)
- skills: `docs-bootstrap`, `docs-verify`, `docs-refresh`, `docs-synthesise-landscape`
- per-repository and central page templates
- deterministic fact extractor
- marker, citation, output safety and change-mapping scripts
- installer and Claude Code permission template
- SME sampling and scoring for the quality bar
