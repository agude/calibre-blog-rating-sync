from unittest.mock import MagicMock

from bulk_link import (
    MatchCandidate,
    ReviewMatch,
    _BulkMatchModel,
    _deselect_duplicate_selections,
    _find_conflict_rows,
)
from qt.core import Qt

_EDIT_ROLE = Qt.ItemDataRole.EditRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(calibre_id, score=0.9):
    return MatchCandidate(
        calibre_id=calibre_id,
        calibre_title=f"Title {calibre_id}",
        calibre_authors="Author",
        score=score,
    )


def _match(url, candidates, selected_index=0):
    return ReviewMatch(
        blog_title="Title",
        blog_authors="Author",
        blog_rating=None,
        blog_url=url,
        candidates=candidates,
        selected_index=selected_index,
    )


def _model(rows):
    return _BulkMatchModel(rows)


def _index(model, row):
    """Return a mock index for COL_CALIBRE_MATCH at the given row."""
    idx = MagicMock()
    idx.row.return_value = row
    idx.column.return_value = _BulkMatchModel.COL_CALIBRE_MATCH
    return idx


# ---------------------------------------------------------------------------
# _deselect_duplicate_selections
# ---------------------------------------------------------------------------

def test_deselect_keeps_best_resets_weaker_without_dropping_rows():
    # Both rows auto-selected book 1; only the higher score keeps it.
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(1, 0.6)], selected_index=1),
    ]
    _deselect_duplicate_selections(matches)
    assert len(matches) == 2
    assert matches[0].selected_index == 1
    assert matches[1].selected_index == 0


def test_deselect_keeps_both_when_different_books():
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(2, 0.8)], selected_index=1),
    ]
    _deselect_duplicate_selections(matches)
    assert matches[0].selected_index == 1
    assert matches[1].selected_index == 1


def test_deselect_three_rows_same_book_keeps_only_best():
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(1, 0.7)], selected_index=1),
        _match("url_c", [_candidate(1, 0.5)], selected_index=1),
    ]
    _deselect_duplicate_selections(matches)
    assert [m.selected_index for m in matches] == [1, 0, 0]


def test_deselect_tie_keeps_exactly_one():
    matches = [
        _match("url_a", [_candidate(1, 0.8)], selected_index=1),
        _match("url_b", [_candidate(1, 0.8)], selected_index=1),
    ]
    _deselect_duplicate_selections(matches)
    assert sorted(m.selected_index for m in matches) == [0, 1]


def test_deselect_ignores_skip_rows():
    # Row 0 is Skip; row 1's selection of book 1 is unaffected.
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=0),
        _match("url_b", [_candidate(1, 0.6)], selected_index=1),
    ]
    _deselect_duplicate_selections(matches)
    assert matches[0].selected_index == 0
    assert matches[1].selected_index == 1


def test_deselect_uses_selected_candidate_not_top():
    # Row 1 selected its second candidate (book 2); no conflict with row 0.
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(1, 0.8), _candidate(2, 0.7)], selected_index=2),
    ]
    _deselect_duplicate_selections(matches)
    assert matches[0].selected_index == 1
    assert matches[1].selected_index == 2


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
    assert data[0].selected_index == 0


def test_setdata_clears_all_conflicts_including_incoming_row():
    # Picking a book already selected in two other rows must reset all three to Skip.
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),  # row 0: picking book 1
        _match("url_b", [_candidate(1)], selected_index=1),  # row 1: conflict
        _match("url_c", [_candidate(1)], selected_index=1),  # row 2: conflict
    ]
    m = _model(data)
    m.setData(_index(m, 0), 1, _EDIT_ROLE)
    assert data[0].selected_index == 0
    assert data[1].selected_index == 0
    assert data[2].selected_index == 0


def test_setdata_writes_value_when_no_conflict():
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),
        _match("url_b", [_candidate(2)], selected_index=1),
    ]
    m = _model(data)
    result = m.setData(_index(m, 0), 1, _EDIT_ROLE)
    assert result is True
    assert data[0].selected_index == 1


def test_setdata_skip_selection_always_writes():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
    ]
    m = _model(data)
    result = m.setData(_index(m, 0), 0, _EDIT_ROLE)
    assert result is True
    assert data[0].selected_index == 0
