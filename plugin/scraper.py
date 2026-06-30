import json
import re
from html.parser import HTMLParser

JSONLD_PATTERN = re.compile(
    r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


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
    """Extract the book rating from a blog review page's JSON-LD.

    Returns the integer rating (1-5), or None if not found.
    """
    for block in extract_jsonld_blocks(html):
        if block.get("@type") != "Review":
            continue
        review_rating = block.get("reviewRating")
        if not review_rating:
            continue
        raw = review_rating.get("ratingValue")
        if raw is not None:
            return int(raw)
    return None


def extract_book_info(html):
    """Extract book title and authors from a blog review page's JSON-LD.

    Returns (title, authors_list) or (None, None) if not found.
    """
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


def match_score(blog_title, blog_authors, calibre_title, calibre_authors):
    """Score how well a blog review matches a Calibre book (0 = no match)."""
    bt = blog_title.lower().strip() if blog_title else ""
    ct = calibre_title.lower().strip() if calibre_title else ""

    if bt == ct:
        title_score = 3
    elif bt in ct or ct in bt:
        title_score = 2
    else:
        return 0

    blog_words = _author_words(blog_authors)
    cal_words = _author_words(calibre_authors)

    if not blog_words or not cal_words:
        return title_score

    overlap = blog_words & cal_words
    if not overlap:
        return 0

    return title_score + (2 if overlap == blog_words else 1)
