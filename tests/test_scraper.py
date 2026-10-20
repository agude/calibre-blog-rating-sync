from calibre_plugins.blog_rating_sync.scraper import (
    ReviewPage,
    _normalize_rating,
    extract_rating,
    normalize_url,
    parse_html,
    parse_review_page,
)

URL = "https://alexgude.com/books/hyperion/"

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


def test_parse_html_jsonld_blocks():
    blocks = parse_html(SAMPLE_HTML).jsonld_blocks
    assert len(blocks) == 1
    assert blocks[0]["@type"] == "Review"


def test_parse_html_jsonld_blocks_skips_malformed():
    html = """
    <script type="application/ld+json">{not valid json}</script>
    <script type="application/ld+json">{"@type": "Review"}</script>
    """
    blocks = parse_html(html).jsonld_blocks
    assert len(blocks) == 1
    assert blocks[0]["@type"] == "Review"


def test_extract_rating():
    assert extract_rating(SAMPLE_HTML) == 4


def test_extract_rating_missing():
    assert extract_rating("<html><body>no json-ld</body></html>") is None


def test_extract_rating_preserves_half_stars():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {"@type": "Rating", "ratingValue": "4.5"}
    }</script>"""
    assert extract_rating(html) == 4.5


def test_extract_rating_rounds_to_nearest_half_star():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {"@type": "Rating", "ratingValue": "4.2"}
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


def test_parse_review_page_book_info():
    page = parse_review_page(URL, SAMPLE_HTML)
    assert page.title == "Hyperion"
    assert page.authors == ["Dan Simmons"]


def test_parse_review_page_multiple_authors():
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
    page = parse_review_page(URL, html)
    assert page.title == "Good Omens"
    assert page.authors == ["Terry Pratchett", "Neil Gaiman"]


def test_parse_review_page_missing_book_info():
    page = parse_review_page(URL, "<html></html>")
    assert page.title is None
    assert page.authors is None


def test_parse_review_page_canonical_url():
    page = parse_review_page(URL, SAMPLE_HTML)
    assert page.canonical_url == "https://alexgude.com/books/hyperion/"


def test_parse_review_page_canonical_url_missing():
    page = parse_review_page(URL, "<html><head></head></html>")
    assert page.canonical_url is None


def test_parse_review_page_full():
    page = parse_review_page(URL, SAMPLE_HTML)
    assert page == ReviewPage(
        url=URL,
        canonical_url="https://alexgude.com/books/hyperion/",
        is_outdated=False,
        title="Hyperion",
        authors=["Dan Simmons"],
        rating=4,
    )


def test_parse_review_page_outdated_when_canonical_differs():
    html = '<link rel="canonical" href="https://alexgude.com/books/hyperion-2/">'
    page = parse_review_page(URL, html)
    assert page.canonical_url == "https://alexgude.com/books/hyperion-2/"
    assert page.is_outdated is True


def test_parse_review_page_not_outdated_when_only_trailing_slash_differs():
    page = parse_review_page("https://alexgude.com/books/hyperion", SAMPLE_HTML)
    assert page.canonical_url == "https://alexgude.com/books/hyperion/"
    assert page.is_outdated is False


def test_parse_review_page_without_review():
    page = parse_review_page(URL, "<html><body>no review</body></html>")
    assert page == ReviewPage(
        url=URL,
        canonical_url=None,
        is_outdated=False,
        title=None,
        authors=None,
        rating=None,
    )


def test_normalize_url_strips_trailing_slashes():
    assert normalize_url("https://alexgude.com/books/hyperion/") == (
        "https://alexgude.com/books/hyperion"
    )
    assert normalize_url("https://alexgude.com/books/hyperion//") == (
        "https://alexgude.com/books/hyperion"
    )
    assert normalize_url("https://alexgude.com/books/hyperion") == (
        "https://alexgude.com/books/hyperion"
    )


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


# ---------------------------------------------------------------------------
# Malformed / non-canonical JSON-LD shapes must not crash extraction
# ---------------------------------------------------------------------------


def test_extract_rating_top_level_array():
    html = """<script type="application/ld+json">[
      {"@type": "WebPage", "name": "page"},
      {"@type": "Review", "reviewRating": {"ratingValue": "4"}}
    ]</script>"""
    assert extract_rating(html) == 4


def test_extract_rating_type_list():
    html = """<script type="application/ld+json">{
      "@type": ["Review", "CreativeWork"],
      "reviewRating": {"ratingValue": "4"}
    }</script>"""
    assert extract_rating(html) == 4


def test_extract_rating_scalar_block_ignored():
    html = """<script type="application/ld+json">"just a string"</script>"""
    assert extract_rating(html) is None


def test_normalize_rating_non_numeric_best_rating():
    assert _normalize_rating({"ratingValue": "4", "bestRating": "five"}) is None


def test_normalize_rating_non_dict():
    assert _normalize_rating("4 stars") is None


def test_parse_review_page_string_author():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": {"@type": "Book", "name": "Dune", "author": "Frank Herbert"}
    }</script>"""
    page = parse_review_page(URL, html)
    assert (page.title, page.authors) == ("Dune", ["Frank Herbert"])


