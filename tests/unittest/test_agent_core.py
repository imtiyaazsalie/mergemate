"""Tests for MergeMate agent core: ToolRegistry and MergeMateAgent."""

from unittest.mock import Mock

import pytest

from mergemate.agent.mergemate import MergeMateAgent, ToolRegistry
from mergemate.core.config import AppConfig
from mergemate.core.rate_limiter import RateLimiter
from mergemate.core.types import PullRequest

# ---------------------------------------------------------------------------
# Fakes for agent tests (matching conventions in test_mergemate_routing.py)
# ---------------------------------------------------------------------------


class FakeGitProvider:
    """Minimal fake that satisfies the GitProvider protocol."""

    def get_pr(self):
        return PullRequest(url="test")

    def get_repo_settings(self):
        return None

    def get_diff_files(self):
        return []

    def get_files(self):
        return []

    def get_languages(self):
        return {}

    def publish_comment(self, comment, **kwargs):
        pass

    def publish_description(self, title, description):
        pass

    def publish_code_suggestions(self, suggestions):
        pass

    def get_pr_description_full(self):
        return ""

    def get_commit_messages(self):
        return []

    def generate_link_to_relevant_line_number(self, filename, line):
        return ""

    @property
    def pr_url(self):
        return "test"

    def is_supported(self, capability=""):
        return True


class FakeAIHandler:
    """Minimal fake that satisfies the AIHandler protocol."""

    async def chat_completion(self, *, model, system, user, temperature=0.2, img_path=""):
        return "ok", "ok"


def _make_agent():
    """Create a MergeMateAgent wired with fake providers for testing."""
    return MergeMateAgent(
        config=AppConfig.load_default(),
        git_provider_factory=lambda url: FakeGitProvider(),
        ai_handler_factory=FakeAIHandler,
    )


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    """Unit tests for the ToolRegistry lazy-loading registry."""

    def test_registry_register_and_get(self):
        """Register a tool by name and retrieve it via get()."""
        registry = ToolRegistry()
        mock_class = Mock()
        registry.register("review", lambda: mock_class, description="PR review")

        entry = registry.get("review")
        assert entry is not None
        assert entry.name == "review"
        assert entry.description == "PR review"
        assert entry.tool_class is mock_class

    def test_registry_aliases(self):
        """Tool aliases resolve to the same canonical entry."""
        registry = ToolRegistry()
        mock_class = Mock()
        registry.register("review", lambda: mock_class, aliases=["review_pr", "code_review"])

        entry_via_alias = registry.get("review_pr")
        assert entry_via_alias is not None
        assert entry_via_alias.name == "review"
        assert entry_via_alias.tool_class is mock_class

        # Both aliases should resolve
        entry_via_alias2 = registry.get("code_review")
        assert entry_via_alias2 is not None
        assert entry_via_alias2.name == "review"

    def test_registry_unknown_returns_none(self):
        """get() returns None for unregistered names."""
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None
        assert registry.get("also_missing") is None

    def test_registry_lazy_loading(self):
        """Factory is not invoked during register — only when tool_class is accessed."""
        registry = ToolRegistry()
        factory_calls = []

        def factory():
            factory_calls.append(1)
            return Mock()

        registry.register("lazy", factory, description="Lazy tool")

        # Factory must NOT be called during register
        assert len(factory_calls) == 0

        # First access to tool_class triggers the factory
        entry = registry.get("lazy")
        assert entry is not None
        _ = entry.tool_class
        assert len(factory_calls) == 1

        # Second access uses the cached class — factory NOT called again
        _ = entry.tool_class
        assert len(factory_calls) == 1

    def test_registry_command_names(self):
        """command_names includes all canonical names plus aliases."""
        registry = ToolRegistry()
        registry.register("review", lambda: Mock(), aliases=["review_pr"])
        registry.register("describe", lambda: Mock(), aliases=["desc"])
        registry.register("help", lambda: Mock())

        names = registry.command_names
        assert "review" in names
        assert "review_pr" in names
        assert "describe" in names
        assert "desc" in names
        assert "help" in names
        # No duplicate canonical names expected
        assert len([n for n in names if n == "review"]) == 1

    def test_registry_list_tools(self):
        """list_tools returns canonical name/description pairs only (no aliases)."""
        registry = ToolRegistry()
        registry.register("review", lambda: Mock(), description="Review PRs")
        registry.register("describe", lambda: Mock(), description="Describe PRs", aliases=["desc"])

        tools = registry.list_tools()
        assert len(tools) == 2
        assert {"name": "review", "description": "Review PRs"} in tools
        assert {"name": "describe", "description": "Describe PRs"} in tools


# ---------------------------------------------------------------------------
# MergeMateAgent tests
# ---------------------------------------------------------------------------


class TestMergeMateAgent:
    """Integration-style unit tests for the MergeMateAgent orchestrator.

    All external dependencies (git provider, AI handler, rate limiter) are
    faked or monkeypatched — no network calls are made.
    """

    @pytest.mark.asyncio
    async def test_agent_handle_unknown_command(self):
        """Agent returns False when the command is not registered."""
        agent = _make_agent()
        result = await agent.handle("https://github.com/test/repo/pull/1", "/nonexistent_cmd_xyz")
        assert result is False

    @pytest.mark.asyncio
    async def test_agent_rejects_invalid_url(self):
        """Agent returns False when validate_pr_url raises SecurityError.

        Non-HTTPS schemes are rejected before any processing occurs.
        """
        agent = _make_agent()
        # http:// scheme triggers SecurityError in validate_pr_url
        result = await agent.handle("http://github.com/owner/repo/pull/1", "/review")
        assert result is False

    @pytest.mark.asyncio
    async def test_agent_rate_limit_exceeded(self, monkeypatch):
        """Agent returns False when the rate limiter has no remaining capacity."""
        agent = _make_agent()

        # A RateLimiter with max_requests=0 blocks every request
        exhausted = RateLimiter(max_requests=0, window_seconds=60.0)

        import mergemate.agent.mergemate as agent_module

        monkeypatch.setattr(agent_module, "_get_default_rate_limiter", lambda: exhausted)

        result = await agent.handle("https://github.com/test/repo/pull/1", "/review")
        assert result is False
