# AGENTS.md

`CLAUDE.md` and `GEMINI.md` are symlinks to this file.

## Project Overview

A Calibre plugin that syncs book ratings from blog reviews. It reads
JSON-LD structured data from `alexgude.com` book review pages and writes the
matching rating into the Calibre library.

## Operations

All checks go through `just` (see the project-standards skill for the verb
contract). The pre-commit hook and CI call these same recipes.

```bash
just sync         # install dependencies
just lint         # ruff check + ruff format --check (read-only)
just format       # ruff format + ruff check --fix (mutating)
just test         # pytest
just check        # everything CI runs: lint + test
just build        # produce BlogRatingSync.zip for loading into Calibre
just bump patch   # bump the version in constants.py and pyproject.toml
just hooks-install  # install bin/pre-commit.sh into this clone
```

## Constraints that are not ours to choose

- **Python 3.8.** Calibre ships its own interpreter; the floor is set by the
  oldest Calibre release we support, not by preference. That release is
  Calibre 5.13, which bundles Python 3.8.5. `requires-python` and the CI
  matrix floor both say 3.8 for that reason.
- **No `type-check` recipe.** The plugin imports `calibre.*` and `qt.core`
  at runtime. Neither is installable from PyPI, so mypy cannot resolve them
  outside a Calibre install. The project-standards audit reports the missing
  mypy config; that FAIL is expected here.
- **Version lives in two files.** `plugin/constants.py` holds
  `PLUGIN_VERSION` as a tuple because Calibre requires that form, and
  `pyproject.toml` holds the string. `just bump` keeps them in step. This is
  the one place the single-source-of-version rule cannot apply.

## Layout

- `plugin/` — the plugin itself; this directory is what gets zipped.
- `tests/` — pytest suite. Imports the plugin modules directly, so the
  Calibre-dependent modules are exercised only where they can be stubbed.
- `bin/pre-commit.sh` — the hook; installed by `just hooks-install`.
