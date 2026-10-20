import urllib.error
from unittest.mock import patch

import pytest
from calibre_plugins.blog_rating_sync.sitemap import MAX_SITEMAP_DEPTH, fetch_book_urls

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

HYPERION = "https://alexgude.com/books/hyperion/"
ACCELERANDO = "https://alexgude.com/books/accelerando/"
BLINDSIGHT = "https://alexgude.com/books/blindsight/"


def _urlset(*urls):
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    ).encode()


def _sitemapindex(*locs):
    entries = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</sitemapindex>"
    ).encode()


def test_fetch_book_urls():
    with patch(
        "calibre_plugins.blog_rating_sync.sitemap.fetch_bytes",
        return_value=SAMPLE_SITEMAP.encode("utf-8"),
    ):
        urls, failures = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert failures == []
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
        urls, failures = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert failures == []
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

    urls, failures = fetch_book_urls(http_server.url("/sitemap.xml"))

    assert urls == [
        "https://alexgude.com/books/hyperion/",
        "https://alexgude.com/books/accelerando/",
        "https://alexgude.com/books/blindsight/",
    ]
    assert failures == []


def test_child_sitemap_fetch_failure_is_skipped_and_reported(http_server):
    missing_url = http_server.url("/missing.xml")
    http_server.route("/sitemap.xml", body=_sitemapindex(missing_url, http_server.url("/b.xml")))
    http_server.route("/b.xml", body=_urlset(BLINDSIGHT))

    urls, failures = fetch_book_urls(http_server.url("/sitemap.xml"))

    assert urls == [BLINDSIGHT]
    assert failures == [(missing_url, "HTTP Error 404: Not Found")]


def test_child_sitemap_malformed_xml_is_skipped_and_reported(http_server):
    bad_url = http_server.url("/bad.xml")
    http_server.route("/sitemap.xml", body=_sitemapindex(bad_url, http_server.url("/b.xml")))
    http_server.route("/bad.xml", body=b"this is not xml")
    http_server.route("/b.xml", body=_urlset(BLINDSIGHT))

    urls, failures = fetch_book_urls(http_server.url("/sitemap.xml"))

    assert urls == [BLINDSIGHT]
    assert [url for url, _ in failures] == [bad_url]
    assert failures[0][1].startswith("syntax error")


def test_nested_indexes_stop_at_max_depth():
    self_listing_index = _sitemapindex("https://alexgude.com/sitemap.xml")
    with patch(
        "calibre_plugins.blog_rating_sync.sitemap.fetch_bytes",
        return_value=self_listing_index,
    ) as fetch:
        urls, failures = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert urls == []
    assert failures == []
    assert fetch.call_count == MAX_SITEMAP_DEPTH + 1


def test_duplicate_urls_across_children_are_removed(http_server):
    http_server.route(
        "/sitemap.xml",
        body=_sitemapindex(http_server.url("/a.xml"), http_server.url("/b.xml")),
    )
    http_server.route("/a.xml", body=_urlset(HYPERION, ACCELERANDO, HYPERION))
    http_server.route("/b.xml", body=_urlset(BLINDSIGHT, ACCELERANDO, HYPERION))

    urls, failures = fetch_book_urls(http_server.url("/sitemap.xml"))

    assert urls == [HYPERION, ACCELERANDO, BLINDSIGHT]
    assert failures == []


def test_top_level_failure_raises(http_server):
    http_server.route("/sitemap.xml", status=404)

    with pytest.raises(urllib.error.HTTPError):
        fetch_book_urls(http_server.url("/sitemap.xml"))
