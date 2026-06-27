"""Security utilities — URL validation and SSRF protection."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

# Allowed git-provider hostnames — any other hostname is rejected at the gate.
_ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "dev.azure.com",
    }
)

# IPv4 ranges considered private / internal.
_PRIVATE_NETS_V4 = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),
    ipaddress.IPv4Network("198.18.0.0/15"),
)

# IPv6 ranges considered private / internal.
_PRIVATE_NETS_V6 = (
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("::ffff:0:0/96"),  # mapped v4 — checked via _is_private_v4 below
)


def _is_private_v4(ip: ipaddress.IPv4Address) -> bool:
    """Return True if *ip* falls within known private IPv4 ranges."""
    return any(ip in net for net in _PRIVATE_NETS_V4)


def _is_private_v6(ip: ipaddress.IPv6Address) -> bool:
    """Return True if *ip* falls within known private IPv6 ranges."""
    if ip.ipv4_mapped:
        return _is_private_v4(ip.ipv4_mapped)
    return any(ip in net for net in _PRIVATE_NETS_V6)


def _resolve_host(host: str) -> list[str]:
    """Resolve *host* to a list of IP-address strings (best-effort)."""
    import socket

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        return list({str(info[4][0]) for info in infos})
    except socket.gaierror:
        return []


def _is_hostname_allowed(host: str) -> bool:
    """Check *host* against the allow-list (exact match)."""
    return host.lower() in _ALLOWED_HOSTS


def validate_pr_url(pr_url: str, *, allow_internal: bool = False) -> None:
    """Validate a PR URL is safe and from an allowed provider.

    Checks performed:
      1. Scheme must be ``https`` (or internal mosaico scheme if allow_internal).
      2. Hostname must be in the allowed-provider set.
      3. Resolved IPs must not belong to private / loopback ranges.

    Raises:
        SecurityError: If any check fails.
    """
    from mergemate.core.errors import SecurityError

    parsed = urlparse(pr_url)

    # Allow internal mosaico URLs for testing / local use
    if allow_internal and parsed.scheme in ("mosaico", "internal"):
        return

    if parsed.scheme != "https":
        raise SecurityError(f"Only HTTPS URLs are allowed, got: {parsed.scheme}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise SecurityError("URL has no hostname")

    if not _is_hostname_allowed(host):
        raise SecurityError(f"Hostname not in allowed providers: {host}")

    # Resolve the hostname to IPs and verify none are private / internal.
    addrs = _resolve_host(host)
    if not addrs:
        # DNS resolution failure — allow through (URL passes allow-list check).
        return

    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if isinstance(ip, ipaddress.IPv4Address):
            if _is_private_v4(ip):
                raise SecurityError(f"Host {host} resolved to private IPv4 address {addr}")
        elif isinstance(ip, ipaddress.IPv6Address):
            if _is_private_v6(ip):
                raise SecurityError(f"Host {host} resolved to private IPv6 address {addr}")
