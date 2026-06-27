"""Tests for mergemate.core.security — URL validation and SSRF protection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mergemate.core.errors import SecurityError
from mergemate.core.security import (
    _is_hostname_allowed,
    _is_private_v4,
    _is_private_v6,
    validate_pr_url,
)

# ---------------------------------------------------------------------------
# test_allows_github / test_allows_gitlab
# ---------------------------------------------------------------------------


def test_allows_github():
    """A valid github.com HTTPS URL should pass validation."""
    # Patch _resolve_host so we don't hit real DNS.
    with patch("mergemate.core.security._resolve_host", return_value=["140.82.121.3"]):
        validate_pr_url("https://github.com/owner/repo/pull/42")


def test_allows_gitlab():
    """A valid gitlab.com HTTPS URL should pass validation."""
    with patch("mergemate.core.security._resolve_host", return_value=["172.65.251.78"]):
        validate_pr_url("https://gitlab.com/group/project/-/merge_requests/1")


def test_allows_bitbucket():
    """A valid bitbucket.org HTTPS URL should pass validation."""
    with patch("mergemate.core.security._resolve_host", return_value=["104.192.143.3"]):
        validate_pr_url("https://bitbucket.org/workspace/repo/pull-requests/1")


def test_allows_azure_devops():
    """A valid dev.azure.com HTTPS URL should pass validation."""
    with patch("mergemate.core.security._resolve_host", return_value=["13.107.42.20"]):
        validate_pr_url("https://dev.azure.com/org/project/_git/repo/pullrequest/1")


def test_allows_url_with_path_and_query():
    """URLs with paths and query strings should pass."""
    with patch("mergemate.core.security._resolve_host", return_value=["140.82.121.3"]):
        validate_pr_url("https://github.com/org/repo/pull/1/files?w=1")


def test_allows_when_dns_fails():
    """When DNS resolution returns nothing, the URL should still pass if host is allowed."""
    with patch("mergemate.core.security._resolve_host", return_value=[]):
        validate_pr_url("https://github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# test_rejects_http
# ---------------------------------------------------------------------------


def test_rejects_http():
    """Non-HTTPS scheme should raise SecurityError."""
    with pytest.raises(SecurityError, match="Only HTTPS URLs are allowed"):
        validate_pr_url("http://github.com/owner/repo/pull/1")


def test_rejects_ftp_scheme():
    """ftp:// scheme should be rejected."""
    with pytest.raises(SecurityError, match="Only HTTPS URLs are allowed"):
        validate_pr_url("ftp://github.com/owner/repo/pull/1")


