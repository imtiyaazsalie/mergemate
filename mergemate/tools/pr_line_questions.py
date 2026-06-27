"""PR Ask Line tool — answer questions about specific lines in a pull request.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

from mergemate.algo.git_patch_processing import extract_hunk_lines_from_patch
from mergemate.core.errors import ToolError
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a helpful code assistant answering questions about specific lines in a pull request.
Answer the user's question based on the provided code context and line-specific diff.
Be concise, accurate, and reference specific lines when relevant.

Language of the PR: {{ language }}
"""

DEFAULT_USER_PROMPT = """
## PR Information
- Title: {{ pr_title }}
- Branch: {{ pr_branch }}

## Selected Code Context
### Full Hunk
{{ full_hunk }}

### Selected Lines
{{ selected_lines }}

{% if conversation_history %}
## Conversation History
{{ conversation_history }}
{% endif %}

## Question
{{ question }}
"""


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class PRLineQuestions(BaseTool):
    """Answers questions about specific lines in a pull request.

    Pipeline:
        1. _prepare() — parse question, extract line-specific diff, load
           conversation history, build prompts
        2. _predict() — call AI model with line-focused context
        3. _publish() — sanitize answer, reply to thread or post comment

    Unlike the ask tool which looks at the entire PR, this tool focuses
    on a specific hunk of code identified by file + line range.
    """

    @property
    def tool_name(self) -> str:
        return "ask_line"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Parse question, extract line-specific diff, load history, build prompts."""
        # Parse the question string from args
        self._question_str: str = self._parse_args()

        # Extract per-invocation runtime settings from context metadata
        ctx_meta = self.context.metadata
        self._ask_diff_hunk: str = str(ctx_meta.get("ask_diff_hunk", ""))
        self._line_start: str = str(ctx_meta.get("line_start", ""))
        self._line_end: str = str(ctx_meta.get("line_end", ""))
        self._side: str = str(ctx_meta.get("side", "RIGHT"))
        self._file_name: str = str(ctx_meta.get("file_name", ""))
        self._comment_id: str = str(ctx_meta.get("comment_id", ""))

        # Extract the line-specific patch
        self._patch_with_lines: str
        self._selected_lines: str
        self._patch_with_lines, self._selected_lines = self._extract_hunk()

        # Load conversation history if enabled and supported
        self._conversation_history: str = ""
        tool_cfg = self._get_tool_config()
        if tool_cfg.get("use_conversation_history", False):
            self._conversation_history = self._load_conversation_history()

        # Determine main language
        languages: dict[str, int] = self.git_provider.get_languages()
        main_language: str = ""
        if languages:
            main_language = max(languages, key=lambda k: languages[k])

        # Build template variables
        self._vars.update(
            {
                "language": main_language,
                "full_hunk": self._patch_with_lines,
                "selected_lines": self._selected_lines,
                "question": self._question_str,
                "conversation_history": self._conversation_history,
            }
        )

        # Get prompts from config (fall back to defaults)
        prompts = self._get_prompts()
        system_template = prompts.get("system") or DEFAULT_SYSTEM_PROMPT
        user_template = prompts.get("user") or DEFAULT_USER_PROMPT

        # Render prompts
        self._system_prompt: str = self._render_prompt(system_template)
        self._user_prompt: str = self._render_prompt(user_template)

        if self.config.verbosity_level >= 2:
            get_logger().debug(
                "Ask line system prompt",
                artifact={"system_prompt": self._system_prompt},
            )
            get_logger().debug(
                "Ask line user prompt",
                artifact={"user_prompt": self._user_prompt},
            )

        get_logger().debug(
            "Ask line prepared",
            pr_url=self.pr_url,
            file_name=self._file_name,
            line_start=self._line_start,
            line_end=self._line_end,
            has_history=bool(self._conversation_history),
        )

    async def _predict(self) -> str:
        """Call the AI model with line-specific context, trying fallback models."""
        model_cfg = self.config.model
        all_models = [model_cfg.model] + (model_cfg.fallback_models or [])

        last_error: Exception | None = None

        for model in all_models:
            try:
                get_logger().debug(f"Generating ask_line prediction with {model}")
                response, status = await self.ai_handler.chat_completion(
                    model=model,
                    system=self._system_prompt,
                    user=self._user_prompt,
                    temperature=model_cfg.temperature,
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
        """Sanitize the answer and publish it to the PR."""
        if not self._patch_with_lines:
            get_logger().warning("Empty hunk — skipping publish", pr_url=self.pr_url)
            return

        if not self.config.publish_output:
            get_logger().info("Publish disabled — skipping ask_line output", pr_url=self.pr_url)
            return

        answer_sanitized = self._sanitize_answer(result)

        get_logger().info("Preparing answer...")

        # Reply to a specific review thread comment, or publish a new comment
        if self._comment_id:
            reply_fn = getattr(self.git_provider, "reply_to_comment_from_comment_id", None)
            if reply_fn is not None:
                reply_fn(self._comment_id, answer_sanitized)
                get_logger().info("Replied to comment", comment_id=self._comment_id)
            else:
                self.git_provider.publish_comment(answer_sanitized)
        else:
            self.git_provider.publish_comment(answer_sanitized)
            get_logger().info("Published ask_line answer", pr_url=self.pr_url)

    # ------------------------------------------------------------------
    # Ask Line-specific logic
    # ------------------------------------------------------------------

    def _parse_args(self) -> str:
        """Extract the question string from the tool args."""
        if self.args:
            return " ".join(self.args)
        return ""

    def _extract_hunk(self) -> tuple[str, str]:
        """Extract line-specific hunk from the PR diff.

        Uses the provided hunk directly from settings (when available)
        or looks up the file in the PR diff files.

        Returns:
            Tuple of (patch_with_lines_str, selected_lines_str).
        """
        patch = self._ask_diff_hunk
        file_name = self._file_name
        line_start = self._line_start
        line_end = self._line_end
        side = self._side

        if patch:
            return extract_hunk_lines_from_patch(
                patch,
                file_name,
                line_start=line_start,
                line_end=line_end,
                side=side,
            )

        # Fall back to searching diff files
        diff_files = self.git_provider.get_diff_files()
        for file in diff_files:
            if file.filename == file_name:
                return extract_hunk_lines_from_patch(
                    file.patch,
                    file.filename,
                    line_start=line_start,
                    line_end=line_end,
                    side=side,
                )

        return "", ""

    def _load_conversation_history(self) -> str:
        """Load the review thread conversation history for context.

        Only works when comment_id, file_name, and line_end are all provided.
        Currently requires GitHub provider (uses get_review_thread_comments).

        Returns:
            Formatted conversation history string, or empty string on failure.
        """
        comment_id = self._comment_id
        file_path = self._file_name
        line_number = self._line_end

        # Early return if any required parameter is missing
        if not all([comment_id, file_path, line_number]):
            get_logger().error("Missing required parameters for conversation history")
            return ""

        # Check if provider supports thread comments
        get_review_thread_comments = getattr(self.git_provider, "get_review_thread_comments", None)
        if get_review_thread_comments is None:
            get_logger().debug("Provider does not support review thread comments")
            return ""

        try:
            thread_comments = get_review_thread_comments(comment_id)

            # Filter and prepare comments
            filtered_comments: list[tuple[str, str]] = []
            for comment in thread_comments:
                body = getattr(comment, "body", "")

                # Skip empty comments and the current comment
                if not body or not body.strip() or str(getattr(comment, "id", "")) == str(comment_id):
                    continue

                user = getattr(comment, "user", None)
                author = user.login if user is not None and hasattr(user, "login") else "Unknown"
                filtered_comments.append((author, body))

            if filtered_comments:
                comment_count = len(filtered_comments)
                get_logger().info(f"Loaded {comment_count} comments from the code review thread")

                conversation_history_str = "\n".join(
                    f"{i + 1}. {author}: {body}" for i, (author, body) in enumerate(filtered_comments)
                )
                return conversation_history_str

            return ""

        except Exception as exc:
            get_logger().error(f"Error processing conversation history, error: {exc}")
            return ""

    def _sanitize_answer(self, model_answer: str) -> str:
        """Sanitize the model answer to prevent unintended quick actions."""
        answer = model_answer.strip()

        # Prevent lines starting with '/' which could trigger quick actions
        answer_sanitized = answer.replace("\n/", "\n /")
        if answer_sanitized.startswith("/"):
            answer_sanitized = " " + answer_sanitized

        return answer_sanitized


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_line_questions_class() -> type:
    """Return the PRLineQuestions class for the tool registry factory."""
    return PRLineQuestions
