from unittest.mock import patch
import socket

import pytest
import requests

from observateur_actif.source_fetcher import (
    SourceFetchError,
    _validate_public_url,
    fetch_source,
)


def _public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "text/html; charset=utf-8"}
    encoding = "utf-8"

    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size):
        yield from self.chunks

    def close(self):
        self.closed = True


def test_rejects_non_http_and_credentials():
    with pytest.raises(SourceFetchError):
        _validate_public_url("file:///etc/passwd")
    with pytest.raises(SourceFetchError):
        _validate_public_url("https://user:pass@example.com/article")


def test_rejects_private_ip_resolution():
    private_dns = lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
    ]
    with patch("observateur_actif.source_fetcher.socket.getaddrinfo", private_dns):
        with pytest.raises(SourceFetchError, match="locale|privée|réservée"):
            _validate_public_url("https://example.com/article")


def test_extracts_title_and_visible_text_and_marks_unverified():
    html = b"<html><head><title>Article historique</title></head><body><nav>Menu</nav><h1>Le site ancien</h1><p>Un texte documente.</p><script>secret()</script></body></html>"
    response = FakeResponse([html])
    with patch("observateur_actif.source_fetcher.socket.getaddrinfo", _public_dns), patch(
        "observateur_actif.source_fetcher.requests.get", return_value=response
    ):
        document = fetch_source("https://example.com/article")
    assert document.title == "Article historique"
    assert "Le site ancien" in document.text
    assert "Un texte documente." in document.text
    assert "secret" not in document.text
    assert document.editorial_status == "source_text_unverified"
    assert response.closed


def test_refuses_redirects():
    response = FakeResponse([])
    response.status_code = 302
    response.headers = {"Location": "https://other.example/"}
    with patch("observateur_actif.source_fetcher.socket.getaddrinfo", _public_dns), patch(
        "observateur_actif.source_fetcher.requests.get", return_value=response
    ):
        with pytest.raises(SourceFetchError, match="Redirection refusée"):
            fetch_source("https://example.com/article")
    assert response.closed


def test_enforces_download_size_limit():
    response = FakeResponse([b"x" * 20])
    with patch("observateur_actif.source_fetcher.socket.getaddrinfo", _public_dns), patch(
        "observateur_actif.source_fetcher.requests.get", return_value=response
    ):
        with pytest.raises(SourceFetchError, match="trop volumineuse"):
            fetch_source("https://example.com/article", max_bytes=10)
    assert response.closed


def test_rejects_non_html_content():
    response = FakeResponse([b"not html"])
    response.headers = {"Content-Type": "application/pdf"}
    with patch("observateur_actif.source_fetcher.socket.getaddrinfo", _public_dns), patch(
        "observateur_actif.source_fetcher.requests.get", return_value=response
    ):
        with pytest.raises(SourceFetchError, match="non HTML"):
            fetch_source("https://example.com/article")
    assert response.closed
