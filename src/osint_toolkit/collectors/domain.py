"""域名信息采集 / Domain information collector."""

import socket
from typing import Any


def collect_domain_info(domain: str) -> dict[str, Any]:
    """收集域名的基础 DNS 信息。"""
    records: list[dict[str, str]] = []

    try:
        addr_info = socket.getaddrinfo(domain, None)
        seen: set[str] = set()
        for entry in addr_info:
            ip = entry[4][0]
            if ip not in seen:
                seen.add(ip)
                records.append({"type": "A", "value": ip})
    except socket.gaierror:
        pass

    return {
        "domain": domain,
        "dns_records": records,
    }
