"""Focused unit tests for /describe output behavior.

These tests target stable helper seams on ``PRDescription`` and the
``process_description`` helper. They avoid LLM/network calls by bypassing
``__init__`` and providing minimal in-memory state.

Coverage:
* ``_parse_prediction`` key reordering, diagram sanitization removal, and
  ``add_original_user_description`` injection.
* ``_prepare_labels`` list/string parsing, fallback-to-type behavior, and
  ``labels_minimal_to_labels_dict`` re-casing.
* ``_prepare_pr_answer_with_markers`` HTML-comment guards, generated-by
  header injection, list-type joining, and the diagram marker dual-format.
* ``_prepare_pr_answer`` non-gfm vs gfm branching, ``enable_pr_type``
  toggling, ``get_labels`` removal, and description bullet formatting.
* ``_process_pr_files_prediction`` gfm-only table rendering.
* Round-trip: ``process_description`` recovers files from a rendered
  walkthrough produced by ``_process_pr_files_prediction``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

from mergemate.algo.types import FilePatchInfo
from mergemate.algo.utils import PRDescriptionHeader, process_description
from mergemate.tools.pr_description import PRDescription


def _make_instance(prediction_yaml: str = "") -> PRDescription:
    """Construct a ``PRDescription`` instance without running ``__init__``."""
    with patch.object(PRDescription, "__init__", lambda self, *a, **kw: None):
        obj = PRDescription.__new__(PRDescription)
    obj._prediction = prediction_yaml
    obj._user_description = ""
    obj._vars = {}
    obj._file_label_dict = {}
    obj._describe_cfg = _describe_cfg()
    obj.pr_url = "1"
    obj._COLLAPSIBLE_FILE_LIST_THRESHOLD = 8
    obj.git_provider = MagicMock()
    obj.git_provider.get_pr_id.return_value = "1"
    return obj


def _describe_cfg(
    *,
    add_original_user_description: bool = False,
    publish_labels: bool = False,
    enable_pr_type: bool = True,
    generate_ai_title: bool = True,
    include_generated_by_header: bool = False,
    enable_semantic_files_types: bool = True,
    collapsible_file_list: str = "adaptive",
    file_table_collapsible_open_by_default: bool = False,
) -> dict:
    """Build a describe config dict with all PR-description knobs the SUT reads."""
    return {
        "add_original_user_description": add_original_user_description,
        "publish_labels": publish_labels,
        "enable_pr_type": enable_pr_type,
        "generate_ai_title": generate_ai_title,
        "include_generated_by_header": include_generated_by_header,
        "enable_semantic_files_types": enable_semantic_files_types,
        "collapsible_file_list": collapsible_file_list,
        "file_table_collapsible_open_by_default": file_table_collapsible_open_by_default,
    }


# ---------------------------------------------------------------------------
# _parse_prediction
# ---------------------------------------------------------------------------
class TestPrepareData:
    def test_keys_are_reordered_in_canonical_sequence(self):
        obj = _make_instance(
            yaml.dump(
                {
                    "pr_files": [],
                    "description": "desc",
                    "labels": ["bug"],
                    "type": "Bug fix",
                    "title": "AI title",
                }
            )
        )

        data = obj._parse_prediction()

        assert list(data.keys()) == ["title", "type", "labels", "description", "pr_files"]

    def test_empty_diagram_key_is_dropped(self):
        obj = _make_instance(
            yaml.dump(
                {
                    "title": "t",
                    "description": "d",
                    "changes_diagram": "graph LR\nA --> B",  # no mermaid fence -> sanitized to ''
                }
            )
        )

        data = obj._parse_prediction()

        assert "changes_diagram" not in data

    def test_user_description_is_injected_when_enabled(self):
        obj = _make_instance(yaml.dump({"title": "t", "description": "d"}))
        obj._describe_cfg = _describe_cfg(add_original_user_description=True)
        obj._user_description = "Original body from user"

        data = obj._parse_prediction()

        assert data["User Description"] == "Original body from user"


# ---------------------------------------------------------------------------
# _prepare_labels
# ---------------------------------------------------------------------------
class TestPrepareLabels:
    def test_labels_list_is_returned_stripped(self):
        obj = _make_instance()
        obj._vars = {}
        data = {"labels": ["  bug ", "perf"]}

        assert obj._prepare_labels(data) == ["bug", "perf"]

    def test_labels_comma_string_is_split(self):
        obj = _make_instance()
        obj._vars = {}
        data = {"labels": "bug, perf , docs"}

        assert obj._prepare_labels(data) == ["bug", "perf", "docs"]

    def test_falls_back_to_type_only_when_publish_labels_enabled(self):
        obj = _make_instance()
        obj._describe_cfg = _describe_cfg(publish_labels=True)
        obj._vars = {}
        data = {"type": "Bug fix, Refactor"}

        assert obj._prepare_labels(data) == ["Bug fix", "Refactor"]

    def test_does_not_fall_back_to_type_when_publish_labels_disabled(self):
        obj = _make_instance()
        obj._describe_cfg = _describe_cfg(publish_labels=False)
        obj._vars = {}
        data = {"type": "Bug fix"}

        assert obj._prepare_labels(data) == []

    def test_labels_minimal_dict_remaps_case(self):
        obj = _make_instance()
        obj._vars = {"labels_minimal_to_labels_dict": {"bug fix": "Bug Fix"}}
        data = {"labels": ["bug fix", "perf"]}

        assert obj._prepare_labels(data) == ["Bug Fix", "perf"]


# ---------------------------------------------------------------------------
# _prepare_pr_answer_with_markers
# ---------------------------------------------------------------------------
class TestPrepareAnswerWithMarkers:
    def _obj_with_user_description(self, user_description: str) -> PRDescription:
        obj = _make_instance()
        obj._vars = {"title": "Original title"}
        obj._user_description = user_description
        obj._describe_cfg = _describe_cfg()
        obj.git_provider = MagicMock()
        obj.git_provider.last_commit_id.sha = "deadbeef"
        return obj

    def test_html_comment_guard_prevents_type_replacement(self):
        body_in = "<!-- mergemate:type -->\nmergemate:type stays raw"
        obj = self._obj_with_user_description(body_in)
        data = {"title": "AI", "type": "Bug fix"}

        _, body, _, _ = obj._prepare_pr_answer_with_markers(data)

        # Guard present -> the plain marker is NOT replaced.
        assert "mergemate:type stays raw" in body
        assert "Bug fix" not in body

    def test_plain_summary_marker_is_replaced(self):
        obj = self._obj_with_user_description("Intro\nmergemate:summary\nOutro")
        data = {"title": "AI", "description": "Adds caching layer."}

        _, body, _, _ = obj._prepare_pr_answer_with_markers(data)

        assert "Adds caching layer." in body
        assert "mergemate:summary" not in body

    def test_generated_by_header_prefixes_replacements(self):
        obj = self._obj_with_user_description("mergemate:type\nmergemate:summary")
        obj._describe_cfg = _describe_cfg(include_generated_by_header=True)
        data = {"title": "AI", "type": "Bug fix", "description": "Fix bug."}

        _, body, _, _ = obj._prepare_pr_answer_with_markers(data)

        assert "### 🤖 Generated by MergeMate at deadbeef" in body
        # Header appears for both replaced markers.
        assert body.count("### 🤖 Generated by MergeMate at deadbeef") == 2

    def test_list_type_is_joined_with_comma(self):
        obj = self._obj_with_user_description("mergemate:type")
        data = {"title": "AI", "type": ["Bug fix", "Refactor"]}

        _, body, _, _ = obj._prepare_pr_answer_with_markers(data)

        assert "Bug fix, Refactor" in body

    def test_diagram_marker_replaces_both_plain_and_html_comment(self):
        diagram = "\n```mermaid\ngraph LR\nA --> B\n```"
        obj = self._obj_with_user_description("First: mergemate:diagram\nSecond: <!-- mergemate:diagram -->")
        data = {"title": "AI", "changes_diagram": diagram}

        _, body, _, _ = obj._prepare_pr_answer_with_markers(data)

        # Both forms are substituted with the diagram.
        assert diagram in body
        # No leftover markers remain.
        assert "mergemate:diagram" not in body.replace("```mermaid", "")

    def test_title_falls_back_when_generate_ai_title_disabled(self):
        obj = self._obj_with_user_description("mergemate:summary")
        obj._describe_cfg = _describe_cfg(generate_ai_title=False)
        data = {"title": "AI Title", "description": "x"}

        title, _, _, _ = obj._prepare_pr_answer_with_markers(data)

        assert title == "Original title"


# ---------------------------------------------------------------------------
# _prepare_pr_answer (non-marker rendering path)
# ---------------------------------------------------------------------------
class TestPrepareAnswer:
    def _obj(self, data: dict, *, gfm: bool = True) -> PRDescription:
        obj = _make_instance()
        obj._test_data = data
        obj._vars = {"title": "Original title"}
        obj._file_label_dict = {}
        obj.git_provider = MagicMock()
        obj.git_provider.is_supported.side_effect = lambda cap: {
            "gfm_markdown": gfm,
            "get_labels": False,
        }.get(cap, False)
        obj.git_provider.get_diff_files.return_value = []
        obj.git_provider.get_line_link.return_value = ""
        return obj

    def test_labels_removed_when_provider_supports_get_labels(self):
        obj = self._obj({"title": "t", "labels": ["bug"], "description": "d"})
        obj.git_provider.is_supported.side_effect = lambda cap: cap in {"gfm_markdown", "get_labels"}

        _, body, _, _ = obj._prepare_pr_answer(obj._test_data, obj._file_label_dict)

        # The Labels section is suppressed for providers with native label support.
        assert "Labels" not in body
        assert "bug" not in body

    def test_type_section_removed_when_disabled(self):
        obj = self._obj({"title": "t", "type": "Bug fix", "description": "d"})
        obj._describe_cfg = _describe_cfg(enable_pr_type=False)

        _, body, _, _ = obj._prepare_pr_answer(obj._test_data, obj._file_label_dict)

        assert "PR Type" not in body
        assert "Bug fix" not in body

    def test_description_list_value_is_joined_and_bullets_spaced(self):
        obj = self._obj(
            {
                "title": "t",
                "description": "Intro\n- one\n- two",
            }
        )

        _, body, _, _ = obj._prepare_pr_answer(obj._test_data, obj._file_label_dict)

        # Bullet readability: single newline before "-" becomes double newline.
        assert "Intro\n\n- one\n\n- two" in body

    def test_diagram_section_uses_header_enum(self):
        diagram = "\n```mermaid\ngraph LR\nA --> B\n```"
        obj = self._obj({"title": "t", "description": "d", "changes_diagram": diagram})

        _, body, _, _ = obj._prepare_pr_answer(obj._test_data, obj._file_label_dict)

        assert f"### {PRDescriptionHeader.DIAGRAM_WALKTHROUGH.value}" in body
        assert "```mermaid" in body

    def test_title_uses_vars_title_when_data_has_no_title(self):
        obj = self._obj({"description": "d"})
        obj._describe_cfg = _describe_cfg(generate_ai_title=False)

        title, _, _, _ = obj._prepare_pr_answer(obj._test_data, obj._file_label_dict)

        assert title == "Original title"


# ---------------------------------------------------------------------------
# _process_pr_files_prediction (gfm vs non-gfm)
# ---------------------------------------------------------------------------
class TestProcessPRFilesPrediction:
    def _obj(self, *, gfm: bool, diff_files=None) -> PRDescription:
        obj = _make_instance()
        obj.git_provider = MagicMock()
        obj.git_provider.is_supported.side_effect = lambda cap: cap == "gfm_markdown" and gfm
        obj.git_provider.get_diff_files.return_value = diff_files or []
        obj.git_provider.get_line_link.return_value = "https://example/blob/main/src/app.py#L1"
        return obj

    def test_non_gfm_provider_skips_table_rendering(self):
        obj = self._obj(gfm=False)
        obj._describe_cfg = _describe_cfg()
        value = {"backend": [("src/app.py", "Add cache", "Adds a bounded cache.")]}

        body, comments = obj._process_pr_files_prediction("PRE", value)

        assert body == "PRE"
        assert comments == []

    def test_gfm_provider_emits_table_with_file_row(self):
        diff = FilePatchInfo("", "", "", "src/app.py")
        diff.num_plus_lines = 5
        diff.num_minus_lines = 2
        obj = self._obj(gfm=True, diff_files=[diff])
        obj._describe_cfg = _describe_cfg()
        value = {"backend": [("src/app.py", "Add cache", "Adds a bounded cache.")]}

        body, comments = obj._process_pr_files_prediction("", value)

        assert body.startswith("<table>")
        assert body.rstrip().endswith("</table>")
        assert "<strong>Backend</strong>" in body
        assert "<strong>app.py</strong>" in body
        assert "+5/-2" in body
        assert comments == []

    def test_adaptive_collapsible_triggers_above_threshold(self):
        obj = self._obj(gfm=True)
        obj._describe_cfg = _describe_cfg(collapsible_file_list="adaptive")
        obj._COLLAPSIBLE_FILE_LIST_THRESHOLD = 1  # force collapsible behavior with 2 files
        value = {
            "backend": [
                ("a.py", "t1", "s1"),
                ("b.py", "t2", "s2"),
            ]
        }

        body, _ = obj._process_pr_files_prediction("", value)

        assert "<details><summary>2 files</summary>" in body


# ---------------------------------------------------------------------------
# Round-trip: process_description recovers structured files from rendering
# ---------------------------------------------------------------------------
class TestRoundTripWithProcessDescription:
    def test_walkthrough_table_round_trips_through_process_description(self):
        obj = _make_instance()
        obj._describe_cfg = _describe_cfg(collapsible_file_list=False)
        diff = FilePatchInfo("", "", "", "src/app.py")
        diff.num_plus_lines = 3
        diff.num_minus_lines = 1
        obj.git_provider = MagicMock()
        obj.git_provider.is_supported.side_effect = lambda cap: cap == "gfm_markdown"
        obj.git_provider.get_diff_files.return_value = [diff]
        obj.git_provider.get_line_link.return_value = "https://example/blob/main/src/app.py#L1"

        value = {"backend": [("src/app.py", "Add cache", "Adds a bounded cache.")]}
        table, _ = obj._process_pr_files_prediction("", value)

        full_description = (
            "Some intro text.\n\n___\n\n"
            f"<details> <summary><h3> {PRDescriptionHeader.FILE_WALKTHROUGH.value}</h3></summary>\n\n"
            f"{table}\n\n</details>\n\n___\n\nFooter"
        )

        base, files = process_description(full_description)

        assert base.startswith("Some intro text.")
        # At least one structured file entry was recovered.
        assert files, "expected process_description to recover at least one file entry"
        recovered = files[0]
        assert recovered["short_file_name"] == "app.py"
        assert recovered["full_file_name"] == "src/app.py"
        assert "Add cache" in recovered["short_summary"]

    def test_process_description_returns_empty_on_empty_input(self):
        assert process_description("") == ("", [])

    def test_process_description_without_walkthrough_returns_full_text(self):
        text = "Just a description without any walkthrough section."
        base, files = process_description(text)
        assert base == text
        assert files == []


# ---------------------------------------------------------------------------
# _prepare_file_labels edge cases not covered elsewhere
# ---------------------------------------------------------------------------
class TestPrepareFileLabelsEdgeCases:
    def test_returns_empty_when_data_missing_pr_files(self):
        obj = _make_instance()
        data = {"title": "t"}
        assert obj._prepare_file_labels(data) == {}

    def test_returns_empty_when_data_is_not_a_dict(self):
        obj = _make_instance()
        assert obj._prepare_file_labels(None) == {}

    def test_filename_quotes_are_normalized(self):
        obj = _make_instance()
        obj._vars = {"include_file_summary_changes": True}
        data = {
            "pr_files": [
                {
                    "filename": 'src/it\'s a "file".py',
                    "changes_title": "T",
                    "changes_summary": "S",
                    "label": "Backend",
                },
            ]
        }

        labels = obj._prepare_file_labels(data)

        # Single and double quotes in filenames are replaced with backticks;
        # labels are lower-cased for grouping.
        assert list(labels.keys()) == ["backend"]
        recovered_name = labels["backend"][0][0]
        assert "'" not in recovered_name
        assert '"' not in recovered_name
