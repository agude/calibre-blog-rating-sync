import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))


# ---------------------------------------------------------------------------
# Qt / calibre stubs — installed here so every test file can import plugin
# modules regardless of collection order.
# ---------------------------------------------------------------------------

class _FakeQtBase:
    """Minimal stand-in for QAbstractTableModel and QStyledItemDelegate."""

    def __init__(self):
        self.dataChanged = MagicMock()

    def index(self, row, col):
        index = MagicMock()
        index.row.return_value = row
        index.column.return_value = col
        return index


_QT = MagicMock()
_QT.Qt.ItemDataRole.UserRole = 256
_QT.Qt.ItemDataRole.EditRole = 2
_QT.Qt.ItemDataRole.DisplayRole = 0
_QT.QAbstractTableModel = _FakeQtBase
_QT.QStyledItemDelegate = _FakeQtBase

for _module_name in [
    "qt",
    "qt.core",
    "calibre_plugins",
    "calibre_plugins.blog_rating_sync",
    "calibre_plugins.blog_rating_sync.config",
]:
    sys.modules.setdefault(_module_name, _QT)

# Map the plugin's calibre_plugins imports to the real modules so cross-module
# calls (e.g. sitemap -> network.fetch_bytes) hit real code under test.
import network  # noqa: E402
import scraper  # noqa: E402
import sitemap  # noqa: E402
import sync  # noqa: E402

sys.modules["calibre_plugins.blog_rating_sync.network"] = network
sys.modules["calibre_plugins.blog_rating_sync.scraper"] = scraper
sys.modules["calibre_plugins.blog_rating_sync.sitemap"] = sitemap
sys.modules["calibre_plugins.blog_rating_sync.sync"] = sync
