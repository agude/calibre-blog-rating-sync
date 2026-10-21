from calibre_plugins.blog_rating_sync.sync import (
    apply_fetched_ratings,
    apply_links,
    collect_linked_books,
    format_sync_report,
    to_calibre_rating,
    to_stars,
    unique_urls,
)

REVIEW_HTML = """<script type="application/ld+json">{
  "@type": "Review",
  "reviewRating": {"@type": "Rating", "ratingValue": "5"}
}</script>"""

REVIEW_HTML_RATING_3 = """<script type="application/ld+json">{
  "@type": "Review",
  "reviewRating": {"@type": "Rating", "ratingValue": "3"}
}</script>"""

REVIEW_HTML_RATING_3_5 = """<script type="application/ld+json">{
  "@type": "Review",
  "reviewRating": {"@type": "Rating", "ratingValue": "3.5"}
}</script>"""


class FakeDb:
    def __init__(self, books):
        self._books = books
        self.set_field_calls = []

    def all_book_ids(self):
        return list(self._books.keys())

    def field_for(self, field, book_id):
        return self._books.get(book_id, {}).get(field)

    def set_field(self, field, updates):
        self.set_field_calls.append((field, dict(updates)))
        for book_id, value in updates.items():
            if book_id in self._books:
                self._books[book_id][field] = value


def test_collect_linked_books():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "#blog_url": "https://example.com/hyperion/"},
            2: {"title": "Blindsight", "#blog_url": None},
            3: {"title": "Accelerando", "#blog_url": "https://example.com/accelerando/"},
        }
    )
    linked = collect_linked_books(db, "#blog_url")
    assert len(linked) == 2
    assert linked[1] == ("Hyperion", "https://example.com/hyperion/")
    assert linked[3] == ("Accelerando", "https://example.com/accelerando/")


def test_collect_linked_books_limited_to_given_ids():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "#blog_url": "https://example.com/hyperion/"},
            2: {"title": "Blindsight", "#blog_url": None},
            3: {"title": "Accelerando", "#blog_url": "https://example.com/accelerando/"},
            4: {"title": "Permutation City", "#blog_url": None},
        }
    )
    linked = collect_linked_books(db, "#blog_url", book_ids=[1, 2])

    assert linked == {1: ("Hyperion", "https://example.com/hyperion/")}


def test_collect_linked_books_keeps_given_order():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "#blog_url": "https://example.com/hyperion/"},
            2: {"title": "Blindsight", "#blog_url": None},
            3: {"title": "Accelerando", "#blog_url": "https://example.com/accelerando/"},
        }
    )
    linked = collect_linked_books(db, "#blog_url", book_ids=[3, 1])

    assert list(linked) == [3, 1]


def test_apply_updates_rating():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 6},
        }
    )
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", REVIEW_HTML, None)]

    updated, _skipped, _errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(updated) == 1
    assert updated[0] == ("Hyperion", 3, 5)
    assert db._books[1]["rating"] == 10


def test_apply_half_star_rating():
    # Calibre stores half stars as odd values on its 0-10 scale.
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 5},
        }
    )
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", REVIEW_HTML_RATING_3_5, None)]

    updated, _skipped, _errors = apply_fetched_ratings(db, linked, fetch_results)

    assert updated[0] == ("Hyperion", 2.5, 3.5)
    assert db._books[1]["rating"] == 7
    assert isinstance(db._books[1]["rating"], int)


def test_apply_skips_unchanged():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 10},
        }
    )
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", REVIEW_HTML, None)]

    updated, skipped, _errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(updated) == 0
    assert len(skipped) == 1


def test_apply_reports_fetch_error():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 6},
        }
    )
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", None, "404 Not Found")]

    _updated, _skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(errors) == 1
    assert errors[0] == ("Hyperion", "404 Not Found")


def test_apply_reports_missing_jsonld():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 6},
        }
    )
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", "<html></html>", None)]

    _updated, _skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(errors) == 1
    assert "No rating" in errors[0][1]


def test_apply_multiple_books():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 6},
            2: {"title": "Accelerando", "rating": 4},
        }
    )
    linked = {
        1: ("Hyperion", "https://example.com/hyperion/"),
        2: ("Accelerando", "https://example.com/accelerando/"),
    }
    fetch_results = [
        ("https://example.com/hyperion/", REVIEW_HTML, None),
        ("https://example.com/accelerando/", REVIEW_HTML_RATING_3, None),
    ]

    updated, _skipped, _errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(updated) == 2
    assert db._books[1]["rating"] == 10
    assert db._books[2]["rating"] == 6


def test_to_calibre_rating_half_stars():
    assert to_calibre_rating(0.5) == 1
    assert to_calibre_rating(3.5) == 7
    assert to_calibre_rating(4) == 8
    assert to_calibre_rating(5) == 10


def test_to_stars_whole_and_half():
    assert to_stars(7) == 3.5
    assert isinstance(to_stars(7), float)
    assert to_stars(6) == 3
    assert isinstance(to_stars(6), int)


