import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ALLOWED_SCHEMES = {"http", "https"}
FETCH_TIMEOUT_SECONDS = 15
MAX_SITEMAP_DEPTH = 3
USER_AGENT = "CalibreBlogRatingSync/0.1 (Calibre plugin; +https://github.com)"


def fetch_book_urls(sitemap_url, path_prefix="/books/", _depth=0):
    """Fetch all book review URLs from a sitemap.xml.

    Handles both flat urlset sitemaps and sitemap index files.
    """
    if _depth > MAX_SITEMAP_DEPTH:
        return []

    parsed = urlparse(sitemap_url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed")

    request = Request(sitemap_url, headers={"User-Agent": USER_AGENT})
    response = urlopen(request, timeout=FETCH_TIMEOUT_SECONDS).read()
    root = ET.fromstring(response)

    sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", SITEMAP_NAMESPACE)
    if sub_sitemaps:
        urls = []
        for loc in sub_sitemaps:
            if loc.text:
                urls.extend(fetch_book_urls(loc.text, path_prefix, _depth + 1))
        return urls

    all_urls = [
        loc.text
        for loc in root.findall(".//sm:loc", SITEMAP_NAMESPACE)
        if loc.text
    ]
    return [url for url in all_urls if _is_book_page(url, path_prefix)]


def _is_book_page(url, path_prefix):
    """Match URLs that are direct children of path_prefix, not deeper descendants.

    /books/hyperion/              -> True  (one slug after prefix)
    /books/authors/someone/       -> False (nested subdirectory)
    /books/series/culture/        -> False (nested subdirectory)
    /books/                       -> False (index page, no slug)
    """
    path = urlparse(url).path
    idx = path.find(path_prefix)
    if idx == -1:
        return False
    remainder = path[idx + len(path_prefix):]
    slug = remainder.strip("/")
    return bool(slug) and "/" not in slug
