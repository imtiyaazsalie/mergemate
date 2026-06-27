"""Tests for mergemate.core.rate_limiter — sliding-window RateLimiter."""

from __future__ import annotations

import time

import pytest

from mergemate.core.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# test_allows_within_limit
# ---------------------------------------------------------------------------


def test_allows_within_limit():
    """Requests under the max should be allowed."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is True


def test_first_request_always_allowed():
    """The very first request for a key should always be allowed."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("new-key") is True


# ---------------------------------------------------------------------------
# test_blocks_over_limit
# ---------------------------------------------------------------------------


def test_blocks_over_limit():
    """Exceeding max_requests should block further requests."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is False  # 3rd request blocked


def test_blocks_with_cost():
    """Requests with cost > 1 should consume more budget."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.is_allowed("key-a", cost=2) is True  # consumes 2
    assert limiter.is_allowed("key-a", cost=2) is False  # would exceed 3


def test_different_keys_independent():
    """Rate limits for different keys are independent."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is False  # key-a exhausted
    assert limiter.is_allowed("key-b") is True  # key-b still available
    assert limiter.is_allowed("key-b") is False


# ---------------------------------------------------------------------------
# test_resets_after_window
# ---------------------------------------------------------------------------


def test_resets_after_window():
    """After the window expires, all entries are pruned and requests allowed again."""
    limiter = RateLimiter(max_requests=2, window_seconds=10)

    # Manually seed the bucket with expired (old) timestamps.
    old = time.monotonic() - 20
    limiter._buckets["key-a"] = [old, old - 1]

    # Prune removes expired entries automatically via is_allowed.
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is False  # 3rd now blocked


def test_resets_after_window_boundary():
    """Exactly at window boundary, old requests should be pruned."""
    limiter = RateLimiter(max_requests=2, window_seconds=10)

    # Manually insert a timestamp right at the cutoff.
    old_ts = time.monotonic() - 10.0  # exactly at boundary (<= cutoff)

    # Force it into the bucket and test.
    limiter._buckets["test-key"] = [old_ts]
    # The _prune keeps ts > cutoff, so old_ts (== cutoff) should be pruned.
    limiter._prune("test-key")
    assert "test-key" not in limiter._buckets


# ---------------------------------------------------------------------------
# test_pr_url_specific — per-PR buckets
# ---------------------------------------------------------------------------


def test_pr_url_specific_buckets():
    """Using PR URLs as keys isolates rate limits per PR."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    pr1 = "https://github.com/org/repo/pull/1"
    pr2 = "https://github.com/org/repo/pull/2"

    # Fill pr1
    assert limiter.is_allowed(pr1) is True
    assert limiter.is_allowed(pr1) is True
    assert limiter.is_allowed(pr1) is False

    # pr2 is unaffected
    assert limiter.is_allowed(pr2) is True
    assert limiter.is_allowed(pr2) is True


# ---------------------------------------------------------------------------
# test_check_does_not_consume — peek doesn't count
# ---------------------------------------------------------------------------


def test_check_does_not_consume():
    """check() should not consume capacity."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    assert limiter.check("key-a") is True
    assert limiter.check("key-a") is True
    # Still available because check doesn't record.
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is True
    assert limiter.is_allowed("key-a") is False


def test_check_reflects_consumed_requests():
    """check() should reflect previously consumed capacity."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.is_allowed("key-a")  # consume 1
    assert limiter.check("key-a") is True  # 1 more available
    limiter.is_allowed("key-a")  # consume 2nd
    assert limiter.check("key-a") is False  # exhausted


def test_check_with_cost():
    """check() with cost should reflect accurate remaining capacity."""
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    limiter.is_allowed("key-a", cost=3)  # consumed 3
    assert limiter.check("key-a", cost=2) is True  # 3 + 2 = 5, still ok
    assert limiter.check("key-a", cost=3) is False  # 3 + 3 = 6, would exceed


# ---------------------------------------------------------------------------
# test_prunes_expired — old entries cleaned
# ---------------------------------------------------------------------------


def test_prunes_expired():
    """_prune should remove expired timestamps from buckets."""
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    now = time.monotonic()
    limiter._buckets["test-key"] = [now - 15, now - 12, now - 5, now - 1]

    limiter._prune("test-key")

    # Only the two recent timestamps should remain.
    remaining = limiter._buckets["test-key"]
    assert len(remaining) == 2
    assert all(ts > now - 10 for ts in remaining)


def test_prunes_removes_empty_bucket():
    """_prune should delete the key when all entries expire."""
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    now = time.monotonic()
    limiter._buckets["test-key"] = [now - 15]

    limiter._prune("test-key")
    assert "test-key" not in limiter._buckets


def test_prune_on_nonexistent_key_is_safe():
    """Pruning a key not in buckets should not raise."""
    limiter = RateLimiter()
    limiter._prune("nonexistent")  # no exception


# ---------------------------------------------------------------------------
# remaining
# ---------------------------------------------------------------------------


def test_remaining_full_capacity():
    """remaining() should return max_requests for a fresh key."""
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    assert limiter.remaining("fresh-key") == 10


def test_remaining_after_consumption():
    """remaining() should decrease as requests are consumed."""
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    limiter.is_allowed("key")
    assert limiter.remaining("key") == 4
    limiter.is_allowed("key")
    limiter.is_allowed("key")
    assert limiter.remaining("key") == 2


def test_remaining_never_negative():
    """remaining() should return 0 when exhausted, never negative."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.is_allowed("key")
    limiter.is_allowed("key")
    limiter.is_allowed("key")  # blocked, not recorded
    assert limiter.remaining("key") == 0


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_clears_key():
    """reset() should clear all state for a key."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.is_allowed("key")
    limiter.is_allowed("key")
    assert limiter.remaining("key") == 0

    limiter.reset("key")
    assert limiter.remaining("key") == 2
    assert limiter.is_allowed("key") is True


def test_reset_nonexistent_key():
    """reset() on a key not tracked should not raise."""
    limiter = RateLimiter()
    limiter.reset("no-such-key")  # no exception
