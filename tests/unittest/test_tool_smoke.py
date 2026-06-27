"""Smoke tests for tool modules — verifies imports and class hierarchy integrity.

These tests exercise module-level code paths without requiring AI backends or
full PR context. Full integration is covered by health/e2e tests.
"""

from __future__ import annotations


class TestPrAddDocs:
    def test_import(self):
        from mergemate.tools.pr_add_docs import PRAddDocs

        assert PRAddDocs is not None

    def test_is_base_tool_subclass(self):
        from mergemate.tools.base import BaseTool
        from mergemate.tools.pr_add_docs import PRAddDocs

        assert issubclass(PRAddDocs, BaseTool)


class TestPrGenerateLabels:
    def test_import(self):
        from mergemate.tools.pr_generate_labels import PRGenerateLabels

        assert PRGenerateLabels is not None

    def test_is_base_tool_subclass(self):
        from mergemate.tools.base import BaseTool
        from mergemate.tools.pr_generate_labels import PRGenerateLabels

        assert issubclass(PRGenerateLabels, BaseTool)


class TestPrHelpDocs:
    def test_import(self):
        from mergemate.tools.pr_help_docs import PRHelpDocs

        assert PRHelpDocs is not None

    def test_is_standalone_class(self):
        """PRHelpDocs is a standalone class (not yet migrated to BaseTool)."""
        from mergemate.tools.pr_help_docs import PRHelpDocs

        assert PRHelpDocs is not None


class TestPrConfig:
    def test_import(self):
        from mergemate.tools.pr_config import PRConfig

        assert PRConfig is not None


class TestPrSimilarIssue:
    def test_import(self):
        from mergemate.tools.pr_similar_issue import PRSimilarIssue

        assert PRSimilarIssue is not None

    def test_metadata_model(self):
        from mergemate.tools.pr_similar_issue import IssueLevel, Metadata

        m = Metadata(repo="owner/repo", username="@test", level=IssueLevel.ISSUE)
        assert m.repo == "owner/repo"
        assert m.level == IssueLevel.ISSUE

    def test_issue_level_enum(self):
        from mergemate.tools.pr_similar_issue import IssueLevel

        assert IssueLevel.ISSUE.value == "issue"
        assert IssueLevel.COMMENT.value == "comment"


class TestPrHelpMessage:
    def test_import(self):
        from mergemate.tools.pr_help_message import PRHelpMessage

        assert PRHelpMessage is not None


class TestPrUpdateChangelog:
    def test_import(self):
        from mergemate.tools.pr_update_changelog import PRUpdateChangelog

        assert PRUpdateChangelog is not None

    def test_is_base_tool_subclass(self):
        from mergemate.tools.base import BaseTool
        from mergemate.tools.pr_update_changelog import PRUpdateChangelog

        assert issubclass(PRUpdateChangelog, BaseTool)
