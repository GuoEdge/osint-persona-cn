"""SSRF 防护 / Block server-side requests to private networks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFError(ValueError):
    """URL 不允许由服务端发起请求。"""


def assert_public_http_url(url: str) -> str:
    """仅允许公网 http(s) URL。"""
    text = str(url or "").strip()
    if not text:
        raise SSRFError("empty url")
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise SSRFError(f"unsupported scheme: {scheme or '(none)'}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise SSRFError("missing hostname")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        raise SSRFError("loopback host blocked")
    if host.endswith(".local") or host.endswith(".internal"):
        raise SSRFError("internal host suffix blocked")
    _assert_resolved_public(host)
    return text


def _assert_resolved_public(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host)
        _reject_private_ip(ip)
        return
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SSRFError(f"cannot resolve host: {host}") from exc
    if not infos:
        raise SSRFError(f"cannot resolve host: {host}")
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        _reject_private_ip(ip)


def _reject_private_ip(ip: ipaddress._BaseAddress) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise SSRFError(f"private or reserved address blocked: {ip}")
