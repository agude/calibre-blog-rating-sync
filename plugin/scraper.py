import json
import re
from html.parser import HTMLParser

JSONLD_PATTERN = re.compile(
    r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

MIN_SUBSTRING_TITLE_LENGTH = 4


class _CanonicalFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical_url = None

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        attr_dict = dict(attrs)
        if attr_dict.get("rel") == "canonical":
            self.canonical_url = attr_dict.get("href")


def find_canonical_url(html):
    parser = _CanonicalFinder()
    parser.feed(html)
    return parser.canonical_url


def extract_jsonld_blocks(html):
    return [json.loads(m.group(1)) for m in JSONLD_PATTERN.finditer(html)]


def extract_rating(html):
    for block in extract_jsonld_blocks(html):
        if block.get("@type") != "Review":
            continue
        review_rating = block.get("reviewRating")
        if not review_rating:
            continue
        raw = review_rating.get("ratingValue")
        if raw is not None:
            return round(float(raw))
    return None


def extract_book_info(html):
    """Returns (title, authors_list) or (None, None) if not found."""
    for block in extract_jsonld_blocks(html):
        if block.get("@type") != "Review":
            continue
        item = block.get("itemReviewed", {})
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


def _author_words(authors):
    return {
        w.strip(".,;:")
        for a in authors
        for w in a.lower().split()
        if w.strip(".,;:")
    }


def _title_score(blog_title_lower, calibre_title_lower):
    if blog_title_lower == calibre_title_lower:
        return 3

    shorter = min(len(blog_title_lower), len(calibre_title_lower))
    if shorter < MIN_SUBSTRING_TITLE_LENGTH:
        return 0

    if blog_title_lower in calibre_title_lower or calibre_title_lower in blog_title_lower:
        return 2

    return 0


def match_score(blog_title, blog_authors, calibre_title, calibre_authors):
    """Score how well a blog review matches a Calibre book (0 = no match)."""
    blog_title_lower = blog_title.lower().strip() if blog_title else ""
    calibre_title_lower = calibre_title.lower().strip() if calibre_title else ""

    title_points = _title_score(blog_title_lower, calibre_title_lower)
    if title_points == 0:
        return 0

    blog_words = _author_words(blog_authors)
    calibre_words = _author_words(calibre_authors)

    if not blog_words or not calibre_words:
        return title_points

    overlap = blog_words & calibre_words
    if not overlap:
        return 0

    return title_points + (2 if overlap == blog_words else 1)
