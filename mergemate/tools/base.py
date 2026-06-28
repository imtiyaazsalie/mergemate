"""Base class for all MergeMate tools.

Provides the shared pipeline that every tool follows:
1. Prepare — gather context, build prompts, process diffs
2. Predict — call the AI model
3. Publish — post results back to the PR

Individual tools only need to implement their specific logic
for each phase, not the orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from jinja2 import Environment, StrictUndefined

from mergemate.core.config import AppConfig
from mergemate.core.errors import ToolError
from mergemate.core.providers import AIHandler, GitProvider
from mergemate.core.types import ToolContext
from mergemate.log import get_logger


class BaseTool(ABC):
    """Abstract base for all PR review tools.

    Subclasses implement `_prepare()`, `_predict()`, and `_publish()`.
    The `run()` method orchestrates the pipeline.

    Dependencies are injected via the constructor — no global state access.
    """

    def __init__(
        self,
        *,
        pr_url: str,
        config: AppConfig,
        git_provider: GitProvider,
        ai_handler: AIHandler,
        context: ToolContext,
        args: list[str] | None = None,
    ) -> None:
        self.pr_url = pr_url
        self.config = config
        self.git_provider = git_provider
        self.ai_handler = ai_handler
        self.context = context
        self.args = args or []

        # Template rendering
        self._jinja = Environment(undefined=StrictUndefined)

        # Per-invocation state
        self._vars: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> Any:
        """Execute the full tool pipeline: prepare → predict → publish."""
        self._vars = self._build_template_vars()

        await self._prepare()
        result = await self._predict()
        await self._publish(result)

        return result

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def _prepare(self) -> None:
        """Gather data, build prompts, process diffs.

        Called after `_vars` is populated. Subclasses should populate
        any additional state needed for prediction.
        """
        ...

    @abstractmethod
    async def _predict(self) -> Any:
        """Call the AI model and return structured results."""
        ...

    @abstractmethod
    async def _publish(self, result: Any) -> None:
        """Post results back to the PR (comments, descriptions, labels, etc.)."""
        ...

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def _build_template_vars(self) -> dict[str, Any]:
        """Build the Jinja2 template variable dictionary.

        Override in subclasses to add tool-specific variables.
        """
        pr = self.context.pr
        return {
            "pr_url": self.pr_url,
            "pr_title": pr.title,
            "pr_description": pr.description,
            "pr_branch": pr.branch,
            "pr_base_branch": pr.base_branch,
        }

    def _render_prompt(self, template_str: str) -> str:
        """Render a Jinja2 template string using current _vars."""
        try:
            template = self._jinja.from_string(template_str)
            return template.render(**self._vars)
        except Exception as exc:
            raise ToolError(f"Failed to render prompt template: {exc}", tool=self.tool_name) from exc

    def _get_prompts(self) -> dict[str, str]:
        """Get the system and user prompts from config."""
        return self.config.get_prompts(self.tool_name)

    def _get_tool_config(self) -> dict[str, Any]:
        """Get this tool's configuration section."""
        return self.config.get_tool_config(f"pr_{self.tool_name}")

    async def _call_ai(self, system: str, user: str, temperature: float | None = None) -> tuple[str, str]:
        """Make an AI completion call with the current model config.

        Args:
            system: System prompt.
            user: User prompt.
            temperature: Override the model's default temperature. If None, uses config value.
        """
        model_cfg = self.config.model
        response, status = await self.ai_handler.chat_completion(
            model=model_cfg.model,
            system=system,
            user=user,
            temperature=temperature if temperature is not None else model_cfg.temperature,
        )

        if status == "error":
            raise ToolError(f"AI call failed: {response}", tool=self.tool_name)

        return response, status

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the canonical tool name (e.g., 'review', 'describe')."""
        ...
