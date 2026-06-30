from scraper import (
    _normalize_rating,
    extract_book_info,
    extract_jsonld_blocks,
    extract_rating,
    find_canonical_url,
)

SAMPLE_JSONLD = """{
  "@context": "https://schema.org",
  "@type": "Review",
  "reviewRating": {
    "@type": "Rating",
    "ratingValue": "4",
    "bestRating": "5",
    "worstRating": "1"
  },
  "itemReviewed": {
    "@type": "Book",
    "name": "Hyperion",
    "author": {"@type": "Person", "name": "Dan Simmons"},
    "isbn": "978-0-385-24949-2"
  }
}"""

SAMPLE_HTML = f"""<!DOCTYPE html>
<html>
<head>
<link rel="canonical" href="https://alexgude.com/books/hyperion/">
<script type="application/ld+json">{SAMPLE_JSONLD}</script>
</head>
<body><p>Review content</p></body>
</html>"""


def test_extract_jsonld_blocks():
    blocks = extract_jsonld_blocks(SAMPLE_HTML)
    assert len(blocks) == 1
    assert blocks[0]["@type"] == "Review"


def test_extract_jsonld_blocks_skips_malformed():
    html = """
    <script type="application/ld+json">{not valid json}</script>
    <script type="application/ld+json">{"@type": "Review"}</script>
    """
    blocks = extract_jsonld_blocks(html)
    assert len(blocks) == 1
    assert blocks[0]["@type"] == "Review"


def test_extract_rating():
    assert extract_rating(SAMPLE_HTML) == 4


def test_extract_rating_missing():
    assert extract_rating("<html><body>no json-ld</body></html>") is None


def test_extract_rating_fractional_rounds_up():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {"@type": "Rating", "ratingValue": "4.5"}
    }</script>"""
    assert extract_rating(html) == 5


def test_extract_rating_fractional_rounds_down():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {"@type": "Rating", "ratingValue": "4.4"}
    }</script>"""
    assert extract_rating(html) == 4


def test_extract_rating_normalizes_best_rating():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {
        "@type": "Rating",
        "ratingValue": "8",
        "bestRating": "10",
        "worstRating": "1"
      }
    }</script>"""
    assert extract_rating(html) == 4


def test_extract_rating_from_graph():
    html = """<script type="application/ld+json">{
      "@graph": [
        {"@type": "WebPage", "name": "page"},
        {"@type": "Review", "reviewRating": {"ratingValue": "3"}}
      ]
    }</script>"""
    assert extract_rating(html) == 3


def test_normalize_rating_non_numeric():
    assert _normalize_rating({"ratingValue": "excellent"}) is None


def test_normalize_rating_none_value():
    assert _normalize_rating({"ratingValue": None}) is None


def test_normalize_rating_missing_value():
    assert _normalize_rating({}) is None


def test_normalize_rating_equal_best_worst():
    assert _normalize_rating({"ratingValue": "3", "bestRating": "5", "worstRating": "5"}) is None


def test_normalize_rating_clamps_to_range():
    result = _normalize_rating({"ratingValue": "11", "bestRating": "10", "worstRating": "1"})
    assert result == 5


def test_extract_book_info():
    title, authors = extract_book_info(SAMPLE_HTML)
    assert title == "Hyperion"
    assert authors == ["Dan Simmons"]


def test_extract_book_info_multiple_authors():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": {
        "@type": "Book",
        "name": "Good Omens",
        "author": [
          {"@type": "Person", "name": "Terry Pratchett"},
          {"@type": "Person", "name": "Neil Gaiman"}
        ]
      }
    }</script>"""
    title, authors = extract_book_info(html)
    assert title == "Good Omens"
    assert authors == ["Terry Pratchett", "Neil Gaiman"]


def test_extract_book_info_missing():
    title, authors = extract_book_info("<html></html>")
    assert title is None
    assert authors is None


def test_find_canonical_url():
    url = find_canonical_url(SAMPLE_HTML)
    assert url == "https://alexgude.com/books/hyperion/"


def test_find_canonical_url_missing():
    url = find_canonical_url("<html><head></head></html>")
    assert url is None


def test_extract_rating_non_review_jsonld_ignored():
    html = """<script type="application/ld+json">{
      "@type": "WebPage",
      "name": "Some page"
    }</script>
    <script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {"@type": "Rating", "ratingValue": "3"}
    }</script>"""
    assert extract_rating(html) == 3
