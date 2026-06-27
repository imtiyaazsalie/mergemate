"""MergeMate agent — orchestrates PR review commands.

Rewritten with proper dependency injection, lazy tool loading,
and clean separation from the old config_loader global singleton.
"""

from __future__ import annotations

import shlex
from typing import Any, Callable

from mergemate.core.config import AppConfig
from mergemate.core.errors import SecurityError
from mergemate.core.providers import AIHandler, GitProvider
from mergemate.core.rate_limiter import RateLimiter
from mergemate.core.security import validate_pr_url
from mergemate.core.types import ToolContext
from mergemate.log import get_logger

# ---------------------------------------------------------------------------
# Tool registry with metadata — tools are registered here, not eagerly imported
# ---------------------------------------------------------------------------

CommandHandler = Callable[..., Any]


class ToolRegistry:
    """Registry of available tools with lazy loading.

    Tools are only imported when first used, avoiding the eager-import problem
    where importing the agent module pulled in the entire codebase.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        name: str,
        factory: Callable[[], type],
        aliases: list[str] | None = None,
        description: str = "",
    ) -> None:
        """Register a tool with lazy-loading factory.

        Args:
            name: Canonical tool name (e.g., 'review').
            factory: Zero-arg callable that returns the tool class.
            aliases: Alternative names (e.g., 'review_pr' for 'review').
            description: Human-readable description.
        """
        self._tools[name] = ToolEntry(name, factory, description)
        for alias in aliases or []:
            self._aliases[alias] = name

    def get(self, name: str) -> ToolEntry | None:
        """Resolve a tool by name or alias."""
        canonical = self._aliases.get(name, name)
        return self._tools.get(canonical)

    @property
    def command_names(self) -> list[str]:
        """All registered command names including aliases."""
        names = list(self._tools.keys())
        names.extend(self._aliases.keys())
        return names

    def list_tools(self) -> list[dict[str, str]]:
        """List all tools with names and descriptions."""
        return [{"name": entry.name, "description": entry.description} for entry in self._tools.values()]


class ToolEntry:
    """A registered tool with lazy-loading support."""

    __slots__ = ("name", "_factory", "description", "_class")

    def __init__(self, name: str, factory: Callable[[], type], description: str = "") -> None:
        self.name = name
        self._factory = factory
        self.description = description
        self._class: type | None = None

    @property
    def tool_class(self) -> type:
        """Lazily load and cache the tool class."""
        if self._class is None:
            self._class = self._factory()
        return self._class


# ---------------------------------------------------------------------------
# Default tool registry — tools map to their canonical names
# ---------------------------------------------------------------------------


def _default_registry() -> ToolRegistry:
    """Build the default tool registry with all available tools."""
    registry = ToolRegistry()

    registry.register(
        "review",
        _factory("pr_reviewer", "get_reviewer_class"),
        aliases=["review_pr"],
        description="Comprehensive PR review with findings and suggestions",
    )
    registry.register(
        "describe",
        _factory("pr_description", "get_describe_class"),
        aliases=["describe_pr"],
        description="Generate or update PR title and description",
    )
    registry.register(
        "improve",
        _factory("pr_code_suggestions", "get_improve_class"),
        aliases=["improve_code"],
        description="Suggest code improvements as inline comments",
    )
    registry.register(
        "ask",
        _factory("pr_questions", "get_questions_class"),
        aliases=["ask_question"],
        description="Ask questions about the PR",
    )
    registry.register(
        "ask_line",
        _factory("pr_line_questions", "get_line_questions_class"),
        description="Ask questions about specific lines",
    )
    registry.register(
        "update_changelog",
        _factory("pr_update_changelog", "get_update_changelog_class"),
        description="Update CHANGELOG based on PR changes",
    )
    registry.register(
        "config",
        _factory("pr_config", "get_config_class"),
        aliases=["settings"],
        description="Show or modify configuration",
    )
    registry.register(
        "add_docs", _factory("pr_add_docs", "get_add_docs_class"), description="Generate documentation for changes"
    )
    registry.register(
        "generate_labels",
        _factory("pr_generate_labels", "get_generate_labels_class"),
        description="Auto-generate PR labels",
    )
    registry.register(
        "similar_issue",
        _factory("pr_similar_issue", "get_similar_issue_class"),
        description="Find issues similar to this PR",
    )
    registry.register(
        "help", _factory("pr_help_message", "get_help_class"), description="Show help and usage information"
    )

    return registry


def _factory(module_name: str, factory_name: str) -> Callable[[], type]:
    """Return a lazy-import factory for a tool class."""

    def _load() -> type:
        import importlib

        mod = importlib.import_module(f"mergemate.tools.{module_name}")
        return getattr(mod, factory_name)()

    return _load


# ---------------------------------------------------------------------------
# MergeMate Agent
# ---------------------------------------------------------------------------


class MergeMateAgent:
    """Orchestrates PR review commands.

    Accepts its dependencies via constructor injection rather than
    reaching for global singletons. This makes testing trivial and
    the code explicit about what it needs.

    Usage:
        config = AppConfig.load_default()
        agent = MergeMateAgent(config=config)
        await agent.handle("https://github.com/owner/repo/pull/42", ["review"])
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        registry: ToolRegistry | None = None,
        git_provider_factory: Callable[[str], GitProvider] | None = None,
        ai_handler_factory: Callable[[], AIHandler] | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or _default_registry()
        self._git_provider_factory = git_provider_factory or _default_git_provider_factory
        self._ai_handler_factory = ai_handler_factory or _default_ai_handler_factory

    async def handle(self, pr_url: str, request: list[str] | str, *, notify: Callable[[], None] | None = None) -> bool:
        """Handle a PR review command.

        Args:
            pr_url: URL of the pull request.
            request: Command string like '/review' or list of args.
            notify: Optional callback invoked before tool execution (e.g., for Slack notifications).

        Returns:
            True if the command was handled successfully, False otherwise.
        """
        command, args = self._parse_request(request)

        # Security: validate the PR URL before any processing.
        try:
            validate_pr_url(pr_url)
        except SecurityError as exc:
            get_logger().error(f"Security check failed: {exc}", pr_url=pr_url)
            return False

        # Rate limiting: check before processing.
        rate_limiter = _get_default_rate_limiter()
        if not rate_limiter.is_allowed(pr_url):
            get_logger().warning(
                f"Rate limit exceeded for PR, try again later. Remaining: {rate_limiter.remaining(pr_url)}",
                pr_url=pr_url,
            )
            return False

        # Validate the command exists
        entry = self.registry.get(command)
        if entry is None:
            get_logger().warning(f"Unknown command: {command}", pr_url=pr_url)
            return False

        # Build dependencies
        git_provider = self._git_provider_factory(pr_url)
        ai_handler = self._ai_handler_factory()

        # Apply repo-specific config if available
        repo_settings = git_provider.get_repo_settings()
        if repo_settings:
            self.config = self.config.merge_repo_config(repo_settings)

        # Build tool context
        tool_ctx = ToolContext(pr=git_provider.get_pr())

        # Notify if needed
        if notify:
            notify()

        # Execute the tool
        try:
            tool = entry.tool_class(
                pr_url=pr_url,
                config=self.config,
                git_provider=git_provider,
                ai_handler=ai_handler,
                context=tool_ctx,
                args=args,
            )
            await tool.run()
            return True
        except Exception:
            get_logger().exception(f"Tool '{command}' failed", pr_url=pr_url)
            return False

    def _parse_request(self, request: list[str] | str) -> tuple[str, list[str]]:
        """Parse a command request into (command_name, args)."""
        if isinstance(request, str):
            request = request.replace("'", "\\'")
            lexer = shlex.shlex(request, posix=True)
            lexer.whitespace_split = True
            parts = list(lexer)
        else:
            parts = list(request)

        if not parts:
            return "help", []

        command = parts[0].lstrip("/").lower()
        args = parts[1:]
        return command, args


