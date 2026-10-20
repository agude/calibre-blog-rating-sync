import re
from pathlib import Path

from calibre_plugins.blog_rating_sync.constants import PLUGIN_VERSION_STRING

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_pyproject_version_matches_plugin_version():
    # tomllib is not available on Python 3.8, so read the version line directly.
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    assert match is not None
    assert match.group(1) == PLUGIN_VERSION_STRING
