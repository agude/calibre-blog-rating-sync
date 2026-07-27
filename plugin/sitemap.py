import xml.etree.ElementTree as ET
from urllib.parse import urlparse

try:
    from calibre_plugins.blog_rating_sync.network import fetch_bytes
except ImportError:
    from network import fetch_bytes

SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
MAX_SITEMAP_DEPTH = 3


def fetch_book_urls(sitemap_url, path_prefix="/books/", _depth=0):
    """Fetch all book review URLs from a sitemap.xml.

    Handles both flat urlset sitemaps and sitemap index files.
    """
    if _depth > MAX_SITEMAP_DEPTH:
        return []

    root = ET.fromstring(fetch_bytes(sitemap_url))

    sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", SITEMAP_NAMESPACE)
    if sub_sitemaps:
        urls = []
        for loc in sub_sitemaps:
            if loc.text:
                urls.extend(fetch_book_urls(loc.text, path_prefix, _depth + 1))
        return urls

    all_urls = [loc.text for loc in root.findall(".//sm:loc", SITEMAP_NAMESPACE) if loc.text]
    return [url for url in all_urls if _is_book_page(url, path_prefix)]


def _is_book_page(url, path_prefix):
    """Match URLs that are direct children of path_prefix, not deeper descendants.

    /books/hyperion/              -> True  (one slug after prefix)
    /books/authors/someone/       -> False (nested subdirectory)
    /books/                       -> False (index page, no slug)
    /archive/books/hyperion/      -> False (prefix not at path start)
    """
    path = urlparse(url).path
    if not path.startswith(path_prefix):
        return False
    slug = path[len(path_prefix) :].strip("/")
    return bool(slug) and "/" not in slug
