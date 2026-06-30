import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Qt / calibre stubs — must be installed before importing bulk_link
# ---------------------------------------------------------------------------

class _FakeBase:
    """Minimal stand-in for QAbstractTableModel and QStyledItemDelegate."""
    def __init__(self):
        self.dataChanged = MagicMock()

    def index(self, row, col):
        idx = MagicMock()
        idx.row.return_value = row
        idx.column.return_value = col
        return idx


_QT = MagicMock()
_QT.Qt.ItemDataRole.UserRole = 256
_QT.Qt.ItemDataRole.EditRole = 2
_QT.Qt.ItemDataRole.DisplayRole = 0
_QT.QAbstractTableModel = _FakeBase
_QT.QStyledItemDelegate = _FakeBase

for _mod in [
    "qt",
    "qt.core",
    "calibre_plugins",
    "calibre_plugins.blog_rating_sync",
    "calibre_plugins.blog_rating_sync.config",
    "calibre_plugins.blog_rating_sync.network",
    "calibre_plugins.blog_rating_sync.sitemap",
    "calibre_plugins.blog_rating_sync.sync",
]:
    sys.modules.setdefault(_mod, _QT)

import scraper as _scraper_mod
sys.modules["calibre_plugins.blog_rating_sync.scraper"] = _scraper_mod

from bulk_link import _BulkMatchModel, _filter_mutual_best, _find_conflict_rows  # noqa: E402

_EDIT_ROLE = _QT.Qt.ItemDataRole.EditRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(calibre_id, score=0.9):
    return {
        "calibre_id": calibre_id,
        "calibre_title": f"Title {calibre_id}",
        "calibre_authors": "Author",
        "score": score,
    }


def _match(url, candidates, selected_index=0):
    return {
        "blog_title": "Title",
        "blog_authors": "Author",
        "blog_rating": None,
        "blog_url": url,
        "candidates": candidates,
        "selected_index": selected_index,
    }


def _model(rows):
    return _BulkMatchModel(rows)


def _index(model, row):
    """Return a mock index for COL_CALIBRE_MATCH at the given row."""
    idx = MagicMock()
    idx.row.return_value = row
    idx.column.return_value = _BulkMatchModel.COL_CALIBRE_MATCH
    return idx


# ---------------------------------------------------------------------------
# _filter_mutual_best
# ---------------------------------------------------------------------------

def test_filter_keeps_best_claimant_drops_weaker():
    # url_a scores higher against book 1 than url_b does.
    matches = [
        _match("url_a", [_candidate(1, 0.9)]),
        _match("url_b", [_candidate(1, 0.6)]),
    ]
    result = _filter_mutual_best(matches)
    urls = {m["blog_url"] for m in result}
    assert urls == {"url_a"}


def test_filter_keeps_both_when_different_top_books():
    # url_a wins book 1, url_b wins book 2 — both rows survive.
    matches = [
        _match("url_a", [_candidate(1, 0.9)]),
        _match("url_b", [_candidate(2, 0.8)]),
    ]
    result = _filter_mutual_best(matches)
    urls = {m["blog_url"] for m in result}
    assert urls == {"url_a", "url_b"}


def test_filter_three_urls_same_book_keeps_only_best():
    matches = [
        _match("url_a", [_candidate(1, 0.9)]),
        _match("url_b", [_candidate(1, 0.7)]),
        _match("url_c", [_candidate(1, 0.5)]),
    ]
    result = _filter_mutual_best(matches)
    assert len(result) == 1
    assert result[0]["blog_url"] == "url_a"


def test_filter_url_that_wins_multiple_books_appears_once():
    # url_a is top candidate for both books; it should appear only once.
    matches = [
        _match("url_a", [_candidate(1, 0.9), _candidate(2, 0.8)]),
    ]
    result = _filter_mutual_best(matches)
    assert len(result) == 1
    assert result[0]["blog_url"] == "url_a"


# ---------------------------------------------------------------------------
# _find_conflict_rows
# ---------------------------------------------------------------------------

def test_no_conflicts_when_books_differ():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
        _match("url_b", [_candidate(2)], selected_index=1),
    ]
    assert _find_conflict_rows(data, 0, 1) == []


def test_finds_single_conflict():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
        _match("url_b", [_candidate(1)], selected_index=1),
    ]
    assert _find_conflict_rows(data, 0, 1) == [1]


def test_finds_all_conflicts_not_just_first():
    # Three other rows all have the same book — all must be returned.
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),  # current_row=0
        _match("url_b", [_candidate(1)], selected_index=1),
        _match("url_c", [_candidate(1)], selected_index=1),
        _match("url_d", [_candidate(1)], selected_index=1),
    ]
    assert sorted(_find_conflict_rows(data, 0, 1)) == [1, 2, 3]


def test_skip_rows_not_counted_as_conflicts():
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),  # Skip
        _match("url_b", [_candidate(1)], selected_index=1),
    ]
    # Row 0 is Skip (selected_index=0); not a conflict for row 1.
    assert _find_conflict_rows(data, 1, 1) == []


# ---------------------------------------------------------------------------
# _BulkMatchModel.setData
# ---------------------------------------------------------------------------

def test_setdata_rejects_string_value():
    # The base-class setModelData bug passed a str; setData must reject it.
    data = [_match("url_a", [_candidate(1)], selected_index=0)]
    m = _model(data)
    idx = _index(m, 0)
    result = m.setData(idx, "1", _EDIT_ROLE)
    assert result is False
    assert data[0]["selected_index"] == 0


def test_setdata_clears_all_conflicts_including_incoming_row():
    # Picking a book already selected in two other rows must reset all three to Skip.
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),  # row 0: picking book 1
        _match("url_b", [_candidate(1)], selected_index=1),  # row 1: conflict
        _match("url_c", [_candidate(1)], selected_index=1),  # row 2: conflict
    ]
    m = _model(data)
    m.setData(_index(m, 0), 1, _EDIT_ROLE)
    assert data[0]["selected_index"] == 0
    assert data[1]["selected_index"] == 0
    assert data[2]["selected_index"] == 0


def test_setdata_writes_value_when_no_conflict():
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),
        _match("url_b", [_candidate(2)], selected_index=1),
    ]
    m = _model(data)
    result = m.setData(_index(m, 0), 1, _EDIT_ROLE)
    assert result is True
    assert data[0]["selected_index"] == 1


def test_setdata_skip_selection_always_writes():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
    ]
    m = _model(data)
    result = m.setData(_index(m, 0), 0, _EDIT_ROLE)
    assert result is True
    assert data[0]["selected_index"] == 0
