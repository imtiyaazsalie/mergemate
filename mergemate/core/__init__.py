"""MergeMate core module — configuration, types, logging, and provider interfaces."""

from mergemate.core.config import AppConfig, GitConfig, ModelConfig, ReviewConfig
from mergemate.core.errors import (
    AIHandlerError,
    ConfigError,
    GitProviderError,
    MergeMateError,
    RateLimitError,
    ToolError,
    ValidationError,
)
from mergemate.core.logging import LogFormat, get, setup
from mergemate.core.types import EditType, FilePatch, PullRequest, ReviewResult, ToolContext

__all__ = [
    # Config
    "AppConfig",
    "GitConfig",
    "ModelConfig",
    "ReviewConfig",
    # Errors
    "MergeMateError",
    "ConfigError",
    "GitProviderError",
    "AIHandlerError",
    "ToolError",
    "ValidationError",
    "RateLimitError",
    # Logging
    "LogFormat",
    "setup",
    "get",
    # Types
    "EditType",
    "FilePatch",
    "PullRequest",
    "ReviewResult",
    "ToolContext",
]
