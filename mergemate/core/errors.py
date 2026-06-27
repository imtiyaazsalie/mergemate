"""Error types for MergeMate."""

from __future__ import annotations


class MergeMateError(Exception):
    """Base exception for all MergeMate errors."""


class ConfigError(MergeMateError):
    """Raised when configuration is invalid or missing."""


class GitProviderError(MergeMateError):
    """Raised when a git provider operation fails."""

    def __init__(self, message: str, provider: str = "", pr_url: str = ""):
        super().__init__(message)
        self.provider = provider
        self.pr_url = pr_url


class AIHandlerError(MergeMateError):
    """Raised when an AI model call fails."""

    def __init__(self, message: str, model: str = "", provider: str = ""):
        super().__init__(message)
        self.model = model
        self.provider = provider


class ToolError(MergeMateError):
    """Raised when a tool execution fails."""

    def __init__(self, message: str, tool: str = ""):
        super().__init__(message)
        self.tool = tool


class ValidationError(MergeMateError):
    """Raised when input validation fails."""


class RateLimitError(GitProviderError):
    """Raised when hitting git provider rate limits."""


class SecurityError(MergeMateError):
    """Raised when a security check fails (e.g., SSRF attempt, invalid URL)."""