def test_parse_review_page_mixed_author_list():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": {
        "@type": "Book",
        "name": "Good Omens",
        "author": ["Terry Pratchett", {"@type": "Person", "name": "Neil Gaiman"}]
      }
    }</script>"""
    page = parse_review_page(URL, html)
    assert (page.title, page.authors) == ("Good Omens", ["Terry Pratchett", "Neil Gaiman"])


def test_parse_review_page_item_reviewed_string():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": "Dune"
    }</script>"""
    page = parse_review_page(URL, html)
    assert (page.title, page.authors) == (None, None)


def test_parse_review_page_no_author():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": {"@type": "Book", "name": "Anonymous Work"}
    }</script>"""
    page = parse_review_page(URL, html)
    assert (page.title, page.authors) == ("Anonymous Work", [])


def test_parse_review_page_nameless_author_object():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": {
        "@type": "Book",
        "name": "Anonymous Work",
        "author": {"@type": "Person"}
      }
    }</script>"""
    page = parse_review_page(URL, html)
    assert (page.title, page.authors) == ("Anonymous Work", [])


def test_parse_review_page_whitespace_author_dropped():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "itemReviewed": {
        "@type": "Book",
        "name": "Good Omens",
        "author": [
          "   ",
          {"@type": "Person", "name": ""},
          {"@type": "Person", "name": "  Neil Gaiman  "}
        ]
      }
    }</script>"""
    page = parse_review_page(URL, html)
    assert (page.title, page.authors) == ("Good Omens", ["Neil Gaiman"])


def test_normalize_rating_rejects_nan():
    assert _normalize_rating({"ratingValue": "NaN"}) is None


def test_normalize_rating_rejects_inf():
    assert _normalize_rating({"ratingValue": "inf"}) is None


def test_normalize_rating_rejects_negative_inf():
    assert _normalize_rating({"ratingValue": "-inf"}) is None


def test_normalize_rating_rejects_non_finite_best_rating():
    assert _normalize_rating({"ratingValue": "4", "bestRating": "inf", "worstRating": "1"}) is None
    assert _normalize_rating({"ratingValue": "4", "bestRating": "5", "worstRating": "-inf"}) is None
    assert _normalize_rating({"ratingValue": "4", "bestRating": "nan", "worstRating": "1"}) is None


def test_extract_rating_nan_literal_in_json():
    html = """<script type="application/ld+json">{
      "@type": "Review",
      "reviewRating": {"@type": "Rating", "ratingValue": NaN}
    }</script>"""
    assert extract_rating(html) is None


def test_parse_html_jsonld_blocks_survives_deep_nesting():
    html = '<script type="application/ld+json">' + "[" * 10000 + "]" * 10000 + "</script>"
    assert isinstance(parse_html(html).jsonld_blocks, list)


def test_normalize_rating_rejects_huge_integer():
    assert _normalize_rating({"ratingValue": 10**400}) is None
    html = (
        '<script type="application/ld+json">{"@type": "Review", "reviewRating": '
        f'{{"ratingValue": {"9" * 400}}}}}</script>'
    )
    assert extract_rating(html) is None
