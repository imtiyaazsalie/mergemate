"""Provider interfaces for MergeMate.

Defines protocols for AI handlers and git providers.
Tools depend on these protocols, not concrete implementations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from mergemate.core.types import FilePatch, PullRequest


@runtime_checkable
class AIHandler(Protocol):
    """Protocol for AI model handlers.

    Any class implementing chat_completion() satisfies this protocol.
    No need to inherit from an ABC — structural subtyping is used.
    """

    async def chat_completion(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        img_path: str = "",
    ) -> tuple[str, str]:
        """Send a chat completion request to the AI model.

        Returns:
            Tuple of (response_text, status) where status is 'ok' or 'error'.
        """
        ...


@runtime_checkable
class GitProvider(Protocol):
    """Protocol for git hosting providers.

    Implementations handle PR data retrieval, comment publishing,
    and provider-specific operations for GitHub, GitLab, Bitbucket, etc.
    """

    def get_pr(self) -> PullRequest:
        """Return the pull request being processed."""
        ...

    def get_diff_files(self) -> list[FilePatch]:
        """Get the list of changed files in the PR."""
        ...

    def get_files(self) -> list[dict]:
        """Get all files in the PR."""
        ...

    def get_languages(self) -> dict[str, int]:
        """Get language breakdown of PR files."""
        ...

    def publish_comment(self, comment: str, **kwargs: Any) -> None:
        """Publish a comment on the PR."""
        ...

    def publish_description(self, title: str, description: str) -> None:
        """Update the PR description and title."""
        ...

    def publish_code_suggestions(self, suggestions: list[dict]) -> None:
        """Publish code suggestions as inline comments."""
        ...

    def get_repo_settings(self) -> str | None:
        """Fetch repository-level .mergemate.toml content."""
        ...

    def get_pr_description_full(self) -> str:
        """Get the full PR description body."""
        ...

    def get_commit_messages(self) -> list[str]:
        """Get commit messages for this PR."""
        ...

    def generate_link_to_relevant_line_number(self, filename: str, line: int) -> str:
        """Generate a permalink to a specific line in a file."""
        ...

    @property
    def pr_url(self) -> str:
        """The URL of the pull request."""
        ...

    @property
    def is_supported(self) -> bool:
        """Whether this provider supports all required operations."""
        ...
