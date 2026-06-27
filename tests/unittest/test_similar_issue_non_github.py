from unittest.mock import MagicMock

import pytest

from mergemate.tools.pr_similar_issue import PRSimilarIssue


@pytest.mark.asyncio
async def test_similar_issue_non_github_publishes_message(monkeypatch):
    class FakeProvider:
        def __init__(self):
            self.comments = []

        def publish_comment(self, body):
            self.comments.append(body)

    fake_provider = FakeProvider()

    class FakeSettings:
        class config:
            git_provider = "gitlab"
            publish_output = True

    monkeypatch.setattr("mergemate.tools.pr_similar_issue.get_settings", lambda: FakeSettings)
    monkeypatch.setattr(
        "mergemate.git_providers.get_git_provider_with_context",
        lambda _: fake_provider,
    )

    # Use __new__ to bypass the constructor (which requires DI arguments).
    # The tool's _prepare and _publish still use get_settings() and
    # get_git_provider_with_context() globally.
    tool = PRSimilarIssue.__new__(PRSimilarIssue)
    tool.pr_url = "https://gitlab.example.com/group/repo/-/merge_requests/1"
    tool.config = MagicMock(publish_output=True)
    tool.args = None

    result = await tool.run()

    assert result == {"supported": False}
    assert fake_provider.comments == ["The /similar_issue tool is currently supported only for GitHub."]


@pytest.mark.asyncio
async def test_similar_issue_non_github_no_publish(monkeypatch):
    class FakeSettings:
        class config:
            git_provider = "gitlab"
            publish_output = False

    monkeypatch.setattr("mergemate.tools.pr_similar_issue.get_settings", lambda: FakeSettings)

    tool = PRSimilarIssue.__new__(PRSimilarIssue)
    tool.pr_url = "https://gitlab.example.com/group/repo/-/merge_requests/1"
    tool.config = MagicMock(publish_output=False)
    tool.args = None

    result = await tool.run()

    assert result == {"supported": False}
