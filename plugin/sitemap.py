import re
from urllib.request import urlopen

LOC_PATTERN = re.compile(r"<loc>(.*?)</loc>")


def fetch_book_urls(sitemap_url, path_prefix="/books/"):
    """Fetch all book review URLs from a sitemap.xml."""
    xml = urlopen(sitemap_url, timeout=15).read().decode("utf-8")
    urls = LOC_PATTERN.findall(xml)
    return [u for u in urls if path_prefix in u]
