"""PR Code Suggestions tool — AI-powered code improvement suggestions.

Rewritten using the BaseTool pipeline pattern with dependency injection.
Preserves all unique functionality: self-reflection loop, dual publishing mode,
persistent comment history, code dedent, decoupled hunks with line numbers,
summarized suggestions table, score mechanism, and progress comments.
"""

from __future__ import annotations

import asyncio
import copy
import difflib
import re
import textwrap
from datetime import datetime
from typing import Any

from jinja2 import Environment, StrictUndefined

from mergemate.algo import MAX_TOKENS
from mergemate.algo.git_patch_processing import decouple_and_convert_to_hunks_with_lines_numbers
from mergemate.algo.pr_processing import (
    add_ai_metadata_to_diff_files,
    get_pr_multi_diffs,
    retry_with_fallback_models,
)
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import (
    ModelType,
    clip_tokens,
    get_max_tokens,
    get_model,
    load_yaml,
    replace_code_tags,
    show_relevant_configurations,
)
from mergemate.git_providers import GithubProvider
from mergemate.git_providers.git_provider import get_main_pr_language
from mergemate.log import get_logger
from mergemate.servers.help import HelpMessage
from mergemate.tools.base import BaseTool
from mergemate.tools.pr_description import insert_br_after_x_chars
from mergemate.tools.progress_comment import build_progress_comment

# ---------------------------------------------------------------------------
# Default prompts
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a code review assistant specializing in code improvement suggestions.
Your task is to analyze pull request diffs and provide actionable code suggestions.

For each suggestion, provide:
- one_sentence_summary: a brief summary of the suggestion
- label: the category (e.g., performance, security, readability, bug)
- relevant_file: the file path
- relevant_lines_start: the starting line number
- relevant_lines_end: the ending line number
- suggestion_content: detailed description of the suggested change
- existing_code: the current code snippet
- improved_code: the improved code snippet

You MUST output ONLY valid JSON with a "code_suggestions" list. No markdown, no explanation."""

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

Provide {{ num_code_suggestions }} code suggestions in JSON format. Output ONLY the JSON object.
"""

DEFAULT_REFLECT_SYSTEM_PROMPT = """You are a code review quality evaluator. Your task is to score code
suggestions on their relevance and correctness.

For each suggestion, provide:
- suggestion_score: integer from 1-10 rating the suggestion's quality
- why: brief explanation of the score
- relevant_lines_start: corrected starting line number (or -1 if invalid)
- relevant_lines_end: corrected ending line number (or -1 if invalid)

Output valid YAML with a `code_suggestions` list of evaluations."""

DEFAULT_REFLECT_USER_PROMPT = """
## PR Diff
{{ diff }}

## Code Suggestions to Evaluate
{{ suggestion_str }}

Evaluate each suggestion and provide scores with reasoning.
"""


# ---------------------------------------------------------------------------
# PRCodeSuggestions tool class
# ---------------------------------------------------------------------------


