from unittest.mock import MagicMock, patch

import pytest
import yaml

from mergemate.algo.types import FilePatchInfo
from mergemate.tools.pr_description import PRDescription, sanitize_diagram

KEYS_FIX = ["filename:", "language:", "changes_summary:", "changes_title:", "description:", "title:"]


def _make_instance(prediction_yaml: str = ""):
    """Create a PRDescription instance, bypassing __init__."""
    with patch.object(PRDescription, "__init__", lambda self, *a, **kw: None):
        obj = PRDescription.__new__(PRDescription)
    obj._prediction = prediction_yaml
    obj._user_description = ""
    obj._describe_cfg = {}
    obj._vars = {}
    obj._file_label_dict = {}
    obj.pr_url = "1"
    obj.git_provider = MagicMock()
    obj.git_provider.get_pr_id.return_value = "1"
    return obj


def _prediction_with_diagram(diagram_value: str) -> str:
    """Build a minimal YAML prediction string that includes changes_diagram."""
    return yaml.dump(
        {
            "title": "test",
            "description": "test",
            "changes_diagram": diagram_value,
        }
    )


class TestPRDescriptionDiagram:
    def test_diagram_not_starting_with_fence_is_removed(self):
        obj = _make_instance(_prediction_with_diagram("graph LR\nA --> B"))
        data = obj._parse_prediction()
        assert "changes_diagram" not in data

    def test_diagram_missing_closing_fence_is_appended(self):
        obj = _make_instance(_prediction_with_diagram("```mermaid\ngraph LR\nA --> B"))
        data = obj._parse_prediction()
        assert data["changes_diagram"] == "\n```mermaid\ngraph LR\nA --> B\n```"

    def test_backticks_inside_label_are_removed(self):
        obj = _make_instance(_prediction_with_diagram('```mermaid\ngraph LR\nA["`file`"] --> B\n```'))
        data = obj._parse_prediction()
        assert data["changes_diagram"] == '\n```mermaid\ngraph LR\nA["file"] --> B\n```'

    def test_backticks_outside_label_are_kept(self):
        obj = _make_instance(_prediction_with_diagram('```mermaid\ngraph LR\nA["`file`"] -->|`edge`| B\n```'))
        data = obj._parse_prediction()
        assert data["changes_diagram"] == '\n```mermaid\ngraph LR\nA["file"] -->|`edge`| B\n```'

    def test_normal_diagram_only_adds_newline(self):
        obj = _make_instance(_prediction_with_diagram('```mermaid\ngraph LR\nA["file.py"] --> B["output"]\n```'))
        data = obj._parse_prediction()
        assert data["changes_diagram"] == '\n```mermaid\ngraph LR\nA["file.py"] --> B["output"]\n```'

    def test_none_input_returns_empty(self):
        assert sanitize_diagram(None) == ""

    def test_non_string_input_returns_empty(self):
        assert sanitize_diagram(123) == ""

    def test_non_mermaid_fence_returns_empty(self):
        assert sanitize_diagram('```python\nprint("hello")\n```') == ""


class TestPRDescriptionCore:
    def test_prepare_file_labels_groups_valid_files_and_skips_incomplete_entries(self):
        obj = _make_instance()
        obj._vars = {"include_file_summary_changes": True}
        data = {
            "pr_files": [
                {
                    "filename": "src/app.py",
                    "changes_title": "Add cache",
                    "changes_summary": "Adds a bounded cache.",
                    "label": "backend",
                },
                {
                    "filename": "src/skip.py",
                    "changes_title": "Missing summary",
                    "label": "backend",
                },
                {
                    "filename": "docs/readme.md",
                    "changes_title": "Update docs",
                    "changes_summary": "Clarifies setup.",
                    "label": "docs",
                },
            ]
        }

        labels = obj._prepare_file_labels(data)

        assert labels == {
            "backend": [("src/app.py", "Add cache", "Adds a bounded cache.")],
            "docs": [("docs/readme.md", "Update docs", "Clarifies setup.")],
        }

    def test_prepare_pr_answer_with_markers_replaces_plain_and_comment_markers(self):
        obj = _make_instance()
        obj._describe_cfg = {
            "generate_ai_title": True,
            "include_generated_by_header": False,
        }
        obj._vars = {"title": "Original title"}
        obj._file_label_dict = {}
        obj.git_provider = MagicMock()
        obj.git_provider.last_commit_id.sha = "abc123"
        obj._user_description = "mergemate:type\nmergemate:summary\n<!-- mergemate:diagram -->\n"
        data = {
            "title": "AI title",
            "type": "Bug fix",
            "description": "Fixes the cache invalidation bug.",
            "changes_diagram": "\n```mermaid\ngraph LR\nA --> B\n```",
        }

        title, body, walkthrough, file_changes = obj._prepare_pr_answer_with_markers(data)

        assert title == "AI title"
        assert "Bug fix" in body
        assert "Fixes the cache invalidation bug." in body
        assert "```mermaid" in body
        assert walkthrough == ""
        assert file_changes == []

    @pytest.mark.asyncio
    async def test_extend_uncovered_files_adds_missing_diff_files_to_prediction(self):
        obj = _make_instance()
        obj.git_provider = MagicMock()
        obj.git_provider.get_pr_id.return_value = "1"
        obj.git_provider.get_diff_files.return_value = [
            FilePatchInfo("", "", "", "shown.py"),
            FilePatchInfo("", "", "", "missing.py"),
        ]
        prediction = """
pr_files:
  - filename: shown.py
    changes_title: Existing summary
    label: backend
"""

        extended = await obj._extend_uncovered_files(prediction)
        loaded = yaml.safe_load(extended)

        assert [file["filename"].strip() for file in loaded["pr_files"]] == ["shown.py", "missing.py"]
        assert loaded["pr_files"][1]["label"].strip() == "additional files"
