import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from calibre_plugins.blog_rating_sync.network import fetch_bytes

SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
MAX_SITEMAP_DEPTH = 3


def fetch_book_urls(sitemap_url, path_prefix="/books/"):
    """Fetch all book review URLs from a sitemap.xml.

    Handles both flat urlset sitemaps and sitemap index files. Returns
    (urls, failures). urls are unique, in first-seen order. failures lists
    (child_sitemap_url, error_text) for each child sitemap that could not be
    fetched or parsed; those children are skipped. An error in sitemap_url
    itself is raised.
    """
    urls = []
    failures = []
    _collect_book_urls(sitemap_url, path_prefix, 0, urls, failures)
    return list(dict.fromkeys(urls)), failures


def _collect_book_urls(sitemap_url, path_prefix, depth, urls, failures):
    """Append the book URLs under sitemap_url to urls, and child errors to failures.

    Sitemaps deeper than MAX_SITEMAP_DEPTH are not fetched, and nothing is
    recorded for them.
    """
    if depth > MAX_SITEMAP_DEPTH:
        return

    root = ET.fromstring(fetch_bytes(sitemap_url))

    sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", SITEMAP_NAMESPACE)
    if sub_sitemaps:
        for child_url in _loc_texts(sub_sitemaps):
            try:
                _collect_book_urls(child_url, path_prefix, depth + 1, urls, failures)
            except Exception as error:
                failures.append((child_url, str(error) or type(error).__name__))
        return

    all_urls = _loc_texts(root.findall(".//sm:loc", SITEMAP_NAMESPACE))
    book_urls = [url for url in all_urls if _is_book_page(url, path_prefix)]
    urls.extend(book_urls)


def _loc_texts(elements):
    """Yield each <loc> text with surrounding whitespace removed, skipping empty ones."""
    for element in elements:
        text = (element.text or "").strip()
        if text:
            yield text


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
