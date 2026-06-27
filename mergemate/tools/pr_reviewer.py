"""PR Review tool — comprehensive pull request analysis.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

from typing import Any

from mergemate.core.config import AppConfig
from mergemate.core.errors import ToolError
from mergemate.core.providers import AIHandler, GitProvider
from mergemate.core.types import FilePatch, ToolContext
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a code review assistant. Your task is to review pull requests
and provide clear, actionable feedback.

Analyze the code changes and provide:
1. A concise summary of what the PR does
2. Key findings — potential bugs, security issues, performance concerns
3. Specific suggestions for improvement

Be constructive and professional. Focus on the code, not the author."""

DEFAULT_USER_PROMPT = """
## PR Information
- Title: {{ pr_title }}
- Branch: {{ pr_branch }} → {{ pr_base_branch }}

## PR Description
{{ pr_description }}

## Changed Files
{% for file in files %}
### {{ file.filename }} ({{ file.edit_type }})
```diff
{{ file.patch }}
```
{% endfor %}

Please provide a thorough code review.
"""


class PRReviewer(BaseTool):
    """Reviews a pull request and publishes findings.

    Pipeline:
        1. _prepare() — gather diff, build prompts, handle token limits
        2. _predict() — call AI model with review prompt
        3. _publish() — post review findings as PR comment

    Dependencies are injected via constructor, making this testable
    with mock providers and handlers.
    """

    @property
    def tool_name(self) -> str:
        return "review"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Gather PR diff and build the review prompt."""
        # Get the diff files
        files = self.git_provider.get_diff_files()
        self.context.files = files

        # Filter and sort files
        languages = self.git_provider.get_languages()
        files = self._sort_by_importance(files, languages)

        # Build template variables
        self._vars["files"] = [
            {
                "filename": f.filename,
                "patch": f.patch,
                "edit_type": f.edit_type.value,
                "language": f.language or "",
            }
            for f in files
        ]

        # Get prompts from config (fall back to defaults)
        prompts = self._get_prompts()
        system_template = prompts.get("system") or DEFAULT_SYSTEM_PROMPT
        user_template = prompts.get("user") or DEFAULT_USER_PROMPT

        # Render prompts
        self._system_prompt = self._render_prompt(system_template)
        self._user_prompt = self._render_prompt(user_template)

        get_logger().debug(
            "Review prepared",
            pr_url=self.pr_url,
            file_count=len(files),
            prompt_tokens=len(self._system_prompt) + len(self._user_prompt),
        )

    async def _predict(self) -> dict[str, Any]:
        """Call the AI model and parse the review response."""
        response, _ = await self._call_ai(
            system=self._system_prompt,
            user=self._user_prompt,
        )

        # Parse the response into structured findings
        result = self._parse_review(response)
        return result

    async def _publish(self, result: dict[str, Any]) -> None:
        """Publish the review as a PR comment."""
        comment = self._format_review_comment(result)
        if not self.config.publish_output:
            # Store formatted output for MOSAICO / offline capture
            cap = self.config._raw.get("__output_capture__")
            if cap is not None:
                cap[0] = comment
            get_logger().info("Publish disabled — skipping review output", pr_url=self.pr_url)
            return

        self.git_provider.publish_comment(comment)

        get_logger().info(
            "Review published",
            pr_url=self.pr_url,
            finding_count=len(result.get("findings", [])),
        )

    # ------------------------------------------------------------------
    # Review-specific logic
    # ------------------------------------------------------------------

    def _sort_by_importance(self, files: list[FilePatch], languages: dict[str, int]) -> list[FilePatch]:
        """Sort files by importance: main language first, then by size."""
        if not languages:
            return files

        # Find the dominant language
        main_lang = max(languages, key=languages.get) if languages else ""

        def _sort_key(f: FilePatch) -> tuple[int, int]:
            is_main = 0 if f.language == main_lang else 1
            tokens = max(f.tokens, f.num_plus_lines + f.num_minus_lines, 0)
            return (is_main, -tokens)  # Main language first, largest files first

        return sorted(files, key=_sort_key)

    def _parse_review(self, response: str) -> dict[str, Any]:
        """Parse the AI response into structured review data."""
        import json
        import re

        # Try JSON parsing
        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", response.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: use the entire markdown response as-is
        return {
            "summary": response.strip(),
            "findings": [],
        }

    def _format_review_comment(self, result: dict[str, Any]) -> str:
        """Format review results as a markdown PR comment."""
        lines = ["## 🤖 MergeMate Review", ""]

        # If we have the raw response and the summary is just the response itself,
        # use it directly (model returned formatted markdown)
        summary = result.get("summary", "")
        if summary:
            lines.append(summary)
            lines.append("")

        # Findings (only if structured JSON was returned)
        findings = result.get("findings", [])
        if findings:
            lines.append("### Key Findings")
            lines.append("")
            for i, finding in enumerate(findings, 1):
                if isinstance(finding, dict):
                    title = finding.get("title", finding.get("issue", f"Finding {i}"))
                    desc = finding.get("description", finding.get("suggestion", ""))
                    severity = finding.get("severity", "")
                    lines.append(f"**{i}. {title}** {severity}")
                    if desc:
                        lines.append(f"   {desc}")
                    lines.append("")
                else:
                    lines.append(f"{i}. {finding}")
                    lines.append("")

        suggestions = result.get("suggestions", [])
        if suggestions:
            lines.append("### Suggestions")
            lines.append("")
            for s in suggestions:
                if isinstance(s, dict):
                    lines.append(f"- **{s.get('title', 'Suggestion')}**: {s.get('description', '')}")
                else:
                    lines.append(f"- {s}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_reviewer_class() -> type:
    """Return the PRReviewer class for the tool registry factory."""
    return PRReviewer
