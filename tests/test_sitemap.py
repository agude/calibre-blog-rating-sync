from unittest.mock import MagicMock, patch

from sitemap import fetch_book_urls

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alexgude.com/</loc></url>
  <url><loc>https://alexgude.com/books/hyperion/</loc></url>
  <url><loc>https://alexgude.com/books/accelerando/</loc></url>
  <url><loc>https://alexgude.com/blog/some-post/</loc></url>
  <url><loc>https://alexgude.com/books/blindsight/</loc></url>
</urlset>"""

PREFIXED_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sm:url><sm:loc>https://alexgude.com/books/hyperion/</sm:loc></sm:url>
  <sm:url><sm:loc>https://alexgude.com/books/blindsight/</sm:loc></sm:url>
</sm:urlset>"""


def _mock_urlopen(xml_content):
    mock_response = MagicMock()
    mock_response.read.return_value = xml_content.encode("utf-8")
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def test_fetch_book_urls():
    with patch("sitemap.urlopen", return_value=_mock_urlopen(SAMPLE_SITEMAP)):
        urls = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert len(urls) == 3
    assert "https://alexgude.com/books/hyperion/" in urls
    assert "https://alexgude.com/books/accelerando/" in urls
    assert "https://alexgude.com/books/blindsight/" in urls
    assert "https://alexgude.com/blog/some-post/" not in urls


def test_fetch_book_urls_with_namespace_prefix():
    with patch("sitemap.urlopen", return_value=_mock_urlopen(PREFIXED_SITEMAP)):
        urls = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert len(urls) == 2
    assert "https://alexgude.com/books/hyperion/" in urls
    assert "https://alexgude.com/books/blindsight/" in urls


def test_rejects_file_scheme():
    try:
        fetch_book_urls("file:///etc/passwd")
        assert False, "Should have raised ValueError"
    except ValueError as error:
        assert "not allowed" in str(error)
