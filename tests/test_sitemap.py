from unittest.mock import patch

import pytest
from calibre_plugins.blog_rating_sync.sitemap import fetch_book_urls

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alexgude.com/</loc></url>
  <url><loc>https://alexgude.com/books/hyperion/</loc></url>
  <url><loc>https://alexgude.com/books/accelerando/</loc></url>
  <url><loc>https://alexgude.com/blog/some-post/</loc></url>
  <url><loc>https://alexgude.com/books/blindsight/</loc></url>
  <url><loc>https://alexgude.com/books/authors/dan_simmons/</loc></url>
  <url><loc>https://alexgude.com/books/series/hyperion_cantos/</loc></url>
  <url><loc>https://alexgude.com/books/by-rating/</loc></url>
  <url><loc>https://alexgude.com/books/</loc></url>
  <url><loc>https://alexgude.com/archive/books/sneaky/</loc></url>
</urlset>"""

PREFIXED_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sm:url><sm:loc>https://alexgude.com/books/hyperion/</sm:loc></sm:url>
  <sm:url><sm:loc>https://alexgude.com/books/blindsight/</sm:loc></sm:url>
</sm:urlset>"""


def test_fetch_book_urls():
    with patch(
        "calibre_plugins.blog_rating_sync.sitemap.fetch_bytes",
        return_value=SAMPLE_SITEMAP.encode("utf-8"),
    ):
        urls = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert "https://alexgude.com/books/hyperion/" in urls
    assert "https://alexgude.com/books/accelerando/" in urls
    assert "https://alexgude.com/books/blindsight/" in urls
    assert "https://alexgude.com/blog/some-post/" not in urls
    assert "https://alexgude.com/books/authors/dan_simmons/" not in urls
    assert "https://alexgude.com/books/series/hyperion_cantos/" not in urls
    assert "https://alexgude.com/books/" not in urls
    assert "https://alexgude.com/archive/books/sneaky/" not in urls


def test_fetch_book_urls_with_namespace_prefix():
    with patch(
        "calibre_plugins.blog_rating_sync.sitemap.fetch_bytes",
        return_value=PREFIXED_SITEMAP.encode("utf-8"),
    ):
        urls = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert len(urls) == 2
    assert "https://alexgude.com/books/hyperion/" in urls
    assert "https://alexgude.com/books/blindsight/" in urls


def test_rejects_file_scheme():
    with pytest.raises(ValueError, match="not allowed"):
        fetch_book_urls("file:///etc/passwd")


def test_fetch_book_urls_reads_sitemap_index_over_http(http_server):
    index = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <sitemap><loc>{http_server.url('/a.xml')}</loc></sitemap>\n"
        f"  <sitemap><loc>{http_server.url('/b.xml')}</loc></sitemap>\n"
        "</sitemapindex>"
    )
    child_a = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alexgude.com/books/hyperion/</loc></url>
  <url><loc>https://alexgude.com/blog/some-post/</loc></url>
  <url><loc>https://alexgude.com/books/accelerando/</loc></url>
</urlset>"""
    child_b = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alexgude.com/books/blindsight/</loc></url>
  <url><loc>https://alexgude.com/about/</loc></url>
</urlset>"""
    http_server.route("/sitemap.xml", body=index.encode("utf-8"))
    http_server.route("/a.xml", body=child_a.encode("utf-8"))
    http_server.route("/b.xml", body=child_b.encode("utf-8"))

    urls = fetch_book_urls(http_server.url("/sitemap.xml"))

    assert urls == [
        "https://alexgude.com/books/hyperion/",
        "https://alexgude.com/books/accelerando/",
        "https://alexgude.com/books/blindsight/",
    ]
