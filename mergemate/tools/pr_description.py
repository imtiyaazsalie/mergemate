"""PR Description tool — automated pull request description generation.

Rewritten using the BaseTool pipeline pattern with dependency injection.
Preserves all unique functionality: semantic file labeling, mermaid sanitization,
description markers, large-PR handling, async multi-patch predictions, and
collapsible file walkthrough tables.
"""

from __future__ import annotations

import asyncio
import copy
import re
import traceback
from typing import Any, Tuple

import yaml
from jinja2 import Environment, StrictUndefined

from mergemate.algo.pr_processing import (
    OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD,
    get_pr_diff,
    get_pr_diff_multiple_patchs,
    retry_with_fallback_models,
)
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import (
    ModelType,
    PRDescriptionHeader,
    clip_tokens,
    get_max_tokens,
    get_user_labels,
    load_yaml,
    set_custom_labels,
    show_relevant_configurations,
)
from mergemate.git_providers import GithubProvider
from mergemate.log import get_logger
from mergemate.servers.help import HelpMessage
from mergemate.tools.base import BaseTool
from mergemate.tools.ticket_pr_compliance_check import (
    extract_and_cache_pr_tickets,
)

# ---------------------------------------------------------------------------
# Module-level helpers (unchanged from legacy)
# ---------------------------------------------------------------------------


def sanitize_diagram(diagram_raw: str) -> str:
    """Sanitize a mermaid diagram string: fix missing closing fence and remove backticks."""
    if not isinstance(diagram_raw, str):
        return ""
    diagram = diagram_raw.strip()
    if not diagram.startswith("```mermaid"):
        return ""

    if not diagram.endswith("```"):
        diagram += "\n```"

    result = []
    for line in diagram.split("\n"):
        line = re.sub(
            r'\["([^"]*?)"\]',
            lambda m: '["' + m.group(1).replace("`", "") + '"]',
            line,
        )
        result.append(line)
    return "\n" + "\n".join(result)


def count_chars_without_html(string: str) -> int:
    if "<" not in string:
        return len(string)
    no_html_string = re.sub("<[^>]+>", "", string)
    return len(no_html_string)


def insert_br_after_x_chars(text: str, x: int = 70) -> str:
    """Insert <br> into a string after a word that increases its length above x characters."""
    if not text:
        return ""
    if count_chars_without_html(text) < x:
        return text

    is_list = text.lstrip().startswith(("- ", "* "))
    text = replace_code_tags(text)

    if is_list:
        leading_whitespace = text[: len(text) - len(text.lstrip())]
        body = text.lstrip()
        body = "<li>" + body[2:]
        text = leading_whitespace + body
        text = text.replace("\n- ", "<br><li> ").replace("\n - ", "<br><li> ")
        text = text.replace("\n* ", "<br><li> ").replace("\n * ", "<br><li> ")

    text = text.replace("\n", "<br>")
    lines = text.split("<br>")
    words: list[str] = []
    for i, line in enumerate(lines):
        words += line.split(" ")
        if i < len(lines) - 1:
            words[-1] += "<br>"

    new_text: list[str] = []
    is_inside_code = False
    current_length = 0
    for word in words:
        is_saved_word = word in ("<code>", "</code>", "<li>", "<br>")
        len_word = count_chars_without_html(word)
        if not is_saved_word and (current_length + len_word > x):
            if is_inside_code:
                new_text.append("</code><br><code>")
            else:
                new_text.append("<br>")
            current_length = 0
        new_text.append(word + " ")

        if not is_saved_word:
            current_length += len_word + 1

        if word in ("<li>", "<br>"):
            current_length = 0

        if "<code>" in word:
            is_inside_code = True
        if "</code>" in word:
            is_inside_code = False

    processed_text = "".join(new_text).strip()

    if is_list:
        processed_text = f"<ul>{processed_text}</ul>"

    return processed_text


def replace_code_tags(text: str) -> str:
    """Replace odd instances of ` with <code> and even instances of ` with </code>."""
    parts = text.split("`")
    for i in range(1, len(parts), 2):
        parts[i] = "<code>" + parts[i] + "</code>"
    return "".join(parts)


# ---------------------------------------------------------------------------
# Default prompts
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a PR description generator. Your task is to analyze pull request
code changes and produce a clear, structured JSON description.

You MUST respond in English. Output ONLY valid JSON with these top-level keys:
- title: a concise PR title (English)
- type: the type of change (bug fix, feature, refactor, etc.)
- labels: relevant labels as a list or comma-separated string
- description: a detailed English summary of what the PR does
- pr_files: a list of file entries with filename, changes_title, changes_summary, and label
- changes_diagram (optional): a mermaid diagram describing the changes

Do NOT include any text outside the JSON object. Do NOT use markdown fences.\nBe thorough and professional."""

DEFAULT_USER_PROMPT = """
## PR Information
- Title: {{ pr_title }}
- Branch: {{ pr_branch }} → {{ pr_base_branch }}
- Language: {{ language }}

