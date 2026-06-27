import pytest

from mergemate.agent.mergemate import _default_registry


def test_help_docs_is_not_registered():
    """Security stopgap: the /help_docs command must be disabled (unregistered)."""
    reg = _default_registry()
    assert reg.get("help_docs") is None
    assert "help_docs" not in reg.command_names


@pytest.mark.asyncio
async def test_help_docs_command_is_not_routed(monkeypatch):
    """An incoming /help_docs command is rejected as unknown."""
    from mergemate.agent.mergemate import MergeMateAgent, _default_registry
    from mergemate.core.config import AppConfig

    config = AppConfig.load_default()

    class _FakeGitProvider:
        def get_pr(self):
            from mergemate.core.types import PullRequest

            return PullRequest(url="https://example.com/test/repo/pull/1")

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
            return "https://example.com/test/repo/pull/1"

        @property
        def is_supported(self):
            return True

    class _FakeAIHandler:
        async def chat_completion(self, *, model, system, user, temperature=0.2, img_path=""):
            return "ok", "ok"

    agent = MergeMateAgent(
        config=config,
        git_provider_factory=lambda url: _FakeGitProvider(),
        ai_handler_factory=_FakeAIHandler,
    )

    result = await agent.handle("https://example.com/test/repo/pull/1", "/help_docs")
    assert result is False, "/help_docs must be rejected as unknown command"
