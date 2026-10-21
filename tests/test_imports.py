import importlib
import importlib.util
from pathlib import Path

import pytest
from calibre_plugins.blog_rating_sync.constants import PLUGIN_VERSION

PLUGIN_INIT_PATH = Path(__file__).resolve().parents[1] / "plugin" / "__init__.py"


@pytest.mark.parametrize(
    "module_name",
    [
        "bulk_link",
        "config",
        "constants",
        "link",
        "matching",
        "network",
        "scraper",
        "sitemap",
        "sync",
        "ui",
    ],
)
def test_module_imports(module_name):
    importlib.import_module(f"calibre_plugins.blog_rating_sync.{module_name}")


def test_plugin_class_loads():
    spec = importlib.util.spec_from_file_location("blog_rating_sync_plugin_init", PLUGIN_INIT_PATH)
    plugin_init = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin_init)

    assert plugin_init.BlogRatingSyncPlugin.version == PLUGIN_VERSION
    assert plugin_init.BlogRatingSyncPlugin.minimum_calibre_version == (5, 13, 0)
