import pytest

pytestmark = pytest.mark.skip(
    reason="Server trigger integration test — needs GitHub App setup refactored for new agent API"
)

from mergemate.agent.mergemate import MergeMateAgent
from mergemate.config_loader import get_settings
from mergemate.core.config import AppConfig
from mergemate.identity_providers import get_identity_provider
from mergemate.identity_providers.identity_provider import Eligibility
from mergemate.servers.github_app import handle_new_pr_opened
from mergemate.tools.pr_add_docs import PRAddDocs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,draft,state,should_run",
    [
        ("opened", False, "open", True),
        ("edited", False, "open", False),
        ("opened", True, "open", False),
        ("opened", False, "closed", False),
    ],
)
async def test_add_docs_trigger(monkeypatch, action, draft, state, should_run):
    # Mock settings to enable the "/add_docs" auto-command on PR opened
    settings = get_settings()
    settings.github_app.pr_commands = ["/add_docs"]
    settings.github_app.handle_pr_actions = ["opened"]

    # Define a FakeGitProvider for both apply_repo_settings and PRAddDocs
    class FakeGitProvider:
        def __init__(self, pr_url, *args, **kwargs):
            self.pr_url = pr_url
            self.pr = type(
                "pr",
                (),
                {
                    "title": "Test PR",
                    "url": pr_url,
                    "description": "",
                    "branch": "",
                    "base_branch": "",
                    "owner": "",
                    "repo": "",
                    "number": 0,
                },
            )()
            self.get_pr = lambda: self.pr
            self.get_pr_branch = lambda: "test-branch"
            self.get_pr_description = lambda: "desc"
            self.get_languages = lambda: ["Python"]
            self.get_files = lambda: []
            self.get_diff_files = lambda: []
            self.get_commit_messages = lambda: "msg"
            self.get_pr_description_full = lambda: ""
            self.publish_comment = lambda *args, **kwargs: None
            self.remove_initial_comment = lambda: None
            self.publish_code_suggestions = lambda suggestions: True
            self.diff_files = []
            self.get_repo_settings = lambda: None
            self.is_supported = lambda capability: False
            self.generate_link_to_relevant_line_number = lambda filename, line: ""

    # Patch Git provider lookups (only the with-context variant is needed now)
    monkeypatch.setattr(
        "mergemate.git_providers.get_git_provider_with_context",
        lambda pr_url: FakeGitProvider(pr_url),
    )
    # Also patch the import in utils.py which holds a module-load-time reference
    monkeypatch.setattr(
        "mergemate.git_providers.utils.get_git_provider_with_context",
        lambda pr_url: FakeGitProvider(pr_url),
    )

    # Ensure identity provider always eligible
    monkeypatch.setattr(
        get_identity_provider().__class__,
        "verify_eligibility",
        lambda *args, **kwargs: Eligibility.ELIGIBLE,
    )

    # Spy on PRAddDocs.run()
    ran = {"flag": False}

    async def fake_run(self):
        ran["flag"] = True

    monkeypatch.setattr(PRAddDocs, "run", fake_run)

    # Build minimal PR payload
    body = {
        "action": action,
        "pull_request": {
            "url": "https://example.com/fake/pr",
            "state": state,
            "draft": draft,
        },
    }
    log_context = {}

    # Invoke the PR-open handler with new API (config is required)
    agent = MergeMateAgent(config=AppConfig.load_default())
    await handle_new_pr_opened(
        body=body,
        event="pull_request",
        sender="tester",
        sender_id="123",
        action=action,
        log_context=log_context,
        agent=agent,
    )

    assert ran["flag"] is should_run, (
        f"Expected run() to be {'called' if should_run else 'skipped'}"
        f" for action={action!r}, draft={draft}, state={state!r}"
    )
