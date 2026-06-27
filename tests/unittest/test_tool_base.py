"""Tests for the BaseTool abstract class and its shared pipeline helpers."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from mergemate.core.config import AppConfig
from mergemate.core.errors import ToolError
from mergemate.core.types import PullRequest, ToolContext
from mergemate.tools.base import BaseTool

# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing BaseTool
# ---------------------------------------------------------------------------


class _ConcreteTool(BaseTool):
    """Trivial concrete implementation used to exercise BaseTool helpers."""

    @property
    def tool_name(self) -> str:
        return "test_tool"

    async def _prepare(self) -> None:
        pass

    async def _predict(self) -> Any:
        return {"result": "ok"}

    async def _publish(self, result: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeGitProvider:
    def get_pr(self):
        return PullRequest(
            url="https://github.com/test/repo/pull/1",
            title="Test PR",
            description="PR description body",
            branch="feature/x",
            base_branch="main",
        )

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
        return "https://github.com/test/repo/pull/1"

    def is_supported(self, capability=""):
        return True


class FakeAIHandler:
    async def chat_completion(self, *, model, system, user, temperature=0.2, img_path=""):
        return "ai response", "ok"


def _make_tool(**overrides) -> _ConcreteTool:
    """Create a _ConcreteTool with default fakes, overridable per test."""
    kwargs = dict(
        pr_url="https://github.com/test/repo/pull/1",
        config=AppConfig(),
        git_provider=FakeGitProvider(),
        ai_handler=FakeAIHandler(),
        context=ToolContext(pr=PullRequest(url="https://github.com/test/repo/pull/1")),
    )
    kwargs.update(overrides)
    return _ConcreteTool(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBaseToolTemplateVars:
    """Tests for _build_template_vars and Jinja2 rendering."""

    def test_build_template_vars_defaults(self):
        """_build_template_vars returns expected keys from PR context."""
        pr = PullRequest(
            url="https://github.com/test/repo/pull/1",
            title="Add feature X",
            description="This PR adds feature X",
            branch="feature/x",
            base_branch="main",
        )
        tool = _make_tool(context=ToolContext(pr=pr))

        vars_ = tool._build_template_vars()
        assert vars_["pr_url"] == "https://github.com/test/repo/pull/1"
        assert vars_["pr_title"] == "Add feature X"
        assert vars_["pr_description"] == "This PR adds feature X"
        assert vars_["pr_branch"] == "feature/x"
        assert vars_["pr_base_branch"] == "main"

    def test_render_prompt(self):
        """_render_prompt substitutes variables using Jinja2."""
        tool = _make_tool()
        tool._vars = {"name": "world", "count": 42}

        result = tool._render_prompt("Hello {{ name }}, count is {{ count }}")
        assert result == "Hello world, count is 42"

    def test_render_prompt_with_default_filters(self):
        """Jinja2 built-in filters (e.g. upper) work in templates."""
        tool = _make_tool()
        tool._vars = {"name": "world"}

        result = tool._render_prompt("{{ name | upper }}")
        assert result == "WORLD"

    def test_render_prompt_error(self):
        """Undefined variables raise ToolError because StrictUndefined is used."""
        tool = _make_tool()
        tool._vars = {"defined": "value"}

        with pytest.raises(ToolError, match="Failed to render prompt template"):
            tool._render_prompt("Hello {{ undefined_var }}")


class TestBaseToolConfig:
    """Tests for _get_prompts and _get_tool_config."""

    def test_get_prompts(self):
        """_get_prompts retrieves system/user from config raw data."""
        config = AppConfig(
            _raw={
                "pr_test_tool_prompts": {
                    "system": "You are a tester.",
                    "user": "Review {{ pr_title }}",
                },
            },
        )
        tool = _make_tool(config=config)

        prompts = tool._get_prompts()
        assert prompts["system"] == "You are a tester."
        assert prompts["user"] == "Review {{ pr_title }}"

    def test_get_prompts_empty_when_not_configured(self):
        """_get_prompts returns empty strings when no prompt config exists."""
        tool = _make_tool(config=AppConfig())

        prompts = tool._get_prompts()
        assert prompts["system"] == ""
        assert prompts["user"] == ""

    def test_get_tool_config(self):
        """_get_tool_config fetches the tool's configuration section."""
        config = AppConfig(
            _raw={
                "pr_test_tool": {
                    "max_items": 10,
                    "enabled": True,
                },
            },
        )
        tool = _make_tool(config=config)

        tool_config = tool._get_tool_config()
        assert tool_config["max_items"] == 10
        assert tool_config["enabled"] is True

    def test_get_tool_config_empty_when_not_configured(self):
        """_get_tool_config returns an empty dict when no section exists."""
        tool = _make_tool(config=AppConfig())

        tool_config = tool._get_tool_config()
        assert tool_config == {}


class TestBaseToolInheritance:
    """Tests for the abstract base class contract."""

    def test_cannot_instantiate_base_tool_directly(self):
        """Instantiating BaseTool directly raises TypeError (missing abstract methods)."""
        with pytest.raises(TypeError):
            BaseTool(  # type: ignore[abstract]
                pr_url="test",
                config=AppConfig(),
                git_provider=FakeGitProvider(),
                ai_handler=FakeAIHandler(),
                context=ToolContext(pr=PullRequest(url="test")),
            )

    def test_subclass_must_implement_abstract_methods(self):
        """A subclass missing an abstract method cannot be instantiated."""

        class _IncompleteTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "incomplete"

            # _prepare, _predict, _publish are NOT implemented
            async def _prepare(self) -> None:  # type: ignore[empty-body]
                ...

        with pytest.raises(TypeError):
            _IncompleteTool(  # type: ignore[abstract]
                pr_url="test",
                config=AppConfig(),
                git_provider=FakeGitProvider(),
                ai_handler=FakeAIHandler(),
                context=ToolContext(pr=PullRequest(url="test")),
            )

    def test_full_subclass_instantiates(self):
        """A subclass implementing all abstract methods instantiates without error."""
        tool = _ConcreteTool(
            pr_url="test",
            config=AppConfig(),
            git_provider=FakeGitProvider(),
            ai_handler=FakeAIHandler(),
            context=ToolContext(pr=PullRequest(url="test")),
        )
        assert tool.tool_name == "test_tool"
