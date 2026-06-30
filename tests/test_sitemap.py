import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))

from sitemap import fetch_book_urls

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://alexgude.com/</loc></url>
  <url><loc>https://alexgude.com/books/hyperion/</loc></url>
  <url><loc>https://alexgude.com/books/accelerando/</loc></url>
  <url><loc>https://alexgude.com/blog/some-post/</loc></url>
  <url><loc>https://alexgude.com/books/blindsight/</loc></url>
</urlset>"""


def test_fetch_book_urls():
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_SITEMAP.encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("sitemap.urlopen", return_value=mock_response):
        urls = fetch_book_urls("https://alexgude.com/sitemap.xml")

    assert len(urls) == 3
    assert "https://alexgude.com/books/hyperion/" in urls
    assert "https://alexgude.com/books/accelerando/" in urls
    assert "https://alexgude.com/books/blindsight/" in urls
    assert "https://alexgude.com/blog/some-post/" not in urls
