import contextlib
import json
import math
from difflib import SequenceMatcher
from html.parser import HTMLParser

TARGET_SCALE = 5
MATCH_THRESHOLD = 0.5


class _JsonLdExtractor(HTMLParser):
    """Extract JSON-LD blocks and canonical URL in a single parse pass."""

    def __init__(self):
        super().__init__()
        self.jsonld_blocks = []
        self.canonical_url = None
        self._in_jsonld = False
        self._current_data = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "script" and attr_dict.get("type") == "application/ld+json":
            self._in_jsonld = True
            self._current_data = []
        elif tag == "link" and attr_dict.get("rel") == "canonical":
            self.canonical_url = attr_dict.get("href")

    def handle_data(self, data):
        if self._in_jsonld:
            self._current_data.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            raw = "".join(self._current_data)
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                self.jsonld_blocks.append(json.loads(raw))


def parse_html(html):
    parser = _JsonLdExtractor()
    parser.feed(html)
    return parser


def find_canonical_url(html):
    return parse_html(html).canonical_url


def _is_review(item):
    """JSON-LD @type may be a single string or a list of types."""
    declared_type = item.get("@type")
    if isinstance(declared_type, list):
        return "Review" in declared_type
    return declared_type == "Review"


def _iter_review_blocks(blocks):
    """Yield Review-typed objects, unwrapping top-level arrays and @graph containers."""
    for block in blocks:
        items = block if isinstance(block, list) else [block]
        for item in items:
            if not isinstance(item, dict):
                continue
            if _is_review(item):
                yield item
            graph = item.get("@graph")
            if not isinstance(graph, list):
                continue
            for graph_item in graph:
                if isinstance(graph_item, dict) and _is_review(graph_item):
                    yield graph_item


def extract_jsonld_blocks(html):
    return parse_html(html).jsonld_blocks


def _normalize_rating(review_rating):
    """Normalize a rating to the 1-5 scale using bestRating/worstRating.

    Returns a multiple of 0.5 (as int when whole) — Calibre stores half stars.
    """
    if not isinstance(review_rating, dict):
        return None

    raw = review_rating.get("ratingValue")
    if raw is None:
        return None

    try:
        value = float(raw)
        best = float(review_rating.get("bestRating", TARGET_SCALE))
        worst = float(review_rating.get("worstRating", 1))
    except (ValueError, TypeError):
        return None

    if best <= worst:
        return None

    normalized = (value - worst) / (best - worst) * (TARGET_SCALE - 1) + 1
    clamped = max(1.0, min(TARGET_SCALE, normalized))
    # floor(x + 0.5) rounds half up; round() would round half to even.
    half_stars = math.floor(clamped * 2 + 0.5) / 2
    return int(half_stars) if half_stars.is_integer() else half_stars


def extract_rating(html):
    return extract_rating_from_blocks(parse_html(html).jsonld_blocks)


def extract_rating_from_blocks(blocks):
    for review in _iter_review_blocks(blocks):
        review_rating = review.get("reviewRating")
        if not review_rating:
            continue
        rating = _normalize_rating(review_rating)
        if rating is not None:
            return rating
    return None


def extract_book_info(html):
    """Returns (title, authors_list) or (None, None) if not found."""
    return extract_book_info_from_blocks(parse_html(html).jsonld_blocks)


def extract_book_info_from_blocks(blocks):
    """Returns (title, authors_list) or (None, None) if not found."""
    for review in _iter_review_blocks(blocks):
        item = review.get("itemReviewed")
        if not isinstance(item, dict):
            continue
        title = item.get("name")
        if title:
            return title, _author_names(item.get("author"))
    return None, None


def _author_names(author_data):
    """Extract names from schema.org author data: a string, an object, or a list of either."""
    entries = author_data if isinstance(author_data, list) else [author_data]
    names = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict):
            names.append(entry.get("name", ""))
    return names


def _normalize_for_comparison(text):
    return " ".join(text.lower().split())


def _title_similarity(title_a, title_b):
    return SequenceMatcher(
        None,
        _normalize_for_comparison(title_a),
        _normalize_for_comparison(title_b),
    ).ratio()


def _single_author_similarity(author_a, author_b):
    return SequenceMatcher(
        None,
        _normalize_for_comparison(author_a),
        _normalize_for_comparison(author_b),
    ).ratio()


def _author_similarity(authors_a, authors_b):
    """Compare two author lists, handling reordering.

    For each author in the shorter list, find the best match in the longer
    list. Return the average of the best matches.
    """
    if len(authors_a) > len(authors_b):
        authors_a, authors_b = authors_b, authors_a

    total = 0.0
    for author_a in authors_a:
        best = max(_single_author_similarity(author_a, author_b) for author_b in authors_b)
        total += best
    return total / len(authors_a)


def match_score(blog_title, blog_authors, calibre_title, calibre_authors):
    """Score how well a blog review matches a Calibre book.

    Returns a float from 0.0 (no match) to 1.0 (perfect match).
    """
    if not blog_title or not calibre_title:
        return 0.0

    title_sim = _title_similarity(blog_title, calibre_title)
    if title_sim < MATCH_THRESHOLD:
        return 0.0

    if not blog_authors and not calibre_authors:
        return title_sim

    if not blog_authors or not calibre_authors:
        return title_sim * 0.5

    author_sim = _author_similarity(blog_authors, calibre_authors)
    if author_sim < MATCH_THRESHOLD:
        return 0.0

    return (title_sim + author_sim) / 2
