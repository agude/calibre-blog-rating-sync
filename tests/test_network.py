import pytest

from network import validate_url


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