# ---------------------------------------------------------------------------
# Default factory functions (bridge to legacy code during migration)
# ---------------------------------------------------------------------------


def _default_git_provider_factory(pr_url: str) -> GitProvider:
    """Create a git provider using the legacy factory."""
    from mergemate.git_providers import get_git_provider_with_context

    return get_git_provider_with_context(pr_url)


# ---------------------------------------------------------------------------
# Default rate limiter (module-level singleton)
# ---------------------------------------------------------------------------

_default_rate_limiter: RateLimiter | None = None


def _get_default_rate_limiter() -> RateLimiter:
    """Return the module-level rate limiter, creating it on first access."""
    global _default_rate_limiter
    if _default_rate_limiter is None:
        _default_rate_limiter = RateLimiter(max_requests=30, window_seconds=60.0)
    return _default_rate_limiter


def _default_ai_handler_factory() -> AIHandler:
    """Create an AI handler using the new credential-aware pattern."""
    from mergemate.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler, ProviderCredentials
    from mergemate.config_loader import get_settings

    # Build credentials from legacy settings during migration
    raw = {k.upper(): dict(v) if hasattr(v, "items") else v for k, v in get_settings().items() if isinstance(k, str)}
    creds = ProviderCredentials.from_raw_settings(raw)
    return LiteLLMAIHandler(credentials=creds)