## PR Description
{{ pr_description }}

## Commit Messages
{{ commit_messages_str }}

## Diff
{{ diff }}

{% if extra_instructions %}
## Extra Instructions
{{ extra_instructions }}
{% endif %}

Please generate a complete PR description in YAML format.
"""


# ---------------------------------------------------------------------------
# PRDescription tool class
# ---------------------------------------------------------------------------


class PRDescription(BaseTool):
    """Generates and publishes a PR description.

    Pipeline:
        1. _prepare() — token handling, diff splitting, prompt building
        2. _predict() — AI model calls (with retry), YAML parsing, file extension
        3. _publish() — labels, description body, file walkthrough, help text

    Dependencies are injected via constructor.
    """

    _COLLAPSIBLE_FILE_LIST_THRESHOLD = 8
    _KEYS_FIX = ["filename:", "language:", "changes_summary:", "changes_title:", "description:", "title:"]

    @property
    def tool_name(self) -> str:
        return "describe"

    # ------------------------------------------------------------------
    # Template vars (extended from BaseTool)
    # ------------------------------------------------------------------

    def _build_template_vars(self) -> dict[str, Any]:
        base = super()._build_template_vars()
        pr = self.context.pr

        main_language = self._get_main_pr_language()

        cfg = self._cfg("pr_description")
        enable_diagram = cfg.get("enable_pr_diagram", False) and self.git_provider.is_supported("gfm_markdown")

        diff_files = self.git_provider.get_diff_files()
        include_file_summary = len(diff_files) <= cfg.get(
            "collapsible_file_list_threshold", self._COLLAPSIBLE_FILE_LIST_THRESHOLD
        )

        return {
            **base,
            "title": pr.title,
            "branch": pr.branch,
            "description": pr.description,
            "language": main_language,
            "diff": "",
            "extra_instructions": cfg.get("extra_instructions", ""),
            "commit_messages_str": self._get_commit_messages_str(),
            "enable_custom_labels": self._raw("config", {}).get("enable_custom_labels", False),
            "custom_labels_class": "",
            "enable_semantic_files_types": cfg.get("enable_semantic_files_types", False),
            "related_tickets": "",
            "include_file_summary_changes": include_file_summary,
            "duplicate_prompt_examples": self._raw("config", {}).get("duplicate_prompt_examples", False),
            "enable_pr_diagram": enable_diagram,
        }

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Gather PR diff, handle token limits, build prompts."""
        get_logger().info(f"Preparing PR description for pr_id: {self._pr_id()}")

        # Ticket extraction
        await extract_and_cache_pr_tickets(self.git_provider, self._vars)

        # Publish "preparing" comment
        cfg = self._cfg("config")
        if cfg.get("publish_output") and not cfg.get("is_auto_command", False):
            self.git_provider.publish_comment("Preparing PR description...", is_temporary=True)

        # Store the user description for marker-based mode
        self._user_description = self._get_user_description()

        # Build the token handler
        prompts = self._get_prompts()
        system_template = prompts.get("system") or DEFAULT_SYSTEM_PROMPT
        user_template = prompts.get("user") or DEFAULT_USER_PROMPT
        self._token_handler = TokenHandler(
            self.git_provider.pr,
            self._vars,
            system_template,
            user_template,
        )

        # Store prompts in _vars for access during prediction
        self._vars["system_prompt_template"] = system_template
        self._vars["user_prompt_template"] = user_template

        # Detect semantic file types support
        describe_cfg = self._cfg("pr_description")
        if describe_cfg.get("enable_semantic_files_types") and not self.git_provider.is_supported("gfm_markdown"):
            get_logger().debug(f"Disabling semantic files types for {self._pr_id()}, gfm_markdown not supported.")
            describe_cfg["enable_semantic_files_types"] = False
            self._vars["enable_semantic_files_types"] = False

        self._describe_cfg = describe_cfg

    async def _predict(self) -> dict[str, Any]:
        """Call the AI model and parse the prediction."""
        await self._prepare_and_predict(self.config.model.model)

        if not self._prediction:
            get_logger().warning(f"Empty prediction, PR: {self._pr_id()}")
            return {"prediction": None, "data": None}

        # Parse prediction YAML into structured data
        try:
            data = self._parse_prediction() or {"title": "", "type": "", "description": "Failed to parse"}
        except Exception as e:
            get_logger().error(f"Failed to parse AI prediction: {e}")
            data = {"title": "", "type": "", "description": f"Parse error: {e}"}

        # Extend with uncovered files if semantic file types are enabled
        if self._describe_cfg.get("enable_semantic_files_types"):
            self._file_label_dict = self._prepare_file_labels(data)
        else:
            self._file_label_dict = {}

        return {"prediction": self._prediction, "data": data, "file_label_dict": self._file_label_dict}

    async def _publish(self, result: dict[str, Any]) -> None:
        """Format and publish the PR description, labels, and walkthrough."""
        data = result.get("data")
        if not data:
            self.git_provider.remove_initial_comment()
            return

        file_label_dict = result.get("file_label_dict", {})

        describe_cfg = self._describe_cfg
        config_cfg = self._cfg("config")

        # Prepare labels
        pr_labels: list[str] = []
        if describe_cfg.get("publish_labels"):
            pr_labels = self._prepare_labels(data)

        # Prepare the PR answer (title + body)
        if describe_cfg.get("use_description_markers"):
            pr_title, pr_body, changes_walkthrough, pr_file_changes = self._prepare_pr_answer_with_markers(data)
        else:
            pr_title, pr_body, changes_walkthrough, pr_file_changes = self._prepare_pr_answer(data, file_label_dict)
            if not self.git_provider.is_supported("publish_file_comments") or not describe_cfg.get(
                "inline_file_summary"
            ):
                pr_body += "\n\n" + changes_walkthrough + "___\n\n"

        get_logger().debug("PR output", artifact={"title": pr_title, "body": pr_body})

        # Add help text
        if self.git_provider.is_supported("gfm_markdown") and describe_cfg.get("enable_help_text"):
            pr_body += (
                "<hr>\n\n<details> <summary><strong>✨ Describe tool usage guide:</strong></summary><hr> \n\n"
                + HelpMessage.get_describe_usage_guide()
                + "\n</details>\n"
            )
        elif describe_cfg.get("enable_help_comment") and self.git_provider.is_supported("gfm_markdown"):
            if isinstance(self.git_provider, GithubProvider):
                pr_body += (
                    "\n\n___\n\n> <details> <summary>  Need help?</summary><li>Type <code>/help how to ...</code> "
                    "in the comments thread for any questions about MergeMate usage.</li><li>Check out the "
                    '<a href="https://imtiyaazsalie.github.io/mergemate/usage-guide/">documentation</a> '
                    "for more information.</li></details>"
                )
            else:
                pr_body += (
                    "\n\n___\n\n<details><summary>Need help?</summary>- Type <code>/help how to ...</code> in the comments "
                    "thread for any questions about MergeMate usage.<br>- Check out the "
                    "<a href='https://imtiyaazsalie.github.io/mergemate/usage-guide/'>documentation</a> for more information.</details>"
                )

        # Output relevant configurations if enabled
        if config_cfg.get("output_relevant_configurations", False):
            pr_body += show_relevant_configurations(relevant_section="pr_description")

        if not config_cfg.get("publish_output", True):
            get_logger().info("PR description generated but not published (publish_output=False).")
            # Store formatted output for MOSAICO / offline capture
            cap = self.config._raw.get("__output_capture__")
            if cap is not None:
                cap[0] = pr_body
            return

        # Publish labels
        if describe_cfg.get("publish_labels") and pr_labels and self.git_provider.is_supported("get_labels"):
            original_labels = self.git_provider.get_pr_labels(update=True)
            get_logger().debug("original labels", artifact=original_labels)
            user_labels = get_user_labels(original_labels)
            new_labels = pr_labels + user_labels
            get_logger().debug("published labels", artifact=new_labels)
            if set(new_labels) != set(original_labels):
                get_logger().info(f"Setting describe labels:\n{new_labels}")
                self.git_provider.publish_labels(new_labels)
            else:
                get_logger().debug("Labels are the same, not updating")

        # Publish description
        if describe_cfg.get("publish_description_as_comment"):
            full_markdown_description = f"## Title\n\n{pr_title.strip()}\n\n___\n{pr_body}"
            if describe_cfg.get("publish_description_as_comment_persistent"):
                self.git_provider.publish_persistent_comment(
                    full_markdown_description,
                    initial_header="## Title",
                    update_header=True,
                    name="describe",
                    final_update_message=False,
                )
            else:
                self.git_provider.publish_comment(full_markdown_description)
        else:
            title_to_publish = pr_title.strip() if describe_cfg.get("generate_ai_title") else None
            self.git_provider.publish_description(title_to_publish, pr_body)

            if describe_cfg.get("final_update_message") and not config_cfg.get("is_auto_command", False):
                latest_commit_url = self.git_provider.get_latest_commit_url()
                if latest_commit_url:
                    pr_url = self.git_provider.get_pr_url()
                    update_comment = f"**[PR Description]({pr_url})** updated to latest commit ({latest_commit_url})"
                    self.git_provider.publish_comment(update_comment)

        self.git_provider.remove_initial_comment()

    # ------------------------------------------------------------------
    # Prediction logic (called via retry_with_fallback_models)
    # ------------------------------------------------------------------

    async def _prepare_and_predict(self, model: str) -> None:
        """Core prediction logic: handle large PR splitting, call AI, parse results."""
        describe_cfg = self._describe_cfg

        # Check for marker mode bailout
        if describe_cfg.get("use_description_markers") and "mergemate:" not in self._user_description:
            get_logger().info(
                "Markers were enabled, but user description does not contain markers. Skipping AI prediction"
            )
            self._prediction = None
            return

        large_pr_handling = (
            describe_cfg.get("enable_large_pr_handling", True)
            and "pr_description_only_files_prompts" in self._raw_all()
        )

        # Auto-detect large PRs and split into chunks
        large_pr_handling = (
            describe_cfg.get("enable_large_pr_handling", True)
            and "pr_description_only_files_prompts" in self._raw_all()
        )

        output = get_pr_diff(
            self.git_provider,
            self._token_handler,
            model,
            large_pr_handling=large_pr_handling,
            return_remaining_files=True,
        )

        if isinstance(output, tuple):
            patches_diff, _remaining_files_list = output
        else:
            patches_diff = output
            _remaining_files_list = []

        if not large_pr_handling or patches_diff:
            self._patches_diff = patches_diff
            if patches_diff:
                get_logger().debug("PR diff", artifact=self._patches_diff)
                self._prediction = await self._call_prediction(model, patches_diff, prompt_key="pr_description_prompt")

                if describe_cfg.get("enable_semantic_files_types"):
                    self._prediction = await self._extend_uncovered_files(self._prediction)
            else:
                get_logger().error(
                    f"Error getting PR diff {self._pr_id()}", artifact={"traceback": traceback.format_exc()}
                )
                self._prediction = None
        else:
            # Large PR: multiple patches
            await self._handle_large_pr(model)

    async def _handle_large_pr(self, model: str) -> None:
        """Handle large PRs with multiple diff patches and async AI calls."""
        get_logger().debug("large_pr_handling for describe")

        # Token handler for files-only prompts
        files_prompts = self._raw("pr_description_only_files_prompts", {})
        token_handler_files = TokenHandler(
            self.git_provider.pr,
            self._vars,
            files_prompts.get("system", ""),
            files_prompts.get("user", ""),
        )

        (
            patches_compressed_list,
            total_tokens_list,
            deleted_files_list,
            remaining_files_list,
            file_dict,
            files_in_patches_list,
        ) = get_pr_diff_multiple_patchs(self.git_provider, token_handler_files, model)

        # Get files prediction for each patch
        results: list[str] = []
        if not self._describe_cfg.get("async_ai_calls"):
            for i, patches in enumerate(patches_compressed_list):
                patches_diff = "\n".join(patches)
                get_logger().debug(f"PR diff number {i + 1} for describe files")
                prediction_files = await self._call_prediction(
                    model, patches_diff, prompt_key="pr_description_only_files_prompts"
                )
                results.append(prediction_files)
        else:
            tasks = []
            for patches in patches_compressed_list:
                if patches:
                    patches_diff = "\n".join(patches)
                    get_logger().debug("async PR diff for describe files")
                    task = asyncio.create_task(
                        self._call_prediction(model, patches_diff, prompt_key="pr_description_only_files_prompts")
                    )
                    tasks.append(task)
            results = await asyncio.gather(*tasks)

        file_description_str_list = []
        for i, result in enumerate(results):
            prediction_files = result.strip().removeprefix("```yaml").strip("`").strip()
            if load_yaml(prediction_files, keys_fix_yaml=self._KEYS_FIX) and prediction_files.startswith("pr_files"):
                prediction_files = prediction_files.removeprefix("pr_files:").strip()
                file_description_str_list.append(prediction_files)
            else:
                get_logger().debug(f"failed to generate predictions in iteration {i + 1} for describe files")

        # Build files walkthrough with token handling for the description prompt
        desc_prompts = self._raw("pr_description_only_description_prompts", {})
        token_handler_desc = TokenHandler(
            self.git_provider.pr,
            self._vars,
            desc_prompts.get("system", ""),
            desc_prompts.get("user", ""),
        )

        files_walkthrough = "\n".join(file_description_str_list)
        files_walkthrough_prompt = copy.deepcopy(files_walkthrough)
        MAX_EXTRA_FILES = 50

        if remaining_files_list:
            files_walkthrough_prompt += "\n\nNo more token budget. Additional unprocessed files:"
            for i, file in enumerate(remaining_files_list):
                files_walkthrough_prompt += f"\n- {file}"
                if i >= MAX_EXTRA_FILES:
                    get_logger().debug(f"Too many remaining files, clipping to {MAX_EXTRA_FILES}")
                    files_walkthrough_prompt += f"\n... and {len(remaining_files_list) - MAX_EXTRA_FILES} more"
                    break
        if deleted_files_list:
            files_walkthrough_prompt += "\n\nAdditional deleted files:"
            for i, file in enumerate(deleted_files_list):
                files_walkthrough_prompt += f"\n- {file}"
                if i >= MAX_EXTRA_FILES:
                    get_logger().debug(f"Too many deleted files, clipping to {MAX_EXTRA_FILES}")
                    files_walkthrough_prompt += f"\n... and {len(deleted_files_list) - MAX_EXTRA_FILES} more"
                    break

        # Clip tokens if needed
        tokens_files_walkthrough = len(token_handler_desc.encoder.encode(files_walkthrough_prompt))
        total_tokens = token_handler_desc.prompt_tokens + tokens_files_walkthrough
        max_tokens_model = get_max_tokens(model)
        if total_tokens > max_tokens_model - OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD:
            files_walkthrough_prompt = clip_tokens(
                files_walkthrough_prompt,
                max_tokens_model - OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD - token_handler_desc.prompt_tokens,
                num_input_tokens=tokens_files_walkthrough,
            )

        # PR header inference
        get_logger().debug("PR diff only description", artifact=files_walkthrough_prompt)
        prediction_headers = await self._call_prediction(
            model, patches_diff=files_walkthrough_prompt, prompt_key="pr_description_only_description_prompts"
        )
        prediction_headers = prediction_headers.strip().removeprefix("```yaml").strip("`").strip()

        files_walkthrough_extended = await self._extend_uncovered_files(files_walkthrough)

        self._prediction = prediction_headers + "\n" + "pr_files:\n" + files_walkthrough_extended
        if not load_yaml(self._prediction, keys_fix_yaml=self._KEYS_FIX):
            get_logger().error(f"Error getting valid YAML in large PR handling for describe {self._pr_id()}")
            if load_yaml(prediction_headers, keys_fix_yaml=self._KEYS_FIX):
                get_logger().debug(f"Using only headers for describe {self._pr_id()}")
                self._prediction = prediction_headers

    async def _call_prediction(self, model: str, patches_diff: str, prompt_key: str = "pr_description_prompt") -> str:
        """Make a single AI prediction call."""
        variables = copy.deepcopy(self._vars)
        variables["diff"] = patches_diff

        set_custom_labels(variables, self.git_provider)

        prompts = self._raw(prompt_key, {})
        system_prompt = self._render_template(prompts.get("system", ""), variables)
        user_prompt = self._render_template(prompts.get("user", ""), variables)

        response, finish_reason = await self.ai_handler.chat_completion(
            model=model,
            temperature=self.config.model.temperature,
            system=system_prompt,
            user=user_prompt,
        )

        return response

    async def _extend_uncovered_files(self, original_prediction: str) -> str:
        """Extend the prediction with files not covered by the AI response."""
        try:
            prediction = original_prediction
            original_loaded = load_yaml(original_prediction, keys_fix_yaml=self._KEYS_FIX)

            if isinstance(original_loaded, list):
                original_dict = {"pr_files": original_loaded}
            else:
                original_dict = original_loaded

            filenames_predicted: list[str] = []
            if original_dict:
                files = original_dict.get("pr_files", [])
                filenames_predicted = [f.get("filename", "").strip() for f in files if isinstance(f, dict)]

            pr_files = self.git_provider.get_diff_files()
            prediction_extra = "pr_files:"
            MAX_EXTRA_FILES = 100
            counter = 0

            for file in pr_files:
                if file.filename in filenames_predicted:
                    continue

                counter += 1
                if counter > MAX_EXTRA_FILES:
                    extra = (
                        "- filename: |\n"
                        "    Additional files not shown\n"
                        "  changes_title: |\n"
                        "    ...\n"
                        "  label: |\n"
                        "    additional files\n"
                    )
                    prediction_extra += "\n" + extra.strip()
                    get_logger().debug(f"Too many remaining files, clipping to {MAX_EXTRA_FILES}")
                    break

                extra = (
                    f"- filename: |\n"
                    f"    {file.filename}\n"
                    f"  changes_title: |\n"
                    f"    ...\n"
                    f"  label: |\n"
                    f"    additional files\n"
                )
                prediction_extra += "\n" + extra.strip()

            if counter > 0:
                get_logger().info(f"Adding {counter} unprocessed extra files to table prediction")
                prediction_extra_dict = load_yaml(prediction_extra, keys_fix_yaml=self._KEYS_FIX)
                if (
                    original_dict
                    and isinstance(original_dict, dict)
                    and isinstance(prediction_extra_dict, dict)
                    and "pr_files" in prediction_extra_dict
                ):
                    if "pr_files" in original_dict:
                        original_dict["pr_files"].extend(prediction_extra_dict["pr_files"])
                    else:
                        original_dict["pr_files"] = prediction_extra_dict["pr_files"]
                    new_yaml = yaml.dump(original_dict)
                    if load_yaml(new_yaml, keys_fix_yaml=self._KEYS_FIX):
                        prediction = new_yaml
                if isinstance(original_prediction, list):
                    prediction = yaml.dump(original_dict["pr_files"])

            return prediction
        except Exception as e:
            get_logger().exception(f"Error extending uncovered files {self._pr_id()}", artifact={"error": e})
            return original_prediction

    # ------------------------------------------------------------------
    # Data parsing
    # ------------------------------------------------------------------

    def _parse_prediction(self) -> dict[str, Any]:
        """Parse the AI prediction YAML into structured data."""
        data = load_yaml(self._prediction.strip(), keys_fix_yaml=self._KEYS_FIX)
        if not isinstance(data, dict):
            get_logger().warning(f"load_yaml returned non-dict: {type(data).__name__}, using raw response")
            # Fallback: use the raw prediction as description
            data = {
                "title": self._vars.get("pr_title", ""),
                "type": "",
                "description": str(data) if data else self._prediction.strip(),
            }

        describe_cfg = self._describe_cfg
        if describe_cfg.get("add_original_user_description") and self._user_description:
            data["User Description"] = self._user_description

        # Re-order keys for consistent output
        ordered: dict[str, Any] = {}
        for key in ("User Description", "title", "type", "labels", "description", "changes_diagram", "pr_files"):
            if key in data:
                ordered[key] = data.pop(key)
        ordered.update(data)

        # Sanitize diagram
        if "changes_diagram" in ordered:
            sanitized = sanitize_diagram(ordered["changes_diagram"])
            if sanitized:
                ordered["changes_diagram"] = sanitized
            else:
                del ordered["changes_diagram"]

        return ordered

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def _prepare_labels(self, data: dict[str, Any]) -> list[str]:
        pr_labels: list[str] = []
        if "labels" in data and data["labels"]:
            if isinstance(data["labels"], list):
                pr_labels = data["labels"]
            elif isinstance(data["labels"], str):
                pr_labels = data["labels"].split(",")
        elif "type" in data and data["type"] and self._describe_cfg.get("publish_labels"):
            if isinstance(data["type"], list):
                pr_labels = data["type"]
            elif isinstance(data["type"], str):
                pr_labels = data["type"].split(",")
        pr_labels = [label.strip() for label in pr_labels]

        # Convert lowercase labels to original case
        try:
            if "labels_minimal_to_labels_dict" in self._vars:
                d: dict = self._vars["labels_minimal_to_labels_dict"]
                for i, label_i in enumerate(pr_labels):
                    if label_i in d:
                        pr_labels[i] = d[label_i]
        except Exception as e:
            get_logger().error(f"Error converting labels to original case {self._pr_id()}: {e}")

        return pr_labels

    # ------------------------------------------------------------------
    # PR answer formatting
    # ------------------------------------------------------------------

    def _prepare_pr_answer_with_markers(self, data: dict[str, Any]) -> Tuple[str, str, str, list[dict]]:
        """Format PR description using user-provided markers in the description body."""
        get_logger().info(f"Using description marker replacements {self._pr_id()}")

        describe_cfg = self._describe_cfg
        ai_title = data.pop("title", self._vars["title"])
        if not describe_cfg.get("generate_ai_title"):
            title = self._vars["title"]
        else:
            title = ai_title

        body = self._user_description
        if describe_cfg.get("include_generated_by_header"):
            ai_header = f"### 🤖 Generated by MergeMate at {self.git_provider.last_commit_id.sha}\n\n"
        else:
            ai_header = ""

        ai_type = data.get("type")
        if ai_type and not re.search(r"<!--\s*mergemate:type\s*-->", body):
            if isinstance(ai_type, list):
                pr_type = ", ".join(str(t) for t in ai_type)
            else:
                pr_type = ai_type
            pr_type = f"{ai_header}{pr_type}"
            body = body.replace("mergemate:type", pr_type)

        ai_summary = data.get("description")
        if ai_summary and not re.search(r"<!--\s*mergemate:summary\s*-->", body):
            summary = f"{ai_header}{ai_summary}"
            body = body.replace("mergemate:summary", summary)

        ai_walkthrough = data.get("pr_files")
        walkthrough_gfm = ""
        pr_file_changes: list[dict] = []
        if ai_walkthrough and not re.search(r"<!--\s*mergemate:walkthrough\s*-->", body):
            try:
                walkthrough_gfm, pr_file_changes = self._process_pr_files_prediction(
                    walkthrough_gfm, self._file_label_dict
                )
                body = body.replace("mergemate:walkthrough", walkthrough_gfm)
            except Exception as e:
                get_logger().error(f"Failing to process walkthrough {self._pr_id()}: {e}")
                body = body.replace("mergemate:walkthrough", "")

        ai_diagram = data.get("changes_diagram")
        if ai_diagram:
            body = re.sub(r"<!--\s*mergemate:diagram\s*-->|mergemate:diagram", ai_diagram, body)

        return title, body, walkthrough_gfm, pr_file_changes

    def _prepare_pr_answer(self, data: dict[str, Any], file_label_dict: dict) -> Tuple[str, str, str, list[dict]]:
        """Format PR description as a standalone markdown body."""
        describe_cfg = self._describe_cfg

        if "labels" in data and self.git_provider.is_supported("get_labels"):
            data.pop("labels")
        if not describe_cfg.get("enable_pr_type"):
            data.pop("type", None)

        ai_title = data.pop("title", self._vars["title"])
        if not describe_cfg.get("generate_ai_title"):
            title = self._vars["title"]
        else:
            title = ai_title

        pr_body, changes_walkthrough = "", ""
        pr_file_changes: list[dict] = []

        items = list(data.items())
        for idx, (key, value) in enumerate(items):
            if key == "changes_diagram":
                pr_body += f"### {PRDescriptionHeader.DIAGRAM_WALKTHROUGH.value}\n\n"
                pr_body += f"{value}\n\n"
                continue
            if key == "pr_files":
                value = file_label_dict
            else:
                key_publish = key.rstrip(":").replace("_", " ").capitalize()
                if key_publish == "Type":
                    key_publish = "PR Type"
                pr_body += f"### **{key_publish}**\n"

            if "walkthrough" in key.lower():
                if self.git_provider.is_supported("gfm_markdown"):
                    pr_body += "<details> <summary>files:</summary>\n\n"
                for file in value:
                    filename = file["filename"].replace("'", "`")
                    description = file["changes_in_file"]
                    pr_body += f"- `{filename}`: {description}\n"
                if self.git_provider.is_supported("gfm_markdown"):
                    pr_body += "</details>\n"
            elif "pr_files" in key.lower() and describe_cfg.get("enable_semantic_files_types"):
                changes_walkthrough_table, pr_file_changes = self._process_pr_files_prediction(
                    changes_walkthrough, value
                )
                if describe_cfg.get("file_table_collapsible_open_by_default", False):
                    initial_status = " open"
                else:
                    initial_status = ""
                changes_walkthrough = (
                    f"<details{initial_status}> <summary><h3> {PRDescriptionHeader.FILE_WALKTHROUGH.value}</h3></summary>\n\n"
                    f"{changes_walkthrough_table}\n\n"
                    f"</details>\n\n"
                )
            elif key.lower().strip() == "description":
                if isinstance(value, list):
                    value = ", ".join(v.rstrip() for v in value)
                value = value.replace("\n-", "\n\n-").strip()
                pr_body += f"{value}\n"
            else:
                if isinstance(value, list):
                    value = ", ".join(v.rstrip() for v in value)
                pr_body += f"{value}\n"

            if idx < len(items) - 1:
                pr_body += "\n\n___\n\n"

        return title, pr_body, changes_walkthrough, pr_file_changes

    # ------------------------------------------------------------------
    # File label / walkthrough formatting
    # ------------------------------------------------------------------

    def _prepare_file_labels(self, data: dict[str, Any]) -> dict[str, list[Tuple[str, str, str]]]:
        """Organize predicted file data into label groups."""
        file_label_dict: dict[str, list[Tuple[str, str, str]]] = {}
        if not data or not isinstance(data, dict) or "pr_files" not in data or not data["pr_files"]:
            return file_label_dict

        for file in data["pr_files"]:
            try:
                required = ["changes_title", "filename", "label"]
                if not all(field in file for field in required):
                    get_logger().warning(
                        f"Missing required fields in file label dict {self._pr_id()}, skipping file",
                        artifact={"file": file},
                    )
                    continue
                if not file.get("changes_title"):
                    get_logger().warning(
                        f"Empty changes title in file label dict {self._pr_id()}, skipping file",
                        artifact={"file": file},
                    )
                    continue
                filename = file["filename"].replace("'", "`").replace('"', "`")
                changes_summary = file.get("changes_summary", "")
                if not changes_summary and self._vars.get("include_file_summary_changes", True):
                    get_logger().warning(
                        f"Empty changes summary in file label dict, skipping file", artifact={"file": file}
                    )
                    continue
                changes_summary = changes_summary.strip()
                changes_title = file["changes_title"].strip()
                label = file.get("label").strip().lower()
                if label not in file_label_dict:
                    file_label_dict[label] = []
                file_label_dict[label].append((filename, changes_title, changes_summary))
            except Exception:
                get_logger().exception(f"Error preparing file label dict {self._pr_id()}")

        return file_label_dict

    def _process_pr_files_prediction(self, pr_body: str, value: dict) -> Tuple[str, list[dict]]:
        """Generate the file walkthrough HTML table."""
        pr_comments: list[dict] = []
        describe_cfg = self._describe_cfg

        use_collapsible = describe_cfg.get("collapsible_file_list")
        num_files = sum(len(v) for v in value.values()) if value else 0
        if use_collapsible == "adaptive":
            use_collapsible = num_files > self._COLLAPSIBLE_FILE_LIST_THRESHOLD

        if not self.git_provider.is_supported("gfm_markdown"):
            return pr_body, pr_comments

        try:
            pr_body += "<table>"
            header = "Relevant files"
            delta = 75
            pr_body += f"""<thead><tr><th></th><th align="left">{header}</th></tr></thead>"""
            pr_body += "<tbody>"

            for semantic_label in value.keys():
                s_label = semantic_label.strip("'").strip('"')
                pr_body += f"""<tr><td><strong>{s_label.capitalize()}</strong></td>"""
                list_tuples = value[semantic_label]

                if use_collapsible:
                    pr_body += f"""<td><details><summary>{len(list_tuples)} files</summary><table>"""
                else:
                    pr_body += "<td><table>"

                for filename, file_changes_title, file_change_description in list_tuples:
                    filename = filename.replace("'", "`").rstrip()
                    filename_publish = filename.split("/")[-1]

                    if file_changes_title and file_changes_title.strip() != "...":
                        file_changes_title_code = f"<code>{file_changes_title}</code>"
                        file_changes_title_code_br = insert_br_after_x_chars(
                            file_changes_title_code, x=(delta - 5)
                        ).strip()
                        if len(file_changes_title_code_br) < (delta - 5):
                            file_changes_title_code_br += "&nbsp; " * ((delta - 5) - len(file_changes_title_code_br))
                        filename_publish = f"<strong>{filename_publish}</strong><dd>{file_changes_title_code_br}</dd>"
                    else:
                        filename_publish = f"<strong>{filename_publish}</strong>"

                    diff_plus_minus = ""
                    delta_nbsp = ""
                    diff_files = self.git_provider.get_diff_files()
                    for f in diff_files:
                        if f.filename.lower().strip("/") == filename.lower().strip("/"):
                            num_plus = f.num_plus_lines
                            num_minus = f.num_minus_lines
                            diff_plus_minus = f"+{num_plus}/-{num_minus}"
                            if len(diff_plus_minus) > 12 or diff_plus_minus == "+0/-0":
                                diff_plus_minus = "[link]"
                            delta_nbsp = "&nbsp; " * max(0, 8 - len(diff_plus_minus))
                            break

                    link = ""
                    if hasattr(self.git_provider, "get_line_link"):
                        filename_clean = filename.strip()
                        link = self.git_provider.get_line_link(filename_clean, relevant_line_start=-1)

                    file_change_description_br = insert_br_after_x_chars(file_change_description, x=(delta - 5))
                    pr_body = self._add_file_data(
                        delta_nbsp,
                        diff_plus_minus,
                        file_change_description_br,
                        filename,
                        filename_publish,
                        link,
                        pr_body,
                    )

                if use_collapsible:
                    pr_body += "</table></details></td></tr>"
                else:
                    pr_body += "</table></td></tr>"

            pr_body += "</tr></tbody></table>"
        except Exception as e:
            get_logger().error(f"Error processing pr files to markdown {self._pr_id()}: {str(e)}")

        return pr_body, pr_comments

    @staticmethod
    def _add_file_data(
        delta_nbsp: str,
        diff_plus_minus: str,
        file_change_description_br: str,
        filename: str,
        filename_publish: str,
        link: str,
        pr_body: str,
    ) -> str:
        if not file_change_description_br:
            pr_body += f"""
<tr>
  <td>{filename_publish}</td>
  <td><a href="{link}">{diff_plus_minus}</a>{delta_nbsp}</td>

</tr>
"""
        else:
            pr_body += f"""
<tr>
  <td>
    <details>
      <summary>{filename_publish}</summary>
<hr>

{filename}

{file_change_description_br}


</details>


  </td>
  <td><a href="{link}">{diff_plus_minus}</a>{delta_nbsp}</td>

</tr>
"""
        return pr_body

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pr_id(self) -> str:
        """Get the PR identifier from the git provider."""
        try:
            return self.git_provider.get_pr_id()
        except AttributeError:
            return self.pr_url

    def _get_main_pr_language(self) -> str:
        """Determine the main language of the PR."""
        try:
            from mergemate.git_providers.git_provider import get_main_pr_language

            return get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())
        except Exception:
            return ""

    def _get_commit_messages_str(self) -> str:
        """Get commit messages as a formatted string."""
        try:
            messages = self.git_provider.get_commit_messages()
            if isinstance(messages, list):
                return "\n".join(messages)
            return str(messages)
        except Exception:
            return ""

    def _get_user_description(self) -> str:
        """Get the user-provided PR description."""
        try:
            return self.git_provider.get_user_description()
        except AttributeError:
            return self.context.pr.description

    def _cfg(self, section: str) -> dict[str, Any]:
        """Access a raw config section."""
        return self.config._raw.get(section, {})

    def _raw(self, key: str, default: Any = None) -> Any:
        """Access any raw config key."""
        return self.config._raw.get(key, default)

    def _raw_all(self) -> dict[str, Any]:
        """Get the full raw config dict."""
        return self.config._raw

    def _render_template(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template with the given variables."""
        environment = Environment(undefined=StrictUndefined)
        return environment.from_string(template_str).render(variables)


# ---------------------------------------------------------------------------
# Factory function for the tool registry
# ---------------------------------------------------------------------------


def get_describe_class() -> type:
    """Return the PRDescription class for the tool registry factory."""
    return PRDescription
