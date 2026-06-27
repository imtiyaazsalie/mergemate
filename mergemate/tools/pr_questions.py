"""PR Ask tool — answer free-form questions about a pull request.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

from mergemate.core.errors import ToolError
from mergemate.log import get_logger
from mergemate.servers.help import HelpMessage
from mergemate.tools.base import BaseTool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a helpful code assistant answering questions about a pull request.
Answer the user's question based on the provided PR information and code diff.
Be concise, accurate, and reference specific files or lines when relevant.

Language of the PR: {{ language }}
"""

DEFAULT_USER_PROMPT = """
## PR Information
- Title: {{ pr_title }}
- Branch: {{ pr_branch }} → {{ pr_base_branch }}

## PR Description
{{ pr_description }}

## Commit Messages
{{ commit_messages_str }}

{% if img_path %}
## Attached Image
![image]({{ img_path }})
{% endif %}

## Changed Files
{{ diff }}

## Question
{{ questions }}
"""

GITLAB_QUICK_ACTIONS = [
    "/approve",
    "/close",
    "/merge",
    "/reopen",
    "/unapprove",
    "/title",
    "/assign",
    "/copy_metadata",
    "/target_branch",
]


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class PRQuestions(BaseTool):
    """Answers free-form questions about a pull request.

    Pipeline:
        1. _prepare() — parse question, detect images, gather diff, build prompts
        2. _predict() — call AI model (with image support, fallback models)
        3. _publish() — sanitize answer, format comment, publish to PR

    Supports image attachments in the question (via `![image](...)` markdown
    or direct image URLs) which are passed to the vision-capable AI model.
    """

    @property
    def tool_name(self) -> str:
        return "ask"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Parse question args, detect images, gather diff, and build prompts."""
        # Parse the question string from args
        self._question_str: str = self._parse_args()

        # Identify any attached image
        self._img_path: str = self._identify_image()

        # Gather diff content from all changed files
        files = self.git_provider.get_diff_files()
        self.context.files = files

        diff_parts: list[str] = []
        for f in files:
            diff_parts.append(f"### {f.filename} ({f.edit_type.value})\n```diff\n{f.patch}\n```")
        diff_str = "\n\n".join(diff_parts)

        # Determine main language
        languages: dict[str, int] = self.git_provider.get_languages()
        main_language: str = ""
        if languages:
            main_language = max({k: v for k, v in languages.items() if isinstance(v, (int, float))}, key=lambda k: languages[k])

        # Get commit messages
        commit_messages = self.git_provider.get_commit_messages()
        commit_messages_str = "\n".join(f"- {msg}" for msg in commit_messages) if commit_messages else ""

        # Build template variables
        self._vars.update(
            {
                "language": main_language,
                "diff": diff_str,
                "questions": self._question_str,
                "commit_messages_str": commit_messages_str,
                "img_path": self._img_path,
            }
        )

        # Get prompts from config (fall back to defaults)
        prompts = self._get_prompts()
        system_template = prompts.get("system") or DEFAULT_SYSTEM_PROMPT
        user_template = prompts.get("user") or DEFAULT_USER_PROMPT

        # Render prompts
        self._system_prompt: str = self._render_prompt(system_template)
        self._user_prompt: str = self._render_prompt(user_template)

        get_logger().debug(
            "Ask prepared",
            pr_url=self.pr_url,
            question=self._question_str,
            has_image=bool(self._img_path),
            file_count=len(files),
        )

    async def _predict(self) -> str:
        """Call the AI model with optional image, trying fallback models on failure."""
        model_cfg = self.config.model
        all_models = [model_cfg.model] + (model_cfg.fallback_models or [])

        last_error: Exception | None = None

        for model in all_models:
            try:
                get_logger().debug(f"Generating ask prediction with {model}")
                response, status = await self.ai_handler.chat_completion(
                    model=model,
                    system=self._system_prompt,
                    user=self._user_prompt,
                    temperature=model_cfg.temperature,
                    img_path=self._img_path,
                )

                if status == "error":
                    raise ToolError(f"AI call failed: {response}", tool=self.tool_name)

                return response

            except Exception as exc:
                last_error = exc
                get_logger().warning(
                    f"Failed to generate prediction with {model}",
                    artifact={"error": str(exc)},
                )

        raise ToolError(
            f"Failed to generate prediction with any model: {all_models}",
            tool=self.tool_name,
        ) from last_error

    async def _publish(self, result: str) -> None:
        """Sanitize the answer and publish it as a PR comment."""
        pr_comment = self._format_answer(result)
        if not self.config.publish_output:
            # Store formatted output for MOSAICO / offline capture
            cap = self.config._raw.get("__output_capture__")
            if cap is not None:
                cap[0] = pr_comment
            get_logger().info("Publish disabled — skipping ask output", pr_url=self.pr_url)
            return

        # Append help text if supported
        tool_cfg = self._get_tool_config()
        is_supported_fn = getattr(self.git_provider, "is_supported", None)
        gfm_supported = is_supported_fn("gfm_markdown") if callable(is_supported_fn) else False
        if gfm_supported and tool_cfg.get("enable_help_text", True):
            pr_comment += (
                "\n<hr>\n\n"
                + "<details> <summary><strong>💡 Tool usage guide:</strong></summary><hr> \n\n"
                + HelpMessage.get_ask_usage_guide()
                + "\n</details>\n"
            )

        self.git_provider.publish_comment(pr_comment)

        get_logger().info("Ask answer published", pr_url=self.pr_url)

    # ------------------------------------------------------------------
    # Ask-specific logic
    # ------------------------------------------------------------------

    def _parse_args(self) -> str:
        """Extract the question string from the tool args."""
        if self.args:
            return " ".join(self.args)
        return ""

    def _identify_image(self) -> str:
        """Detect attached images in the question string.

        Supports:
            - Markdown image syntax: ![image](path)
            - Direct image URLs ending in .png or .jpg
        """
        question = self._question_str

        # Markdown image syntax
        if "![image]" in question:
            img_path = question.split("![image]")[1].strip().strip("()")
            return img_path

        # Direct image URL
        if "https://" in question and (".png" in question or ".jpg" in question):
            img_path = "https://" + question.split("https://")[1]
            return img_path

        return ""

    def _format_answer(self, model_answer: str) -> str:
        """Format the model answer into a markdown PR comment.

        Sanitizes leading '/' characters and applies GitLab-specific protections.
        """
        answer = model_answer.strip()

        # Sanitize leading '/' to prevent unintended quick actions
        answer_sanitized = answer.replace("\n/", "\n /").replace("\r/", "\r /")

        # GitLab-specific: block GitHub-only quick actions
        if self._is_gitlab():
            answer_sanitized = self._gitlab_protections(answer_sanitized)

        if answer_sanitized.startswith("/"):
            answer_sanitized = " " + answer_sanitized

        if answer_sanitized != answer:
            get_logger().debug(
                "Sanitized model answer",
                artifact={"model_answer": answer, "sanitized_answer": answer_sanitized},
            )

        lines = [
            f"### **Ask**❓\n{self._question_str}\n",
            f"### **Answer:**\n{answer_sanitized}\n",
        ]
        return "\n".join(lines)

    def _is_gitlab(self) -> bool:
        """Detect if the current provider is GitLab."""
        provider_name = type(self.git_provider).__name__.lower()
        return "gitlab" in provider_name or self.config.git.provider == "gitlab"

    def _gitlab_protections(self, model_answer: str) -> str:
        """Block GitHub quick actions that are not valid in GitLab."""
        if any(action in model_answer for action in GITLAB_QUICK_ACTIONS):
            get_logger().error("Model answer contains GitHub quick actions, which are not supported in GitLab")
            return "Model answer contains GitHub quick actions, which are not supported in GitLab"
        return model_answer


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_questions_class() -> type:
    """Return the PRQuestions class for the tool registry factory."""
    return PRQuestions
