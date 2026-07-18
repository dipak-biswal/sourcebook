"""fetch_url tool: SSRF guard, redirects, content-type gate, text extraction."""

import httpx
import pytest

import app.agents.fetch_url as fetch_url_mod
from app.agents.fetch_url import (
    MAX_CONTENT_BYTES,
    fetch_url_content,
    validate_fetch_url,
)

PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]
PRIVATE_ADDRINFO = [(2, 1, 6, "", ("10.0.0.5", 0))]


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every host as public, except literal private/link-local IPs."""

    def fake_getaddrinfo(host, port):
        try:
            import ipaddress

            ipaddress.ip_address(host)
            return [(2, 1, 6, "", (host, 0))]  # literal IP resolves to itself
        except ValueError:
            return PUBLIC_ADDRINFO

    monkeypatch.setattr(fetch_url_mod.socket, "getaddrinfo", fake_getaddrinfo)


class FakeResponse:
    def __init__(self, status_code=200, headers=None, body=b"", encoding="utf-8"):
        self.status_code = status_code
        self.headers = httpx.Headers(headers or {"content-type": "text/html"})
        self._body = body
        self.encoding = encoding

    def iter_bytes(self):
        yield self._body


class _Stream:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp

    def __exit__(self, *args):
        return False


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requested = []

    def stream(self, method, url, follow_redirects=False):
        self.requested.append(url)
        return _Stream(self._responses.pop(0))

    def close(self):
        pass


# --- validation / SSRF guard ---


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/x",
        "file:///etc/passwd",
        "http://localhost/x",
        "http://127.0.0.1:8000/health",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://user:pass@example.com/",
    ],
)
def test_validate_rejects_unsafe_urls(url):
    assert validate_fetch_url(url) is not None


def test_validate_rejects_host_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        fetch_url_mod.socket, "getaddrinfo", lambda host, port: PRIVATE_ADDRINFO
    )
    assert validate_fetch_url("http://internal.example.com/") is not None


def test_validate_accepts_public_host(public_dns):
    assert validate_fetch_url("https://example.com/page") is None


def test_fetch_returns_error_dict_for_blocked_url():
    result = fetch_url_content("http://127.0.0.1/x")
    assert result["url"] == "http://127.0.0.1/x"
    assert "error" in result


# --- fetching ---


def test_fetch_extracts_html_text_and_title(public_dns):
    html = (
        b"<html><head><title>My Page</title><style>p{color:red}</style>"
        b"<script>alert(1)</script></head>"
        b"<body><p>Hello &amp; welcome</p></body></html>"
    )
    client = FakeClient([FakeResponse(body=html)])
    result = fetch_url_content("https://example.com/", client=client)
    assert result["title"] == "My Page"
    assert "Hello & welcome" in result["text"]
    assert "alert" not in result["text"]
    assert "color:red" not in result["text"]
    assert result["status_code"] == 200
    assert result["truncated"] is False


def test_fetch_truncates_long_text(public_dns):
    body = b"<html><body>" + b"word " * 5000 + b"</body></html>"
    client = FakeClient([FakeResponse(body=body)])
    result = fetch_url_content("https://example.com/", client=client, max_chars=100)
    assert result["truncated"] is True
    assert result["text_chars"] == 100


def test_fetch_rejects_unsupported_content_type(public_dns):
    client = FakeClient(
        [FakeResponse(headers={"content-type": "image/png"}, body=b"\x89PNG")]
    )
    result = fetch_url_content("https://example.com/logo.png", client=client)
    assert "unsupported content type" in result["error"]


def test_fetch_allows_json(public_dns):
    client = FakeClient(
        [
            FakeResponse(
                headers={"content-type": "application/json"},
                body=b'{"a": 1}',
            )
        ]
    )
    result = fetch_url_content("https://example.com/api", client=client)
    assert result["text"] == '{"a": 1}'


def test_fetch_follows_public_redirect(public_dns):
    client = FakeClient(
        [
            FakeResponse(
                status_code=301,
                headers={"location": "https://example.com/final"},
            ),
            FakeResponse(body=b"<html><body>landed</body></html>"),
        ]
    )
    result = fetch_url_content("https://example.com/old", client=client)
    assert result["final_url"] == "https://example.com/final"
    assert "landed" in result["text"]


def test_fetch_blocks_redirect_to_private_host(public_dns):
    client = FakeClient(
        [
            FakeResponse(
                status_code=302,
                headers={"location": "http://169.254.169.254/latest/meta-data"},
            )
        ]
    )
    result = fetch_url_content("https://example.com/", client=client)
    assert "blocked redirect" in result["error"]


def test_fetch_caps_redirect_hops(public_dns):
    hop = FakeResponse(
        status_code=301, headers={"location": "https://example.com/loop"}
    )
    client = FakeClient([hop, hop, hop, hop, hop])
    result = fetch_url_content("https://example.com/", client=client)
    assert result["error"] == "too many redirects"


def test_fetch_handles_transport_error(public_dns):
    client = FakeClient([httpx.ConnectError("boom")])
    result = fetch_url_content("https://example.com/", client=client)
    assert "fetch failed" in result["error"]


def test_fetch_handles_non_2xx(public_dns):
    client = FakeClient([FakeResponse(status_code=404)])
    result = fetch_url_content("https://example.com/missing", client=client)
    assert "HTTP 404" in result["error"]


def test_fetch_caps_body_bytes(public_dns):
    class BigBodyResponse(FakeResponse):
        def iter_bytes(self):
            for _ in range(64):
                yield b"x" * (MAX_CONTENT_BYTES // 32)

    client = FakeClient([BigBodyResponse(headers={"content-type": "text/plain"})])
    result = fetch_url_content("https://example.com/big", client=client)
    assert result["truncated"] is True
