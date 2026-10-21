set shell := ["bash", "-euo", "pipefail", "-c"]

plugin_name := "BlogRatingSync.zip"

# List available recipes
default:
    @just --list

# Build the plugin zip for loading into Calibre
build:
    cd plugin && zip -r ../{{plugin_name}} . -x '*__pycache__*' '*.pyc'

# Install the locked development environment.
sync:
    uv sync --locked

# Regenerate uv.lock after changing dependencies in pyproject.toml.
lock:
    uv lock

# Run the test suite
test *args:
    uv run --locked pytest {{ args }}

# Lint and check formatting
lint:
    uv run --locked ruff check plugin/ tests/
    uv run --locked ruff format --check plugin/ tests/
    uv run --locked actionlint
    uv run --locked zizmor --pedantic --quiet .

# Format code and apply safe lint fixes
format:
    uv run --locked ruff format plugin/ tests/
    uv run --locked ruff check --fix plugin/ tests/

# No type-check: the plugin imports calibre and qt at runtime, neither of
# which is installable from PyPI, so mypy cannot resolve them here.

# Run everything CI runs.
check: lint test

# Install the pre-commit hook into this clone
hooks-install:
    @mkdir -p .git/hooks
    @cp bin/pre-commit.sh .git/hooks/pre-commit
    @chmod +x .git/hooks/pre-commit
    @echo "Pre-commit hook installed."

# Remove build artifacts
clean:
    rm -f {{plugin_name}}

# Bump the version in constants.py, pyproject.toml, and uv.lock: just bump major|minor|patch
bump kind:
    #!/usr/bin/env python3
    import re
    import subprocess
    import sys

    kind = "{{kind}}"
    if kind not in ("major", "minor", "patch"):
        sys.exit(f"usage: just bump major|minor|patch (got {kind!r})")

    with open("plugin/constants.py") as source:
        constants = source.read()
    version_match = re.search(r"PLUGIN_VERSION = \((\d+), (\d+), (\d+)\)", constants)
    if version_match is None:
        sys.exit("PLUGIN_VERSION tuple not found in plugin/constants.py")
    major, minor, patch = map(int, version_match.groups())

    if kind == "major":
        major, minor, patch = major + 1, 0, 0
    elif kind == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1

    constants = re.sub(
        r"PLUGIN_VERSION = \(\d+, \d+, \d+\)",
        f"PLUGIN_VERSION = ({major}, {minor}, {patch})",
        constants,
    )
    with open("plugin/constants.py", "w") as target:
        target.write(constants)

    with open("pyproject.toml") as source:
        pyproject = source.read()
    pyproject = re.sub(
        r'^version = "\d+\.\d+\.\d+"',
        f'version = "{major}.{minor}.{patch}"',
        pyproject,
        count=1,
        flags=re.MULTILINE,
    )
    with open("pyproject.toml", "w") as target:
        target.write(pyproject)

    subprocess.run(["uv", "lock"], check=True)

    print(f"Bumped version to {major}.{minor}.{patch}")
