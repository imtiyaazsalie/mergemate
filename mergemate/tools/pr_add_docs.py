"""PR Add Docs tool — generates documentation for changed code.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

import copy
import textwrap
from typing import Dict

from jinja2 import Environment, StrictUndefined

from mergemate.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import load_yaml
from mergemate.config_loader import get_settings
from mergemate.git_providers.git_provider import get_main_pr_language
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool


class PRAddDocs(BaseTool):
    """Generates inline code documentation suggestions for a PR.

    Pipeline:
        1. _prepare() — gather diff, build prompts
        2. _predict() — call AI model to generate documentation
        3. _publish() — push inline doc suggestions to the PR
    """

    @property
    def tool_name(self) -> str:
        return "add_docs"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Gather PR diff and determine main language for docs style."""
        self.main_language = get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())

        self.patches_diff = None
        self.prediction = None

        self._vars.update(
            {
                "title": self.context.pr.title,
                "branch": self.context.pr.branch,
                "description": self.context.pr.description,
                "language": self.main_language,
                "diff": "",
                "extra_instructions": get_settings().pr_add_docs.extra_instructions,
                "commit_messages_str": self.git_provider.get_commit_messages(),
                "docs_for_language": get_docs_for_language(self.main_language, get_settings().pr_add_docs.docs_style),
            }
        )

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self._vars,
            get_settings().pr_add_docs_prompt.system,
            get_settings().pr_add_docs_prompt.user,
        )

        get_logger().info("Preparing PR documentation...")
        await retry_with_fallback_models(self._prepare_prediction)

    async def _predict(self) -> Dict:
        """Parse the AI response into structured documentation data."""
        data = self._prepare_pr_code_docs()
        return data

    async def _publish(self, result: Dict) -> None:
        """Push inline doc suggestions to the PR."""
        if not result or "Code Documentation" not in result:
            get_logger().info("No code documentation found for PR.")
            return

        if self.config.publish_output:
            get_logger().info("Pushing inline code documentation...")
            self.push_inline_docs(result)

    # ------------------------------------------------------------------
    # Docs-specific logic
    # ------------------------------------------------------------------

    async def _prepare_prediction(self, model: str) -> None:
        get_logger().info("Getting PR diff...")
        self.patches_diff = get_pr_diff(
            self.git_provider,
            self.token_handler,
            model,
            add_line_numbers_to_hunks=True,
            disable_extra_lines=False,
        )
        get_logger().info("Getting AI prediction...")
        self.prediction = await self._get_prediction(model)

    async def _get_prediction(self, model: str) -> str:
        variables = copy.deepcopy(self._vars)
        variables["diff"] = self.patches_diff
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_add_docs_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_add_docs_prompt.user).render(variables)
        if get_settings().config.verbosity_level >= 2:
            get_logger().info(f"\nSystem prompt:\n{system_prompt}")
            get_logger().info(f"\nUser prompt:\n{user_prompt}")
        response, _finish_reason = await self.ai_handler.chat_completion(
            model=model,
            temperature=self.config.model.temperature,
            system=system_prompt,
            user=user_prompt,
        )
        return response

    def _prepare_pr_code_docs(self) -> Dict:
        docs = self.prediction.strip()
        data = load_yaml(docs)
        if isinstance(data, list):
            data = {"Code Documentation": data}
        return data

    def push_inline_docs(self, data: Dict) -> None:
        docs = []

        if not data["Code Documentation"]:
            self.git_provider.publish_comment("No code documentation found to improve this PR.")
            return

        for d in data["Code Documentation"]:
            try:
                if get_settings().config.verbosity_level >= 2:
                    get_logger().info(f"add_docs: {d}")
                relevant_file = d["relevant file"].strip()
                relevant_line = int(d["relevant line"])
                documentation = d["documentation"]
                doc_placement = d["doc placement"].strip()
                if documentation:
                    new_code_snippet = self.dedent_code(
                        relevant_file,
                        relevant_line,
                        documentation,
                        doc_placement,
                        add_original_line=True,
                    )
                    body = f"**Suggestion:** Proposed documentation\n```suggestion\n" + new_code_snippet + "\n```"
                    docs.append(
                        {
                            "body": body,
                            "relevant_file": relevant_file,
                            "relevant_lines_start": relevant_line,
                            "relevant_lines_end": relevant_line,
                        }
                    )
            except Exception:
                if get_settings().config.verbosity_level >= 2:
                    get_logger().info(f"Could not parse code docs: {d}")

        is_successful = self.git_provider.publish_code_suggestions(docs)
        if not is_successful:
            get_logger().info("Failed to publish code docs, trying to publish each docs separately")
            for doc_suggestion in docs:
                self.git_provider.publish_code_suggestions([doc_suggestion])

    def dedent_code(
        self,
        relevant_file: str,
        relevant_lines_start: int,
        new_code_snippet: str,
        doc_placement: str = "after",
        add_original_line: bool = False,
    ) -> str:
        try:
            self.diff_files = (
                self.git_provider.diff_files if self.git_provider.diff_files else self.git_provider.get_diff_files()
            )
            original_initial_line = None
            for file in self.diff_files:
                if file.filename.strip() == relevant_file:
                    original_initial_line = file.head_file.splitlines()[relevant_lines_start - 1]
                    break
            if original_initial_line:
                if doc_placement == "after":
                    line = file.head_file.splitlines()[relevant_lines_start]
                else:
                    line = original_initial_line
                suggested_initial_line = new_code_snippet.splitlines()[0]
                original_initial_spaces = len(line) - len(line.lstrip())
                suggested_initial_spaces = len(suggested_initial_line) - len(suggested_initial_line.lstrip())
                delta_spaces = original_initial_spaces - suggested_initial_spaces
                if delta_spaces > 0:
                    new_code_snippet = textwrap.indent(new_code_snippet, delta_spaces * " ").rstrip("\n")
                if add_original_line:
                    if doc_placement == "after":
                        new_code_snippet = original_initial_line + "\n" + new_code_snippet
                    else:
                        new_code_snippet = new_code_snippet.rstrip() + "\n" + original_initial_line
        except Exception as e:
            if get_settings().config.verbosity_level >= 2:
                get_logger().info(f"Could not dedent code snippet for file {relevant_file}, error: {e}")

        return new_code_snippet


def get_docs_for_language(language: str, style: str) -> str:
    language = language.lower()
    if language == "java":
        return "Javadocs"
    elif language in ("python", "lisp", "clojure"):
        return f"Docstring ({style})"
    elif language in ("javascript", "typescript"):
        return "JSdocs"
    elif language == "c++":
        return "Doxygen"
    else:
        return "Docs"


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_add_docs_class() -> type:
    """Return the PRAddDocs class for the tool registry factory."""
    return PRAddDocs
