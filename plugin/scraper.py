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
            try:
                self.jsonld_blocks.append(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                pass


def parse_html(html):
    parser = _JsonLdExtractor()
    parser.feed(html)
    return parser


def find_canonical_url(html):
    return parse_html(html).canonical_url


def _iter_review_blocks(blocks):
    """Yield Review-typed objects, unwrapping @graph containers."""
    for block in blocks:
        if block.get("@type") == "Review":
            yield block
        for item in block.get("@graph", []):
            if isinstance(item, dict) and item.get("@type") == "Review":
                yield item


def extract_jsonld_blocks(html):
    return parse_html(html).jsonld_blocks


def _normalize_rating(review_rating):
    """Normalize a rating to a 1-5 scale using bestRating/worstRating."""
    raw = review_rating.get("ratingValue")
    if raw is None:
        return None

    try:
        value = float(raw)
    except (ValueError, TypeError):
        return None

    best = float(review_rating.get("bestRating", TARGET_SCALE))
    worst = float(review_rating.get("worstRating", 1))

    if best <= worst:
        return None

    normalized = (value - worst) / (best - worst) * (TARGET_SCALE - 1) + 1
    clamped = max(1, min(TARGET_SCALE, normalized))
    return int(math.floor(clamped + 0.5))


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
        item = review.get("itemReviewed", {})
        title = item.get("name")
        author_data = item.get("author")
        if author_data is None:
            authors = []
        elif isinstance(author_data, list):
            authors = [a.get("name", "") for a in author_data]
        else:
            authors = [author_data.get("name", "")]
        if title:
            return title, authors
    return None, None


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
        best = max(
            _single_author_similarity(author_a, author_b)
            for author_b in authors_b
        )
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
