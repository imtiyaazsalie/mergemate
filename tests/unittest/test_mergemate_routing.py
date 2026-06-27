"""Tests for MergeMate agent command routing."""

import pytest

from mergemate.agent.mergemate import MergeMateAgent
from mergemate.core.config import AppConfig
from mergemate.core.types import PullRequest


class FakeGitProvider:
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
    async def chat_completion(self, *, model, system, user, temperature=0.2, img_path=""):
        return "ok", "ok"


def make_agent(config=None):
    return MergeMateAgent(
        config=config or AppConfig.load_default(),
        git_provider_factory=lambda url: FakeGitProvider(),
        ai_handler_factory=FakeAIHandler,
    )


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_request_routes_known_command():
    agent = make_agent()
    handled = await agent.handle("https://github.com/test/repo/pull/1", "/help")
    # help doesn't need AI, just returns config info
    assert handled is True


@pytest.mark.asyncio
async def test_handle_request_returns_false_for_unknown_command():
    agent = make_agent()
    handled = await agent.handle("https://github.com/test/repo/pull/1", "/nonexistent_command_xyz")
    assert handled is False
