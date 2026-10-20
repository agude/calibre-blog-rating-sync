import pytest
from calibre_plugins.blog_rating_sync.network import fetch_page, validate_url


def test_accepts_https():
    validate_url("https://example.com/page")


def test_accepts_http():
    validate_url("http://example.com/page")


def test_rejects_file_scheme():
    with pytest.raises(ValueError, match="not allowed"):
        validate_url("file:///etc/passwd")


def test_rejects_ftp_scheme():
    with pytest.raises(ValueError, match="not allowed"):
        validate_url("ftp://example.com/file")


def test_rejects_empty_scheme():
    with pytest.raises(ValueError, match="not allowed"):
        validate_url("/etc/passwd")


def test_fetch_page_uses_declared_charset(http_server):
    http_server.route(
        "/page",
        headers={"Content-Type": "text/html; charset=latin-1"},
        body="café".encode("latin-1"),
    )
    assert fetch_page(http_server.url("/page")) == "café"


def test_fetch_page_defaults_to_utf8(http_server):
    http_server.route("/page", headers={"Content-Type": "text/html"}, body="café".encode())
    assert fetch_page(http_server.url("/page")) == "café"


def test_fetch_page_unknown_charset_falls_back_to_utf8(http_server):
    http_server.route(
        "/page",
        headers={"Content-Type": "text/html; charset=bogus-charset"},
        body="café".encode(),
    )
    assert fetch_page(http_server.url("/page")) == "café"