class PRCodeSuggestions(BaseTool):
    """Generates and publishes code improvement suggestions for a PR.

    Pipeline:
        1. _prepare() — token handling, diff splitting, prompt building
        2. _predict() — parallel AI calls, self-reflection, suggestion parsing
        3. _publish() — summarized table, persistent comments, dual publishing

    Dependencies are injected via constructor.
    """

    @property
    def tool_name(self) -> str:
        return "improve"

    # ------------------------------------------------------------------
    # Template vars (extended from BaseTool)
    # ------------------------------------------------------------------

    def _build_template_vars(self) -> dict[str, Any]:
        base = super()._build_template_vars()
        pr = self.context.pr

        main_language = self._get_main_pr_language()
        config_cfg = self._cfg("config")

        # Determine number of suggestions per chunk
        num_suggestions = int(self._cfg("pr_code_suggestions").get("num_code_suggestions_per_chunk", 4))

        return {
            **base,
            "title": pr.title,
            "branch": pr.branch,
            "description": pr.description,
            "language": main_language,
            "diff": "",
            "diff_no_line_numbers": "",
            "num_code_suggestions": num_suggestions,
            "extra_instructions": self._cfg("pr_code_suggestions").get("extra_instructions", ""),
            "commit_messages_str": self._get_commit_messages_str(),
            "relevant_best_practices": "",
            "is_ai_metadata": config_cfg.get("enable_ai_metadata", False),
            "focus_only_on_problems": self._cfg("pr_code_suggestions").get("focus_only_on_problems", False),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "duplicate_prompt_examples": config_cfg.get("duplicate_prompt_examples", False),
        }

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Gather PR files, build token handler, select prompts."""
        if not self.git_provider.get_files():
            get_logger().info(f"PR has no files: {self.pr_url}, skipping code suggestions")
            self._skip = True
            return

        self._skip = False
        get_logger().info("Preparing code suggestions for PR...")

        cfg = self._cfg("pr_code_suggestions")
        config_cfg = self._cfg("config")

        # Build progress comment for publishing
        self._progress = build_progress_comment()
        self._progress_response = None

        # Publish "Preparing suggestions..." comment
        if (
            config_cfg.get("publish_output")
            and config_cfg.get("publish_output_progress")
            and not config_cfg.get("is_auto_command", False)
        ):
            if self.git_provider.is_supported("gfm_markdown"):
                self._progress_response = self.git_provider.publish_comment(self._progress)
            else:
                self.git_provider.publish_comment("Preparing suggestions...", is_temporary=True)

        # Get PR description (possibly with AI metadata)
        pr_description, pr_description_files = self.git_provider.get_pr_description(split_changes_walkthrough=True)
        self._pr_description = pr_description
        self._pr_description_files = pr_description_files

        if (
            pr_description_files
            and config_cfg.get("is_auto_command", False)
            and config_cfg.get("enable_ai_metadata", False)
        ):
            add_ai_metadata_to_diff_files(self.git_provider, pr_description_files)
            get_logger().debug("AI metadata added to this command")
        else:
            # Disable AI metadata for this run
            self._vars["is_ai_metadata"] = False
            get_logger().debug("AI metadata is disabled for this command")

        # Select prompts based on decouple mode
        decouple = cfg.get("decouple_hunks", True)
        if decouple:
            system_template = self._raw("pr_code_suggestions_prompt", {}).get("system") or DEFAULT_SYSTEM_PROMPT
            user_template = self._raw("pr_code_suggestions_prompt", {}).get("user") or DEFAULT_USER_PROMPT
        else:
            system_template = (
                self._raw("pr_code_suggestions_prompt_not_decoupled", {}).get("system") or DEFAULT_SYSTEM_PROMPT
            )
            user_template = self._raw("pr_code_suggestions_prompt_not_decoupled", {}).get("user") or DEFAULT_USER_PROMPT

        # Build token handler
        self._token_handler = TokenHandler(
            self.git_provider.pr,
            self._vars,
            system_template,
            user_template,
        )

        self._system_template = system_template
        self._user_template = user_template
        self._decouple = decouple
        self._cfg_suggestions = cfg
        self._cfg_config = config_cfg

    async def _predict(self) -> dict[str, Any]:
        """Call the AI models (with retry), self-reflect, and parse suggestions."""
        if getattr(self, "_skip", False):
            return {"code_suggestions": []}

        data = await retry_with_fallback_models(self._prepare_prediction_main, model_type=ModelType.REGULAR)
        if not data:
            data = {"code_suggestions": []}
        return data

    async def _publish(self, result: dict[str, Any]) -> None:
        """Publish code suggestions as PR comment and/or inline suggestions."""
        data = result
        if getattr(self, "_skip", False):
            return

        config_cfg = self._cfg_config
        cfg = self._cfg_suggestions

        if data is None or "code_suggestions" not in data or not data["code_suggestions"]:
            get_logger().warning(
                f"No code suggestions found in AI response. Data keys: {list(data.keys()) if data else 'None'}. Suggestions count: {len(data.get('code_suggestions', [])) if data else 0}"
            )
            await self._publish_no_suggestions()
            return

        if not config_cfg.get("publish_output", True):
            get_logger().info("Code suggestions generated but not published (publish_output=False).")
            pr_body = self._generate_summarized_suggestions(data)
            # Store formatted output for MOSAICO / offline capture
            cap = self.config._raw.get("__output_capture__")
            if cap is not None:
                cap[0] = pr_body
            return

        # Remove temporary comment
        get_logger().info(f"Publishing {len(data.get('code_suggestions', []))} code suggestions")
        self.git_provider.remove_initial_comment()

        if not cfg.get("commitable_code_suggestions") and self.git_provider.is_supported("gfm_markdown"):
            # Generate summarized suggestions table
            pr_body = self._generate_summarized_suggestions(data)
            get_logger().debug("PR output", artifact=pr_body)

            # Self-review checkbox
            if cfg.get("demand_code_suggestions_self_review"):
                pr_body = self._add_self_review_text(pr_body)

            # Chat text for auto commands on GitHub
            if (
                cfg.get("enable_chat_text")
                and config_cfg.get("is_auto_command")
                and isinstance(self.git_provider, GithubProvider)
            ):
                pr_body += (
                    "\n\n>💡 Need additional feedback ? start a "
                    "[PR chat](https://chromewebstore.google.com/detail/ephlnjeghhogofkifjloamocljapahnl) \n\n"
                )

            # Help text
            if cfg.get("enable_help_text"):
                pr_body += (
                    "<hr>\n\n<details> <summary><strong>💡 Tool usage guide:</strong></summary><hr> \n\n"
                    + HelpMessage.get_improve_usage_guide()
                    + "\n</details>\n"
                )

            # Output relevant configurations
            if config_cfg.get("output_relevant_configurations", False):
                pr_body += show_relevant_configurations(relevant_section="pr_code_suggestions")

            # Publish the PR comment
            if cfg.get("persistent_comment", True):
                self._publish_persistent_comment_with_history(
                    self.git_provider,
                    pr_body,
                    initial_header="## PR Code Suggestions ✨",
                    update_header=True,
                    name="suggestions",
                    final_update_message=False,
                    max_previous_comments=cfg.get("max_history_len", 4),
                    progress_response=self._progress_response,
                )
            else:
                if self._progress_response:
                    self.git_provider.edit_comment(self._progress_response, body=pr_body)
                else:
                    self.git_provider.publish_comment(pr_body)

            # Dual publishing mode
            if int(cfg.get("dual_publishing_score_threshold", 0)) > 0:
                await self._dual_publishing(data)
        else:
            await self._push_inline_code_suggestions(data)
            if self._progress_response:
                self.git_provider.remove_comment(self._progress_response)

    # ------------------------------------------------------------------
    # Main prediction logic
    # ------------------------------------------------------------------

    async def _prepare_prediction_main(self, model: str) -> dict[str, Any]:
        """Get PR diffs and make parallel/sequential AI prediction calls."""
        cfg = self._cfg_suggestions

        if self._decouple:
            # Decoupled hunks with line numbers
            patches_diff_list = get_pr_multi_diffs(
                self.git_provider,
                self._token_handler,
                model,
                max_calls=cfg.get("max_number_of_calls", 5),
                add_line_numbers=True,
            )
            patches_diff_list_no_line_numbers = self._remove_line_numbers(patches_diff_list)
        else:
            # Non-decoupled hunks
            patches_diff_list_no_line_numbers = get_pr_multi_diffs(
                self.git_provider,
                self._token_handler,
                model,
                max_calls=cfg.get("max_number_of_calls", 5),
                add_line_numbers=False,
            )
            patches_diff_list = await self._convert_to_decoupled_with_line_numbers(
                patches_diff_list_no_line_numbers, model
            )
            if not patches_diff_list:
                # Fallback to decoupled hunks
                patches_diff_list = get_pr_multi_diffs(
                    self.git_provider,
                    self._token_handler,
                    model,
                    max_calls=cfg.get("max_number_of_calls", 5),
                    add_line_numbers=True,
                )

        if not patches_diff_list:
            get_logger().warning("Empty PR diff list")
            return None

        get_logger().info(f"Number of PR chunk calls: {len(patches_diff_list)}")

        # Parallel or sequential AI calls
        if cfg.get("parallel_calls"):
            prediction_list = await asyncio.gather(
                *[
                    self._get_prediction(model, patches_diff, patches_diff_no_lines)
                    for patches_diff, patches_diff_no_lines in zip(patches_diff_list, patches_diff_list_no_line_numbers)
                ]
            )
        else:
            prediction_list = []
            for patches_diff, patches_diff_no_lines in zip(patches_diff_list, patches_diff_list_no_line_numbers):
                prediction = await self._get_prediction(model, patches_diff, patches_diff_no_lines)
                prediction_list.append(prediction)

        # Aggregate results with score threshold filtering
        data: dict[str, list] = {"code_suggestions": []}
        score_threshold = max(1, int(cfg.get("suggestions_score_threshold", 1)))
        for j, predictions in enumerate(prediction_list):
            if "code_suggestions" in predictions:
                for i, pred in enumerate(predictions["code_suggestions"]):
                    try:
                        score = int(pred.get("score", 1))
                        if score >= score_threshold:
                            data["code_suggestions"].append(pred)
                        else:
                            get_logger().info(
                                f"Removing suggestion {i} from call {j}, score={score} < threshold={score_threshold}",
                                artifact=pred,
                            )
                    except Exception as e:
                        get_logger().error(
                            f"Error processing suggestion {i} in call {j}: {e}",
                            artifact={"prediction": pred},
                        )

        return data

    async def _get_prediction(self, model: str, patches_diff: str, patches_diff_no_line_numbers: str) -> dict:
        """Call the AI model and self-reflect on the suggestions."""
        variables = copy.deepcopy(self._vars)
        variables["diff"] = patches_diff
        variables["diff_no_line_numbers"] = patches_diff_no_line_numbers

        system_prompt = self._render_template(self._system_template, variables)
        user_prompt = self._render_template(self._user_template, variables)

        response, _finish_reason = await self.ai_handler.chat_completion(
            model=model,
            temperature=self.config.model.temperature,
            system=system_prompt,
            user=user_prompt,
        )

        data = self._parse_code_suggestions(response)

        # Self-reflection on suggestions
        model_reflect = get_model("model_reasoning")
        fallbacks = self.config.model.fallback_models
        if (
            model_reflect == self.config.model.model
            and model != self.config.model.model
            and fallbacks
            and model == fallbacks[0]
        ):
            get_logger().warning("Using the same model for self-reflection as the one used for suggestions")
            model_reflect = model

        response_reflect = await self._self_reflect_on_suggestions(
            data["code_suggestions"], patches_diff, model=model_reflect
        )
        if response_reflect:
            self._analyze_self_reflection_response(data, response_reflect)
        else:
            for suggestion in data["code_suggestions"]:
                suggestion["score"] = 7
                suggestion["score_why"] = ""

        return data

    # ------------------------------------------------------------------
    # Self-reflection
    # ------------------------------------------------------------------

    async def _self_reflect_on_suggestions(
        self,
        suggestion_list: list,
        patches_diff: str,
        model: str,
        prev_suggestions_str: str = "",
        dedicated_prompt: str = "",
    ) -> str:
        """Ask the AI to score and validate its own suggestions."""
        if not suggestion_list:
            return ""

        try:
            suggestion_str = ""
            for i, suggestion in enumerate(suggestion_list):
                suggestion_str += f"suggestion {i + 1}: " + str(suggestion) + "\n\n"

            variables: dict[str, Any] = {
                "suggestion_list": suggestion_list,
                "suggestion_str": suggestion_str,
                "diff": patches_diff,
                "num_code_suggestions": len(suggestion_list),
                "prev_suggestions_str": prev_suggestions_str,
                "is_ai_metadata": self._vars.get("is_ai_metadata", False),
                "duplicate_prompt_examples": self._vars.get("duplicate_prompt_examples", False),
            }

            if dedicated_prompt:
                reflect_cfg = self._raw(dedicated_prompt, {})
                system_reflect = self._render_template(reflect_cfg.get("system", ""), variables)
                user_reflect = self._render_template(reflect_cfg.get("user", ""), variables)
            else:
                reflect_cfg = self._raw("pr_code_suggestions_reflect_prompt", {})
                system_reflect = self._render_template(
                    reflect_cfg.get("system") or DEFAULT_REFLECT_SYSTEM_PROMPT, variables
                )
                user_reflect = self._render_template(reflect_cfg.get("user") or DEFAULT_REFLECT_USER_PROMPT, variables)

            with get_logger().contextualize(command="self_reflect_on_suggestions"):
                response_reflect, _reflect_reason = await self.ai_handler.chat_completion(
                    model=model,
                    system=system_reflect,
                    temperature=self.config.model.temperature,
                    user=user_reflect,
                )
        except Exception as e:
            get_logger().info(f"Could not reflect on suggestions, error: {e}")
            return ""

        return response_reflect

    def _analyze_self_reflection_response(self, data: dict, response_reflect: str) -> None:
        """Parse the self-reflection response and update suggestion scores."""
        response_reflect_yaml = load_yaml(response_reflect)
        code_suggestions_feedback = response_reflect_yaml.get("code_suggestions", [])

        if not code_suggestions_feedback or len(code_suggestions_feedback) != len(data["code_suggestions"]):
            for suggestion in data["code_suggestions"]:
                suggestion["score"] = 7
                suggestion["score_why"] = ""
            return

        for i, suggestion in enumerate(data["code_suggestions"]):
            try:
                suggestion["score"] = code_suggestions_feedback[i]["suggestion_score"]
                suggestion["score_why"] = code_suggestions_feedback[i]["why"]

                if "relevant_lines_start" not in suggestion:
                    relevant_lines_start = code_suggestions_feedback[i].get("relevant_lines_start", -1)
                    relevant_lines_end = code_suggestions_feedback[i].get("relevant_lines_end", -1)
                    suggestion["relevant_lines_start"] = relevant_lines_start
                    suggestion["relevant_lines_end"] = relevant_lines_end
                    if relevant_lines_start < 0 or relevant_lines_end < 0:
                        suggestion["score"] = 0

                # Analytics logging
                if self.config.publish_output:
                    try:
                        if not suggestion["score"]:
                            score = -1
                        else:
                            score = int(suggestion["score"])
                        label = suggestion["label"].lower().strip().replace("<br>", " ")
                        get_logger().info(
                            "MergeMate suggestions statistics",
                            statistics={"score": score, "label": label},
                            analytics=True,
                        )
                    except Exception:
                        pass

            except Exception:
                get_logger().error(
                    f"Error processing suggestion score {i}",
                    artifact={"suggestion": suggestion, "feedback": code_suggestions_feedback[i]},
                )
                suggestion["score"] = 7
                suggestion["score_why"] = ""

            suggestion = self._validate_one_liner_suggestion_not_repeating_code(suggestion)

            # Clear identical existing/improved code
            try:
                if suggestion["existing_code"] == suggestion["improved_code"]:
                    get_logger().debug(f"Edited improved suggestion {i + 1}: existing == improved code")
                    if self._cfg_suggestions.get("commitable_code_suggestions"):
                        suggestion["improved_code"] = ""
                    else:
                        suggestion["existing_code"] = ""
            except Exception as e:
                get_logger().error(f"Error processing suggestion {i + 1}: {e}")

    # ------------------------------------------------------------------
    # Suggestion parsing and validation
    # ------------------------------------------------------------------

    def _parse_code_suggestions(self, predictions: str) -> dict:
        """Parse the AI response into structured code suggestions."""
        data = load_yaml(
            predictions.strip(),
            keys_fix_yaml=["relevant_file", "suggestion_content", "existing_code", "improved_code"],
            first_key="code_suggestions",
            last_key="label",
        )
        if isinstance(data, list):
            data = {"code_suggestions": data}

        # Debug: log what was parsed
        raw_count = len(data.get("code_suggestions", []) if isinstance(data, dict) else [])
        get_logger().debug(f"Parsed {raw_count} suggestions from AI response (first 200 chars: {predictions[:200]!r})")

        suggestion_list: list[dict] = []
        one_sentence_summary_list: list[str] = []
        focus_only_on_problems = self._cfg_suggestions.get("focus_only_on_problems", False)

        for i, suggestion in enumerate(data.get("code_suggestions", [])):
            try:
                needed_keys = ["one_sentence_summary", "label", "relevant_file"]
                if not all(key in suggestion for key in needed_keys):
                    get_logger().debug(f"Skipping suggestion {i + 1}: missing required keys")
                    continue

                if focus_only_on_problems:
                    if "critical" in suggestion["label"].lower():
                        suggestion["label"] = "possible issue"

                if suggestion["one_sentence_summary"] in one_sentence_summary_list:
                    get_logger().debug(f"Skipping duplicate suggestion {i + 1}")
                    continue

                # Skip "const instead let" suggestions
                if (
                    "const" in suggestion.get("suggestion_content", "")
                    and "instead" in suggestion.get("suggestion_content", "")
                    and "let" in suggestion.get("suggestion_content", "")
                ):
                    get_logger().debug(f"Skipping 'const instead let' suggestion {i + 1}")
                    continue

                if "existing_code" in suggestion and "improved_code" in suggestion:
                    suggestion = self._truncate_if_needed(suggestion)
                    one_sentence_summary_list.append(suggestion["one_sentence_summary"])
                    suggestion_list.append(suggestion)
                else:
                    get_logger().info(f"Skipping suggestion {i + 1}: missing existing_code or improved_code")
            except Exception as e:
                get_logger().error(f"Error processing suggestion {i + 1}: {e}")

        data["code_suggestions"] = suggestion_list
        return data

    @staticmethod
    def _truncate_if_needed(suggestion: dict) -> dict:
        from mergemate.config_loader import get_settings

        max_length = get_settings().get("PR_CODE_SUGGESTIONS.MAX_CODE_SUGGESTION_LENGTH", 0)
        truncation_message = get_settings().get("PR_CODE_SUGGESTIONS.SUGGESTION_TRUNCATION_MESSAGE", "")
        if max_length > 0 and len(suggestion.get("improved_code", "")) > max_length:
            get_logger().info(
                f"Truncated suggestion from {len(suggestion['improved_code'])} to {max_length} characters"
            )
            suggestion["improved_code"] = suggestion["improved_code"][:max_length] + f"\n{truncation_message}"
        return suggestion

    def _validate_one_liner_suggestion_not_repeating_code(self, suggestion: dict) -> dict:
        """Check if a suggestion's existing_code is in the base but not head file."""
        try:
            existing_code = suggestion.get("existing_code", "").strip()
            if "..." in existing_code:
                return suggestion
            new_code = suggestion.get("improved_code", "").strip()
            relevant_file = suggestion.get("relevant_file", "").strip()

            diff_files = self.git_provider.get_diff_files()
            for file in diff_files:
                if file.filename.strip() == relevant_file:
                    if not file.head_file:
                        get_logger().info("head_file is empty")
                        return suggestion
                    head_file = file.head_file
                    base_file = file.base_file
                    if existing_code in base_file and existing_code not in head_file and new_code in head_file:
                        suggestion["score"] = 0
                        get_logger().warning(
                            "existing_code is in base but not head, setting score to 0",
                            artifact={"suggestion": suggestion},
                        )
        except Exception as e:
            get_logger().exception("Error validating one-liner suggestion", artifact={"error": e})

        return suggestion

    # ------------------------------------------------------------------
    # Diff processing helpers
    # ------------------------------------------------------------------

    def _remove_line_numbers(self, patches_diff_list: list[str]) -> list[str]:
        """Remove line numbers from decoupled hunk sections."""
        try:
            result: list[str] = []
            for patches_diff in patches_diff_list:
                lines = patches_diff.splitlines()
                for i, line in enumerate(lines):
                    if line.strip():
                        if line.isnumeric():
                            lines[i] = ""
                        elif line[0].isdigit():
                            for j, char in enumerate(line):
                                if not char.isdigit():
                                    lines[i] = line[j + 1 :]
                                    break
                result.append("\n".join(lines))
            return result
        except Exception as e:
            get_logger().error(f"Error removing line numbers from patches_diff_list: {e}")
            return patches_diff_list

    async def _convert_to_decoupled_with_line_numbers(
        self, patches_diff_list_no_line_numbers: list[str], model: str
    ) -> list[str]:
        """Convert non-decoupled diffs to decoupled format with line numbers."""
        with get_logger().contextualize(sub_feature="convert_to_decoupled_with_line_numbers"):
            try:
                patches_diff_list: list[str] = []
                for patch_prompt in patches_diff_list_no_line_numbers:
                    file_prefix = "## File: "
                    patches = patch_prompt.strip().split(f"\n{file_prefix}")
                    patches_new = copy.deepcopy(patches)
                    for i in range(len(patches_new)):
                        if i == 0:
                            prefix = patches_new[i].split("\n@@")[0].strip()
                        else:
                            prefix = file_prefix + patches_new[i].split("\n@@")[0][1:]
                            prefix = prefix.strip()
                        patches_new[i] = (
                            prefix
                            + "\n\n"
                            + decouple_and_convert_to_hunks_with_lines_numbers(patches_new[i], file=None).strip()
                        )
                        patches_new[i] = patches_new[i].strip()
                    patch_final = "\n\n\n".join(patches_new)

                    max_tokens_full = MAX_TOKENS.get(model, get_max_tokens(model))
                    delta_output = 2000
                    token_count = self._token_handler.count_tokens(patch_final)
                    if token_count > max_tokens_full - delta_output:
                        get_logger().warning(
                            f"Token count {token_count} exceeds limit {max_tokens_full - delta_output}, clipping"
                        )
                        patch_final = clip_tokens(patch_final, max_tokens_full - delta_output)
                    patches_diff_list.append(patch_final)
                return patches_diff_list
            except Exception:
                get_logger().exception(
                    "Error converting to decoupled with line numbers",
                    artifact={"patches": patches_diff_list_no_line_numbers},
                )
                return []

    # ------------------------------------------------------------------
    # Publishing helpers
    # ------------------------------------------------------------------

    async def _publish_no_suggestions(self) -> None:
        """Publish a "no suggestions found" message."""
        pr_body = "## PR Code Suggestions ✨\n\nNo code suggestions found for the PR."
        cfg = self._cfg_suggestions
        config_cfg = self._cfg_config

        if config_cfg.get("publish_output") and cfg.get("publish_output_no_suggestions", True):
            get_logger().warning("No code suggestions found for the PR.")
            if self._progress_response:
                self.git_provider.edit_comment(self._progress_response, body=pr_body)
            else:
                self.git_provider.publish_comment(pr_body)

    def _add_self_review_text(self, pr_body: str) -> str:
        """Append self-review checkbox to the comment body."""
        cfg = self._cfg_suggestions
        text = cfg.get("code_suggestions_self_review_text", "")
        pr_body += f"\n\n- [ ]  {text}"
        approve = cfg.get("approve_pr_on_self_review", False)
        fold = cfg.get("fold_suggestions_on_self_review", False)
        if approve and not fold:
            pr_body += " <!-- approve pr self-review -->"
        elif fold and not approve:
            pr_body += " <!-- fold suggestions self-review -->"
        else:
            pr_body += " <!-- approve and fold suggestions self-review -->"
        return pr_body

    async def _dual_publishing(self, data: dict) -> None:
        """Publish high-scoring suggestions inline (dual publishing mode)."""
        threshold = int(self._cfg_suggestions.get("dual_publishing_score_threshold", 0))
        data_above: dict[str, list] = {"code_suggestions": []}
        try:
            for suggestion in data.get("code_suggestions", []):
                if int(suggestion.get("score", 0)) >= threshold and suggestion.get("improved_code"):
                    data_above["code_suggestions"].append(suggestion)
                    if not data_above["code_suggestions"][-1].get("existing_code"):
                        get_logger().info("Identical existing and improved code for dual publishing")
                        data_above["code_suggestions"][-1]["existing_code"] = suggestion["improved_code"]
            if data_above["code_suggestions"]:
                get_logger().info(
                    f"Publishing {len(data_above['code_suggestions'])} suggestions in dual publishing mode"
                )
                await self._push_inline_code_suggestions(data_above)
        except Exception as e:
            get_logger().error(f"Failed to publish dual publishing suggestions: {e}")

    async def _push_inline_code_suggestions(self, data: dict) -> None:
        """Push code suggestions as inline PR comments."""
        code_suggestions: list[dict] = []
        get_logger().debug(f"Pushing {len(data.get('code_suggestions', []))} inline suggestions")

        if not data.get("code_suggestions"):
            get_logger().info("No suggestions found to improve this PR.")
            msg = "No suggestions found to improve this PR."
            if self._progress_response:
                self.git_provider.edit_comment(self._progress_response, body=msg)
            else:
                self.git_provider.publish_comment(msg)
            return

        for d in data["code_suggestions"]:
            try:
                if self.config.verbosity_level >= 2:
                    get_logger().info(f"suggestion: {d}")
                relevant_file = d["relevant_file"].strip()
                relevant_lines_start = int(d["relevant_lines_start"])
                relevant_lines_end = int(d["relevant_lines_end"])
                content = d["suggestion_content"].rstrip()
                new_code_snippet = d["improved_code"].rstrip()
                label = d["label"].strip()

                if new_code_snippet:
                    new_code_snippet = self._dedent_code(relevant_file, relevant_lines_start, new_code_snippet)

                if d.get("score"):
                    body = (
                        f"**Suggestion:** {content} [{label}, importance: {d.get('score')}]\n"
                        f"```suggestion\n{new_code_snippet}\n```"
                    )
                else:
                    body = f"**Suggestion:** {content} [{label}]\n```suggestion\n{new_code_snippet}\n```"
                code_suggestions.append(
                    {
                        "body": body,
                        "relevant_file": relevant_file,
                        "relevant_lines_start": relevant_lines_start,
                        "relevant_lines_end": relevant_lines_end,
                        "original_suggestion": d,
                    }
                )
            except Exception:
                get_logger().info(f"Could not parse suggestion: {d}")

        is_successful = self.git_provider.publish_code_suggestions(code_suggestions)
        get_logger().debug(f"Inline publish result: {is_successful}, suggestions: {len(code_suggestions)}")
        if not is_successful:
            get_logger().info("Failed to publish code suggestions, trying individually")
            for cs in code_suggestions:
                self.git_provider.publish_code_suggestions([cs])

    def _dedent_code(self, relevant_file: str, relevant_lines_start: int, new_code_snippet: str) -> str:
        """Adjust indentation of a code suggestion to match the original file."""
        try:
            diff_files = getattr(self.git_provider, "diff_files", None) or self.git_provider.get_diff_files()
            original_initial_line = None
            for file in diff_files:
                if file.filename.strip() == relevant_file:
                    if file.head_file:
                        file_lines = file.head_file.splitlines()
                        if relevant_lines_start > len(file_lines):
                            get_logger().warning(
                                "Could not dedent: relevant_lines_start out of range",
                                artifact={
                                    "filename": file.filename,
                                    "relevant_lines_start": relevant_lines_start,
                                },
                            )
                            return new_code_snippet
                        original_initial_line = file_lines[relevant_lines_start - 1]
                    else:
                        get_logger().warning(
                            "Could not dedent: head_file missing",
                            artifact={"filename": file.filename},
                        )
                        return new_code_snippet
                    break

            if original_initial_line:
                suggested_initial_line = new_code_snippet.splitlines()[0]
                original_spaces = len(original_initial_line) - len(original_initial_line.lstrip())
                suggested_spaces = len(suggested_initial_line) - len(suggested_initial_line.lstrip())
                delta = original_spaces - suggested_spaces
                if delta > 0:
                    indent_char = "\t" if original_initial_line.startswith("\t") else " "
                    new_code_snippet = textwrap.indent(new_code_snippet, delta * indent_char).rstrip("\n")
        except Exception as e:
            get_logger().error(f"Error dedenting code snippet for {relevant_file}: {e}")

        return new_code_snippet

    # ------------------------------------------------------------------
    # Persistent comment with history
    # ------------------------------------------------------------------

    @staticmethod
    def _publish_persistent_comment_with_history(
        git_provider: GitProvider,
        pr_comment: str,
        initial_header: str,
        update_header: bool = True,
        name: str = "review",
        final_update_message: bool = True,
        max_previous_comments: int = 4,
        progress_response=None,
        only_fold: bool = False,
    ):
        """Publish a persistent PR comment that maintains suggestion history."""

        def _extract_link(comment_text: str) -> str:
            r = re.compile(r"<!--.*?-->")
            match = r.search(comment_text)
            if match:
                return f" up to commit {match.group(0)[4:-3].strip()}"
            return ""

        from mergemate.config_loader import get_settings

        history_header = "#### Previous suggestions\n"
        last_commit_num = git_provider.get_latest_commit_url().split("/")[-1][:7]
        if only_fold:
            text = get_settings().pr_code_suggestions.code_suggestions_self_review_text
            latest_suggestion_header = f"\n\n- [x]  {text}"
        else:
            latest_suggestion_header = f"Latest suggestions up to {last_commit_num}"
        latest_commit_html_comment = f"<!-- {last_commit_num} -->"
        found_comment = None

        if max_previous_comments > 0:
            try:
                prev_comments = list(git_provider.get_issue_comments())
                for comment in prev_comments:
                    if comment.body.startswith(initial_header):
                        prev_suggestions = comment.body
                        found_comment = comment
                        comment_url = git_provider.get_comment_url(comment)

                        if history_header.strip() not in comment.body:
                            # No history section yet
                            table_index = comment.body.find("<table>")
                            if table_index == -1:
                                git_provider.edit_comment(comment, pr_comment)
                                continue
                            up_to_commit_txt = _extract_link(comment.body[:table_index])
                            prev_suggestion_table = comment.body[
                                table_index : comment.body.rfind("</table>") + len("</table>")
                            ]
                            tick = "✅ " if "✅" in prev_suggestion_table else ""
                            prev_suggestion_table = (
                                f"<details><summary>{tick}{name.capitalize()}{up_to_commit_txt}</summary>\n"
                                f"<br>{prev_suggestion_table}\n\n</details>"
                            )
                            new_suggestion_table = pr_comment.replace(initial_header, "").strip()
                            pr_comment_updated = (
                                f"{initial_header}\n{latest_commit_html_comment}\n\n"
                                f"{latest_suggestion_header}\n{new_suggestion_table}\n\n___\n\n"
                                f"{history_header}{prev_suggestion_table}\n"
                            )
                        else:
                            # History section exists
                            sections = prev_suggestions.split(history_header.strip())
                            latest_table = sections[0].strip()
                            prev_suggestion_table = sections[1].replace(history_header, "").strip()

                            table_ind = latest_table.find("<table>")
                            up_to_commit_txt = _extract_link(latest_table[:table_ind])
                            latest_table = latest_table[table_ind : latest_table.rfind("</table>") + len("</table>")]

                            # Enforce max_previous_comments
                            count = prev_suggestions.count(f"\n<details><summary>{name.capitalize()}")
                            count += prev_suggestions.count(f"\n<details><summary>✅ {name.capitalize()}")
                            if count >= max_previous_comments:
                                prev_suggestion_table = prev_suggestion_table[
                                    : prev_suggestion_table.rfind(f"<details><summary>{name.capitalize()} up to commit")
                                ]

                            tick = "✅ " if "✅" in latest_table else ""
                            last_prev_table = (
                                f"\n<details><summary>{tick}{name.capitalize()}{up_to_commit_txt}</summary>\n"
                                f"<br>{latest_table}\n\n</details>"
                            )
                            prev_suggestion_table = last_prev_table + "\n" + prev_suggestion_table

                            new_suggestion_table = pr_comment.replace(initial_header, "").strip()
                            pr_comment_updated = (
                                f"{initial_header}\n"
                                f"{latest_commit_html_comment}\n\n"
                                f"{latest_suggestion_header}\n\n{new_suggestion_table}\n\n"
                                f"___\n\n"
                                f"{history_header}\n"
                                f"{prev_suggestion_table}\n"
                            )

                        get_logger().info(f"Persistent mode - updating comment {comment_url} to latest {name} message")
                        if progress_response:
                            git_provider.edit_comment(progress_response, pr_comment_updated)
                            git_provider.remove_comment(comment)
                            comment = progress_response
                        else:
                            git_provider.edit_comment(comment, pr_comment_updated)
                        return comment
            except Exception as e:
                get_logger().exception(f"Failed to update persistent {name}: {e}")

        # No previous comment found — publish new
        body = pr_comment.replace(initial_header, "").strip()
        pr_comment = f"{initial_header}\n\n{latest_commit_html_comment}\n\n{body}\n\n"
        if progress_response:
            git_provider.edit_comment(progress_response, pr_comment)
            new_comment = progress_response
        else:
            new_comment = git_provider.publish_comment(pr_comment)
        return new_comment

    # ------------------------------------------------------------------
    # Summarized suggestions table
    # ------------------------------------------------------------------

    def _generate_summarized_suggestions(self, data: dict) -> str:
        """Generate the HTML table for summarized code suggestions."""
        try:
            pr_body = "## PR Code Suggestions ✨\n\n"

            if len(data.get("code_suggestions", [])) == 0:
                return pr_body + "No suggestions found to improve this PR."

            if self._cfg_config.get("is_auto_command"):
                pr_body += "Explore these optional code suggestions:\n\n"

            # Build table header
            delta = 66
            header = "Suggestion" + "&nbsp; " * delta
            pr_body += (
                "<table>"
                "<thead><tr><td><strong>Category</strong></td>"
                f"<td align=left><strong>{header}</strong></td>"
                "<td align=center><strong>Impact</strong></td></tr>"
                "<tbody>"
            )

            # Group suggestions by label
            suggestions_labels: dict[str, list] = {}
            for suggestion in data["code_suggestions"]:
                label = suggestion["label"].strip().strip("'").strip('"')
                if label not in suggestions_labels:
                    suggestions_labels[label] = []
                suggestions_labels[label].append(suggestion)

            # Sort by max score, then sort within each group
            suggestions_labels = dict(
                sorted(
                    suggestions_labels.items(),
                    key=lambda x: max(s["score"] for s in x[1]),
                    reverse=True,
                )
            )
            for label in suggestions_labels:
                suggestions_labels[label] = sorted(suggestions_labels[label], key=lambda x: x["score"], reverse=True)

            for label, suggestions in suggestions_labels.items():
                num = len(suggestions)
                pr_body += f"<tr><td rowspan={num}>{label.capitalize()}</td>\n"

                for i, suggestion in enumerate(suggestions):
                    relevant_file = suggestion["relevant_file"].strip()
                    relevant_lines_start = int(suggestion["relevant_lines_start"])
                    relevant_lines_end = int(suggestion["relevant_lines_end"])

                    if relevant_lines_start == relevant_lines_end:
                        range_str = f"[{relevant_lines_start}]"
                    else:
                        range_str = f"[{relevant_lines_start}-{relevant_lines_end}]"

                    try:
                        code_snippet_link = self.git_provider.get_line_link(
                            relevant_file, relevant_lines_start, relevant_lines_end
                        )
                    except Exception:
                        code_snippet_link = ""

                    suggestion_content = suggestion["suggestion_content"].rstrip()
                    suggestion_content = insert_br_after_x_chars(suggestion_content, 84)

                    # Build diff for existing → improved code
                    existing_code = suggestion.get("existing_code", "").rstrip() + "\n"
                    improved_code = suggestion.get("improved_code", "").rstrip() + "\n"
                    diff = difflib.unified_diff(existing_code.split("\n"), improved_code.split("\n"), n=999)
                    patch_orig = "\n".join(diff)
                    patch = "\n".join(patch_orig.splitlines()[5:]).strip("\n")
                    example_code = f"```diff\n{patch}\n```\n"

                    if i == 0:
                        pr_body += "<td>\n\n"
                    else:
                        pr_body += "<tr><td>\n\n"

                    suggestion_summary = suggestion["one_sentence_summary"].strip().rstrip(".")
                    if "'<" in suggestion_summary and ">'" in suggestion_summary:
                        suggestion_summary = suggestion_summary.replace("'<", "`<").replace(">'", ">`")
                    if "`" in suggestion_summary:
                        suggestion_summary = replace_code_tags(suggestion_summary)

                    pr_body += f"\n\n<details><summary>{suggestion_summary}</summary>\n\n___\n\n"
                    pr_body += (
                        f"**{suggestion_content}**\n\n"
                        f"[{relevant_file} {range_str}]({code_snippet_link})\n\n"
                        f"{example_code.rstrip()}\n"
                    )

                    if suggestion.get("score_why"):
                        pr_body += (
                            f"<details><summary>Suggestion importance[1-10]: {suggestion['score']}</summary>\n\n"
                            f"__\n\nWhy: {suggestion['score_why']}\n\n"
                            f"</details>"
                        )

                    pr_body += "</details>"

                    # Score column
                    score_int = int(suggestion.get("score", 0))
                    if self._cfg_suggestions.get("new_score_mechanism"):
                        score_str = self._get_score_str(score_int)
                    else:
                        score_str = str(score_int)
                    pr_body += f"</td><td align=center>{score_str}\n\n</td></tr>"

            pr_body += "</tr></tbody></table>"
            return pr_body
        except Exception as e:
            get_logger().info(f"Failed to publish summarized code suggestions: {e}")
            return ""

    def _get_score_str(self, score: int) -> str:
        """Convert numeric score to High/Medium/Low string."""
        cfg = self._cfg_suggestions
        th_high = cfg.get("new_score_mechanism_th_high", 9)
        th_medium = cfg.get("new_score_mechanism_th_medium", 7)
        if score >= th_high:
            return "High"
        elif score >= th_medium:
            return "Medium"
        return "Low"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_main_pr_language(self) -> str:
        """Determine the main language of the PR."""
        try:
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

    def _cfg(self, section: str) -> dict[str, Any]:
        """Access a raw config section — checks top-level and under 'configuration'."""
        val = self.config._raw.get(section)
        if val is not None:
            return val if isinstance(val, dict) else {}
        # Check nested under configuration section
        config_section = self.config._raw.get("configuration", {})
        val = config_section.get(section) if isinstance(config_section, dict) else None
        return val if isinstance(val, dict) else {}

    def _raw(self, key: str, default: Any = None) -> Any:
        """Access any raw config key — checks top-level and under 'configuration'."""
        val = self.config._raw.get(key)
        if val is not None:
            return val
        config_section = self.config._raw.get("configuration", {})
        if isinstance(config_section, dict):
            return config_section.get(key, default)
        return default

    def _render_template(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template with the given variables."""
        environment = Environment(undefined=StrictUndefined)
        return environment.from_string(template_str).render(variables)


# ---------------------------------------------------------------------------
# Factory function for the tool registry
# ---------------------------------------------------------------------------


def get_improve_class() -> type:
    """Return the PRCodeSuggestions class for the tool registry factory."""
    return PRCodeSuggestions
