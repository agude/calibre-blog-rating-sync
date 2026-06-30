import xml.etree.ElementTree as ET
from urllib.request import urlopen

SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_book_urls(sitemap_url, path_prefix="/books/"):
    """Fetch all book review URLs from a sitemap.xml."""
    response = urlopen(sitemap_url, timeout=15).read()
    root = ET.fromstring(response)
    urls = [
        loc.text
        for loc in root.findall(".//sm:loc", SITEMAP_NAMESPACE)
        if loc.text
    ]
    return [url for url in urls if path_prefix in url]
