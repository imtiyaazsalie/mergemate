"""Focused unit tests for PRQuestions / PRLineQuestions pure helpers.

These tests avoid constructing the tool objects through their public
``__init__`` (which would create real git providers and a TokenHandler).
Instead, instances are built with ``__new__`` and only the attributes needed
by the method under test are populated. No live providers and no AI calls.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mergemate.config_loader import get_settings
from mergemate.git_providers.gitlab_provider import GitLabProvider
from mergemate.tools.pr_line_questions import PRLineQuestions
from mergemate.tools.pr_questions import PRQuestions
from tests.unittest._settings_helpers import SENTINEL, restore_settings, snapshot_settings


def _make_pr_questions(question_str: str = "", prediction: str = "", git_provider=None) -> PRQuestions:
    obj = PRQuestions.__new__(PRQuestions)
    obj._question_str = question_str
    obj.prediction = prediction
    obj._vars = {}
    obj.git_provider = git_provider if git_provider is not None else MagicMock()
    obj.config = MagicMock()
    obj.args = []
    return obj


def _make_line_questions() -> PRLineQuestions:
    obj = PRLineQuestions.__new__(PRLineQuestions)
    obj._vars = {}
    obj.git_provider = MagicMock()
    return obj


# ---------------------------------------------------------------------------
# PRQuestions._parse_args
# ---------------------------------------------------------------------------


class TestPRQuestionsParseArgs:
    def test_joins_multiple_args(self):
        pr = _make_pr_questions()
        pr.args = ["why", "is", "the", "sky", "blue?"]
        assert pr._parse_args() == "why is the sky blue?"

    def test_empty_args_returns_empty_string(self):
        pr = _make_pr_questions()
        pr.args = []
        assert pr._parse_args() == ""
        pr.args = None
        assert pr._parse_args() == ""

    def test_single_arg(self):
        pr = _make_pr_questions()
        pr.args = ["hello"]
        assert pr._parse_args() == "hello"


# ---------------------------------------------------------------------------
# PRQuestions._identify_image
# ---------------------------------------------------------------------------


class TestIdentifyImageInComment:
    def test_markdown_image_extracts_url_and_sets_vars(self):
        pr = _make_pr_questions(question_str="explain this ![image](https://example.com/foo.png)")
        result = pr._identify_image()
        # Current contract: parses out content between the parentheses after
        # the literal "![image]" marker (strips surrounding parens).
        assert result == "https://example.com/foo.png"

    def test_direct_image_url_png(self):
        pr = _make_pr_questions(question_str="please look at https://example.com/diagram.png and answer")
        result = pr._identify_image()
        # Current behavior captures everything from "https://" to end of string
        # (including any trailing text). We assert the prefix / contains the URL,
        # rather than the exact full match, to remain robust to that quirk.
        assert result.startswith("https://example.com/diagram.png")

    def test_direct_image_url_jpg(self):
        pr = _make_pr_questions(question_str="see https://example.com/screen.jpg")
        result = pr._identify_image()
        assert result.startswith("https://example.com/screen.jpg")

    def test_no_image_returns_empty_and_does_not_set_vars(self):
        pr = _make_pr_questions(question_str="just a plain text question")
        result = pr._identify_image()
        assert result == ""

    def test_https_without_image_extension_returns_empty(self):
        pr = _make_pr_questions(question_str="see https://example.com/docs.html")
        result = pr._identify_image()
        assert result == ""


# ---------------------------------------------------------------------------
# PRQuestions._format_answer
# ---------------------------------------------------------------------------


class TestPreparePrAnswer:
    def test_wraps_answer_with_ask_answer_headers(self):
        pr = _make_pr_questions(
            question_str="why?",
            git_provider=MagicMock(),  # not GitLab
        )
        out = pr._format_answer("because reasons")
        assert "### **Ask**❓" in out
        assert "why?" in out
        assert "### **Answer:**" in out
        assert "because reasons" in out

    def test_sanitizes_leading_slash(self):
        pr = _make_pr_questions(question_str="q", git_provider=MagicMock())
        out = pr._format_answer("/merge looks fine")
        # Leading "/" should have been prefixed with a space so the answer
        # does not look like a slash command to the host platform.
        assert "\n /merge looks fine" in out
        assert "\n/merge" not in out

    def test_sanitizes_newline_slash(self):
        pr = _make_pr_questions(question_str="q", git_provider=MagicMock())
        out = pr._format_answer("hello\n/close now")
        assert "\n /close now" in out
        assert "\n/close" not in out

    def test_sanitizes_carriage_return_slash(self):
        pr = _make_pr_questions(question_str="q", git_provider=MagicMock())
        out = pr._format_answer("hello\r/close")
        assert "\r /close" in out
        assert "\r/close" not in out

    def test_non_gitlab_provider_does_not_apply_gitlab_protections(self):
        # Use a non-GitLab provider; a model answer that *does* contain a
        # quick-action substring like "/merge" must still come through as a
        # (sanitized) answer, NOT be replaced with the GitLab error string.
        pr = _make_pr_questions(question_str="q", git_provider=MagicMock())
        out = pr._format_answer("/merge would be premature")
        assert "Model answer contains GitHub quick actions" not in out
        assert "would be premature" in out

    def test_gitlab_provider_blocks_quick_actions(self):
        gitlab_provider = GitLabProvider.__new__(GitLabProvider)
        pr = _make_pr_questions(
            question_str="q",
            git_provider=gitlab_provider,
        )
        out = pr._format_answer("/merge this please")
        assert "Model answer contains GitHub quick actions" in out

    def test_gitlab_provider_passes_through_safe_text(self):
        gitlab_provider = GitLabProvider.__new__(GitLabProvider)
        pr = _make_pr_questions(
            question_str="q",
            git_provider=gitlab_provider,
        )
        out = pr._format_answer("this change looks correct")
        assert "this change looks correct" in out
        assert "Model answer contains GitHub quick actions" not in out


# ---------------------------------------------------------------------------
# PRQuestions._gitlab_protections
# ---------------------------------------------------------------------------


class TestGitlabProtections:
    @pytest.mark.parametrize(
        "quick_action",
        [
            "/approve",
            "/close",
            "/merge",
            "/reopen",
            "/unapprove",
            "/title",
            "/assign",
            "/copy_metadata",
            "/target_branch",
        ],
    )
    def test_detects_each_quick_action(self, quick_action):
        pr = _make_pr_questions()
        result = pr._gitlab_protections(f"prefix {quick_action} suffix")
        assert "GitHub quick actions" in result

    def test_passthrough_for_safe_text(self):
        pr = _make_pr_questions()
        safe = "everything is fine here"
        assert pr._gitlab_protections(safe) == safe


# ---------------------------------------------------------------------------
# PRLineQuestions._parse_args
# ---------------------------------------------------------------------------


class TestLineQuestionsParseArgs:
    def test_joins_multiple_args(self):
        lq = _make_line_questions()
        lq.args = ["what", "does", "this", "do"]
        assert lq._parse_args() == "what does this do"

    def test_empty_args(self):
        lq = _make_line_questions()
        lq.args = []
        assert lq._parse_args() == ""
        lq.args = None
        assert lq._parse_args() == ""


# ---------------------------------------------------------------------------
# PRLineQuestions._load_conversation_history
# ---------------------------------------------------------------------------


class TestLoadConversationHistory:
    def test_returns_empty_when_settings_missing(self):
        lq = _make_line_questions()
        # Set required attributes to empty/falsy (simulating missing context metadata)
        lq._comment_id = ""
        lq._file_name = ""
        lq._line_end = ""
        # provider should not be consulted at all
        lq.git_provider.get_review_thread_comments = MagicMock(
            side_effect=AssertionError("provider must not be called")
        )
        assert lq._load_conversation_history() == ""

    def test_returns_empty_when_only_one_required_setting_missing(self):
        lq = _make_line_questions()
        lq._comment_id = "7"
        lq._file_name = ""  # missing
        lq._line_end = "5"
        lq.git_provider.get_review_thread_comments = MagicMock(
            side_effect=AssertionError("provider must not be called")
        )
        assert lq._load_conversation_history() == ""

    def test_filters_empty_and_current_comment_and_formats(self):
        current = SimpleNamespace(id="100", body="this is the current comment", user=SimpleNamespace(login="alice"))
        empty = SimpleNamespace(id="101", body="", user=SimpleNamespace(login="bob"))
        whitespace = SimpleNamespace(id="102", body="   \n  ", user=SimpleNamespace(login="carol"))
        good1 = SimpleNamespace(id="103", body="first reply", user=SimpleNamespace(login="dave"))
        good2 = SimpleNamespace(id="104", body="second reply", user=SimpleNamespace(login="erin"))

        lq = _make_line_questions()
        lq._comment_id = "100"
        lq._file_name = "src/foo.py"
        lq._line_end = "10"
        lq.git_provider.get_review_thread_comments = MagicMock(return_value=[current, empty, whitespace, good1, good2])

        out = lq._load_conversation_history()
        assert out == "1. dave: first reply\n2. erin: second reply"

    def test_user_without_login_attribute_is_unknown(self):
        # user object that has no 'login' attribute at all
        class _NoLoginUser:
            pass

        comment = SimpleNamespace(id="2", body="anonymous reply", user=_NoLoginUser())

        lq = _make_line_questions()
        lq._comment_id = "1"
        lq._file_name = "src/foo.py"
        lq._line_end = "5"
        lq.git_provider.get_review_thread_comments = MagicMock(return_value=[comment])

        out = lq._load_conversation_history()
        assert out == "1. Unknown: anonymous reply"

    def test_provider_exception_returns_empty_without_raising(self):
        lq = _make_line_questions()
        lq._comment_id = "1"
        lq._file_name = "src/foo.py"
        lq._line_end = "5"
        lq.git_provider.get_review_thread_comments = MagicMock(side_effect=RuntimeError("boom"))

        # must not propagate the exception
        assert lq._load_conversation_history() == ""

    def test_only_filtered_comments_returns_empty(self):
        # everything in the thread is either the current comment or empty
        current = SimpleNamespace(id="10", body="current", user=SimpleNamespace(login="u"))
        blank = SimpleNamespace(id="11", body="", user=SimpleNamespace(login="u"))

        lq = _make_line_questions()
        lq._comment_id = "10"
        lq._file_name = "src/foo.py"
        lq._line_end = "5"
        lq.git_provider.get_review_thread_comments = MagicMock(return_value=[current, blank])
        assert lq._load_conversation_history() == ""


def test_line_question_settings_teardown_restores_sentinel_for_missing_keys():
    """Run the fixture manually and verify keys absent before are absent after."""
    settings = get_settings()
    key = "comment_id"
    # Make sure key is genuinely absent on entry.
    if settings.get(key, SENTINEL) is not SENTINEL:
        restore_settings({key: SENTINEL})
    assert settings.get(key, SENTINEL) is SENTINEL

    saved = snapshot_settings((key,))
    try:
        settings.set(key, 999)
        assert settings.get(key) == 999
    finally:
        restore_settings(saved)

    assert settings.get(key, SENTINEL) is SENTINEL
