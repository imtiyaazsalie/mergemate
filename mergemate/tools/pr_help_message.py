"""PR Help Message tool — answers questions or shows available tools.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

from mergemate.algo import MAX_TOKENS
from mergemate.algo.pr_processing import retry_with_fallback_models
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import ModelType, clip_tokens, get_max_tokens, load_yaml
from mergemate.config_loader import get_settings
from mergemate.git_providers import BitbucketServerProvider, GithubProvider, get_git_provider_with_context
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool


def extract_header(snippet: str) -> str:
    res = ""
    lines = snippet.split("===Snippet content===")[0].split("\n")
    highest_header = ""
    for line in lines[::-1]:
        line = line.strip()
        if line.startswith("Header "):
            highest_header = line.split(": ")[1]
    if highest_header:
        res = f"#{highest_header.lower().replace(' ', '-')}"
    return res


class PRHelpMessage(BaseTool):
    """Answers PR-related questions or displays available tool commands.

    Two modes:
        - With a question: reads docs, calls AI, returns an answer
        - Without a question: displays the available tool table

    Pipeline:
        1. _prepare() — parse question, read docs content if in Q&A mode
        2. _predict() — call AI (Q&A mode) or return None (table mode)
        3. _publish() — post answer or tool table
    """

    @property
    def tool_name(self) -> str:
        return "help"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Parse the user's question and prepare documentation snippets."""
        self.question_str = self.parse_args(self.args)

        self._mode_qa = bool(self.question_str)
        if not self._mode_qa:
            get_logger().info("Preparing PR Help Message table...")
            return

        get_logger().info(f"Answering PR question: {self.question_str}")

        self._vars["question"] = self.question_str
        self._vars["snippets"] = ""

        self.token_handler = TokenHandler(
            None,
            self._vars,
            get_settings().pr_help_prompts.system,
            get_settings().pr_help_prompts.user,
        )

        # Load documentation content
        docs_path = Path(__file__).parent.parent.parent / "docs" / "docs"
        md_files = list(docs_path.glob("**/*.md"))
        folders_to_exclude = ["/finetuning_benchmark/"]
        files_to_exclude = {"EXAMPLE_BEST_PRACTICE.md", "compression_strategy.md", "/docs/overview/index.md"}
        md_files = [
            file
            for file in md_files
            if not any(folder in str(file) for folder in folders_to_exclude)
            and not any(file.name == fe for fe in files_to_exclude)
        ]

        priority_files_strings = [
            "/docs/index.md",
            "/usage-guide",
            "tools/describe.md",
            "tools/review.md",
            "tools/improve.md",
            "/faq",
        ]
        md_files_priority = [
            file for file in md_files if any(priority_string in str(file) for priority_string in priority_files_strings)
        ]
        md_files_not_priority = [file for file in md_files if file not in md_files_priority]
        md_files = md_files_priority + md_files_not_priority

        docs_prompt = ""
        for file in md_files:
            try:
                with open(file, "r") as f:
                    file_path = str(file).replace(str(docs_path), "")
                    docs_prompt += (
                        f"\n==file name==\n\n{file_path}\n\n==file content==\n\n{f.read().strip()}\n=========\n\n"
                    )
            except Exception as e:
                get_logger().error(f"Error while reading the file {file}: {e}")

        token_count = self.token_handler.count_tokens(docs_prompt)
        get_logger().debug(f"Token count of full documentation website: {token_count}")

        model = self.config.model.model
        if model in MAX_TOKENS:
            max_tokens_full = MAX_TOKENS[model]
        else:
            max_tokens_full = get_max_tokens(model)
        delta_output = 2000
        if token_count > max_tokens_full - delta_output:
            get_logger().info(
                f"Token count {token_count} exceeds the limit {max_tokens_full - delta_output}. "
                "Clipping documentation content."
            )
            docs_prompt = clip_tokens(docs_prompt, max_tokens_full - delta_output)
        self._vars["snippets"] = docs_prompt.strip()

    async def _predict(self) -> Any:
        """Call AI for Q&A mode, or skip for table mode."""
        if not self._mode_qa:
            return None
        response = await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR)
        return response

    async def _publish(self, result: Any) -> None:
        """Publish the answer or tool table."""
        if not self.config.publish_output:
            get_logger().info("Publish disabled — skipping help output", pr_url=self.pr_url)
            return

        if self._mode_qa and result is not None:
            self._publish_qa_answer(result)
        elif not self._mode_qa:
            self._publish_tool_table()

    # ------------------------------------------------------------------
    # Q&A mode
    # ------------------------------------------------------------------

    def _publish_qa_answer(self, response: str) -> None:
        response_yaml = load_yaml(response)
        if isinstance(response_yaml, str):
            get_logger().warning(f"Failing to parse response: {response_yaml}, publishing the response as is")
            answer_str = f"### Question: \n{self.question_str}\n\n"
            answer_str += "### Answer:\n\n"
            answer_str += response_yaml
            self.git_provider.publish_comment(answer_str)
            return

        response_str = response_yaml.get("response")
        relevant_sections = response_yaml.get("relevant_sections")

        if not relevant_sections:
            get_logger().info(f"Could not find relevant answer for the question: {self.question_str}")
            answer_str = f"### Question: \n{self.question_str}\n\n"
            answer_str += "### Answer:\n\n"
            answer_str += "Could not find relevant information to answer the question. "
            answer_str += "Please provide more details and try again."
            self.git_provider.publish_comment(answer_str)
            return

        answer_str = ""
        if response_str:
            answer_str += f"### Question: \n{self.question_str}\n\n"
            answer_str += f"### Answer:\n{response_str.strip()}\n\n"
            answer_str += "#### Relevant Sources:\n\n"
            base_path = "https://imtiyaazsalie.github.io/mergemate/"
            for section in relevant_sections:
                file = section.get("file_name").strip().removesuffix(".md")
                if str(section["relevant_section_header_string"]).strip():
                    markdown_header = self.format_markdown_header(section["relevant_section_header_string"])
                    answer_str += f"> - {base_path}{file}#{markdown_header}\n"
                else:
                    answer_str += f"> - {base_path}{file}\n"

        self.git_provider.publish_comment(answer_str)

    async def _prepare_prediction(self, model: str) -> str:
        try:
            variables = copy.deepcopy(self._vars)
            environment = Environment(undefined=StrictUndefined)
            system_prompt = environment.from_string(get_settings().pr_help_prompts.system).render(variables)
            user_prompt = environment.from_string(get_settings().pr_help_prompts.user).render(variables)
            response, _finish_reason = await self.ai_handler.chat_completion(
                model=model,
                temperature=self.config.model.temperature,
                system=system_prompt,
                user=user_prompt,
            )
            return response
        except Exception as e:
            get_logger().error(f"Error while preparing prediction: {e}")
            return ""

    # ------------------------------------------------------------------
    # Tool table mode
    # ------------------------------------------------------------------

    def _publish_tool_table(self) -> None:
        if not isinstance(self.git_provider, BitbucketServerProvider) and not self.git_provider.is_supported(
            "gfm_markdown"
        ):
            self.git_provider.publish_comment(
                "The `Help` tool requires gfm markdown, which is not supported by your code platform."
            )
            return

        get_logger().info("Getting PR Help Message...")
        pr_comment = "## MergeMate Walkthrough 🤖\n\n"
        pr_comment += (
            "Welcome to the MergeMate, an AI-powered tool for automated pull request analysis, "
            "feedback, suggestions and more."
        )
        pr_comment += "\n\nHere is a list of tools you can use to interact with the MergeMate:\n"
        base_path = "https://imtiyaazsalie.github.io/mergemate/tools"

        tool_names = [
            f"[DESCRIBE]({base_path}/describe/)",
            f"[REVIEW]({base_path}/review/)",
            f"[IMPROVE]({base_path}/improve/)",
            f"[UPDATE CHANGELOG]({base_path}/update_changelog/)",
            f"[HELP DOCS]({base_path}/help_docs/)",
            f"[ADD DOCS]({base_path}/add_docs/)",
            f"[ASK]({base_path}/ask/)",
            f"[GENERATE CUSTOM LABELS]({base_path}/generate_labels/)",
        ]

        descriptions = [
            "Generates PR description - title, type, summary, code walkthrough and labels",
            "Adjustable feedback about the PR, possible issues, security concerns, review effort and more",
            "Code suggestions for improving the PR",
            "Automatically updates the changelog",
            "Answers a question regarding this repository, or a given one, based on given documentation path",
            "Generates documentation to methods/functions/classes that changed in the PR",
            "Answering free-text questions about the PR",
            "Generates custom labels for the PR, based on specific guidelines defined by the user",
        ]

        commands = [
            "`/describe`",
            "`/review`",
            "`/improve`",
            "`/update_changelog`",
            "`/help_docs`",
            "`/add_docs`",
            "`/ask`",
            "`/generate_labels`",
        ]

        checkbox_list = [
            " - [ ] Run <!-- /describe -->",
            " - [ ] Run <!-- /review -->",
            " - [ ] Run <!-- /improve -->",
            " - [ ] Run <!-- /update_changelog -->",
            " - [ ] Run <!-- /help_docs -->",
            " - [ ] Run <!-- /add_docs -->",
            "[*]",
            "[*]",
            "[*]",
            "[*]",
            "[*]",
        ]

        if isinstance(self.git_provider, GithubProvider) and not self.config._raw.get("config", {}).get(
            "disable_checkboxes", False
        ):
            pr_comment += (
                "<table><tr align='left'><th align='left'>Tool</th>"
                "<th align='left'>Description</th>"
                "<th align='left'>Trigger Interactively :gem:</th></tr>"
            )
            for i in range(len(tool_names)):
                pr_comment += (
                    f"\n<tr><td align='left'>\n\n<strong>{tool_names[i]}</strong></td>\n"
                    f"<td>{descriptions[i]}</td>\n"
                    f"<td>\n\n{checkbox_list[i]}\n</td></tr>"
                )
            pr_comment += "</table>\n\n"
            pr_comment += (
                "\n\n(1) Note that each tool can be [triggered automatically]"
                "(https://imtiyaazsalie.github.io/mergemate/usage-guide/automations_and_usage/"
                "#github-app-automatic-tools-when-a-new-pr-is-opened) when a new PR is opened, "
                "or called manually by [commenting on a PR]"
                "(https://imtiyaazsalie.github.io/mergemate/usage-guide/automations_and_usage/#online-usage)."
            )
            pr_comment += (
                "\n\n(2) Tools marked with [*] require additional parameters to be passed. "
                "For example, to invoke the `/ask` tool, you need to comment on a PR: "
                '`/ask "<question content>"`. '
                "See the relevant documentation for each tool for more details."
            )
        elif isinstance(self.git_provider, BitbucketServerProvider):
            pr_comment = generate_bbdc_table(tool_names[:4], descriptions[:4])
        else:
            pr_comment += (
                "<table><tr align='left'><th align='left'>Tool</th>"
                "<th align='left'>Command</th><th align='left'>Description</th></tr>"
            )
            for i in range(len(tool_names)):
                pr_comment += (
                    f"\n<tr><td align='left'>\n\n<strong>{tool_names[i]}</strong></td>"
                    f"<td>{commands[i]}</td><td>{descriptions[i]}</td></tr>"
                )
            pr_comment += "</table>\n\n"
            pr_comment += (
                "\n\nNote that each tool can be [invoked automatically]"
                "(https://imtiyaazsalie.github.io/mergemate/usage-guide/automations_and_usage/) "
                "when a new PR is opened, or called manually by [commenting on a PR]"
                "(https://imtiyaazsalie.github.io/mergemate/usage-guide/automations_and_usage/#online-usage)."
            )

        self.git_provider.publish_comment(pr_comment)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def parse_args(self, args: list[str] | None) -> str:
        if args and len(args) > 0:
            return " ".join(args)
        return ""

    def format_markdown_header(self, header: str) -> str:
        try:
            cleaned = header.strip("# 💎\n")
            replacements = {
                "'": "",
                "`": "",
                "(": "",
                ")": "",
                ",": "",
                ".": "",
                "?": "",
                "!": "",
                " ": "-",
            }
            pattern = re.compile("|".join(map(re.escape, replacements.keys())))
            return pattern.sub(lambda m: replacements[m.group()], cleaned).lower()
        except Exception:
            get_logger().exception("Error while formatting markdown header", artifacts={"header": header})
            return ""

    async def prepare_relevant_snippets(self, sim_results):
        relevant_snippets_full = []
        relevant_pages_full = []
        relevant_snippets_full_header = []
        for s in sim_results:
            page = s[0].metadata["source"]
            content = s[0].page_content
            relevant_snippets_full.append(content)
            relevant_snippets_full_header.append(extract_header(content))
            relevant_pages_full.append(page)
        relevant_snippets_str = ""
        for i, s in enumerate(relevant_snippets_full):
            relevant_snippets_str += f"Snippet {i + 1}:\n\n{s}\n\n"
            relevant_snippets_str += "-------------------\n\n"
        return relevant_pages_full, relevant_snippets_full_header, relevant_snippets_str


def generate_bbdc_table(column_arr_1, column_arr_2):
    header_row = "| Tool  | Description | \n"
    separator_row = "|--|--|\n"
    data_rows = ""
    max_len = max(len(column_arr_1), len(column_arr_2))
    for i in range(max_len):
        col1 = column_arr_1[i] if i < len(column_arr_1) else ""
        col2 = column_arr_2[i] if i < len(column_arr_2) else ""
        data_rows += f"| {col1} | {col2} |\n"
    return header_row + separator_row + data_rows


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_help_class() -> type:
    """Return the PRHelpMessage class for the tool registry factory."""
    return PRHelpMessage