def test_apply_writes_ratings_in_one_call():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 6},
            2: {"title": "Accelerando", "rating": 4},
        }
    )
    linked = {
        1: ("Hyperion", "https://example.com/hyperion/"),
        2: ("Accelerando", "https://example.com/accelerando/"),
    }
    fetch_results = [
        ("https://example.com/hyperion/", REVIEW_HTML, None),
        ("https://example.com/accelerando/", REVIEW_HTML_RATING_3, None),
    ]

    apply_fetched_ratings(db, linked, fetch_results)

    assert db.set_field_calls == [("rating", {1: 10, 2: 6})]


def test_apply_makes_no_write_when_nothing_changed():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 10},
        }
    )
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", REVIEW_HTML, None)]

    apply_fetched_ratings(db, linked, fetch_results)

    assert db.set_field_calls == []


def test_apply_links_writes_urls_and_ratings_in_two_calls():
    db = FakeDb(
        {
            1: {"title": "Hyperion"},
            2: {"title": "Accelerando"},
        }
    )
    links = [
        (1, "https://example.com/hyperion/", 2.5),
        (2, "https://example.com/accelerando/", 3.5),
    ]

    apply_links(db, "#blog_url", links)

    assert db.set_field_calls == [
        (
            "#blog_url",
            {1: "https://example.com/hyperion/", 2: "https://example.com/accelerando/"},
        ),
        ("rating", {1: 5, 2: 7}),
    ]
    assert db._books[1]["#blog_url"] == "https://example.com/hyperion/"
    assert db._books[2]["rating"] == 7


def test_apply_links_skips_none_ratings():
    db = FakeDb(
        {
            1: {"title": "Hyperion", "rating": 6},
            2: {"title": "Accelerando"},
        }
    )
    links = [
        (1, "https://example.com/hyperion/", None),
        (2, "https://example.com/accelerando/", 4),
    ]

    apply_links(db, "#blog_url", links)

    assert db.set_field_calls == [
        (
            "#blog_url",
            {1: "https://example.com/hyperion/", 2: "https://example.com/accelerando/"},
        ),
        ("rating", {2: 8}),
    ]
    assert db._books[1]["rating"] == 6

    unrated_db = FakeDb({1: {"title": "Hyperion"}})
    apply_links(unrated_db, "#blog_url", [(1, "https://example.com/hyperion/", None)])

    assert unrated_db.set_field_calls == [("#blog_url", {1: "https://example.com/hyperion/"})]


def test_apply_links_returns_rating_count():
    db = FakeDb(
        {
            1: {"title": "Hyperion"},
            2: {"title": "Blindsight"},
            3: {"title": "Accelerando"},
        }
    )
    links = [
        (1, "https://example.com/hyperion/", 5),
        (2, "https://example.com/blindsight/", None),
        (3, "https://example.com/accelerando/", 3.5),
    ]

    assert apply_links(db, "#blog_url", links) == 2


def test_unique_urls_keeps_first_seen_order():
    linked = {
        1: ("Hyperion", "https://example.com/hyperion/"),
        2: ("Blindsight", "https://example.com/blindsight/"),
        3: ("Hyperion (second copy)", "https://example.com/hyperion/"),
        4: ("Accelerando", "https://example.com/accelerando/"),
    }

    assert unique_urls(linked) == [
        "https://example.com/hyperion/",
        "https://example.com/blindsight/",
        "https://example.com/accelerando/",
    ]


def test_format_sync_report_updated_and_errors():
    text = format_sync_report(
        [("Hyperion", 3, 5), ("Accelerando", 2.5, 3.5)],
        [],
        [("Blindsight", "404 Not Found")],
    )

    assert text == (
        "Updated 2 rating(s):\n"
        "  Hyperion: 3 → 5\n"
        "  Accelerando: 2.5 → 3.5\n"
        "\n"
        "Errors (1):\n"
        "  Blindsight: 404 Not Found"
    )


def test_format_sync_report_skipped_only():
    # Unchanged ratings count as up to date, so the closing line follows.
    text = format_sync_report([], ["Hyperion", "Accelerando"], [])

    assert text == ("\nSkipped 2 (rating unchanged).\nAll linked books already up to date.")


def test_format_sync_report_all_up_to_date():
    assert format_sync_report([], [], []) == "All linked books already up to date."


def test_format_sync_report_cancelled():
    text = format_sync_report([("Hyperion", 3, 5)], [], [], was_cancelled=True)

    assert text == (
        "Sync cancelled — showing partial results.\n\nUpdated 1 rating(s):\n  Hyperion: 3 → 5"
    )
    assert format_sync_report([], [], [], was_cancelled=True) == (
        "Sync cancelled — showing partial results.\n"
    )


def test_format_sync_report_counts_unlinked_selection():
    text = format_sync_report([("Hyperion", 3, 5)], [], [], not_linked=2)

    assert text == (
        "Updated 1 rating(s):\n  Hyperion: 3 → 5\n\n2 selected book(s) have no review URL."
    )
    assert format_sync_report([], [], [], not_linked=1) == (
        "All linked books already up to date.\n\n1 selected book(s) have no review URL."
    )
