"""Property-based tests for the scraper, sitemap, and rating conversions."""

import json

from calibre_plugins.blog_rating_sync.scraper import (
    _normalize_rating,
    extract_rating,
    match_score,
    parse_review_page,
)
from calibre_plugins.blog_rating_sync.sitemap import _is_book_page
from calibre_plugins.blog_rating_sync.sync import to_calibre_rating, to_stars
from hypothesis import assume, given, settings
from hypothesis import strategies as st

URL = "https://alexgude.com/books/hyperion/"
HALF_STARS = {n / 2 for n in range(2, 11)}

FINITE_FLOATS = st.floats(allow_nan=False, allow_infinity=False)
JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
)
RATING_OBJECTS = st.fixed_dictionaries(
    {"ratingValue": JSON_VALUES, "bestRating": JSON_VALUES, "worstRating": JSON_VALUES}
)
REVIEW_RATINGS = st.one_of(JSON_VALUES, RATING_OBJECTS)
RATING_FIELDS = st.one_of(
    st.none(),
    st.integers(),
    st.floats(),
    st.integers().map(str),
    st.floats().map(str),
    st.text(),
)
RATING_INPUTS = st.fixed_dictionaries(
    {"ratingValue": RATING_FIELDS, "bestRating": RATING_FIELDS, "worstRating": RATING_FIELDS}
)
# Raw control characters are invalid in URLs; urlparse strips tab and newline (WHATWG).
PATH_SEGMENTS = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs"), blacklist_characters="/?#"),
    min_size=1,
)


def _review(rating):
    return {"@type": "Review", "reviewRating": rating}


REVIEW_BLOCKS = st.one_of(
    REVIEW_RATINGS.map(_review),
    REVIEW_RATINGS.map(lambda rating: [_review(rating)]),
    REVIEW_RATINGS.map(lambda rating: {"@graph": [_review(rating)]}),
)


def _jsonld_page(value):
    """Embed value in a JSON-LD script block.

    json.dumps emits "<" only inside strings, so escaping it keeps a
    "</script>" string from closing the block early.
    """
    payload = json.dumps(value).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'


@settings(derandomize=True)
@given(st.text())
def test_extract_rating_never_raises_on_text(html):
    extract_rating(html)


@settings(derandomize=True)
@given(st.text())
def test_parse_review_page_never_raises_on_text(html):
    parse_review_page(URL, html)


@settings(derandomize=True)
@given(st.one_of(JSON_VALUES, REVIEW_BLOCKS))
def test_extract_rating_never_raises_on_json_values(value):
    extract_rating(_jsonld_page(value))


@settings(derandomize=True)
@given(RATING_INPUTS)
def test_normalize_rating_is_none_or_a_half_star(review_rating):
    rating = _normalize_rating(review_rating)
    assert rating is None or rating in HALF_STARS


@settings(derandomize=True)
@given(worst=FINITE_FLOATS, best=FINITE_FLOATS, first=FINITE_FLOATS, second=FINITE_FLOATS)
def test_normalize_rating_is_monotonic_in_rating_value(worst, best, first, second):
    assume(best > worst)
    low, high = sorted((first, second))
    low_rating = _normalize_rating({"ratingValue": low, "bestRating": best, "worstRating": worst})
    high_rating = _normalize_rating({"ratingValue": high, "bestRating": best, "worstRating": worst})
    assert low_rating is not None
    assert high_rating is not None
    assert low_rating <= high_rating


@settings(derandomize=True)
@given(st.text(), st.lists(st.text()), st.text(), st.lists(st.text()))
def test_match_score_is_between_zero_and_one(
    blog_title, blog_authors, calibre_title, calibre_authors
):
    score = match_score(blog_title, blog_authors, calibre_title, calibre_authors)
    assert 0.0 <= score <= 1.0


@settings(derandomize=True)
@given(segments=st.lists(PATH_SEGMENTS, min_size=2), trailing_slash=st.booleans())
def test_is_book_page_rejects_nested_slugs(segments, trailing_slash):
    url = "https://alexgude.com/books/" + "/".join(segments) + ("/" if trailing_slash else "")
    assert not _is_book_page(url, "/books/")


@settings(derandomize=True)
@given(st.integers(0, 10))
def test_calibre_rating_round_trips_through_stars(n):
    assert to_calibre_rating(to_stars(n)) == n
