from calibre_plugins.blog_rating_sync.matching import (
    MatchCandidate,
    ReviewMatch,
    deselect_duplicate_selections,
    find_conflict_rows,
)

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


# ---------------------------------------------------------------------------
# deselect_duplicate_selections
# ---------------------------------------------------------------------------


def test_deselect_keeps_best_resets_weaker_without_dropping_rows():
    # Both rows auto-selected book 1; only the higher score keeps it.
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(1, 0.6)], selected_index=1),
    ]
    deselect_duplicate_selections(matches)
    assert len(matches) == 2
    assert matches[0].selected_index == 1
    assert matches[1].selected_index == 0


def test_deselect_keeps_both_when_different_books():
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(2, 0.8)], selected_index=1),
    ]
    deselect_duplicate_selections(matches)
    assert matches[0].selected_index == 1
    assert matches[1].selected_index == 1


def test_deselect_three_rows_same_book_keeps_only_best():
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(1, 0.7)], selected_index=1),
        _match("url_c", [_candidate(1, 0.5)], selected_index=1),
    ]
    deselect_duplicate_selections(matches)
    assert [m.selected_index for m in matches] == [1, 0, 0]


def test_deselect_tie_keeps_exactly_one():
    matches = [
        _match("url_a", [_candidate(1, 0.8)], selected_index=1),
        _match("url_b", [_candidate(1, 0.8)], selected_index=1),
    ]
    deselect_duplicate_selections(matches)
    assert sorted(m.selected_index for m in matches) == [0, 1]


def test_deselect_ignores_skip_rows():
    # Row 0 is Skip; row 1's selection of book 1 is unaffected.
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=0),
        _match("url_b", [_candidate(1, 0.6)], selected_index=1),
    ]
    deselect_duplicate_selections(matches)
    assert matches[0].selected_index == 0
    assert matches[1].selected_index == 1


def test_deselect_uses_selected_candidate_not_top():
    # Row 1 selected its second candidate (book 2); no conflict with row 0.
    matches = [
        _match("url_a", [_candidate(1, 0.9)], selected_index=1),
        _match("url_b", [_candidate(1, 0.8), _candidate(2, 0.7)], selected_index=2),
    ]
    deselect_duplicate_selections(matches)
    assert matches[0].selected_index == 1
    assert matches[1].selected_index == 2


# ---------------------------------------------------------------------------
# find_conflict_rows
# ---------------------------------------------------------------------------


def test_no_conflicts_when_books_differ():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
        _match("url_b", [_candidate(2)], selected_index=1),
    ]
    assert find_conflict_rows(data, 0, 1) == []


def test_finds_single_conflict():
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),
        _match("url_b", [_candidate(1)], selected_index=1),
    ]
    assert find_conflict_rows(data, 0, 1) == [1]


def test_finds_all_conflicts_not_just_first():
    # Three other rows all have the same book — all must be returned.
    data = [
        _match("url_a", [_candidate(1)], selected_index=1),  # current_row=0
        _match("url_b", [_candidate(1)], selected_index=1),
        _match("url_c", [_candidate(1)], selected_index=1),
        _match("url_d", [_candidate(1)], selected_index=1),
    ]
    assert sorted(find_conflict_rows(data, 0, 1)) == [1, 2, 3]


def test_skip_rows_not_counted_as_conflicts():
    data = [
        _match("url_a", [_candidate(1)], selected_index=0),  # Skip
        _match("url_b", [_candidate(1)], selected_index=1),
    ]
    # Row 0 is Skip (selected_index=0); not a conflict for row 1.
    assert find_conflict_rows(data, 1, 1) == []
