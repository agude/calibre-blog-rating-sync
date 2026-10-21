import http.client
import urllib.error

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


def test_fetch_page_404_raises_http_error(http_server):
    http_server.route("/missing", status=404, body=b"Not found")
    with pytest.raises(urllib.error.HTTPError) as error:
        fetch_page(http_server.url("/missing"))
    assert error.value.code == 404


def test_fetch_page_500_raises_http_error(http_server):
    http_server.route("/broken", status=500, body=b"Server error")
    with pytest.raises(urllib.error.HTTPError) as error:
        fetch_page(http_server.url("/broken"))
    assert error.value.code == 500


def test_fetch_page_oversized_body_raises(http_server, monkeypatch):
    monkeypatch.setattr("calibre_plugins.blog_rating_sync.network.MAX_RESPONSE_BYTES", 1024)
    http_server.route("/big", body=b"x" * 2048)
    with pytest.raises(ValueError, match="exceeds 1024 bytes"):
        fetch_page(http_server.url("/big"))


def test_fetch_page_truncated_body_raises(http_server):
    http_server.raw_route("/short", b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort")
    with pytest.raises(ValueError, match="Truncated response: got 5 of 100 bytes"):
        fetch_page(http_server.url("/short"))


def test_fetch_page_ignores_unparseable_content_length(http_server):
    http_server.raw_route("/odd", b"HTTP/1.1 200 OK\r\nContent-Length: abc\r\n\r\nhello")
    assert fetch_page(http_server.url("/odd")) == "hello"


def test_fetch_page_garbage_status_line_raises_bad_status_line(http_server):
    """BadStatusLine is not an OSError, so fetch_all's broad except is what catches it."""
    http_server.raw_route("/garbage", b"garbage\r\n\r\n")
    with pytest.raises(http.client.BadStatusLine):
        fetch_page(http_server.url("/garbage"))
