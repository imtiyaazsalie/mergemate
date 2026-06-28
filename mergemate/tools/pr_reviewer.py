"""PR Review tool — comprehensive pull request analysis.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

from typing import Any

from mergemate.core.errors import ToolError
from mergemate.core.types import FilePatch
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a code review assistant. Your task is to review pull requests
and provide clear, actionable feedback.

Analyze the code changes and provide structured findings. Return your response as a JSON object
with exactly this schema:
{
  "summary": "A concise 2-3 sentence summary of what the PR does",
  "findings": [
    {
      "severity": "critical|major|minor|nitpick",
      "category": "bug|security|performance|style|logic|documentation",
      "file": "path/to/file.py",
      "line": 42,
      "title": "Short finding title",
      "description": "Detailed explanation of the finding",
      "suggestion": "Actionable suggestion for improvement"
    }
  ]
}

Be constructive and professional. Focus on the code, not the author.
Prioritize critical and major findings over minor ones. Include at most 10 findings."""

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

Please provide a thorough code review. Return ONLY valid JSON. No markdown wrapping, no explanations outside the JSON."""

# Token budget: reserve headroom for the AI response (25% of max tokens)
TOKEN_BUDGET_RATIO = 0.75
# Approximate tokens per character for budget estimation
CHARS_PER_TOKEN = 4


class PRReviewer(BaseTool):
    """Reviews a pull request and publishes findings.

    Pipeline:
        1. _prepare() — gather diff, enforce token budget, sort files by importance
        2. _predict() — call AI model with review prompt (with chunking for large PRs)
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
        """Gather PR diff, enforce token budget, and build the review prompt."""
        files = self.git_provider.get_diff_files()
        self.context.files = files

        # Sort by importance: main language first, largest files first
        languages = self.git_provider.get_languages()
        files = self._sort_by_importance(files, languages)

        # Enforce token budget — trim the largest files if needed
        max_tokens = int(self.config.model.max_tokens * TOKEN_BUDGET_RATIO)
        files = self._trim_to_budget(files, max_tokens)

        # Get prompts from config first (needed for token budget estimation)
        prompts = self._get_prompts()
        system_template = prompts.get("system") or DEFAULT_SYSTEM_PROMPT
        user_template = prompts.get("user") or DEFAULT_USER_PROMPT

        # Build template vars for estimation (without files)
        self._vars.update(
            {
                "files": [],  # Placeholder for estimation
            }
        )
        # Estimate prompt overhead (system + user template without file patches)
        estimated_overhead = len(self._render_prompt(system_template)) + len(self._render_prompt(user_template))
        max_tokens = int(self.config.model.max_tokens * TOKEN_BUDGET_RATIO)
        available_for_files = max_tokens - (estimated_overhead // CHARS_PER_TOKEN)

        # Enforce token budget — trim the largest files if needed
        files = self._trim_to_budget(files, available_for_files)

        # Now build full template vars with trimmed files
        self._vars["files"] = [
            {
                "filename": f.filename,
                "patch": f.patch,
                "edit_type": f.edit_type.value,
                "language": f.language or "",
            }
            for f in files
        ]

        # Render final prompts
        self._system_prompt = self._render_prompt(system_template)
        self._user_prompt = self._render_prompt(user_template)

        get_logger().debug(
            "Review prepared",
            pr_url=self.pr_url,
            file_count=len(files),
            estimated_tokens=len(self._system_prompt) // CHARS_PER_TOKEN + len(self._user_prompt) // CHARS_PER_TOKEN,
        )

    async def _predict(self) -> dict[str, Any]:
        """Call the AI model and parse the review response."""
        response, _ = await self._call_ai(
            system=self._system_prompt,
            user=self._user_prompt,
            temperature=0.1,  # Low temperature for precise code review
        )

        return self._parse_review(response)

    async def _publish(self, result: dict[str, Any]) -> None:
        """Publish the review as a PR comment."""
        comment = self._format_review_comment(result)
        if not self.config.publish_output:
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
    # Token budget management
    # ------------------------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from character length."""
        return len(text) // CHARS_PER_TOKEN

    def _trim_to_budget(self, files: list[FilePatch], available_tokens: int) -> list[FilePatch]:
        """Trim the file list to fit within the available token budget.

        Strategy: include files from most to least important until the
        available token budget is exhausted.
        """
        included: list[FilePatch] = []
        total_est = 0

        for f in files:
            file_est = self._estimate_tokens(f.patch) if f.patch else 0
            if total_est + file_est <= available_tokens:
                included.append(f)
                total_est += file_est
            else:
                get_logger().debug(
                    f"Skipping file due to token budget: {f.filename} "
                    f"(need {file_est}, available {available_tokens - total_est})"
                )

        if len(included) < len(files):
            get_logger().info(
                f"Token budget enforced: {len(included)}/{len(files)} files included "
                f"(~{total_est}/{available_tokens} tokens)"
            )

        return included

    # ------------------------------------------------------------------
    # Review-specific logic
    # ------------------------------------------------------------------

    def _sort_by_importance(self, files: list[FilePatch], languages: dict[str, int]) -> list[FilePatch]:
        """Sort files by importance: main language first, then by size."""
        if not languages:
            return files

        lang_counts = {k: v for k, v in languages.items() if isinstance(v, (int, float))}
        main_lang = max(lang_counts, key=lang_counts.get) if lang_counts else ""

        def _sort_key(f: FilePatch) -> tuple[int, int]:
            is_main = 0 if f.language == main_lang else 1
            tokens = max(f.tokens, f.num_plus_lines + f.num_minus_lines, 0)
            return (is_main, -tokens)

        return sorted(files, key=_sort_key)

    def _parse_review(self, response: str) -> dict[str, Any]:
        """Parse the AI response into structured review data with schema validation."""
        import json
        import re

        # Try JSON parsing (strip markdown code fences)
        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", response.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            result = json.loads(cleaned)
            # Validate minimum structure
            if isinstance(result, dict) and "summary" in result:
                result.setdefault("findings", [])
                return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: wrap raw response as summary-only
        get_logger().warning("AI response was not valid JSON — using raw text as summary")
        return {
            "summary": response.strip(),
            "findings": [],
        }

    def _format_review_comment(self, result: dict[str, Any]) -> str:
        """Format review results as a markdown PR comment."""
        lines = ["## 🤖 MergeMate Review", ""]
        lines.append(result.get("summary", ""))
        lines.append("")

        findings = result.get("findings", [])
        if findings:
            lines.append("### 🔍 Findings")
            lines.append("")
            for i, f in enumerate(findings, 1):
                severity_emoji = {"critical": "🔴", "major": "🟠", "minor": "🟡", "nitpick": "⚪"}.get(
                    f.get("severity", ""), "📌"
                )
                lines.append(
                    f"**{i}. {severity_emoji} [{f.get('severity', 'unknown').upper()}] {f.get('title', 'Finding')}**"
                )
                if f.get("file"):
                    lines.append(f"> 📁 `{f['file']}`" + (f":{f['line']}" if f.get("line") else ""))
                if f.get("description"):
                    lines.append(f"")
                    lines.append(f.get("description", ""))
                if f.get("suggestion"):
                    lines.append(f"")
                    lines.append(f"**💡 Suggestion:** {f.get('suggestion', '')}")
                lines.append("")

        return "\n".join(lines)


def get_reviewer_class() -> type[PRReviewer]:
    """Factory for lazy tool loading (used by ToolRegistry)."""
    return PRReviewer
