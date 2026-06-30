from sync import apply_fetched_ratings, collect_linked_books

REVIEW_HTML = """<script type="application/ld+json">{
  "@type": "Review",
  "reviewRating": {"@type": "Rating", "ratingValue": "5"}
}</script>"""

REVIEW_HTML_RATING_3 = """<script type="application/ld+json">{
  "@type": "Review",
  "reviewRating": {"@type": "Rating", "ratingValue": "3"}
}</script>"""


class FakeDb:
    def __init__(self, books):
        self._books = books

    def all_book_ids(self):
        return list(self._books.keys())

    def field_for(self, field, book_id):
        return self._books.get(book_id, {}).get(field)

    def set_field(self, field, updates):
        for book_id, value in updates.items():
            if book_id in self._books:
                self._books[book_id][field] = value


def test_collect_linked_books():
    db = FakeDb({
        1: {"title": "Hyperion", "#blog_url": "https://example.com/hyperion/"},
        2: {"title": "Blindsight", "#blog_url": None},
        3: {"title": "Accelerando", "#blog_url": "https://example.com/accelerando/"},
    })
    linked = collect_linked_books(db, "#blog_url")
    assert len(linked) == 2
    assert linked[1] == ("Hyperion", "https://example.com/hyperion/")
    assert linked[3] == ("Accelerando", "https://example.com/accelerando/")


def test_apply_updates_rating():
    db = FakeDb({
        1: {"title": "Hyperion", "rating": 6},
    })
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", REVIEW_HTML, None)]

    updated, skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(updated) == 1
    assert updated[0] == ("Hyperion", 3, 5)
    assert db._books[1]["rating"] == 10


def test_apply_skips_unchanged():
    db = FakeDb({
        1: {"title": "Hyperion", "rating": 10},
    })
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", REVIEW_HTML, None)]

    updated, skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(updated) == 0
    assert len(skipped) == 1


def test_apply_reports_fetch_error():
    db = FakeDb({
        1: {"title": "Hyperion", "rating": 6},
    })
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", None, "404 Not Found")]

    updated, skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(errors) == 1
    assert errors[0] == ("Hyperion", "404 Not Found")


def test_apply_reports_missing_jsonld():
    db = FakeDb({
        1: {"title": "Hyperion", "rating": 6},
    })
    linked = {1: ("Hyperion", "https://example.com/hyperion/")}
    fetch_results = [("https://example.com/hyperion/", "<html></html>", None)]

    updated, skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(errors) == 1
    assert "No rating" in errors[0][1]


def test_apply_multiple_books():
    db = FakeDb({
        1: {"title": "Hyperion", "rating": 6},
        2: {"title": "Accelerando", "rating": 4},
    })
    linked = {
        1: ("Hyperion", "https://example.com/hyperion/"),
        2: ("Accelerando", "https://example.com/accelerando/"),
    }
    fetch_results = [
        ("https://example.com/hyperion/", REVIEW_HTML, None),
        ("https://example.com/accelerando/", REVIEW_HTML_RATING_3, None),
    ]

    updated, skipped, errors = apply_fetched_ratings(db, linked, fetch_results)

    assert len(updated) == 2
    assert db._books[1]["rating"] == 10
    assert db._books[2]["rating"] == 6
