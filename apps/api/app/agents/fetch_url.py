"""Fetch a public web page as text for agent research."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.ingestion.parsers import strip_html_text

ALLOWED_SCHEMES = ("http", "https")
_ALLOWED_CONTENT_PREFIXES = (
    "text/",
    "application/json",
    "application/xhtml+xml",
    "application/xml",
)
DEFAULT_TIMEOUT_S = 10.0
MAX_CONTENT_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 8000
MAX_REDIRECTS = 3
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_USER_AGENT = "SourcebookAgent/1.0"

_TITLE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")


def _host_block_reason(host: str) -> str | None:
    """Resolve host and reject anything that is not a public unicast address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return f"could not resolve host: {host}"
    if not infos:
        return f"could not resolve host: {host}"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return f"unresolvable address for host: {host}"
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return f"host resolves to a non-public address: {host}"
    return None


def validate_fetch_url(url: str) -> str | None:
    """Return an error string when the URL must not be fetched, else None."""
    u = (url or "").strip()
    if not u:
        return "URL is required"
    try:
        parts = urlsplit(u)
    except ValueError:
        return "invalid URL"
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        return f"unsupported URL scheme: {parts.scheme or '(none)'}"
    if not parts.hostname:
        return "URL has no host"
    if "@" in parts.netloc:
        return "URLs with credentials are not allowed"
    return _host_block_reason(parts.hostname)


def _extract_title(html: str) -> str:
    m = _TITLE.search(html)
    if not m:
        return ""
    return re.sub(r"\s+", " ", strip_html_text(m.group(1))).strip()[:300]


def _read_body(resp: httpx.Response) -> tuple[bytes, bool]:
    """Consume up to MAX_CONTENT_BYTES of the response body."""
    body = b""
    truncated = False
    for chunk in resp.iter_bytes():
        body += chunk
        if len(body) >= MAX_CONTENT_BYTES:
            body = body[:MAX_CONTENT_BYTES]
            truncated = True
            break
    return body, truncated


def fetch_url_content(
    url: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_chars: int = MAX_TEXT_CHARS,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    Fetch a public http(s) URL and return page text.

    Returns a normalized payload for the agent and UI:
    {url, final_url, status_code, content_type, title, text, text_chars, truncated}
    or {url, error} on any failure — never raises.
    """
    original_url = (url or "").strip()
    error = validate_fetch_url(original_url)
    if error:
        return {"url": original_url, "error": error}

    own_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={"User-Agent": _USER_AGENT},
        )

    try:
        current_url = original_url
        resp: httpx.Response | None = None
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current_url, follow_redirects=False) as r:
                    if r.status_code in _REDIRECT_STATUSES:
                        location = r.headers.get("location")
                        if not location:
                            return {"url": original_url, "error": "redirect without Location header"}
                        current_url = urljoin(current_url, location)
                        error = validate_fetch_url(current_url)
                        if error:
                            return {"url": original_url, "error": f"blocked redirect: {error}"}
                        resp = None
                        continue
                    if r.status_code < 200 or r.status_code >= 300:
                        return {
                            "url": original_url,
                            "error": f"HTTP {r.status_code} from {current_url}",
                        }
                    content_type = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                    if content_type and not content_type.startswith(_ALLOWED_CONTENT_PREFIXES):
                        return {
                            "url": original_url,
                            "error": f"unsupported content type: {content_type}",
                        }
                    body, byte_truncated = _read_body(r)
                    resp = r
                    break
            except httpx.HTTPError as exc:
                return {"url": original_url, "error": f"fetch failed: {exc}"}
        else:
            return {"url": original_url, "error": "too many redirects"}

        if resp is None:
            return {"url": original_url, "error": "too many redirects"}

        encoding = resp.encoding or "utf-8"
        try:
            raw_text = body.decode(encoding, errors="replace")
        except (LookupError, ValueError):
            raw_text = body.decode("utf-8", errors="replace")
        raw_text = raw_text.replace("\x00", "")

        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        title = ""
        if "html" in content_type or "<html" in raw_text[:2000].lower():
            title = _extract_title(raw_text)
            text = re.sub(r"\s+", " ", strip_html_text(raw_text)).strip()
        else:
            text = raw_text.strip()

        char_truncated = len(text) > max_chars
        if char_truncated:
            text = text[:max_chars]

        return {
            "url": original_url,
            "final_url": current_url,
            "status_code": resp.status_code,
            "content_type": content_type,
            "title": title,
            "text": text,
            "text_chars": len(text),
            "truncated": byte_truncated or char_truncated,
        }
    finally:
        if own_client:
            client.close()
