"""PR Update Changelog tool — generates changelog entries from PR changes.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

import copy
from datetime import date
from time import sleep
from typing import Tuple

from jinja2 import Environment, StrictUndefined

from mergemate.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import ModelType
from mergemate.config_loader import get_settings
from mergemate.git_providers.git_provider import get_main_pr_language
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool

CHANGELOG_LINES = 50


class PRUpdateChangelog(BaseTool):
    """Generates changelog entries for a PR and optionally pushes them.

    Pipeline:
        1. _prepare() — gather diff, get changelog file, build prompts
        2. _predict() — call AI model to generate changelog content
        3. _publish() — push changelog update or post as comment
    """

    @property
    def tool_name(self) -> str:
        return "update_changelog"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Gather PR diff, determine main language, and fetch changelog file."""
        self.main_language = get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())
        self.commit_changelog = get_settings().pr_update_changelog.push_changelog_changes
        self._get_changelog_file()

        self.patches_diff = None
        self.prediction = None

        self._vars.update(
            {
                "title": self.context.pr.title,
                "branch": self.context.pr.branch,
                "description": self.context.pr.description,
                "language": self.main_language,
                "diff": "",
                "pr_link": "",
                "changelog_file_str": self.changelog_file_str,
                "today": date.today(),
                "extra_instructions": get_settings().pr_update_changelog.extra_instructions,
                "commit_messages_str": self.git_provider.get_commit_messages(),
            }
        )

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self._vars,
            get_settings().pr_update_changelog_prompt.system,
            get_settings().pr_update_changelog_prompt.user,
        )

        get_logger().info("Preparing changelog update...")
        await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.WEAK)

    async def _predict(self) -> str:
        """Return the generated changelog content and prepared file content."""
        new_file_content, answer = self._prepare_changelog_update()
        return {"new_file_content": new_file_content, "answer": answer}

    async def _publish(self, result: dict[str, str]) -> None:
        """Push changelog update or publish as a comment."""
        answer = result["answer"]
        new_file_content = result["new_file_content"]

        if not self.config.publish_output:
            get_logger().info("Publish disabled — skipping changelog output", pr_url=self.pr_url)
            return

        if self.commit_changelog:
            self._push_changelog_update(new_file_content, answer)
        else:
            self.git_provider.publish_comment(f"**Changelog updates:** 🔄\n\n{answer}")

    # ------------------------------------------------------------------
    # Changelog-specific logic
    # ------------------------------------------------------------------

    async def _prepare_prediction(self, model: str) -> None:
        self.patches_diff = get_pr_diff(self.git_provider, self.token_handler, model)
        if self.patches_diff:
            get_logger().debug("PR diff", artifact=self.patches_diff)
            self.prediction = await self._get_prediction(model)
        else:
            get_logger().error("Error getting PR diff")
            self.prediction = ""

    async def _get_prediction(self, model: str) -> str:
        variables = copy.deepcopy(self._vars)
        variables["diff"] = self.patches_diff
        if get_settings().pr_update_changelog.add_pr_link:
            variables["pr_link"] = self.git_provider.pr_url
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_update_changelog_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_update_changelog_prompt.user).render(variables)
        response, _finish_reason = await self.ai_handler.chat_completion(
            model=model,
            system=system_prompt,
            user=user_prompt,
            temperature=self.config.model.temperature,
        )
        response = response.strip()
        if not response:
            return ""
        if response.startswith("```"):
            response_lines = response.splitlines()
            response_lines = response_lines[1:]
            response = "\n".join(response_lines)
        response = response.strip("`")
        return response

    def _prepare_changelog_update(self) -> Tuple[str, str]:
        answer = self.prediction.strip().strip("```").strip()  # noqa B005
        existing_content = getattr(self, "changelog_file", "")
        if existing_content:
            new_file_content = answer + "\n\n" + self.changelog_file
        else:
            new_file_content = answer
        if not self.commit_changelog:
            answer += (
                "\n\n\n>to commit the new content to the CHANGELOG.md file, please type:"
                "\n>'/update_changelog --pr_update_changelog.push_changelog_changes=true'\n"
            )
        return new_file_content, answer

    def _push_changelog_update(self, new_file_content: str, answer: str) -> None:
        if get_settings().pr_update_changelog.get("skip_ci_on_push", True):
            commit_message = "[skip ci] Update CHANGELOG.md"
        else:
            commit_message = "Update CHANGELOG.md"
        self.git_provider.create_or_update_pr_file(
            file_path="CHANGELOG.md",
            branch=self.git_provider.get_pr_branch(),
            contents=new_file_content,
            message=commit_message,
        )
        sleep(5)
        try:
            if get_settings().config.git_provider == "github":
                last_commit_id = list(self.git_provider.pr.get_commits())[-1]
                d = dict(
                    body="CHANGELOG.md update",
                    path="CHANGELOG.md",
                    line=max(2, len(answer.splitlines())),
                    start_line=1,
                )
                self.git_provider.pr.create_review(commit=last_commit_id, comments=[d])
        except Exception:
            self.git_provider.publish_comment(f"**Changelog updates:** 🔄\n\n{answer}")

    def _get_default_changelog(self) -> str:
        return "\nExample:\n## <current_date>\n\n### Added\n...\n### Changed\n...\n### Fixed\n...\n"

    def _get_changelog_file(self) -> None:
        try:
            self.changelog_file = self.git_provider.get_pr_file_content(
                "CHANGELOG.md", self.git_provider.get_pr_branch()
            )
            if isinstance(self.changelog_file, bytes):
                self.changelog_file = self.changelog_file.decode("utf-8")
            changelog_file_lines = self.changelog_file.splitlines()
            changelog_file_lines = changelog_file_lines[:CHANGELOG_LINES]
            self.changelog_file_str = "\n".join(changelog_file_lines)
        except Exception as e:
            get_logger().warning(f"Error getting changelog file: {e}")
            self.changelog_file_str = ""
            self.changelog_file = ""

        if not self.changelog_file_str:
            self.changelog_file_str = self._get_default_changelog()


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_update_changelog_class() -> type:
    """Return the PRUpdateChangelog class for the tool registry factory."""
    return PRUpdateChangelog
