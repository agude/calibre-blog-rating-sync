from calibre_plugins.blog_rating_sync.bulk_link import _BulkMatchModel
from calibre_plugins.blog_rating_sync.matching import MatchCandidate, ReviewMatch
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


# ---------------------------------------------------------------------------
# _BulkMatchModel.setData
# ---------------------------------------------------------------------------


def test_setdata_rejects_string_value():
    # The base-class setModelData bug passed a str; setData must reject it.
    data = [_match("url_a", [_candidate(1)], selected_index=0)]
    m = _model(data)
    idx = m.index(0, _BulkMatchModel.COL_CALIBRE_MATCH)
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
    m.setData(m.index(0, _BulkMatchModel.COL_CALIBRE_MATCH), 1, _EDIT_ROLE)
    assert data[0].selected_index == 0
    assert data[1].selected_index == 0
    assert data[2].selected_index == 0


def test_setdata_writes_value_when_no_conflict():
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),
        _match("url_b", [_candidate(2)], selected_index=1),
    ]
    m = _model(data)
    result = m.setData(m.index(0, _BulkMatchModel.COL_CALIBRE_MATCH), 1, _EDIT_ROLE)
    assert result is True
    assert data[0].selected_index == 1


def test_setdata_skip_selection_always_writes():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
    ]
    m = _model(data)
    result = m.setData(m.index(0, _BulkMatchModel.COL_CALIBRE_MATCH), 0, _EDIT_ROLE)
    assert result is True
    assert data[0].selected_index == 0
