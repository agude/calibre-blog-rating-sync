import json

from calibre_plugins.blog_rating_sync.matching import (
    MatchCandidate,
    MatchStats,
    ReviewMatch,
    build_review_matches,
    deselect_duplicate_selections,
    find_conflict_rows,
    selected_links,
)
from calibre_plugins.blog_rating_sync.scraper import match_score

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


def _review_page(title, authors=(), rating="4", canonical_url=None):
    """Return a review page with JSON-LD. A title of None leaves the book unnamed."""
    item = {"@type": "Book", "author": [{"@type": "Person", "name": name} for name in authors]}
    if title is not None:
        item["name"] = title
    review = {
        "@type": "Review",
        "reviewRating": {
            "@type": "Rating",
            "ratingValue": rating,
            "bestRating": "5",
            "worstRating": "1",
        },
        "itemReviewed": item,
    }
    canonical = f'<link rel="canonical" href="{canonical_url}">' if canonical_url else ""
    script = f'<script type="application/ld+json">{json.dumps(review)}</script>'
    return f"<html><head>{canonical}{script}</head><body></body></html>"


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


# ---------------------------------------------------------------------------
# build_review_matches
# ---------------------------------------------------------------------------


def test_build_skips_outdated_pages():
    calibre_books = {1: ("Hyperion", ["Dan Simmons"])}
    fetch_results = [
        (
            "https://alexgude.com/books/hyperion-old/",
            _review_page(
                "Hyperion",
                ["Dan Simmons"],
                canonical_url="https://alexgude.com/books/hyperion/",
            ),
            None,
        ),
        ("https://alexgude.com/books/hyperion/", _review_page("Hyperion", ["Dan Simmons"]), None),
    ]
    matches, stats = build_review_matches(fetch_results, calibre_books)
    assert stats == MatchStats(outdated=1, errors=0, no_candidates=0)
    assert [m.blog_url for m in matches] == ["https://alexgude.com/books/hyperion/"]


def test_build_counts_fetch_errors_and_missing_titles():
    calibre_books = {1: ("Hyperion", ["Dan Simmons"])}
    fetch_results = [
        ("https://alexgude.com/books/timeout/", None, "timed out"),
        ("https://alexgude.com/books/no-review/", "<html><body>none</body></html>", None),
        ("https://alexgude.com/books/no-name/", _review_page(None, ["Dan Simmons"]), None),
        ("https://alexgude.com/books/hyperion/", _review_page("Hyperion", ["Dan Simmons"]), None),
    ]
    matches, stats = build_review_matches(fetch_results, calibre_books)
    assert stats == MatchStats(outdated=0, errors=3, no_candidates=0)
    assert [m.blog_title for m in matches] == ["Hyperion"]


def test_build_counts_reviews_without_candidates():
    calibre_books = {1: ("Hyperion", ["Dan Simmons"])}
    fetch_results = [
        (
            "https://alexgude.com/books/blindsight/",
            _review_page("Blindsight", ["Peter Watts"]),
            None,
        ),
        ("https://alexgude.com/books/hyperion/", _review_page("Hyperion", ["Dan Simmons"]), None),
    ]
    matches, stats = build_review_matches(fetch_results, calibre_books)
    assert stats == MatchStats(outdated=0, errors=0, no_candidates=1)
    assert [m.blog_title for m in matches] == ["Hyperion"]


def test_build_auto_selects_at_threshold(monkeypatch):
    calibre_books = {1: ("Hyperion", [])}
    fetch_results = [
        ("https://alexgude.com/books/hyperion-cantos/", _review_page("Hyperion Cantos"), None),
    ]
    score = match_score("Hyperion Cantos", [], "Hyperion", [])

    monkeypatch.setattr("calibre_plugins.blog_rating_sync.matching.AUTO_SELECT_THRESHOLD", score)
    matches, _ = build_review_matches(fetch_results, calibre_books)
    assert matches[0].candidates[0].score == score
    assert matches[0].selected_index == 1

    monkeypatch.setattr(
        "calibre_plugins.blog_rating_sync.matching.AUTO_SELECT_THRESHOLD", score + 0.01
    )
    matches, _ = build_review_matches(fetch_results, calibre_books)
    assert matches[0].selected_index == 0


def test_build_sorts_by_best_score():
    calibre_books = {1: ("Hyperion", []), 2: ("Dune", [])}
    fetch_results = [
        ("https://alexgude.com/books/hyperion-cantos/", _review_page("Hyperion Cantos"), None),
        ("https://alexgude.com/books/dune-period/", _review_page("Dune."), None),
        ("https://alexgude.com/books/hyperion/", _review_page("Hyperion"), None),
    ]
    matches, _ = build_review_matches(fetch_results, calibre_books)
    assert [m.blog_title for m in matches] == ["Hyperion", "Dune.", "Hyperion Cantos"]


def test_build_deselects_duplicate_books():
    calibre_books = {1: ("Hyperion", [])}
    # Both reviews auto-select book 1. The weaker review comes first in fetch
    # order, so the keep-the-best rule (not fetch order) decides the winner.
    fetch_results = [
        ("https://alexgude.com/books/hyperion-period/", _review_page("Hyperion."), None),
        ("https://alexgude.com/books/hyperion/", _review_page("Hyperion"), None),
    ]
    matches, _ = build_review_matches(fetch_results, calibre_books)
    assert [(m.blog_title, m.selected_index) for m in matches] == [
        ("Hyperion", 1),
        ("Hyperion.", 0),
    ]


def test_build_caps_candidates_at_top_n():
    calibre_books = {
        1: ("Hyperion", []),
        2: ("Hyperion 2", []),
        3: ("Hyperion Two", []),
        4: ("Hyperion Cantos", []),
        5: ("Hyperion Cantos 2", []),
        6: ("Hyperion Cantos Two", []),
        7: ("Hyperion Cantos Three", []),
    }
    fetch_results = [("https://alexgude.com/books/hyperion/", _review_page("Hyperion"), None)]
    matches, _ = build_review_matches(fetch_results, calibre_books)
    assert [c.calibre_id for c in matches[0].candidates] == [1, 2, 3, 4, 5]
    assert matches[0].selected_index == 1


# ---------------------------------------------------------------------------
# selected_links
# ---------------------------------------------------------------------------


def test_selected_links_skips_unselected_rows():
    matches = [
        ReviewMatch("A", "", 4, "url_a", [_candidate(1)], selected_index=1),
        ReviewMatch("B", "", None, "url_b", [_candidate(2)], selected_index=0),
        ReviewMatch("C", "", 3.5, "url_c", [_candidate(3), _candidate(4)], selected_index=2),
    ]
    assert selected_links(matches) == [(1, "url_a", 4), (4, "url_c", 3.5)]
