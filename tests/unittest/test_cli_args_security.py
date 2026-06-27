from unittest.mock import Mock

import pytest

from mergemate.algo.cli_args import CliArgs

FORBIDDEN_ARGS = [
    "--openai.key=secret",
    "--OPENAI.KEY=secret",
    "--config.openai.key=secret",
    "--openai__key=secret",
    "--OPENAI__KEY=secret",
    "--github.webhook_secret=secret",
    "--github_app.private_key=---BEGIN---",
    "--github_app.app_id=123",
    "--github_app.webhook_secret=secret",
    "--github.base_url=https://evil.example",
    "--litellm.api_base=https://evil.example",
    "--litellm.api_type=azure",
    "--litellm.api_version=2024-01-01",
    "--jira.jira_base_url=https://evil.example",
    "--config.url=https://evil.example",
    "--config.uri=https://evil.example",
    "--config.secret_provider=aws",
    "--config.git_provider=github",
    "--config.skip_keys=foo",
    "--auth.bearer_token=abc",
    "--provider.personal_access_token=ghp_xxx",
    "--provider.PERSONAL_ACCESS_TOKEN=ghp_xxx",
    "--config.enable_auto_approval=true",
    "--config.enable_manual_approval=true",
    "--config.enable_comment_approval=true",
    "--config.approve_pr_on_self_review=true",
    "--config.override_deployment_type=app",
    "--config.enable_local_cache=true",
    "--config.local_cache_path=/etc",
    "--config.shared_secret=xxx",
    "--config.app_name=evil",
    "--config.analytics_folder=/tmp",
    "--github__webhook_secret=secret",
    "--github_app__private_key=xxx",
    "--litellm__api_base=https://evil.example",
]

ALLOWED_ARGS_SINGLE = [
    "--pr_reviewer.num_code_suggestions=3",
    "--pr_reviewer.require_tests_review=true",
    "--config.response_language=zh-tw",
    "--pr_description.publish_labels=false",
    "some-positional-arg",
    "yes",
    "because prod is broken",
    "",
]


@pytest.mark.parametrize("forbidden", FORBIDDEN_ARGS)
def test_validate_user_args_rejects_forbidden(forbidden):
    ok, offending = CliArgs.validate_user_args([forbidden])
    assert ok is False, f"Expected {forbidden!r} to be rejected"
    assert isinstance(offending, str) and offending, (
        f"Expected an offending-token string for {forbidden!r}, got {offending!r}"
    )


@pytest.mark.parametrize("allowed", ALLOWED_ARGS_SINGLE)
def test_validate_user_args_accepts_allowed_single(allowed):
    ok, offending = CliArgs.validate_user_args([allowed])
    assert ok is True, f"Expected {allowed!r} to be accepted, but it was rejected as {offending!r}"
    assert offending == ""


def test_validate_user_args_empty_list_is_allowed():
    assert CliArgs.validate_user_args([]) == (True, "")


def test_validate_user_args_none_is_allowed():
    assert CliArgs.validate_user_args(None) == (True, "")


def test_validate_user_args_mixed_allowed_then_forbidden():
    ok, offending = CliArgs.validate_user_args(
        ["--pr_reviewer.num_code_suggestions=3", "--github.webhook_secret=secret"]
    )
    assert ok is False
    assert "webhook_secret" in offending


def test_validate_user_args_all_allowed_together():
    ok, offending = CliArgs.validate_user_args(ALLOWED_ARGS_SINGLE)
    assert ok is True, f"Allowed batch unexpectedly rejected at {offending!r}"
    assert offending == ""


@pytest.mark.asyncio
async def test_cli_parser_rejects_known_secret_args():
    """The CLI parser should not accept args like --openai.key or --github.webhook_secret."""
    from mergemate.cli import build_parser

    parser = build_parser()

    # Verify the parser only has safe, expected arguments
    known_args = {action.dest for action in parser._actions if action.dest != "help"}
    forbidden_patterns = ["key", "secret", "token", "password", "bearer", "private"]
    for arg in known_args:
        for pattern in forbidden_patterns:
            assert pattern not in arg.lower(), f"Potentially unsafe arg found: {arg}"
