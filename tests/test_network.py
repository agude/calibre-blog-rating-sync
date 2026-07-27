from unittest.mock import MagicMock, patch

import pytest
from network import fetch_page, validate_url


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


def _mock_response(body, charset):
    response = MagicMock()
    response.read.return_value = body
    response.headers.get_content_charset.return_value = charset
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_fetch_page_uses_declared_charset():
    body = "café".encode("latin-1")
    with patch("network.urlopen", return_value=_mock_response(body, "latin-1")):
        assert fetch_page("https://example.com/") == "café"


def test_fetch_page_defaults_to_utf8():
    body = "café".encode()
    with patch("network.urlopen", return_value=_mock_response(body, None)):
        assert fetch_page("https://example.com/") == "café"


def test_fetch_page_unknown_charset_falls_back_to_utf8():
    body = "café".encode()
    with patch("network.urlopen", return_value=_mock_response(body, "bogus-charset")):
        assert fetch_page("https://example.com/") == "café"
