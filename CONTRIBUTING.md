# Contributing

Thanks for helping!

We welcome all kinds of contributions:

- Bug fixes
- Documentation improvements
- New features
- Refactoring & tidying


# Contributing to AI-Horde-Worker

## Code Quality Tools

* [pre-commit](https://pre-commit.com/)
  - Creates virtual environments for formatting and linting tools
  - Run `pre-commit run --all-files` or see `.pre-commit-config.yaml` for more info.
* [black](https://github.com/psf/black)
  - Whitespace formatter
* [ruff](https://github.com/astral-sh/ruff)
  - Linting rules from a wide variety of selectable rule sets
  - See `pyproject.toml` for the rules used.
  - See all rules (but not necessarily used in the project) availible in rust [here](https://beta.ruff.rs/docs/rules/).

## Things to know

  * logstats.py is a stand-alone script that has no interaction with the main horde_scribe_bridge.py.
