# Working on this repository

This repository contains the documentation agent itself. It is public, so never add organisation names, internal repository names, hostnames, sample output from target repositories, or credentials. The identifying-terms test (`tests/test_no_identifying_terms.py`) checks for this.

- `RULES.md` and `skills/` define the agent's behaviour when it runs against a target repository. They are not instructions for working on this repository.
- Scripts use the Python standard library only (Python 3.9+). Do not add third-party dependencies.
- Run the tests with `python3 -m unittest discover -s tests`.
- Any change to `RULES.md`, `skills/`, `config/claude-settings.template.json` or `scripts/check_output.py` changes what reviewers approved. Bump `VERSION` and note it in `CHANGELOG.md`.
