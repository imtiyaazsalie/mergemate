"""PR Generate Labels tool — generates labels for a pull request.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

import copy
from typing import List

from jinja2 import Environment, StrictUndefined

from mergemate.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from mergemate.algo.token_handler import TokenHandler
from mergemate.algo.utils import get_user_labels, load_yaml, set_custom_labels
from mergemate.config_loader import get_settings
from mergemate.git_providers.git_provider import get_main_pr_language
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool


class PRGenerateLabels(BaseTool):
    """Generates PR labels using an AI model and publishes them.

    Pipeline:
        1. _prepare() — gather diff, build prompts, set custom labels
        2. _predict() — call AI model to generate labels
        3. _publish() — parse labels and publish to PR
    """

    @property
    def tool_name(self) -> str:
        return "generate_labels"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Gather PR diff and build label generation prompts."""
        self.main_pr_language = get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())

        self.patches_diff = None
        self.prediction = None

        self._vars.update(
            {
                "title": self.context.pr.title,
                "branch": self.context.pr.branch,
                "description": self.git_provider.get_pr_description_full(),
                "language": self.main_pr_language,
                "diff": "",
                "extra_instructions": get_settings().pr_description.extra_instructions,
                "commit_messages_str": self.git_provider.get_commit_messages(),
                "enable_custom_labels": get_settings().config.enable_custom_labels,
                "custom_labels_class": "",
            }
        )

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self._vars,
            get_settings().pr_custom_labels_prompt.system,
            get_settings().pr_custom_labels_prompt.user,
        )

        get_logger().info(f"Generating PR labels {self.context.pr.number}")
        await retry_with_fallback_models(self._prepare_prediction)

    async def _predict(self) -> List[str]:
        """Parse AI response into label list."""
        if not self.prediction:
            return []
        self._prepare_data()
        return self._prepare_labels()

    async def _publish(self, result: List[str]) -> None:
        """Publish generated labels to the PR."""
        if not self.config.publish_output:
            get_logger().info("Publish disabled — skipping label output", pr_url=self.pr_url)
            return

        current_labels = self.git_provider.get_pr_labels()
        user_labels = get_user_labels(current_labels)
        pr_labels = result + user_labels

        if self.git_provider.is_supported("get_labels"):
            self.git_provider.publish_labels(pr_labels)
        elif pr_labels:
            value = ", ".join(v for v in pr_labels)
            pr_labels_text = f"## PR Labels:\n{value}\n"
            self.git_provider.publish_comment(pr_labels_text, is_temporary=False)

    # ------------------------------------------------------------------
    # Labels-specific logic
    # ------------------------------------------------------------------

    async def _prepare_prediction(self, model: str) -> None:
        get_logger().info(f"Getting PR diff {self.context.pr.number}")
        self.patches_diff = get_pr_diff(self.git_provider, self.token_handler, model)
        get_logger().info(f"Getting AI prediction {self.context.pr.number}")
        self.prediction = await self._get_prediction(model)

    async def _get_prediction(self, model: str) -> str:
        variables = copy.deepcopy(self._vars)
        variables["diff"] = self.patches_diff

        environment = Environment(undefined=StrictUndefined)
        set_custom_labels(variables, self.git_provider)
        self.variables = variables

        system_prompt = environment.from_string(get_settings().pr_custom_labels_prompt.system).render(self.variables)
        user_prompt = environment.from_string(get_settings().pr_custom_labels_prompt.user).render(self.variables)

        response, _finish_reason = await self.ai_handler.chat_completion(
            model=model,
            temperature=self.config.model.temperature,
            system=system_prompt,
            user=user_prompt,
        )
        return response

    def _prepare_data(self) -> None:
        self.data = load_yaml(self.prediction.strip())

    def _prepare_labels(self) -> List[str]:
        pr_types: List[str] = []
        if "labels" in self.data:
            if type(self.data["labels"]) == list:
                pr_types = self.data["labels"]
            elif type(self.data["labels"]) == str:
                pr_types = self.data["labels"].split(",")
        pr_types = [label.strip() for label in pr_types]

        try:
            if "labels_minimal_to_labels_dict" in self.variables:
                d: dict = self.variables["labels_minimal_to_labels_dict"]
                for i, label_i in enumerate(pr_types):
                    if label_i in d:
                        pr_types[i] = d[label_i]
        except Exception as e:
            get_logger().error(f"Error converting labels to original case {self.context.pr.number}: {e}")

        return pr_types


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_generate_labels_class() -> type:
    """Return the PRGenerateLabels class for the tool registry factory."""
    return PRGenerateLabels