def test_rejects_no_scheme():
    """URLs without a scheme should fail."""
    with pytest.raises(SecurityError, match="Only HTTPS URLs are allowed"):
        validate_pr_url("github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# test_rejects_unknown_host
# ---------------------------------------------------------------------------


def test_rejects_unknown_host():
    """Non-allowlisted hostname should raise SecurityError."""
    with pytest.raises(SecurityError, match="Hostname not in allowed providers"):
        validate_pr_url("https://evil.example.com/owner/repo/pull/1")


def test_rejects_spoofed_host():
    """A host that looks like github.com but isn't should be rejected."""
    with pytest.raises(SecurityError, match="Hostname not in allowed providers"):
        validate_pr_url("https://github.com.evil.com/owner/repo/pull/1")


def test_rejects_url_with_no_hostname():
    """URLs with no hostname at all should raise SecurityError."""
    with pytest.raises(SecurityError, match="URL has no hostname"):
        validate_pr_url("https:///path")


# ---------------------------------------------------------------------------
# test_rejects_internal — localhost / private IP
# ---------------------------------------------------------------------------


def test_rejects_localhost():
    """localhost should be rejected (not in allowlist)."""
    with pytest.raises(SecurityError, match="Hostname not in allowed providers"):
        validate_pr_url("https://localhost:8080/repo/pull/1")


def test_rejects_private_ip_resolution():
    """If a valid host resolves to a private IP, it should be rejected."""
    with patch(
        "mergemate.core.security._resolve_host",
        return_value=["10.0.0.1", "192.168.1.1"],
    ):
        with pytest.raises(SecurityError, match="resolved to private IPv4"):
            validate_pr_url("https://github.com/owner/repo/pull/1")


def test_rejects_loopback_resolution():
    """127.x.x.x resolution should be rejected."""
    with patch(
        "mergemate.core.security._resolve_host",
        return_value=["127.0.0.1"],
    ):
        with pytest.raises(SecurityError, match="resolved to private IPv4"):
            validate_pr_url("https://github.com/owner/repo/pull/1")


def test_rejects_ipv6_loopback_resolution():
    """::1 resolution should be rejected."""
    with patch(
        "mergemate.core.security._resolve_host",
        return_value=["::1"],
    ):
        with pytest.raises(SecurityError, match="resolved to private IPv6"):
            validate_pr_url("https://github.com/owner/repo/pull/1")


def test_rejects_ipv6_private_resolution():
    """fc00::/7 resolution should be rejected."""
    with patch(
        "mergemate.core.security._resolve_host",
        return_value=["fc00::1"],
    ):
        with pytest.raises(SecurityError, match="resolved to private IPv6"):
            validate_pr_url("https://github.com/owner/repo/pull/1")


def test_rejects_ipv4_mapped_private():
    """IPv4-mapped IPv6 (::ffff:10.0.0.1) should be rejected."""
    with patch(
        "mergemate.core.security._resolve_host",
        return_value=["::ffff:10.0.0.1"],
    ):
        with pytest.raises(SecurityError, match="resolved to private IPv6"):
            validate_pr_url("https://github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# test_allows_internal_with_flag
# ---------------------------------------------------------------------------


def test_allows_internal_mosaico_scheme():
    """Mosaico scheme should pass when allow_internal=True."""
    # No DNS patching needed — mosaico scheme short-circuits.
    validate_pr_url("mosaico://github.com/org/repo/pull/1", allow_internal=True)


def test_allows_internal_internal_scheme():
    """'internal' scheme should work with allow_internal."""
    validate_pr_url("internal://localhost/pr/1", allow_internal=True)


def test_internal_scheme_blocked_without_flag():
    """Mosaico scheme should be blocked when allow_internal=False."""
    with pytest.raises(SecurityError, match="Only HTTPS URLs are allowed"):
        validate_pr_url("mosaico://github.com/org/repo/pull/1", allow_internal=False)


def test_https_still_validated_with_flag():
    """Even with allow_internal=True, HTTPS URLs are still validated."""
    with patch(
        "mergemate.core.security._resolve_host",
        return_value=["10.0.0.1"],
    ):
        with pytest.raises(SecurityError, match="resolved to private IPv4"):
            validate_pr_url("https://github.com/org/repo/pull/1", allow_internal=True)


# ---------------------------------------------------------------------------
# _is_hostname_allowed unit tests
# ---------------------------------------------------------------------------


def test_is_hostname_allowed_case_insensitive():
    """Hostname check should be case-insensitive."""
    assert _is_hostname_allowed("GITHUB.COM") is True
    assert _is_hostname_allowed("GitLab.com") is True


def test_is_hostname_allowed_unknown():
    """Unknown hostnames should return False."""
    assert _is_hostname_allowed("google.com") is False
    assert _is_hostname_allowed("") is False


# ---------------------------------------------------------------------------
# _is_private_v4 unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip_str",
    [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.255.255",
        "127.0.0.1",
        "169.254.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "198.18.0.1",
    ],
)
def test_is_private_v4_true(ip_str):
    """Known private ranges should be identified."""
    from ipaddress import IPv4Address

    assert _is_private_v4(IPv4Address(ip_str)) is True


@pytest.mark.parametrize(
    "ip_str",
    [
        "8.8.8.8",
        "1.1.1.1",
        "140.82.121.3",
        "172.32.0.1",  # just outside 172.16/12
        "172.15.255.255",  # just outside 172.16/12
    ],
)
def test_is_private_v4_false(ip_str):
    """Public IPs should not be flagged."""
    from ipaddress import IPv4Address

    assert _is_private_v4(IPv4Address(ip_str)) is False


# ---------------------------------------------------------------------------
# _is_private_v6 unit tests
# ---------------------------------------------------------------------------


def test_is_private_v6_ipv4_mapped_private():
    """IPv4-mapped private address should be recognized."""
    from ipaddress import IPv6Address

    assert _is_private_v6(IPv6Address("::ffff:192.168.0.1")) is True


def test_is_private_v6_ipv4_mapped_public():
    """IPv4-mapped public address should pass."""
    from ipaddress import IPv6Address

    assert _is_private_v6(IPv6Address("::ffff:8.8.8.8")) is False


def test_is_private_v6_link_local():
    """fe80::/10 link-local should be private."""
    from ipaddress import IPv6Address

    assert _is_private_v6(IPv6Address("fe80::1")) is True


def test_is_private_v6_public():
    """Public IPv6 addresses should not be flagged."""
    from ipaddress import IPv6Address

    assert _is_private_v6(IPv6Address("2001:4860:4860::8888")) is False
