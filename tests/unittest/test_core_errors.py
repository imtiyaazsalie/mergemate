"""Tests for mergemate.core.errors — exception hierarchy."""

from __future__ import annotations

from mergemate.core.errors import (
    AIHandlerError,
    ConfigError,
    GitProviderError,
    MergeMateError,
    RateLimitError,
    SecurityError,
    ToolError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# test_merge_mate_error — base exception
# ---------------------------------------------------------------------------


def test_merge_mate_error_is_base():
    """All MergeMate errors should inherit from MergeMateError."""
    assert issubclass(MergeMateError, Exception)


def test_merge_mate_error_message():
    """Base exception should store the message."""
    err = MergeMateError("something went wrong")
    assert str(err) == "something went wrong"


def test_merge_mate_error_no_args():
    """Base exception should work with no arguments."""
    err = MergeMateError()
    assert isinstance(err, MergeMateError)


# ---------------------------------------------------------------------------
# test_config_error
# ---------------------------------------------------------------------------


def test_config_error_inherits():
    """ConfigError is a MergeMateError."""
    err = ConfigError("missing key")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, ConfigError)


def test_config_error_message():
    """ConfigError stores the message."""
    err = ConfigError("invalid configuration")
    assert str(err) == "invalid configuration"


# ---------------------------------------------------------------------------
# test_git_provider_error — with provider/pr_url attrs
# ---------------------------------------------------------------------------


def test_git_provider_error_inherits():
    """GitProviderError is a MergeMateError."""
    err = GitProviderError("failed")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, GitProviderError)


def test_git_provider_error_default_attrs():
    """Default provider and pr_url should be empty strings."""
    err = GitProviderError("request failed")
    assert err.provider == ""
    assert err.pr_url == ""


def test_git_provider_error_with_attrs():
    """Provider and pr_url should be stored when provided."""
    err = GitProviderError("not found", provider="github", pr_url="https://github.com/org/repo/pull/1")
    assert err.provider == "github"
    assert err.pr_url == "https://github.com/org/repo/pull/1"
    assert str(err) == "not found"


# ---------------------------------------------------------------------------
# test_ai_handler_error — with model/provider attrs
# ---------------------------------------------------------------------------


def test_ai_handler_error_inherits():
    """AIHandlerError is a MergeMateError."""
    err = AIHandlerError("timeout")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, AIHandlerError)


def test_ai_handler_error_default_attrs():
    """Default model and provider should be empty strings."""
    err = AIHandlerError("AI call failed")
    assert err.model == ""
    assert err.provider == ""


def test_ai_handler_error_with_attrs():
    """Model and provider should be stored when provided."""
    err = AIHandlerError("rate limited", model="gpt-4o", provider="openai")
    assert err.model == "gpt-4o"
    assert err.provider == "openai"
    assert str(err) == "rate limited"


# ---------------------------------------------------------------------------
# test_tool_error — with tool name
# ---------------------------------------------------------------------------


def test_tool_error_inherits():
    """ToolError is a MergeMateError."""
    err = ToolError("execution failed")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, ToolError)


def test_tool_error_default_tool():
    """Default tool name should be empty string."""
    err = ToolError("something broke")
    assert err.tool == ""


def test_tool_error_with_tool():
    """Tool name should be stored when provided."""
    err = ToolError("parse error", tool="review")
    assert err.tool == "review"
    assert str(err) == "parse error"


# ---------------------------------------------------------------------------
# test_security_error
# ---------------------------------------------------------------------------


def test_security_error_inherits():
    """SecurityError is a MergeMateError."""
    err = SecurityError("invalid URL")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, SecurityError)


def test_security_error_message():
    """SecurityError should store the message."""
    err = SecurityError("SSRF attempt detected")
    assert str(err) == "SSRF attempt detected"


# ---------------------------------------------------------------------------
# test_rate_limit_error
# ---------------------------------------------------------------------------


def test_rate_limit_error_inherits_git_provider_error():
    """RateLimitError should be a GitProviderError and MergeMateError."""
    err = RateLimitError("too many requests")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, GitProviderError)
    assert isinstance(err, RateLimitError)


def test_rate_limit_error_inherits_attrs():
    """RateLimitError should support provider/pr_url from GitProviderError."""
    err = RateLimitError("rate limited", provider="gitlab", pr_url="https://gitlab.com/a/b/-/merge_requests/1")
    assert err.provider == "gitlab"
    assert err.pr_url == "https://gitlab.com/a/b/-/merge_requests/1"


def test_rate_limit_error_is_not_ai_handler():
    """RateLimitError is git-provider, not AI."""
    err = RateLimitError("too fast")
    assert not isinstance(err, AIHandlerError)


# ---------------------------------------------------------------------------
# test_validation_error
# ---------------------------------------------------------------------------


def test_validation_error_inherits():
    """ValidationError is a MergeMateError."""
    err = ValidationError("field required")
    assert isinstance(err, MergeMateError)
    assert isinstance(err, ValidationError)
