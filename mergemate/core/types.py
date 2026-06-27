"""Core domain types for MergeMate."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EditType(Enum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    UNKNOWN = "unknown"


@dataclass
class FilePatch:
    """Represents a single file change in a pull request."""

    base_file: str
    head_file: str
    patch: str
    filename: str
    tokens: int = -1
    edit_type: EditType = EditType.UNKNOWN
    old_filename: Optional[str] = None
    num_plus_lines: int = -1
    num_minus_lines: int = -1
    language: Optional[str] = None
    ai_file_summary: Optional[str] = None


@dataclass
class PullRequest:
    """Minimal representation of a pull request being reviewed."""

    url: str
    title: str = ""
    description: str = ""
    branch: str = ""
    base_branch: str = ""
    owner: str = ""
    repo: str = ""
    number: int = 0


@dataclass
class ReviewResult:
    """Output from a review operation."""

    summary: str = ""
    findings: list[dict] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)
    approved: bool = False


@dataclass
class ToolContext:
    """Context passed to all tools during execution."""

    pr: PullRequest
    files: list[FilePatch] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
